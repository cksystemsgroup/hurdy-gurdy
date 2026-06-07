"""ESBMC adapter for the aarch64-btor2 SOTA Pareto comparison.

Invokes ``esbmc`` on a task's ``task.c`` (when present) and emits
one row of the schema from ``bench/riscv-btor2/baselines/README.md`` §2.
ESBMC is the P14 peer — a second-vendor C BMC that handles some C-UB cases
differently from CBMC.

This adapter uses ``task.c`` directly: ESBMC interprets
``__builtin_unreachable()`` as ``assert(0)``, so the corpus trap idiom
(trap() → brk #0 + __builtin_unreachable()) works without a wrapper file.
Entry is ``_start`` (set via ``--function _start``).

Verdict mapping:

- ``VERIFICATION SUCCESSFUL`` → ``unreachable`` (no path to trap within
  the unwind bound).
- ``VERIFICATION FAILED`` → ``reachable`` (BMC found a path to trap()).
- Subprocess timeout → ``timeout``.
- ``esbmc`` not on PATH → ``error notes="esbmc not on PATH"``.
- No ``task.c`` in the task dir → ``skip notes="no task.c"``.
- Parse or GOTO-program error → ``error``.

Adapted from bench/riscv-btor2/baselines/esbmc.py; ISA-agnostic invocation
unchanged. Only corpus path adapts: seeds live under corpus/seed/ here.

Usage::

    python bench/aarch64-btor2/baselines/esbmc.py --task 0001
    python bench/aarch64-btor2/baselines/esbmc.py --max-tasks 5
"""

from __future__ import annotations

import argparse
import json
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "seed"


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


def _parse_esbmc_output(stdout: str, stderr: str) -> tuple[str, str]:
    """Return ``(verdict, notes)`` from ESBMC's textual output.

    ESBMC prints ``VERIFICATION SUCCESSFUL`` or ``VERIFICATION FAILED``
    on its last non-empty output line.  Check FAILED first (a multi-
    property run may print both; any FAILED means reachable).
    """
    out = stdout + "\n" + stderr
    if "VERIFICATION FAILED" in out:
        return ("reachable", "VERIFICATION FAILED")
    if "VERIFICATION SUCCESSFUL" in out:
        return ("unreachable", "VERIFICATION SUCCESSFUL")
    if "PARSING ERROR" in out or "Parsing error" in out:
        return ("error", "PARSING ERROR")
    if "error" in out.lower() and "goto" in out.lower():
        return ("error", "GOTO-program error")
    return ("error", "no verdict line in ESBMC output")


def run_one(
    task_dir: Path,
    *,
    timeout_s: int = 60,
    memory_mb: int = 2000,
    unwind: int = 20,
) -> dict[str, Any]:
    """Run ESBMC on ``task.c``; return one row of the output schema.

    Caps:
    - ``timeout_s`` — wall-clock subprocess cap (default 60s).
    - ``memory_mb`` — per-process RSS cap via ``setrlimit(RLIMIT_AS)``.
    - ``unwind`` — ESBMC loop unwind depth (``--unwind``).
    """
    task_id = task_dir.name
    expected = _expected_verdict(task_dir)
    c_path = task_dir / "task.c"

    if not c_path.exists():
        return {
            "tool": "esbmc",
            "task": task_id,
            "verdict": "skip",
            "wall_s": 0.0,
            "rss_mb": 0.0,
            "expected": expected,
            "correct": None,
            "cmd": "",
            "raw_excerpt": "",
            "notes": "no task.c",
        }

    if shutil.which("esbmc") is None:
        return {
            "tool": "esbmc",
            "task": task_id,
            "verdict": "error",
            "wall_s": 0.0,
            "rss_mb": 0.0,
            "expected": expected,
            "correct": None,
            "cmd": "",
            "raw_excerpt": "",
            "notes": "esbmc not on PATH",
        }

    cmd = [
        "esbmc",
        str(c_path),
        "--function", "_start",
        "--unwind", str(unwind),
    ]

    def _set_limits():
        bytes_cap = memory_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (bytes_cap, bytes_cap))
        except Exception:
            pass

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
        verdict, notes = _parse_esbmc_output(proc.stdout, proc.stderr)
        raw = (proc.stdout + "\n----\n" + proc.stderr)[:4096]
    except subprocess.TimeoutExpired:
        wall = time.monotonic() - t0
        verdict = "timeout"
        notes = f"timeout after {timeout_s}s"
        raw = ""

    correct: bool | None
    if verdict in ("reachable", "unreachable"):
        correct = (verdict == expected)
    else:
        correct = None

    return {
        "tool": "esbmc",
        "task": task_id,
        "verdict": verdict,
        "wall_s": round(wall, 3),
        "rss_mb": 0.0,
        "expected": expected,
        "correct": correct,
        "cmd": " ".join(cmd),
        "raw_excerpt": raw,
        "notes": notes,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ESBMC baseline adapter (aarch64-btor2)")
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
        and (d / "task.c").exists()
    )
    if args.task:
        candidates = [d for d in candidates if args.task in d.name]
    if len(candidates) > args.max_tasks:
        print(
            f"{len(candidates)} ESBMC-ready tasks; --max-tasks={args.max_tasks}"
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
        sys.stdout.write(json.dumps(row, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "run_one",
    "main",
    "_parse_esbmc_output",
    "_expected_verdict",
]
