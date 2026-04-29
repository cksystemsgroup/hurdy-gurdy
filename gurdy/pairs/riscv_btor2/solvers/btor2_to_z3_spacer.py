"""z3-Spacer: encode a compiled BTOR2 transition system as Horn
clauses and query Spacer for an inductive proof / counterexample.

Spacer is a separate beast from BMC. It does not unroll cycle-by-
cycle; instead it discovers an inductive invariant ``Inv(state)``
from three Horn rules:

  init:  init_clauses(s)                        => Inv(s)
  trans: Inv(s) ∧ next_clauses(s → s')          => Inv(s')
  bad:   Inv(s) ∧ bad_clauses(s)                => Goal()

If ``Goal()`` is *unreachable* in the Horn-clause derivation, Inv is
a real inductive invariant and the property holds at all depths
(verdict ``proved``). If reachable, the property has a (witnessable)
counterexample (verdict ``reachable``). Otherwise ``unknown``.

The encoding reuses ``Z3Backend.apply_op`` for the BTOR2→z3
expression translation; only the driver (cycle vs Horn) differs.

Caveats
-------

- Spacer's array-theory support is partial; pairs whose property
  depends on memory state may time out or return ``unknown``. The
  bench's BMC backends are usable for those.
- This is "best-effort Spacer": the encoding is the natural Horn
  rendering of the BTOR2 transition system, with no
  abstraction/refinement tricks.
"""

from __future__ import annotations

from typing import Any

from gurdy.pairs.riscv_btor2.solvers._bmc import (
    Compiled,
    compile_btor2,
    evaluate_all,
    find_sort_for,
)

try:
    import z3 as _z3
except ImportError:  # pragma: no cover
    _z3 = None  # type: ignore[assignment]


def _require_z3():
    if _z3 is None:
        raise ImportError("z3-solver is not installed")
    return _z3


def _make_state_var(name: str, sort_nid: int, comp: Compiled):
    """Create one z3 variable for a state nid based on its declared sort."""
    if sort_nid in comp.sort_widths:
        return _z3.BitVec(name, comp.sort_widths[sort_nid])
    if sort_nid in comp.array_meta:
        idx_s, elt_s = comp.array_meta[sort_nid]
        return _z3.Array(
            name,
            _z3.BitVecSort(comp.sort_widths[idx_s]),
            _z3.BitVecSort(comp.sort_widths[elt_s]),
        )
    raise ValueError(f"unknown sort nid {sort_nid}")


def _state_sort(sort_nid: int, comp: Compiled):
    if sort_nid in comp.sort_widths:
        return _z3.BitVecSort(comp.sort_widths[sort_nid])
    if sort_nid in comp.array_meta:
        idx_s, elt_s = comp.array_meta[sort_nid]
        return _z3.ArraySort(
            _z3.BitVecSort(comp.sort_widths[idx_s]),
            _z3.BitVecSort(comp.sort_widths[elt_s]),
        )
    raise ValueError(f"unknown sort nid {sort_nid}")


def query(comp: Compiled, *, timeout_ms: int | None = None) -> tuple[str, Any]:
    """Encode the system as Horn clauses and run Spacer.

    Returns ``(verdict, fixedpoint)`` where verdict is one of
    ``'reachable'`` / ``'proved'`` / ``'unknown'``. The fixedpoint
    object is engine-specific and only useful when the verdict is
    ``proved`` (caller can extract the inductive invariant via
    ``fp.get_cover_delta``).
    """
    _require_z3()
    # Local import to avoid a cycle: Z3Backend lives in btor2_to_z3
    # which imports _bmc; this module also imports _bmc but not z3.
    from gurdy.pairs.riscv_btor2.solvers.btor2_to_z3 import Z3Backend

    backend = Z3Backend()
    fp = _z3.Fixedpoint()
    fp.set("engine", "spacer")
    if timeout_ms is not None:
        fp.set("timeout", int(timeout_ms))

    # --- Declare state and primed-state variables ------------------------
    # Order is comp.state_nids (already sorted by declaration order).
    state_sorts = [_state_sort(find_sort_for(nid, comp), comp) for nid in comp.state_nids]
    state_vars_s = {
        nid: _make_state_var(f"s_{nid}", find_sort_for(nid, comp), comp)
        for nid in comp.state_nids
    }
    state_vars_sp = {
        nid: _make_state_var(f"sp_{nid}", find_sort_for(nid, comp), comp)
        for nid in comp.state_nids
    }

    # --- Declare Inv(state...) and Goal() -------------------------------
    inv = _z3.Function("Inv", *state_sorts, _z3.BoolSort())
    fp.register_relation(inv)
    goal = _z3.Function("Goal", _z3.BoolSort())
    fp.register_relation(goal)

    inv_args_s = [state_vars_s[nid] for nid in comp.state_nids]
    inv_args_sp = [state_vars_sp[nid] for nid in comp.state_nids]
    for v in inv_args_s + inv_args_sp:
        fp.declare_var(v)

    # --- Build init rule -------------------------------------------------
    init_env = dict(state_vars_s)
    for nid in comp.input_nids:
        sort_nid = find_sort_for(nid, comp)
        init_env[nid] = _make_state_var(f"in_init_{nid}", sort_nid, comp)
        fp.declare_var(init_env[nid])
    evaluate_all(init_env, comp, backend)

    init_clauses = [
        state_vars_s[state_nid] == init_env[value_nid]
        for state_nid, value_nid in comp.init_pairs
    ]
    init_clauses += [
        init_env[c] == _z3.BitVecVal(1, 1) for c in comp.constraint_nids
    ]
    body = _z3.And(*init_clauses) if init_clauses else _z3.BoolVal(True)
    fp.rule(inv(*inv_args_s), body)

    # --- Build trans rule ------------------------------------------------
    trans_env = dict(state_vars_s)
    for nid in comp.input_nids:
        sort_nid = find_sort_for(nid, comp)
        trans_env[nid] = _make_state_var(f"in_trans_{nid}", sort_nid, comp)
        fp.declare_var(trans_env[nid])
    evaluate_all(trans_env, comp, backend)

    trans_clauses = [
        state_vars_sp[state_nid] == trans_env[value_nid]
        for state_nid, value_nid in comp.next_pairs
    ]
    trans_clauses += [
        trans_env[c] == _z3.BitVecVal(1, 1) for c in comp.constraint_nids
    ]
    trans_body = _z3.And(inv(*inv_args_s), *trans_clauses)
    fp.rule(inv(*inv_args_sp), trans_body)

    # --- Build bad rule --------------------------------------------------
    if not comp.bad_nids:
        return "proved", fp  # No bad clause, vacuously safe.

    bad_env = dict(state_vars_s)
    for nid in comp.input_nids:
        sort_nid = find_sort_for(nid, comp)
        bad_env[nid] = _make_state_var(f"in_bad_{nid}", sort_nid, comp)
        fp.declare_var(bad_env[nid])
    evaluate_all(bad_env, comp, backend)

    bad_terms = [bad_env[b] == _z3.BitVecVal(1, 1) for b in comp.bad_nids]
    bad_disj = _z3.Or(*bad_terms) if len(bad_terms) > 1 else bad_terms[0]
    bad_body = _z3.And(inv(*inv_args_s), bad_disj)
    fp.rule(goal(), bad_body)

    # --- Query -----------------------------------------------------------
    res = fp.query(goal())
    if res == _z3.sat:
        return "reachable", fp
    if res == _z3.unsat:
        return "proved", fp
    return "unknown", fp


__all__ = ["query", "compile_btor2"]
