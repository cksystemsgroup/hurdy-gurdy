"""Per-engine wall-clock comparison for the riscv-btor2 corpus.

Runs every (task, question) under every compatible BMC engine N times
(default 3) and reports median wall-clock per engine. Used to:

- find tasks where one engine is meaningfully faster than another
  (the empirical justification for engine pinning in `task.toml`),
- spot regressions when a solver version is bumped,
- inform v0.3+ corpus design (where should bitwuzla / cvc5 / pono
  earn their place over z3-bmc?).

This is *not* a correctness oracle (`oracle_cross.py` is). The
verdict column is reported only so a SKIP / error can be
distinguished from a genuine runtime measurement.

Usage::

    python bench/riscv-btor2/engine_bench.py --repeat 3
    python bench/riscv-btor2/engine_bench.py --task 0014 --repeat 5
    python bench/riscv-btor2/engine_bench.py --inductive --repeat 3
    python bench/riscv-btor2/engine_bench.py --json > engine_bench.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

# Make ``gurdy.*`` importable without depending on the package being installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.core.tools.compile import compile_spec
from gurdy.pairs.riscv_btor2 import PAIR  # noqa: F401  (registers pair)

from framework_oracle import CORPUS, iter_questions  # type: ignore
from oracle_cross import (  # type: ignore
    BMC_PROFILES,
    INDUCTIVE_PINNED,
    INDUCTIVE_PROFILES,
    Profile,
    _override_directive,
    _run_profile,
)


def _profiles(spec_engine: str, inductive_only: bool, bmc_only: bool) -> tuple[Profile, ...]:
    if spec_engine in INDUCTIVE_PINNED:
        if bmc_only:
            return ()
        return INDUCTIVE_PROFILES
    if inductive_only:
        return ()
    return BMC_PROFILES


def _measure(spec, profiles: tuple[Profile, ...], repeat: int) -> dict[str, dict[str, Any]]:
    """Compile once, dispatch repeat × len(profiles) times. Per
    profile, return ``{verdict, samples_s, median_s, min_s}``."""
    artifact = compile_spec(spec)
    out: dict[str, dict[str, Any]] = {}
    for p in profiles:
        samples: list[float] = []
        last_verdict = "unknown"
        last_reason: str | None = None
        for _ in range(repeat):
            row = _run_profile(spec, p, artifact)
            samples.append(row["elapsed"])
            last_verdict = row["verdict"]
            last_reason = row.get("reason")
        out[p.label] = {
            "engine":  p.engine,
            "verdict": last_verdict,
            "reason":  last_reason,
            "samples": samples,
            "median":  statistics.median(samples),
            "min":     min(samples),
        }
    return out


def _row_text(label: str, results: dict[str, dict[str, Any]]) -> str:
    pieces = [f"{label:42s}"]
    # Print engines in a fixed order so the columns line up across rows.
    order = ["z3-bmc", "bitwuzla", "cvc5", "pono", "z3-spacer", "pono-ind"]
    seen = []
    for name in order:
        if name in results:
            r = results[name]
            seen.append(name)
            if r["verdict"] in ("error", "unknown"):
                pieces.append(f"{name}=SKIP")
            else:
                pieces.append(f"{name}={r['median']*1000:7.1f}ms")
    # Pick up any engine label not in the fixed order.
    for name, r in results.items():
        if name in seen:
            continue
        if r["verdict"] in ("error", "unknown"):
            pieces.append(f"{name}=SKIP")
        else:
            pieces.append(f"{name}={r['median']*1000:7.1f}ms")
    return "  ".join(pieces)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="riscv-btor2 per-engine wall-clock comparison"
    )
    ap.add_argument("--task", help="run only one task by id (substring match)")
    ap.add_argument(
        "--corpus",
        default=str(CORPUS),
        help="corpus directory (default: bench/riscv-btor2/corpus)",
    )
    ap.add_argument("--repeat", type=int, default=3, help="samples per (task, engine)")
    ap.add_argument(
        "--bmc-only",
        action="store_true",
        help="restrict to BMC tasks (skip pinned-spacer tasks)",
    )
    ap.add_argument(
        "--inductive",
        action="store_true",
        help="restrict to inductive tasks (skip BMC tasks)",
    )
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args(argv)

    corpus = Path(args.corpus)
    task_dirs = sorted(
        d for d in corpus.iterdir()
        if d.is_dir() and (d / "task.toml").exists()
    )
    if args.task:
        task_dirs = [d for d in task_dirs if d.name == args.task or args.task in d.name]
        if not task_dirs:
            print(f"no task matching {args.task!r}", file=sys.stderr)
            return 2

    rows_out: list[dict[str, Any]] = []
    t_start = time.monotonic()
    for d in task_dirs:
        try:
            questions = iter_questions(d)
        except Exception as exc:
            if args.json:
                rows_out.append({"task": d.name, "error": str(exc)})
            else:
                print(f"ERROR {d.name}: {exc}")
            continue
        for qid, expected, spec in questions:
            label = d.name if qid is None else f"{d.name}#{qid}"
            profiles = _profiles(spec.analysis.engine, args.inductive, args.bmc_only)
            if not profiles:
                continue
            results = _measure(spec, profiles, args.repeat)
            if args.json:
                rows_out.append({
                    "task":     d.name,
                    "question": qid,
                    "expected": expected,
                    "engines":  results,
                })
            else:
                print(_row_text(label, results))

    elapsed = time.monotonic() - t_start
    if args.json:
        json.dump({"rows": rows_out, "elapsed_s": elapsed}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"\n# total wall-clock: {elapsed:.1f}s ({args.repeat}× per cell)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
