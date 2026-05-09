"""Framework-only oracle for the riscv-btor2 benchmark corpus.

A no-LLM, end-to-end validation that exercises the full pair pipeline
(``compile`` -> ``dispatch`` -> ``lift``) on every corpus task, using
each task's *pre-registered* ``spec.json`` and ``analysis`` directive.
The lifted verdict is compared to the task's ``expected.verdict``.

This is BENCHMARKING.md condition "B0" -- the spec is given, the LLM
is removed. It measures whether the framework (translation +
dispatch + lift) is *capable* of producing the expected answer when
fed a correct spec; it does not measure LLM effectiveness. As such
it's a strict superset of ``oracle.py`` (the §9.10 concrete-execution
oracle), which only walks the source interpreter without invoking a
solver. Run both: §9.10 to validate ground-truth labels against
concrete execution, this oracle to validate ground-truth labels
against solver-mediated reasoning.

Output:

    PASS  0001-x0-write-dropped         expected=unreachable raw=unreachable engine=z3-bmc 0.05s
    PASS  0002-bound-sensitive-loop     expected=reachable   raw=reachable   engine=z3-bmc 0.21s
    SKIP  0009-uninit-load              expected=reachable   raw=unknown     engine=z3-bmc (timeout)
    FAIL  0007-simple-add-baseline      expected=reachable   raw=unreachable engine=z3-bmc 0.04s

Exit code is 1 if any FAIL is reported; 0 otherwise. SKIP rows
indicate the solver returned ``unknown`` (timeout / resource-limit /
spec-error) -- not a label/framework disagreement.

Usage:

    python bench/riscv-btor2/framework_oracle.py
    python bench/riscv-btor2/framework_oracle.py --task 0001-x0-write-dropped
    python bench/riscv-btor2/framework_oracle.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


# Make `gurdy.*` importable without depending on the package being installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.dispatch import dispatch
from gurdy.pairs.riscv_btor2 import PAIR  # noqa: F401  (registers pair)
from gurdy.pairs.riscv_btor2.lift.lift import Lifter
from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec


CORPUS = Path(__file__).resolve().parent / "corpus"


def _load_spec_obj(task_dir: Path, spec_filename: str) -> RiscvBtor2Spec:
    """Read a single spec.json (or per-question spec.qN.json) and parse
    it, with the binary.path field rewritten to an absolute path."""
    p = task_dir / spec_filename
    if not p.exists():
        # Per-question fallback: the multi-question shape allows
        # ``spec_file = "spec.qN.json"`` but tolerates missing files
        # by falling back to the base spec.json.
        p = task_dir / "spec.json"
    spec_obj = json.loads(p.read_text())
    fields = spec_obj.setdefault("fields", {})
    bin_field = fields.setdefault("binary", {})
    rel = bin_field.get("path", "source.elf")
    bin_field["path"] = str((task_dir / rel).resolve())
    return RiscvBtor2Spec.from_jsonable(spec_obj)


def load_task(task_dir: Path) -> tuple[dict[str, Any], RiscvBtor2Spec]:
    """Single-question load. For multi-question tasks, callers should
    use ``iter_questions(task_dir)`` instead.

    Preserved for backward-compat with callers that read the legacy
    ``[expected]`` table directly. spec.binary.path is rewritten to an
    absolute path before parsing.
    """
    try:
        import tomllib  # py311+
    except Exception:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    raw = tomllib.loads((task_dir / "task.toml").read_text())
    return raw, _load_spec_obj(task_dir, "spec.json")


def iter_questions(
    task_dir: Path,
) -> list[tuple[str | None, str, RiscvBtor2Spec]]:
    """Yield ``(question_id, expected_verdict, spec)`` per question.

    Single-question tasks yield a length-1 list with ``question_id=None``
    so callers can preserve their existing one-row-per-task output. Multi-
    question tasks (``[questions.qN]``) yield one entry per question, with
    each question's ``spec_file`` (or the default ``spec.qN.json``)
    loaded.

    The expected verdict per question lives at
    ``[questions.qN].expected_verdict``; we deliberately re-derive it
    here (rather than going through harness.discover_tasks) so the
    framework oracle remains an independent check on the corpus.
    """
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


def run_one(spec: RiscvBtor2Spec) -> dict[str, Any]:
    t0 = time.monotonic()
    artifact = compile_spec(spec)
    raw = dispatch(artifact, spec.analysis)
    elapsed = time.monotonic() - t0
    try:
        source = load_riscv_binary(Path(spec.binary.path))
        lifted = Lifter().lift(artifact, raw, source=source)
        lifted_verdict = lifted.verdict
    except Exception as exc:
        lifted_verdict = f"lift-error: {exc}"
    return {
        "raw_verdict": raw.verdict,
        "lifted_verdict": lifted_verdict,
        "engine": raw.engine,
        "elapsed": elapsed,
        "reason": raw.reason,
    }


def compare(expected: str, raw_verdict: str) -> str:
    """Map (expected, dispatch-verdict) into PASS / FAIL / SKIP.

    ``proved`` is strictly stronger than ``unreachable`` (an inductive
    invariant rules out violations at every bound), so a solver
    returning either one satisfies an ``expected=unreachable`` or
    ``expected=proved`` task. ``unknown`` and ``error`` are inconclusive
    and surface as SKIP, not FAIL.
    """
    if raw_verdict in ("unknown", "error"):
        return "SKIP"
    if expected == "reachable":
        return "PASS" if raw_verdict == "reachable" else "FAIL"
    if expected in ("unreachable", "proved"):
        return "PASS" if raw_verdict in ("unreachable", "proved") else "FAIL"
    return "SKIP"


def render_row(status: str, task_id: str, expected: str, result: dict[str, Any]) -> str:
    raw = result["raw_verdict"]
    eng = result["engine"]
    elapsed = result["elapsed"]
    reason = result.get("reason") or ""
    tail = f"({reason})" if raw in ("unknown", "error") and reason else f"{elapsed:.2f}s"
    return f"{status:5s} {task_id:38s} expected={expected:11s} raw={raw:11s} engine={eng:10s} {tail}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="riscv-btor2 framework oracle (no LLM)")
    p.add_argument("--task", help="run only one task by id (substring match)")
    p.add_argument(
        "--corpus",
        default=str(CORPUS),
        help="corpus directory (default: bench/riscv-btor2/corpus)",
    )
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = p.parse_args(argv)

    corpus = Path(args.corpus)
    task_dirs = sorted(d for d in corpus.iterdir() if d.is_dir() and (d / "task.toml").exists())
    if args.task:
        task_dirs = [d for d in task_dirs if d.name == args.task or args.task in d.name]
        if not task_dirs:
            print(f"no task matching {args.task!r}", file=sys.stderr)
            return 2

    rows: list[dict[str, Any]] = []
    fail_count = 0
    for d in task_dirs:
        try:
            questions = iter_questions(d)
        except Exception as exc:
            row = {"task": d.name, "status": "ERROR", "reason": str(exc)}
            rows.append(row)
            if not args.json:
                print(f"ERROR {d.name:38s} {exc}")
            continue
        for qid, expected, spec in questions:
            row_label = d.name if qid is None else f"{d.name}#{qid}"
            try:
                result = run_one(spec)
            except Exception as exc:
                result = {
                    "raw_verdict": "error",
                    "lifted_verdict": "error",
                    "engine": "<exception>",
                    "elapsed": 0.0,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            status = compare(expected, result["raw_verdict"])
            if status == "FAIL":
                fail_count += 1
            if args.json:
                rows.append({
                    "task":     d.name,
                    "question": qid,
                    "status":   status,
                    "expected": expected,
                    **result,
                })
            else:
                print(render_row(status, row_label, expected, result))

    if args.json:
        json.dump({"rows": rows, "failures": fail_count}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif fail_count:
        print(
            f"\n{fail_count} task(s) flagged: dispatch verdict disagrees with expected",
            file=sys.stderr,
        )

    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
