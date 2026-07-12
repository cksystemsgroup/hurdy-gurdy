"""tools/shadow_ledger.py — shadow-mode ledger accumulation (SCALING.md §12.8).

While the merge queue runs in propose mode (L0), every resolved PR is a free
*shadow trial* of autonomy: the coordinator records what it *would* have
auto-executed (per tools/autonomy.py) beside what the human actually did, plus
the per-run non-vacuity signals (did the negative control fire? did a Lane-B
fan-out reject a real regression?) and the post-merge outcome. Folding those
records builds the very ledger :func:`autonomy.attained_level` reads — so the
evidence for L1/L2/L3 accrues *automatically at L0*, and graduating becomes a
human flip once the bar is already cleared, not a leap of faith.

A **shadow entry** (one per resolved candidate; the coordinator emits it at merge
time, when it knows everything):

    {
      "ref": "builder/foo",
      "class": "independent" | "lane_a_shared" | "fanout" | null,  # null: escalate/reject
      "shadow_execution": "EXECUTE" | "PROPOSE",   # what autonomy would do at that class's level
      "human_action": "merged" | "rejected" | "changes_requested",
      "outcome": "clean" | "reverted" | null,      # post-merge; null if not yet known
      "negative_control_fired": bool,              # the per-pair control caught its seeded defect
      "fanout": "accept" | "reject-regression" | null,
    }

Only entries where autonomy *would have gone* (``shadow_execution == EXECUTE``)
count toward a class's shadow total — a run the safety rails held back is not a
trial of the thing being trusted. A trial where the human did **not** merge is a
disagreement (a would-be false-go), which is exactly what must be zero to
graduate. :func:`entry_from_plan` builds an entry from a live merge-queue plan;
:func:`accumulate` folds a stream into a ledger; :func:`progress` reports the gap
to each rung.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _autonomy():
    import importlib.util
    spec = importlib.util.spec_from_file_location("autonomy", ROOT / "tools" / "autonomy.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# The level at which each risk class first auto-executes (so a shadow trial is
# evaluated at the level that would actually let it go).
def _eligible_level(au) -> dict:
    return {"independent": au.L1, "lane_a_shared": au.L2, "fanout": au.L3}


def _classify(decision: dict, cand) -> str | None:
    kind = decision["decision"]
    shared = bool(cand.scope.get("touches_shared_layer"))
    lane = cand.verdict.get("shared_lane")
    if kind == "MERGE" and not shared:
        return "independent"
    if kind == "MERGE" and shared and lane == "A":
        return "lane_a_shared"
    if kind == "FAN_OUT":
        return "fanout"
    return None                      # ESCALATE / REJECT — not a shadow trial


def entry_from_plan(plan: dict, ref: str, cand, *, human_action: str,
                    outcome: str | None = None, negative_control_fired: bool = False,
                    fanout: str | None = None, anchor_resolved: dict | None = None,
                    fanout_accepts: dict | None = None, au=None) -> dict:
    """Build a shadow entry from a live merge-queue plan decision. Computes the
    class and, via autonomy, what it *would* have executed at that class's level."""
    au = au or _autonomy()
    decision = plan["decisions"][ref]
    cls = _classify(decision, cand)
    if cls is None:
        shadow = au.PROPOSE
    else:
        flags = au.flags_for(decision, cand, anchor_resolved or {}, fanout_accepts or {})
        shadow, _ = au.execution_for(flags, _eligible_level(au)[cls])
    return {"ref": ref, "class": cls, "shadow_execution": shadow,
            "human_action": human_action, "outcome": outcome,
            "negative_control_fired": bool(negative_control_fired), "fanout": fanout}


_CLASS_FIELDS = {
    "independent": ("independent_shadow_seen", "independent_shadow_disagreements"),
    "lane_a_shared": ("additive_shared_shadow_seen", "additive_shared_shadow_disagreements"),
    "fanout": ("fanout_shadow_seen", "fanout_shadow_disagreements"),
}


def fold(ledger, entry: dict, au=None):
    """Fold one shadow entry into a ledger, returning a new ledger."""
    au = au or _autonomy()
    g = dataclasses.replace(ledger)
    if entry.get("negative_control_fired"):
        g.negative_control_catches += 1
    if entry.get("fanout") == "reject-regression":
        g.fanout_regressions_caught += 1
    if entry.get("outcome") == "reverted":
        g.reverts_in_window += 1
    cls = entry.get("class")
    if cls in _CLASS_FIELDS and entry.get("shadow_execution") == au.EXECUTE:
        seen_f, dis_f = _CLASS_FIELDS[cls]
        setattr(g, seen_f, getattr(g, seen_f) + 1)
        if entry.get("human_action") != "merged":
            setattr(g, dis_f, getattr(g, dis_f) + 1)
    return g


def accumulate(entries: list[dict], base=None, au=None):
    """Fold a stream of shadow entries into a ledger (starting from ``base`` or an
    empty ledger)."""
    au = au or _autonomy()
    g = base if base is not None else au.Ledger()
    for e in entries:
        g = fold(g, e, au)
    return g


def to_dict(ledger) -> dict:
    return dataclasses.asdict(ledger)


def progress(ledger, au=None) -> dict:
    """The gap to each rung: per requirement, have/need/met, plus the level the
    ledger currently earns."""
    au = au or _autonomy()
    g = ledger
    t = au.THRESHOLDS

    def req(have, need, ok=None):
        met = (have >= need) if ok is None else ok
        return {"have": have, "need": need, "met": met}

    rungs = {
        au.L1: {
            "negative_control_catches": req(g.negative_control_catches,
                                            t[au.L1]["negative_control_catches"]),
            "independent_shadow": req(g.independent_shadow_seen,
                                      t[au.L1]["independent_shadow"]),
            "zero_disagreements": req(g.independent_shadow_disagreements, 0,
                                      ok=g.independent_shadow_disagreements == 0),
        },
        au.L2: {
            "additive_shared_shadow": req(g.additive_shared_shadow_seen,
                                          t[au.L2]["additive_shared_shadow"]),
            "zero_disagreements": req(g.additive_shared_shadow_disagreements, 0,
                                      ok=g.additive_shared_shadow_disagreements == 0),
        },
        au.L3: {
            "fanout_regressions_caught": req(g.fanout_regressions_caught,
                                             t[au.L3]["fanout_regressions_caught"]),
            "fanout_shadow": req(g.fanout_shadow_seen, t[au.L3]["fanout_shadow"]),
            "zero_disagreements": req(g.fanout_shadow_disagreements, 0,
                                      ok=g.fanout_shadow_disagreements == 0),
        },
    }
    return {"attained_level": au.attained_level(g),
            "reverts_in_window": g.reverts_in_window, "rungs": rungs}


def _render_progress(p: dict) -> str:
    lines = [f"attained level: {p['attained_level']}"
             + (f"  (kill switch: {p['reverts_in_window']} revert(s) in window → L0)"
                if p["reverts_in_window"] else "")]
    for level, reqs in p["rungs"].items():
        lines.append(f"  {level}:")
        for name, r in reqs.items():
            mark = "✓" if r["met"] else "✗"
            lines.append(f"    [{mark}] {name}: {r['have']}/{r['need']}")
    return "\n".join(lines)


def main() -> int:
    au = _autonomy()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    acc = sub.add_parser("accumulate", help="fold a JSONL of shadow entries into a ledger")
    acc.add_argument("entries", help="JSONL file, one shadow entry per line")
    acc.add_argument("--base", default=None, help="existing ledger JSON to extend")
    acc.add_argument("--out", default=None, help="write the new ledger JSON here")
    prog = sub.add_parser("progress", help="gap-to-graduation for a ledger")
    prog.add_argument("ledger", help="ledger JSON")
    args = ap.parse_args()

    if args.cmd == "accumulate":
        entries = [json.loads(ln) for ln in
                   pathlib.Path(args.entries).read_text().splitlines() if ln.strip()]
        base = (au.ledger_from(json.loads(pathlib.Path(args.base).read_text()))
                if args.base else None)
        g = accumulate(entries, base, au)
        out = to_dict(g)
        if args.out:
            pathlib.Path(args.out).write_text(json.dumps(out, indent=2))
        print(json.dumps(out, indent=2))
        print(_render_progress(progress(g, au)), file=sys.stderr)
        return 0
    if args.cmd == "progress":
        g = au.ledger_from(json.loads(pathlib.Path(args.ledger).read_text()))
        print(_render_progress(progress(g, au)))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
