"""tools/autonomy.py — graduating the merge queue out of propose mode
(SCALING.md §12.6, §7, §9–§10). *Draft policy — defaults to propose (L0).*

Phase 6 emits merge plans for a human to approve; it never auto-merges. Autonomy
is not a single on/off switch — it is a **monotone ladder**, and each rung is
*earned by evidence*, not asserted. The governing principle is the platform's own
negative-control discipline turned on the merge decision itself: **a gate you let
merge unattended must first have demonstrably caught real defects.** A fan-out
that has never rejected anything, a negative control that has never fired, is
untrustworthy precisely because it is unproven — so autonomy for a risk class is
withheld until the check guarding that class is shown non-vacuous *and* has a
clean shadow track record.

The ladder (ESCALATE always → human; REJECT never merges, at every rung):

* **L0 — propose** *(default)*. Every decision is proposed. Nothing auto-merges.
* **L1 — auto-independent**. Auto-execute ``MERGE`` for *independent* pair PRs
  (pair-only, gate green): the lowest-risk class, ratchet-protected, no shared
  layer. Earned once the per-pair negative control has caught ≥ K seeded defects
  (non-vacuity) and a shadow period of independent MERGEs agreed with the human
  with **zero** disagreements.
* **L2 — auto-additive-shared**. Also auto-execute Lane-A (syntactically
  additive) shared MERGEs — safe by construction (no existing path changed).
  Earned once the additivity checker has classified ≥ N shared changes with zero
  shadow disagreements, on top of a clean L1 window.
* **L3 — auto-fan-out**. Also auto-execute Lane-B candidates whose re-validation
  fan-out *reconcile-accepts*. Earned once **the fan-out has caught ≥ R real
  regressions** — the §12.6 criterion, and the direct non-vacuity proof — with a
  clean reconcile shadow record.

**Safety rails**, applied at every rung (they only ever pull EXECUTE → PROPOSE):
a protected-instrument change is always human (§9); an external-differential pair
whose anchor round has not confirmed its anchor-required set stays proposed (§9);
a Lane-B candidate that has not reconcile-accepted stays proposed.

**Demotion / kill switch.** Any autonomous merge followed by ``main`` going red is
a revert; while the trailing window holds any revert, the attained level collapses
to **L0** until a human re-graduates. Autonomy is thus continuously re-earned, not
granted once.

The engine is pure (a ledger of accumulated evidence in, a level + per-decision
execution mode out) and defaults, with an empty ledger, to L0 — so wiring it in
changes nothing until the evidence exists and a human raises the level.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import dataclass

# Decision kinds shared with tools/merge_queue.py.
MERGE = "MERGE"
FAN_OUT = "FAN_OUT"
ESCALATE = "ESCALATE"
REJECT = "REJECT"

# Autonomy levels, low to high.
L0, L1, L2, L3 = "L0-propose", "L1-independent", "L2-additive-shared", "L3-fanout"
_ORDER = [L0, L1, L2, L3]

# Execution modes for a single decision under a level.
EXECUTE = "EXECUTE"
PROPOSE = "PROPOSE"

# Graduation thresholds (tunable). Deliberately conservative — this is a draft.
THRESHOLDS = {
    L1: {"negative_control_catches": 5, "independent_shadow": 20},
    L2: {"additive_shared_shadow": 15},
    L3: {"fanout_regressions_caught": 3, "fanout_shadow": 10},
}


@dataclass
class Ledger:
    """Accumulated, coordinator-maintained evidence. Empty ledger → L0."""
    # non-vacuity: the guarding checks have caught *real* defects
    negative_control_catches: int = 0
    fanout_regressions_caught: int = 0
    # shadow track record per class: (decisions seen, disagreements with human)
    independent_shadow_seen: int = 0
    independent_shadow_disagreements: int = 0
    additive_shared_shadow_seen: int = 0
    additive_shared_shadow_disagreements: int = 0
    fanout_shadow_seen: int = 0
    fanout_shadow_disagreements: int = 0
    # kill switch: autonomous merges that led to a post-merge red in the window
    reverts_in_window: int = 0


def _meets_L1(g: Ledger) -> bool:
    t = THRESHOLDS[L1]
    return (g.negative_control_catches >= t["negative_control_catches"]
            and g.independent_shadow_seen >= t["independent_shadow"]
            and g.independent_shadow_disagreements == 0)


def _meets_L2(g: Ledger) -> bool:
    t = THRESHOLDS[L2]
    return (_meets_L1(g)
            and g.additive_shared_shadow_seen >= t["additive_shared_shadow"]
            and g.additive_shared_shadow_disagreements == 0)


def _meets_L3(g: Ledger) -> bool:
    t = THRESHOLDS[L3]
    return (_meets_L2(g)
            and g.fanout_regressions_caught >= t["fanout_regressions_caught"]
            and g.fanout_shadow_seen >= t["fanout_shadow"]
            and g.fanout_shadow_disagreements == 0)


def attained_level(ledger: Ledger) -> str:
    """The highest rung the ledger's evidence earns. The kill switch collapses to
    L0 while the trailing window holds any revert."""
    if ledger.reverts_in_window > 0:
        return L0
    if _meets_L3(ledger):
        return L3
    if _meets_L2(ledger):
        return L2
    if _meets_L1(ledger):
        return L1
    return L0


def _ge(level: str, floor: str) -> bool:
    return _ORDER.index(level) >= _ORDER.index(floor)


def execution_for(flags: dict, level: str) -> tuple[str, str]:
    """Decide EXECUTE vs PROPOSE (or leave REJECT) for one decision at ``level``,
    applying the ladder and the safety rails. ``flags`` carries the decision kind
    and the risk-class booleans."""
    kind = flags["kind"]
    if kind == REJECT:
        return REJECT, "structural violation — never merges"
    if kind == ESCALATE:
        return PROPOSE, "escalated — human review (never auto)"
    if flags.get("touches_protected"):
        return PROPOSE, "protected instrument — human authorization (§9)"

    if kind == MERGE:
        if flags.get("independent"):
            return ((EXECUTE, f"independent pair MERGE, level ≥ {L1}")
                    if _ge(level, L1) else (PROPOSE, f"independent MERGE — propose until {L1}"))
        if flags.get("lane_a_shared"):
            if not flags.get("anchor_resolved", True):
                return PROPOSE, "external-differential pair: anchor round not confirmed (§9)"
            return ((EXECUTE, f"Lane-A additive shared MERGE, level ≥ {L2}")
                    if _ge(level, L2) else (PROPOSE, f"Lane-A shared — propose until {L2}"))
        return PROPOSE, "MERGE not in an auto-eligible class — propose"

    if kind == FAN_OUT:
        if not flags.get("fanout_accepts"):
            return PROPOSE, "Lane-B fan-out not reconcile-accepted — propose"
        if not flags.get("anchor_resolved", True):
            return PROPOSE, "external-differential pair: anchor round not confirmed (§9)"
        return ((EXECUTE, f"Lane-B fan-out reconcile-accepted, level ≥ {L3}")
                if _ge(level, L3) else (PROPOSE, f"Lane-B fan-out — propose until {L3}"))

    return PROPOSE, f"unknown decision {kind!r} — propose"


def _flags_for(decision: dict, cand, anchor_resolved: dict, fanout_accepts: dict) -> dict:
    kind = decision["decision"]
    shared = bool(cand.scope.get("touches_shared_layer"))
    lane = cand.verdict.get("shared_lane")
    pairs = cand.scope.get("touched_pairs", [])
    return {
        "kind": kind,
        "independent": kind == MERGE and not shared,
        "lane_a_shared": kind == MERGE and shared and lane == "A",
        "touches_protected": bool(cand.scope.get("touches_protected")),
        # a pair absent from anchor_resolved is assumed confirmed; the coordinator
        # passes {pair: False} for an unconfirmed external-differential pair.
        "anchor_resolved": all(anchor_resolved.get(p, True) for p in pairs),
        "fanout_accepts": bool(fanout_accepts.get(cand.ref)),
    }


def annotate(plan: dict, cands: list, ledger: Ledger,
             anchor_resolved: dict | None = None,
             fanout_accepts: dict | None = None) -> dict:
    """Annotate a merge plan (from tools/merge_queue.py) with the attained level
    and a per-decision execution mode. Mutates and returns ``plan``."""
    level = attained_level(ledger)
    by_ref = {c.ref: c for c in cands}
    anchor_resolved = anchor_resolved or {}
    fanout_accepts = fanout_accepts or {}
    for ref, d in plan["decisions"].items():
        flags = _flags_for(d, by_ref[ref], anchor_resolved, fanout_accepts)
        mode, reason = execution_for(flags, level)
        d["execution"] = mode
        d["execution_reason"] = reason
    plan["autonomy_level"] = level
    return plan


def ledger_from(data: dict) -> Ledger:
    fields = Ledger.__dataclass_fields__
    return Ledger(**{k: v for k, v in data.items() if k in fields})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ledger", help="JSON autonomy ledger")
    args = ap.parse_args()
    g = ledger_from(json.loads(pathlib.Path(args.ledger).read_text()))
    level = attained_level(g)
    print(json.dumps({"attained_level": level,
                      "next": _ORDER[min(_ORDER.index(level) + 1, len(_ORDER) - 1)],
                      "thresholds": THRESHOLDS}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
