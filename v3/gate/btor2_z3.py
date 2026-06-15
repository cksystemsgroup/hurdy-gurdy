"""A small BTOR2 -> z3 unroller, used by the F2 bounded-equivalence gate.

It parses the (bit-vector, non-array) BTOR2 a pair's own lowering emits and
unrolls its transition relation ``steps`` times into z3, with caller-supplied
symbolic initial state. This lets the gate reason about the ACTUAL emitted
artifact symbolically (over all inputs), rather than a re-implementation.

Supported ops are exactly those ``gurdy/hops/riscv_btor2/btor2.py`` emits:
constd, state/init/next, add sub mul and or xor, sll srl sra, udiv sdiv urem
srem, eq neq ult slt ugte, ite, slice, sext uext concat, not. (Arrays / inputs
are not used by the specialized own lowering, so they are intentionally absent.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import z3


@dataclass
class _Node:
    op: str
    sort: int                 # sort nid (0 for sort lines themselves)
    args: list                # ints (nids) or trailing immediates


@dataclass
class Btor2System:
    width: dict[int, int] = field(default_factory=dict)        # sort nid -> bit width
    nodes: dict[int, _Node] = field(default_factory=dict)      # nid -> node
    states: list[tuple[int, str]] = field(default_factory=list)  # (nid, name)
    init: dict[int, int] = field(default_factory=dict)         # state nid -> value nid
    nxt: dict[int, int] = field(default_factory=dict)          # state nid -> next nid

    def state_by_name(self) -> dict[str, int]:
        return {name: nid for nid, name in self.states}


def parse(text: str) -> Btor2System:
    sys = Btor2System()
    for line in text.splitlines():
        line = line.split(";", 1)[0].strip()
        if not line:
            continue
        t = line.split()
        nid, op = int(t[0]), t[1]
        if op == "sort":
            if t[2] == "bitvec":
                sys.width[nid] = int(t[3])
            continue
        if op == "state":
            sys.width[nid] = sys.width[int(t[2])]
            name = t[3] if len(t) > 3 else f"s{nid}"
            sys.states.append((nid, name))
            sys.nodes[nid] = _Node("state", int(t[2]), [])
            continue
        if op == "init":
            sys.init[int(t[3])] = int(t[4])
            continue
        if op == "next":
            sys.nxt[int(t[3])] = int(t[4])
            continue
        if op == "bad":
            continue
        sort = int(t[2])
        sys.width[nid] = sys.width.get(sort, 0)
        sys.nodes[nid] = _Node(op, sort, [int(x) for x in t[3:]])
    return sys


_BIN = {
    "add": lambda a, b: a + b, "sub": lambda a, b: a - b, "mul": lambda a, b: a * b,
    "and": lambda a, b: a & b, "or": lambda a, b: a | b, "xor": lambda a, b: a ^ b,
    "sll": lambda a, b: a << b, "srl": lambda a, b: z3.LShR(a, b), "sra": lambda a, b: a >> b,
    "udiv": z3.UDiv, "sdiv": lambda a, b: a / b, "urem": z3.URem, "srem": z3.SRem,
    "concat": lambda a, b: z3.Concat(a, b),
}
_one1, _zero1 = z3.BitVecVal(1, 1), z3.BitVecVal(0, 1)


def _evaluator(sys: Btor2System, state_env: dict[int, z3.BitVecRef]):
    memo: dict[int, z3.BitVecRef] = {}

    def ev(nid: int) -> z3.BitVecRef:
        if nid in state_env and sys.nodes.get(nid, _Node("", 0, [])).op == "state":
            return state_env[nid]
        if nid in memo:
            return memo[nid]
        n = sys.nodes[nid]
        op, a = n.op, n.args
        if op == "constd":
            r = z3.BitVecVal(a[0], sys.width[n.sort])
        elif op in _BIN:
            r = _BIN[op](ev(a[0]), ev(a[1]))
        elif op == "not":
            r = ~ev(a[0])
        elif op == "eq":
            r = z3.If(ev(a[0]) == ev(a[1]), _one1, _zero1)
        elif op == "neq":
            r = z3.If(ev(a[0]) != ev(a[1]), _one1, _zero1)
        elif op == "ult":
            r = z3.If(z3.ULT(ev(a[0]), ev(a[1])), _one1, _zero1)
        elif op == "slt":
            r = z3.If(ev(a[0]) < ev(a[1]), _one1, _zero1)
        elif op == "ugte":
            r = z3.If(z3.UGE(ev(a[0]), ev(a[1])), _one1, _zero1)
        elif op == "ite":
            r = z3.If(ev(a[0]) == _one1, ev(a[1]), ev(a[2]))
        elif op == "slice":
            r = z3.Extract(a[1], a[2], ev(a[0]))
        elif op == "sext":
            r = z3.SignExt(a[1], ev(a[0]))
        elif op == "uext":
            r = z3.ZeroExt(a[1], ev(a[0]))
        else:
            raise ValueError(f"btor2_z3: unsupported op {op!r}")
        memo[nid] = r
        return r

    return ev


def unroll(text: str, steps: int, initials: dict[str, z3.BitVecRef]) -> dict[str, z3.BitVecRef]:
    """Unroll the transition ``steps`` times. ``initials`` maps state names to
    their initial z3 value (states omitted use their BTOR2 ``init`` constant, or
    a fresh free symbol). Returns the final state keyed by name."""
    sys = parse(text)
    by_name = sys.state_by_name()
    env: dict[int, z3.BitVecRef] = {}
    for nid, name in sys.states:
        w = sys.width[nid]
        if name in initials:
            env[nid] = initials[name]
        elif nid in sys.init:
            iv = sys.nodes[sys.init[nid]]
            env[nid] = z3.BitVecVal(iv.args[0], w)
        else:
            env[nid] = z3.BitVec(f"{name}_init", w)

    for _ in range(steps):
        ev = _evaluator(sys, env)
        env = {nid: ev(sys.nxt[nid]) for nid, _ in sys.states if nid in sys.nxt}
        # carry states without a next unchanged
        for nid, _ in sys.states:
            if nid not in sys.nxt:
                env.setdefault(nid, env.get(nid))
    return {name: env[by_name[name]] for name in by_name if by_name[name] in env}
