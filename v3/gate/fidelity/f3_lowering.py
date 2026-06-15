"""F3 — Lowering. Per-instruction machine-checked QF_BV lemma vs Sail =>
programs faithful by composition (the paste lemma).

For a reasoning hop whose source group ships a verified btor2-machine, F3 is
discharged by REUSING the machine model's per-instruction lemmas rather than
re-proving them — but only for the *machine* path; the *own* path's independent
lowering must be proven on its own to retain validator status.

This check therefore:
  * runs the source group's machine gate (``gate_machine``), which discharges
    the per-instruction QF_BV execute lemmas with z3 and cross-validates the
    reference against the real Sail emulator (so "vs Sail" is literal);
  * PASSes when every per-instruction lowering lemma holds and the reference is
    not in conflict with Sail — i.e. the machine-path lowering is proven;
  * reports the *own*-path lowering status (validator standing) without
    overclaiming: a stubbed own path is honestly flagged.

It does NOT manufacture a pass: a single failed lemma, or a reference that
diverges from Sail, is a FAIL with the counterexample.
"""

from __future__ import annotations

from gurdy.core.manifest import Manifest
from gurdy.core.report import CheckResult, CheckStatus, Fidelity


def check(manifest: Manifest) -> CheckResult:
    if manifest.kind not in ("reasoning", "bridge") or not manifest.source_group:
        return CheckResult(Fidelity.F3_lowering, CheckStatus.SKIP,
                           "F3 lowering not applicable to this hop")
    if manifest.machine_tool is None:
        # No verified machine model to reuse; the own-path lowering would have
        # to be proven independently, which is not available in this skeleton.
        return CheckResult(Fidelity.F3_lowering, CheckStatus.NOT_IMPLEMENTED,
                           "no machine_tool to reuse; own-path lowering proof [TODO]")

    from gate.machine.verify_machine import gate_machine

    report = gate_machine(manifest.source_group)
    if report.instructions_total == 0:
        return CheckResult(Fidelity.F3_lowering, CheckStatus.SKIP,
                           f"no btor2-machine realization for group {manifest.source_group!r}")

    # the per-instruction lowering lemmas (the substance of F3)
    proven, total = report.instructions_proven, report.instructions_total
    per_instr_divs = [d for d in report.divergences if not d.startswith(("harness:",))]
    if proven < total or per_instr_divs:
        shown = "; ".join(per_instr_divs[:3]) or f"{proven}/{total} proven"
        return CheckResult(Fidelity.F3_lowering, CheckStatus.FAIL,
                           f"per-instruction lowering lemma(s) failed: {shown}")

    # "vs Sail" qualifier — the reference these lemmas target is cross-validated
    # against the real emulator (Step 4a). False = genuine conflict => FAIL.
    if report.reference_vs_sail_ok is False:
        return CheckResult(Fidelity.F3_lowering, CheckStatus.FAIL,
                           "reference diverges from Sail (reference_vs_sail_ok=False)")
    sail_note = ("vs Sail v0.12" if report.reference_vs_sail_ok is True
                 else "vs the spec-derived reference (Sail cross-check unavailable here)")

    own = _own_path_status(manifest)
    return CheckResult(
        Fidelity.F3_lowering, CheckStatus.PASS,
        f"{total}/{total} per-instruction lowering lemmas {sail_note}, discharged via "
        f"the verified machine model (machine path); own-path lowering: {own}",
    )


def _own_path_status(manifest: Manifest) -> str:
    """Report whether the hop's *own* (independent, Sail-validating) lowering is
    implemented. A stubbed own path is honest about validator standing: the
    machine path is trusted, but the pair does not yet independently validate
    Sail."""
    import importlib

    from gurdy.hops.base import NotYetImplemented

    try:
        hop = importlib.import_module(f"gurdy.hops.{manifest.id}").HOP
        if "own" not in hop.paths():
            return "n/a (no own path declared)"
        try:
            hop.translate(None, {}, path="own")
        except NotYetImplemented:
            return "not yet implemented (validator status pending; independent proof TODO)"
        except Exception:
            pass
        return "implemented (independent lowering proof is a separate F3 obligation)"
    except Exception as e:  # noqa: BLE001
        return f"unknown ({e!r})"
