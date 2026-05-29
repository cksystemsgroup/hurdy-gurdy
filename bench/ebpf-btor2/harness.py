"""ebpf-btor2 benchmark harness — P9.

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

# r1 += 1 (ADD K, dst=r1); r0 += r1 (ADD X, dst=r0, src=r1); EXIT
# Multi-register chain: with initial r0=0, r1=0 → r1=1, r0=0+1=1.
_R1_ADD1_R0_ADD_R1_EXIT = bytes([
    0x07, 0x01, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r1 += 1
    0x0f, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 += r1  (ADD X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r2 *= r3 (MUL X, dst=r2, src=r3); EXIT
# Witness: r2=2, r3=3 → r2=6.
_R2_MUL_R3_EXIT = bytes([
    0x2f, 0x32, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r2 *= r3  (MUL X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 -= r0 (SUB X self — always zeroes r0); EXIT
_R0_SUB_SELF_EXIT = bytes([
    0x1f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 -= r0  (SUB X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 /= 8  (ALU64 DIV K, dst=r0, imm=8); EXIT
# Witness: initial r0=24 → 24//8=3.
_R0_DIV8_EXIT = bytes([
    0x37, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00,  # r0 /= 8  (DIV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 |= 0x80  (ALU64 OR K, dst=r0, imm=128); EXIT
# Witness: initial r0=0 → 0|0x80=128.
_R0_OR_0X80_EXIT = bytes([
    0x47, 0x00, 0x00, 0x00, 0x80, 0x00, 0x00, 0x00,  # r0 |= 0x80  (OR K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 &= 0xf  (ALU64 AND K, dst=r0, imm=15); EXIT
# Witness: initial r0=15 → 15&0xf=15.
_R0_AND_0XF_EXIT = bytes([
    0x57, 0x00, 0x00, 0x00, 0x0f, 0x00, 0x00, 0x00,  # r0 &= 0xf  (AND K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 %= 3  (ALU64 MOD K, dst=r0, imm=3); EXIT
# Witness: initial r0=2 → 2%3=2.
_R0_MOD3_EXIT = bytes([
    0x97, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00,  # r0 %= 3  (MOD K)
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
    # P9 additions — multi-register ALU:
    # ADD K to r1, then ADD X r1 into r0. Exercises src_reg field and two
    # distinct state variables. Witness: initial r0=0, r1=0 → r1=1, r0=1.
    CorpusTask(
        task_id="seed/r1_add1_r0_add_r1_exit_r0_eq_1",
        spec=_spec("seed/r1_add1_r0_add_r1_exit_r0_eq_1", "r0 == 1", max_insns=6),
        bytecode=_R1_ADD1_R0_ADD_R1_EXIT,
        expected_verdict="reachable",
    ),
    # MUL X between two free registers. Witness: r2=2, r3=3 → r2=6.
    CorpusTask(
        task_id="seed/r2_mul_r3_exit_r2_eq_6",
        spec=_spec("seed/r2_mul_r3_exit_r2_eq_6", "r2 == 6", max_insns=4),
        bytecode=_R2_MUL_R3_EXIT,
        expected_verdict="reachable",
    ),
    # SUB X self-zeroes r0 (r0 -= r0 = 0); r0==1 can never fire.
    CorpusTask(
        task_id="seed/r0_sub_self_exit_r0_eq_1_unreachable",
        spec=_spec("seed/r0_sub_self_exit_r0_eq_1_unreachable", "r0 == 1", max_insns=4),
        bytecode=_R0_SUB_SELF_EXIT,
        expected_verdict="unreachable",
    ),
    # P10 additions — DIV/OR/AND/MOD K corpus:
    # DIV K: r0 /= 8. Witness: initial r0=24 → 24//8=3.
    CorpusTask(
        task_id="seed/r0_div8_exit_r0_eq_3",
        spec=_spec("seed/r0_div8_exit_r0_eq_3", "r0 == 3", max_insns=4),
        bytecode=_R0_DIV8_EXIT,
        expected_verdict="reachable",
    ),
    # OR K: r0 |= 0x80. Witness: initial r0=0 → 0|0x80=128.
    CorpusTask(
        task_id="seed/r0_or_0x80_exit_r0_eq_128",
        spec=_spec("seed/r0_or_0x80_exit_r0_eq_128", "r0 == 128", max_insns=4),
        bytecode=_R0_OR_0X80_EXIT,
        expected_verdict="reachable",
    ),
    # OR K always sets bit 7; result ≥ 0x80, so r0==0 is unreachable.
    CorpusTask(
        task_id="seed/r0_or_0x80_exit_r0_eq_0_unreachable",
        spec=_spec("seed/r0_or_0x80_exit_r0_eq_0_unreachable", "r0 == 0", max_insns=4),
        bytecode=_R0_OR_0X80_EXIT,
        expected_verdict="unreachable",
    ),
    # AND K: r0 &= 0xf. Witness: initial r0=15 → 15&0xf=15.
    CorpusTask(
        task_id="seed/r0_and_0xf_exit_r0_eq_15",
        spec=_spec("seed/r0_and_0xf_exit_r0_eq_15", "r0 == 15", max_insns=4),
        bytecode=_R0_AND_0XF_EXIT,
        expected_verdict="reachable",
    ),
    # MOD K: r0 %= 3. Witness: initial r0=2 → 2%3=2.
    CorpusTask(
        task_id="seed/r0_mod3_exit_r0_eq_2",
        spec=_spec("seed/r0_mod3_exit_r0_eq_2", "r0 == 2", max_insns=4),
        bytecode=_R0_MOD3_EXIT,
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
