"""Tests for ``RiscvSourceInterpreter`` — the framework wrapper around
the RV64 simulator.
"""

from __future__ import annotations

import pytest

from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
from gurdy.pairs.riscv_btor2.source_interp.bindings import RiscvInputBinding
from gurdy.pairs.riscv_btor2.source_interp.interpreter import (
    INTERPRETER_VERSION,
    RiscvSourceInterpreter,
)

from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000


def _build_simple_binary(tmp_path):
    # ADDI x10, x0, 1 ; ADDI x10, x10, 20 ; JALR x0, 0(x0) — terminates
    # via fetch_failed at PC 0 (no fetchable bytes).
    code = bytes.fromhex("13051000" "13054501" "67800000")
    p = tmp_path / "addchain.elf"
    p.write_bytes(
        build_elf(
            code,
            TEXT_BASE,
            [FuncDef(name="main", addr=TEXT_BASE, size=len(code))],
        )
    )
    return p


def test_run_produces_step_per_instruction(tmp_path):
    binary = _build_simple_binary(tmp_path)
    source = load_riscv_binary(binary)
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding()
    trace = interp.run(source, binding, max_steps=10)
    # First two instructions are ADDIs; third JALRs to 0 (fetch_failed there).
    assert trace.pair == "riscv-btor2"
    assert trace.interpreter_version == INTERPRETER_VERSION
    assert len(trace.steps) == 3  # addi, addi, jalr executed
    assert trace.steps[0].location["mnemonic"] == "ADDI"
    assert trace.steps[1].location["mnemonic"] == "ADDI"
    assert trace.steps[2].location["mnemonic"] == "JALR"


def test_post_step_register_visible_in_deltas(tmp_path):
    binary = _build_simple_binary(tmp_path)
    source = load_riscv_binary(binary)
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding()
    trace = interp.run(source, binding, max_steps=2)
    # After ADDI x10, x0, 1: x10 == 1
    regs0 = trace.steps[0].deltas["regs"]
    assert regs0[10] == 1
    # After ADDI x10, x10, 20: x10 == 21
    regs1 = trace.steps[1].deltas["regs"]
    assert regs1[10] == 21


def test_register_init_overrides_starting_state(tmp_path):
    # ADD x10, x10, x11 — uses initial values from x10/x11.
    code = bytes.fromhex("3305B500")  # ADD x10, x10, x11
    p = tmp_path / "add.elf"
    p.write_bytes(
        build_elf(
            code,
            TEXT_BASE,
            [FuncDef(name="main", addr=TEXT_BASE, size=len(code))],
        )
    )
    source = load_riscv_binary(p)
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding(register_init={10: 5, 11: 7})
    trace = interp.run(source, binding, max_steps=1)
    assert len(trace.steps) == 1
    assert trace.steps[0].deltas["regs"][10] == 12


def test_inputs_hash_stable_across_runs(tmp_path):
    a = RiscvInputBinding(register_init={10: 5, 11: 7})
    b = RiscvInputBinding(register_init={11: 7, 10: 5})  # same content, diff insert order
    assert a.inputs_hash() == b.inputs_hash()


def test_excluded_pc_range_terminates_run(tmp_path):
    binary = _build_simple_binary(tmp_path)
    source = load_riscv_binary(binary)

    class _Spec:
        class entry:
            excluded_pc_ranges = ((TEXT_BASE + 4, TEXT_BASE + 8),)  # exclude second instr

    interp = RiscvSourceInterpreter()
    trace = interp.run(source, RiscvInputBinding(), max_steps=10, spec=_Spec())
    # First instr executes; second is in the excluded range so we halt before it.
    assert len(trace.steps) == 1
    assert trace.halt_reason == "pc_in_excluded_range"
