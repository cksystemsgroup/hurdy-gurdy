"""BTOR2 -> SMT-LIB bounded model checking (the BTOR2 <-> SMT-LIB bridge).

A *transparent* translation between two reasoning languages: it symbolically
unrolls a BTOR2 transition system to a bound ``k`` and emits an SMT-LIB
(QF_BV / QF_ABV) formula that is **sat iff some ``bad`` is reachable within
``k`` steps**. Every BTOR2 operator maps to the standard SMT bit-vector / array
operator that a native BTOR2 solver also uses, so the bridged verdict agrees
with the native one — which is exactly what makes a "many chains, one question"
cross-check a translator-bug detector (``DESIGN_generalized_pairs.md`` §6).

The supported operator set mirrors ``gurdy.core.btor2.evaluator`` (the concrete
BTOR2 interpreter); an unsupported op raises :class:`BridgeError` rather than
emitting a wrong encoding. See ``SCHEMA.md``.
"""

from __future__ import annotations

import hashlib
import json

from gurdy.core.annotation.types import Role
from gurdy.core.pair import CompiledArtifact, Layer
from gurdy.core.btor2.nodes import ArraySort, BitvecSort, Model
from gurdy.core.btor2.parser import from_text

SCHEMA_VERSION = "0.1.0"
PAIR_ID = "btor2-smtlib"
_META_PREFIX = "; @btor2-bmc "

# Directive / structural ops handled outside _node_expr.
_STRUCTURAL = {"sort", "state", "input", "init", "next", "bad", "constraint", "output"}


class BridgeError(ValueError):
    """Malformed BTOR2, or an operator outside the supported subset."""


def parse_btor2(payload: bytes | str | None) -> Model:
    """Source loader: BTOR2 text (bytes/str) -> in-memory ``Model``."""
    if payload is None:
        raise BridgeError("no BTOR2 source provided")
    text = (
        payload.decode("utf-8")
        if isinstance(payload, (bytes, bytearray))
        else str(payload)
    )
    return from_text(text).model


def _bv(width: int, value: int) -> str:
    return f"(_ bv{value % (1 << width)} {width})"


def _smt_sort(sort_nid: int, sorts: dict[int, tuple]) -> str:
    kind = sorts[sort_nid]
    if kind[0] == "bv":
        return f"(_ BitVec {kind[1]})"
    iw = sorts[kind[1]][1]
    ew = sorts[kind[2]][1]
    return f"(Array (_ BitVec {iw}) (_ BitVec {ew}))"


def _node_expr(node, sorts: dict[int, tuple], vn) -> str:
    """SMT-LIB expression for a combinational/const node, in terms of operand
    variables (``vn(nid)`` gives the operand's variable at the current step)."""
    op = node.op
    sort_nid = int(node.args[0])
    width = sorts[sort_nid][1] if sorts[sort_nid][0] == "bv" else None

    def a(i: int) -> str:
        return vn(int(node.args[i]))

    # constants
    if op == "zero":
        return _bv(width, 0)
    if op == "one":
        return _bv(width, 1)
    if op == "ones":
        return f"(bvnot {_bv(width, 0)})"
    if op == "constd":
        return _bv(width, int(node.args[1]))
    if op == "const":
        return _bv(width, int(node.args[1], 2))
    if op == "consth":
        return _bv(width, int(node.args[1], 16))

    # binary bit-vector
    _BIN = {
        "add": "bvadd", "sub": "bvsub", "mul": "bvmul", "and": "bvand", "or": "bvor",
        "xor": "bvxor", "sll": "bvshl", "srl": "bvlshr", "sra": "bvashr",
        "udiv": "bvudiv", "urem": "bvurem", "sdiv": "bvsdiv", "srem": "bvsrem",
    }
    if op in _BIN:
        return f"({_BIN[op]} {a(1)} {a(2)})"
    if op == "not":
        return f"(bvnot {a(1)})"
    if op == "neg":
        return f"(bvneg {a(1)})"

    # comparisons -> bv1
    _CMP = {
        "eq": None, "neq": None, "ult": "bvult", "ugt": "bvugt", "ulte": "bvule",
        "ugte": "bvuge", "slt": "bvslt", "sgt": "bvsgt", "slte": "bvsle", "sgte": "bvsge",
    }
    if op in _CMP:
        if op == "eq":
            pred = f"(= {a(1)} {a(2)})"
        elif op == "neq":
            pred = f"(not (= {a(1)} {a(2)}))"
        else:
            pred = f"({_CMP[op]} {a(1)} {a(2)})"
        return f"(ite {pred} (_ bv1 1) (_ bv0 1))"

    if op == "ite":
        return f"(ite (= {a(1)} (_ bv1 1)) {a(2)} {a(3)})"
    if op == "sext":
        return f"((_ sign_extend {int(node.args[2])}) {a(1)})"
    if op == "uext":
        return f"((_ zero_extend {int(node.args[2])}) {a(1)})"
    if op == "slice":
        return f"((_ extract {int(node.args[2])} {int(node.args[3])}) {a(1)})"
    if op == "concat":
        return f"(concat {a(1)} {a(2)})"
    if op == "read":
        return f"(select {a(1)} {a(2)})"
    if op == "write":
        return f"(store {a(1)} {a(2)} {a(3)})"

    raise BridgeError(f"unsupported BTOR2 op {op!r} (nid {node.nid})")


def encode_bmc(model: Model, bound: int) -> str:
    """Emit the SMT-LIB unrolling of ``model`` to depth ``bound``. ``sat`` iff a
    ``bad`` is reachable within ``bound`` steps."""
    if bound < 0:
        raise BridgeError("bound must be >= 0")

    sorts: dict[int, tuple] = {}
    node_sort: dict[int, int] = {}
    states, inputs, comb = [], [], []
    inits: dict[int, int] = {}
    nexts: dict[int, int] = {}
    bads: list[int] = []
    constraints: list[int] = []

    for n in model.nodes():
        op = n.op
        if op == "sort":
            if isinstance(n.sort, BitvecSort):
                sorts[n.nid] = ("bv", n.sort.width)
            elif isinstance(n.sort, ArraySort):
                sorts[n.nid] = ("array", n.sort.index_sort_nid, n.sort.element_sort_nid)
            continue
        if op == "state":
            node_sort[n.nid] = int(n.args[0])
            states.append(n)
            continue
        if op == "input":
            node_sort[n.nid] = int(n.args[0])
            inputs.append(n)
            continue
        if op == "init":
            inits[int(n.args[1])] = int(n.args[2])
            continue
        if op == "next":
            nexts[int(n.args[1])] = int(n.args[2])
            continue
        if op == "bad":
            bads.append(int(n.args[0]))
            continue
        if op == "constraint":
            constraints.append(int(n.args[0]))
            continue
        if op == "output":
            continue
        node_sort[n.nid] = int(n.args[0])
        comb.append(n)

    has_array = any(k[0] == "array" for k in sorts.values())
    logic = "QF_ABV" if has_array else "QF_BV"

    def vn(nid: int, t: int) -> str:
        return f"n{nid}_{t}"

    meta = {
        "bound": bound,
        "states": [{"nid": s.nid, "symbol": s.symbol} for s in states],
    }
    out: list[str] = [_META_PREFIX + json.dumps(meta, sort_keys=True, separators=(",", ":"))]
    out.append(f"(set-logic {logic})")

    for t in range(bound + 1):
        for s in (*states, *inputs):
            out.append(f"(declare-const {vn(s.nid, t)} {_smt_sort(node_sort[s.nid], sorts)})")
        for c in comb:
            out.append(f"(declare-const {vn(c.nid, t)} {_smt_sort(node_sort[c.nid], sorts)})")
            expr = _node_expr(c, sorts, lambda nid, _t=t: vn(nid, _t))
            out.append(f"(assert (= {vn(c.nid, t)} {expr}))")

    for state_nid, value_nid in inits.items():
        out.append(f"(assert (= {vn(state_nid, 0)} {vn(value_nid, 0)}))")
    for t in range(bound):
        for state_nid, value_nid in nexts.items():
            out.append(f"(assert (= {vn(state_nid, t + 1)} {vn(value_nid, t)}))")
    for cond in constraints:
        for t in range(bound + 1):
            out.append(f"(assert (= {vn(cond, t)} (_ bv1 1)))")

    bad_terms = [
        f"(= {vn(cond, t)} (_ bv1 1))" for cond in bads for t in range(bound + 1)
    ]
    if not bad_terms:
        out.append("; no bad properties -> nothing to reach")
        out.append("(assert false)")
    elif len(bad_terms) == 1:
        out.append(f"(assert {bad_terms[0]})")
    else:
        out.append(f"(assert (or {' '.join(bad_terms)}))")

    out.append("(check-sat)")
    out.append("(get-model)")
    return "\n".join(out) + "\n"


class _Translator:
    def translate(self, spec, source: Model, emitter) -> CompiledArtifact:
        body = encode_bmc(source, spec.bound).encode("utf-8")
        content_hash = hashlib.sha256(body).hexdigest()
        for i, s in enumerate(n for n in source.nodes() if n.op == "state"):
            emitter.emit("smtlib", i, Role.STATE, source_mapping={"state": s.symbol})
        return CompiledArtifact(
            pair=PAIR_ID,
            layers={"smtlib": Layer(name="smtlib", body=body, content_hash=content_hash)},
            annotation=emitter.sidecar,
            flattened=body,
            schema_version=SCHEMA_VERSION,
            spec_hash=spec.spec_hash(),
        )


translate = _Translator()

__all__ = ["SCHEMA_VERSION", "PAIR_ID", "BridgeError", "parse_btor2", "encode_bmc", "translate"]
