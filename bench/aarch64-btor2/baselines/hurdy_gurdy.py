"""hurdy-gurdy baseline runner for aarch64-btor2 Pareto comparison.

Thin shim over the translate+dispatch+lift pipeline that emits one
schema-conformant JSON line per (task, question) for consumption by
``pareto.py``. The hurdy-gurdy verdict is the **lifted** verdict
(post-``Lifter``), not the raw solver verdict, because the lifted
form is what hurdy-gurdy "reports" (lift maps raw solver outcomes
through pair semantics — see SCHEMA.md §10/§11).

Adapted from bench/riscv-btor2/baselines/hurdy_gurdy.py. Key aarch64
differences:
- CORPUS points to corpus/seed/ (seeds in a seed/ subdirectory).
- Tasks without spec.json (ELF not yet cross-compiled) emit verdict="skip".
- Uses gurdy.pairs.aarch64_btor2, Aarch64Btor2Spec, load_aarch64_binary.

Verdict mapping (lifted → schema):

- ``reachable`` / ``unreachable`` / ``proved`` — pass through.
- ``unknown`` — pass through.
- anything starting with ``lift-error:`` — schema ``error``.
- anything else — schema ``error`` with the unrecognized verdict in notes.

Usage::

    python bench/aarch64-btor2/baselines/hurdy_gurdy.py --max-tasks 5
    python bench/aarch64-btor2/baselines/hurdy_gurdy.py --max-tasks 5 \\
        > bench/aarch64-btor2/baselines/_runs/hurdy-gurdy.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

# Make `gurdy.*` importable without the package being installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from gurdy.pairs.aarch64_btor2 import PAIR  # noqa: F401  (registers pair)
from gurdy.pairs.aarch64_btor2.lift.lift import Lifter
from gurdy.pairs.aarch64_btor2.source.loader import load_aarch64_binary
from gurdy.pairs.aarch64_btor2.spec import Aarch64Btor2Spec
from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.dispatch import dispatch


CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "seed"

_lifter = Lifter()


def _lifted_to_schema(lifted: str) -> tuple[str, str]:
    """Map a lifted verdict to (schema_verdict, notes)."""
    if lifted in ("reachable", "unreachable", "proved", "unknown"):
        return (lifted, f"lifted={lifted}")
    if lifted.startswith("lift-error:"):
        return ("error", lifted)
    return ("error", f"unrecognized lifted verdict: {lifted!r}")


def _load_spec(task_dir: Path, filename: str) -> Aarch64Btor2Spec:
    """Load a spec JSON file, rewriting binary.path to an absolute path."""
    p = task_dir / filename
    if not p.exists():
        p = task_dir / "spec.json"
    spec_obj = json.loads(p.read_text())
    bin_field = spec_obj.setdefault("fields", {}).setdefault("binary", {})
    rel = bin_field.get("path", "source.elf")
    bin_field["path"] = str((task_dir / rel).resolve())
    return Aarch64Btor2Spec.from_jsonable(spec_obj)


def _iter_questions(
    task_dir: Path,
) -> list[tuple[str | None, str, Aarch64Btor2Spec]]:
    """Return (question_id, expected_verdict, spec) per question.

    Returns an empty list when spec.json is absent — the task ELF has
    not been compiled yet (cross-compiler not installed). The caller
    converts an empty list to a "skip" row.
    """
    if not (task_dir / "spec.json").exists():
        return []

    toml_raw = tomllib.loads((task_dir / "task.toml").read_text())

    if "questions" in toml_raw:
        out: list[tuple[str | None, str, Aarch64Btor2Spec]] = []
        keys = sorted(
            toml_raw["questions"].keys(),
            key=lambda k: int(k.lstrip("q") or "0"),
        )
        for qid in keys:
            q = toml_raw["questions"][qid]
            spec_file = q.get("spec_file") or f"spec.{qid}.json"
            out.append((qid, q.get("expected_verdict", "?"), _load_spec(task_dir, spec_file)))
        return out

    return [(
        None,
        toml_raw.get("expected", {}).get("verdict", "?"),
        _load_spec(task_dir, "spec.json"),
    )]


def run_one(
    task_dir: Path,
    *,
    timeout_s: int = 60,
    memory_mb: int = 2000,  # noqa: ARG001 — informational
) -> list[dict[str, Any]]:
    """Run hurdy-gurdy on every question in this task; return one schema
    row per question."""
    questions = _iter_questions(task_dir)

    if not questions:
        return [{
            "tool": "hurdy-gurdy",
            "task": task_dir.name,
            "verdict": "skip",
            "wall_s": 0.0,
            "rss_mb": 0.0,
            "expected": "?",
            "correct": None,
            "cmd": "",
            "raw_excerpt": "",
            "notes": "no spec.json — ELF not yet compiled (cross-compiler unavailable)",
        }]

    rows: list[dict[str, Any]] = []
    for qid, expected, spec in questions:
        tid = task_dir.name if qid is None else f"{task_dir.name}::{qid}"
        t0 = time.monotonic()
        try:
            elf_path = Path(spec.binary.path)
            artifact = compile_spec(spec, source_payload=elf_path)
            raw = dispatch(artifact, spec.analysis)
            source = load_aarch64_binary(elf_path)
            lifted = _lifter.lift(artifact, raw, source=source)
            elapsed = time.monotonic() - t0
            lifted_str = lifted.verdict
            engine = raw.engine
            reason = raw.reason or ""
        except Exception as exc:
            rows.append({
                "tool": "hurdy-gurdy",
                "task": tid,
                "verdict": "error",
                "wall_s": round(time.monotonic() - t0, 3),
                "rss_mb": 0.0,
                "expected": expected,
                "correct": None,
                "cmd": "translate+dispatch+lift",
                "raw_excerpt": "",
                "notes": f"pipeline error: {type(exc).__name__}: {exc}",
            })
            continue
        verdict, notes = _lifted_to_schema(lifted_str)
        correct: bool | None
        if verdict in ("reachable", "unreachable", "proved"):
            normalized = "unreachable" if verdict == "proved" else verdict
            normalized_expected = "unreachable" if expected == "proved" else expected
            correct = (normalized == normalized_expected)
        else:
            correct = None
        rows.append({
            "tool": "hurdy-gurdy",
            "task": tid,
            "verdict": verdict,
            "wall_s": round(elapsed, 3),
            "rss_mb": 0.0,
            "expected": expected,
            "correct": correct,
            "cmd": f"translate+dispatch+lift(engine={engine})",
            "raw_excerpt": "",
            "notes": f"{notes}; engine={engine}; reason={reason}",
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="hurdy-gurdy baseline row (aarch64-btor2)")
    p.add_argument("--task", help="run only one task by id (substring)")
    p.add_argument("--corpus", default=str(CORPUS))
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--max-tasks", type=int, default=3)
    args = p.parse_args(argv)

    corpus = Path(args.corpus)
    if not corpus.exists():
        print(f"corpus directory not found: {corpus}", file=sys.stderr)
        return 2

    candidates = sorted(
        d for d in corpus.iterdir()
        if d.is_dir() and (d / "task.toml").exists()
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
        for row in run_one(d, timeout_s=args.timeout):
            sys.stdout.write(json.dumps(row, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["CORPUS", "run_one", "main"]
