"""Combine v0.1.2 / v0.2 / v0.3 transcripts into v0.3/ summaries.

v0.3 changes:

- Two new corpus tasks (0050-deep-mul-chain, 0051-large-bound-loop-
  bitwuzla) — both pinned to bitwuzla.
- prompts/condition_b.md gains an "Engine selection" section that
  names every engine + its verdict semantics + when to pick it.

Implications for combining:

- Condition A's prompt is unchanged in v0.3, so v0.1.2 + v0.2-delta
  transcripts on the 49 existing tasks remain valid; the v0.3 deltas
  add coverage of 0050 and 0051.
- Condition B's prompt is *different* in v0.3 (the engine-selection
  block is new). v0.2's B transcripts are therefore no longer
  representative of the v0.3 prompt's behaviour. The v0.3 B summary
  is built entirely from a fresh full-corpus B sweep against
  slot_CC_haiku at the v0.3 prompt — committed under
  ``runs/v0.3/_full_B/``.

Output:
  ``runs/v0.3/summaries/{A,B}.json`` — per-cell records, source-tagged
  so reviewers can audit which rows are inherited vs newly run.

Usage:
  python _v03_combine.py
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
V03_OUT = BENCH / "runs" / "v0.3"
V02_DELTA_A = V02_OUT / "_delta_A" / "transcripts"
V02_DELTA_B = V02_OUT / "_delta_B" / "transcripts"
V03_DELTA_A = V03_OUT / "_delta_A" / "transcripts"
V03_FULL_B  = V03_OUT / "_full_B"  / "transcripts"
V03_FULL_C  = V03_OUT / "_full_C"  / "transcripts"


# v0.3 deltas (tasks not present in v0.2).
V03_NEW_TASK_IDS = {
    "0050-deep-mul-chain",
    "0051-large-bound-loop-bitwuzla",
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
    graded = grade(task, observed, question_id=question_id)
    return {
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
        "source":           source_label,
        # Engines actually invoked under condition B (empty for A).
        "engines_invoked":  _extract_engines(transcript),
    }


def _extract_engines(transcript: dict) -> list[str]:
    """Walk the transcript's tool_call_log for `dispatch` (B) or
    `solve` (C) calls and return the list of engine strings in
    invocation order. Empty for condition A (no tools).

    The MCP server prefixes tool names with ``mcp__<server>__``, so
    `dispatch` arrives as `mcp__bench__dispatch` and `solve` as
    `mcp__bench__solve`. We match the suffix."""
    log = transcript.get("tool_call_log") or []
    out: list[str] = []
    for entry in log:
        name = entry.get("name") or ""
        suffix = name.split("__")[-1]
        if suffix not in ("dispatch", "solve"):
            continue
        inp = entry.get("input") or {}
        # B uses `dispatch(directive)` where directive carries engine.
        # C uses `solve(engine, ...)` with engine top-level.
        if suffix == "solve":
            engine = inp.get("engine")
        else:
            directive = inp.get("directive") or {}
            engine = directive.get("engine")
        if isinstance(engine, str):
            out.append(engine)
    return out


def _walk_transcripts(
    tx_root: Path, condition: str, model_slot: str = "slot_CC_haiku",
    seed: int = 0,
) -> list[tuple[str, str | None, Path]]:
    """Same shape as _v02_combine._walk_transcripts."""
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
        single = slot_dir / f"seed-{seed}.json"
        if single.is_file():
            out.append((task_dir.name, None, single))
            continue
        for q_dir in sorted(slot_dir.iterdir()):
            if not q_dir.is_dir():
                continue
            seed_file = q_dir / f"seed-{seed}.json"
            if seed_file.is_file():
                out.append((task_dir.name, q_dir.name, seed_file))
    return out


def build_summary(condition: str) -> list[dict]:
    """Build the v0.3 summary array for one condition.

    Condition A: combine v0.1.2 + v0.2-delta + v0.3-delta. A's prompt
    didn't change across versions, so prior transcripts remain valid.

    Condition B: use only v0.3 _full_B transcripts. v0.2's B prompt
    lacked the engine-selection block; its behaviour is no longer
    representative.
    """
    tasks = {t.id: t for t in discover_tasks()}
    rows: list[dict] = []

    if condition == "A":
        # v0.1.2's tree wraps a sweep label dir.
        for task_id, qid, path in _walk_transcripts(V012_TX / "A", "A"):
            if task_id not in tasks:
                continue
            tr = _read_transcript(path)
            if tr is None:
                continue
            rows.append(_row_for(tasks[task_id], tr,
                                 source_label="v0.1.2", question_id=qid))
        for task_id, qid, path in _walk_transcripts(V02_DELTA_A, "A"):
            if task_id not in tasks:
                continue
            tr = _read_transcript(path)
            if tr is None:
                continue
            rows.append(_row_for(tasks[task_id], tr,
                                 source_label="v0.2-delta", question_id=qid))
        for task_id, qid, path in _walk_transcripts(V03_DELTA_A, "A"):
            if task_id not in tasks:
                continue
            tr = _read_transcript(path)
            if tr is None:
                continue
            rows.append(_row_for(tasks[task_id], tr,
                                 source_label="v0.3-delta", question_id=qid))
    elif condition == "B":
        for task_id, qid, path in _walk_transcripts(V03_FULL_B, "B"):
            if task_id not in tasks:
                continue
            tr = _read_transcript(path)
            if tr is None:
                continue
            rows.append(_row_for(tasks[task_id], tr,
                                 source_label="v0.3", question_id=qid))
    elif condition == "C":
        for task_id, qid, path in _walk_transcripts(V03_FULL_C, "C"):
            if task_id not in tasks:
                continue
            tr = _read_transcript(path)
            if tr is None:
                continue
            rows.append(_row_for(tasks[task_id], tr,
                                 source_label="v0.3", question_id=qid))
    else:
        raise ValueError(f"unknown condition {condition!r}")

    rows.sort(key=lambda r: (r["task_id"], r["question_id"] or ""))
    return rows


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    n_correct = sum(1 for r in rows if r["verdict_correct"])
    n_unknown = sum(1 for r in rows if r["observed_verdict"] == "unknown")
    n_scored = n - n_unknown
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


def engine_choice_report(rows_b: list[dict]) -> dict:
    """v0.3-specific: for each B cell, report the corpus-pinned
    engine vs every engine the LLM actually dispatched. The
    Stream 6 measurement question is whether the LLM keeps the
    pin (especially the bitwuzla pin on 0050 / 0051) or switches."""
    tasks = {t.id: t for t in discover_tasks()}
    out: list[dict] = []
    for r in rows_b:
        t = tasks.get(r["task_id"])
        if t is None:
            continue
        # Task.spec / Question.spec are *dicts* (parsed spec.json), not
        # RiscvBtor2Spec instances. The pinned engine lives at
        # spec["fields"]["analysis"]["engine"].
        pinned = None
        if r["question_id"] is None:
            spec_dict = t.spec
        else:
            spec_dict = next(
                (q.spec for q in t.questions if q.id == r["question_id"]),
                None,
            )
        if isinstance(spec_dict, dict):
            pinned = (spec_dict.get("fields") or {}).get("analysis", {}).get("engine")
        invoked = r.get("engines_invoked") or []
        kept = bool(invoked) and all(e == pinned for e in invoked)
        out.append({
            "task":     r["task"],
            "pinned":   pinned,
            "invoked":  invoked,
            "kept_pin": kept,
        })
    n_with_calls = sum(1 for x in out if x["invoked"])
    n_kept = sum(1 for x in out if x["kept_pin"])
    return {
        "rows": out,
        "n_total": len(out),
        "n_with_dispatch": n_with_calls,
        "n_kept_pin": n_kept,
        "kept_pin_rate": (
            round(n_kept / n_with_calls, 4) if n_with_calls else None
        ),
    }


def solve_usage_report(rows_c: list[dict]) -> dict:
    """v0.3 Stream 5 measurement: under condition C the LLM may
    either hand-write SMT-LIB and call ``solve``, or reason
    directly. Per BENCHMARKING.md §3.C, only solve-mediated correct
    verdicts attribute the answer to "access to a solver"; direct-
    reasoning correct verdicts attribute it to "the LLM is just
    smart enough." This function reports the split."""
    n = len(rows_c)
    n_with_solve = 0
    n_solve_correct = 0
    n_direct_correct = 0
    by_engine: dict[str, int] = {}
    for r in rows_c:
        invoked = r.get("engines_invoked") or []
        if invoked:
            n_with_solve += 1
            for e in invoked:
                by_engine[e] = by_engine.get(e, 0) + 1
            if r["verdict_correct"]:
                n_solve_correct += 1
        else:
            if r["verdict_correct"]:
                n_direct_correct += 1
    return {
        "n_total":          n,
        "n_with_solve":     n_with_solve,
        "n_direct":         n - n_with_solve,
        "n_solve_correct":  n_solve_correct,
        "n_direct_correct": n_direct_correct,
        "solve_rate":       round(n_with_solve / n, 4) if n else None,
        "engines_invoked":  by_engine,
    }


def main() -> int:
    summaries_dir = V03_OUT / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)

    # Determine which conditions have transcripts on disk; skip
    # silently if the sweep hasn't run yet.
    conds_present = []
    for cond, root in (("A", V03_DELTA_A), ("B", V03_FULL_B), ("C", V03_FULL_C)):
        if cond == "A":  # A is always reachable via inheritance
            conds_present.append(cond)
        elif root.exists():
            conds_present.append(cond)

    out: dict[str, dict] = {}
    rows_by_cond: dict[str, list[dict]] = {}
    for cond in conds_present:
        rows = build_summary(cond)
        path = summaries_dir / f"{cond}.json"
        path.write_text(json.dumps(rows, indent=2) + "\n")
        agg = aggregate(rows)
        out[cond] = agg
        rows_by_cond[cond] = rows
        print(f"{cond}: {agg['n_correct']}/{agg['n_scored']} correct "
              f"(unknown={agg['n_unknown']}); "
              f"witness {agg['witness_ok']}/{agg['witness_req']}; "
              f"hallucination {agg['hallucination_count']} "
              f"-> {path}")

    if "A" in out and "B" in out:
        print()
        print(f"verdict accuracy: A={out['A']['accuracy']:.3f}  "
              f"B={out['B']['accuracy']:.3f}  "
              f"Δ={out['B']['accuracy']-out['A']['accuracy']:+.3f}")
        if out['A']['witness_match_rate'] and out['B']['witness_match_rate']:
            print(f"witness match:    A={out['A']['witness_match_rate']:.3f}  "
                  f"B={out['B']['witness_match_rate']:.3f}  "
                  f"Δ={out['B']['witness_match_rate']-out['A']['witness_match_rate']:+.3f}")
    if "C" in out:
        print(f"                  C={out['C']['accuracy']:.3f}")

    # Stream 6 engine-choice report (B only).
    if "B" in rows_by_cond:
        ec = engine_choice_report(rows_by_cond["B"])
        ec_path = summaries_dir / "engine_choice.json"
        ec_path.write_text(json.dumps(ec, indent=2) + "\n")
        print()
        print(
            f"engine-choice (B): {ec['n_kept_pin']}/{ec['n_with_dispatch']} cells kept the "
            f"pinned engine (rate={ec['kept_pin_rate']}). Detail: {ec_path}."
        )

    # Stream 5 solve-usage report (C only).
    if "C" in rows_by_cond:
        su = solve_usage_report(rows_by_cond["C"])
        su_path = summaries_dir / "solve_usage.json"
        su_path.write_text(json.dumps(su, indent=2) + "\n")
        print(
            f"solve-usage (C):   {su['n_with_solve']}/{su['n_total']} cells called "
            f"solve (rate={su['solve_rate']}). "
            f"Correct: {su['n_solve_correct']} via solve, "
            f"{su['n_direct_correct']} via direct reasoning. "
            f"Engines invoked: {su['engines_invoked']}. Detail: {su_path}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
