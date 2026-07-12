"""tools/merge_queue.py — the coordinator merge queue (SCALING.md §6–§7, Phase 6).

The coordinator is **mechanism, not judgment**: it executes the ratchet and the
fan-out, it does not decide whether code is "good". This module is its brain —
given a set of candidate PRs (each carrying its Phase-1 manifest and, for a
non-additive shared change, a shared-change manifest), it produces an *ordered
merge plan*:

* **Ordering (the dependency DAG, §7).** ``framework → interpreters → pairs``
  (FRAMEWORK.md's bootstrap order as a live queue): shared-touching PRs are
  **serialized** — each its own wave, framework (``gurdy/core``) before
  interpreters (``gurdy/languages``) — while independent pair PRs stay **parallel
  and cheap**, packed into waves so no two in a wave touch the same pair
  (the advisory per-symbol/per-pair lock, §6).

* **Per-candidate decision.** From the manifest verdict + the additivity lane
  (§6): ``MERGE`` (independent, or Lane-A additive shared change — auto-
  integrable), ``FAN_OUT`` (Lane-B shared change — needs the re-validation
  fan-out), ``ESCALATE`` (a *protected* instrument changed, §9 — human
  authorization), or ``REJECT`` (fast gate red, or Lane B with no shared-change
  manifest).

* **The re-validation fan-out (§6, Lane B).** For a Lane-B change the plan names
  the **dependent pairs** (everything consuming the touched interpreter; every
  pair for a ``gurdy/core`` change) and the manifest's **expected verdict per
  pair**. After the coordinator re-gates them on one integration branch,
  :func:`reconcile` compares observed vs. expected: a green→red the manifest did
  not predict is a regression → reject; a change matching the manifest → accept.

**Propose mode (Phase 6).** This tool never merges. It emits the plan for a human
to approve; autonomy is graduated in only once the fan-out has caught real
regressions (SCALING.md §12.6). The plan is machine-readable so a later
autonomous coordinator consumes the same artifact.

The engine (:func:`build_plan`, :func:`classify_candidate`, :func:`order_waves`,
:func:`reconcile`) is pure and consumes plain dicts, so it is unit-tested without
git. The CLI is a thin driver that reads candidate bundles (the ``.hg/pr.yaml``
manifests CI already uploads, serialized to JSON) and the registry.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Decision kinds.
MERGE = "MERGE"        # eligible to integrate (proposed; auto only once graduated)
FAN_OUT = "FAN_OUT"    # Lane B — run the re-validation fan-out, then reconcile
ESCALATE = "ESCALATE"  # needs human authorization (protected instrument)
REJECT = "REJECT"      # structural violation — gate red, or Lane B w/o manifest


@dataclass
class Candidate:
    ref: str
    scope: dict
    verdict: dict
    shared_change: dict | None = None      # the Lane-B declaration (symbol/reason/expect)
    provenance: dict | None = None         # author/builder (Phase 7 hardens this)

    @classmethod
    def from_manifest(cls, ref: str, manifest: dict, shared_change: dict | None = None,
                      provenance: dict | None = None) -> "Candidate":
        return cls(ref=ref, scope=manifest["scope"], verdict=manifest["verdict"],
                   shared_change=shared_change, provenance=provenance)

    @property
    def touches_shared(self) -> bool:
        return bool(self.scope.get("touches_shared_layer"))

    @property
    def pairs(self) -> set[str]:
        return set(self.scope.get("touched_pairs", []))


# --- per-candidate decision --------------------------------------------------

def classify_candidate(c: Candidate) -> tuple[str, str]:
    """Decide a candidate in isolation (ordering/locks are separate). Returns
    ``(kind, reason)``."""
    v, s = c.verdict, c.scope
    if (v.get("measurement_errors") or v.get("determinism_failures")
            or v.get("negative_control_failures")):
        return (REJECT, "fast gate red — a pair failed to measure, is "
                        "non-deterministic, or fails its negative control")
    if s.get("touches_protected"):
        return (ESCALATE, "a protected instrument (inventory/probes, §9) changed "
                          "— requires human authorization, never auto-integrated")
    if not c.touches_shared:
        return (MERGE, "independent pair change; fast gate green")
    lane = v.get("shared_lane")
    if lane == "A":
        return (MERGE, "shared change is Lane A (syntactically additive) — "
                       "auto-integrable, re-stamp + version bump")
    if lane == "B":
        if not c.shared_change:
            return (REJECT, "Lane B (non-additive) shared change without a "
                            "shared-change manifest (§6.1) — cannot fan out")
        return (FAN_OUT, "Lane B (non-additive) shared change — re-validation "
                         "fan-out over dependent pairs required before merge")
    return (ESCALATE, f"shared change with unresolved lane {lane!r}")


# --- ordering (the dependency DAG) -------------------------------------------

def _rank(scope: dict) -> int:
    """0 = touches framework (gurdy/core, gurdy/solvers), 1 = touches an
    interpreter (gurdy/languages), 2 = pair-only. Lower merges first."""
    files = scope.get("changed_files", [])
    if any(f.startswith(("gurdy/core/", "gurdy/solvers/")) for f in files):
        return 0
    if any(f.startswith("gurdy/languages/") for f in files):
        return 1
    return 2


def order_waves(cands: list[Candidate]) -> list[list[str]]:
    """Group candidates into ordered waves. Shared-touching PRs are serialized
    (one per wave, framework before interpreters); independent pair PRs are
    packed into parallel waves such that no two in a wave touch the same pair."""
    shared = sorted((c for c in cands if c.touches_shared),
                    key=lambda c: (_rank(c.scope), c.ref))
    indep = sorted((c for c in cands if not c.touches_shared), key=lambda c: c.ref)

    waves: list[list[str]] = [[c.ref] for c in shared]   # serialized, in DAG order

    remaining = indep
    while remaining:
        wave: list[str] = []
        used: set[str] = set()
        deferred: list[Candidate] = []
        for c in remaining:
            if c.pairs & used:                 # per-pair lock: conflict -> next wave
                deferred.append(c)
            else:
                wave.append(c.ref)
                used |= c.pairs or {c.ref}     # a pair-less change still locks its ref
        waves.append(wave)
        remaining = deferred
    return waves


# --- the Lane-B fan-out ------------------------------------------------------

def dependents_of(scope: dict, pairs: dict[str, dict]) -> list[str]:
    """Pairs affected by a shared change. A ``gurdy/core`` change touches the
    framework → every pair is a dependent; a ``gurdy/languages/<L>`` change
    touches interpreter ``L`` → every pair whose source or target is ``L``.
    ``pairs`` maps ``pair_id -> {"source": .., "target": ..}``."""
    files = scope.get("changed_files", [])
    if any(f.startswith(("gurdy/core/", "gurdy/solvers/")) for f in files):
        return sorted(pairs)
    langs = set(scope.get("touched_languages", []))
    if not langs:
        for f in files:                        # fall back to path parsing
            parts = f.split("/")
            if len(parts) >= 3 and parts[0] == "gurdy" and parts[1] == "languages":
                langs.add(parts[2])
    dep = [pid for pid, meta in pairs.items()
           if meta.get("source") in langs or meta.get("target") in langs]
    return sorted(dep)


def reconcile(base: dict[str, dict], expected: dict[str, dict],
              observed: dict[str, dict], dependents: list[str]) -> dict:
    """Compare the fan-out's observed per-pair verdicts against what the
    shared-change manifest predicted. A dependent's target verdict is its
    manifest-declared ``expected`` entry, defaulting to *unchanged from base*.
    Any deviation — an undeclared change, or a dependent that did not re-measure
    — is a regression → reject. All match → accept."""
    mismatches: list[dict] = []
    for pid in dependents:
        target = expected.get(pid, base.get(pid))
        obs = observed.get(pid)
        if obs is None:
            mismatches.append({"pair": pid, "reason": "not measured in the fan-out"})
        elif obs != target:
            mismatches.append({"pair": pid, "reason": "unpredicted verdict change",
                               "expected": target, "observed": obs})
    return {"accept": not mismatches, "mismatches": mismatches}


# --- the plan ----------------------------------------------------------------

def _load_provenance():
    import importlib.util
    spec = importlib.util.spec_from_file_location("provenance", ROOT / "tools" / "provenance.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _apply_provenance(kind: str, reason: str, c: Candidate, ledger) -> tuple[str, str]:
    """Fold a candidate's author-diversity provenance (§9) into its decision: a
    provenance REJECT is terminal; an ESCALATE (e.g. an unregistered — possibly
    builder-authored — external artifact) pulls a would-be MERGE/FAN_OUT to human
    review. Skipped when no ledger or no provenance record is supplied."""
    if ledger is None or not c.provenance:
        return kind, reason
    prov = _load_provenance()
    pv, preasons = prov.check(c.provenance, ledger)
    if pv == prov.REJECT:
        return REJECT, "provenance: " + "; ".join(preasons)
    if pv == prov.ESCALATE and kind in (MERGE, FAN_OUT):
        return ESCALATE, "provenance: " + "; ".join(preasons)
    return kind, reason


def build_plan(cands: list[Candidate], pairs: dict[str, dict], ledger=None) -> dict:
    """The full merge plan: per-candidate decision (folding in author-diversity
    provenance when a ledger is supplied, §9), wave ordering, and — for each
    Lane-B candidate — the fan-out spec (dependent pairs + expected verdicts)."""
    decisions = {}
    fanouts = {}
    for c in cands:
        kind, reason = classify_candidate(c)
        kind, reason = _apply_provenance(kind, reason, c, ledger)
        decisions[c.ref] = {"decision": kind, "reason": reason,
                            "rank": _rank(c.scope)}
        if kind == FAN_OUT:
            expected = (c.shared_change or {}).get("expect", {})
            fanouts[c.ref] = {
                "symbol": (c.shared_change or {}).get("symbol"),
                "dependents": dependents_of(c.scope, pairs),
                "expected": expected,
            }
    return {
        "schema": "hg-merge-plan/v1",
        "mode": "propose",                     # Phase 6 never auto-merges
        "waves": order_waves(cands),
        "decisions": decisions,
        "fanouts": fanouts,
    }


# --- rendering + CLI ---------------------------------------------------------

_ICON = {MERGE: "✓ merge", FAN_OUT: "⟳ fan-out", ESCALATE: "! escalate",
         REJECT: "✗ reject"}


def render(plan: dict) -> str:
    header = f"merge plan ({plan['mode']} mode — coordinator proposes, human approves)"
    if "autonomy_level" in plan:
        header += f"  [autonomy: {plan['autonomy_level']}]"
    lines = [header]
    for i, wave in enumerate(plan["waves"], 1):
        if not wave:
            continue
        # A shared-touching wave (rank 0/1) is serialized by constraint; the
        # independent tier (rank 2) is parallel by nature, whatever its size.
        ranks = {plan["decisions"][r]["rank"] for r in wave}
        kind = "serialized" if ranks <= {0, 1} else "parallel"
        lines.append(f"  wave {i} ({kind}):")
        for ref in wave:
            d = plan["decisions"][ref]
            exec_tag = f" -> {d['execution']}" if "execution" in d else ""
            lines.append(f"    [{_ICON.get(d['decision'], d['decision'])}] {ref}{exec_tag}")
            lines.append(f"        {d['reason']}")
            if d.get("execution_reason"):
                lines.append(f"        execution: {d['execution_reason']}")
            fo = plan["fanouts"].get(ref)
            if fo:
                deps = ", ".join(fo["dependents"]) or "(none)"
                lines.append(f"        fan-out over: {deps}")
                if fo["expected"]:
                    lines.append(f"        expected changes: {fo['expected']}")
    return "\n".join(lines)


def _registry_pairs() -> dict[str, dict]:
    """Load ``pair_id -> {source, target}`` from the live registry."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("pr_manifest", ROOT / "tools" / "pr_manifest.py")
    pm = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = pm
    spec.loader.exec_module(pm)
    pm._import_all_pairs()
    from gurdy.core import registry
    return {pid: {"source": p.source, "target": p.target}
            for pid, p in registry.list_pairs().items()}


def _load_bundle(path: str) -> Candidate:
    """A candidate bundle is JSON: ``{ref, manifest, shared_change?, provenance?}``.
    ``manifest`` is a Phase-1 PR manifest (its ``scope`` + ``verdict`` are used)."""
    data = json.loads(pathlib.Path(path).read_text())
    return Candidate.from_manifest(
        data["ref"], data["manifest"],
        shared_change=data.get("shared_change"),
        provenance=data.get("provenance"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan", help="build a merge plan from candidate bundles")
    p_plan.add_argument("bundles", nargs="+", help="candidate bundle JSON files")
    p_plan.add_argument("--json", action="store_true", help="machine-readable output")
    p_plan.add_argument("--ledger", default=None,
                        help="JSON attestation ledger — enables author-diversity "
                             "provenance checks (§9)")
    p_plan.add_argument("--autonomy-ledger", default=None,
                        help="JSON autonomy ledger — annotates each decision with "
                             "an execution mode (EXECUTE/PROPOSE) at the earned "
                             "level (§12.6). Absent → propose-only.")
    p_rec = sub.add_parser("reconcile", help="reconcile a fan-out's observed verdicts")
    p_rec.add_argument("result", help="JSON: {base, expected, observed, dependents}")
    args = ap.parse_args()

    if args.cmd == "plan":
        cands = [_load_bundle(b) for b in args.bundles]
        ledger = None
        if args.ledger:
            prov = _load_provenance()
            data = json.loads(pathlib.Path(args.ledger).read_text())
            ledger = prov.Ledger(
                interpreter_contributions=data.get("interpreter_contributions", {}),
                external_artifacts=set(data.get("external_artifacts", [])))
        plan = build_plan(cands, _registry_pairs(), ledger=ledger)
        if args.autonomy_ledger:
            import importlib.util
            spec = importlib.util.spec_from_file_location("autonomy", ROOT / "tools" / "autonomy.py")
            au = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = au
            spec.loader.exec_module(au)
            g = au.ledger_from(json.loads(pathlib.Path(args.autonomy_ledger).read_text()))
            au.annotate(plan, cands, g)
        print(json.dumps(plan, indent=2) if args.json else render(plan))
        return 0
    if args.cmd == "reconcile":
        r = json.loads(pathlib.Path(args.result).read_text())
        res = reconcile(r.get("base", {}), r.get("expected", {}),
                        r.get("observed", {}), r["dependents"])
        print(json.dumps(res, indent=2))
        return 0 if res["accept"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
