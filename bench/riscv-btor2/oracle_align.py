"""Primary trace-alignment oracle for the riscv-btor2 benchmark corpus.

For every task whose dispatch produces a `reachable` witness, walks the
source interpreter and the reasoning interpreter in lock-step (via
`replay_witness` + `align_traces`) and reports whether the two traces
agree on the projected observables.

This oracle operationalises ``V2_BOOTSTRAP.md`` §4 — the alignment
contract that defines translator correctness. The framework primitives
(``gurdy.core.interp.align.align_traces`` +
``gurdy.pairs.riscv_btor2.lift.replayer.replay_witness``) already exist;
this file wires them into a per-task bench-side runner that complements
``framework_oracle.py`` (verdict-only) and ``oracle_cross.py`` (engine
agreement).

Status: **SHELL (P1.1)**. Argument parsing, task discovery, and the
PASS/SKIP/FAIL output skeleton are real. The compile / dispatch /
replay / align pipeline is stubbed and returns ``SKIP(stub)``. P1.2 and
P1.3 wire the framework calls.

Output:

    PASS  0001-x0-write-dropped         expected=unreachable align=N/A     (no witness)
    PASS  0002-bound-sensitive-loop     expected=reachable   align=ok      (steps=12, fields=48)
    SKIP  0030-two-callees-mixed        expected=reachable   align=N/A     (verdict=unknown)
    FAIL  0017-loop-witness             expected=reachable   align=diverge@step=4 label=pc

Exit code: 1 if any FAIL is reported; 0 otherwise. SKIP rows are not
failures.

Usage:

    python bench/riscv-btor2/oracle_align.py
    python bench/riscv-btor2/oracle_align.py --task 0002-bound-sensitive-loop
    python bench/riscv-btor2/oracle_align.py --engine z3-bmc
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Allow `import gurdy.*` without depending on installed package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.pairs.riscv_btor2 import PAIR  # noqa: F401  (registers pair)
from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec


CORPUS = Path(__file__).resolve().parent / "corpus"


# ---------------------------------------------------------------------------
# Task loading (mirrors oracle.py + framework_oracle.py)
# ---------------------------------------------------------------------------


def load_task(task_dir: Path) -> tuple[dict[str, Any], RiscvBtor2Spec, Path]:
    """Read task.toml + spec.json + locate source.elf."""
    try:
        import tomllib  # py311+
    except Exception:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    raw = tomllib.loads((task_dir / "task.toml").read_text())
    spec_obj = json.loads((task_dir / "spec.json").read_text())
    spec = RiscvBtor2Spec.from_jsonable(spec_obj)
    binary = task_dir / spec.binary.path
    return raw, spec, binary


# ---------------------------------------------------------------------------
# Per-task align result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlignResult:
    """Outcome of running the alignment oracle on a single task.

    - ``status``: PASS / SKIP / FAIL / ERROR.
    - ``align_kind``: 'ok' | 'diverge' | 'N/A' (only meaningful when
      a witness was produced and aligned).
    - ``divergence_step`` / ``divergence_label``: populated when
      ``align_kind == 'diverge'``.
    - ``steps_checked`` / ``fields_checked``: from the CrossCheckReport.
    - ``note``: free-text reason for SKIP / ERROR.
    """

    task: str
    expected: str
    status: str
    align_kind: str = "N/A"
    divergence_step: int | None = None
    divergence_label: str | None = None
    steps_checked: int = 0
    fields_checked: int = 0
    note: str = ""

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "expected": self.expected,
            "status": self.status,
            "align_kind": self.align_kind,
            "divergence_step": self.divergence_step,
            "divergence_label": self.divergence_label,
            "steps_checked": self.steps_checked,
            "fields_checked": self.fields_checked,
            "note": self.note,
        }


def render_row(r: AlignResult) -> str:
    align_str: str
    if r.align_kind == "ok":
        align_str = f"ok      (steps={r.steps_checked}, fields={r.fields_checked})"
    elif r.align_kind == "diverge":
        align_str = (
            f"diverge@step={r.divergence_step} "
            f"label={r.divergence_label or '?'}"
        )
    else:
        align_str = f"N/A     ({r.note})" if r.note else "N/A"
    return f"{r.status:5s} {r.task:38s} expected={r.expected:11s} align={align_str}"


# ---------------------------------------------------------------------------
# Per-task runner — STUB at P1.1
# ---------------------------------------------------------------------------


def run_one(task_dir: Path, *, engine: str, max_steps: int) -> AlignResult:
    """Run the alignment oracle on one task.

    P1.1 stub: returns SKIP with note 'stub: P1.2 not yet implemented'.

    P1.2 will: load spec/binary, call compile + dispatch (engine),
    classify verdict, branch on reachable -> replay+align,
    unreachable/proved/unknown -> SKIP(N/A).

    P1.3 will: invoke replay_witness + align_traces; map agreement
    -> align_kind='ok', divergence -> align_kind='diverge' with step
    + label.
    """
    try:
        raw, spec, binary = load_task(task_dir)
    except Exception as exc:
        return AlignResult(
            task=task_dir.name,
            expected="?",
            status="ERROR",
            note=f"load_task: {type(exc).__name__}: {exc}",
        )
    expected = raw.get("expected", {}).get("verdict", "?")
    return AlignResult(
        task=task_dir.name,
        expected=expected,
        status="SKIP",
        note="stub: P1.2 not yet implemented",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="riscv-btor2 primary trace-alignment oracle"
    )
    p.add_argument("--task", help="run only one task by id (substring match)")
    p.add_argument("--max-steps", type=int, default=64)
    p.add_argument(
        "--engine",
        default="z3-bmc",
        help=(
            "solver engine; per-task `analysis` directive overrides this "
            "where present (default: z3-bmc)"
        ),
    )
    p.add_argument(
        "--corpus",
        default=str(CORPUS),
        help="corpus directory (default: bench/riscv-btor2/corpus)",
    )
    p.add_argument(
        "--max-tasks",
        type=int,
        default=5,
        help=(
            "RAM-safety cap: limit per-invocation task count "
            "(see V2_AGENT_LOOP.md §4). Default 5."
        ),
    )
    p.add_argument("--json", action="store_true", help="emit JSON")
    args = p.parse_args(argv)

    corpus = Path(args.corpus)
    if not corpus.is_dir():
        print(f"corpus not found: {corpus}", file=sys.stderr)
        return 2
    task_dirs = sorted(
        d
        for d in corpus.iterdir()
        if d.is_dir() and (d / "task.toml").exists()
    )
    if args.task:
        task_dirs = [d for d in task_dirs if args.task in d.name]
        if not task_dirs:
            print(f"no task matching {args.task!r}", file=sys.stderr)
            return 2
    if len(task_dirs) > args.max_tasks:
        print(
            f"{len(task_dirs)} matching tasks; --max-tasks={args.max_tasks} "
            f"caps this run; pass --max-tasks N to raise (RAM safety)",
            file=sys.stderr,
        )
        task_dirs = task_dirs[: args.max_tasks]

    results: list[AlignResult] = []
    fail_count = 0
    for d in task_dirs:
        r = run_one(d, engine=args.engine, max_steps=args.max_steps)
        results.append(r)
        if r.status == "FAIL":
            fail_count += 1
        if not args.json:
            print(render_row(r))

    if args.json:
        json.dump(
            {"rows": [r.to_jsonable() for r in results], "failures": fail_count},
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    elif fail_count:
        print(
            f"\n{fail_count} task(s) failed alignment "
            f"(translator-vs-interpreters divergence)",
            file=sys.stderr,
        )

    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
