"""The auto-merge predicate. Pure function over a FidelityReport + manifest.

Merge iff ALL hold:
  1. fidelity level >= manifest target;
  2. projection + fidelity target byte-identical to the registered manifest
     (the agent cannot weaken pi or the bar);
  3. independence audit clean — and, when the agent is sandboxed from the
     oracle, the audit must have actually RUN and passed (a clean=True result),
     not merely "not failed". An unrun audit (None) is treated as not-yet-clean
     for these hops, because there is no evidence the agent stayed independent;
  4. reasoning-side differential trust passed;
  5. any referenced machine_tool realization is itself gated GREEN.
"""

from __future__ import annotations

from dataclasses import dataclass

from gurdy.core.manifest import Manifest
from gurdy.core.report import FidelityReport

# oracle-access modes in which the agent is sandboxed from the oracle, so an
# independence audit is mandatory before merge (an unaudited build could have
# cribbed from the held-out / forbidden oracle).
_SANDBOXED_ACCESS = ("differential_only", "held_out_behavioral")


@dataclass
class MergeDecision:
    allow: bool
    reasons: list[str]


def independence_required(manifest: Manifest) -> bool:
    """True iff this hop's contract sandboxes the agent from the oracle (or
    forbids the machine path during construction), so a clean independence
    audit is a precondition for merge."""
    if manifest.oracle_access in _SANDBOXED_ACCESS:
        return True
    if manifest.machine_tool and manifest.machine_tool.construction == "forbidden":
        return True
    return False


def decide(report: FidelityReport, manifest: Manifest, *, machine_realization_green: bool | None = None) -> MergeDecision:
    reasons: list[str] = []

    if not report.meets(manifest.fidelity_target):
        reasons.append(
            f"fidelity {report.level.label} < target {manifest.fidelity_target.label}"
        )
    if report.projection_pinned_ok is False:
        reasons.append("projection/fidelity drifted from the registered manifest")

    # independence audit: a failed audit always blocks; for sandboxed hops, an
    # unrun audit (None) blocks too — absence of evidence is not independence.
    if report.independence_audit_ok is False:
        reasons.append("independence audit failed")
    elif report.independence_audit_ok is not True and independence_required(manifest):
        reasons.append(
            f"independence audit not run (required for oracle_access="
            f"{manifest.oracle_access!r}; agent sandboxed from the oracle)"
        )

    if report.reasoning_trust_ok is False:
        reasons.append("reasoning-side differential trust failed")
    if manifest.machine_tool and machine_realization_green is False:
        reasons.append(
            f"machine_tool {manifest.machine_tool.realization} not gated GREEN"
        )

    return MergeDecision(allow=not reasons, reasons=reasons or ["all gates green"])
