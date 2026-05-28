"""Independent re-checker for a Spacer ``proved``-path certificate.

The certificate consists of:

  - the BTOR2 model bytes that were sent to Spacer (already a public
    artifact via ``CompiledArtifact.flattened``),
  - the inductive invariant Spacer discovered, serialized as SMT-LIB
    over named state variables ``s_<nid>``,
  - the ordered list of state nids used by that naming scheme.

The checker re-parses the BTOR2 model with ``compile_btor2``, parses
the SMT-LIB invariant via z3's smt2 parser, and discharges the three
Horn-rule obligations with a *plain SMT solver* (not Spacer / not
fixedpoint). Each obligation is encoded as the negation of an
implication and must be ``unsat``:

  C1 (base):       init(s) ∧ ¬Inv(s)
  C2 (induction):  Inv(s) ∧ trans(s, s') ∧ ¬Inv(s')
  C3 (safety):     Inv(s) ∧ bad(s)

If all three are unsat, Inv is a real inductive invariant for the
property; the certificate is accepted.

Methodologically this is the small-trusted-checker pattern from
Froleyks et al. (HWMCC 2024+ certificates): the prover ships a
witness, and a tiny external checker re-verifies — at no point is
Spacer's IC3 frame structure trusted. The BTOR2 → SMT compiler used
here (``Z3Backend``) is shared with the BMC adapters, which gives the
checker independence from Spacer's encoding *driver* even though it
shares the term-construction code.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gurdy.pairs.riscv_btor2.btor2.parser import from_text
from gurdy.pairs.riscv_btor2.solvers._bmc import (
    Compiled,
    compile_btor2,
    evaluate_all,
    find_sort_for,
)


_DEFAULT_IMAGE = os.environ.get(
    "HURDY_PONO_DOCKER_IMAGE", "christophkirsch/hurdy-gurdy-bench:latest"
)

# CLI checkers we know how to invoke. Each maps to the binary name and
# the argv tail to run on the SMT-LIB file.
_CLI_CHECKERS = {
    "bitwuzla": lambda path: ["bitwuzla", path],
    "cvc5": lambda path: ["cvc5", "--lang", "smt2", path],
}


@dataclass(frozen=True)
class CertificateReport:
    accepted: bool
    base_case_unsat: bool
    inductive_step_unsat: bool
    safety_unsat: bool
    checker: str = "z3"
    reason: str | None = None

    def summary(self) -> str:
        if self.accepted:
            return f"PASS: invariant is inductive and safe (checker={self.checker})"
        flags = []
        if not self.base_case_unsat:
            flags.append("init⇒Inv FAILED")
        if not self.inductive_step_unsat:
            flags.append("Inv∧trans⇒Inv' FAILED")
        if not self.safety_unsat:
            flags.append("Inv⇒¬bad FAILED")
        suffix = f" ({self.reason})" if self.reason else ""
        return f"FAIL [checker={self.checker}]: " + ", ".join(flags) + suffix


def _run_cli_check_sat(
    formula_z3: Any,
    *,
    checker: str,
    image: str,
    timeout_s: float,
) -> str:
    """Run an SMT-LIB ``(check-sat)`` query through a CLI checker in
    the bench Docker image and return ``'sat'`` / ``'unsat'`` / ``'unknown'``.

    The formula is rendered to SMT-LIB via z3's ``Solver.to_smt2``, then
    handed to ``bitwuzla`` or ``cvc5`` — neither shares the
    ``Z3Backend.apply_op`` BTOR2-to-term compiler that built the formula,
    but both consume standard SMT-LIB so the round-trip is portable.
    """
    import z3

    if checker not in _CLI_CHECKERS:
        return "unknown"

    z3solver = z3.Solver()
    z3solver.add(formula_z3)
    smt = z3solver.to_smt2()
    if "(check-sat)" not in smt:
        smt = smt.rstrip() + "\n(check-sat)\n"

    with tempfile.TemporaryDirectory(prefix="cert-cli-") as td:
        tdpath = Path(td)
        (tdpath / "q.smt2").write_text(smt)
        argv = [
            "docker", "run", "--rm",
            "-v", f"{tdpath}:/work",
            image,
        ] + _CLI_CHECKERS[checker]("/work/q.smt2")
        try:
            proc = subprocess.run(
                argv, capture_output=True, timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return "unknown"

    out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    if re.search(r"^unsat\b", out, re.MULTILINE):
        return "unsat"
    if re.search(r"^sat\b", out, re.MULTILINE):
        return "sat"
    return "unknown"


def _make_named_state_vars(comp: Compiled, suffix: str, z3mod: Any) -> dict[int, Any]:
    out: dict[int, Any] = {}
    for nid in comp.state_nids:
        sort_nid = find_sort_for(nid, comp)
        if sort_nid in comp.sort_widths:
            out[nid] = z3mod.BitVec(f"s_{nid}{suffix}", comp.sort_widths[sort_nid])
        elif sort_nid in comp.array_meta:
            idx_s, elt_s = comp.array_meta[sort_nid]
            out[nid] = z3mod.Array(
                f"s_{nid}{suffix}",
                z3mod.BitVecSort(comp.sort_widths[idx_s]),
                z3mod.BitVecSort(comp.sort_widths[elt_s]),
            )
        else:
            raise ValueError(f"unknown sort nid {sort_nid}")
    return out


def _make_input_vars(comp: Compiled, tag: str, z3mod: Any) -> dict[int, Any]:
    out: dict[int, Any] = {}
    for nid in comp.input_nids:
        sort_nid = find_sort_for(nid, comp)
        if sort_nid in comp.sort_widths:
            out[nid] = z3mod.BitVec(f"in_{tag}_{nid}", comp.sort_widths[sort_nid])
        elif sort_nid in comp.array_meta:
            idx_s, elt_s = comp.array_meta[sort_nid]
            out[nid] = z3mod.Array(
                f"in_{tag}_{nid}",
                z3mod.BitVecSort(comp.sort_widths[idx_s]),
                z3mod.BitVecSort(comp.sort_widths[elt_s]),
            )
    return out


def _parse_invariant(invariant_smtlib: str, state_vars: dict[int, Any], z3mod: Any) -> Any:
    asserts = z3mod.parse_smt2_string(invariant_smtlib)
    if len(asserts) != 1:
        raise ValueError(
            f"expected exactly one assertion in invariant smtlib, got {len(asserts)}"
        )
    parsed = asserts[0]
    # The parser built fresh constants for each (declare-const s_<nid> ...).
    # Walk the assertion's free vars and rebind them to our state_vars by name
    # — this is what makes the invariant unify with the model we just rebuilt.
    name_to_state = {f"s_{nid}": var for nid, var in state_vars.items()}
    parsed_consts = _collect_consts(parsed, z3mod)
    pairs = []
    for c in parsed_consts:
        nm = c.decl().name()
        if nm in name_to_state:
            pairs.append((c, name_to_state[nm]))
    if not pairs:
        return parsed
    return z3mod.substitute(parsed, *pairs)


def _collect_consts(expr: Any, z3mod: Any) -> list[Any]:
    seen: dict[str, Any] = {}
    stack = [expr]
    while stack:
        node = stack.pop()
        if z3mod.is_const(node) and node.decl().kind() == z3mod.Z3_OP_UNINTERPRETED:
            seen[node.decl().name()] = node
            continue
        for i in range(node.num_args()):
            stack.append(node.arg(i))
    return list(seen.values())


def _substitute(expr: Any, src_vars: dict[int, Any], dst_vars: dict[int, Any], z3mod: Any) -> Any:
    pairs = [(src_vars[nid], dst_vars[nid]) for nid in src_vars]
    return z3mod.substitute(expr, *pairs)


def verify_certificate(
    artifact_bytes: bytes,
    invariant_smtlib: str,
    state_nid_order: list[int],
    *,
    timeout_ms: int | None = None,
    checker: str = "z3",
    image: str = _DEFAULT_IMAGE,
    cli_timeout_s: float = 60.0,
) -> CertificateReport:
    """Re-verify a ``proved`` certificate against the BTOR2 model.

    Takes only the published artifact bytes and the certificate fields
    a prover emitted (Spacer or Pono ic3sa/ic3ia). Returns a structured
    report.

    ``checker`` selects the SMT backend used to discharge the three
    Horn obligations:

      - ``'z3'`` (default): in-process via the ``z3-solver`` Python
        wheel. Fast (~ms per obligation) but the formula is built
        with ``Z3Backend.apply_op`` — the same BTOR2→z3 term compiler
        Spacer used — so the trust gap on shared compilation bugs
        isn't closed.
      - ``'bitwuzla'`` / ``'cvc5'``: dump each obligation as SMT-LIB
        via ``z3.Solver.to_smt2`` and run the named binary in the
        bench Docker image. The formula construction still goes
        through ``Z3Backend``, but the *check* is performed by a
        completely separate solver that re-parses the SMT-LIB from
        scratch — a meaningful independent verification.
    """
    try:
        import z3
    except ImportError:
        return CertificateReport(
            False, False, False, False, checker=checker,
            reason="z3-solver not installed",
        )

    from gurdy.pairs.riscv_btor2.solvers.btor2_to_z3 import Z3Backend

    parsed = from_text(artifact_bytes.decode("utf-8", "replace"))
    comp = compile_btor2(parsed.model)

    if list(comp.state_nids) != list(state_nid_order):
        return CertificateReport(
            False, False, False, False, checker=checker,
            reason=(
                "state_nid_order mismatch: certificate names "
                f"{state_nid_order!r}, model has {comp.state_nids!r}"
            ),
        )

    backend = Z3Backend()

    s_vars = _make_named_state_vars(comp, "", z3)
    sp_vars = _make_named_state_vars(comp, "_p", z3)
    inv_s = _parse_invariant(invariant_smtlib, s_vars, z3)
    inv_sp = _substitute(inv_s, s_vars, sp_vars, z3)

    def _solve(formula: Any) -> str:
        if checker == "z3":
            solver = z3.Solver()
            if timeout_ms is not None:
                solver.set("timeout", int(timeout_ms))
            solver.add(formula)
            return repr(solver.check())
        return _run_cli_check_sat(
            formula, checker=checker, image=image, timeout_s=cli_timeout_s,
        )

    # C1: init(s) ∧ ¬Inv(s)
    init_env = dict(s_vars)
    init_env.update(_make_input_vars(comp, "init", z3))
    evaluate_all(init_env, comp, backend)
    init_clauses = [s_vars[s] == init_env[v] for s, v in comp.init_pairs]
    init_clauses += [init_env[c] == z3.BitVecVal(1, 1) for c in comp.constraint_nids]
    base_formula = z3.And(*init_clauses, z3.Not(inv_s)) if init_clauses else z3.Not(inv_s)
    base_result = _solve(base_formula)
    base_unsat = base_result == "unsat"

    # C2: Inv(s) ∧ trans(s, s') ∧ ¬Inv(s')
    trans_env = dict(s_vars)
    trans_env.update(_make_input_vars(comp, "trans", z3))
    evaluate_all(trans_env, comp, backend)
    trans_clauses = [sp_vars[s] == trans_env[v] for s, v in comp.next_pairs]
    trans_clauses += [trans_env[c] == z3.BitVecVal(1, 1) for c in comp.constraint_nids]
    induct_formula = z3.And(inv_s, *trans_clauses, z3.Not(inv_sp))
    induct_result = _solve(induct_formula)
    induct_unsat = induct_result == "unsat"

    # C3: Inv(s) ∧ bad(s)
    bad_env = dict(s_vars)
    bad_env.update(_make_input_vars(comp, "bad", z3))
    evaluate_all(bad_env, comp, backend)
    if not comp.bad_nids:
        # No bad clause: safety holds vacuously.
        safety_unsat = True
    else:
        bad_terms = [bad_env[b] == z3.BitVecVal(1, 1) for b in comp.bad_nids]
        bad_disj = z3.Or(*bad_terms) if len(bad_terms) > 1 else bad_terms[0]
        safety_formula = z3.And(inv_s, bad_disj)
        safety_result = _solve(safety_formula)
        safety_unsat = safety_result == "unsat"

    accepted = base_unsat and induct_unsat and safety_unsat
    return CertificateReport(
        accepted=accepted,
        base_case_unsat=base_unsat,
        inductive_step_unsat=induct_unsat,
        safety_unsat=safety_unsat,
        checker=checker,
    )


__all__ = ["CertificateReport", "verify_certificate"]
