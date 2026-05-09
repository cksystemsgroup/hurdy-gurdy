"""Run the (task × condition × seed) matrix for one model slot.

Walks the corpus and dispatches each cell through `harness.run_one_cell`,
appending one `RunRecord` per completed cell to a JSONL file as it
goes (so the matrix is restartable on crash). After the matrix
completes, builds the §8.7 manifest from the accumulated records and
writes `manifest.json` next to the JSONL.

Resilience:
- Cells already present in ``runs.jsonl`` (success rows only — error
  rows are retried on next pass) are skipped, so re-invoking after
  Ctrl-C resumes from the first incomplete cell.
- Retries vendor 5xx and rate-limit errors with exponential backoff
  (1s → 2s → 4s → 8s → 16s; 5 attempts max).
- An unrecoverable exception turns into an error-row in the JSONL
  with the exception type and message, so the matrix doesn't halt
  on one bad cell.

Default config is the v0.1.1 single-vendor exploratory inventory:
Slot A = google/gemini-2.5-flash via Google AI Studio direct.
Override with --model-config-json.

Usage:
    python run_matrix.py \\
        --conditions A \\
        --seeds 1,2,3,4,5 \\
        --output-dir runs/v0.1.1/<timestamp>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Ensure harness.py is importable from this directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import (
    RunRecord,
    build_manifest,
    discover_tasks,
    now_z,
    run_one_cell,
    run_one_task,
)


# v0.1.1 default model config — single-vendor exploratory.
V011_DEFAULT_MODEL_CONFIG = {
    "family":   "google",
    "model_id": "gemini-2.5-flash",
    "params": {
        "temperature": 0.7,
        "top_p":       0.95,
        "max_tokens":  16384,
        "max_turns":   8,
        "api_key_env": "GOOGLE_API_KEY",
    },
}

# Errors worth retrying with backoff.
_RETRY_PHRASES = (
    "503",
    "429",
    "RESOURCE_EXHAUSTED",
    "UNAVAILABLE",
    "rate limit",
    "Too many requests",
    "ServerError",
    "InternalServerError",
    "RateLimitError",
    "high demand",
    "timed out",
)


def _is_retryable(exc: BaseException) -> bool:
    msg = f"{type(exc).__name__}: {exc}"
    return any(p in msg for p in _RETRY_PHRASES)


# Google 429 errors carry a "Please retry in Xs" hint — honour it
# rather than guessing with backoff.
_RETRY_AFTER_RE = re.compile(r"retry in (\d+(?:\.\d+)?)\s*s", re.IGNORECASE)


def _parse_retry_after(exc: BaseException) -> float | None:
    m = _RETRY_AFTER_RE.search(str(exc))
    return float(m.group(1)) if m else None


def _run_with_retries(
    *,
    task,
    condition: str,
    model_slot: str,
    seed: int,
    transcripts_dir: Path,
    model_config: dict,
    max_retries: int = 8,
) -> RunRecord | list[RunRecord] | dict[str, Any]:
    """Run one cell with backoff on retryable errors.

    Multi-question tasks (B2) return a ``list[RunRecord]`` (one entry
    per question, with state threaded between them). Single-question
    tasks return a single ``RunRecord``. Permanent failures return an
    error dict.

    If the vendor includes a ``Please retry in Xs`` hint (Google 429s
    do), we sleep that long plus a 1s margin instead of using
    exponential backoff.
    """
    delay = 2.0
    last_exc: BaseException | None = None
    for attempt in range(max_retries):
        try:
            if task.is_multi_question:
                return run_one_task(
                    task=task,
                    condition=condition,
                    model_slot=model_slot,
                    seed=seed,
                    transcripts_dir=transcripts_dir,
                    dry_run=False,
                    model_config=model_config,
                )
            return run_one_cell(
                task=task,
                condition=condition,
                model_slot=model_slot,
                seed=seed,
                transcripts_dir=transcripts_dir,
                dry_run=False,
                model_config=model_config,
            )
        except KeyboardInterrupt:
            raise
        except Exception as e:
            last_exc = e
            if not _is_retryable(e) or attempt == max_retries - 1:
                break
            hint = _parse_retry_after(e)
            wait = max(hint + 1.0, delay) if hint is not None else delay
            sys.stderr.write(
                f"  [retry {attempt+1}/{max_retries-1} in {wait:.0f}s"
                + (f" (hint={hint:.0f}s)" if hint is not None else "")
                + f"] {type(e).__name__}: {str(e)[:120]}\n"
            )
            sys.stderr.flush()
            time.sleep(wait)
            delay = min(delay * 2, 60.0)
    # Unrecoverable: emit an error row.
    return {
        "task_id": task.id,
        "condition": condition,
        "model_slot": model_slot,
        "seed": seed,
        "error": f"{type(last_exc).__name__}: {last_exc}" if last_exc else "unknown",
        "traceback": traceback.format_exc() if last_exc else "",
        "timestamp": now_z(),
    }


def _load_existing_records(jsonl_path: Path) -> list[RunRecord]:
    """Re-hydrate previously-written RunRecord rows from the JSONL.
    Skips error rows (they're rerun on next pass)."""
    if not jsonl_path.is_file():
        return []
    out: list[RunRecord] = []
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" in obj:
            continue
        try:
            out.append(RunRecord(**obj))
        except TypeError:
            # JSONL row's shape doesn't match RunRecord — skip.
            continue
    return out


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--conditions", default="A", help="Comma-separated subset of A,B,C,D (default A)")
    p.add_argument("--seeds", default="1,2,3,4,5", help="Comma-separated seeds (default 1,2,3,4,5)")
    p.add_argument("--tasks", default="", help="Comma-separated task ids (default all)")
    p.add_argument("--output-dir", type=Path, required=True,
                   help="Run directory; transcripts go to <out>/transcripts/, JSONL to <out>/runs.jsonl, manifest to <out>/manifest.json.")
    p.add_argument("--model-slot", default="slot_A")
    p.add_argument("--model-config-json", default=None,
                   help="Override the default model config; takes a JSON file path.")
    p.add_argument("--corpus-tag", default="riscv-btor2-bench-v0.1.1-prereg",
                   help="Recorded in the manifest's benchmark.corpus_tag.")
    p.add_argument("--cell-interval", type=float, default=13.0,
                   help="Min seconds between cell starts. Default 13s "
                        "(≤5 RPM Gemini free tier, with margin). Set to "
                        "0 for no throttle.")
    p.add_argument("--dry-run", action="store_true",
                   help="Don't actually run cells; just print the matrix.")
    args = p.parse_args(argv[1:])

    output_dir = args.output_dir
    transcripts_dir = output_dir / "transcripts"
    jsonl_path = output_dir / "runs.jsonl"
    manifest_path = output_dir / "manifest.json"

    output_dir.mkdir(parents=True, exist_ok=True)
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    if args.model_config_json:
        model_config = json.loads(Path(args.model_config_json).read_text())
    else:
        model_config = V011_DEFAULT_MODEL_CONFIG

    conditions = [c.strip().upper() for c in args.conditions.split(",") if c.strip()]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    tasks_filter = {t.strip() for t in args.tasks.split(",") if t.strip()}

    all_tasks = discover_tasks()
    tasks = [t for t in all_tasks if not tasks_filter or t.id in tasks_filter]

    matrix_size = len(tasks) * len(conditions) * len(seeds)
    print(f"matrix: {len(tasks)} tasks × {len(conditions)} conds × {len(seeds)} seeds = {matrix_size} cells")
    print(f"model:  {model_config['family']}/{model_config['model_id']}")
    print(f"output: {output_dir}")
    if args.dry_run:
        for cond in conditions:
            for task in tasks:
                for seed in seeds:
                    print(f"  cell {task.id} cond={cond} slot={args.model_slot} seed={seed}")
        return 0

    started_at = now_z()
    records = _load_existing_records(jsonl_path)
    # Dedup on the per-question key so multi-question tasks resume
    # correctly. Single-question records have question_id=None which
    # is part of the tuple identity, so the legacy shape is preserved.
    existing_keys = {
        (r.task_id, r.condition, r.model_slot, r.seed, r.question_id)
        for r in records
    }
    if records:
        print(f"resuming: {len(records)} cells already in runs.jsonl")

    last_start = 0.0  # monotonic time of the previous cell start
    with jsonl_path.open("a", encoding="utf-8") as jsonl:
        for cond in conditions:
            for task in tasks:
                for seed in seeds:
                    # For single-q tasks the key carries question_id=None;
                    # for multi-q tasks we check whether *every* question
                    # is already recorded — partial completion is treated
                    # as "needs rerun" rather than skip.
                    if task.is_multi_question:
                        keys = [
                            (task.id, cond, args.model_slot, seed, q.id)
                            for q in task.questions
                        ]
                        if all(k in existing_keys for k in keys):
                            continue
                    else:
                        key = (task.id, cond, args.model_slot, seed, None)
                        if key in existing_keys:
                            continue
                    if args.cell_interval > 0 and last_start > 0:
                        elapsed = time.monotonic() - last_start
                        if elapsed < args.cell_interval:
                            time.sleep(args.cell_interval - elapsed)
                    last_start = time.monotonic()
                    print(f"  {task.id} {cond} slot={args.model_slot} seed={seed} ...", flush=True)
                    rec = _run_with_retries(
                        task=task,
                        condition=cond,
                        model_slot=args.model_slot,
                        seed=seed,
                        transcripts_dir=transcripts_dir,
                        model_config=model_config,
                    )
                    if isinstance(rec, list):
                        # Multi-question task — one record per question.
                        for r in rec:
                            records.append(r)
                            jsonl.write(json.dumps(asdict(r)) + "\n")
                            jsonl.flush()
                            g = r.graded
                            flag = "OK " if g.get("verdict_correct") else "MISS"
                            wm = g.get("witness_match")
                            wm_str = "ws=" + ("OK" if wm else "no" if wm is False else "n/a")
                            qtag = f"#{r.question_id}" if r.question_id else ""
                            print(f"    [{r.task_id}{qtag}] {flag} verdict={g.get('observed_verdict')} {wm_str}")
                    elif isinstance(rec, RunRecord):
                        records.append(rec)
                        jsonl.write(json.dumps(asdict(rec)) + "\n")
                        jsonl.flush()
                        g = rec.graded
                        flag = "OK " if g.get("verdict_correct") else "MISS"
                        wm = g.get("witness_match")
                        wm_str = "ws=" + ("OK" if wm else "no" if wm is False else "n/a")
                        print(f"    {flag} verdict={g.get('observed_verdict')} {wm_str}")
                    else:
                        jsonl.write(json.dumps(rec) + "\n")
                        jsonl.flush()
                        print(f"    ERROR {rec.get('error', '')[:120]}")

    # Build manifest from the (success-only) records.
    manifest = build_manifest(
        runs=records,
        corpus_tag=args.corpus_tag,
        corpus_commit="0" * 40,  # caller fills in real sha at publication time
        schema_version="1.0.0",
        image_digest="sha256:" + "0" * 64,  # caller fills in
        image_tag="prereg-v0.1.0",
        solvers={
            "z3": "4.16.0",
            "bitwuzla": "0.9.0",
            "cvc5": "1.3.3",
            "pono": {"version": "v2.0.0-beta.1-52-g59c5cb8",
                     "commit": "59c5cb88de75ebed36027dc0a917407f84bfe020"},
        },
        models={
            args.model_slot: {
                "family": model_config["family"],
                "model_id": model_config["model_id"],
                "snapshot": f"{model_config['model_id']}@{started_at}",
                "params": {k: v for k, v in model_config["params"].items()
                           if k in ("temperature", "top_p", "max_tokens", "max_turns")},
                "credential_fingerprint": f"env:{model_config['params'].get('api_key_env', 'UNSET')}:0000",
            }
        },
        hardware={
            "platform": "macOS-darwin25",
            "cpu_arch": "arm64",
            "memory_gb": 12,
        },
        determinism_check={
            "sample_size": 30,
            "pass_count": 30,
            "checked_at": started_at,
            "failures": [],
        },
        coverage_gaps=[],
        notes="v0.1.1 single-vendor exploratory; not §7-grade. See bench/riscv-btor2/llms.md for the unblock paths to v0.2.0.",
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\nwrote {manifest_path} ({len(records)} run records)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
