"""A tiny bit-vector expression IR — the single source of truth.

Each RV64 instruction's *execute* is written ONCE as an ``Expr`` tree over a
small QF_BV vocabulary that maps 1:1 onto both:

  * z3 BitVec terms (for the equivalence proof in ``verify.py``), and
  * BTOR2 op lines (for the emitted ``model.btor2`` in ``generate.py``).

Because the same tree feeds both lowerings, the BTOR2 fragment and the
proven semantics cannot drift: the proof is *about the very expression that
was emitted*.

Vocabulary (all map directly to BTOR2 core ops / QF_BV):
  inputs:   var(name, width)            leaf bitvector
  consts:   const(value, width)
  bitwise:  and_ or_ xor_ not_
  arith:    add sub mul
  signed:   sdiv srem  / unsigned: udiv urem
  shifts:   sll srl(logical) sra(arith)
  compare:  ult slt (-> 1-bit), used with ite to make 0/1 words
  resize:   sext zext slice(hi,lo) concat
  select:   ite(cond1bit, a, b)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

import z3


@dataclass(frozen=True)
class Expr:
    op: str
    args: Tuple["Expr", ...] = ()
    width: int = 0
    # extra immediate attributes (value for const; hi/lo for slice; name for var)
    attr: tuple = ()

    # ---- builders (read like the spec) ----
    def __add__(self, o): return _bin("add", self, o, self.width)
    def __sub__(self, o): return _bin("sub", self, o, self.width)
    def __mul__(self, o): return _bin("mul", self, o, self.width)
    def __and__(self, o): return _bin("and", self, o, self.width)
    def __or__(self, o):  return _bin("or", self, o, self.width)
    def __xor__(self, o): return _bin("xor", self, o, self.width)


def var(name: str, width: int) -> Expr:
    return Expr("var", (), width, (name,))


def const(value: int, width: int) -> Expr:
    return Expr("const", (), width, (value & ((1 << width) - 1),))


def _bin(op: str, a: Expr, b: Expr, width: int) -> Expr:
    assert a.width == b.width, f"{op}: width mismatch {a.width} vs {b.width}"
    return Expr(op, (a, b), width)


def add(a, b): return _bin("add", a, b, a.width)
def sub(a, b): return _bin("sub", a, b, a.width)
def mul(a, b): return _bin("mul", a, b, a.width)
def and_(a, b): return _bin("and", a, b, a.width)
def or_(a, b): return _bin("or", a, b, a.width)
def xor_(a, b): return _bin("xor", a, b, a.width)
def sll(a, b): return _bin("sll", a, b, a.width)
def srl(a, b): return _bin("srl", a, b, a.width)
def sra(a, b): return _bin("sra", a, b, a.width)
def udiv(a, b): return _bin("udiv", a, b, a.width)
def sdiv(a, b): return _bin("sdiv", a, b, a.width)
def urem(a, b): return _bin("urem", a, b, a.width)
def srem(a, b): return _bin("srem", a, b, a.width)


def not_(a): return Expr("not", (a,), a.width)


def ult(a, b):  # -> 1-bit
    assert a.width == b.width
    return Expr("ult", (a, b), 1)


def slt(a, b):  # signed less-than -> 1-bit
    assert a.width == b.width
    return Expr("slt", (a, b), 1)


def eq(a, b):  # -> 1-bit
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


def clone(e: Expr) -> Expr:
    """Deep-copy an Expr tree into fresh objects. Used so the BTOR2 harness can
    lower a SHARED execute tree (e.g. EXEC['ADD'], reused by ADD and ADDI) under
    different operand bindings without the id-keyed memo aliasing them."""
    return Expr(e.op, tuple(clone(c) for c in e.args), e.width, e.attr)


# ===========================================================================
# Lowering 1: Expr -> z3
# ===========================================================================

def to_z3(e: Expr, env: dict) -> z3.BitVecRef:
    op = e.op
    if op == "var":
        return env[e.attr[0]]
    if op == "const":
        return z3.BitVecVal(e.attr[0], e.width)
    a = [to_z3(x, env) for x in e.args]
    if op == "add": return a[0] + a[1]
    if op == "sub": return a[0] - a[1]
    if op == "mul": return a[0] * a[1]
    if op == "and": return a[0] & a[1]
    if op == "or":  return a[0] | a[1]
    if op == "xor": return a[0] ^ a[1]
    if op == "not": return ~a[0]
    if op == "sll": return a[0] << a[1]
    if op == "srl": return z3.LShR(a[0], a[1])
    if op == "sra": return a[0] >> a[1]
    if op == "udiv": return z3.UDiv(a[0], a[1])
    if op == "sdiv": return a[0] / a[1]
    if op == "urem": return z3.URem(a[0], a[1])
    if op == "srem": return z3.SRem(a[0], a[1])
    if op == "ult": return z3.If(z3.ULT(a[0], a[1]), z3.BitVecVal(1, 1), z3.BitVecVal(0, 1))
    if op == "slt": return z3.If(a[0] < a[1], z3.BitVecVal(1, 1), z3.BitVecVal(0, 1))
    if op == "eq":  return z3.If(a[0] == a[1], z3.BitVecVal(1, 1), z3.BitVecVal(0, 1))
    if op == "sext": return z3.SignExt(e.width - e.attr[0], a[0])
    if op == "zext": return z3.ZeroExt(e.width - e.attr[0], a[0])
    if op == "slice": return z3.Extract(e.attr[0], e.attr[1], a[0])
    if op == "concat": return z3.Concat(a[0], a[1])
    if op == "ite": return z3.If(a[0] == z3.BitVecVal(1, 1), a[1], a[2])
    raise ValueError(f"to_z3: unknown op {op!r}")


# ===========================================================================
# Lowering 2: Expr -> BTOR2 lines
# ===========================================================================
# A BTOR2 emitter accumulates numbered lines; nodes are memoized by identity
# so a shared subexpression is emitted once. Sorts are allocated on demand.

@dataclass
class Btor2Builder:
    lines: list = field(default_factory=list)
    _nid: int = 0
    _sorts: dict = field(default_factory=dict)        # width -> sort nid
    _memo: dict = field(default_factory=dict)         # id(Expr) -> result nid
    _inputs: dict = field(default_factory=dict)       # var name -> input nid
    bindings: dict = field(default_factory=dict)      # var name -> precomputed nid

    def _next(self) -> int:
        self._nid += 1
        return self._nid

    def sort(self, width: int) -> int:
        if width not in self._sorts:
            nid = self._next()
            self.lines.append(f"{nid} sort bitvec {width}")
            self._sorts[width] = nid
        return self._sorts[width]

    def raw(self, fmt: str, *parts) -> int:
        """Emit a raw op line, returning its nid (for harness plumbing that is
        not a pure Expr tree: array sorts, read/write, state/init/next)."""
        return self.emit(fmt, *parts)

    def emit(self, fmt: str, *parts) -> int:
        nid = self._next()
        self.lines.append(f"{nid} " + fmt.format(*parts))
        return nid

    def input(self, name: str, width: int) -> int:
        if name not in self._inputs:
            s = self.sort(width)
            nid = self._next()
            self.lines.append(f"{nid} input {s} {name}")
            self._inputs[name] = nid
        return self._inputs[name]

    def lower(self, e: Expr) -> int:
        key = id(e)
        if key in self._memo:
            return self._memo[key]
        nid = self._lower(e)
        self._memo[key] = nid
        return nid

    def _lower(self, e: Expr) -> int:
        op = e.op
        s = self.sort(e.width)
        if op == "var":
            name = e.attr[0]
            if name in self.bindings:        # operand wired from the decoder
                return self.bindings[name]
            return self.input(name, e.width)
        if op == "const":
            return self.emit("constd {} {}", s, e.attr[0])
        ch = [self.lower(x) for x in e.args]
        simple = {
            "add": "add", "sub": "sub", "mul": "mul",
            "and": "and", "or": "or", "xor": "xor",
            "sll": "sll", "srl": "srl", "sra": "sra",
            "udiv": "udiv", "sdiv": "sdiv", "urem": "urem", "srem": "srem",
            "concat": "concat",
        }
        if op in simple:
            return self.emit("{} {} {} {}", simple[op], s, ch[0], ch[1])
        if op == "not":
            return self.emit("not {} {}", s, ch[0])
        if op == "ult":
            return self.emit("ult {} {} {}", s, ch[0], ch[1])
        if op == "slt":
            return self.emit("slt {} {} {}", s, ch[0], ch[1])
        if op == "eq":
            return self.emit("eq {} {} {}", s, ch[0], ch[1])
        if op == "sext":
            return self.emit("sext {} {} {}", s, ch[0], e.width - e.attr[0])
        if op == "zext":
            return self.emit("uext {} {} {}", s, ch[0], e.width - e.attr[0])
        if op == "slice":
            return self.emit("slice {} {} {} {}", s, ch[0], e.attr[0], e.attr[1])
        if op == "ite":
            return self.emit("ite {} {} {} {}", s, ch[0], ch[1], ch[2])
        raise ValueError(f"btor2: unknown op {op!r}")
