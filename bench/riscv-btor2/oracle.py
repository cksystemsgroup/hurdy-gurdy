"""Concrete-execution oracle for the riscv-btor2 benchmark corpus.

Walks the corpus, runs the framework's ``check`` tool on each task
with a default ``RiscvInputBinding`` (no register/memory init, no
havoc), and reports whether the concrete-trace verdict agrees with
the task's pre-registered ``expected.verdict``.

The oracle is solver-free: it only invokes the source interpreter and
the predicate evaluator. It does **not** replace the real bench
matrix — its purpose is to flag tasks whose ground-truth label seems
inconsistent with concrete execution, so they can be reviewed before
LLM runs are recorded against them.

Output:

    PASS  0001-x0-write-dropped         expected=unreachable check=holds
    PASS  0002-bound-sensitive-loop     expected=reachable   check=violated@4
    SKIP  0030-two-callees-mixed        check=inconclusive   (no witness on default inputs)
    FAIL  0007-simple-add-baseline      expected=unreachable check=violated@2

Exit code is 1 if any FAIL is reported; 0 otherwise (SKIPs do not
count as failures since the default binding is one concrete input
out of many).

Usage:

    python bench/riscv-btor2/oracle.py
    python bench/riscv-btor2/oracle.py --task 0001-x0-write-dropped
    python bench/riscv-btor2/oracle.py --max-steps 32
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow `import harness` to find the harness module sibling-adjacent.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Allow `import gurdy.*` to resolve (we don't depend on the package
# being installed).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.core.tools.check import check
from gurdy.pairs.riscv_btor2 import PAIR  # noqa: F401  (registers pair)
from gurdy.pairs.riscv_btor2.source_interp.bindings import RiscvInputBinding
from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec


CORPUS = Path(__file__).resolve().parent / "corpus"


def load_task(task_dir: Path) -> tuple[dict[str, Any], RiscvBtor2Spec, Path]:
    """Read task.toml + spec.json + locate source.elf next to them."""
    try:
        import tomllib  # py311+
    except Exception:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    raw = tomllib.loads((task_dir / "task.toml").read_text())
    spec_obj = json.loads((task_dir / "spec.json").read_text())
    spec = RiscvBtor2Spec.from_jsonable(spec_obj)
    binary = task_dir / spec.binary.path
    return raw, spec, binary


def label_from_check(spec: RiscvBtor2Spec, binary: Path, max_steps: int) -> dict:
    binding = RiscvInputBinding()
    se = check(spec, binding, max_steps, source_payload=binary)
    holds = se.property_result.holds if se.property_result else None
    violations = list(se.property_result.violations) if se.property_result else []
    note = se.property_result.note if se.property_result else ""
    return {
        "holds": holds,
        "violations": violations,
        "note": note,
        "steps_executed": se.steps_executed,
        "halted": se.halted,
    }


def compare(expected_verdict: str, label: dict) -> str:
    """Map (expected, check-result) into PASS / FAIL / SKIP."""
    holds = label["holds"]
    if holds is None:
        return "SKIP"
    if expected_verdict == "unreachable":
        return "PASS" if holds is True else "FAIL"
    if expected_verdict == "reachable":
        # Default-input check: violation gives positive evidence; absence
        # of violation is inconclusive (we just didn't try the right input).
        return "PASS" if holds is False else "SKIP"
    return "SKIP"


def render_row(status: str, task_id: str, expected: str, label: dict) -> str:
    holds = label["holds"]
    violations = label["violations"]
    if holds is True:
        check_str = "holds"
    elif holds is False:
        first = violations[0] if violations else "?"
        check_str = f"violated@{first}"
    else:
        check_str = f"unsupported({label['note']})" if label["note"] else "unknown"
    return f"{status:5s} {task_id:38s} expected={expected:11s} check={check_str}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="riscv-btor2 concrete-execution oracle")
    p.add_argument("--task", help="run only one task by id")
    p.add_argument("--max-steps", type=int, default=64)
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
            raw, spec, binary = load_task(d)
        except Exception as exc:
            row = {"task": d.name, "status": "ERROR", "reason": str(exc)}
            rows.append(row)
            if not args.json:
                print(f"ERROR {d.name:38s} {exc}")
            continue
        expected = raw.get("expected", {}).get("verdict", "?")
        label = label_from_check(spec, binary, args.max_steps)
        status = compare(expected, label)
        if status == "FAIL":
            fail_count += 1
        if args.json:
            rows.append({
                "task": d.name,
                "status": status,
                "expected": expected,
                **label,
            })
        else:
            print(render_row(status, d.name, expected, label))

    if args.json:
        json.dump({"rows": rows, "failures": fail_count}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif fail_count:
        print(f"\n{fail_count} task(s) flagged: expected verdict disagrees with concrete check", file=sys.stderr)

    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
