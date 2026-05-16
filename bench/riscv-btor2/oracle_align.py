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
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Allow `import gurdy.*` without depending on installed package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.dispatch import dispatch
from gurdy.pairs.riscv_btor2 import PAIR  # noqa: F401  (registers pair)
from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec


CORPUS = Path(__file__).resolve().parent / "corpus"


# ---------------------------------------------------------------------------
# Task loading (mirrors oracle.py + framework_oracle.py)
# ---------------------------------------------------------------------------


def _load_spec_obj(task_dir: Path, spec_filename: str) -> RiscvBtor2Spec:
    """Read a single spec.json and rewrite ``binary.path`` to an absolute
    path so ``compile_spec`` / ``dispatch`` resolve the ELF correctly
    independent of the caller's cwd. Mirrors ``framework_oracle.py``."""
    p = task_dir / spec_filename
    if not p.exists():
        p = task_dir / "spec.json"
    spec_obj = json.loads(p.read_text())
    fields = spec_obj.setdefault("fields", {})
    bin_field = fields.setdefault("binary", {})
    rel = bin_field.get("path", "source.elf")
    bin_field["path"] = str((task_dir / rel).resolve())
    return RiscvBtor2Spec.from_jsonable(spec_obj)


def _iter_questions(
    task_dir: Path,
) -> list[tuple[str | None, str, RiscvBtor2Spec]]:
    """Yield ``(question_id, expected_verdict, spec)`` per question.
    Mirrors ``framework_oracle.iter_questions``."""
    try:
        import tomllib  # py311+
    except Exception:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    raw = tomllib.loads((task_dir / "task.toml").read_text())
    if "questions" in raw:
        out: list[tuple[str | None, str, RiscvBtor2Spec]] = []
        keys = sorted(
            raw["questions"].keys(), key=lambda k: int(k.lstrip("q") or "0")
        )
        for qid in keys:
            q = raw["questions"][qid]
            spec_filename = q.get("spec_file") or f"spec.{qid}.json"
            out.append((
                qid,
                q.get("expected_verdict", "?"),
                _load_spec_obj(task_dir, spec_filename),
            ))
        return out
    return [(
        None,
        raw.get("expected", {}).get("verdict", "?"),
        _load_spec_obj(task_dir, "spec.json"),
    )]


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
    - ``raw_verdict``: solver-side raw verdict for context.
    - ``engine``: which solver produced it.
    - ``elapsed``: dispatch wall time in seconds.
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
    raw_verdict: str = ""
    engine: str = ""
    elapsed: float = 0.0
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
            "raw_verdict": self.raw_verdict,
            "engine": self.engine,
            "elapsed": self.elapsed,
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


def _run_one_question(
    task_id: str,
    expected: str,
    spec: RiscvBtor2Spec,
) -> AlignResult:
    """Compile + dispatch one (task, question) cell; classify the
    raw verdict. **No alignment yet — that's P1.3.**

    Verdict mapping for this iteration:
    - ``reachable``: a witness exists. SKIP for now with note
      'P1.3 pending: align this witness'. P1.3 will replace this
      branch with replay_witness + align_traces.
    - ``unreachable`` / ``proved`` / ``unknown``: SKIP. Alignment
      doesn't apply without a concrete trajectory.
    - ``error`` or unexpected: ERROR.
    """
    t0 = time.monotonic()
    try:
        artifact = compile_spec(spec)
        raw = dispatch(artifact, spec.analysis)
    except Exception as exc:
        return AlignResult(
            task=task_id,
            expected=expected,
            status="ERROR",
            note=f"compile/dispatch: {type(exc).__name__}: {exc}",
            elapsed=time.monotonic() - t0,
        )

    elapsed = time.monotonic() - t0
    verdict = raw.verdict
    engine = raw.engine or "?"

    if verdict == "reachable":
        # A witness is available; replay + align come in P1.3.
        return AlignResult(
            task=task_id,
            expected=expected,
            status="SKIP",
            align_kind="N/A",
            raw_verdict=verdict,
            engine=engine,
            elapsed=elapsed,
            note="P1.3 pending: align this witness",
        )
    if verdict in ("unreachable", "proved", "unknown"):
        return AlignResult(
            task=task_id,
            expected=expected,
            status="SKIP",
            align_kind="N/A",
            raw_verdict=verdict,
            engine=engine,
            elapsed=elapsed,
            note=f"verdict={verdict}",
        )
    return AlignResult(
        task=task_id,
        expected=expected,
        status="ERROR",
        raw_verdict=verdict,
        engine=engine,
        elapsed=elapsed,
        note=f"unexpected verdict: {verdict!r} ({raw.reason or ''})",
    )


def run_one(task_dir: Path, *, engine: str, max_steps: int) -> list[AlignResult]:
    """Run the alignment oracle on every question in one task.

    Returns one ``AlignResult`` per question. Single-question tasks
    return a length-1 list. The ``engine`` and ``max_steps`` parameters
    are forwarded to the per-question runner via ``spec.analysis`` (the
    spec's own analysis directive wins; we honor it).
    """
    try:
        questions = _iter_questions(task_dir)
    except Exception as exc:
        return [AlignResult(
            task=task_dir.name,
            expected="?",
            status="ERROR",
            note=f"load_task: {type(exc).__name__}: {exc}",
        )]
    out: list[AlignResult] = []
    for qid, expected, spec in questions:
        tid = task_dir.name if qid is None else f"{task_dir.name}::{qid}"
        out.append(_run_one_question(tid, expected, spec))
    return out


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
        for r in run_one(d, engine=args.engine, max_steps=args.max_steps):
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
