"""CBMC adapter for the SOTA Pareto comparison.

Invokes ``cbmc`` on a task's C source and emits one row of the schema
in ``README.md`` §2.  CBMC is the immediate-peer C BMC reference
(6.9.0 confirmed working at iter-14 audit).

Source file preference (first found wins):

1. ``task.cbmc.c`` — explicit CBMC wrapper with ``main()`` entry.
2. ``task.c`` — direct source with ``--function _start`` entry.

If neither is present the row is ``skip``.

Verdict mapping:

- ``VERIFICATION SUCCESSFUL`` → ``unreachable`` (assertion holds for
  every path within the unwind bound).
- ``VERIFICATION FAILED`` → ``reachable`` (assertion violated; a
  counterexample exists).
- Any "may be unsound due to incomplete unwinding" warning surfaced
  alongside SUCCESS → ``unknown`` (bounded verification, not a proof).
- Process exit 0 with no verdict line → ``error``.
- Subprocess timeout → ``timeout``.
- ``cbmc`` not on PATH → ``error notes="cbmc not on PATH"``.
- No C source in the task dir → ``skip notes="no task.c or task.cbmc.c"``.

Usage:

    python bench/riscv-btor2/baselines/cbmc.py --task 0100
    python bench/riscv-btor2/baselines/cbmc.py --max-tasks 5
"""

from __future__ import annotations

import argparse
import json
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


CORPUS = Path(__file__).resolve().parent.parent / "corpus"


def _expected_verdict(task_dir: Path) -> str:
    """Read [expected].verdict from task.toml; '?' if missing."""
    try:
        import tomllib  # py311+
    except Exception:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    try:
        raw = tomllib.loads((task_dir / "task.toml").read_text())
        return raw.get("expected", {}).get("verdict", "?")
    except Exception:
        return "?"


def _parse_cbmc_output(stdout: str, stderr: str) -> tuple[str, str]:
    """Return ``(verdict, notes)`` from CBMC's textual output.

    Order matters: check FAILED before SUCCESSFUL because a multi-property
    run can report both lines (we treat any FAILED as reachable since the
    schema property is a single bad-clause).
    """
    out = stdout + "\n" + stderr
    if "VERIFICATION FAILED" in out:
        return ("reachable", "VERIFICATION FAILED")
    if "VERIFICATION SUCCESSFUL" in out:
        if "**** WARNING" in out and "unwinding assertion" in out:
            return ("unknown", "bounded SUCCESSFUL with unwinding assertion")
        return ("unreachable", "VERIFICATION SUCCESSFUL")
    if "PARSING ERROR" in out:
        return ("error", "PARSING ERROR")
    if "**** ERROR" in out:
        return ("error", "**** ERROR in cbmc output")
    return ("error", "no verdict line in output")


def run_one(
    task_dir: Path,
    *,
    timeout_s: int = 60,
    memory_mb: int = 2000,
    unwind: int = 20,
) -> dict[str, Any]:
    """Run CBMC on this task's C source; return one schema row.

    Caps:
    - ``timeout_s`` — wall-clock subprocess cap (default 60s,
      ``V2_AGENT_LOOP.md`` §4).
    - ``memory_mb`` — per-process RSS cap via ``setrlimit(RLIMIT_AS)``.
    - ``unwind`` — CBMC loop unwind depth.
    """
    task_id = task_dir.name
    expected = _expected_verdict(task_dir)

    # Prefer task.cbmc.c (explicit CBMC wrapper); fall back to task.c
    # with --function _start (corpus trap idiom works via --bounds-check).
    cbmc_path = task_dir / "task.cbmc.c"
    plain_path = task_dir / "task.c"
    if cbmc_path.exists():
        c_path = cbmc_path
        entry_flags: list[str] = []
        tmp_wrapper: "tempfile.NamedTemporaryFile | None" = None
    elif plain_path.exists():
        # Patch __builtin_unreachable() → __CPROVER_assert(0,"trap reached")
        # so CBMC detects trap() reachability, not just UB side-effects.
        src = plain_path.read_text()
        patched = src.replace(
            "__builtin_unreachable()",
            '__CPROVER_assert(0, "trap reached"); __builtin_unreachable()',
        )
        tmp_wrapper = tempfile.NamedTemporaryFile(
            suffix=".c", delete=False, mode="w"
        )
        tmp_wrapper.write(patched)
        tmp_wrapper.flush()
        c_path = Path(tmp_wrapper.name)
        entry_flags = ["--function", "_start"]
    else:
        return {
            "tool": "cbmc",
            "task": task_id,
            "verdict": "skip",
            "wall_s": 0.0,
            "rss_mb": 0.0,
            "expected": expected,
            "correct": None,
            "cmd": "",
            "raw_excerpt": "",
            "notes": "no task.c or task.cbmc.c",
        }

    if shutil.which("cbmc") is None:
        if tmp_wrapper is not None:
            Path(tmp_wrapper.name).unlink(missing_ok=True)
        return {
            "tool": "cbmc",
            "task": task_id,
            "verdict": "error",
            "wall_s": 0.0,
            "rss_mb": 0.0,
            "expected": expected,
            "correct": None,
            "cmd": "",
            "raw_excerpt": "",
            "notes": "cbmc not on PATH",
        }

    cmd = [
        "cbmc",
        str(c_path),
        *entry_flags,
        "--unwind", str(unwind),
        "--bounds-check",
        "--pointer-check",
    ]

    def _set_limits():
        bytes_cap = memory_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (bytes_cap, bytes_cap))
        except Exception:
            pass  # RLIMIT_AS not enforced on every OS (notably macOS).

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            preexec_fn=_set_limits,
        )
        wall = time.monotonic() - t0
        verdict, notes = _parse_cbmc_output(proc.stdout, proc.stderr)
        raw = (proc.stdout + "\n----\n" + proc.stderr)[:4096]
    except subprocess.TimeoutExpired:
        wall = time.monotonic() - t0
        verdict = "timeout"
        notes = f"timeout after {timeout_s}s"
        raw = ""
    finally:
        if tmp_wrapper is not None:
            Path(tmp_wrapper.name).unlink(missing_ok=True)

    correct: bool | None
    if verdict in ("reachable", "unreachable"):
        correct = (verdict == expected)
    else:
        correct = None

    return {
        "tool": "cbmc",
        "task": task_id,
        "verdict": verdict,
        "wall_s": round(wall, 3),
        "rss_mb": 0.0,  # CBMC doesn't self-report; skip ru_maxrss for portability
        "expected": expected,
        "correct": correct,
        "cmd": " ".join(cmd),
        "raw_excerpt": raw,
        "notes": notes,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CBMC baseline adapter")
    p.add_argument("--task", help="run only one task by id (substring match)")
    p.add_argument("--corpus", default=str(CORPUS))
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--memory-mb", type=int, default=2000)
    p.add_argument("--unwind", type=int, default=20)
    p.add_argument(
        "--max-tasks",
        type=int,
        default=3,
        help="RAM-safety cap (default 3). Pass higher to expand.",
    )
    args = p.parse_args(argv)

    corpus = Path(args.corpus)
    if not corpus.is_dir():
        print(f"corpus not found: {corpus}", file=sys.stderr)
        return 2

    candidates = sorted(
        d
        for d in corpus.iterdir()
        if d.is_dir()
        and (d / "task.toml").exists()
        and ((d / "task.cbmc.c").exists() or (d / "task.c").exists())
    )
    if args.task:
        candidates = [d for d in candidates if args.task in d.name]
    if len(candidates) > args.max_tasks:
        print(
            f"{len(candidates)} CBMC-ready tasks; --max-tasks={args.max_tasks}"
            f" caps this run",
            file=sys.stderr,
        )
        candidates = candidates[: args.max_tasks]

    for d in candidates:
        row = run_one(
            d,
            timeout_s=args.timeout,
            memory_mb=args.memory_mb,
            unwind=args.unwind,
        )
        # Print one JSON line per task per the schema.
        sys.stdout.write(json.dumps(row, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
