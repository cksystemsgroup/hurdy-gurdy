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

# r0 <<= 2  (ALU64 LSH K, dst=r0, imm=2); EXIT
# Witness: initial r0=1 → 1<<2=4.
_R0_LSH2_EXIT = bytes([
    0x67, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00,  # r0 <<= 2  (LSH K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 >>= 1  (ALU64 RSH K, dst=r0, imm=1); EXIT
# Witness: initial r0=8 → 8>>1=4.
_R0_RSH1_EXIT = bytes([
    0x77, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 >>= 1  (RSH K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 s>>= 1  (ALU64 ARSH K, dst=r0, imm=1); EXIT
# Arithmetic right shift: sign bit replicated. Witness: r0=2 → 1; r0=-1 → -1.
_R0_ARSH1_EXIT = bytes([
    0xc7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 s>>= 1  (ARSH K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -r0  (ALU64 NEG K, opcode=0x87, src ignored); EXIT
# Witness: r0=0 → 0; r0=0xFFFFFFFFFFFFFFFF → 1.
_R0_NEG_EXIT = bytes([
    0x87, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = -r0  (NEG)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 42  (ALU64 MOV K, opcode=0xb7, dst=r0, imm=42); EXIT
# Deterministic: always sets r0=42 regardless of initial value.
_R0_MOV_K42_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r0 = 42  (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = r1  (ALU64 MOV X, opcode=0xbf, dst=r0, src=r1); EXIT
# Witness: initial r1=7 → r0=7.
_R0_MOV_X_R1_EXIT = bytes([
    0xbf, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = r1  (MOV X)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 5; r0 = -r0; EXIT
# MOV K pins r0=5, then NEG makes r0=-5=0xFFFFFFFFFFFFFFFB. Fully deterministic.
_MOV5_NEG_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0x87, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = -r0  (NEG)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0=42; r1=r0; JEQ r1, 42, +1; r0=0; EXIT
# MOV K + MOV X + JEQ chain. JEQ is always taken (r1==42), so r0=0 is never reached.
_MOV42_MOVX_JEQ_MOV0_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x2a, 0x00, 0x00, 0x00,  # r0 = 42   (MOV K)
    0xbf, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r1 = r0   (MOV X dst=r1 src=r0)
    0x15, 0x01, 0x01, 0x00, 0x2a, 0x00, 0x00, 0x00,  # JEQ r1, 42, +1
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0=1; JNE r0, 1, +1; r0=99; EXIT
# MOV K sets r0=1. JNE not taken (r0==1), falls through to MOV K r0=99.
_MOV1_JNE_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JNE r0, 1, +1  (not taken)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
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
    # P11 additions — LSH/RSH/ARSH K shift operations:
    # LSH K: r0 <<= 2. Witness: initial r0=1 → 1<<2=4.
    CorpusTask(
        task_id="seed/r0_lsh2_exit_r0_eq_4",
        spec=_spec("seed/r0_lsh2_exit_r0_eq_4", "r0 == 4", max_insns=4),
        bytecode=_R0_LSH2_EXIT,
        expected_verdict="reachable",
    ),
    # LSH K 2 always zeros bits 0–1; result is never odd, so r0==3 unreachable.
    CorpusTask(
        task_id="seed/r0_lsh2_exit_r0_eq_3_unreachable",
        spec=_spec("seed/r0_lsh2_exit_r0_eq_3_unreachable", "r0 == 3", max_insns=4),
        bytecode=_R0_LSH2_EXIT,
        expected_verdict="unreachable",
    ),
    # RSH K: r0 >>= 1 (unsigned). Witness: initial r0=8 → 8>>1=4.
    CorpusTask(
        task_id="seed/r0_rsh1_exit_r0_eq_4",
        spec=_spec("seed/r0_rsh1_exit_r0_eq_4", "r0 == 4", max_insns=4),
        bytecode=_R0_RSH1_EXIT,
        expected_verdict="reachable",
    ),
    # ARSH K: r0 s>>= 1. Witness: initial r0=2 → 2 s>>1=1.
    CorpusTask(
        task_id="seed/r0_arsh1_exit_r0_eq_1",
        spec=_spec("seed/r0_arsh1_exit_r0_eq_1", "r0 == 1", max_insns=4),
        bytecode=_R0_ARSH1_EXIT,
        expected_verdict="reachable",
    ),
    # ARSH K sign-extension: r0 s>>= 1 of -1 (0xFFFFFFFFFFFFFFFF) stays -1.
    # Witness: initial r0=0xFFFFFFFFFFFFFFFF → ARSH 1 → 0xFFFFFFFFFFFFFFFF.
    CorpusTask(
        task_id="seed/r0_arsh1_exit_r0_eq_neg1",
        spec=_spec("seed/r0_arsh1_exit_r0_eq_neg1",
                   "r0 == 0xffffffffffffffff", max_insns=4),
        bytecode=_R0_ARSH1_EXIT,
        expected_verdict="reachable",
    ),
    # P12 additions — NEG and MOV opcodes:
    # NEG: r0 = -r0. Witness: initial r0=0 → 0 (neg of zero is zero).
    CorpusTask(
        task_id="seed/r0_neg_exit_r0_eq_0",
        spec=_spec("seed/r0_neg_exit_r0_eq_0", "r0 == 0", max_insns=4),
        bytecode=_R0_NEG_EXIT,
        expected_verdict="reachable",
    ),
    # NEG: r0 = -r0. Witness: initial r0=0xFFFFFFFFFFFFFFFF (-1) → 1.
    CorpusTask(
        task_id="seed/r0_neg_exit_r0_eq_1",
        spec=_spec("seed/r0_neg_exit_r0_eq_1", "r0 == 1", max_insns=4),
        bytecode=_R0_NEG_EXIT,
        expected_verdict="reachable",
    ),
    # MOV K: r0 = 42. Deterministic; r0==42 always holds at halt.
    CorpusTask(
        task_id="seed/r0_mov_k42_exit_r0_eq_42",
        spec=_spec("seed/r0_mov_k42_exit_r0_eq_42", "r0 == 42", max_insns=4),
        bytecode=_R0_MOV_K42_EXIT,
        expected_verdict="reachable",
    ),
    # MOV K: r0 = 42. Property r0==41 unreachable — MOV K pins exact value.
    CorpusTask(
        task_id="seed/r0_mov_k42_exit_r0_eq_41_unreachable",
        spec=_spec("seed/r0_mov_k42_exit_r0_eq_41_unreachable", "r0 == 41", max_insns=4),
        bytecode=_R0_MOV_K42_EXIT,
        expected_verdict="unreachable",
    ),
    # MOV X: r0 = r1. Witness: initial r1=7 → r0=7.
    CorpusTask(
        task_id="seed/r0_mov_x_r1_exit_r0_eq_7",
        spec=_spec("seed/r0_mov_x_r1_exit_r0_eq_7", "r0 == 7", max_insns=4),
        bytecode=_R0_MOV_X_R1_EXIT,
        expected_verdict="reachable",
    ),
    # P13 additions — multi-instruction programs chaining NEG/MOV with branches:
    # MOV K + NEG: r0=5 then negated → 0xFFFFFFFFFFFFFFFB. Fully deterministic.
    CorpusTask(
        task_id="seed/mov5_neg_exit_r0_eq_neg5",
        spec=_spec("seed/mov5_neg_exit_r0_eq_neg5",
                   "r0 == 0xfffffffffffffffb", max_insns=6),
        bytecode=_MOV5_NEG_EXIT,
        expected_verdict="reachable",
    ),
    # MOV K + NEG: r0==5 unreachable — NEG(-5)≠5 (they differ by 2^64-10).
    CorpusTask(
        task_id="seed/mov5_neg_exit_r0_eq_5_unreachable",
        spec=_spec("seed/mov5_neg_exit_r0_eq_5_unreachable", "r0 == 5", max_insns=6),
        bytecode=_MOV5_NEG_EXIT,
        expected_verdict="unreachable",
    ),
    # MOV K + MOV X + JEQ taken + EXIT: r0 stays 42 because MOV K r0=0 is skipped.
    CorpusTask(
        task_id="seed/mov42_movx_jeq_exit_r0_eq_42",
        spec=_spec("seed/mov42_movx_jeq_exit_r0_eq_42", "r0 == 42", max_insns=10),
        bytecode=_MOV42_MOVX_JEQ_MOV0_EXIT,
        expected_verdict="reachable",
    ),
    # Same program: r0==0 unreachable because JEQ is always taken.
    CorpusTask(
        task_id="seed/mov42_movx_jeq_exit_r0_eq_0_unreachable",
        spec=_spec("seed/mov42_movx_jeq_exit_r0_eq_0_unreachable",
                   "r0 == 0", max_insns=10),
        bytecode=_MOV42_MOVX_JEQ_MOV0_EXIT,
        expected_verdict="unreachable",
    ),
    # MOV K + JNE not taken + MOV K + EXIT: JNE not taken, r0 becomes 99.
    CorpusTask(
        task_id="seed/mov1_jne_mov99_exit_r0_eq_99",
        spec=_spec("seed/mov1_jne_mov99_exit_r0_eq_99", "r0 == 99", max_insns=8),
        bytecode=_MOV1_JNE_MOV99_EXIT,
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
