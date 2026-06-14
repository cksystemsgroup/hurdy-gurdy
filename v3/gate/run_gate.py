"""Run the pair fidelity battery for one hop and decide merge.

Real in this skeleton: F0, the reasoning-trust *structure* check, the
projection-pin check, and the merge decision. F1-F3, the independence audit
execution, and the Sail differential are stubs (return NOT_IMPLEMENTED /
None), so a stubbed pair lands at F0 and is merge-blocked for any target > F0
— which is correct: nothing has been proven yet.
"""

from __future__ import annotations

from pathlib import Path

from gate import fidelity
from gate.machine.verify_machine import gate_machine
from gate.merge_policy import MergeDecision, decide
from gate.trust.diff_agreement import check as trust_check
from gurdy.core.manifest import Manifest, load
from gurdy.core.report import Fidelity, FidelityReport

REGISTRY = Path(__file__).resolve().parents[1] / "registry"


def run(manifest: Manifest, branch: str = "(working-tree)") -> tuple[FidelityReport, MergeDecision]:
    report = FidelityReport(hop_id=manifest.id, branch=branch)

    # the battery, up to the manifest target
    battery = [fidelity.f0, fidelity.f1, fidelity.f2, fidelity.f3]
    for level, fn in zip(Fidelity, battery):
        if level > manifest.fidelity_target:
            break
        report.checks.append(fn(manifest))

    # projection-pin check (skeleton: the loaded manifest *is* the registered
    # one, so this is trivially ok; a real gate diffs branch vs registry HEAD).
    registered = load(REGISTRY / f"{manifest.id}.yaml")
    report.projection_pinned_ok = (
        registered.projection == manifest.projection
        and registered.fidelity_target == manifest.fidelity_target
    )

    # reasoning-side differential trust applies only to hops that produce a
    # reasoning language (reasoning/bridge). A compile hop's trust is
    # reproducibility + a verifier differential, handled by its fidelity battery.
    if manifest.kind in ("reasoning", "bridge"):
        report.reasoning_trust_ok = trust_check(manifest).ok
    else:
        report.reasoning_trust_ok = None  # not applicable

    # independence audit (skeleton): unknown until the real audit runs.
    report.independence_audit_ok = None

    # machine realization status, if this pair relies on one
    machine_green: bool | None = None
    if manifest.machine_tool:
        group = manifest.machine_tool.realization.split("@", 1)[0]
        machine_green = gate_machine(group).green

    decision = decide(report, manifest, machine_realization_green=machine_green)
    return report, decision


def run_by_id(hop_id: str) -> tuple[FidelityReport, MergeDecision]:
    return run(load(REGISTRY / f"{hop_id}.yaml"))
