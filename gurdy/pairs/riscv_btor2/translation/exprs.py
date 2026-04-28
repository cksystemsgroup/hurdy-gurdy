"""Tiny expression language used in spec strings.

Constraint / property / learned-fact expressions in the spec carry
their bodies as strings. We support a small s-expression-like
syntax that the translator parses into BTOR2 nodes:

    reg(N)          -- current value of register N (bv64)
    mem(addr, w)    -- memory at addr, width w bytes (bv(8w))
    pc              -- current PC
    const(value)    -- 64-bit constant (decimal or 0x...)
    eq(a, b)        -- a == b -> bv1
    neq(a, b)       -- a != b
    lt(a, b)        -- signed
    le(a, b)
    gt(a, b)
    ge(a, b)
    ltu(a, b)       -- unsigned
    leu(a, b)
    gtu(a, b)
    geu(a, b)
    add(a, b)
    sub(a, b)
    and(a, b)
    or(a, b)
    xor(a, b)
    not(a)
    true
    false

Returned nids are bv64 unless stated otherwise; comparisons return
bv1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from gurdy.pairs.riscv_btor2.translation.builder import Builder


_TOKEN_RE = re.compile(r"\s*([(),]|0x[0-9A-Fa-f]+|-?\d+|[A-Za-z_][A-Za-z_0-9.]*)")


def _tokenize(s: str) -> list[str]:
    out: list[str] = []
    pos = 0
    while pos < len(s):
        m = _TOKEN_RE.match(s, pos)
        if not m:
            if s[pos].isspace():
                pos += 1
                continue
            raise ValueError(f"unexpected character {s[pos]!r} at position {pos}")
        out.append(m.group(1))
        pos = m.end()
    return out


@dataclass
class _Cursor:
    tokens: list[str]
    i: int = 0

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self) -> str:
        t = self.tokens[self.i]
        self.i += 1
        return t

    def expect(self, expected: str) -> None:
        t = self.take()
        if t != expected:
            raise ValueError(f"expected {expected!r} got {t!r}")


@dataclass
class ExprContext:
    """Resolved nids the parser uses to encode references."""

    builder: Builder
    reg_nid: dict[int, int]
    """Index N -> bv64 nid representing the *current* value of regN.
    Index 0 is the bv64 zero const."""

    pc_nid: int
    mem_nid: int


def parse_and_emit(expr: str, ctx: ExprContext) -> int:
    """Parse ``expr`` and emit BTOR2 nodes; return the result nid."""
    cur = _Cursor(_tokenize(expr))
    nid = _parse_expr(cur, ctx)
    if cur.peek() is not None:
        raise ValueError(f"trailing tokens at position {cur.i}: {cur.tokens[cur.i:]}")
    return nid


def _parse_expr(cur: _Cursor, ctx: ExprContext) -> int:
    t = cur.take()
    if t == "true":
        return ctx.builder.const("bv1", 1)
    if t == "false":
        return ctx.builder.const("bv1", 0)
    if t == "pc":
        return ctx.pc_nid
    if t.startswith("0x"):
        return ctx.builder.const("bv64", int(t, 16))
    if t.lstrip("-").isdigit():
        return ctx.builder.const("bv64", int(t) & 0xFFFFFFFFFFFFFFFF)
    # function call
    if cur.peek() != "(":
        raise ValueError(f"expected '(' after {t!r}")
    cur.take()  # (
    args = _parse_args(cur, ctx)
    cur.expect(")")
    return _apply(t, args, ctx)


def _parse_args(cur: _Cursor, ctx: ExprContext) -> list[int]:
    args: list[int] = []
    if cur.peek() == ")":
        return args
    while True:
        # Args are either nested expressions or raw integers (which we
        # treat as bv64 constants for arithmetic; for reg/mem, we expect
        # ints). Simpler: just parse expr.
        # However, reg(N), mem(A,W) need integer literals not nids; so
        # we look ahead: if the head is a digit and the next token is
        # ',' or ')', it's an integer literal — we stash it; otherwise
        # we parse an expression.
        head = cur.peek()
        if head is not None and (
            head.startswith("0x") or head.lstrip("-").isdigit()
        ) and len(cur.tokens) > cur.i + 1 and cur.tokens[cur.i + 1] in (",", ")"):
            tok = cur.take()
            args.append(_RawInt(int(tok, 0) if tok.startswith("0x") else int(tok)))  # type: ignore
        else:
            args.append(_parse_expr(cur, ctx))
        if cur.peek() == ",":
            cur.take()
            continue
        return args


class _RawInt(int):
    """Sentinel: an integer literal not yet resolved to a BTOR2 const."""


def _apply(name: str, args: list[Any], ctx: ExprContext) -> int:
    b = ctx.builder
    if name == "reg":
        if len(args) != 1:
            raise ValueError("reg expects 1 argument")
        n = int(args[0])
        if not 0 <= n < 32:
            raise ValueError(f"reg index out of range: {n}")
        return ctx.reg_nid[n]
    if name == "mem":
        if len(args) != 2:
            raise ValueError("mem expects 2 arguments (addr, width)")
        addr = int(args[0])
        width = int(args[1])
        addr_nid = b.const("bv64", addr)
        # Compose width bytes little-endian.
        if width == 1:
            return b.read("bv8", ctx.mem_nid, addr_nid)
        nbytes: list[int] = []
        for i in range(width):
            off = b.add("bv64", addr_nid, b.const("bv64", i))
            nbytes.append(b.read("bv8", ctx.mem_nid, off))
        acc = nbytes[0]
        for i in range(1, width):
            acc = b.concat(f"bv{8 * (i + 1)}", nbytes[i], acc)
        return acc
    if name == "const":
        if len(args) != 1:
            raise ValueError("const expects 1 argument")
        return b.const("bv64", int(args[0]) & 0xFFFFFFFFFFFFFFFF)
    if name in {"eq", "neq"}:
        a, c = args
        a_nid = _to_nid(a, ctx)
        c_nid = _to_nid(c, ctx)
        return (b.eq if name == "eq" else b.neq)(a_nid, c_nid)
    if name in {"lt", "le", "gt", "ge"}:
        a, c = args
        a_nid = _to_nid(a, ctx)
        c_nid = _to_nid(c, ctx)
        return {
            "lt": b.slt,
            "le": lambda x, y: b.emit("slte", "bv1", x, y),
            "gt": b.sgt,
            "ge": lambda x, y: b.emit("sgte", "bv1", x, y),
        }[name](a_nid, c_nid)
    if name in {"ltu", "leu", "gtu", "geu"}:
        a, c = args
        a_nid = _to_nid(a, ctx)
        c_nid = _to_nid(c, ctx)
        return {
            "ltu": b.ult,
            "leu": lambda x, y: b.emit("ulte", "bv1", x, y),
            "gtu": lambda x, y: b.emit("ugt", "bv1", x, y),
            "geu": b.uge,
        }[name](a_nid, c_nid)
    if name in {"add", "sub", "and", "or", "xor"}:
        a, c = args
        a_nid = _to_nid(a, ctx)
        c_nid = _to_nid(c, ctx)
        return {
            "add": b.add,
            "sub": b.sub,
            "and": b.and_,
            "or": b.or_,
            "xor": b.xor,
        }[name]("bv64", a_nid, c_nid)
    if name == "not":
        a, = args
        return b.not_("bv1", _to_nid(a, ctx))
    raise ValueError(f"unknown function {name!r}")


def _to_nid(v: Any, ctx: ExprContext) -> int:
    if isinstance(v, _RawInt):
        return ctx.builder.const("bv64", int(v) & 0xFFFFFFFFFFFFFFFF)
    return int(v)


__all__ = ["ExprContext", "parse_and_emit"]
