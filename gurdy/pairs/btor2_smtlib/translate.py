"""BTOR2 -> SMT-LIB bridge: unroll a transition system to bound ``k``
(pairs/btor2-smtlib brief).

Emits an SMT-LIB (``QF_ABV``) script that is ``sat`` iff some ``bad`` is
asserted within ``k`` steps. Every BTOR2 operator maps to the standard SMT
bit-vector/array operator a native BTOR2 solver also uses, so the bridged
verdict and a native verdict on the same system must agree — the native-vs-
bridged cross-check (SOLVERS.md §7). The output is determined byte-for-byte by
``(system, k)`` (``predicted`` fidelity): nodes are emitted in id order, steps
in ascending order.

Each value node becomes a per-step ``define-fun``; states and inputs are
per-step ``declare-fun``; init/next/bad become assertions across steps.
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.model import Array, Bitvec, Node, System, from_text

_DIRECTIVES = {"init", "next", "bad", "constraint", "output"}


def _as_system(system: Any) -> System:
    if isinstance(system, System):
        return system
    text = system.decode("utf-8") if isinstance(system, (bytes, bytearray)) else str(system)
    return from_text(text)


def _bw(sys: System, node: Node) -> int:
    sort = sys.sorts[node.sort]
    if isinstance(sort, Bitvec):
        return sort.width
    raise Unsupported("btor2-smtlib", f"non-bitvec result for {node.op}")


def _sort_str(sys: System, sort_id: int) -> str:
    sort = sys.sorts[sort_id]
    if isinstance(sort, Bitvec):
        return f"(_ BitVec {sort.width})"
    assert isinstance(sort, Array)
    iw = sys.sorts[sort.index].width
    ew = sys.sorts[sort.element].width
    return f"(Array (_ BitVec {iw}) (_ BitVec {ew}))"


def _name(sys: System, nid: int, t: int) -> str:
    op = sys.nodes[nid].op
    if op == "state":
        return f"s{nid}_{t}"
    if op == "input":
        return f"i{nid}_{t}"
    return f"n{nid}_{t}"


def _const_smt(sys: System, node: Node) -> str:
    w = _bw(sys, node)
    if node.op == "zero":
        v = 0
    elif node.op == "one":
        v = 1 % (1 << w)
    elif node.op == "ones":
        v = (1 << w) - 1
    elif node.op == "constd":
        v = int(node.literal) % (1 << w)
    elif node.op == "const":
        v = int(node.literal, 2) % (1 << w)
    elif node.op == "consth":
        v = int(node.literal, 16) % (1 << w)
    else:
        raise Unsupported("btor2-smtlib", f"const.{node.op}")
    return f"(_ bv{v} {w})"


_BIN = {
    "and": "bvand", "or": "bvor", "xor": "bvxor", "nand": "bvnand", "nor": "bvnor",
    "add": "bvadd", "sub": "bvsub", "mul": "bvmul", "udiv": "bvudiv", "urem": "bvurem",
    "sll": "bvshl", "srl": "bvlshr", "sra": "bvashr", "concat": "concat",
}
_CMP = {
    "ult": "bvult", "ulte": "bvule", "ugt": "bvugt", "ugte": "bvuge",
    "slt": "bvslt", "slte": "bvsle", "sgt": "bvsgt", "sgte": "bvsge",
}


def _expr(sys: System, node: Node, t: int) -> str:
    op = node.op

    def a(i: int) -> str:
        return _name(sys, node.refs[i], t)

    if op in ("zero", "one", "ones", "const", "constd", "consth"):
        return _const_smt(sys, node)
    if op == "not":
        return f"(bvnot {a(0)})"
    if op == "neg":
        return f"(bvneg {a(0)})"
    if op == "inc":
        return f"(bvadd {a(0)} (_ bv1 {_bw(sys, node)}))"
    if op == "dec":
        return f"(bvsub {a(0)} (_ bv1 {_bw(sys, node)}))"
    if op in _BIN:
        return f"({_BIN[op]} {a(0)} {a(1)})"
    if op == "eq":
        return f"(ite (= {a(0)} {a(1)}) #b1 #b0)"
    if op == "neq":
        return f"(ite (distinct {a(0)} {a(1)}) #b1 #b0)"
    if op in _CMP:
        return f"(ite ({_CMP[op]} {a(0)} {a(1)}) #b1 #b0)"
    if op == "implies":
        return f"(ite (=> (= {a(0)} #b1) (= {a(1)} #b1)) #b1 #b0)"
    if op == "iff":
        return f"(ite (= {a(0)} {a(1)}) #b1 #b0)"
    if op == "redor":
        aw = sys.sorts[sys.nodes[node.refs[0]].sort].width
        return f"(ite (distinct {a(0)} (_ bv0 {aw})) #b1 #b0)"
    if op == "redand":
        aw = sys.sorts[sys.nodes[node.refs[0]].sort].width
        return f"(ite (= {a(0)} (_ bv{(1 << aw) - 1} {aw})) #b1 #b0)"
    if op == "slice":
        upper, lower = node.bounds
        return f"((_ extract {upper} {lower}) {a(0)})"
    if op == "sext":
        return f"((_ sign_extend {node.bounds[0]}) {a(0)})"
    if op == "uext":
        return f"((_ zero_extend {node.bounds[0]}) {a(0)})"
    if op == "ite":
        return f"(ite (= {a(0)} #b1) {a(1)} {a(2)})"
    if op == "read":
        return f"(select {a(0)} {a(1)})"
    if op == "write":
        return f"(store {a(0)} {a(1)} {a(2)})"
    raise Unsupported("btor2-smtlib", f"op.{op}")


def translate(program: dict[str, Any]) -> bytes:
    sys = _as_system(program["system"])
    k = int(program["k"])

    states = sys.states()
    inputs = [n for n in sys.nodes.values() if n.op == "input"]
    value_ids = sorted(nid for nid, n in sys.nodes.items() if n.op not in _DIRECTIVES
                       and n.op not in ("state", "input"))

    lines = ["(set-logic QF_ABV)"]
    for t in range(k + 1):
        for s in states:
            lines.append(f"(declare-fun s{s.id}_{t} () {_sort_str(sys, s.sort)})")
        for inp in inputs:
            lines.append(f"(declare-fun i{inp.id}_{t} () {_sort_str(sys, inp.sort)})")
        for nid in value_ids:
            node = sys.nodes[nid]
            lines.append(f"(define-fun n{nid}_{t} () {_sort_str(sys, node.sort)} {_expr(sys, node, t)})")

    # init: state_0 == init value (at step 0)
    for n in sys.nodes.values():
        if n.op == "init":
            lines.append(f"(assert (= {_name(sys, n.refs[0], 0)} {_name(sys, n.refs[1], 0)}))")
    # transitions: state_{t+1} == next value (at step t)
    for t in range(k):
        for n in sys.nodes.values():
            if n.op == "next":
                lines.append(f"(assert (= {_name(sys, n.refs[0], t + 1)} {_name(sys, n.refs[1], t)}))")
    # bad reachable within k: OR over bads, steps 0..k
    disj = [f"(= {_name(sys, bn.refs[0], t)} #b1)" for bn in sys.bads() for t in range(k + 1)]
    if disj:
        lines.append(f"(assert (or {' '.join(disj)}))" if len(disj) > 1 else f"(assert {disj[0]})")
    else:
        lines.append("(assert false)")  # no bad => nothing to reach
    lines.append("(check-sat)")
    return ("\n".join(lines) + "\n").encode("utf-8")
