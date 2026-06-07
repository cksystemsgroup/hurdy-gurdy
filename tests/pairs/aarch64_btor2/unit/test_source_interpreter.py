"""Tests for AArch64SourceInterpreter."""

from __future__ import annotations

import pytest

from gurdy.pairs.aarch64_btor2.source.loader import load_aarch64_binary
from gurdy.pairs.aarch64_btor2.source_interp.bindings import AArch64InputBinding
from gurdy.pairs.aarch64_btor2.source_interp.interpreter import (
    INTERPRETER_VERSION,
    AArch64SourceInterpreter,
)
from tests.fixtures.elf_builder_aarch64 import FuncDef, build_elf

TEXT_BASE = 0x400000

# NOP: 0xD503201F; SVC #0: 0xD4000001; RET: 0xD65F03C0
_NOP = bytes.fromhex("1F2003D5")
_SVC = bytes.fromhex("010000D4")
_RET = bytes.fromhex("C0035FD6")


def _make_source(code: bytes, tmp_path):
    p = tmp_path / "test.elf"
    p.write_bytes(build_elf(code, TEXT_BASE, [FuncDef("main", TEXT_BASE, len(code))]))
    return load_aarch64_binary(p)


def test_run_produces_step_per_instruction(tmp_path):
    source = _make_source(_NOP + _SVC, tmp_path)
    interp = AArch64SourceInterpreter()
    binding = AArch64InputBinding()
    trace = interp.run(source, binding, max_steps=10)
    assert trace.pair == "aarch64-btor2"
    assert trace.interpreter_version == INTERPRETER_VERSION
    # NOP executes, then SVC executes (SVC sets halted → loop stops after SVC)
    assert len(trace.steps) == 2
    assert trace.steps[0].location["mnemonic"] == "NOP"
    assert trace.steps[1].location["mnemonic"] == "SVC"
    assert trace.halted is True
    assert trace.halt_reason == "svc_or_brk"


def test_register_init_applied(tmp_path):
    # ADD X0, X1, #5 then SVC
    # ADD X0, X1, #5: 0x91001420
    code = bytes.fromhex("20140091") + _SVC
    source = _make_source(code, tmp_path)
    interp = AArch64SourceInterpreter()
    binding = AArch64InputBinding(register_init={1: 10})
    trace = interp.run(source, binding, max_steps=10)
    assert trace.steps[0].deltas["regs"][0] == 15


def test_sp_init_applied(tmp_path):
    source = _make_source(_NOP + _SVC, tmp_path)
    interp = AArch64SourceInterpreter()
    binding = AArch64InputBinding(sp_init=0x1000)
    trace = interp.run(source, binding, max_steps=2)
    assert trace.final_state["sp"] == 0x1000


def test_nzcv_init_applied(tmp_path):
    source = _make_source(_NOP + _SVC, tmp_path)
    interp = AArch64SourceInterpreter()
    binding = AArch64InputBinding(nzcv_init=0b0100)  # Z=1
    trace = interp.run(source, binding, max_steps=2)
    # NOP doesn't change NZCV
    assert trace.final_state["nzcv"] == 0b0100


def test_inputs_hash_stable(tmp_path):
    a = AArch64InputBinding(register_init={0: 1, 1: 2})
    b = AArch64InputBinding(register_init={1: 2, 0: 1})
    assert a.inputs_hash() == b.inputs_hash()


def test_fetch_failed_halt(tmp_path):
    # RET to PC=0 (nothing there → fetch_failed)
    source = _make_source(_RET, tmp_path)
    interp = AArch64SourceInterpreter()
    binding = AArch64InputBinding()
    trace = interp.run(source, binding, max_steps=10)
    assert trace.halt_reason == "fetch_failed"
