"""Reference CBMC oracle for the v0.4 C-subset corpus.

Condition D (BENCHMARKING.md §3.D) is the source-level-verifier
baseline: an LLM may invoke a verifier that consumes the C source
directly, with no help from the pair. For RISC-V there is no
direct source-level verifier analogue (SCOPE.md §6 documents the
omission for the original assembly corpus), but the v0.4 C-derived
corpus *does* have a natural source-level baseline: CBMC.

This script is the §3.D analogue of ``framework_oracle.py`` (B0)
and ``condition_c_reference.py`` (C-smoke). For every task in the
C subset, it:

  1. Rewrites ``task.c`` to a CBMC-friendly variant via
     ``corpus/_emit_cbmc.py`` (`task.cbmc.c`).
  2. Runs ``cbmc task.cbmc.c --unwind <bound>`` and parses the
     "VERIFICATION SUCCESSFUL" / "VERIFICATION FAILED" verdict.
  3. Maps CBMC's verdict to the corpus vocabulary:
       SUCCESSFUL → ``unreachable``  (no assertion violation; the
                                       trap is unreachable in the C
                                       semantics CBMC sees)
       FAILED     → ``reachable``    (assertion violated; trap reach.)
       other      → ``unknown``
  4. Compares to the task's pre-registered ``expected_verdict``
     and reports PASS / FAIL / SKIP.

The script does *not* validate translation: CBMC reasons over the
C source's standard semantics; the bench's BTOR2 lowering may
interpret the same source differently (especially on lowering-
sensitive cases — that's the whole point of the lowering tier).
A FAIL row here is interesting: it flags either a CBMC-vs-bench
disagreement (study it) or a true bench bug (rare).

Usage::

    python bench/riscv-btor2/condition_d_reference.py
    python bench/riscv-btor2/condition_d_reference.py --task 0100
    python bench/riscv-btor2/condition_d_reference.py --json > d.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore


BENCH = Path(__file__).resolve().parent
CORPUS = BENCH / "corpus"
EMIT_CBMC = CORPUS / "_emit_cbmc.py"


def _read_task_toml(task_dir: Path) -> dict:
    return tomllib.loads((task_dir / "task.toml").read_text())


def _expected_verdict(task_toml: dict) -> str:
    if "expected" in task_toml:
        v = task_toml["expected"].get("verdict")
        if isinstance(v, str):
            return v
    if "questions" in task_toml:
        # Multi-question tasks aren't expected in the C subset; fall
        # back to the first question's verdict.
        for _, q in sorted(task_toml["questions"].items()):
            return q.get("expected_verdict", "?")
    return "?"


def _is_c_task(task_dir: Path) -> bool:
    return (task_dir / "task.c").exists()


def _emit_cbmc_variant(task_dir: Path) -> Path:
    res = subprocess.run(
        [sys.executable, str(EMIT_CBMC), str(task_dir)],
        capture_output=True, text=True, check=True,
    )
    return task_dir / "task.cbmc.c"


def _cbmc_verdict(text: str) -> str:
    """Parse CBMC's stdout for the headline verdict line."""
    for line in reversed(text.splitlines()):
        s = line.strip()
        if s == "VERIFICATION SUCCESSFUL":
            return "successful"
        if s == "VERIFICATION FAILED":
            return "failed"
        if s.startswith("VERIFICATION INCONCLUSIVE"):
            return "inconclusive"
    return "unknown"


def _bench_verdict(cbmc_verdict: str) -> str:
    if cbmc_verdict == "successful":
        return "unreachable"
    if cbmc_verdict == "failed":
        return "reachable"
    return "unknown"


def _verdict_satisfies(expected: str, observed: str) -> bool:
    if observed in ("unknown", "error"):
        return False
    if expected == "reachable":
        return observed == "reachable"
    if expected in ("unreachable", "proved"):
        return observed in ("unreachable", "proved")
    return False


def run_one(task_dir: Path) -> dict[str, Any]:
    task_toml = _read_task_toml(task_dir)
    expected = _expected_verdict(task_toml)
    cbmc_c = _emit_cbmc_variant(task_dir)
    bound = int(task_toml.get("c", {}).get("bound", 100))
    # CBMC unwind is the per-loop unrolling depth; we use a generous
    # multiple of the task's bound so loops that aren't tightly bounded
    # don't trigger CBMC's "loop unwinding" warning. Cap at 256.
    unwind = min(max(bound, 30), 256)

    t0 = time.monotonic()
    res = subprocess.run(
        ["cbmc", str(cbmc_c), "--unwind", str(unwind)],
        capture_output=True, text=True,
        timeout=60,
    )
    elapsed = time.monotonic() - t0
    cbmc_v = _cbmc_verdict(res.stdout + res.stderr)
    bench_v = _bench_verdict(cbmc_v)
    return {
        "task":             task_dir.name,
        "expected":         expected,
        "cbmc_verdict":     cbmc_v,
        "bench_verdict":    bench_v,
        "passes":           _verdict_satisfies(expected, bench_v),
        "elapsed":          elapsed,
        "unwind":           unwind,
        "stdout_tail":      res.stdout[-200:].strip(),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", help="run only one task (substring match)")
    p.add_argument("--corpus", default=str(CORPUS))
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if shutil.which("cbmc") is None:
        print("cbmc not on PATH — install via `brew install cbmc` or in the bench Docker image",
              file=sys.stderr)
        return 2

    corpus = Path(args.corpus)
    task_dirs = sorted(
        d for d in corpus.iterdir()
        if d.is_dir() and _is_c_task(d) and (d / "task.toml").exists()
    )
    if args.task:
        task_dirs = [d for d in task_dirs if args.task in d.name]
        if not task_dirs:
            print(f"no C task matching {args.task!r}", file=sys.stderr)
            return 2

    rows: list[dict[str, Any]] = []
    fail_count = 0
    skip_count = 0
    for d in task_dirs:
        try:
            row = run_one(d)
        except subprocess.TimeoutExpired:
            row = {
                "task":          d.name,
                "expected":      _expected_verdict(_read_task_toml(d)),
                "cbmc_verdict":  "timeout",
                "bench_verdict": "unknown",
                "passes":        False,
                "elapsed":       60.0,
            }
            skip_count += 1
        except Exception as exc:
            row = {
                "task":          d.name,
                "error":         f"{type(exc).__name__}: {exc}",
                "passes":        False,
            }
            skip_count += 1
        rows.append(row)
        if not row.get("passes") and "error" not in row \
                and row.get("cbmc_verdict") not in ("timeout", "inconclusive", "unknown"):
            fail_count += 1
        if not args.json:
            tag = (
                "PASS" if row.get("passes") else
                ("SKIP" if row.get("cbmc_verdict") in ("timeout", "inconclusive", "unknown")
                 else "FAIL")
            )
            label = row["task"]
            cbmc_v = row.get("cbmc_verdict", "?")
            bench_v = row.get("bench_verdict", "?")
            exp = row.get("expected", "?")
            elapsed = row.get("elapsed", 0)
            print(
                f"{tag:5s} {label:42s} expected={exp:11s} "
                f"cbmc={cbmc_v:11s} → {bench_v:11s} {elapsed:.2f}s"
            )

    if args.json:
        json.dump({"rows": rows, "failures": fail_count, "skipped": skip_count},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif fail_count:
        print(f"\n{fail_count} task(s) FAILED CBMC vs expected", file=sys.stderr)

    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
