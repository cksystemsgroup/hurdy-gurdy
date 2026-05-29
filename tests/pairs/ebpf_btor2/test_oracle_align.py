"""Tests for the P5 ebpf-btor2 alignment oracle.

Verifies that ``align(source_trace, reasoning_trace, artifact)`` correctly
detects agreement and disagreement between the source and reasoning
interpreters on the P4 seed programs.

Seed programs (reused from test_translation.py):
  _EXIT_ONLY    : [EXIT]
  _ADD_EXIT     : [r0 += 1, EXIT]
  _ADD_X_EXIT   : [r1 += r0, EXIT]
  _BRANCH_EXIT  : [JEQ K r0==5 +1, r0 ^= 0, EXIT]
  _JA_EXIT      : [JA +1, r0 += 99 (skipped), EXIT]

Initial-register contract: source register values are reconstructed from
deltas, seeded at zero.  Each aligned test uses initial_regs such that
any non-zero register either (a) appears in the first step's delta because
it is modified by the first instruction, or (b) starts at zero.
"""

from __future__ import annotations

import struct

import pytest

from gurdy.pairs.ebpf_btor2.oracle_align import AlignmentFailure, align
from gurdy.pairs.ebpf_btor2.reasoning_interp import (
    EbpfReasoningBinding,
    EbpfReasoningInterpreter,
)
from gurdy.pairs.ebpf_btor2.source_interp import EbpfInputBinding
from gurdy.pairs.ebpf_btor2.source_interp import run as src_run
from gurdy.pairs.ebpf_btor2.spec import EbpfBtor2Spec, EbpfProgramRef, Property
from gurdy.pairs.ebpf_btor2.translation import translate


# ---------------------------------------------------------------------------
# Bytecode fixtures (identical to test_translation.py)
# ---------------------------------------------------------------------------


def _insn(opcode: int, dst: int, src: int, off: int, imm: int) -> bytes:
    return struct.pack("<BBhi", opcode, (src << 4) | dst, off, imm)


_EXIT_ONLY = _insn(0x95, 0, 0, 0, 0)

_ADD_EXIT = (
    _insn(0x07, 0, 0, 0, 1)    # r0 += 1
    + _insn(0x95, 0, 0, 0, 0)  # EXIT
)

_ADD_X_EXIT = (
    _insn(0x0F, 1, 0, 0, 0)    # r1 += r0
    + _insn(0x95, 0, 0, 0, 0)  # EXIT
)

_BRANCH_EXIT = (
    _insn(0x15, 0, 0, 1, 5)    # JEQ K: if r0==5, skip 1
    + _insn(0xA7, 0, 0, 0, 0)  # r0 ^= 0 (no-op XOR)
    + _insn(0x95, 0, 0, 0, 0)  # EXIT
)

_JA_EXIT = (
    _insn(0x05, 0, 0, 1, 0)    # JA +1 (skip next)
    + _insn(0x07, 0, 0, 0, 99) # r0 += 99 (skipped)
    + _insn(0x95, 0, 0, 0, 0)  # EXIT
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec(expression: str = "false") -> EbpfBtor2Spec:
    return EbpfBtor2Spec(
        program=EbpfProgramRef(path="test"),
        property=Property(expression=expression),
    )


def _run_both(bytecode: bytes, initial_regs: tuple[int, ...], max_steps: int = 6):
    art = translate(_spec(), bytecode)
    src_trace = src_run(EbpfInputBinding(bytecode=bytecode, initial_regs=initial_regs))
    binding = EbpfReasoningBinding(
        state_init_by_symbol={
            f"reg_r{i}": v for i, v in enumerate(initial_regs)
        }
    )
    r_trace = EbpfReasoningInterpreter().run(art, binding, max_steps=max_steps)
    return src_trace, r_trace, art


# ---------------------------------------------------------------------------
# Aligned tests — seed programs with all-zero or delta-covered initial regs
# ---------------------------------------------------------------------------


def test_align_exit_only_aligned():
    """EXIT-only program; all regs zero; no register deltas; traces agree."""
    src, r, art = _run_both(_EXIT_ONLY, (0,) * 10)
    failures, aligned = align(src, r, art)
    assert aligned
    assert failures == []


def test_align_add_exit_aligned():
    """r0 += 1 then EXIT; r0 initial=5, delta at step 1 sets r0=6."""
    src, r, art = _run_both(_ADD_EXIT, (5,) + (0,) * 9)
    failures, aligned = align(src, r, art)
    assert aligned
    assert failures == []


def test_align_add_x_exit_aligned():
    """r1 += r0 then EXIT; all regs zero; r1 stays 0; traces agree."""
    src, r, art = _run_both(_ADD_X_EXIT, (0,) * 10)
    failures, aligned = align(src, r, art)
    assert aligned
    assert failures == []


def test_align_branch_not_taken_aligned():
    """JEQ r0==5 not taken (r0=0), XOR no-op, EXIT; all regs zero."""
    src, r, art = _run_both(_BRANCH_EXIT, (0,) * 10)
    failures, aligned = align(src, r, art)
    assert aligned
    assert failures == []


def test_align_ja_exit_aligned():
    """JA skips r0 += 99; r0 stays zero throughout; traces agree."""
    src, r, art = _run_both(_JA_EXIT, (0,) * 10)
    failures, aligned = align(src, r, art)
    assert aligned
    assert failures == []


# ---------------------------------------------------------------------------
# Misaligned tests — detect register disagreements
# ---------------------------------------------------------------------------


def test_align_detects_r0_mismatch():
    """Source r0=5 (→6 after ADD), reasoning r0=10 (→11); oracle flags it."""
    src_initial = (5,) + (0,) * 9
    r_initial = (10,) + (0,) * 9
    art = translate(_spec(), _ADD_EXIT)
    src_trace = src_run(EbpfInputBinding(bytecode=_ADD_EXIT, initial_regs=src_initial))
    binding = EbpfReasoningBinding(
        state_init_by_symbol={f"reg_r{i}": v for i, v in enumerate(r_initial)}
    )
    r_trace = EbpfReasoningInterpreter().run(art, binding, max_steps=6)

    failures, aligned = align(src_trace, r_trace, art)
    assert not aligned
    assert len(failures) >= 1
    r0_fail = next(f for f in failures if f.symbol == "reg_r0")
    assert r0_fail.src_val == 6   # 5 + 1
    assert r0_fail.r_val == 11    # 10 + 1


def test_align_failure_has_correct_step():
    """AlignmentFailure.step is the source step index (reasoning step + 1)."""
    src_initial = (5,) + (0,) * 9
    r_initial = (10,) + (0,) * 9
    art = translate(_spec(), _ADD_EXIT)
    src_trace = src_run(EbpfInputBinding(bytecode=_ADD_EXIT, initial_regs=src_initial))
    binding = EbpfReasoningBinding(
        state_init_by_symbol={f"reg_r{i}": v for i, v in enumerate(r_initial)}
    )
    r_trace = EbpfReasoningInterpreter().run(art, binding, max_steps=6)

    failures, _ = align(src_trace, r_trace, art)
    r0_fail = next(f for f in failures if f.symbol == "reg_r0")
    # Step 1 = after executing the ADD instruction.
    assert r0_fail.step == 1


def test_align_not_aligned_flag_is_false_on_mismatch():
    """The boolean return value is False when any failure is present."""
    src_initial = (5,) + (0,) * 9
    r_initial = (10,) + (0,) * 9
    art = translate(_spec(), _ADD_EXIT)
    src_trace = src_run(EbpfInputBinding(bytecode=_ADD_EXIT, initial_regs=src_initial))
    binding = EbpfReasoningBinding(
        state_init_by_symbol={f"reg_r{i}": v for i, v in enumerate(r_initial)}
    )
    r_trace = EbpfReasoningInterpreter().run(art, binding, max_steps=6)

    _, aligned = align(src_trace, r_trace, art)
    assert aligned is False


def test_align_r1_mismatch_after_add_x():
    """r1 += r0 with mismatched initial r1; oracle flags reg_r1."""
    # source: r1=10 (→10+0=10, no change since r0=0), but r_initial has r1=20
    # Actually: with r0=0 and r1=10, r1 += 0 = 10, no delta for r1.
    # So source reconstructed r1=0, but reasoning r1=10.
    # This tests that unchanged registers from non-zero initial cause failures
    # (documenting the known limitation while verifying the oracle catches it).
    src_initial = (0,) + (10,) + (0,) * 8   # r0=0, r1=10
    r_initial = (0,) + (20,) + (0,) * 8     # r0=0, r1=20
    art = translate(_spec(), _ADD_X_EXIT)
    src_trace = src_run(EbpfInputBinding(bytecode=_ADD_X_EXIT, initial_regs=src_initial))
    binding = EbpfReasoningBinding(
        state_init_by_symbol={f"reg_r{i}": v for i, v in enumerate(r_initial)}
    )
    r_trace = EbpfReasoningInterpreter().run(art, binding, max_steps=6)

    failures, aligned = align(src_trace, r_trace, art)
    # r1 mismatch: src reconstructed as 0, reasoning as 20
    assert not aligned
    r1_fail = next(f for f in failures if f.symbol == "reg_r1")
    assert r1_fail.src_val == 0
    assert r1_fail.r_val == 20


def test_align_no_steps_in_reasoning_no_comparison():
    """Zero reasoning steps → nothing compared → aligned=True, failures=[]."""
    src_initial = (0,) * 10
    art = translate(_spec(), _EXIT_ONLY)
    src_trace = src_run(EbpfInputBinding(bytecode=_EXIT_ONLY, initial_regs=src_initial))
    binding = EbpfReasoningBinding()
    from gurdy.core.interp.types import ReasoningTrace
    r_trace = ReasoningTrace(
        pair="ebpf-btor2",
        interpreter_version="1.0.0",
        artifact_hash="",
        bindings_hash="",
        steps=(),
    )
    failures, aligned = align(src_trace, r_trace, art)
    assert aligned
    assert failures == []


def test_align_add_exit_halted_step_included():
    """Both steps (ADD and EXIT) are checked; r0 must agree at EXIT step too."""
    src, r, art = _run_both(_ADD_EXIT, (3,) + (0,) * 9)
    # Verify two comparison points exist (k=0: ADD step, k=1: EXIT step).
    assert len(src.steps) == 3   # step0=init, step1=ADD, step2=EXIT
    assert len(r.steps) >= 2
    failures, aligned = align(src, r, art)
    assert aligned
    assert failures == []
