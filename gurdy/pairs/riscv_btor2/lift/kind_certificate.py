"""Independent re-checker for a k-induction ``proved``-path certificate.

Pono's ``-e ind`` engine proves AG ¬bad at some bound k but emits no
inductive invariant — the *(k, base-case, induction-step)* triple is the
certificate. This module re-discharges the two k-induction obligations
in plain z3 SMT (no Pono / no Spacer trusted), against the canonical
BTOR2 model bytes:

  C_base:  init(s_0) ∧ trans(s_0,s_1) ∧ ... ∧ trans(s_{k-1}, s_k)
           ∧ (bad(s_0) ∨ ... ∨ bad(s_k))
           must be UNSAT

  C_step:  ¬bad(s_0) ∧ trans(s_0,s_1) ∧ ¬bad(s_1) ∧ ...
           ∧ ¬bad(s_k) ∧ trans(s_k, s_{k+1}) ∧ bad(s_{k+1})
           must be UNSAT

(The step obligation quantifies over arbitrary state sequences — *not*
init-rooted. That's what makes k-induction different from BMC: BASE
covers the init-reachable prefix, STEP closes the inductive case.)

A pass on both obligations means: for any reachable trace of any
length, no bad state is reachable. This is the same unbounded-safety
claim Spacer's inductive invariant proves, just packaged differently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gurdy.core.btor2.parser import from_text
from gurdy.core.btor2._bmc import (
    Compiled,
    compile_btor2,
    evaluate_all,
    find_sort_for,
)


@dataclass(frozen=True)
class KindCertificateReport:
    accepted: bool
    k: int
    base_case_unsat: bool
    step_case_unsat: bool
    reason: str | None = None

    def summary(self) -> str:
        if self.accepted:
            return f"PASS: k-induction at k={self.k} verified"
        flags = []
        if not self.base_case_unsat:
            flags.append("BASE FAILED")
        if not self.step_case_unsat:
            flags.append("STEP FAILED")
        suffix = f" ({self.reason})" if self.reason else ""
        return f"FAIL at k={self.k}: " + ", ".join(flags) + suffix


def _make_state_var(name: str, sort_nid: int, comp: Compiled, z3mod: Any) -> Any:
    if sort_nid in comp.sort_widths:
        return z3mod.BitVec(name, comp.sort_widths[sort_nid])
    if sort_nid in comp.array_meta:
        idx_s, elt_s = comp.array_meta[sort_nid]
        return z3mod.Array(
            name,
            z3mod.BitVecSort(comp.sort_widths[idx_s]),
            z3mod.BitVecSort(comp.sort_widths[elt_s]),
        )
    raise ValueError(f"unknown sort nid {sort_nid}")


def _build_cycle_envs(comp: Compiled, k: int, prefix: str, z3mod: Any) -> list[dict[int, Any]]:
    """Build k+1 cycle environments wired by the transition relation.

    Each env has state vars (named ``{prefix}_c{cycle}_s{nid}``), input
    vars, and all op nodes evaluated. Consecutive cycles are linked by
    asserting ``state'[next_pair_state] == prev_env[next_pair_value]``
    (these come back as extra equalities returned alongside).
    """
    envs: list[dict[int, Any]] = []
    trans_eqs: list[Any] = []
    constraint_eqs: list[Any] = []

    from gurdy.pairs.riscv_btor2.solvers.btor2_to_z3 import Z3Backend
    backend = Z3Backend()

    for cycle in range(k + 1):
        env: dict[int, Any] = {}
        for nid in comp.state_nids:
            env[nid] = _make_state_var(
                f"{prefix}_c{cycle}_s{nid}", find_sort_for(nid, comp), comp, z3mod
            )
        for nid in comp.input_nids:
            env[nid] = _make_state_var(
                f"{prefix}_c{cycle}_in{nid}", find_sort_for(nid, comp), comp, z3mod
            )
        evaluate_all(env, comp, backend)
        envs.append(env)

        # Constraints at every cycle.
        for c in comp.constraint_nids:
            constraint_eqs.append(env[c] == z3mod.BitVecVal(1, 1))

        if cycle > 0:
            prev = envs[cycle - 1]
            for state_nid, value_nid in comp.next_pairs:
                trans_eqs.append(env[state_nid] == prev[value_nid])

    return envs, trans_eqs, constraint_eqs


def _bad_disj_at(env: dict[int, Any], comp: Compiled, z3mod: Any) -> Any:
    if not comp.bad_nids:
        return z3mod.BoolVal(False)
    terms = [env[b] == z3mod.BitVecVal(1, 1) for b in comp.bad_nids]
    return z3mod.Or(*terms) if len(terms) > 1 else terms[0]


def verify_kind_certificate(
    artifact_bytes: bytes,
    k: int,
    *,
    timeout_ms: int | None = None,
) -> KindCertificateReport:
    """Re-verify a k-induction proved certificate.

    Takes only the canonical BTOR2 bytes and the bound k. Re-builds both
    obligations in plain z3 SMT and confirms each is unsat.
    """
    try:
        import z3
    except ImportError:
        return KindCertificateReport(
            False, k, False, False, reason="z3-solver not installed"
        )

    if k < 0:
        return KindCertificateReport(False, k, False, False, reason="k must be >= 0")

    parsed = from_text(artifact_bytes.decode("utf-8", "replace"))
    comp = compile_btor2(parsed.model)
    if not comp.bad_nids:
        return KindCertificateReport(True, k, True, True)  # vacuously safe

    def _solve(formula: Any) -> str:
        solver = z3.Solver()
        if timeout_ms is not None:
            solver.set("timeout", int(timeout_ms))
        solver.add(formula)
        return repr(solver.check())

    # --- BASE: init at cycle 0, k transitions, bad somewhere in 0..k ---
    base_envs, base_trans, base_constraints = _build_cycle_envs(comp, k, "B", z3)
    base_clauses: list[Any] = list(base_trans) + list(base_constraints)
    # init constraints fix cycle-0 states to their init values.
    for state_nid, value_nid in comp.init_pairs:
        base_clauses.append(base_envs[0][state_nid] == base_envs[0][value_nid])
    base_bad_terms = [_bad_disj_at(env, comp, z3) for env in base_envs]
    base_bad = z3.Or(*base_bad_terms) if len(base_bad_terms) > 1 else base_bad_terms[0]
    base_formula = z3.And(*base_clauses, base_bad) if base_clauses else base_bad
    base_unsat = _solve(base_formula) == "unsat"

    # --- STEP: arbitrary s_0..s_{k+1}; 0..k non-bad; bad at k+1 ---
    step_envs, step_trans, step_constraints = _build_cycle_envs(comp, k + 1, "S", z3)
    step_clauses: list[Any] = list(step_trans) + list(step_constraints)
    # cycles 0..k must be non-bad (no init clause here — k-induction's step
    # quantifies over arbitrary state sequences, not init-rooted ones).
    for i in range(k + 1):
        step_clauses.append(z3.Not(_bad_disj_at(step_envs[i], comp, z3)))
    # cycle k+1 is bad.
    step_clauses.append(_bad_disj_at(step_envs[k + 1], comp, z3))
    step_formula = z3.And(*step_clauses)
    step_unsat = _solve(step_formula) == "unsat"

    accepted = base_unsat and step_unsat
    return KindCertificateReport(accepted, k, base_unsat, step_unsat)


__all__ = ["KindCertificateReport", "verify_kind_certificate"]
