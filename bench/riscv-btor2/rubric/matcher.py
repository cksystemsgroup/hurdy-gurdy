"""Deterministic matcher for the riscv-btor2 benchmark rubric.

Reads a task's `task.toml` (the expected verdict + witness fingerprint)
and an LLM's emitted answer JSON (see `witness_schema.md`) and
returns a structured grade. Stateless, no LLM calls.

Two entry points:

    python matcher.py <task_dir>
        Self-validate the task: parses task.toml, checks that the
        [witness] table is present iff expected.verdict == "reachable",
        checks that bad_pc field is set when needed. Useful as CI.

    python matcher.py <task_dir> --observed <answer.json>
        Grade the LLM's answer. Prints a JSON report.

Usable as a library: `match(task_dir: Path, observed: dict) -> Report`.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


U64_MASK = (1 << 64) - 1


@dataclass
class Report:
    task_id: str
    expected_verdict: str
    observed_verdict: str | None
    verdict_correct: bool
    witness_required: bool
    witness_match: bool | None  # None when verdict didn't even match
    failures: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        return asdict(self)


def _u64(x: int) -> int:
    return x & U64_MASK


def _read_task(task_dir: Path) -> dict[str, Any]:
    with (task_dir / "task.toml").open("rb") as f:
        return tomllib.load(f)


def _expected_verdict(task: dict[str, Any]) -> str:
    return task["expected"]["verdict"]


def _expected_witness(task: dict[str, Any]) -> dict[str, Any] | None:
    return task.get("witness")


def validate_task(task_dir: Path) -> list[str]:
    """Return a list of structural problems with the task, [] if OK."""
    problems: list[str] = []
    try:
        task = _read_task(task_dir)
    except Exception as e:
        return [f"task.toml unreadable: {e}"]

    verdict = _expected_verdict(task)
    if verdict not in ("reachable", "unreachable", "proved", "unknown"):
        problems.append(f"expected.verdict {verdict!r} not in vocabulary")

    witness = _expected_witness(task)
    if verdict == "reachable":
        if witness is None:
            problems.append("expected.verdict='reachable' requires [witness]")
        elif "bad_pc" not in witness:
            problems.append("[witness] requires bad_pc when expected.verdict='reachable'")
    else:
        if witness is not None:
            problems.append(f"[witness] only allowed when expected.verdict='reachable' (got {verdict!r})")

    return problems


def match(task_dir: Path, observed: dict[str, Any]) -> Report:
    task = _read_task(task_dir)
    expected = _expected_verdict(task)
    observed_verdict = observed.get("verdict")
    failures: list[str] = []

    verdict_ok = observed_verdict == expected

    witness_required = expected == "reachable"
    witness_match: bool | None = None

    if not verdict_ok:
        failures.append(
            f"verdict mismatch: expected {expected!r}, observed {observed_verdict!r}"
        )
        return Report(
            task_id=task["task"]["id"],
            expected_verdict=expected,
            observed_verdict=observed_verdict,
            verdict_correct=False,
            witness_required=witness_required,
            witness_match=None,
            failures=failures,
        )

    if witness_required:
        witness_match = _check_witness(task, observed, failures)

    return Report(
        task_id=task["task"]["id"],
        expected_verdict=expected,
        observed_verdict=observed_verdict,
        verdict_correct=True,
        witness_required=witness_required,
        witness_match=witness_match,
        failures=failures,
    )


def _check_witness(
    task: dict[str, Any], observed: dict[str, Any], failures: list[str]
) -> bool:
    expected = task["witness"]
    obs = observed.get("witness")
    if obs is None:
        failures.append("witness fingerprint required but observed.witness is null")
        return False

    bad_pc = expected["bad_pc"]
    if obs.get("bad_pc") != bad_pc:
        failures.append(
            f"witness.bad_pc mismatch: expected {bad_pc}, observed {obs.get('bad_pc')}"
        )
        return False

    if "halted_step" in expected:
        tol = int(expected.get("halted_step_tolerance", 0))
        exp_step = int(expected["halted_step"])
        obs_step = obs.get("anchor_step")
        if obs_step is None:
            failures.append("witness.anchor_step required (halted_step set in task)")
            return False
        if abs(int(obs_step) - exp_step) > tol:
            failures.append(
                f"witness.anchor_step {obs_step} not within {tol} of expected {exp_step}"
            )
            return False

    if "final_regs" in expected:
        obs_regs = obs.get("final_regs", {}) or {}
        for reg, want in expected["final_regs"].items():
            reg_n = int(reg)
            key = str(reg_n)
            if key not in obs_regs:
                failures.append(f"witness.final_regs[{reg_n}] not reported")
                return False
            got = _u64(int(obs_regs[key], 0) if isinstance(obs_regs[key], str) else int(obs_regs[key]))
            if got != _u64(int(want)):
                failures.append(
                    f"witness.final_regs[{reg_n}] mismatch: expected {want}, observed {obs_regs[key]}"
                )
                return False

    if "executed_pcs" in expected:
        obs_pcs = set(int(p) for p in obs.get("executed_pcs", []) or [])
        for pc in expected["executed_pcs"]:
            if int(pc) not in obs_pcs:
                failures.append(f"witness.executed_pcs missing {pc}")
                return False

    if "memory" in expected:
        obs_mem = obs.get("memory", {}) or {}
        for addr, spec in expected["memory"].items():
            key = str(int(addr))
            if key not in obs_mem:
                failures.append(f"witness.memory[{addr}] not reported")
                return False
            got = obs_mem[key]
            if int(got.get("width", -1)) != int(spec["width"]):
                failures.append(f"witness.memory[{addr}] width mismatch")
                return False
            if int(got.get("value"), 0) != int(spec["value"]):
                failures.append(f"witness.memory[{addr}] value mismatch")
                return False

    return True


def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("task_dir", type=Path)
    p.add_argument("--observed", type=Path, default=None,
                   help="LLM output JSON; if omitted, only self-validate the task")
    args = p.parse_args(argv[1:])

    problems = validate_task(args.task_dir)
    if problems:
        for problem in problems:
            print(f"task error: {problem}", file=sys.stderr)
        return 2

    if args.observed is None:
        print(f"task {args.task_dir.name}: schema OK", file=sys.stderr)
        return 0

    with args.observed.open() as f:
        observed = json.load(f)
    report = match(args.task_dir, observed)
    print(json.dumps(report.to_jsonable(), indent=2))
    return 0 if report.verdict_correct and (report.witness_match is not False) else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
