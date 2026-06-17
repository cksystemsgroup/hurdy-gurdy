"""A tiny bit-vector expression IR — the single source of truth for the
Sail-derived RISC-V semantics (salvaged from the v3 ``sail_btor2_machine``).

Each instruction's *execute* is written once as an ``Expr`` tree over a small
QF_BV vocabulary that lowers three ways from the SAME tree, so they cannot
drift:

  * ``evaluate`` — concrete Python bit-vector eval (the shared Sail
    interpreter), matching ``languages/btor2/eval.py`` op-for-op;
  * ``lower`` — BTOR2 nodes via the shared :class:`Builder` (the emitted
    transition-system datapath in ``sail-btor2``);
  * ``to_z3`` — z3 ``BitVec`` terms (the equivalence proof).

This is the *independence* the Sail branch buys: these trees are a second,
separate encoding of RISC-V from the one the hand-written ``riscv-btor2``
translator and ``riscv`` interpreter use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..btor2.build import Builder


@dataclass(frozen=True)
class Expr:
    op: str
    args: tuple = ()
    width: int = 0
    attr: tuple = ()           # const value; (hi, lo) for slice; (name,) for var; (from_w,) for ext

    def __add__(self, o): return _bin("add", self, o)
    def __sub__(self, o): return _bin("sub", self, o)
    def __mul__(self, o): return _bin("mul", self, o)
    def __and__(self, o): return _bin("and", self, o)
    def __or__(self, o):  return _bin("or", self, o)
    def __xor__(self, o): return _bin("xor", self, o)


def var(name: str, width: int) -> Expr:
    return Expr("var", (), width, (name,))


def const(value: int, width: int) -> Expr:
    return Expr("const", (), width, (value & ((1 << width) - 1),))


def _bin(op: str, a: Expr, b: Expr) -> Expr:
    assert a.width == b.width, f"{op}: width {a.width} vs {b.width}"
    return Expr(op, (a, b), a.width)


def add(a, b): return _bin("add", a, b)
def sub(a, b): return _bin("sub", a, b)
def mul(a, b): return _bin("mul", a, b)
def and_(a, b): return _bin("and", a, b)
def or_(a, b): return _bin("or", a, b)
def xor_(a, b): return _bin("xor", a, b)
def sll(a, b): return _bin("sll", a, b)
def srl(a, b): return _bin("srl", a, b)
def sra(a, b): return _bin("sra", a, b)
def udiv(a, b): return _bin("udiv", a, b)
def sdiv(a, b): return _bin("sdiv", a, b)
def urem(a, b): return _bin("urem", a, b)
def srem(a, b): return _bin("srem", a, b)
def and1(a, b): return Expr("and", (a, b), 1)   # 1-bit conjunction (div-overflow guard)


def not_(a): return Expr("not", (a,), a.width)


def ult(a, b):
    assert a.width == b.width
    return Expr("ult", (a, b), 1)


def slt(a, b):
    assert a.width == b.width
    return Expr("slt", (a, b), 1)


def eq(a, b):
    assert a.width == b.width
    return Expr("eq", (a, b), 1)


def sext(a, to_width):
    assert to_width >= a.width
    return Expr("sext", (a,), to_width, (a.width,))


def zext(a, to_width):
    assert to_width >= a.width
    return Expr("zext", (a,), to_width, (a.width,))


def slice_(a, hi, lo):
    return Expr("slice", (a,), hi - lo + 1, (hi, lo))


def concat(hi_part, lo_part):
    return Expr("concat", (hi_part, lo_part), hi_part.width + lo_part.width)


def ite(cond1, a, b):
    assert cond1.width == 1 and a.width == b.width
    return Expr("ite", (cond1, a, b), a.width)


# --------------------------------------------------------------------------
# Lowering 1: concrete evaluation (matches languages/btor2/eval.py op-for-op)
# --------------------------------------------------------------------------
def _to_signed(v: int, w: int) -> int:
    v &= (1 << w) - 1
    return v - (1 << w) if v >> (w - 1) else v


def evaluate(e: Expr, env: dict[str, int]) -> int:
    op, w = e.op, e.width
    m = (1 << w) - 1 if w else 1
    if op == "var":
        return env[e.attr[0]] & m
    if op == "const":
        return e.attr[0] & m
    a = [evaluate(x, env) for x in e.args]
    if op == "add": return (a[0] + a[1]) & m
    if op == "sub": return (a[0] - a[1]) & m
    if op == "mul": return (a[0] * a[1]) & m
    if op == "and": return (a[0] & a[1]) & m
    if op == "or": return (a[0] | a[1]) & m
    if op == "xor": return (a[0] ^ a[1]) & m
    if op == "not": return (~a[0]) & m
    if op == "sll": return 0 if a[1] >= w else (a[0] << a[1]) & m
    if op == "srl": return 0 if a[1] >= w else (a[0] & m) >> a[1]
    if op == "sra":
        sv = _to_signed(a[0], w)
        return (m if sv < 0 else 0) if a[1] >= w else (sv >> a[1]) & m
    if op == "udiv": return m if a[1] == 0 else (a[0] // a[1]) & m
    if op == "urem": return a[0] & m if a[1] == 0 else (a[0] % a[1]) & m
    if op == "sdiv":
        x, y = _to_signed(a[0], w), _to_signed(a[1], w)
        if y == 0:
            return m if x >= 0 else 1
        return (-(abs(x) // abs(y)) if (x < 0) != (y < 0) else abs(x) // abs(y)) & m
    if op == "srem":
        x, y = _to_signed(a[0], w), _to_signed(a[1], w)
        if y == 0:
            return a[0] & m
        r = abs(x) % abs(y)
        return (-r if x < 0 else r) & m
    if op == "ult": return 1 if a[0] < a[1] else 0
    if op == "slt":
        aw = e.args[0].width
        return 1 if _to_signed(a[0], aw) < _to_signed(a[1], aw) else 0
    if op == "eq": return 1 if a[0] == a[1] else 0
    if op == "sext": return _to_signed(a[0], e.attr[0]) & m
    if op == "zext": return a[0] & m
    if op == "slice": return (a[0] >> e.attr[1]) & ((1 << (e.attr[0] - e.attr[1] + 1)) - 1)
    if op == "concat":
        bw = e.args[1].width
        return ((a[0] << bw) | (a[1] & ((1 << bw) - 1))) & m
    if op == "ite": return a[1] if a[0] != 0 else a[2]
    raise ValueError(f"evaluate: unknown op {op!r}")


# --------------------------------------------------------------------------
# Lowering 2: Expr -> BTOR2 nodes via the shared Builder
# --------------------------------------------------------------------------
_SIMPLE2 = {"add", "sub", "mul", "and", "or", "xor",
            "sll", "srl", "sra", "udiv", "sdiv", "urem", "srem", "concat"}


def lower(b: Builder, e: Expr, bindings: dict[str, int],
          memo: dict[int, int] | None = None) -> int:
    """Lower an Expr to a BTOR2 node id; ``bindings`` maps operand var names to
    existing node ids. Shared subtrees are emitted once."""
    memo = {} if memo is None else memo
    key = id(e)
    if key in memo:
        return memo[key]
    nid = _lower(b, e, bindings, memo)
    memo[key] = nid
    return nid


def _lower(b: Builder, e: Expr, bindings: dict[str, int], memo: dict[int, int]) -> int:
    op, w = e.op, e.width
    if op == "var":
        name = e.attr[0]
        if name not in bindings:
            raise KeyError(f"unbound operand {name!r}")
        return bindings[name]
    if op == "const":
        return b.constd(w, e.attr[0])
    ch = [lower(b, x, bindings, memo) for x in e.args]
    if op in _SIMPLE2:
        return b.op2(op, w, ch[0], ch[1])
    if op == "not":
        return b.op1("not", w, ch[0])
    if op in ("ult", "slt", "eq"):
        return b.op2(op, 1, ch[0], ch[1])
    if op == "sext":
        return b.sext(w, ch[0], w - e.attr[0])
    if op == "zext":
        return b.uext(w, ch[0], w - e.attr[0])
    if op == "slice":
        return b.slice(ch[0], e.attr[0], e.attr[1])
    if op == "ite":
        return b.ite(w, ch[0], ch[1], ch[2])
    raise ValueError(f"lower: unknown op {op!r}")


# --------------------------------------------------------------------------
# Lowering 3: Expr -> z3 (the equivalence proof; z3 imported lazily)
# --------------------------------------------------------------------------
def to_z3(e: Expr, env: dict[str, Any]) -> Any:
    import z3

    op = e.op
    if op == "var":
        return env[e.attr[0]]
    if op == "const":
        return z3.BitVecVal(e.attr[0], e.width)
    a = [to_z3(x, env) for x in e.args]
    one, zero = z3.BitVecVal(1, 1), z3.BitVecVal(0, 1)
    table = {
        "add": lambda: a[0] + a[1], "sub": lambda: a[0] - a[1], "mul": lambda: a[0] * a[1],
        "and": lambda: a[0] & a[1], "or": lambda: a[0] | a[1], "xor": lambda: a[0] ^ a[1],
        "not": lambda: ~a[0], "sll": lambda: a[0] << a[1], "srl": lambda: z3.LShR(a[0], a[1]),
        "sra": lambda: a[0] >> a[1], "udiv": lambda: z3.UDiv(a[0], a[1]), "sdiv": lambda: a[0] / a[1],
        "urem": lambda: z3.URem(a[0], a[1]), "srem": lambda: z3.SRem(a[0], a[1]),
        "ult": lambda: z3.If(z3.ULT(a[0], a[1]), one, zero),
        "slt": lambda: z3.If(a[0] < a[1], one, zero),
        "eq": lambda: z3.If(a[0] == a[1], one, zero),
        "sext": lambda: z3.SignExt(e.width - e.attr[0], a[0]),
        "zext": lambda: z3.ZeroExt(e.width - e.attr[0], a[0]),
        "slice": lambda: z3.Extract(e.attr[0], e.attr[1], a[0]),
        "concat": lambda: z3.Concat(a[0], a[1]),
        "ite": lambda: z3.If(a[0] == one, a[1], a[2]),
    }
    if op not in table:
        raise ValueError(f"to_z3: unknown op {op!r}")
    return table[op]()
