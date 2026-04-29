"""Compile a parsed BTOR2 ``Model`` into a Z3 BMC encoding.

This is a small, self-contained translator from the subset of BTOR2
the riscv-btor2 pair emits into Z3 expressions. It is *not* a full
HWMCC-grade BTOR2 backend; it covers exactly the operators the
library and translation layers produce.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from gurdy.pairs.riscv_btor2.btor2.nodes import ArraySort, BitvecSort, Model, Node


# z3 is an optional runtime dependency. Importing this module must not
# fail when z3 is absent — that would break pair registration in
# environments where the BMC backend isn't going to be exercised. We
# attempt the import and store None on failure; ``bmc`` checks before
# running, and the Z3BMCSolver wrapper converts the absence into a
# structured RawSolverResult error.
try:
    import z3 as _z3
except ImportError:  # pragma: no cover - exercised only without z3
    _z3 = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover
    import z3


def _require_z3():
    if _z3 is None:
        raise ImportError("z3-solver is not installed")
    return _z3


@dataclass
class CompiledZ3:
    """A BMC-ready Z3 representation of a BTOR2 model."""

    sort_widths: dict[int, int] = field(default_factory=dict)
    array_meta: dict[int, tuple[int, int]] = field(default_factory=dict)

    # node_kind: 'state', 'input', 'expr', 'const'.
    node_kind: dict[int, str] = field(default_factory=dict)

    # For each node, a function (state_vec, input_vec) -> z3.ExprRef.
    # state_vec / input_vec are dicts keyed on nid.
    builders: dict[int, Any] = field(default_factory=dict)

    state_nids: list[int] = field(default_factory=list)
    input_nids: list[int] = field(default_factory=list)
    init_pairs: list[tuple[int, int]] = field(default_factory=list)
    next_pairs: list[tuple[int, int]] = field(default_factory=list)
    bad_nids: list[int] = field(default_factory=list)
    constraint_nids: list[int] = field(default_factory=list)


def compile_to_z3(model: Model) -> CompiledZ3:
    out = CompiledZ3()
    for node in model.nodes():
        op = node.op
        if op == "sort":
            if isinstance(node.sort, BitvecSort):
                out.sort_widths[node.nid] = node.sort.width
            elif isinstance(node.sort, ArraySort):
                out.array_meta[node.nid] = (
                    node.sort.index_sort_nid,
                    node.sort.element_sort_nid,
                )
            continue
        if op == "state":
            out.state_nids.append(node.nid)
            sort_nid = int(node.args[0])
            out.node_kind[node.nid] = "state"
            out.builders[node.nid] = ("state", node.nid, sort_nid)
            continue
        if op == "input":
            out.input_nids.append(node.nid)
            sort_nid = int(node.args[0])
            out.node_kind[node.nid] = "input"
            out.builders[node.nid] = ("input", node.nid, sort_nid)
            continue
        if op == "init":
            sort_nid = int(node.args[0])
            state_nid = int(node.args[1])
            value_nid = int(node.args[2])
            out.init_pairs.append((state_nid, value_nid))
            continue
        if op == "next":
            sort_nid = int(node.args[0])
            state_nid = int(node.args[1])
            value_nid = int(node.args[2])
            out.next_pairs.append((state_nid, value_nid))
            continue
        if op == "bad":
            out.bad_nids.append(int(node.args[0]))
            continue
        if op == "constraint":
            out.constraint_nids.append(int(node.args[0]))
            continue
        # Generic: store builder.
        out.node_kind[node.nid] = "expr"
        out.builders[node.nid] = ("op", op, [int(a) for a in node.args])
    return out


def _bv_const(width: int, value: int) -> "z3.BitVecNumRef":
    return _z3.BitVecVal(value & ((1 << width) - 1), width)


def _make_var(name: str, sort_nid: int, comp: CompiledZ3) -> Any:
    if sort_nid in comp.sort_widths:
        return _z3.BitVec(name, comp.sort_widths[sort_nid])
    if sort_nid in comp.array_meta:
        idx_s, elt_s = comp.array_meta[sort_nid]
        idx_w = comp.sort_widths[idx_s]
        elt_w = comp.sort_widths[elt_s]
        return _z3.Array(name, _z3.BitVecSort(idx_w), _z3.BitVecSort(elt_w))
    raise ValueError(f"unknown sort nid {sort_nid}")


def _eval_node(nid: int, env: dict[int, Any], comp: CompiledZ3) -> Any:
    if nid in env:
        return env[nid]
    builder = comp.builders.get(nid)
    if builder is None:
        # Constant-style node: zero, one, ones, constd, const, consth.
        # Re-fetch via raw model lookup.
        raise KeyError(f"no builder for nid {nid}")
    kind, *rest = builder
    if kind in ("state", "input"):
        # Already pre-bound by the BMC driver.
        raise KeyError(f"unbound {kind} nid {nid}")
    op, args = rest
    return _eval_op(nid, op, args, env, comp)


def _eval_op(nid: int, op: str, args: list[int], env: dict[int, Any], comp: CompiledZ3) -> Any:
    if op == "zero":
        return _bv_const(comp.sort_widths[args[0]], 0)
    if op == "one":
        return _bv_const(comp.sort_widths[args[0]], 1)
    if op == "ones":
        w = comp.sort_widths[args[0]]
        return _bv_const(w, (1 << w) - 1)
    if op == "constd":
        return _bv_const(comp.sort_widths[args[0]], args[1])
    if op == "const":
        return _bv_const(comp.sort_widths[args[0]], args[1])
    if op == "consth":
        return _bv_const(comp.sort_widths[args[0]], args[1])

    # Ops with mixed integer / nid args. The generic loop below assumes
    # every arg after the result sort is a nid, which is wrong for these
    # — slice's hi/lo and sext/uext's count are integer indices, not nids.
    # When such an integer happens to be 0, _eval_node raises
    # `no builder for nid 0`; for other small integers it silently looks
    # up the wrong node. Short-circuit them first.
    if op == "slice":
        operand = _eval_node(args[1], env, comp)
        return _z3.Extract(args[2], args[3], operand)
    if op == "sext":
        operand = _eval_node(args[1], env, comp)
        target_w = comp.sort_widths[args[0]]
        return _z3.SignExt(target_w - operand.size(), operand)
    if op == "uext":
        operand = _eval_node(args[1], env, comp)
        target_w = comp.sort_widths[args[0]]
        return _z3.ZeroExt(target_w - operand.size(), operand)

    # All other ops are operators with the first arg = result sort.
    result_sort = args[0]
    operands = [_eval_node(a, env, comp) for a in args[1:]]
    if op == "add":
        return operands[0] + operands[1]
    if op == "sub":
        return operands[0] - operands[1]
    if op == "mul":
        return operands[0] * operands[1]
    if op == "and":
        return operands[0] & operands[1]
    if op == "or":
        return operands[0] | operands[1]
    if op == "xor":
        return operands[0] ^ operands[1]
    if op == "not":
        return ~operands[0]
    if op == "neg":
        return -operands[0]
    if op == "sll":
        return operands[0] << operands[1]
    if op == "srl":
        return _z3.LShR(operands[0], operands[1])
    if op == "sra":
        return operands[0] >> operands[1]
    if op == "udiv":
        return _z3.UDiv(operands[0], operands[1])
    if op == "urem":
        return _z3.URem(operands[0], operands[1])
    if op == "sdiv":
        return operands[0] / operands[1]
    if op == "srem":
        return _z3.SRem(operands[0], operands[1])
    if op == "eq":
        return _z3.If(operands[0] == operands[1], _bv_const(1, 1), _bv_const(1, 0))
    if op == "neq":
        return _z3.If(operands[0] != operands[1], _bv_const(1, 1), _bv_const(1, 0))
    if op == "slt":
        return _z3.If(operands[0] < operands[1], _bv_const(1, 1), _bv_const(1, 0))
    if op == "sgt":
        return _z3.If(operands[0] > operands[1], _bv_const(1, 1), _bv_const(1, 0))
    if op == "slte":
        return _z3.If(operands[0] <= operands[1], _bv_const(1, 1), _bv_const(1, 0))
    if op == "sgte":
        return _z3.If(operands[0] >= operands[1], _bv_const(1, 1), _bv_const(1, 0))
    if op == "ult":
        return _z3.If(_z3.ULT(operands[0], operands[1]), _bv_const(1, 1), _bv_const(1, 0))
    if op == "ugt":
        return _z3.If(_z3.UGT(operands[0], operands[1]), _bv_const(1, 1), _bv_const(1, 0))
    if op == "ulte":
        return _z3.If(_z3.ULE(operands[0], operands[1]), _bv_const(1, 1), _bv_const(1, 0))
    if op == "ugte":
        return _z3.If(_z3.UGE(operands[0], operands[1]), _bv_const(1, 1), _bv_const(1, 0))
    if op == "ite":
        cond_bv = operands[0]  # bv1
        cond = cond_bv == _bv_const(1, 1)
        return _z3.If(cond, operands[1], operands[2])
    if op == "concat":
        return _z3.Concat(operands[0], operands[1])
    if op == "read":
        return _z3.Select(operands[0], operands[1])
    if op == "write":
        return _z3.Update(operands[0], operands[1], operands[2])
    raise NotImplementedError(f"btor2_to_z3: unsupported op {op!r}")


def _evaluate_all(env: dict[int, Any], comp: CompiledZ3) -> dict[int, Any]:
    """Evaluate every non-state/input/structural node in topological
    order. Since node ids are assigned in declaration order, iterating
    by id suffices."""
    for nid in sorted(comp.builders):
        if comp.node_kind.get(nid) in ("state", "input"):
            continue
        env[nid] = _eval_node(nid, env, comp)
    return env


def bmc(comp: CompiledZ3, bound: int) -> tuple[str, dict[int, Any] | None]:
    """Run BMC up to ``bound`` cycles. Returns (verdict, model)."""
    _require_z3()
    solver = _z3.Solver()

    # Build state vectors for each cycle.
    state_vars: list[dict[int, Any]] = []
    for cycle in range(bound + 1):
        sv: dict[int, Any] = {}
        for nid in comp.state_nids:
            sort_nid = int(__find_sort_for(nid, comp))
            sv[nid] = _make_var(f"s{cycle}_n{nid}", sort_nid, comp)
        state_vars.append(sv)

    # Initialization: state at cycle 0 == init value.
    env0: dict[int, Any] = dict(state_vars[0])
    # Inputs at cycle 0 are also fresh symbolic vars.
    for nid in comp.input_nids:
        sort_nid = int(__find_sort_for(nid, comp))
        env0[nid] = _make_var(f"in0_n{nid}", sort_nid, comp)
    _evaluate_all(env0, comp)

    for state_nid, value_nid in comp.init_pairs:
        solver.add(env0[state_nid] == env0[value_nid])

    # Constraints at cycle 0
    for c in comp.constraint_nids:
        solver.add(env0[c] == _bv_const(1, 1))

    # Bad at cycle 0 — if any reachable, we have a counterexample.
    bad_disj_terms: list[Any] = []
    if comp.bad_nids:
        bad_disj_terms.append(_z3.Or(*[env0[b] == _bv_const(1, 1) for b in comp.bad_nids]))

    # Cycles 1..bound
    prev_env = env0
    for cycle in range(1, bound + 1):
        env: dict[int, Any] = dict(state_vars[cycle])
        for nid in comp.input_nids:
            sort_nid = int(__find_sort_for(nid, comp))
            env[nid] = _make_var(f"in{cycle}_n{nid}", sort_nid, comp)
        # Apply transition: state[cycle] == eval(next_value, prev_env)
        # Need to evaluate prev_env's exprs first.
        _evaluate_all(prev_env, comp)
        for state_nid, value_nid in comp.next_pairs:
            solver.add(env[state_nid] == prev_env[value_nid])
        _evaluate_all(env, comp)
        for c in comp.constraint_nids:
            solver.add(env[c] == _bv_const(1, 1))
        if comp.bad_nids:
            bad_disj_terms.append(
                _z3.Or(*[env[b] == _bv_const(1, 1) for b in comp.bad_nids])
            )
        prev_env = env

    if not bad_disj_terms:
        # No bad expression; nothing to violate.
        return "unreachable", None

    solver.add(_z3.Or(*bad_disj_terms))
    res = solver.check()
    if res == _z3.sat:
        m = solver.model()
        return "reachable", m
    if res == _z3.unsat:
        return "unreachable", None
    return "unknown", None


def __find_sort_for(nid: int, comp: CompiledZ3) -> int:
    """Recover the sort nid of a state/input node from its builder."""
    builder = comp.builders.get(nid)
    if builder is None or builder[0] not in ("state", "input"):
        raise KeyError(nid)
    return builder[2]


__all__ = ["compile_to_z3", "bmc", "CompiledZ3"]
