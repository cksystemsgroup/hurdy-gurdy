"""The auto-merge predicate. Pure function over a FidelityReport + manifest.

Merge iff ALL hold:
  1. fidelity level >= manifest target;
  2. projection + fidelity target byte-identical to the registered manifest
     (the agent cannot weaken pi or the bar);
  3. independence audit clean (no Sail crib, query log within bounds);
  4. reasoning-side differential trust passed;
  5. any referenced machine_tool realization is itself gated GREEN.
"""

from __future__ import annotations

from dataclasses import dataclass

from gurdy.core.manifest import Manifest
from gurdy.core.report import FidelityReport


@dataclass
class MergeDecision:
    allow: bool
    reasons: list[str]


def decide(report: FidelityReport, manifest: Manifest, *, machine_realization_green: bool | None = None) -> MergeDecision:
    reasons: list[str] = []

    if not report.meets(manifest.fidelity_target):
        reasons.append(
            f"fidelity {report.level.label} < target {manifest.fidelity_target.label}"
        )
    if report.projection_pinned_ok is False:
        reasons.append("projection/fidelity drifted from the registered manifest")
    if report.independence_audit_ok is False:
        reasons.append("independence audit failed")
    if report.reasoning_trust_ok is False:
        reasons.append("reasoning-side differential trust failed")
    if manifest.machine_tool and machine_realization_green is False:
        reasons.append(
            f"machine_tool {manifest.machine_tool.realization} not gated GREEN"
        )

    return MergeDecision(allow=not reasons, reasons=reasons or ["all gates green"])
