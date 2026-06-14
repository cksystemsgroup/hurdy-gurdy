#!/usr/bin/env python3
"""Post-hoc §9.7 rubric grading pass over the T4 addendum transcripts.

Decoupled from the matrix run: walks every saved transcript under a
slot's ``transcripts/`` tree, pulls ``observed`` + ``response_text``,
and calls ``rubric_llm.grade_lift`` (blind — the rubric module redacts
model/condition/slot tokens before the call). Writes one JSONL row per
(task, condition, seed) and prints a lift-score table.

Re-runnable: skips rows already present in the output JSONL (so a
rate-limit interruption resumes). Run from bench/riscv-btor2/:

    python3 runs/v0.6-two-family/t4_addendum/grade_lift_pass.py \
        --slot-dir runs/v0.6-two-family/t4_addendum/slot_CC_haiku
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BENCH_ROOT))
sys.path.insert(0, str(BENCH_ROOT / "rubric"))

import harness  # noqa: E402
import rubric_llm  # noqa: E402

CORPUS = BENCH_ROOT / "corpus"


def grade_slot(slot_dir: Path, throttle: float) -> Path:
    tdir = slot_dir / "transcripts"
    out_path = slot_dir / "lift_scores.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["task_id"], r["condition"], r["seed"]))

    files = sorted(tdir.glob("*/*/*/seed-*.json"))
    with out_path.open("a", encoding="utf-8") as out:
        for f in files:
            # .../transcripts/<task>/<cond>/<slot>/seed-N.json
            seed = int(f.stem.split("-")[1])
            cond = f.parts[-3]
            task_id = f.parts[-4]
            if (task_id, cond, seed) in done:
                continue
            t = json.loads(f.read_text())
            observed = t.get("observed") or {}
            transcript_text = t.get("response_text") or ""
            report = rubric_llm.grade_lift(
                CORPUS / task_id,
                observed,
                transcript_text,
                model_config=harness.MODELS["rubric"],
            )
            row = {
                "task_id": task_id,
                "condition": cond,
                "seed": seed,
                "lift_present": observed.get("lift") is not None,
                **report,
            }
            out.write(json.dumps(row) + "\n")
            out.flush()
            print(f"  {task_id} {cond} s{seed}: score={report.get('score')} "
                  f"({report.get('reason','')[:60]})")
            if throttle:
                time.sleep(throttle)
    return out_path


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--slot-dir", required=True, type=Path)
    p.add_argument("--throttle", type=float, default=3.0,
                   help="Seconds between rubric calls (GitHub Models rate limit).")
    a = p.parse_args(argv[1:])
    out = grade_slot(a.slot_dir, a.throttle)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
