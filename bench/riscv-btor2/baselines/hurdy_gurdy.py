"""Hurdy-gurdy self-row for the SOTA Pareto comparison.

Thin shim over ``framework_oracle.run_one`` that emits one
schema-conformant JSON line per (task, question) for consumption by
``pareto.py``. The hurdy-gurdy verdict is the **lifted** verdict
(post-``Lifter``), not the raw solver verdict, because the lifted
form is what hurdy-gurdy "reports" to the LLM (lift maps raw solver
outcomes through pair semantics — see SCHEMA.md §10/§11).

Verdict mapping (lifted → schema):

- ``reachable`` / ``unreachable`` / ``proved`` — pass through.
- ``unknown`` — pass through.
- anything starting with ``lift-error:`` — schema ``error`` with
  the suffix in notes.
- anything else — schema ``error`` with the unrecognized verdict
  in notes.

``--engine`` overrides every question's ``analysis.engine`` (e.g.
``bitwuzla``), emitting rows under the tool name
``hurdy-gurdy-{engine}`` so the Pareto table carries the engine-pinned
variant as its own column — the wall-clock lever identified in
``SUMMARY.md`` without touching the corpus specs.

Usage::

    python bench/riscv-btor2/baselines/hurdy_gurdy.py --max-tasks 5
    python bench/riscv-btor2/baselines/hurdy_gurdy.py --max-tasks 5 \\
        > _runs/hurdy-gurdy.jsonl
    python bench/riscv-btor2/baselines/hurdy_gurdy.py --engine bitwuzla \\
        --max-tasks 5 > _runs/hurdy-gurdy-bitwuzla.jsonl
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Any

# Make sibling imports work + `import gurdy.*` resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from gurdy.pairs.riscv_btor2 import PAIR  # noqa: F401  (registers pair)

from framework_oracle import (  # type: ignore
    CORPUS,
    iter_questions,
    run_one as framework_run_one,
)


def _lifted_to_schema(lifted: str) -> tuple[str, str]:
    """Map a lifted verdict to (schema_verdict, notes)."""
    if lifted in ("reachable", "unreachable", "proved", "unknown"):
        return (lifted, f"lifted={lifted}")
    if lifted.startswith("lift-error:"):
        return ("error", lifted)
    return ("error", f"unrecognized lifted verdict: {lifted!r}")


def run_one(
    task_dir: Path,
    *,
    timeout_s: int = 60,
    memory_mb: int = 2000,  # noqa: ARG001 — informational; the v1 dispatcher carries its own
    engine: str | None = None,
) -> list[dict[str, Any]]:
    """Run hurdy-gurdy on every question in this task; return one
    schema row per question. ``engine`` overrides each question's
    ``analysis.engine`` and renames the tool to ``hurdy-gurdy-{engine}``."""
    tool = "hurdy-gurdy" if engine is None else f"hurdy-gurdy-{engine}"
    rows: list[dict[str, Any]] = []
    try:
        questions = iter_questions(task_dir)
    except Exception as exc:
        return [{
            "tool": tool,
            "task": task_dir.name,
            "verdict": "error",
            "wall_s": 0.0,
            "rss_mb": 0.0,
            "expected": "?",
            "correct": None,
            "cmd": "",
            "raw_excerpt": "",
            "notes": f"iter_questions: {type(exc).__name__}: {exc}",
        }]
    for qid, expected, spec in questions:
        tid = task_dir.name if qid is None else f"{task_dir.name}::{qid}"
        if engine is not None:
            spec = dataclasses.replace(
                spec, analysis=dataclasses.replace(spec.analysis, engine=engine)
            )
        t0 = time.monotonic()
        try:
            r = framework_run_one(spec)
        except Exception as exc:
            rows.append({
                "tool": tool,
                "task": tid,
                "verdict": "error",
                "wall_s": time.monotonic() - t0,
                "rss_mb": 0.0,
                "expected": expected,
                "correct": None,
                "cmd": "framework_oracle.run_one",
                "raw_excerpt": "",
                "notes": f"framework_run_one: {type(exc).__name__}: {exc}",
            })
            continue
        verdict, notes = _lifted_to_schema(r.get("lifted_verdict", ""))
        engine = r.get("engine", "?")
        correct: bool | None
        if verdict in ("reachable", "unreachable", "proved"):
            # `proved` collapses to unreachable for correctness vs
            # expected (proved is strictly stronger than unreachable).
            normalized = "unreachable" if verdict == "proved" else verdict
            normalized_expected = (
                "unreachable" if expected == "proved" else expected
            )
            correct = (normalized == normalized_expected)
        else:
            correct = None
        rows.append({
            "tool": tool,
            "task": tid,
            "verdict": verdict,
            "wall_s": round(r.get("elapsed", 0.0), 3),
            "rss_mb": 0.0,
            "expected": expected,
            "correct": correct,
            "cmd": f"framework_oracle.run_one(engine={engine})",
            "raw_excerpt": "",
            "notes": f"{notes}; engine={engine}; reason={r.get('reason','')}",
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="hurdy-gurdy baseline row")
    p.add_argument("--task", help="run only one task by id (substring)")
    p.add_argument("--corpus", default=str(CORPUS))
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--max-tasks", type=int, default=3)
    p.add_argument(
        "--engine",
        help="override analysis.engine for every question (e.g. bitwuzla); "
        "rows are emitted under tool name hurdy-gurdy-{engine}",
    )
    args = p.parse_args(argv)

    corpus = Path(args.corpus)
    candidates = sorted(
        d for d in corpus.iterdir()
        if d.is_dir() and (d / "task.toml").exists() and (d / "spec.json").exists()
    )
    if args.task:
        candidates = [d for d in candidates if args.task in d.name]
    if len(candidates) > args.max_tasks:
        print(
            f"{len(candidates)} candidate tasks; --max-tasks={args.max_tasks} caps this run",
            file=sys.stderr,
        )
        candidates = candidates[: args.max_tasks]

    for d in candidates:
        for row in run_one(d, timeout_s=args.timeout, engine=args.engine):
            sys.stdout.write(json.dumps(row, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
