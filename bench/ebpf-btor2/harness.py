"""ebpf-btor2 benchmark harness — P8.

Calls ``check()`` on each corpus task and reports PASS / FAIL / SKIP.

PASS  — solver returned the expected verdict.
FAIL  — solver returned a definite but unexpected verdict.
SKIP  — solver returned ``unknown`` or ``error`` (incomplete result).

Usage:
    python bench/ebpf-btor2/harness.py
    python bench/ebpf-btor2/harness.py --list
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Sequence

from gurdy.pairs.ebpf_btor2.spec import (
    AnalysisDirective,
    EbpfBtor2Spec,
    EbpfProgramRef,
    EbpfScope,
    Property,
)
from gurdy.pairs.ebpf_btor2.solvers import check


# ---------------------------------------------------------------------------
# Corpus task definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusTask:
    task_id: str
    spec: EbpfBtor2Spec
    bytecode: bytes
    expected_verdict: str  # "reachable" | "unreachable"


# ---------------------------------------------------------------------------
# Seed corpus
# ---------------------------------------------------------------------------

# r0 += 1  (ALU64 ADD K, dst=r0, imm=1)
# EXIT
_R0_ADD1_EXIT = bytes([
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 += 1
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# EXIT only
_EXIT_ONLY = bytes([
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 ^= r0  (ALU64 XOR X, dst=r0, src=r0 — always zeroes r0)
# EXIT
_R0_XOR_SELF_EXIT = bytes([
    0xaf, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 ^= r0
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 += 1; r0 += 1  (double add-immediate-1)
# EXIT
_R0_ADD1_ADD1_EXIT = bytes([
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 += 1
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 += 1
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# JA -1: unconditional jump to self (off=-1 → target = insn_idx+1-1 = insn_idx).
# Infinite loop; EXIT is never reached within any finite BMC bound.
_JA_SELF_LOOP = bytes([
    0x05, 0x00, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00,  # JA -1 (self-loop)
])

# r0 += 1; JEQ r0, 99, +1; EXIT
# JEQ not taken when r0 ≠ 99; falls through to EXIT. Witness: initial r0=1.
_ADD_JEQ_SKIP_EXIT = bytes([
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 += 1
    0x15, 0x00, 0x01, 0x00, 0x63, 0x00, 0x00, 0x00,  # JEQ r0, 99, +1
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# JEQ r0, 0, +1; r0 += 1; EXIT
# JEQ taken (r0==0) skips the add; EXIT with r0=0. Witness: initial r0=0.
_JEQ_TAKEN_SKIP_ADD = bytes([
    0x15, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JEQ r0, 0, +1
    0x07, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 += 1
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])


def _spec(path: str, expression: str, max_insns: int = 8) -> EbpfBtor2Spec:
    return EbpfBtor2Spec(
        program=EbpfProgramRef(path=path),
        scope=EbpfScope(max_insns=max_insns),
        property=Property(expression=expression),
        analysis=AnalysisDirective(engine="z3-bmc"),
    )


CORPUS: list[CorpusTask] = [
    # P6 seed: r0 += 1; EXIT. Witness: initial r0=0 → r0=1 at halt.
    CorpusTask(
        task_id="seed/r0_add1_exit",
        spec=_spec("seed/r0_add1_exit", "r0 == 1", max_insns=4),
        bytecode=_R0_ADD1_EXIT,
        expected_verdict="reachable",
    ),
    # P7 additions:
    # EXIT-only: exit_reached fires as soon as program halts.
    CorpusTask(
        task_id="seed/exit_only_exit_reached",
        spec=_spec("seed/exit_only_exit_reached", "exit_reached", max_insns=2),
        bytecode=_EXIT_ONLY,
        expected_verdict="reachable",
    ),
    # XOR-self zeroes r0 unconditionally; property r0==0 always fires at halt.
    CorpusTask(
        task_id="seed/r0_xor_self_exit_r0_eq_0",
        spec=_spec("seed/r0_xor_self_exit_r0_eq_0", "r0 == 0", max_insns=4),
        bytecode=_R0_XOR_SELF_EXIT,
        expected_verdict="reachable",
    ),
    # XOR-self always zeroes r0; r0==1 can never fire. Tests unreachable path.
    CorpusTask(
        task_id="seed/r0_xor_self_exit_r0_eq_1_unreachable",
        spec=_spec("seed/r0_xor_self_exit_r0_eq_1_unreachable", "r0 == 1", max_insns=4),
        bytecode=_R0_XOR_SELF_EXIT,
        expected_verdict="unreachable",
    ),
    # Double-add: witness initial r0=0 → r0=2 at halt; property r0==2 fires.
    CorpusTask(
        task_id="seed/r0_add1_add1_exit",
        spec=_spec("seed/r0_add1_add1_exit", "r0 == 2", max_insns=6),
        bytecode=_R0_ADD1_ADD1_EXIT,
        expected_verdict="reachable",
    ),
    # P8 additions — JMP layer:
    # JA -1 self-loop: EXIT is structurally unreachable within any finite bound.
    CorpusTask(
        task_id="seed/ja_self_loop_unreachable",
        spec=_spec("seed/ja_self_loop_unreachable", "exit_reached", max_insns=4),
        bytecode=_JA_SELF_LOOP,
        expected_verdict="unreachable",
    ),
    # JEQ not-taken: r0 += 1; JEQ r0, 99, +1; EXIT.
    # Witness: initial r0=1 → r0=2, JEQ not taken (2 ≠ 99), EXIT with r0=2.
    CorpusTask(
        task_id="seed/add_jeq_skip_exit_r0_eq_2",
        spec=_spec("seed/add_jeq_skip_exit_r0_eq_2", "r0 == 2", max_insns=6),
        bytecode=_ADD_JEQ_SKIP_EXIT,
        expected_verdict="reachable",
    ),
    # JEQ taken: JEQ r0, 0, +1 skips the add when r0==0; EXIT with r0=0.
    # Witness: initial r0=0 → JEQ taken, add skipped, EXIT with r0=0.
    CorpusTask(
        task_id="seed/jeq_taken_skip_add_r0_eq_0",
        spec=_spec("seed/jeq_taken_skip_add_r0_eq_0", "r0 == 0", max_insns=6),
        bytecode=_JEQ_TAKEN_SKIP_ADD,
        expected_verdict="reachable",
    ),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_task(task: CorpusTask) -> str:
    t0 = time.monotonic()
    result = check(task.spec, task.bytecode)
    elapsed = time.monotonic() - t0

    if result.verdict in ("unknown", "error"):
        status = "SKIP"
        detail = result.reason or result.verdict
    elif result.verdict == task.expected_verdict:
        status = "PASS"
        detail = result.verdict
    else:
        status = "FAIL"
        detail = f"got {result.verdict!r}, expected {task.expected_verdict!r}"

    print(f"{status}  {task.task_id}  ({elapsed:.3f}s)  {detail}")
    return status


def run_corpus(tasks: Sequence[CorpusTask] = CORPUS) -> int:
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for task in tasks:
        status = run_task(task)
        counts[status] += 1
    print(
        f"\nTotal: {counts['PASS']} PASS / {counts['FAIL']} FAIL"
        f" / {counts['SKIP']} SKIP"
    )
    return 0 if counts["FAIL"] == 0 else 1


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="ebpf-btor2 benchmark harness")
    p.add_argument("--list", action="store_true", help="list corpus task IDs and exit")
    args = p.parse_args()

    if args.list:
        for task in CORPUS:
            print(task.task_id)
        return 0
    return run_corpus()


if __name__ == "__main__":
    sys.exit(main())
