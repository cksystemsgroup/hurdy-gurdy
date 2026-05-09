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


def _question_keys(task: dict[str, Any]) -> list[str]:
    """Ordered list of question ids (q1, q2, ...) for a multi-question
    task; empty for single-question tasks."""
    qs = task.get("questions") or {}
    return sorted(qs.keys(), key=lambda k: int(k.lstrip("q") or "0"))


def _question_view(
    task: dict[str, Any], question_id: str | None
) -> dict[str, Any]:
    """Return a single-question-shaped view of ``task``.

    For ``question_id=None``, returns ``task`` unchanged (legacy
    single-question shape with top-level ``[expected]`` / ``[witness]``).

    For multi-question tasks, materializes a synthetic dict that looks
    like a single-question task to the rest of the matcher: copies
    ``[task]``, then re-keys the chosen ``[questions.qN]`` block's
    ``expected_verdict`` into ``[expected].verdict`` and lifts its
    ``witness`` / ``lift`` sub-tables to the top level. This keeps the
    rest of the matcher unaware of the multi-question shape.
    """
    if question_id is None:
        return task
    qs = task.get("questions") or {}
    if question_id not in qs:
        raise KeyError(
            f"task has no question {question_id!r}; "
            f"available: {sorted(qs.keys())!r}"
        )
    q = qs[question_id]
    view: dict[str, Any] = {"task": dict(task.get("task", {}))}
    view["task"]["id"] = f"{task['task']['id']}#{question_id}"
    view["expected"] = {"verdict": q["expected_verdict"]}
    if "witness" in q:
        view["witness"] = q["witness"]
    if "lift" in q:
        view["lift"] = q["lift"]
    return view


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

    has_legacy = "question" in task
    has_multi = "questions" in task
    if has_legacy and has_multi:
        problems.append(
            "task.toml has both [question] (singular) and [questions.qN] "
            "(multi-question); pick one"
        )
        return problems

    if has_multi:
        keys = _question_keys(task)
        if not keys:
            problems.append("[questions] table is empty")
            return problems
        for i, qid in enumerate(keys, start=1):
            if qid != f"q{i}":
                problems.append(
                    f"question ids must be q1, q2, q3, ... contiguous; "
                    f"got {keys!r}"
                )
                break
        for qid in keys:
            view = _question_view(task, qid)
            problems.extend(_validate_view(view, prefix=f"{qid}: "))
        return problems

    problems.extend(_validate_view(task))
    return problems


def _validate_view(view: dict[str, Any], *, prefix: str = "") -> list[str]:
    """Validate a single-question view (real task or synthesized)."""
    problems: list[str] = []
    verdict = _expected_verdict(view)
    if verdict not in ("reachable", "unreachable", "proved", "unknown"):
        problems.append(f"{prefix}expected.verdict {verdict!r} not in vocabulary")

    witness = _expected_witness(view)
    if verdict == "reachable":
        if witness is None:
            problems.append(f"{prefix}expected.verdict='reachable' requires [witness]")
        elif "bad_pc" not in witness:
            problems.append(f"{prefix}[witness] requires bad_pc when expected.verdict='reachable'")
    else:
        if witness is not None:
            problems.append(
                f"{prefix}[witness] only allowed when expected.verdict='reachable' "
                f"(got {verdict!r})"
            )
    return problems


def match(
    task_dir: Path,
    observed: dict[str, Any],
    *,
    question_id: str | None = None,
) -> Report:
    task = _read_task(task_dir)
    view = _question_view(task, question_id)
    expected = _expected_verdict(view)
    observed_verdict = observed.get("verdict")
    failures: list[str] = []

    # `proved` is strictly stronger than `unreachable` (an inductive
    # invariant rules out violations at every bound), so an LLM that
    # answers `proved` for an `unreachable`-labeled task has produced
    # a correct, sharper claim — not a wrong verdict. Mirrors the
    # same PASS-equivalence used in the §9.10 oracle's compare() and
    # §9.11 framework_oracle's compare(). The reverse direction
    # (observing `unreachable` for a `proved` task) is *not*
    # equivalent: that would be the LLM weakening a claim the
    # benchmark requires it to make.
    verdict_ok = observed_verdict == expected or (
        expected == "unreachable" and observed_verdict == "proved"
    )

    witness_required = expected == "reachable"
    witness_match: bool | None = None

    if not verdict_ok:
        failures.append(
            f"verdict mismatch: expected {expected!r}, observed {observed_verdict!r}"
        )
        return Report(
            task_id=view["task"]["id"],
            expected_verdict=expected,
            observed_verdict=observed_verdict,
            verdict_correct=False,
            witness_required=witness_required,
            witness_match=None,
            failures=failures,
        )

    if witness_required:
        witness_match = _check_witness(view, observed, failures)

    return Report(
        task_id=view["task"]["id"],
        expected_verdict=expected,
        observed_verdict=observed_verdict,
        verdict_correct=True,
        witness_required=witness_required,
        witness_match=witness_match,
        failures=failures,
    )


def match_all(
    task_dir: Path, observed_list: list[dict[str, Any]]
) -> list[Report]:
    """Grade a multi-question task end-to-end.

    For multi-question tasks, ``observed_list`` must have exactly as
    many elements as ``[questions.qN]`` sections, in order. Single-
    question tasks accept ``observed_list`` of length 1 (or just call
    ``match()`` directly).

    Returns one ``Report`` per question. Aggregation (e.g., "task PASSes
    only if every question PASSes") is the harness / oracle's job.
    """
    task = _read_task(task_dir)
    keys = _question_keys(task)
    if not keys:
        # Legacy single-question.
        if len(observed_list) != 1:
            raise ValueError(
                f"single-question task {task_dir.name} expects exactly 1 "
                f"observation, got {len(observed_list)}"
            )
        return [match(task_dir, observed_list[0])]
    if len(observed_list) != len(keys):
        raise ValueError(
            f"multi-question task {task_dir.name} has {len(keys)} questions "
            f"({keys!r}); got {len(observed_list)} observations"
        )
    return [
        match(task_dir, obs, question_id=qid)
        for qid, obs in zip(keys, observed_list)
    ]


def _check_witness(
    view: dict[str, Any], observed: dict[str, Any], failures: list[str]
) -> bool:
    expected = view["witness"]
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
            # TOML bare keys like ``0x40000`` parse as the *string*
            # "0x40000", not an int — accept hex / decimal / int alike.
            addr_int = (
                int(addr, 0) if isinstance(addr, str) else int(addr)
            )
            key = str(addr_int)
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
