"""sail -> BTOR2 translator (pairs/sail-btor2).

Lowers a Sail program (the RISC-V model applied to a program) into a BTOR2
transition system. The state skeleton and PC-keyed ITE dispatch are the same
shape as ``riscv-btor2``, but each instruction's write-back datapath is lowered
from the Sail-derived ``Expr`` execute tree (``languages/sail/rv64.EXEC``) via
``expr.lower`` — *not* from the hand-written per-opcode rules of
``riscv-btor2``. That independence is what lets the indirect RISC-V→BTOR2 route
cross-check the direct one (PATHS.md §4-5).

Scope: the ALU + control-flow + load/store slice (``rv64.decode``) +
ECALL/EBREAK (halt); data memory is an ``Array bv64 bv8``. Other opcodes
hard-abort with ``Unsupported``. Deterministic in the program.
"""

from __future__ import annotations

import json
from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.build import Builder
from ...languages.sail import expr
from ...languages.sail.rv64 import MASK64, decode, operands

NREG = 32


def _unwrap(program: Any) -> dict:
    """Accept the sail-program dict directly, a predecessor's JSON bytes (from
    ``riscv-sail``), or a ``{"sail": ...}`` wrapper."""
    if isinstance(program, (bytes, bytearray, str)):
        text = program.decode() if isinstance(program, (bytes, bytearray)) else program
        program = json.loads(text)
    if "sail" in program:
        program = program["sail"]
    return program


def _is_ecall(instr: int) -> bool:
    return (instr & 0x7F) == 0x73 and ((instr >> 12) & 0x7) == 0 and (instr >> 20) in (0, 1)


def _uses_memory(words: list[int]) -> bool:
    return any((w & 0x7F) in (0x03, 0x23) for w in words)


def _load_nodes(b: Builder, mem: int, addr: int, n: int) -> tuple[int, int]:
    res = b.read(8, mem, addr)
    w = 8
    for i in range(1, n):
        byte = b.read(8, mem, b.op2("add", 64, addr, b.constd(64, i)))
        res = b.op2("concat", w + 8, byte, res)
        w += 8
    return res, w


def _store_nodes(b: Builder, mem: int, addr: int, value: int, n: int) -> int:
    cur = mem
    for i in range(n):
        byte = b.slice(value, 8 * i + 7, 8 * i)
        a_i = addr if i == 0 else b.op2("add", 64, addr, b.constd(64, i))
        cur = b.write(64, 8, cur, a_i, byte)
    return cur


def _effect(instr: int, addr: int, b: Builder, regs: dict[int, int], zero64: int, mem: int | None):
    """Return (next_pc_node, {rd: value_node}, halts, mem_next_or_None)."""
    def c64(v: int) -> int:
        return b.constd(64, v & MASK64)

    fall = c64(addr + 4)
    if _is_ecall(instr):
        return fall, {}, True, None
    d = decode(instr)
    if d is None:
        raise Unsupported("sail-btor2", f"opcode=0x{instr & 0x7F:02x}")

    bnd = {
        vn: ((zero64 if v == 0 else regs[v]) if k == "reg" else c64(v))
        for vn, (k, v) in operands(d, addr).items()
    }
    if d.kind == "alu":
        val = expr.lower(b, d.execute, bnd)
        return fall, ({d.rd: val} if d.rd != 0 else {}), False, None
    if d.kind == "branch":
        cond = expr.lower(b, d.cond, bnd)
        return b.ite(64, cond, c64(addr + d.offset), fall), {}, False, None
    if d.kind == "jal":
        return c64(addr + d.offset), ({d.rd: fall} if d.rd != 0 else {}), False, None
    if d.kind == "jalr":
        return expr.lower(b, d.target, bnd), ({d.rd: fall} if d.rd != 0 else {}), False, None
    if d.kind == "load":
        assert mem is not None
        raw, w = _load_nodes(b, mem, expr.lower(b, d.addr, bnd), d.nbytes)
        val = raw if w == 64 else (b.sext(64, raw, 64 - w) if d.signed else b.uext(64, raw, 64 - w))
        return fall, ({d.rd: val} if d.rd != 0 else {}), False, None
    if d.kind == "store":
        assert mem is not None
        cur = _store_nodes(b, mem, expr.lower(b, d.addr, bnd), regs[d.b_reg], d.nbytes)
        return fall, {}, False, cur
    return fall, {}, False, None   # fence


def translate(program: Any) -> bytes:
    prog = _unwrap(program)
    words = prog["words"]
    entry = int(prog.get("entry", 0))
    init_regs = {int(k): int(v) for k, v in prog.get("init_regs", {}).items()}

    b = Builder()
    pc = b.state(64, "pc")
    regs = {r: b.state(64, f"x{r}") for r in range(1, NREG)}
    halted = b.state(1, "halted")
    zero64 = b.zero(64)
    mem = b.state_array(64, 8, "mem") if _uses_memory(words) else None

    b.init(pc, b.constd(64, entry))
    for r in range(1, NREG):
        b.init(regs[r], b.constd(64, init_regs.get(r, 0) & MASK64))
    b.init(halted, b.zero(1))

    not_halted = b.op1("not", 1, halted)
    next_pc, next_regs, next_halted, next_mem = pc, dict(regs), halted, mem
    for i, instr in enumerate(words):
        addr = entry + 4 * i
        eff_pc, writes, halts, mem_next = _effect(instr, addr, b, regs, zero64, mem)
        at = b.op2("eq", 1, pc, b.constd(64, addr))
        active = b.op2("and", 1, at, not_halted)
        next_pc = b.ite(64, active, eff_pc, next_pc)
        for rd, val in writes.items():
            next_regs[rd] = b.ite(64, active, val, next_regs[rd])
        if halts:
            next_halted = b.ite(1, active, b.one(1), next_halted)
        if mem_next is not None:
            next_mem = b.ite_array(64, 8, active, mem_next, next_mem)

    b.next(pc, next_pc)
    for r in range(1, NREG):
        b.next(regs[r], next_regs[r])
    b.next(halted, next_halted)
    if mem is not None:
        b.next_array(mem, next_mem)

    prop = prog.get("property")
    if prop and "reg_eq" in prop:
        reg, val = prop["reg_eq"]
        src = zero64 if reg == 0 else regs[reg]
        b.bad(b.op2("eq", 1, src, b.constd(64, int(val) & MASK64)))

    return b.to_text().encode("utf-8")
