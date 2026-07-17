#!/usr/bin/env python3
"""tools/closure_calibration.py — the recommender's own shadow ledger
(FRONTIER-PLAN.md §1.5/O4).

Every design recommendation is a **prediction**: "this target closes
demand set D" — D being exactly the citing questions the frontier
object carries. A recommender whose predictions are never checked is
the kind of unaudited oracle the platform exists to refuse, so:

* **predict** — at promotion time, record the prediction: the target's
  signature and the citing questions verbatim, as a
  ``closure-prediction`` record *in the one ledger* (the plan sketched
  a separate calibration store; pruned — one ledger, no parallel
  currencies).
* **realize** — after the target lands (built, gated, merged), re-ask
  the predicted questions statically and record the
  ``closure-realization``: which are now answerable. Realized short of
  predicted is a finding about the recommender, on the books like any
  other measurement.
* **summary** — per prediction: predicted, realized, precision. What
  the number is *for*: a recommender whose predicted closures
  systematically overshoot loses the benefit of the doubt exactly
  where a gate that never fired does.

Nothing here registers, builds, or writes outside the configured
ledger.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def predict(obj: dict[str, Any]) -> None:
    """Record one closure prediction for a board entry (a
    frontier-object dict). No-op unless a ledger is configured."""
    from gurdy.core import ledger

    ledger.record("closure-prediction", obj["id"],
                  signature=obj["signature"],
                  predicted=list(obj.get("citing", ())))


def realize(oid: str, path: str, *, max_hops: int = 6) -> dict[str, Any]:
    """Re-ask a prediction's questions statically and record what is
    now answerable. Honest by construction: a question still blocked
    counts against precision, and asking it re-books its demand."""
    from gurdy.core import ledger
    from gurdy.core.question import question_key
    from gurdy.core.whynot import why_not

    preds = [r for r in ledger._records(path)
             if r.get("kind") == "closure-prediction"
             and r.get("key") == oid]
    if not preds:
        raise ValueError(f"no closure-prediction for {oid!r}")
    predicted = preds[-1]["predicted"]
    realized = []
    for q in predicted:
        rec = why_not(q["source"], q.get("observables"), q.get("shape"),
                      floor=q.get("floor"), program=q.get("program"),
                      origin="scout", max_hops=max_hops)
        if rec["answerable"]:
            realized.append(question_key(q))
    ledger.record("closure-realization", oid,
                  predicted_n=len(predicted), realized_n=len(realized),
                  realized=realized)
    return {"id": oid, "predicted": len(predicted),
            "realized": len(realized),
            "precision": (round(len(realized) / len(predicted), 4)
                          if predicted else None)}


def summary(path: str) -> list[dict[str, Any]]:
    """Per prediction: the latest realization beside it. A prediction
    with no realization yet reads ``unrealized`` — pending, never
    assumed correct."""
    records = [r for r in _records_of(path)]
    preds = {r["key"]: r for r in records
             if r.get("kind") == "closure-prediction"}
    reals = {r["key"]: r for r in records
             if r.get("kind") == "closure-realization"}
    out = []
    for oid, p in sorted(preds.items()):
        r = reals.get(oid)
        out.append({
            "id": oid,
            "predicted": len(p.get("predicted", ())),
            "realized": r["realized_n"] if r else None,
            "precision": (round(r["realized_n"] / len(p["predicted"]), 4)
                          if r and p.get("predicted") else None),
            "status": "realized" if r else "unrealized",
        })
    return out


def _records_of(path: str) -> list[dict[str, Any]]:
    from gurdy.core import ledger

    return ledger._records(path)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="closure calibration over the books: predict at "
                    "promotion, realize after merge, summarize")
    ap.add_argument("command", choices=["predict", "realize", "summary"])
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--id", help="board entry id (predict/realize)")
    args = ap.parse_args()

    import gurdy.cli  # noqa: F401
    from gurdy.core import ledger as _ledger, registry
    from gurdy.core.frontier import derive

    _ledger.configure(args.ledger)
    try:
        if args.command == "predict":
            records = [r for r in _ledger._records(args.ledger)
                       if r.get("kind") == "demand"]
            board = derive(records, registry.list_pairs())
            matches = [o for o in board if o.id.startswith(args.id or "")]
            if len(matches) != 1:
                print(f"need exactly one match for {args.id!r}, "
                      f"got {len(matches)}")
                return 1
            predict(matches[0].asdict())
            print(f"predicted: {matches[0].id} closes "
                  f"{len(matches[0].citing)} question(s)")
        elif args.command == "realize":
            out = realize(args.id, args.ledger)
            print(out)
        else:
            for row in summary(args.ledger):
                print(row)
    finally:
        _ledger.configure(None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
