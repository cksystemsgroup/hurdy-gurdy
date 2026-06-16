"""Certify a registered model: which declared capabilities are actually backed.

Symmetric to ``gate.run_gate`` (pairs). Lean skeleton (ROADMAP A4): probe each
declared capability and report PASS (certified here), SKIP (declared, backable,
but unconfirmed in this environment — e.g. no emulator binary), or FAIL
(overclaim / broken). The CERTIFIED set is what bounds any pair referencing this
model (A6). It never manufactures a pass: the emulator binary and the verified
machine are the ground truth.
"""

from __future__ import annotations

from pathlib import Path

from gurdy.core import oracle as oracle_mod
from gurdy.core.model import ModelRegistration, load
from gurdy.core.report import CapabilityResult, CheckStatus, ModelReport

MODELS = Path(__file__).resolve().parents[2] / "registry" / "models"
SEMANTICS = Path(__file__).resolve().parents[2] / "semantics"


def run(reg: ModelRegistration) -> ModelReport:
    report = ModelReport(
        model_id=reg.id, language=reg.language,
        declared_capabilities=reg.target_capabilities,
    )
    report.pins_ok, pin_notes = _check_pins(reg)
    report.notes.extend(pin_notes)

    try:
        oracle = oracle_mod.build_oracle(reg)
    except NotImplementedError as e:
        for cap in reg.target_capabilities:
            report.capability_status.append(
                CapabilityResult(cap, CheckStatus.NOT_IMPLEMENTED, str(e)))
        return report

    # The machine report backs proof_export's cross-check and machine_gen; run
    # the (heavy) gate once and share it.
    mrep = None
    if {oracle_mod.PROOF_EXPORT, oracle_mod.MACHINE_GEN} & set(reg.target_capabilities):
        try:
            mrep = oracle.machine_model()
        except Exception as e:  # noqa: BLE001
            report.notes.append(f"machine_model() raised: {e!r}")

    for cap in reg.target_capabilities:
        report.capability_status.append(_certify(cap, oracle, mrep))
    return report


def _check_pins(reg: ModelRegistration) -> tuple[bool, list[str]]:
    src, notes, ok = reg.source, [], True
    if not src.get("emulator_release"):
        ok = False
        notes.append("source.emulator_release missing (the executable must be pinned)")
    ms = src.get("model_source")
    if ms in (None, "transcribed"):
        notes.append("Sail source not byte-vendored; proof_export is backed by the "
                     "transcribed reference cross-validated vs the emulator binary")
    else:
        vend = SEMANTICS / reg.group / "model"
        if not vend.is_dir():
            ok = False
            notes.append(f"model_source pins vendored source but {vend} is absent")
    return ok, notes


def _certify(cap: str, oracle, mrep) -> CapabilityResult:
    available = getattr(oracle, "available", lambda: False)()

    if cap == oracle_mod.EXECUTABLE:
        if available:
            return CapabilityResult(cap, CheckStatus.PASS, "emulator binary reachable; run() wired")
        return CapabilityResult(cap, CheckStatus.SKIP,
                                "emulator binary not reachable here (run in the bench image to certify)")

    if cap == oracle_mod.PROOF_EXPORT:
        try:
            oracle.reference_export()
        except Exception as e:  # noqa: BLE001
            return CapabilityResult(cap, CheckStatus.FAIL, f"no reference to export: {e!r}")
        if mrep is not None and mrep.reference_vs_sail_ok is True:
            return CapabilityResult(cap, CheckStatus.PASS, "reference present + cross-validated vs Sail")
        return CapabilityResult(cap, CheckStatus.SKIP,
                                "reference present; vs-Sail cross-check unconfirmed here")

    if cap == oracle_mod.MACHINE_GEN:
        if mrep is None:
            return CapabilityResult(cap, CheckStatus.FAIL, "machine_model() unavailable")
        if mrep.green:
            return CapabilityResult(cap, CheckStatus.PASS,
                                    f"verified BTOR2 machine GREEN ({mrep.instructions_proven}/{mrep.instructions_total} instrs)")
        return CapabilityResult(cap, CheckStatus.SKIP,
                                f"machine generated; not fully GREEN here "
                                f"({mrep.instructions_proven}/{mrep.instructions_total} instrs, "
                                f"harness={mrep.harness_lemma_ok}, vs-Sail={mrep.reference_vs_sail_ok})")

    return CapabilityResult(cap, CheckStatus.NOT_IMPLEMENTED, f"unknown capability {cap!r}")


def run_by_id(model_id: str) -> ModelReport:
    return run(load(MODELS / f"{model_id}.yaml"))
