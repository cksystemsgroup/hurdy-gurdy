"""Combine v0.4 paid sweep transcripts (A/B/C/D × 25 C tasks) into
runs/v0.4/summaries/.

Mirrors _v03_combine.py but for the v0.4 C subset. The §3.D
addition is the headline: how does the LLM-under-D fare against
both no-tools-A and pair-equipped-B on the lowering-sensitive
subset, where the no-LLM CBMC oracle (condition_d_reference.py)
already showed CBMC FAILs all 5 UB cases?

Output:
  - runs/v0.4/summaries/{A,B,C,D}.json — per-cell records
  - runs/v0.4/summaries/aggregate.json — per-condition rollups +
    the lowering-sensitive subset breakdown
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import discover_tasks, grade  # type: ignore


BENCH = Path(__file__).resolve().parent
V04_OUT = BENCH / "runs" / "v0.4"

# v0.4 lowering-sensitive C tasks (per CORPUS_V0.4_PLAN.md). Used
# for the lowering-subset rollup that's the headline of this sweep.
LOWERING_TASKS = {
    "0115-c-int-overflow",
    "0116-c-divu-sentinel",
    "0117-c-int-min-div-neg-one",
    "0118-c-shift-amount-mask",
    "0119-c-signed-vs-unsigned-shift-right",
    "0120-c-byte-load-signedness",
    "0121-c-mulw-truncation",
    "0122-c-signed-vs-unsigned-cmp",
    "0123-c-endianness-le",
    "0124-c-call-arg-promotion",
}

# v0.4 lowering-sensitive UB subset (the 5 tasks where CBMC's
# C-standard reasoning conflicts with the bench's RV64 lowering
# — the headline finding from condition_d_reference.py).
LOWERING_UB_TASKS = {
    "0115-c-int-overflow",
    "0116-c-divu-sentinel",
    "0117-c-int-min-div-neg-one",
    "0118-c-shift-amount-mask",
    "0121-c-mulw-truncation",
}


def _read_transcript(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _row_for(task, transcript: dict) -> dict:
    observed = transcript.get("observed") or {}
    g = grade(task, observed, question_id=None)
    return {
        "task":             task.id,
        "expected_verdict": g["expected_verdict"],
        "observed_verdict": g["observed_verdict"],
        "verdict_correct":  g["verdict_correct"],
        "witness_required": g["witness_required"],
        "witness_match":    g["witness_match"],
        "failures":         g["failures"],
        "confidence":       observed.get("confidence"),
        "lowering_sensitive": task.id in LOWERING_TASKS,
        "lowering_ub":        task.id in LOWERING_UB_TASKS,
    }


def _walk(condition: str) -> list[dict]:
    tasks = {t.id: t for t in discover_tasks()}
    tx_root = V04_OUT / f"_full_{condition}" / "transcripts"
    rows: list[dict] = []
    if not tx_root.exists():
        return rows
    for task_dir in sorted(tx_root.iterdir()):
        if not task_dir.is_dir():
            continue
        seed_file = task_dir / condition / "slot_CC_haiku" / "seed-0.json"
        if not seed_file.is_file():
            continue
        tr = _read_transcript(seed_file)
        if tr is None or task_dir.name not in tasks:
            continue
        rows.append(_row_for(tasks[task_dir.name], tr))
    rows.sort(key=lambda r: r["task"])
    return rows


def _aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    n_correct = sum(1 for r in rows if r["verdict_correct"])
    n_unknown = sum(1 for r in rows if r["observed_verdict"] == "unknown")
    n_scored = n - n_unknown
    n_hallu = sum(
        1 for r in rows
        if not r["verdict_correct"]
        and (r.get("confidence") or 0) >= 0.8
    )
    wit_req = [r for r in rows if r["witness_required"]]
    wit_ok = sum(1 for r in wit_req if r["witness_match"])
    return {
        "n":                  n,
        "n_correct":          n_correct,
        "n_unknown":          n_unknown,
        "n_scored":           n_scored,
        "accuracy":           round(n_correct / n_scored, 4) if n_scored else None,
        "hallucination":      n_hallu,
        "witness_ok":         wit_ok,
        "witness_required":   len(wit_req),
        "witness_match_rate": round(wit_ok / len(wit_req), 4) if wit_req else None,
    }


def _subset_aggregate(rows: list[dict], subset: set[str]) -> dict:
    return _aggregate([r for r in rows if r["task"] in subset])


def main() -> int:
    summaries_dir = V04_OUT / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)

    rows_by_cond: dict[str, list[dict]] = {}
    agg: dict[str, dict] = {"all": {}, "lowering": {}, "lowering_ub": {}}

    for cond in ("A", "B", "C", "D"):
        rows = _walk(cond)
        if not rows:
            continue
        (summaries_dir / f"{cond}.json").write_text(
            json.dumps(rows, indent=2) + "\n"
        )
        rows_by_cond[cond] = rows
        agg["all"][cond]         = _aggregate(rows)
        agg["lowering"][cond]    = _subset_aggregate(rows, LOWERING_TASKS)
        agg["lowering_ub"][cond] = _subset_aggregate(rows, LOWERING_UB_TASKS)

    (summaries_dir / "aggregate.json").write_text(
        json.dumps(agg, indent=2) + "\n"
    )

    # Print roll-up.
    for label, key in (("All 25", "all"),
                       ("Lowering-sensitive (10)", "lowering"),
                       ("Lowering-UB subset (5)",  "lowering_ub")):
        print(f"\n=== {label} ===")
        for cond, a in agg[key].items():
            acc_pct = (
                f"{a['accuracy']*100:.1f}%" if a.get('accuracy') is not None else "n/a"
            )
            wit_pct = (
                f"{a['witness_match_rate']*100:.1f}%"
                if a.get('witness_match_rate') is not None else "n/a"
            )
            print(
                f"  {cond}: {a['n_correct']:2d}/{a['n_scored']:2d} {acc_pct:>6s}  "
                f"hallu={a['hallucination']:1d}  "
                f"witness={a['witness_ok']}/{a['witness_required']} {wit_pct:>6s}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
