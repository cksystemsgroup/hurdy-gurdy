"""Compile a parsed BTOR2 ``Model`` into a Bitwuzla BMC encoding.

Mirrors ``btor2_to_z3.py`` but emits Bitwuzla terms via the Python
bindings. Bitwuzla's own BTOR2 parser does not support model-checking
extensions (`init` / `next` / `bad` / `constraint`), so we drive the
unrolling explicitly the same way the z3 backend does.

Reuses ``btor2_to_z3.compile_to_z3`` for the structural compile —
that function produces engine-agnostic `(op, args)` builders and is
named after z3 only by historical accident.
"""

from __future__ import annotations

from typing import Any

from gurdy.pairs.riscv_btor2.solvers.btor2_to_z3 import CompiledZ3, compile_to_z3

try:
    import bitwuzla as _bw
except ImportError:  # pragma: no cover
    _bw = None  # type: ignore[assignment]


def _require_bw():
    if _bw is None:
        raise ImportError("bitwuzla bindings not installed")
    return _bw


def _bv_sort(tm: Any, w: int) -> Any:
    return tm.mk_bv_sort(w)


def _bv_const(tm: Any, w: int, v: int) -> Any:
    return tm.mk_bv_value(_bv_sort(tm, w), v & ((1 << w) - 1))


def _make_var(tm: Any, name: str, sort_nid: int, comp: CompiledZ3) -> Any:
    if sort_nid in comp.sort_widths:
        return tm.mk_const(_bv_sort(tm, comp.sort_widths[sort_nid]), name)
    if sort_nid in comp.array_meta:
        idx_s, elt_s = comp.array_meta[sort_nid]
        idx_w = comp.sort_widths[idx_s]
        elt_w = comp.sort_widths[elt_s]
        sort = tm.mk_array_sort(_bv_sort(tm, idx_w), _bv_sort(tm, elt_w))
        return tm.mk_const(sort, name)
    raise ValueError(f"unknown sort nid {sort_nid}")


def _eval_node(nid: int, env: dict[int, Any], comp: CompiledZ3, tm: Any) -> Any:
    if nid in env:
        return env[nid]
    builder = comp.builders.get(nid)
    if builder is None:
        raise KeyError(f"no builder for nid {nid}")
    kind, *rest = builder
    if kind in ("state", "input"):
        raise KeyError(f"unbound {kind} nid {nid}")
    op, args = rest
    return _eval_op(nid, op, args, env, comp, tm)


def _eval_op(
    nid: int, op: str, args: list[int], env: dict[int, Any], comp: CompiledZ3, tm: Any
) -> Any:
    K = _bw.Kind
    if op == "zero":
        return tm.mk_bv_zero(_bv_sort(tm, comp.sort_widths[args[0]]))
    if op == "one":
        return tm.mk_bv_one(_bv_sort(tm, comp.sort_widths[args[0]]))
    if op == "ones":
        return tm.mk_bv_ones(_bv_sort(tm, comp.sort_widths[args[0]]))
    if op in ("constd", "const", "consth"):
        return _bv_const(tm, comp.sort_widths[args[0]], args[1])

    # Mixed integer/nid arg ops — see btor2_to_z3.py for the fix history.
    if op == "slice":
        operand = _eval_node(args[1], env, comp, tm)
        return tm.mk_term(K.BV_EXTRACT, [operand], [args[2], args[3]])
    if op == "sext":
        operand = _eval_node(args[1], env, comp, tm)
        target_w = comp.sort_widths[args[0]]
        in_w = operand.sort().bv_size()
        return tm.mk_term(K.BV_SIGN_EXTEND, [operand], [target_w - in_w])
    if op == "uext":
        operand = _eval_node(args[1], env, comp, tm)
        target_w = comp.sort_widths[args[0]]
        in_w = operand.sort().bv_size()
        return tm.mk_term(K.BV_ZERO_EXTEND, [operand], [target_w - in_w])

    operands = [_eval_node(a, env, comp, tm) for a in args[1:]]

    # Comparison ops return bv1 (per btor2 convention) — bitwuzla's
    # comparison kinds return Bool, so we wrap with ITE(cond, 1, 0).
    bv1 = _bv_sort(tm, 1)
    one1 = tm.mk_bv_one(bv1)
    zero1 = tm.mk_bv_zero(bv1)

    def bool_to_bv1(b):
        return tm.mk_term(K.ITE, [b, one1, zero1])

    if op == "add":
        return tm.mk_term(K.BV_ADD, operands)
    if op == "sub":
        return tm.mk_term(K.BV_SUB, operands)
    if op == "mul":
        return tm.mk_term(K.BV_MUL, operands)
    if op == "and":
        return tm.mk_term(K.BV_AND, operands)
    if op == "or":
        return tm.mk_term(K.BV_OR, operands)
    if op == "xor":
        return tm.mk_term(K.BV_XOR, operands)
    if op == "not":
        return tm.mk_term(K.BV_NOT, operands)
    if op == "neg":
        return tm.mk_term(K.BV_NEG, operands)
    if op == "sll":
        return tm.mk_term(K.BV_SHL, operands)
    if op == "srl":
        return tm.mk_term(K.BV_SHR, operands)
    if op == "sra":
        return tm.mk_term(K.BV_ASHR, operands)
    if op == "udiv":
        return tm.mk_term(K.BV_UDIV, operands)
    if op == "urem":
        return tm.mk_term(K.BV_UREM, operands)
    if op == "sdiv":
        return tm.mk_term(K.BV_SDIV, operands)
    if op == "srem":
        return tm.mk_term(K.BV_SREM, operands)
    if op == "eq":
        return bool_to_bv1(tm.mk_term(K.EQUAL, operands))
    if op == "neq":
        return bool_to_bv1(tm.mk_term(K.DISTINCT, operands))
    if op == "slt":
        return bool_to_bv1(tm.mk_term(K.BV_SLT, operands))
    if op == "sgt":
        return bool_to_bv1(tm.mk_term(K.BV_SGT, operands))
    if op == "slte":
        return bool_to_bv1(tm.mk_term(K.BV_SLE, operands))
    if op == "sgte":
        return bool_to_bv1(tm.mk_term(K.BV_SGE, operands))
    if op == "ult":
        return bool_to_bv1(tm.mk_term(K.BV_ULT, operands))
    if op == "ugt":
        return bool_to_bv1(tm.mk_term(K.BV_UGT, operands))
    if op == "ulte":
        return bool_to_bv1(tm.mk_term(K.BV_ULE, operands))
    if op == "ugte":
        return bool_to_bv1(tm.mk_term(K.BV_UGE, operands))
    if op == "ite":
        # operands[0] is bv1; convert to Bool first.
        cond = tm.mk_term(K.EQUAL, [operands[0], one1])
        return tm.mk_term(K.ITE, [cond, operands[1], operands[2]])
    if op == "concat":
        return tm.mk_term(K.BV_CONCAT, operands)
    if op == "read":
        return tm.mk_term(K.ARRAY_SELECT, operands)
    if op == "write":
        return tm.mk_term(K.ARRAY_STORE, operands)
    raise NotImplementedError(f"btor2_to_bitwuzla: unsupported op {op!r}")


def _evaluate_all(env: dict[int, Any], comp: CompiledZ3, tm: Any) -> dict[int, Any]:
    for nid in sorted(comp.builders):
        if comp.node_kind.get(nid) in ("state", "input"):
            continue
        env[nid] = _eval_node(nid, env, comp, tm)
    return env


def _find_sort_for(nid: int, comp: CompiledZ3) -> int:
    builder = comp.builders.get(nid)
    if builder is None or builder[0] not in ("state", "input"):
        raise KeyError(nid)
    return builder[2]


def bmc(comp: CompiledZ3, bound: int) -> tuple[str, Any]:
    """Run BMC up to ``bound`` cycles. Returns (verdict, solver-or-None)."""
    _require_bw()
    tm = _bw.TermManager()
    opts = _bw.Options()
    opts.set(_bw.Option.PRODUCE_MODELS, True)
    solver = _bw.Bitwuzla(tm, opts)
    K = _bw.Kind
    bv1 = _bv_sort(tm, 1)
    one1 = tm.mk_bv_one(bv1)

    state_vars: list[dict[int, Any]] = []
    for cycle in range(bound + 1):
        sv: dict[int, Any] = {}
        for nid in comp.state_nids:
            sort_nid = _find_sort_for(nid, comp)
            sv[nid] = _make_var(tm, f"s{cycle}_n{nid}", sort_nid, comp)
        state_vars.append(sv)

    env0: dict[int, Any] = dict(state_vars[0])
    for nid in comp.input_nids:
        sort_nid = _find_sort_for(nid, comp)
        env0[nid] = _make_var(tm, f"in0_n{nid}", sort_nid, comp)
    _evaluate_all(env0, comp, tm)

    for state_nid, value_nid in comp.init_pairs:
        solver.assert_formula(tm.mk_term(K.EQUAL, [env0[state_nid], env0[value_nid]]))

    for c in comp.constraint_nids:
        solver.assert_formula(tm.mk_term(K.EQUAL, [env0[c], one1]))

    bad_disj_terms: list[Any] = []
    if comp.bad_nids:
        per_cycle = [tm.mk_term(K.EQUAL, [env0[b], one1]) for b in comp.bad_nids]
        bad_disj_terms.append(tm.mk_term(K.OR, per_cycle) if len(per_cycle) > 1 else per_cycle[0])

    prev_env = env0
    for cycle in range(1, bound + 1):
        env: dict[int, Any] = dict(state_vars[cycle])
        for nid in comp.input_nids:
            sort_nid = _find_sort_for(nid, comp)
            env[nid] = _make_var(tm, f"in{cycle}_n{nid}", sort_nid, comp)
        _evaluate_all(prev_env, comp, tm)
        for state_nid, value_nid in comp.next_pairs:
            solver.assert_formula(
                tm.mk_term(K.EQUAL, [env[state_nid], prev_env[value_nid]])
            )
        _evaluate_all(env, comp, tm)
        for c in comp.constraint_nids:
            solver.assert_formula(tm.mk_term(K.EQUAL, [env[c], one1]))
        if comp.bad_nids:
            per_cycle = [tm.mk_term(K.EQUAL, [env[b], one1]) for b in comp.bad_nids]
            bad_disj_terms.append(
                tm.mk_term(K.OR, per_cycle) if len(per_cycle) > 1 else per_cycle[0]
            )
        prev_env = env

    if not bad_disj_terms:
        return "unreachable", None

    if len(bad_disj_terms) == 1:
        solver.assert_formula(bad_disj_terms[0])
    else:
        solver.assert_formula(tm.mk_term(K.OR, bad_disj_terms))

    res = solver.check_sat()
    if res == _bw.Result.SAT:
        return "reachable", solver
    if res == _bw.Result.UNSAT:
        return "unreachable", None
    return "unknown", None


__all__ = ["bmc", "compile_to_z3"]
