"""Per-engine wall-clock comparison for the aarch64-btor2 corpus.

Runs every task under every compatible BMC engine N times (default 3)
and reports median wall-clock per engine. Tasks without source.elf
(cross-toolchain unavailable) are emitted as SKIP rows; only seed 0001
has an ELF right now.

Adapted from bench/riscv-btor2/engine_bench.py (main). Key AArch64
adaptations vs the riscv reference:
- No framework_oracle.py / iter_questions: task loading is inline via
  oracle_cross._load_task (task.toml + spec.json).
- Tasks without source.elf emit SKIP rows; they never affect timing stats.
- _measure() receives elf_path to pass to compile_spec().
- No per-question loop: one task = one spec = one row.

Usage::

    python bench/aarch64-btor2/engine_bench.py --repeat 3
    python bench/aarch64-btor2/engine_bench.py --task 0001 --repeat 5
    python bench/aarch64-btor2/engine_bench.py --inductive --repeat 3
    python bench/aarch64-btor2/engine_bench.py --json > engine_bench.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.core.tools.compile import compile_spec
from gurdy.pairs.aarch64_btor2 import PAIR  # noqa: F401  (registers pair)

from oracle_cross import (  # type: ignore
    BMC_PROFILES,
    INDUCTIVE_PINNED,
    INDUCTIVE_PROFILES,
    Profile,
    _load_task,
    _run_profile,
    profiles_for,
)

_CORPUS_SEED = Path(__file__).parent / "corpus" / "seed"


def _profiles(spec_engine: str, inductive_only: bool, bmc_only: bool) -> tuple[Profile, ...]:
    if spec_engine in INDUCTIVE_PINNED:
        if bmc_only:
            return ()
        return INDUCTIVE_PROFILES
    if inductive_only:
        return ()
    return BMC_PROFILES


def _measure(
    spec: Any,
    elf_path: Path,
    profiles: tuple[Profile, ...],
    repeat: int,
) -> dict[str, dict[str, Any]]:
    """Compile once, dispatch repeat × len(profiles) times.

    Per profile, return ``{engine, verdict, reason, samples, median, min}``.
    """
    artifact = compile_spec(spec, source_payload=elf_path)
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
    order = ["z3-bmc", "bitwuzla", "cvc5", "pono", "z3-spacer", "pono-ind"]
    seen: list[str] = []
    for name in order:
        if name in results:
            r = results[name]
            seen.append(name)
            if r["verdict"] in ("error", "unknown"):
                pieces.append(f"{name}=SKIP")
            else:
                pieces.append(f"{name}={r['median'] * 1000:7.1f}ms")
    for name, r in results.items():
        if name in seen:
            continue
        if r["verdict"] in ("error", "unknown"):
            pieces.append(f"{name}=SKIP")
        else:
            pieces.append(f"{name}={r['median'] * 1000:7.1f}ms")
    return "  ".join(pieces)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="aarch64-btor2 per-engine wall-clock comparison"
    )
    ap.add_argument("--task", help="run only one task by id (substring match)")
    ap.add_argument(
        "--corpus",
        default=str(_CORPUS_SEED),
        help="seed corpus directory (default: bench/aarch64-btor2/corpus/seed)",
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
        label = d.name
        expected_verdict, elf_path, spec = _load_task(d)

        if elf_path is None or spec is None:
            reason = (
                "no source.elf (cross-toolchain unavailable)"
                if spec is not None
                else "no spec.json"
            )
            if args.json:
                rows_out.append({"task": label, "status": "SKIP", "reason": reason})
            else:
                print(f"SKIP {label}: {reason}")
            continue

        profiles = _profiles(spec.analysis.engine, args.inductive, args.bmc_only)
        if not profiles:
            continue

        try:
            results = _measure(spec, elf_path, profiles, args.repeat)
        except Exception as exc:
            if args.json:
                rows_out.append({"task": label, "error": str(exc)})
            else:
                print(f"ERROR {label}: {exc}")
            continue

        if args.json:
            rows_out.append({
                "task":     label,
                "expected": expected_verdict,
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


__all__ = [
    "_profiles",
    "_measure",
    "_row_text",
]
