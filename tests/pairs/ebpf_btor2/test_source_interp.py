"""Tests for the P2 eBPF source interpreter.

Covers: bytecode decoding, all ALU64 ops, all JMP flavours, EXIT,
halted-freeze semantics, out-of-bounds freeze, determinism, and two
hand-crafted byte-sequence programs.
"""

from __future__ import annotations

import struct

import pytest

from gurdy.pairs.ebpf_btor2.source_interp import (
    BpfInsn,
    EbpfInputBinding,
    EbpfMachineState,
    INTERPRETER_VERSION,
    PAIR_ID,
    R10_BASE,
    decode_program,
    run,
    step,
)


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def _insn(opcode: int, dst: int = 0, src: int = 0, off: int = 0, imm: int = 0) -> bytes:
    """Encode one 8-byte bpf_insn."""
    return struct.pack("<BBhi", opcode, (src << 4) | dst, off, imm)


_EXIT = _insn(0x95)


def _regs(*vals: int) -> tuple[int, ...]:
    """Build a 10-element register tuple; unspecified regs default to 0."""
    base = list(vals) + [0] * (10 - len(vals))
    return tuple(base[:10])


def _binding(bytecode: bytes, **init_regs: int) -> EbpfInputBinding:
    regs = _regs(*[init_regs.get(f"r{i}", 0) for i in range(10)])
    return EbpfInputBinding(bytecode=bytecode, initial_regs=regs)


# ---------------------------------------------------------------------------
# decode_program
# ---------------------------------------------------------------------------

class TestDecodeProgram:
    def test_basic_two_insns(self):
        bytecode = _insn(0x07, dst=0, imm=5) + _EXIT
        insns = decode_program(bytecode)
        assert len(insns) == 2
        assert insns[0].opcode == 0x07
        assert insns[0].dst_reg == 0
        assert insns[0].imm == 5
        assert insns[1].opcode == 0x95

    def test_dst_src_decoding(self):
        # dst=3, src=7
        bytecode = _insn(0x0F, dst=3, src=7) + _EXIT
        insns = decode_program(bytecode)
        assert insns[0].dst_reg == 3
        assert insns[0].src_reg == 7

    def test_signed_off(self):
        bytecode = _insn(0x05, off=-1) + _EXIT
        insns = decode_program(bytecode)
        assert insns[0].off == -1

    def test_signed_imm(self):
        bytecode = _insn(0x07, imm=-42) + _EXIT
        insns = decode_program(bytecode)
        assert insns[0].imm == -42

    def test_bad_length_raises(self):
        with pytest.raises(ValueError, match="0000"):
            decode_program(b"\x95" * 5)

    def test_wide_imm_rejected(self):
        bytecode = _insn(0x18) + _insn(0x00) + _EXIT
        with pytest.raises(ValueError, match="0001"):
            decode_program(bytecode)

    def test_insn_properties(self):
        # opcode 0x2f: op_nibble=2, src_flag=1, cls=7 (ALU64 X)
        bytecode = _insn(0x2F, dst=1, src=2) + _EXIT
        insns = decode_program(bytecode)
        assert insns[0].cls == 0x07
        assert insns[0].src_flag == 1
        assert insns[0].op_nibble == 0x2


# ---------------------------------------------------------------------------
# ALU64 operations via step()
# ---------------------------------------------------------------------------

def _state(insn_idx: int = 0, halted: bool = False, **reg_vals: int) -> EbpfMachineState:
    regs = _regs(*[reg_vals.get(f"r{i}", 0) for i in range(10)])
    return EbpfMachineState(regs=regs, insn_idx=insn_idx, halted=halted)


class TestAlu64:
    def _run_one(self, opcode: int, dst_val: int, src_val: int, dst: int = 0, src: int = 1) -> int:
        bytecode = _insn(opcode, dst=dst, src=src) + _EXIT
        insns = decode_program(bytecode)
        regs = list(_regs())
        regs[dst] = dst_val
        regs[src] = src_val
        state = EbpfMachineState(regs=tuple(regs), insn_idx=0, halted=False)
        new_state = step(insns, state)
        return new_state.regs[dst]

    def test_add_k(self):
        bytecode = _insn(0x07, dst=0, imm=5) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=10)
        ns = step(insns, s)
        assert ns.regs[0] == 15
        assert ns.insn_idx == 1

    def test_add_x(self):
        result = self._run_one(0x0F, dst_val=10, src_val=7)
        assert result == 17

    def test_add_wraps(self):
        MASK64 = (1 << 64) - 1
        result = self._run_one(0x0F, dst_val=MASK64, src_val=1)
        assert result == 0

    def test_sub_k(self):
        bytecode = _insn(0x17, dst=0, imm=3) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=10)
        ns = step(insns, s)
        assert ns.regs[0] == 7

    def test_sub_wraps(self):
        result = self._run_one(0x1F, dst_val=0, src_val=1)
        assert result == (1 << 64) - 1

    def test_mul_k(self):
        bytecode = _insn(0x27, dst=0, imm=6) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=7)
        ns = step(insns, s)
        assert ns.regs[0] == 42

    def test_div_k(self):
        bytecode = _insn(0x37, dst=0, imm=4) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=20)
        ns = step(insns, s)
        assert ns.regs[0] == 5

    def test_div_by_zero_returns_zero(self):
        result = self._run_one(0x3F, dst_val=42, src_val=0)
        assert result == 0

    def test_or_k(self):
        bytecode = _insn(0x47, dst=0, imm=0b1010) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=0b0101)
        ns = step(insns, s)
        assert ns.regs[0] == 0b1111

    def test_and_k(self):
        bytecode = _insn(0x57, dst=0, imm=0b1100) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=0b1010)
        ns = step(insns, s)
        assert ns.regs[0] == 0b1000

    def test_lsh_k(self):
        bytecode = _insn(0x67, dst=0, imm=3) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=1)
        ns = step(insns, s)
        assert ns.regs[0] == 8

    def test_lsh_masks_shift_count(self):
        # shift by 64 should be masked to 0 → result is same as shift by 0
        result = self._run_one(0x6F, dst_val=1, src_val=64)
        assert result == 1  # shift by 0

    def test_rsh_k(self):
        bytecode = _insn(0x77, dst=0, imm=2) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=16)
        ns = step(insns, s)
        assert ns.regs[0] == 4

    def test_neg(self):
        bytecode = _insn(0x87, dst=0) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=1)
        ns = step(insns, s)
        assert ns.regs[0] == (1 << 64) - 1  # -1 as unsigned bv64

    def test_neg_zero(self):
        bytecode = _insn(0x87, dst=0) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=0)
        ns = step(insns, s)
        assert ns.regs[0] == 0

    def test_mod_k(self):
        bytecode = _insn(0x97, dst=0, imm=3) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=10)
        ns = step(insns, s)
        assert ns.regs[0] == 1

    def test_mod_by_zero_returns_dst(self):
        result = self._run_one(0x9F, dst_val=42, src_val=0)
        assert result == 42

    def test_xor_k(self):
        bytecode = _insn(0xA7, dst=0, imm=0xFF) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=0xAA)
        ns = step(insns, s)
        assert ns.regs[0] == 0x55

    def test_arsh_positive(self):
        bytecode = _insn(0xC7, dst=0, imm=1) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=8)
        ns = step(insns, s)
        assert ns.regs[0] == 4

    def test_arsh_negative(self):
        # -8 as bv64, arsh by 1 should be -4
        neg8 = (-8) & ((1 << 64) - 1)
        neg4 = (-4) & ((1 << 64) - 1)
        bytecode = _insn(0xC7, dst=0, imm=1) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=neg8)
        ns = step(insns, s)
        assert ns.regs[0] == neg4

    def test_arsh_masks_shift_count(self):
        # shift by 64 masks to 0
        result = self._run_one(0xCF, dst_val=8, src_val=64)
        assert result == 8  # shift by 0

    def test_insn_idx_advances(self):
        bytecode = _insn(0x07, dst=0, imm=1) + _insn(0x07, dst=0, imm=2) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=0)
        s1 = step(insns, s)
        assert s1.insn_idx == 1
        s2 = step(insns, s1)
        assert s2.insn_idx == 2
        assert s2.regs[0] == 3


# ---------------------------------------------------------------------------
# JMP operations via step()
# ---------------------------------------------------------------------------

class TestJmp:
    def _jmp_state(self, dst_val: int, src_val: int = 0, dst: int = 0, src: int = 1) -> tuple[list[BpfInsn], EbpfMachineState]:
        regs = list(_regs())
        regs[dst] = dst_val
        regs[src] = src_val
        state = EbpfMachineState(regs=tuple(regs), insn_idx=0, halted=False)
        return state

    def test_ja(self):
        # JA off=2 → insn_idx = 0 + 1 + 2 = 3
        bytecode = _insn(0x05, off=2) + _EXIT + _EXIT + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state()
        ns = step(insns, s)
        assert ns.insn_idx == 3

    def test_jeq_taken(self):
        # JEQ K dst=r0, imm=10, off=1 — with r0=10 → jump taken
        bytecode = _insn(0x15, dst=0, off=1, imm=10) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=10)
        ns = step(insns, s)
        assert ns.insn_idx == 2  # 0 + 1 + 1

    def test_jeq_not_taken(self):
        bytecode = _insn(0x15, dst=0, off=1, imm=10) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=99)
        ns = step(insns, s)
        assert ns.insn_idx == 1

    def test_jeq_x(self):
        bytecode = _insn(0x1D, dst=0, src=1, off=1) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=7, r1=7)
        ns = step(insns, s)
        assert ns.insn_idx == 2

    def test_jgt_taken(self):
        bytecode = _insn(0x25, dst=0, off=1, imm=5) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=10)
        ns = step(insns, s)
        assert ns.insn_idx == 2

    def test_jgt_not_taken_equal(self):
        bytecode = _insn(0x25, dst=0, off=1, imm=10) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=10)
        ns = step(insns, s)
        assert ns.insn_idx == 1

    def test_jge_taken_equal(self):
        bytecode = _insn(0x35, dst=0, off=1, imm=10) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=10)
        ns = step(insns, s)
        assert ns.insn_idx == 2

    def test_jset(self):
        bytecode = _insn(0x45, dst=0, off=1, imm=0b0011) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=0b0010)
        ns = step(insns, s)
        assert ns.insn_idx == 2  # 0b0010 & 0b0011 != 0 → taken

    def test_jne_taken(self):
        bytecode = _insn(0x55, dst=0, off=1, imm=5) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=10)
        ns = step(insns, s)
        assert ns.insn_idx == 2

    def test_jsgt_signed(self):
        # -1 as bv64 is large unsigned but signed is -1 < 0
        neg1 = (-1) & ((1 << 64) - 1)
        bytecode = _insn(0x65, dst=0, off=1, imm=0) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=neg1)
        ns = step(insns, s)
        # -1 s> 0? No
        assert ns.insn_idx == 1

    def test_jsge_signed(self):
        bytecode = _insn(0x75, dst=0, off=1, imm=0) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=0)
        ns = step(insns, s)
        # 0 s>= 0? Yes
        assert ns.insn_idx == 2

    def test_jlt_taken(self):
        bytecode = _insn(0xA5, dst=0, off=1, imm=10) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=5)
        ns = step(insns, s)
        assert ns.insn_idx == 2

    def test_jle_taken_equal(self):
        bytecode = _insn(0xB5, dst=0, off=1, imm=10) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=10)
        ns = step(insns, s)
        assert ns.insn_idx == 2

    def test_jslt_signed(self):
        neg1 = (-1) & ((1 << 64) - 1)
        bytecode = _insn(0xC5, dst=0, off=1, imm=0) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=neg1)
        ns = step(insns, s)
        # -1 s< 0? Yes
        assert ns.insn_idx == 2

    def test_jsle_signed_equal(self):
        bytecode = _insn(0xD5, dst=0, off=1, imm=5) + _EXIT + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=5)
        ns = step(insns, s)
        # 5 s<= 5? Yes
        assert ns.insn_idx == 2

    def test_branch_does_not_write_registers(self):
        bytecode = _insn(0x15, dst=0, off=0, imm=0) + _EXIT
        insns = decode_program(bytecode)
        s = _state(r0=0)
        ns = step(insns, s)
        assert ns.regs == s.regs


# ---------------------------------------------------------------------------
# EXIT and halted semantics
# ---------------------------------------------------------------------------

class TestExit:
    def test_exit_sets_halted(self):
        insns = decode_program(_EXIT)
        s = _state()
        ns = step(insns, s)
        assert ns.halted is True

    def test_exit_freezes_insn_idx(self):
        insns = decode_program(_EXIT)
        s = _state(insn_idx=0)
        ns = step(insns, s)
        assert ns.insn_idx == 0

    def test_exit_preserves_regs(self):
        insns = decode_program(_EXIT)
        s = _state(r0=99)
        ns = step(insns, s)
        assert ns.regs[0] == 99

    def test_halted_freeze_on_subsequent_step(self):
        insns = decode_program(_EXIT + _insn(0x07, dst=0, imm=1))
        s = _state()
        s1 = step(insns, s)      # executes EXIT
        assert s1.halted
        s2 = step(insns, s1)     # must freeze
        assert s2 == s1

    def test_out_of_bounds_freezes(self):
        insns = decode_program(_EXIT)
        s = EbpfMachineState(regs=_regs(), insn_idx=999, halted=False)
        ns = step(insns, s)
        assert ns == s


# ---------------------------------------------------------------------------
# run() function
# ---------------------------------------------------------------------------

class TestRun:
    def test_run_simple_add_then_exit(self):
        # r0 += 5; EXIT   (initial r0=10 → final r0=15)
        bytecode = _insn(0x07, dst=0, imm=5) + _EXIT
        trace = run(_binding(bytecode, r0=10))
        assert trace.halted is True
        assert trace.halt_reason == "exit"
        assert trace.final_state["r0"] == 15
        assert trace.pair == PAIR_ID
        assert trace.interpreter_version == INTERPRETER_VERSION

    def test_run_step_count(self):
        # 3 ALU instructions then EXIT → 4 cycles + initial state = 5 steps
        bytecode = (
            _insn(0x07, dst=0, imm=1)
            + _insn(0x07, dst=0, imm=2)
            + _insn(0x07, dst=0, imm=3)
            + _EXIT
        )
        trace = run(_binding(bytecode))
        # step 0 (initial) + steps 1,2,3 (ALU) + step 4 (EXIT)
        assert len(trace.steps) == 5

    def test_run_initial_step_has_no_deltas(self):
        bytecode = _insn(0x07, dst=0, imm=1) + _EXIT
        trace = run(_binding(bytecode))
        assert trace.steps[0].step == 0
        assert trace.steps[0].deltas is None

    def test_run_max_steps_stops_loop(self):
        # Infinite loop: JA off=-1 (back to itself)
        bytecode = _insn(0x05, off=-1)
        trace = run(_binding(bytecode), max_steps=10)
        assert trace.halt_reason == "max_steps"
        assert trace.halted is False

    def test_run_out_of_bounds(self):
        # JA off=5 jumps past end
        bytecode = _insn(0x05, off=5) + _EXIT
        trace = run(_binding(bytecode))
        assert trace.halt_reason == "out_of_bounds"

    def test_run_determinism(self):
        bytecode = (
            _insn(0x07, dst=0, imm=3)
            + _insn(0x17, dst=1, imm=1)
            + _EXIT
        )
        b = _binding(bytecode, r0=10, r1=5)
        t1 = run(b)
        t2 = run(b)
        assert t1.final_state == t2.final_state
        assert t1.inputs_hash == t2.inputs_hash
        assert len(t1.steps) == len(t2.steps)

    def test_run_deltas_track_changes(self):
        # r0 += 7; EXIT
        bytecode = _insn(0x07, dst=0, imm=7) + _EXIT
        trace = run(_binding(bytecode, r0=1))
        # step 1 executed the ADD; r0 should appear in deltas
        step1 = trace.steps[1]
        assert step1.deltas is not None
        assert "r0" in step1.deltas
        assert step1.deltas["r0"] == 8

    def test_run_unchanged_regs_not_in_deltas(self):
        bytecode = _insn(0x07, dst=0, imm=1) + _EXIT
        trace = run(_binding(bytecode))
        step1 = trace.steps[1]
        assert step1.deltas is not None
        assert "r1" not in step1.deltas

    def test_run_inputs_hash_stable(self):
        bytecode = _EXIT
        b = _binding(bytecode)
        t = run(b)
        assert t.inputs_hash == b.inputs_hash()


# ---------------------------------------------------------------------------
# Hand-crafted byte-sequence programs
# ---------------------------------------------------------------------------

class TestHandCraftedPrograms:
    def test_add_mul_exit(self):
        """r0 = r0 * 3 + 2 with initial r0 = 5 → r0 = 17."""
        bytecode = (
            _insn(0x27, dst=0, imm=3)    # r0 *= 3  → 15
            + _insn(0x07, dst=0, imm=2)  # r0 += 2  → 17
            + _EXIT
        )
        trace = run(_binding(bytecode, r0=5))
        assert trace.final_state["r0"] == 17
        assert trace.halted is True

    def test_branch_taken_skips_add(self):
        """JEQ taken (r0==10) skips r0+=1; final r0 should be 10."""
        bytecode = (
            _insn(0x15, dst=0, off=1, imm=10)  # JEQ K r0, 10, off=1
            + _insn(0x07, dst=0, imm=1)         # r0 += 1  (skipped)
            + _EXIT
        )
        trace = run(_binding(bytecode, r0=10))
        assert trace.final_state["r0"] == 10

    def test_branch_not_taken_executes_add(self):
        """JEQ not taken (r0==99) falls through to r0+=1; final r0 = 100."""
        bytecode = (
            _insn(0x15, dst=0, off=1, imm=10)  # JEQ K r0, 10, off=1
            + _insn(0x07, dst=0, imm=1)         # r0 += 1  (executed)
            + _EXIT
        )
        trace = run(_binding(bytecode, r0=99))
        assert trace.final_state["r0"] == 100

    def test_loop_three_iterations(self):
        """r1 counts down from 3 to 0; r0 accumulates 1 each iteration.

        Program:
          0: JEQ r1, 0, +2   → if r1==0 skip to EXIT
          1: r0 += 1
          2: r1 -= 1
          3: JA -4            → jump back to insn 0 (3+1-4 = 0)
          4: EXIT
        """
        bytecode = (
            _insn(0x15, dst=1, off=3, imm=0)    # insn 0: JEQ r1, 0, +3 → insn 4
            + _insn(0x07, dst=0, imm=1)          # insn 1: r0 += 1
            + _insn(0x17, dst=1, imm=1)          # insn 2: r1 -= 1
            + _insn(0x05, off=-4)                # insn 3: JA -4 → 3+1-4=0
            + _EXIT                              # insn 4
        )
        trace = run(_binding(bytecode, r0=0, r1=3))
        assert trace.final_state["r0"] == 3
        assert trace.final_state["r1"] == 0
        assert trace.halted is True

    def test_xor_self_zeroes_register(self):
        """r0 XOR r0 = 0 regardless of initial value."""
        bytecode = _insn(0xAF, dst=0, src=0) + _EXIT
        trace = run(_binding(bytecode, r0=0xDEADBEEF))
        assert trace.final_state["r0"] == 0


# ---------------------------------------------------------------------------
# Unsupported opcodes
# ---------------------------------------------------------------------------

class TestUnsupportedOpcodes:
    def test_call_rejected(self):
        # 0x85 = BPF_CALL — not in P1
        bytecode = _insn(0x85, imm=1) + _EXIT
        insns = decode_program(bytecode)
        s = _state()
        with pytest.raises(ValueError, match="0003"):
            step(insns, s)

    def test_unknown_alu64_op_rejected(self):
        # op nibble 0xe is not a valid eBPF ALU op (0x0-0xc are defined, incl.
        # MOV=0xb which later phases added); opcode = 0xe << 4 | 0 << 3 | 7 = 0xe7
        bytecode = _insn(0xE7, dst=0, imm=1) + _EXIT
        insns = decode_program(bytecode)
        s = _state()
        with pytest.raises(ValueError, match="0003"):
            step(insns, s)
