"""Backend-agnostic BMC for compiled BTOR2 models.

Three pieces:

1. ``Compiled``: the engine-neutral structural form a parsed BTOR2
   model is reduced to. Sort widths, array meta, ordered builders
   for every node, plus the model-checking entries (state / input /
   init / next / bad / constraint).

2. ``Backend``: a Protocol every engine adapter satisfies. It is
   the union of "make a term" and "drive a solver" — every method
   the BMC unroller needs to be engine-agnostic.

3. ``bmc(comp, bound, backend)``: the unroller. Walks `bound` cycles,
   builds state/input variables, asserts init / next / constraint
   and the disjunction of bad-at-any-cycle, then calls check_sat.

Adding a new engine is one Backend implementation; the unroller is
shared. See ``z3bmc.py`` and ``bitwuzla.py`` for the two existing
adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from gurdy.pairs.riscv_btor2.btor2.nodes import ArraySort, BitvecSort, Model


# ---------------------------------------------------------------------------
# Compiled (engine-neutral)
# ---------------------------------------------------------------------------


@dataclass
class Compiled:
    """A BMC-ready structural form of a parsed BTOR2 ``Model``."""

    sort_widths: dict[int, int] = field(default_factory=dict)
    array_meta: dict[int, tuple[int, int]] = field(default_factory=dict)

    # node_kind: 'state' | 'input' | 'expr' | 'const' (when set).
    node_kind: dict[int, str] = field(default_factory=dict)

    # builders[nid] is one of:
    #   ('state', nid, sort_nid)
    #   ('input', nid, sort_nid)
    #   ('op', op_name, [arg_nids])    # op-shaped node
    builders: dict[int, Any] = field(default_factory=dict)

    state_nids: list[int] = field(default_factory=list)
    input_nids: list[int] = field(default_factory=list)
    init_pairs: list[tuple[int, int]] = field(default_factory=list)
    next_pairs: list[tuple[int, int]] = field(default_factory=list)
    bad_nids: list[int] = field(default_factory=list)
    constraint_nids: list[int] = field(default_factory=list)


def compile_btor2(model: Model) -> Compiled:
    out = Compiled()
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
            out.init_pairs.append((int(node.args[1]), int(node.args[2])))
            continue
        if op == "next":
            out.next_pairs.append((int(node.args[1]), int(node.args[2])))
            continue
        if op == "bad":
            out.bad_nids.append(int(node.args[0]))
            continue
        if op == "constraint":
            out.constraint_nids.append(int(node.args[0]))
            continue
        out.node_kind[node.nid] = "expr"
        out.builders[node.nid] = ("op", op, [int(a) for a in node.args])
    return out


def find_sort_for(nid: int, comp: Compiled) -> int:
    """Return the sort_nid of a state/input node from its builder."""
    builder = comp.builders.get(nid)
    if builder is None or builder[0] not in ("state", "input"):
        raise KeyError(nid)
    return builder[2]


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------


class Backend(Protocol):
    """Engine adapter. ``Term`` and ``Solver`` are opaque to the caller."""

    # Sort / variable creation
    def make_var(self, name: str, sort_nid: int, comp: Compiled) -> Any: ...
    def width_of(self, term: Any) -> int: ...

    # Constants
    def bv_const(self, width: int, value: int) -> Any: ...
    def bv_zero(self, width: int) -> Any: ...
    def bv_one(self, width: int) -> Any: ...
    def bv_ones(self, width: int) -> Any: ...

    # Operator dispatch (slice/sext/uext args may be integer indices,
    # not nids; the driver pre-evaluates the operand nid and passes
    # both args and operands through).
    def apply_op(
        self,
        op: str,
        args: list[int],
        operands: list[Any],
        comp: Compiled,
    ) -> Any: ...

    # Solver primitives
    def make_solver(self) -> Any: ...
    def assert_eq(self, solver: Any, a: Any, b: Any) -> None: ...
    def assert_term(self, solver: Any, term: Any) -> None: ...
    def make_or(self, terms: list[Any]) -> Any: ...
    def make_eq_bv1_one(self, term: Any) -> Any: ...
    def check_sat(self, solver: Any) -> str:  # 'sat' | 'unsat' | 'unknown'
        ...


# ---------------------------------------------------------------------------
# Generic evaluator
# ---------------------------------------------------------------------------


def _eval_node(
    nid: int, env: dict[int, Any], comp: Compiled, backend: Backend
) -> Any:
    if nid in env:
        return env[nid]
    builder = comp.builders.get(nid)
    if builder is None:
        raise KeyError(f"no builder for nid {nid}")
    kind, *rest = builder
    if kind in ("state", "input"):
        raise KeyError(f"unbound {kind} nid {nid}")
    op, args = rest
    return _eval_op(nid, op, args, env, comp, backend)


def _eval_op(
    nid: int,
    op: str,
    args: list[int],
    env: dict[int, Any],
    comp: Compiled,
    backend: Backend,
) -> Any:
    # Constant ops
    if op == "zero":
        return backend.bv_zero(comp.sort_widths[args[0]])
    if op == "one":
        return backend.bv_one(comp.sort_widths[args[0]])
    if op == "ones":
        return backend.bv_ones(comp.sort_widths[args[0]])
    if op in ("constd", "const", "consth"):
        return backend.bv_const(comp.sort_widths[args[0]], args[1])

    # Mixed integer / nid arg ops: only args[1] is a nid; args[2..] are
    # integer indices (slice hi/lo) or counts (sext/uext). Eagerly
    # evaluating args[1:] as nids is wrong; pre-evaluate just args[1].
    if op in ("slice", "sext", "uext"):
        operand = _eval_node(args[1], env, comp, backend)
        return backend.apply_op(op, args, [operand], comp)

    operands = [_eval_node(a, env, comp, backend) for a in args[1:]]
    return backend.apply_op(op, args, operands, comp)


def _evaluate_all(
    env: dict[int, Any], comp: Compiled, backend: Backend
) -> dict[int, Any]:
    for nid in sorted(comp.builders):
        if comp.node_kind.get(nid) in ("state", "input"):
            continue
        env[nid] = _eval_node(nid, env, comp, backend)
    return env


# ---------------------------------------------------------------------------
# BMC driver
# ---------------------------------------------------------------------------


def bmc(comp: Compiled, bound: int, backend: Backend) -> tuple[str, Any]:
    """Run BMC up to ``bound`` cycles. Returns (verdict, solver_or_None).

    Verdict is one of ``'reachable'`` / ``'unreachable'`` / ``'unknown'``.
    The returned solver is engine-specific and is only useful when the
    verdict is ``'reachable'`` (caller can extract a model).
    """
    solver = backend.make_solver()

    # Build state vectors for each cycle.
    state_vars: list[dict[int, Any]] = []
    for cycle in range(bound + 1):
        sv: dict[int, Any] = {}
        for nid in comp.state_nids:
            sort_nid = find_sort_for(nid, comp)
            sv[nid] = backend.make_var(f"s{cycle}_n{nid}", sort_nid, comp)
        state_vars.append(sv)

    # Cycle-0 environment: state vars + cycle-0 input vars.
    env0: dict[int, Any] = dict(state_vars[0])
    for nid in comp.input_nids:
        sort_nid = find_sort_for(nid, comp)
        env0[nid] = backend.make_var(f"in0_n{nid}", sort_nid, comp)
    _evaluate_all(env0, comp, backend)

    # Init: state at cycle 0 == evaluated init expression.
    for state_nid, value_nid in comp.init_pairs:
        backend.assert_eq(solver, env0[state_nid], env0[value_nid])

    # Constraints at cycle 0.
    for c in comp.constraint_nids:
        backend.assert_term(solver, backend.make_eq_bv1_one(env0[c]))

    # Bad disjunction across cycles. Each cycle contributes one Or term
    # (a disjunction over the bad_nids of that cycle).
    bad_disj_terms: list[Any] = []
    if comp.bad_nids:
        per_cycle = [backend.make_eq_bv1_one(env0[b]) for b in comp.bad_nids]
        bad_disj_terms.append(
            backend.make_or(per_cycle) if len(per_cycle) > 1 else per_cycle[0]
        )

    # Cycles 1..bound: link via next, repeat constraints/bad.
    prev_env = env0
    for cycle in range(1, bound + 1):
        env: dict[int, Any] = dict(state_vars[cycle])
        for nid in comp.input_nids:
            sort_nid = find_sort_for(nid, comp)
            env[nid] = backend.make_var(f"in{cycle}_n{nid}", sort_nid, comp)
        _evaluate_all(prev_env, comp, backend)
        for state_nid, value_nid in comp.next_pairs:
            backend.assert_eq(solver, env[state_nid], prev_env[value_nid])
        _evaluate_all(env, comp, backend)
        for c in comp.constraint_nids:
            backend.assert_term(solver, backend.make_eq_bv1_one(env[c]))
        if comp.bad_nids:
            per_cycle = [backend.make_eq_bv1_one(env[b]) for b in comp.bad_nids]
            bad_disj_terms.append(
                backend.make_or(per_cycle) if len(per_cycle) > 1 else per_cycle[0]
            )
        prev_env = env

    if not bad_disj_terms:
        return "unreachable", None

    backend.assert_term(
        solver,
        backend.make_or(bad_disj_terms) if len(bad_disj_terms) > 1 else bad_disj_terms[0],
    )
    res = backend.check_sat(solver)
    if res == "sat":
        return "reachable", solver
    if res == "unsat":
        return "unreachable", None
    return "unknown", None


__all__ = [
    "Compiled",
    "compile_btor2",
    "Backend",
    "bmc",
    "find_sort_for",
]
