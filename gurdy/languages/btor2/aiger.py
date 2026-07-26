"""BTOR2 → AIGER bit-blasting (the certificate side of issue #2 route (b)).

Certifaiger checks *witness circuits* in AIGER, so the certificate route
needs the transition system itself as an and-inverter graph: every
bit-vector node becomes a vector of AIGER literals (LSB first), states
become latches, inputs become inputs, ``bad``/``constraint`` become the
1.9 sections of the same name. The emitter is deliberately the platform's
own — its faithfulness is TCB residue the certificate result records
(``hurdy-gurdy:btor2-aiger-bitblast``), exactly the standing the SMT
bridge's operator mapping has under invariant re-discharge and bitwuzla's
bit-blast has under the DRAT chain.

Semantics follow the shared evaluator (``eval.py``) except where replay
and model checking genuinely differ: a state with **no next** is free in
every step (the bridge declares it per-frame free, pono treats it as an
input), so it becomes a latch whose next function is a fresh input — the
evaluator's value-holding is a replay convenience, not the semantics. A
state with no ``init`` is an *uninitialized* AIGER latch (reset = its own
literal). Anything outside the supported subset — arrays, non-constant
``init``, signed division — hard-aborts with ``Unsupported``: an
unsupported system can only fail to produce a certificate, never
mis-certify (the fail-safe direction, SOLVERS.md §6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...core.errors import Unsupported
from .eval import _const_value
from .model import Bitvec, System, from_text

_CONSTS = {"zero", "one", "ones", "const", "constd", "consth"}
_DIRECTIVES = {"init", "next", "bad", "constraint", "output"}

#: AIGER constants (literal encoding: variable ``v`` is ``2v``, ``^1`` negates).
FALSE = 0
TRUE = 1


@dataclass
class _Latch:
    lit: int
    next: int | None = None
    reset: int = 0
    symbol: str | None = None


class Aig:
    """An and-inverter graph with AIGER 1.9 ASCII emission. Inputs must be
    allocated first, then latches, then gates — the consecutive variable
    indexing certifaiger enforces even for the ASCII format."""

    def __init__(self) -> None:
        self._next_var = 1
        self.inputs: list[tuple[int, str | None]] = []
        self.latches: list[_Latch] = []
        self.ands: list[tuple[int, int, int]] = []
        self._cache: dict[tuple[int, int], int] = {}

    def _alloc(self) -> int:
        lit = 2 * self._next_var
        self._next_var += 1
        return lit

    def add_input(self, symbol: str | None = None) -> int:
        if self.latches or self.ands:
            raise Unsupported("btor2-aiger", "input allocated after latch/gate")
        lit = self._alloc()
        self.inputs.append((lit, symbol))
        return lit

    def add_latch(self, symbol: str | None = None) -> int:
        if self.ands:
            raise Unsupported("btor2-aiger", "latch allocated after gate")
        lit = self._alloc()
        self.latches.append(_Latch(lit=lit, symbol=symbol))
        return lit

    def set_latch(self, lit: int, *, next: int, reset: int) -> None:
        for latch in self.latches:
            if latch.lit == lit:
                latch.next, latch.reset = next, reset
                return
        raise ValueError(f"no latch with literal {lit}")

    # ---------------------------------------------------------- gates
    def and_(self, a: int, b: int) -> int:
        if a == FALSE or b == FALSE or a == (b ^ 1):
            return FALSE
        if a == TRUE or a == b:
            return b
        if b == TRUE:
            return a
        key = (a, b) if a < b else (b, a)
        if key in self._cache:
            return self._cache[key]
        lit = self._alloc()
        self.ands.append((lit, key[1], key[0]))  # aiger convention: rhs0 >= rhs1
        self._cache[key] = lit
        return lit

    def or_(self, a: int, b: int) -> int:
        return self.and_(a ^ 1, b ^ 1) ^ 1

    def xor_(self, a: int, b: int) -> int:
        return self.or_(self.and_(a, b ^ 1), self.and_(a ^ 1, b))

    def eq_(self, a: int, b: int) -> int:
        return self.xor_(a, b) ^ 1

    def ite_(self, c: int, t: int, e: int) -> int:
        return self.or_(self.and_(c, t), self.and_(c ^ 1, e))

    # ------------------------------------------------------- emission
    def to_aag(self, *, bads: tuple[int, ...] | list[int] = (),
               constraints: tuple[int, ...] | list[int] = (),
               input_names: list[str | None] | None = None,
               latch_names: list[str | None] | None = None,
               comment: str | None = None) -> str:
        maxvar = self._next_var - 1
        header = ["aag", str(maxvar), str(len(self.inputs)),
                  str(len(self.latches)), "0", str(len(self.ands)),
                  str(len(bads))]
        if constraints:
            header.append(str(len(constraints)))
        lines = [" ".join(header)]
        for lit, _sym in self.inputs:
            lines.append(str(lit))
        for latch in self.latches:
            if latch.next is None:
                raise ValueError(f"latch {latch.lit} has no next function")
            row = [str(latch.lit), str(latch.next)]
            if latch.reset != 0:
                row.append(str(latch.reset))
            lines.append(" ".join(row))
        lines += [str(b) for b in bads]
        lines += [str(c) for c in constraints]
        for lhs, rhs0, rhs1 in self.ands:
            lines.append(f"{lhs} {rhs0} {rhs1}")
        in_names = (input_names if input_names is not None
                    else [sym for _lit, sym in self.inputs])
        l_names = (latch_names if latch_names is not None
                   else [latch.symbol for latch in self.latches])
        for pos, name in enumerate(in_names):
            if name:
                lines.append(f"i{pos} {name}")
        for pos, name in enumerate(l_names):
            if name:
                lines.append(f"l{pos} {name}")
        if comment:
            lines.append("c")
            lines += comment.splitlines()
        return "\n".join(lines) + "\n"


# ------------------------------------------------------------ vector ops
# Vectors are lists of AIGER literals, LSB first; semantics mirror eval.py
# (width masking is structural — a vector *is* its width).

def v_not(vec: list[int]) -> list[int]:
    return [lit ^ 1 for lit in vec]


def v_bitwise(aig: Aig, op: str, a: list[int], b: list[int]) -> list[int]:
    fn = {"and": aig.and_, "or": aig.or_, "xor": aig.xor_}[op]
    return [fn(x, y) for x, y in zip(a, b)]


def v_add(aig: Aig, a: list[int], b: list[int], cin: int = FALSE) -> list[int]:
    out, carry = [], cin
    for x, y in zip(a, b):
        s = aig.xor_(aig.xor_(x, y), carry)
        carry = aig.or_(aig.and_(x, y), aig.and_(carry, aig.xor_(x, y)))
        out.append(s)
    return out


def v_sub(aig: Aig, a: list[int], b: list[int]) -> list[int]:
    return v_add(aig, a, v_not(b), cin=TRUE)


def v_const(width: int, value: int) -> list[int]:
    return [TRUE if (value >> i) & 1 else FALSE for i in range(width)]


def v_mul(aig: Aig, a: list[int], b: list[int]) -> list[int]:
    w = len(a)
    acc = v_const(w, 0)
    for i in range(w):
        partial = v_const(i, 0) + [aig.and_(a[j], b[i]) for j in range(w - i)]
        acc = v_add(aig, acc, partial)
    return acc


def v_ult(aig: Aig, a: list[int], b: list[int]) -> int:
    lt = FALSE
    for x, y in zip(a, b):  # LSB first: the last (MSB) comparison dominates
        lt = aig.ite_(aig.xor_(x, y), aig.and_(x ^ 1, y), lt)
    return lt


def v_slt(aig: Aig, a: list[int], b: list[int]) -> int:
    sa, sb = a[-1], b[-1]
    return aig.ite_(aig.xor_(sa, sb), sa, v_ult(aig, a, b))


def v_eq(aig: Aig, a: list[int], b: list[int]) -> int:
    acc = TRUE
    for x, y in zip(a, b):
        acc = aig.and_(acc, aig.eq_(x, y))
    return acc


def v_red(aig: Aig, op: str, a: list[int]) -> int:
    if op == "redor":
        acc = FALSE
        for x in a:
            acc = aig.or_(acc, x)
        return acc
    if op == "redand":
        acc = TRUE
        for x in a:
            acc = aig.and_(acc, x)
        return acc
    acc = FALSE  # redxor
    for x in a:
        acc = aig.xor_(acc, x)
    return acc


def v_shift(aig: Aig, op: str, a: list[int], sh: list[int]) -> list[int]:
    """Barrel shifter with eval.py's saturation: a shift amount >= width
    yields all zeros (``sll``/``srl``) or the sign fill (``sra``)."""
    w = len(a)
    fill = a[-1] if op == "sra" else FALSE
    cur = list(a)
    big = FALSE  # any shift-amount bit worth >= w set
    for j, bit in enumerate(sh):
        amount = 1 << j
        if amount >= w:
            big = aig.or_(big, bit)
            continue
        if op == "sll":
            shifted = [FALSE] * amount + cur[: w - amount]
        else:
            shifted = cur[amount:] + [fill] * amount
        cur = [aig.ite_(bit, s, c) for s, c in zip(shifted, cur)]
    return [aig.ite_(big, fill, c) for c in cur]


def v_udivrem(aig: Aig, a: list[int], b: list[int]) -> tuple[list[int], list[int]]:
    """Restoring division, MSB first. Division by zero falls out with the
    SMT-LIB semantics eval.py implements: quotient all-ones, remainder the
    dividend (``rem - 0`` never restores)."""
    w = len(a)
    rem = v_const(w, 0)
    quot = [FALSE] * w
    for i in reversed(range(w)):
        rem = [a[i]] + rem[: w - 1]
        geq = v_ult(aig, rem, b) ^ 1
        quot[i] = geq
        diff = v_sub(aig, rem, b)
        rem = [aig.ite_(geq, d, r) for d, r in zip(diff, rem)]
    return quot, rem


# ------------------------------------------------------------- bit-blast

@dataclass
class Blasted:
    """The bit-blasted system: the graph plus every node's literal vector
    (``values`` covers inputs and states too), the ``bad``/``constraint``
    section literals, and the fresh inputs standing in for next-less
    states."""
    aig: Aig
    system: System
    values: dict[int, list[int]] = field(default_factory=dict)
    input_bits: dict[int, list[int]] = field(default_factory=dict)
    state_bits: dict[int, list[int]] = field(default_factory=dict)
    free_next: dict[int, list[int]] = field(default_factory=dict)
    bads: list[int] = field(default_factory=list)
    constraints: list[int] = field(default_factory=list)


def _width(sys: System, nid: int) -> int:
    node = sys.nodes[nid]
    sort = sys.sorts.get(node.sort) if node.sort is not None else None
    if not isinstance(sort, Bitvec):
        raise Unsupported("btor2-aiger", f"non-bitvec node {nid} ({node.op})")
    return sort.width


def _label(sys: System, nid: int) -> str:
    return sys.nodes[nid].symbol or f"n{nid}"


def bitblast(system: str | bytes | System) -> Blasted:
    """Blast a BTOR2 system into an ``Aig``. Node ids are the *file's* ids
    (no renumbering), so pono's ``state<id>`` invariant names index
    ``state_bits`` directly."""
    if isinstance(system, System):
        sys = system
    else:
        text = (system.decode("utf-8")
                if isinstance(system, (bytes, bytearray)) else str(system))
        sys = from_text(text)
    b = Blasted(aig=Aig(), system=sys)
    aig = b.aig

    has_next = {n.refs[0] for n in sys.nodes.values() if n.op == "next"}
    init_of = {n.refs[0]: n.refs[1] for n in sys.nodes.values() if n.op == "init"}
    states = [n for n in sys.nodes.values() if n.op == "state"]

    # Allocation order fixes the AIGER variable layout: real inputs, then
    # the fresh free-next inputs, then all latches — gates only after.
    for n in (n for n in sys.nodes.values() if n.op == "input"):
        w = _width(sys, n.id)
        b.input_bits[n.id] = [aig.add_input(f"{_label(sys, n.id)}[{i}]")
                              for i in range(w)]
        b.values[n.id] = b.input_bits[n.id]
    for s in states:
        if s.id not in has_next:
            w = _width(sys, s.id)
            b.free_next[s.id] = [aig.add_input(f"{_label(sys, s.id)}_free[{i}]")
                                 for i in range(w)]
    for s in states:
        w = _width(sys, s.id)
        b.state_bits[s.id] = [aig.add_latch(f"{_label(sys, s.id)}[{i}]")
                              for i in range(w)]
        b.values[s.id] = b.state_bits[s.id]

    def vec(r: int) -> list[int]:
        v = b.values.get(abs(r))
        if v is None:
            raise Unsupported("btor2-aiger",
                              f"reference to non-bitvec node {abs(r)}")
        return v_not(v) if r < 0 else v

    for nid in sys.order:
        node = sys.nodes.get(nid)
        if node is None or node.op in _DIRECTIVES | {"state", "input"}:
            continue
        op = node.op
        if op in _CONSTS:
            b.values[nid] = v_const(_width(sys, nid), _const_value(sys, node))
            continue
        w = _width(sys, nid)
        r = [vec(x) for x in node.refs]
        if op in ("and", "or", "xor"):
            out = v_bitwise(aig, op, r[0], r[1])
        elif op == "nand":
            out = v_not(v_bitwise(aig, "and", r[0], r[1]))
        elif op == "nor":
            out = v_not(v_bitwise(aig, "or", r[0], r[1]))
        elif op == "not":
            out = v_not(r[0])
        elif op == "neg":
            out = v_add(aig, v_not(r[0]), v_const(w, 0), cin=TRUE)
        elif op == "inc":
            out = v_add(aig, r[0], v_const(w, 1))
        elif op == "dec":
            out = v_sub(aig, r[0], v_const(w, 1))
        elif op == "add":
            out = v_add(aig, r[0], r[1])
        elif op == "sub":
            out = v_sub(aig, r[0], r[1])
        elif op == "mul":
            out = v_mul(aig, r[0], r[1])
        elif op == "udiv":
            out = v_udivrem(aig, r[0], r[1])[0]
        elif op == "urem":
            out = v_udivrem(aig, r[0], r[1])[1]
        elif op in ("sdiv", "srem"):
            raise Unsupported("btor2-aiger", f"op.{op}")
        elif op in ("eq", "iff"):
            out = [v_eq(aig, r[0], r[1])]
        elif op == "neq":
            out = [v_eq(aig, r[0], r[1]) ^ 1]
        elif op == "implies":
            out = [aig.or_(r[0][0] ^ 1, r[1][0])]
        elif op in ("ult", "ulte", "ugt", "ugte"):
            a, c = (r[0], r[1]) if op in ("ult", "ulte") else (r[1], r[0])
            lt = v_ult(aig, a, c)
            out = [lt if op in ("ult", "ugt") else v_ult(aig, c, a) ^ 1]
        elif op in ("slt", "slte", "sgt", "sgte"):
            a, c = (r[0], r[1]) if op in ("slt", "slte") else (r[1], r[0])
            lt = v_slt(aig, a, c)
            out = [lt if op in ("slt", "sgt") else v_slt(aig, c, a) ^ 1]
        elif op in ("redor", "redand", "redxor"):
            out = [v_red(aig, op, r[0])]
        elif op in ("sll", "srl", "sra"):
            out = v_shift(aig, op, r[0], r[1])
        elif op == "concat":
            out = r[1] + r[0]  # refs[0] is the high part
        elif op == "slice":
            upper, lower = node.bounds
            out = r[0][lower:upper + 1]
        elif op == "sext":
            out = r[0] + [r[0][-1]] * node.bounds[0]
        elif op == "uext":
            out = r[0] + [FALSE] * node.bounds[0]
        elif op == "ite":
            out = [aig.ite_(r[0][0], t, e) for t, e in zip(r[1], r[2])]
        else:
            raise Unsupported("btor2-aiger", f"op.{op}")
        if len(out) != w:
            raise Unsupported("btor2-aiger",
                              f"width mismatch blasting node {nid} ({op}): "
                              f"{len(out)} != {w}")
        b.values[nid] = out

    for s in states:
        bits = b.state_bits[s.id]
        nxt = None
        for n in sys.nodes.values():
            if n.op == "next" and n.refs[0] == s.id:
                nxt = vec(n.refs[1])
        if nxt is None:
            nxt = b.free_next[s.id]
        if s.id in init_of:
            ref = init_of[s.id]
            cnode = sys.nodes[abs(ref)]
            if cnode.op not in _CONSTS:
                raise Unsupported("btor2-aiger", "non-constant init")
            value = _const_value(sys, cnode)
            if ref < 0:
                value = ~value & ((1 << len(bits)) - 1)
            resets = [TRUE if (value >> i) & 1 else FALSE
                      for i in range(len(bits))]
        else:
            resets = list(bits)  # uninitialized: reset to own literal
        for bit, nx, rs in zip(bits, nxt, resets):
            aig.set_latch(bit, next=nx, reset=rs)

    for n in sys.nodes.values():
        if n.op in ("bad", "constraint"):
            v = vec(n.refs[0])
            if len(v) != 1:
                raise Unsupported("btor2-aiger", f"{n.op} on width {len(v)}")
            (b.bads if n.op == "bad" else b.constraints).append(v[0])
    return b
