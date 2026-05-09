"""Combine v0.1.2 transcripts (32 tasks) with v0.2 delta transcripts
(17 new tasks) into v0.2/ summaries.

Walks the two source transcript trees, regrades every cell with the
current matcher (so the v0.2 multi-question support is honoured), and
emits per-condition summary JSON arrays in
``runs/v0.2/summaries/<COND>.json``. The output schema mirrors
``runs/v0.1.2/summaries/A.json``.

Usage:
  python _v02_combine.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import discover_tasks, grade  # type: ignore

BENCH = Path(__file__).resolve().parent
V012_TX = BENCH / "runs" / "v0.1.2" / "transcripts"
V02_OUT = BENCH / "runs" / "v0.2"
DELTA_A = V02_OUT / "_delta_A" / "transcripts"
DELTA_B = V02_OUT / "_delta_B" / "transcripts"

NEW_TASK_IDS = {
    "0033-store-load-byte-roundtrip", "0034-sw-then-lh-truncation",
    "0035-misaligned-load-undef", "0036-stack-canary-replay",
    "0037-zero-init-bss",
    "0038-cleanup-must-run", "0039-take-true-branch",
    "0040-init-then-loop",
    "0041-find-input-makes-42", "0042-collision-easy",
    "0043-overflow-trigger", "0044-shift-zero-input",
    "0045-x5-bounded-counter-spacer", "0046-x0-stays-zero-spacer",
    "0047-monotonic-skip-spacer",
    "0048-monotonic-then-bounded", "0049-callee-preserves-x18",
}


def _read_transcript(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _row_for(
    task, transcript: dict, *, source_label: str, question_id: str | None
) -> dict:
    observed = transcript.get("observed") or {}
    # The matcher is the source of truth — re-grade every cell so the
    # v0.2 matcher (proved-as-PASS-for-unreachable, multi-question
    # support, etc.) applies uniformly.
    graded = grade(task, observed, question_id=question_id)
    row = {
        "task":     task.id if question_id is None else f"{task.id}#{question_id}",
        "task_id":  task.id,
        "question_id": question_id,
        "expected_verdict": graded["expected_verdict"],
        "observed_verdict": graded["observed_verdict"],
        "verdict_correct":  graded["verdict_correct"],
        "witness_required": graded["witness_required"],
        "witness_match":    graded["witness_match"],
        "failures":         graded["failures"],
        "lift_score":       graded.get("lift_score"),
        "confidence":       observed.get("confidence"),
        "tokens_out":       0,  # from transcript header if present
        "source":           source_label,
    }
    return row


def _walk_transcripts(
    tx_root: Path, condition: str, model_slot: str = "slot_CC_haiku",
    seed: int = 0,
) -> list[tuple[str, str | None, Path]]:
    """Return [(task_id, question_id, transcript_path)] for every
    transcript under ``tx_root/<task>/<condition>/<slot>/seed-<n>.json``
    (single-q) or ``.../<task>/<condition>/<slot>/<qid>/seed-<n>.json``
    (multi-q, post-B2).

    Returns empty if tx_root doesn't exist (the sweep hasn't been run).
    """
    if not tx_root.exists():
        return []
    out: list[tuple[str, str | None, Path]] = []
    for task_dir in sorted(tx_root.iterdir()):
        if not task_dir.is_dir():
            continue
        cond_dir = task_dir / condition
        if not cond_dir.is_dir():
            continue
        slot_dir = cond_dir / model_slot
        if not slot_dir.is_dir():
            continue
        # Single-question: seed-N.json directly here.
        single = slot_dir / f"seed-{seed}.json"
        if single.is_file():
            out.append((task_dir.name, None, single))
            continue
        # Multi-question: per-question subdirs.
        for q_dir in sorted(slot_dir.iterdir()):
            if not q_dir.is_dir():
                continue
            seed_file = q_dir / f"seed-{seed}.json"
            if seed_file.is_file():
                out.append((task_dir.name, q_dir.name, seed_file))
    return out


def build_summary(condition: str, *, b_label: str = "B") -> list[dict]:
    """Build the summary array for one condition.

    For condition B, the v0.1.2 transcripts live under ``B-v3/`` (the
    final intervention pass); the v0.2 deltas live under ``B/``. We
    treat both as the same condition for v0.2 purposes — v0.1.2's
    intervention ladder is now baked into the current prompts.
    """
    tasks = {t.id: t for t in discover_tasks()}
    rows: list[dict] = []

    # v0.1.2's transcript tree wraps a sweep-label dir around the
    # condition: ``transcripts/A/<task>/A/<slot>/...`` for A, and
    # ``transcripts/B-v3/<task>/B/<slot>/...`` for B-v3 (note the inner
    # condition for B-v3 is ``B``, not ``B-v3``). v0.2 deltas have a
    # flatter layout: ``_delta_A/transcripts/<task>/A/<slot>/...``.
    if condition == "A":
        v012_root = V012_TX / "A"
        v012_inner = "A"
        delta_root = DELTA_A
        delta_inner = "A"
    elif condition == "B":
        v012_root = V012_TX / "B-v3"
        v012_inner = "B"
        delta_root = DELTA_B
        delta_inner = "B"
    else:
        raise ValueError(f"unknown condition {condition!r}")

    for task_id, qid, path in _walk_transcripts(v012_root, v012_inner):
        if task_id not in tasks:
            continue
        tr = _read_transcript(path)
        if tr is None:
            continue
        rows.append(_row_for(tasks[task_id], tr,
                             source_label="v0.1.2", question_id=qid))
    for task_id, qid, path in _walk_transcripts(delta_root, delta_inner):
        if task_id not in tasks:
            continue
        tr = _read_transcript(path)
        if tr is None:
            continue
        rows.append(_row_for(tasks[task_id], tr,
                             source_label="v0.2-delta", question_id=qid))

    # Sort: by task id then question id (q1 < q2 < ...).
    def _sort_key(r: dict) -> tuple:
        return (r["task_id"], r["question_id"] or "")
    rows.sort(key=_sort_key)
    return rows


def aggregate(rows: list[dict]) -> dict:
    """Compute the headline metrics for one condition."""
    n = len(rows)
    n_correct = sum(1 for r in rows if r["verdict_correct"])
    n_unknown = sum(1 for r in rows if r["observed_verdict"] == "unknown")
    n_scored = n - n_unknown  # exclude unknown from accuracy
    accuracy = n_correct / n_scored if n_scored else 0.0
    n_hallucination = sum(
        1 for r in rows
        if not r["verdict_correct"]
        and (r.get("confidence") or 0) >= 0.8
    )
    witness_req_rows = [r for r in rows if r["witness_required"]]
    witness_ok = sum(1 for r in witness_req_rows if r["witness_match"])
    return {
        "n_total":     n,
        "n_correct":   n_correct,
        "n_unknown":   n_unknown,
        "n_scored":    n_scored,
        "accuracy":    round(accuracy, 4),
        "hallucination_count": n_hallucination,
        "hallucination_rate":  round(n_hallucination / n, 4) if n else 0,
        "witness_ok":  witness_ok,
        "witness_req": len(witness_req_rows),
        "witness_match_rate": (
            round(witness_ok / len(witness_req_rows), 4)
            if witness_req_rows else None
        ),
    }


def main() -> int:
    summaries_dir = V02_OUT / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)

    out: dict[str, dict] = {}
    for cond in ("A", "B"):
        rows = build_summary(cond)
        path = summaries_dir / f"{cond}.json"
        path.write_text(json.dumps(rows, indent=2) + "\n")
        agg = aggregate(rows)
        out[cond] = agg
        print(f"{cond}: {agg['n_correct']}/{agg['n_scored']} correct "
              f"(unknown={agg['n_unknown']}); "
              f"witness {agg['witness_ok']}/{agg['witness_req']}; "
              f"hallucination {agg['hallucination_count']} "
              f"-> {path}")

    # Headline diff
    if "A" in out and "B" in out:
        print()
        print(f"verdict accuracy: A={out['A']['accuracy']:.3f}  "
              f"B={out['B']['accuracy']:.3f}  "
              f"Δ={out['B']['accuracy']-out['A']['accuracy']:+.3f}")
        if out['A']['witness_match_rate'] and out['B']['witness_match_rate']:
            print(f"witness match:    A={out['A']['witness_match_rate']:.3f}  "
                  f"B={out['B']['witness_match_rate']:.3f}  "
                  f"Δ={out['B']['witness_match_rate']-out['A']['witness_match_rate']:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
