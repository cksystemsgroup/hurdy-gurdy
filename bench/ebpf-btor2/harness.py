"""ebpf-btor2 benchmark harness — P32.

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

# r0=5; r1=7; EXIT
# Two MOV K instructions set independent registers deterministically.
# Used for P14 AND-conjunction property tasks.
_R0_5_R1_7_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0xb7, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00,  # r1 = 7    (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# P15 signed vs unsigned boundary bytecodes.
# All four programs start with r0 = -1 (0xFFFFFFFFFFFFFFFF via MOV K imm=-1).
# The branch opcode and condition determine whether r0=100 (or r0=0) executes.

# r0 = -1; JLT r0, 1, +1; r0 = 100; EXIT
# JLT is unsigned: 0xFFFFFFFFFFFFFFFF is NOT < 1. Not taken. r0=100 executes.
_NEG1_JLT1_MOV100_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JLT r0, 1, +1  (unsigned, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x64, 0x00, 0x00, 0x00,  # r0 = 100  (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JSLT r0, 1, +1; r0 = 100; EXIT
# JSLT is signed: -1 < 1. Taken. r0 = 100 is skipped. EXIT with r0 = 0xFFFFFFFFFFFFFFFF.
_NEG1_JSLT1_MOV100_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xc5, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JSLT r0, 1, +1  (signed, taken)
    0xb7, 0x00, 0x00, 0x00, 0x64, 0x00, 0x00, 0x00,  # r0 = 100  (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JGT r0, 0, +1; r0 = 0; EXIT
# JGT is unsigned: 0xFFFFFFFFFFFFFFFF > 0. Taken. r0 = 0 is skipped. EXIT with r0 = 0xFFFFFFFFFFFFFFFF.
_NEG1_JGT0_MOV0_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x25, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGT r0, 0, +1  (unsigned, taken)
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JSGT r0, 0, +1; r0 = 0; EXIT
# JSGT is signed: -1 > 0? No. Not taken. r0 = 0 executes. EXIT with r0 = 0.
_NEG1_JSGT0_MOV0_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x65, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSGT r0, 0, +1  (signed, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# P16 signed vs unsigned boundary bytecodes — JLE/JSLE/JSGE.
# All programs start with r0 = 0xFFFFFFFFFFFFFFFF (= -1 signed, UINT64_MAX unsigned).

# r0 = -1; JLE r0, 0, +1; r0 = 50; EXIT
# JLE is unsigned: 0xFFFF...FFFF <= 0? No. Not taken. r0=50 executes.
_NEG1_JLE0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xb5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JLE r0, 0, +1  (unsigned, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JSLE r0, 0, +1; r0 = 50; EXIT
# JSLE is signed: -1 <= 0. Taken. r0=50 is skipped.
_NEG1_JSLE0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xd5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSLE r0, 0, +1  (signed, taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JLE r0, -1, +1; r0 = 50; EXIT
# JLE is unsigned: UINT64_MAX <= UINT64_MAX (imm -1 sign-extends to UINT64_MAX). Taken. r0=50 skipped.
_NEG1_JLE_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xb5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JLE r0, -1, +1 (unsigned: equal, taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JSLE r0, -2, +1; r0 = 50; EXIT
# JSLE is signed: -1 <= -2? No. Not taken. r0=50 executes.
_NEG1_JSLE_NEG2_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xd5, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JSLE r0, -2, +1 (signed, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JSGE r0, 0, +1; r0 = 0; EXIT
# JSGE is signed: -1 >= 0? No. Not taken. r0=0 executes.
_NEG1_JSGE0_MOV0_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x75, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSGE r0, 0, +1  (signed, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JSGE r0, -2, +1; r0 = 0; EXIT
# JSGE is signed: -1 >= -2? Yes. Taken. r0=0 is skipped.
_NEG1_JSGE_NEG2_MOV0_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x75, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JSGE r0, -2, +1 (signed, taken)
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# P17 JGE unsigned corpus bytecodes.
# JGE K opcode = JMP(0x05) | JGE_nibble(0x30) | K(0x00) = 0x35.
# The imm field is sign-extended to 64 bits before the unsigned comparison.

# r0 = -1; JGE r0, 0, +1; r0 = 50; EXIT
# JGE unsigned: UINT64_MAX >= 0 — always true. Taken. r0=50 skipped.
_NEG1_JGE0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x35, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGE r0, 0, +1 (unsigned, taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0; JGE r0, 1, +1; r0 = 50; EXIT
# JGE unsigned: 0 >= 1? No. Not taken. r0=50 executes.
_ZERO_JGE1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x35, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JGE r0, 1, +1 (unsigned, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JGE r0, -1, +1; r0 = 50; EXIT
# JGE unsigned: UINT64_MAX >= UINT64_MAX (equal). Taken. r0=50 skipped.
_NEG1_JGE_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x35, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JGE r0, -1, +1 (unsigned: equal, taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -2; JGE r0, -1, +1; r0 = 50; EXIT
# JGE unsigned: UINT64_MAX-1 >= UINT64_MAX? No. Not taken. r0=50 executes.
_NEG2_JGE_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0x35, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JGE r0, -1, +1 (unsigned, not taken)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# P18 JNE corpus bytecodes.
# JNE K opcode = JMP(0x05) | JNE_nibble(0x50) | K(0x00) = 0x55.
# No signed/unsigned distinction — JNE tests dst != src (bitwise).

# r0 = 5; JNE r0, 5, +1; r0 = 99; EXIT
# JNE: 5 != 5? No. Not taken. r0=99 executes.
_FIVE_JNE5_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00,  # JNE r0, 5, +1 (not taken)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 5; JNE r0, 6, +1; r0 = 99; EXIT
# JNE: 5 != 6? Yes. Taken. r0=99 skipped.
_FIVE_JNE6_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x06, 0x00, 0x00, 0x00,  # JNE r0, 6, +1 (taken)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0; JNE r0, 0, +1; r0 = 99; EXIT
# JNE: 0 != 0? No. Not taken. r0=99 executes.
_ZERO_JNE0_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JNE r0, 0, +1 (not taken)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JNE r0, 0, +1; r0 = 99; EXIT
# JNE: UINT64_MAX != 0? Yes. Taken. r0=99 skipped.
_NEG1_JNE0_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JNE r0, 0, +1 (taken: UINT64_MAX!=0)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# P19 JSET corpus bytecodes.
# JSET K opcode = JMP(0x05) | JSET_nibble(0x40) | K(0x00) = 0x45.
# JSET is taken when (dst & src) != 0 (bitwise AND test).

# r0 = 10 (0b1010); JSET r0, 2 (0b0010), +1; r0 = 99; EXIT
# JSET: 0b1010 & 0b0010 = 0b0010 != 0. Taken. r0=99 skipped.
_TEN_JSET2_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x0a, 0x00, 0x00, 0x00,  # r0 = 10   (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x02, 0x00, 0x00, 0x00,  # JSET r0, 2, +1 (taken: 10&2=2)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 10 (0b1010); JSET r0, 5 (0b0101), +1; r0 = 99; EXIT
# JSET: 0b1010 & 0b0101 = 0. Not taken. r0=99 executes.
_TEN_JSET5_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x0a, 0x00, 0x00, 0x00,  # r0 = 10   (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00,  # JSET r0, 5, +1 (not taken: 10&5=0)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0xFF; JSET r0, 0x0F, +1; r0 = 99; EXIT
# JSET: 0xFF & 0x0F = 0x0F != 0. Taken. r0=99 skipped.
_FF_JSET0F_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0x00, 0x00, 0x00,  # r0 = 0xFF (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x0f, 0x00, 0x00, 0x00,  # JSET r0, 0x0F, +1 (taken: overlap)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0xF0; JSET r0, 0x0F, +1; r0 = 99; EXIT
# JSET: 0xF0 & 0x0F = 0. Not taken. r0=99 executes.
_F0_JSET0F_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xf0, 0x00, 0x00, 0x00,  # r0 = 0xF0 (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x0f, 0x00, 0x00, 0x00,  # JSET r0, 0x0F, +1 (not taken: disjoint)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# P20 JGT additional corpus bytecodes (P15 added 2 basic JGT/JSGT tasks;
# P20 adds boundary cases). JGT K opcode = JMP(0x05) | JGT(0x20) | K = 0x25.

# r0 = 5; JGT r0, 5, +1; r0 = 50; EXIT
# JGT: 5 > 5? No (strict). Not taken. r0=50 executes.
_FIVE_JGT5_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0x25, 0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00,  # JGT r0, 5, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 6; JGT r0, 5, +1; r0 = 50; EXIT
# JGT: 6 > 5. Taken. r0=50 skipped.
_SIX_JGT5_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x06, 0x00, 0x00, 0x00,  # r0 = 6    (MOV K)
    0x25, 0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00,  # JGT r0, 5, +1 (taken: 6>5)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JGT r0, -2, +1; r0 = 50; EXIT
# JGT unsigned: UINT64_MAX > UINT64_MAX-1. Taken. r0=50 skipped.
_NEG1_JGT_NEG2_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x25, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JGT r0, -2, +1 (taken: UINT64_MAX > UINT64_MAX-1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -2; JGT r0, -1, +1; r0 = 50; EXIT
# JGT unsigned: UINT64_MAX-1 > UINT64_MAX? No. Not taken. r0=50 executes.
_NEG2_JGT_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0x25, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JGT r0, -1, +1 (not taken: UINT64_MAX-1 < UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# P21 JLT boundary corpus bytecodes (P15 had the basic JLT/JSLT tasks).
# JLT K opcode = JMP(0x05) | JLT_nibble(0xA0) | K(0x00) = 0xA5.

# r0 = 5; JLT r0, 5, +1; r0 = 50; EXIT
# JLT: 5 < 5? No (strict, equal not taken). r0=50 executes.
_FIVE_JLT5_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00,  # r0 = 5    (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00,  # JLT r0, 5, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 4; JLT r0, 5, +1; r0 = 50; EXIT
# JLT: 4 < 5. Taken. r0=50 skipped.
_FOUR_JLT5_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00,  # r0 = 4    (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00,  # JLT r0, 5, +1 (taken: 4<5)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -2; JLT r0, -1, +1; r0 = 50; EXIT
# JLT unsigned: UINT64_MAX-1 < UINT64_MAX. Taken. r0=50 skipped.
_NEG2_JLT_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JLT r0, -1, +1 (taken: UINT64_MAX-1 < UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JLT r0, -2, +1; r0 = 50; EXIT
# JLT unsigned: UINT64_MAX < UINT64_MAX-1? No. Not taken. r0=50 executes.
_NEG1_JLT_NEG2_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JLT r0, -2, +1 (not taken: UINT64_MAX > UINT64_MAX-1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# P22 JSLT boundary corpus bytecodes (P15 had the basic JLT/JSLT contrast).
# JSLT K opcode = JMP(0x05) | JSLT_nibble(0xC0) | K(0x00) = 0xC5.

# r0 = -1; JSLT r0, -1, +1; r0 = 50; EXIT
# JSLT signed: -1 < -1? No (equal). Not taken. r0=50 executes.
_NEG1_JSLT_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xc5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSLT r0, -1, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -2; JSLT r0, -1, +1; r0 = 50; EXIT
# JSLT signed: -2 < -1. Taken. r0=50 skipped.
_NEG2_JSLT_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0xc5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSLT r0, -1, +1 (taken: -2 < -1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JSLT r0, 0, +1; r0 = 50; EXIT
# JSLT signed: -1 < 0. Taken. r0=50 skipped.
# Signed/unsigned contrast: JLT unsigned UINT64_MAX < 0? No (not taken, P15).
_NEG1_JSLT0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xc5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSLT r0, 0, +1 (taken: -1 < 0 signed)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JSLT r0, -2, +1; r0 = 50; EXIT
# JSLT signed: -1 < -2? No (-1 > -2). Not taken. r0=50 executes.
_NEG1_JSLT_NEG2_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xc5, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JSLT r0, -2, +1 (not taken: -1 > -2)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# P23 JSGT boundary corpus bytecodes (P15 had the basic JSGT/JGT contrast).
# JSGT K opcode = JMP(0x05) | JSGT_nibble(0x60) | K(0x00) = 0x65.

# r0 = -1; JSGT r0, -1, +1; r0 = 50; EXIT
# JSGT signed: -1 > -1? No (equal). Not taken. r0=50 executes.
_NEG1_JSGT_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x65, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSGT r0, -1, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JSGT r0, -2, +1; r0 = 50; EXIT
# JSGT signed: -1 > -2. Taken. r0=50 skipped.
_NEG1_JSGT_NEG2_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x65, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JSGT r0, -2, +1 (taken: -1 > -2)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0; JSGT r0, -1, +1; r0 = 50; EXIT
# JSGT signed: 0 > -1. Taken. r0=50 skipped.
# Signed/unsigned contrast: JGT unsigned 0 > UINT64_MAX? No (not taken).
_ZERO_JSGT_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x65, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSGT r0, -1, +1 (taken: 0 > -1 signed)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -2; JSGT r0, -1, +1; r0 = 50; EXIT
# JSGT signed: -2 > -1? No. Not taken. r0=50 executes.
_NEG2_JSGT_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0x65, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSGT r0, -1, +1 (not taken: -2 < -1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# P24 JSLE additional boundary corpus bytecodes (P16 had JSLE r0,0 and JSLE r0,-2).
# JSLE K opcode = JMP(0x05) | JSLE_nibble(0xD0) | K(0x00) = 0xD5.

# r0 = -1; JSLE r0, -1, +1; r0 = 50; EXIT
# JSLE signed: -1 <= -1 (equal). Taken. r0=50 skipped.
_NEG1_JSLE_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xd5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSLE r0, -1, +1 (taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -2; JSLE r0, -1, +1; r0 = 50; EXIT
# JSLE signed: -2 <= -1. Taken. r0=50 skipped.
_NEG2_JSLE_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0xd5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSLE r0, -1, +1 (taken: -2 <= -1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0; JSLE r0, 0, +1; r0 = 50; EXIT
# JSLE signed: 0 <= 0 (equal). Taken. r0=50 skipped.
_ZERO_JSLE0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0xd5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSLE r0, 0, +1 (taken: 0 <= 0 equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0; JSLE r0, -1, +1; r0 = 50; EXIT
# JSLE signed: 0 <= -1? No (0 > -1). Not taken. r0=50 executes.
_ZERO_JSLE_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0xd5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSLE r0, -1, +1 (not taken: 0 > -1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# ---------------------------------------------------------------------------
# P25 — JSGE signed ≥  (opcode 0x75, JMP K)
# ---------------------------------------------------------------------------

# r0 = -1; JSGE r0, -1, +1; r0 = 50; EXIT
# JSGE signed: -1 >= -1 (equal). Taken. r0=50 skipped.
_NEG1_JSGE_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x75, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSGE r0, -1, +1 (taken: -1 >= -1 equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -2; JSGE r0, -1, +1; r0 = 50; EXIT
# JSGE signed: -2 >= -1? No (-2 < -1). Not taken. r0=50 executes.
_NEG2_JSGE_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0x75, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSGE r0, -1, +1 (not taken: -2 < -1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0; JSGE r0, 0, +1; r0 = 50; EXIT
# JSGE signed: 0 >= 0 (equal). Taken. r0=50 skipped.
_ZERO_JSGE0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x75, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JSGE r0, 0, +1 (taken: 0 >= 0 equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0; JSGE r0, 1, +1; r0 = 50; EXIT
# JSGE signed: 0 >= 1? No (0 < 1). Not taken. r0=50 executes.
_ZERO_JSGE1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x75, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JSGE r0, 1, +1 (not taken: 0 < 1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# ---------------------------------------------------------------------------
# P26 — JLE unsigned ≤  (opcode 0xB5, JMP K)
# ---------------------------------------------------------------------------

# r0 = 0; JLE r0, 0, +1; r0 = 50; EXIT
# JLE unsigned: 0 <= 0 (equal). Taken. r0=50 skipped.
_ZERO_JLE0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0xb5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JLE r0, 0, +1 (taken: 0 <= 0 equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 1; JLE r0, 0, +1; r0 = 50; EXIT
# JLE unsigned: 1 <= 0? No. Not taken. r0=50 executes.
_ONE_JLE0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0xb5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JLE r0, 0, +1 (not taken: 1 > 0)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -2; JLE r0, -1, +1; r0 = 50; EXIT
# JLE unsigned: UINT64_MAX-1 <= UINT64_MAX (-1 sign-extends). Taken. r0=50 skipped.
_NEG2_JLE_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xfe, 0xff, 0xff, 0xff,  # r0 = -2   (MOV K)
    0xb5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JLE r0, -1, +1 (taken: UINT64_MAX-1 <= UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JLE r0, -2, +1; r0 = 50; EXIT
# JLE unsigned: UINT64_MAX <= UINT64_MAX-1? No. Not taken. r0=50 executes.
_NEG1_JLE_NEG2_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xb5, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JLE r0, -2, +1 (not taken: UINT64_MAX > UINT64_MAX-1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# ---------------------------------------------------------------------------
# P27 — JGT unsigned >  (opcode 0x25, JMP K) — zero-boundary and high-unsigned
# P15 added UINT64_MAX > 0 (taken); P20 added equal-at-5, strictly-greater-at-6,
# and the high-unsigned pair. P27 adds zero-equal not-taken, one-gt-zero taken,
# UINT64_MAX equal not-taken, and the unsigned sign-crossing (0 > UINT64_MAX? No).
# ---------------------------------------------------------------------------

# r0 = 0; JGT r0, 0, +1; r0 = 50; EXIT
# JGT unsigned: 0 > 0? No (strict, equal not taken). r0=50 executes.
_ZERO_JGT0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x25, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGT r0, 0, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 1; JGT r0, 0, +1; r0 = 50; EXIT
# JGT unsigned: 1 > 0. Taken. r0=50 skipped.
_ONE_JGT0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x25, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGT r0, 0, +1 (taken: 1 > 0)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JGT r0, -1, +1; r0 = 50; EXIT
# JGT unsigned: UINT64_MAX > UINT64_MAX (equal)? No. Not taken. r0=50 executes.
_NEG1_JGT_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x25, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JGT r0, -1, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0; JGT r0, -1, +1; r0 = 50; EXIT
# JGT unsigned: 0 > UINT64_MAX? No (0 is smallest unsigned). Not taken. r0=50 executes.
# Signed contrast: JSGT r0=0, imm=-1 → 0 > -1 signed? Yes (taken, see P23).
_ZERO_JGT_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x25, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JGT r0, -1, +1 (not taken: 0 < UINT64_MAX unsigned)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# ---------------------------------------------------------------------------
# P28 — JLT unsigned <  (opcode 0xA5, JMP K) — zero-boundary and unsigned sign-crossing
# P15 had UINT64_MAX < 1 (not taken); P21 added equal-at-5, strictly-less-at-4,
# and the high-unsigned pair. P28 adds zero-equal not-taken, one-lt-two taken,
# UINT64_MAX equal not-taken, and unsigned sign-crossing (UINT64_MAX < 0? No —
# complement of JGT P27; contrast with JSLT UINT64_MAX < 0 signed? Yes).
# ---------------------------------------------------------------------------

# r0 = 0; JLT r0, 0, +1; r0 = 50; EXIT
# JLT unsigned: 0 < 0? No (strict, equal not taken). r0=50 executes.
_ZERO_JLT0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JLT r0, 0, +1 (not taken: equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 1; JLT r0, 2, +1; r0 = 50; EXIT
# JLT unsigned: 1 < 2. Taken. r0=50 skipped.
_ONE_JLT2_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0x02, 0x00, 0x00, 0x00,  # JLT r0, 2, +1 (taken: 1 < 2)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JLT r0, -1, +1; r0 = 50; EXIT
# JLT unsigned: UINT64_MAX < UINT64_MAX (equal)? No. Not taken. r0=50 executes.
_NEG1_JLT_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JLT r0, -1, +1 (not taken: UINT64_MAX==UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JLT r0, 0, +1; r0 = 50; EXIT
# JLT unsigned: UINT64_MAX < 0? No (0 is the smallest unsigned value). Not taken. r0=50 executes.
# Signed contrast: JSLT r0=-1, imm=0 → -1 < 0 signed? Yes (taken, see P22).
_NEG1_JLT0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0xa5, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JLT r0, 0, +1 (not taken: UINT64_MAX > 0 unsigned)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# ---------------------------------------------------------------------------
# P29 — JGE unsigned ≥  (opcode 0x35, JMP K) — zero-boundary and sign-crossing
# P17 added UINT64_MAX≥0 (taken), 0≥1 (not taken), UINT64_MAX≥UINT64_MAX equal
# (taken), UINT64_MAX-1≥UINT64_MAX (not taken). P29 adds zero-zero equal (taken),
# one-GE-zero (taken), UINT64_MAX≥UINT64_MAX-1 strictly-greater (taken), and the
# unsigned sign-crossing complement (0≥UINT64_MAX? No — contrast P17's UINT64_MAX≥0
# taken; contrast with JSGE 0≥-1 signed: yes, from P25).
# ---------------------------------------------------------------------------

# r0 = 0; JGE r0, 0, +1; r0 = 50; EXIT
# JGE unsigned: 0 >= 0 (equal). Taken. r0=50 skipped.
_ZERO_JGE0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x35, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGE r0, 0, +1 (taken: 0>=0 equal)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 1; JGE r0, 0, +1; r0 = 50; EXIT
# JGE unsigned: 1 >= 0. Taken. r0=50 skipped.
_ONE_JGE0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x35, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JGE r0, 0, +1 (taken: 1>=0)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JGE r0, -2, +1; r0 = 50; EXIT
# JGE unsigned: UINT64_MAX >= UINT64_MAX-1. Taken. r0=50 skipped.
# Complements P17's neg2_jge_neg1 (UINT64_MAX-1 >= UINT64_MAX? No, not taken).
_NEG1_JGE_NEG2_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x35, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0xff,  # JGE r0, -2, +1 (taken: UINT64_MAX>=UINT64_MAX-1)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0; JGE r0, -1, +1; r0 = 50; EXIT
# JGE unsigned: 0 >= UINT64_MAX? No (0 is smallest). Not taken. r0=50 executes.
# Sign-crossing: complements P17's neg1_jge0 (UINT64_MAX>=0 taken).
# Signed contrast: JSGE 0>=-1 signed? Yes (taken, see P25).
_ZERO_JGE_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x35, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JGE r0, -1, +1 (not taken: 0 < UINT64_MAX unsigned)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# ---------------------------------------------------------------------------
# P30 — JEQ (opcode 0x15, JMP K) — zero-boundary, UINT64_MAX, and not-equal cases
# P8 had complex JEQ programs (add+JEQ, JEQ-taken-skip-add, MOV+JEQ chain).
# P30 adds clean boundary cases: zero-equal taken, one-NE-zero not-taken,
# UINT64_MAX-equal taken, and UINT64_MAX-NE-zero not-taken (no signed/unsigned
# distinction — JEQ is bitwise equality).
# ---------------------------------------------------------------------------

# r0 = 0; JEQ r0, 0, +1; r0 = 50; EXIT
# JEQ: 0 == 0. Taken. r0=50 skipped.
_ZERO_JEQ0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x15, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JEQ r0, 0, +1 (taken: 0==0)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 1; JEQ r0, 0, +1; r0 = 50; EXIT
# JEQ: 1 == 0? No. Not taken. r0=50 executes.
_ONE_JEQ0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x15, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JEQ r0, 0, +1 (not taken: 1!=0)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JEQ r0, -1, +1; r0 = 50; EXIT
# JEQ: UINT64_MAX == UINT64_MAX. Taken. r0=50 skipped.
_NEG1_JEQ_NEG1_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x15, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JEQ r0, -1, +1 (taken: UINT64_MAX==UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JEQ r0, 0, +1; r0 = 50; EXIT
# JEQ: UINT64_MAX == 0? No. Not taken. r0=50 executes.
_NEG1_JEQ0_MOV50_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x15, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # JEQ r0, 0, +1 (not taken: UINT64_MAX!=0)
    0xb7, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00,  # r0 = 50   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# ---------------------------------------------------------------------------
# P31 — JNE (opcode 0x55, JMP K) — additional boundary cases
# P18 had: 5!=5 not-taken, 5!=6 taken, 0!=0 not-taken, UINT64_MAX!=0 taken.
# P31 adds: 1!=1 equal not-taken, 0!=1 taken, UINT64_MAX!=UINT64_MAX not-taken,
# UINT64_MAX!=1 taken. No signed/unsigned distinction — JNE is bitwise inequality.
# ---------------------------------------------------------------------------

# r0 = 1; JNE r0, 1, +1; r0 = 99; EXIT
# JNE: 1 != 1? No. Not taken. r0=99 executes.
_ONE_JNE1_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JNE r0, 1, +1 (not taken: 1==1)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0; JNE r0, 1, +1; r0 = 99; EXIT
# JNE: 0 != 1. Taken. r0=99 skipped.
_ZERO_JNE1_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JNE r0, 1, +1 (taken: 0!=1)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JNE r0, -1, +1; r0 = 99; EXIT
# JNE: UINT64_MAX != UINT64_MAX? No. Not taken. r0=99 executes.
_NEG1_JNE_NEG1_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x55, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JNE r0, -1, +1 (not taken: UINT64_MAX==UINT64_MAX)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JNE r0, 1, +1; r0 = 99; EXIT
# JNE: UINT64_MAX != 1. Taken. r0=99 skipped.
_NEG1_JNE1_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x55, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JNE r0, 1, +1 (taken: UINT64_MAX!=1)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# ---------------------------------------------------------------------------
# P32 — JSET (opcode 0x45, JMP K) — additional boundary cases
# P19 had: 0b1010&0b0010 taken, 0b1010&0b0101 not-taken, 0xFF&0x0F taken,
# 0xF0&0x0F not-taken. P32 adds: single-bit match (1&1) taken, adjacent-bit
# miss (1&2) not-taken, UINT64_MAX self-AND taken, zero-operand not-taken.
# JSET is taken when (dst & imm) != 0; imm is sign-extended 32→64 bit.
# ---------------------------------------------------------------------------

# r0 = 1; JSET r0, 1, +1; r0 = 99; EXIT
# JSET: 0b01 & 0b01 = 1 != 0. Taken. r0=99 skipped.
_ONE_JSET1_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JSET r0, 1, +1 (taken: 1&1=1)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 1; JSET r0, 2, +1; r0 = 99; EXIT
# JSET: 0b01 & 0b10 = 0. Not taken. r0=99 executes.
_ONE_JSET2_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  # r0 = 1    (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x02, 0x00, 0x00, 0x00,  # JSET r0, 2, +1 (not taken: 1&2=0)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = -1; JSET r0, -1, +1; r0 = 99; EXIT
# JSET: UINT64_MAX & UINT64_MAX = UINT64_MAX != 0. Taken. r0=99 skipped.
_NEG1_JSET_NEG1_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,  # r0 = -1   (MOV K)
    0x45, 0x00, 0x01, 0x00, 0xff, 0xff, 0xff, 0xff,  # JSET r0, -1, +1 (taken: UINT64_MAX&UINT64_MAX!=0)
    0xb7, 0x00, 0x00, 0x00, 0x63, 0x00, 0x00, 0x00,  # r0 = 99   (MOV K, skipped)
    0x95, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # EXIT
])

# r0 = 0; JSET r0, 1, +1; r0 = 99; EXIT
# JSET: 0 & 1 = 0. Not taken. r0=99 executes.
_ZERO_JSET1_MOV99_EXIT = bytes([
    0xb7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # r0 = 0    (MOV K)
    0x45, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # JSET r0, 1, +1 (not taken: 0&1=0)
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
    # P14 additions — AND-conjunction property grammar:
    # r0=5; r1=7; EXIT. Both registers deterministic; AND of both holds.
    CorpusTask(
        task_id="seed/r0_5_r1_7_exit_r0_eq_5_and_r1_eq_7",
        spec=_spec("seed/r0_5_r1_7_exit_r0_eq_5_and_r1_eq_7",
                   "r0 == 5 AND r1 == 7", max_insns=6),
        bytecode=_R0_5_R1_7_EXIT,
        expected_verdict="reachable",
    ),
    # r1 is always 7; AND with r1==99 makes the conjunction unreachable.
    CorpusTask(
        task_id="seed/r0_5_r1_7_exit_r0_eq_5_and_r1_eq_99_unreachable",
        spec=_spec("seed/r0_5_r1_7_exit_r0_eq_5_and_r1_eq_99_unreachable",
                   "r0 == 5 AND r1 == 99", max_insns=6),
        bytecode=_R0_5_R1_7_EXIT,
        expected_verdict="unreachable",
    ),
    # exit_reached AND r0==5: both hold since program always exits with r0=5.
    CorpusTask(
        task_id="seed/r0_5_r1_7_exit_exit_reached_and_r0_eq_5",
        spec=_spec("seed/r0_5_r1_7_exit_exit_reached_and_r0_eq_5",
                   "exit_reached AND r0 == 5", max_insns=6),
        bytecode=_R0_5_R1_7_EXIT,
        expected_verdict="reachable",
    ),
    # r0 is always 5; AND with r0==0 makes the conjunction unreachable.
    CorpusTask(
        task_id="seed/r0_5_r1_7_exit_r0_eq_0_and_r1_eq_7_unreachable",
        spec=_spec("seed/r0_5_r1_7_exit_r0_eq_0_and_r1_eq_7_unreachable",
                   "r0 == 0 AND r1 == 7", max_insns=6),
        bytecode=_R0_5_R1_7_EXIT,
        expected_verdict="unreachable",
    ),
    # P15 additions — JLT/JSLT/JGT/JSGT signed vs unsigned boundary cases:
    # The key contrast: r0 = 0xFFFFFFFFFFFFFFFF is large (unsigned) but -1 (signed).
    # JLT unsigned: 0xFFFF... is NOT < 1. Not taken. Falls through to r0=100.
    CorpusTask(
        task_id="seed/neg1_jlt1_mov100_exit_r0_eq_100",
        spec=_spec("seed/neg1_jlt1_mov100_exit_r0_eq_100", "r0 == 100", max_insns=8),
        bytecode=_NEG1_JLT1_MOV100_EXIT,
        expected_verdict="reachable",
    ),
    # JSLT signed: -1 < 1. Taken. r0=100 skipped. Same program, opposite branch behaviour.
    CorpusTask(
        task_id="seed/neg1_jslt1_mov100_exit_r0_eq_100_unreachable",
        spec=_spec("seed/neg1_jslt1_mov100_exit_r0_eq_100_unreachable",
                   "r0 == 100", max_insns=8),
        bytecode=_NEG1_JSLT1_MOV100_EXIT,
        expected_verdict="unreachable",
    ),
    # JGT unsigned: 0xFFFF... > 0. Taken. r0=0 skipped.
    CorpusTask(
        task_id="seed/neg1_jgt0_mov0_exit_r0_eq_0_unreachable",
        spec=_spec("seed/neg1_jgt0_mov0_exit_r0_eq_0_unreachable", "r0 == 0", max_insns=8),
        bytecode=_NEG1_JGT0_MOV0_EXIT,
        expected_verdict="unreachable",
    ),
    # JSGT signed: -1 > 0? No. Not taken. r0=0 executes. Same program, opposite branch behaviour.
    CorpusTask(
        task_id="seed/neg1_jsgt0_mov0_exit_r0_eq_0",
        spec=_spec("seed/neg1_jsgt0_mov0_exit_r0_eq_0", "r0 == 0", max_insns=8),
        bytecode=_NEG1_JSGT0_MOV0_EXIT,
        expected_verdict="reachable",
    ),
    # P16 additions — JLE/JSLE/JSGE signed vs unsigned boundary cases:
    # JLE unsigned: UINT64_MAX > 0, so r0 is NOT <= 0. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg1_jle0_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg1_jle0_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JLE0_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JSLE signed: -1 <= 0. Taken. r0=50 skipped. Same program structure, opposite behaviour.
    CorpusTask(
        task_id="seed/neg1_jsle0_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg1_jsle0_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JSLE0_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JLE unsigned: UINT64_MAX <= UINT64_MAX (imm=-1 sign-extends to UINT64_MAX). Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/neg1_jle_neg1_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg1_jle_neg1_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JLE_NEG1_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JSLE signed: -1 <= -2? No. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg1_jsle_neg2_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg1_jsle_neg2_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JSLE_NEG2_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JSGE signed: -1 >= 0? No. Not taken. r0=0 executes.
    CorpusTask(
        task_id="seed/neg1_jsge0_mov0_exit_r0_eq_0",
        spec=_spec("seed/neg1_jsge0_mov0_exit_r0_eq_0", "r0 == 0", max_insns=8),
        bytecode=_NEG1_JSGE0_MOV0_EXIT,
        expected_verdict="reachable",
    ),
    # JSGE signed: -1 >= -2? Yes. Taken. r0=0 skipped.
    CorpusTask(
        task_id="seed/neg1_jsge_neg2_mov0_exit_r0_eq_0_unreachable",
        spec=_spec("seed/neg1_jsge_neg2_mov0_exit_r0_eq_0_unreachable", "r0 == 0", max_insns=8),
        bytecode=_NEG1_JSGE_NEG2_MOV0_EXIT,
        expected_verdict="unreachable",
    ),
    # P17 additions — JGE unsigned corpus, contrasting with JSGE signed (P16):
    # JGE unsigned: UINT64_MAX >= 0 — always true, taken. r0=50 skipped.
    # Contrast: JSGE signed -1>=0? No — not taken (see P16 neg1_jsge0 task).
    CorpusTask(
        task_id="seed/neg1_jge0_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg1_jge0_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JGE0_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JGE unsigned: 0 >= 1? No. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/zero_jge1_mov50_exit_r0_eq_50",
        spec=_spec("seed/zero_jge1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JGE1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JGE unsigned: UINT64_MAX >= UINT64_MAX (equal). Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/neg1_jge_neg1_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg1_jge_neg1_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JGE_NEG1_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JGE unsigned: UINT64_MAX-1 >= UINT64_MAX? No. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg2_jge_neg1_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg2_jge_neg1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG2_JGE_NEG1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # P18 additions — JNE corpus:
    # JNE: 5 != 5? No. Not taken. r0=99 executes.
    CorpusTask(
        task_id="seed/five_jne5_mov99_exit_r0_eq_99",
        spec=_spec("seed/five_jne5_mov99_exit_r0_eq_99", "r0 == 99", max_insns=8),
        bytecode=_FIVE_JNE5_MOV99_EXIT,
        expected_verdict="reachable",
    ),
    # JNE: 5 != 6? Yes. Taken. r0=99 skipped.
    CorpusTask(
        task_id="seed/five_jne6_mov99_exit_r0_eq_99_unreachable",
        spec=_spec("seed/five_jne6_mov99_exit_r0_eq_99_unreachable", "r0 == 99", max_insns=8),
        bytecode=_FIVE_JNE6_MOV99_EXIT,
        expected_verdict="unreachable",
    ),
    # JNE: 0 != 0? No. Not taken. r0=99 executes.
    CorpusTask(
        task_id="seed/zero_jne0_mov99_exit_r0_eq_99",
        spec=_spec("seed/zero_jne0_mov99_exit_r0_eq_99", "r0 == 99", max_insns=8),
        bytecode=_ZERO_JNE0_MOV99_EXIT,
        expected_verdict="reachable",
    ),
    # JNE: UINT64_MAX != 0? Yes. Taken. r0=99 skipped.
    CorpusTask(
        task_id="seed/neg1_jne0_mov99_exit_r0_eq_99_unreachable",
        spec=_spec("seed/neg1_jne0_mov99_exit_r0_eq_99_unreachable", "r0 == 99", max_insns=8),
        bytecode=_NEG1_JNE0_MOV99_EXIT,
        expected_verdict="unreachable",
    ),
    # P19 additions — JSET bitwise-AND-test corpus:
    # JSET: 0b1010 & 0b0010 = 2 != 0. Taken. r0=99 skipped.
    CorpusTask(
        task_id="seed/ten_jset2_mov99_exit_r0_eq_99_unreachable",
        spec=_spec("seed/ten_jset2_mov99_exit_r0_eq_99_unreachable", "r0 == 99", max_insns=8),
        bytecode=_TEN_JSET2_MOV99_EXIT,
        expected_verdict="unreachable",
    ),
    # JSET: 0b1010 & 0b0101 = 0. Not taken. r0=99 executes.
    CorpusTask(
        task_id="seed/ten_jset5_mov99_exit_r0_eq_99",
        spec=_spec("seed/ten_jset5_mov99_exit_r0_eq_99", "r0 == 99", max_insns=8),
        bytecode=_TEN_JSET5_MOV99_EXIT,
        expected_verdict="reachable",
    ),
    # JSET: 0xFF & 0x0F = 0x0F != 0. Taken. r0=99 skipped.
    CorpusTask(
        task_id="seed/ff_jset0f_mov99_exit_r0_eq_99_unreachable",
        spec=_spec("seed/ff_jset0f_mov99_exit_r0_eq_99_unreachable", "r0 == 99", max_insns=8),
        bytecode=_FF_JSET0F_MOV99_EXIT,
        expected_verdict="unreachable",
    ),
    # JSET: 0xF0 & 0x0F = 0. Not taken. r0=99 executes.
    CorpusTask(
        task_id="seed/f0_jset0f_mov99_exit_r0_eq_99",
        spec=_spec("seed/f0_jset0f_mov99_exit_r0_eq_99", "r0 == 99", max_insns=8),
        bytecode=_F0_JSET0F_MOV99_EXIT,
        expected_verdict="reachable",
    ),
    # P20 additions — JGT boundary cases (P15 had the basic signed/unsigned contrast):
    # JGT: 5 > 5? No (strict, equal not taken). r0=50 executes.
    CorpusTask(
        task_id="seed/five_jgt5_mov50_exit_r0_eq_50",
        spec=_spec("seed/five_jgt5_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_FIVE_JGT5_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JGT: 6 > 5. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/six_jgt5_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/six_jgt5_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_SIX_JGT5_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JGT unsigned: UINT64_MAX > UINT64_MAX-1. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/neg1_jgt_neg2_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg1_jgt_neg2_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JGT_NEG2_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JGT unsigned: UINT64_MAX-1 > UINT64_MAX? No. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg2_jgt_neg1_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg2_jgt_neg1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG2_JGT_NEG1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # P21 additions — JLT boundary cases (P15 had the basic JLT/JSLT contrast):
    # JLT: 5 < 5? No (equal not taken). r0=50 executes.
    CorpusTask(
        task_id="seed/five_jlt5_mov50_exit_r0_eq_50",
        spec=_spec("seed/five_jlt5_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_FIVE_JLT5_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JLT: 4 < 5. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/four_jlt5_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/four_jlt5_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_FOUR_JLT5_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JLT unsigned: UINT64_MAX-1 < UINT64_MAX. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/neg2_jlt_neg1_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg2_jlt_neg1_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG2_JLT_NEG1_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JLT unsigned: UINT64_MAX < UINT64_MAX-1? No. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg1_jlt_neg2_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg1_jlt_neg2_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JLT_NEG2_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # P22 additions — JSLT signed boundary cases:
    # JSLT signed: -1 < -1? No (equal). Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg1_jslt_neg1_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg1_jslt_neg1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JSLT_NEG1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JSLT signed: -2 < -1. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/neg2_jslt_neg1_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg2_jslt_neg1_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG2_JSLT_NEG1_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JSLT signed: -1 < 0. Taken. r0=50 skipped. (JLT unsigned: UINT64_MAX < 0? No — contrast.)
    CorpusTask(
        task_id="seed/neg1_jslt0_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg1_jslt0_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JSLT0_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JSLT signed: -1 < -2? No (-1 > -2). Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg1_jslt_neg2_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg1_jslt_neg2_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JSLT_NEG2_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # P23 additions — JSGT signed boundary cases (P15 had the basic contrast):
    # JSGT signed: -1 > -1? No (equal). Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg1_jsgt_neg1_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg1_jsgt_neg1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JSGT_NEG1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JSGT signed: -1 > -2. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/neg1_jsgt_neg2_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg1_jsgt_neg2_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JSGT_NEG2_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JSGT signed: 0 > -1. Taken. r0=50 skipped. (JGT unsigned: 0 > UINT64_MAX? No.)
    CorpusTask(
        task_id="seed/zero_jsgt_neg1_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/zero_jsgt_neg1_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JSGT_NEG1_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JSGT signed: -2 > -1? No. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg2_jsgt_neg1_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg2_jsgt_neg1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG2_JSGT_NEG1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # P24 additions — JSLE boundary cases (P16 had JSLE r0,0 and JSLE r0,-2):
    # JSLE signed: -1 <= -1 (equal). Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/neg1_jsle_neg1_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg1_jsle_neg1_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JSLE_NEG1_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JSLE signed: -2 <= -1. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/neg2_jsle_neg1_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg2_jsle_neg1_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG2_JSLE_NEG1_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JSLE signed: 0 <= 0 (equal). Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/zero_jsle0_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/zero_jsle0_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JSLE0_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JSLE signed: 0 <= -1? No (0 > -1). Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/zero_jsle_neg1_mov50_exit_r0_eq_50",
        spec=_spec("seed/zero_jsle_neg1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JSLE_NEG1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # P25 additions — JSGE boundary cases (0x75, signed >=):
    # JSGE signed: -1 >= -1 (equal). Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/neg1_jsge_neg1_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg1_jsge_neg1_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JSGE_NEG1_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JSGE signed: -2 >= -1? No (-2 < -1). Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg2_jsge_neg1_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg2_jsge_neg1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG2_JSGE_NEG1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JSGE signed: 0 >= 0 (equal). Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/zero_jsge0_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/zero_jsge0_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JSGE0_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JSGE signed: 0 >= 1? No (0 < 1). Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/zero_jsge1_mov50_exit_r0_eq_50",
        spec=_spec("seed/zero_jsge1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JSGE1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # P26 additions — JLE boundary cases (0xB5, unsigned <=):
    # JLE unsigned: 0 <= 0 (equal). Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/zero_jle0_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/zero_jle0_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JLE0_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JLE unsigned: 1 <= 0? No. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/one_jle0_mov50_exit_r0_eq_50",
        spec=_spec("seed/one_jle0_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_ONE_JLE0_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JLE unsigned: UINT64_MAX-1 <= UINT64_MAX. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/neg2_jle_neg1_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg2_jle_neg1_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG2_JLE_NEG1_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JLE unsigned: UINT64_MAX <= UINT64_MAX-1? No. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg1_jle_neg2_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg1_jle_neg2_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JLE_NEG2_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # P27 additions — JGT zero-boundary and unsigned sign-crossing:
    # JGT: 0 > 0? No (strict, equal not taken). r0=50 executes.
    CorpusTask(
        task_id="seed/zero_jgt0_mov50_exit_r0_eq_50",
        spec=_spec("seed/zero_jgt0_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JGT0_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JGT: 1 > 0. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/one_jgt0_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/one_jgt0_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_ONE_JGT0_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JGT unsigned: UINT64_MAX > UINT64_MAX (equal)? No. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg1_jgt_neg1_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg1_jgt_neg1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JGT_NEG1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JGT unsigned: 0 > UINT64_MAX? No (unsigned sign-crossing). Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/zero_jgt_neg1_mov50_exit_r0_eq_50",
        spec=_spec("seed/zero_jgt_neg1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JGT_NEG1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # P28 additions — JLT zero-boundary and unsigned sign-crossing:
    # JLT: 0 < 0? No (strict, equal not taken). r0=50 executes.
    CorpusTask(
        task_id="seed/zero_jlt0_mov50_exit_r0_eq_50",
        spec=_spec("seed/zero_jlt0_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JLT0_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JLT: 1 < 2. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/one_jlt2_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/one_jlt2_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_ONE_JLT2_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JLT unsigned: UINT64_MAX < UINT64_MAX (equal)? No. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg1_jlt_neg1_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg1_jlt_neg1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JLT_NEG1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JLT unsigned: UINT64_MAX < 0? No (unsigned sign-crossing). Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg1_jlt0_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg1_jlt0_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JLT0_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # P29 additions — JGE zero-boundary and unsigned sign-crossing:
    # JGE: 0 >= 0 (equal). Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/zero_jge0_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/zero_jge0_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JGE0_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JGE: 1 >= 0. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/one_jge0_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/one_jge0_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_ONE_JGE0_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JGE unsigned: UINT64_MAX >= UINT64_MAX-1 (strictly greater). Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/neg1_jge_neg2_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg1_jge_neg2_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JGE_NEG2_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JGE unsigned: 0 >= UINT64_MAX? No (sign-crossing). Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/zero_jge_neg1_mov50_exit_r0_eq_50",
        spec=_spec("seed/zero_jge_neg1_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JGE_NEG1_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # P30 additions — JEQ zero-boundary and UINT64_MAX cases:
    # JEQ: 0 == 0. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/zero_jeq0_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/zero_jeq0_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_ZERO_JEQ0_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JEQ: 1 == 0? No. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/one_jeq0_mov50_exit_r0_eq_50",
        spec=_spec("seed/one_jeq0_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_ONE_JEQ0_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # JEQ: UINT64_MAX == UINT64_MAX. Taken. r0=50 skipped.
    CorpusTask(
        task_id="seed/neg1_jeq_neg1_mov50_exit_r0_eq_50_unreachable",
        spec=_spec("seed/neg1_jeq_neg1_mov50_exit_r0_eq_50_unreachable", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JEQ_NEG1_MOV50_EXIT,
        expected_verdict="unreachable",
    ),
    # JEQ: UINT64_MAX == 0? No. Not taken. r0=50 executes.
    CorpusTask(
        task_id="seed/neg1_jeq0_mov50_exit_r0_eq_50",
        spec=_spec("seed/neg1_jeq0_mov50_exit_r0_eq_50", "r0 == 50", max_insns=8),
        bytecode=_NEG1_JEQ0_MOV50_EXIT,
        expected_verdict="reachable",
    ),
    # P31 additions — JNE additional boundary cases:
    # JNE: 1 != 1? No. Not taken. r0=99 executes.
    CorpusTask(
        task_id="seed/one_jne1_mov99_exit_r0_eq_99",
        spec=_spec("seed/one_jne1_mov99_exit_r0_eq_99", "r0 == 99", max_insns=8),
        bytecode=_ONE_JNE1_MOV99_EXIT,
        expected_verdict="reachable",
    ),
    # JNE: 0 != 1. Taken. r0=99 skipped.
    CorpusTask(
        task_id="seed/zero_jne1_mov99_exit_r0_eq_99_unreachable",
        spec=_spec("seed/zero_jne1_mov99_exit_r0_eq_99_unreachable", "r0 == 99", max_insns=8),
        bytecode=_ZERO_JNE1_MOV99_EXIT,
        expected_verdict="unreachable",
    ),
    # JNE: UINT64_MAX != UINT64_MAX? No. Not taken. r0=99 executes.
    CorpusTask(
        task_id="seed/neg1_jne_neg1_mov99_exit_r0_eq_99",
        spec=_spec("seed/neg1_jne_neg1_mov99_exit_r0_eq_99", "r0 == 99", max_insns=8),
        bytecode=_NEG1_JNE_NEG1_MOV99_EXIT,
        expected_verdict="reachable",
    ),
    # JNE: UINT64_MAX != 1. Taken. r0=99 skipped.
    CorpusTask(
        task_id="seed/neg1_jne1_mov99_exit_r0_eq_99_unreachable",
        spec=_spec("seed/neg1_jne1_mov99_exit_r0_eq_99_unreachable", "r0 == 99", max_insns=8),
        bytecode=_NEG1_JNE1_MOV99_EXIT,
        expected_verdict="unreachable",
    ),
    # P32 additions — JSET additional boundary cases:
    # JSET: 1 & 1 = 1 != 0. Taken. r0=99 skipped.
    CorpusTask(
        task_id="seed/one_jset1_mov99_exit_r0_eq_99_unreachable",
        spec=_spec("seed/one_jset1_mov99_exit_r0_eq_99_unreachable", "r0 == 99", max_insns=8),
        bytecode=_ONE_JSET1_MOV99_EXIT,
        expected_verdict="unreachable",
    ),
    # JSET: 1 & 2 = 0. Not taken. r0=99 executes.
    CorpusTask(
        task_id="seed/one_jset2_mov99_exit_r0_eq_99",
        spec=_spec("seed/one_jset2_mov99_exit_r0_eq_99", "r0 == 99", max_insns=8),
        bytecode=_ONE_JSET2_MOV99_EXIT,
        expected_verdict="reachable",
    ),
    # JSET: UINT64_MAX & UINT64_MAX != 0. Taken. r0=99 skipped.
    CorpusTask(
        task_id="seed/neg1_jset_neg1_mov99_exit_r0_eq_99_unreachable",
        spec=_spec("seed/neg1_jset_neg1_mov99_exit_r0_eq_99_unreachable", "r0 == 99", max_insns=8),
        bytecode=_NEG1_JSET_NEG1_MOV99_EXIT,
        expected_verdict="unreachable",
    ),
    # JSET: 0 & 1 = 0. Not taken. r0=99 executes.
    CorpusTask(
        task_id="seed/zero_jset1_mov99_exit_r0_eq_99",
        spec=_spec("seed/zero_jset1_mov99_exit_r0_eq_99", "r0 == 99", max_insns=8),
        bytecode=_ZERO_JSET1_MOV99_EXIT,
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
