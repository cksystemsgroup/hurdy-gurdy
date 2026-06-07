"""aarch64-btor2 benchmark harness — translate + solve corpus tasks.

``run_task(task_path, engine=None, timeout=None) -> TaskResult``
  Loads spec.json from the task directory, optionally overrides engine/timeout,
  translates the ELF to BTOR2, dispatches the solver, and compares the verdict
  against the expected value in task.toml.

Adapted from bench/riscv-btor2/harness.py (stripped to the translate+solve
path; the riscv-btor2 harness is an LLM evaluation framework, not relevant
here).

Usage::

    # list all seed tasks
    python harness.py --list-tasks

    # run one task (z3-bmc, timeout from spec.json)
    python harness.py --task 0001-c-loopsum-o0

    # override engine and timeout
    python harness.py --task 0001-c-loopsum-o0 --engine z3-bmc --timeout 30

    # JSON output (one object per task)
    python harness.py --task 0001-c-loopsum-o0 --json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.core.tools.compile import compile_spec
from gurdy.pairs.aarch64_btor2 import PAIR  # noqa: F401  (registers pair)
from gurdy.pairs.aarch64_btor2.spec import Aarch64Btor2Spec

_CORPUS = Path(__file__).parent / "corpus"
_SEED_DIR = _CORPUS / "seed"


@dataclass(frozen=True)
class TaskResult:
    """Outcome of running one corpus task through translate + solver."""

    task_id: str
    verdict: str
    expected_verdict: str | None
    match: bool | None  # None when expected_verdict is absent from task.toml
    elapsed: float      # solver wall-clock seconds (from RawSolverResult.elapsed)
    engine: str
    reason: str | None = None


def run_task(
    task_path: str | Path,
    engine: str | None = None,
    timeout: float | None = None,
) -> TaskResult:
    """Translate and solve one corpus task; return a TaskResult.

    engine and timeout override the spec.json values when given.
    The ELF path (spec.binary.path) is resolved relative to task_path.
    """
    task_path = Path(task_path).resolve()
    spec_path = task_path / "spec.json"
    toml_path = task_path / "task.toml"

    spec = Aarch64Btor2Spec.from_jsonable(json.loads(spec_path.read_text()))

    if engine is not None or timeout is not None:
        new_analysis = dataclasses.replace(
            spec.analysis,
            engine=engine if engine is not None else spec.analysis.engine,
            timeout=timeout if timeout is not None else spec.analysis.timeout,
        )
        spec = dataclasses.replace(spec, analysis=new_analysis)

    elf_path = (task_path / spec.binary.path).resolve()
    artifact = compile_spec(spec, source_payload=elf_path)

    solver_cls = PAIR.solvers[spec.analysis.engine]
    t0 = time.monotonic()
    raw = solver_cls().dispatch(artifact.flattened, spec.analysis)
    elapsed = time.monotonic() - t0

    task_id = task_path.name
    expected_verdict: str | None = None
    if toml_path.exists():
        task_toml = tomllib.loads(toml_path.read_text())
        task_id = task_toml.get("task", {}).get("id", task_path.name)
        expected_verdict = task_toml.get("expected", {}).get("verdict")

    match: bool | None = None
    if expected_verdict is not None:
        match = raw.verdict == expected_verdict

    return TaskResult(
        task_id=task_id,
        verdict=raw.verdict,
        expected_verdict=expected_verdict,
        match=match,
        elapsed=elapsed,
        engine=raw.engine,
        reason=raw.reason,
    )


def list_tasks() -> list[Path]:
    """Return paths to all corpus seed task directories (sorted)."""
    return sorted(p for p in _SEED_DIR.iterdir() if p.is_dir())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-tasks", action="store_true", help="print all task IDs and exit")
    ap.add_argument("--task", metavar="ID_OR_PATH", help="task ID or directory path")
    ap.add_argument("--engine", help="override engine (e.g. z3-bmc, bitwuzla)")
    ap.add_argument("--timeout", type=float, metavar="SEC", help="override timeout in seconds")
    ap.add_argument("--json", dest="as_json", action="store_true", help="emit JSON result")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.list_tasks:
        for p in list_tasks():
            print(p.name)
        return 0

    if not args.task:
        print("specify --task <id> or --list-tasks", file=sys.stderr)
        return 2

    # Accept either a bare task ID (looked up in seed/) or a path
    task_path = Path(args.task)
    if not task_path.is_dir():
        task_path = _SEED_DIR / args.task
    if not task_path.is_dir():
        print(f"task not found: {args.task}", file=sys.stderr)
        return 2

    result = run_task(task_path, engine=args.engine, timeout=args.timeout)

    if args.as_json:
        print(json.dumps(dataclasses.asdict(result), indent=2))
    else:
        match_str = {True: "PASS", False: "FAIL", None: "?"}[result.match]
        print(
            f"{result.task_id}: {result.verdict}"
            f" (expected={result.expected_verdict or '?'})"
            f" [{match_str}]"
            f" engine={result.engine}"
            f" elapsed={result.elapsed:.3f}s"
            + (f" reason={result.reason!r}" if result.reason else "")
        )

    return 0 if result.match is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["TaskResult", "run_task", "list_tasks"]
