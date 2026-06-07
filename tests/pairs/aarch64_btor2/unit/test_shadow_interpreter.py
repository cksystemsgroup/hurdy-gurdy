"""Tests for AArch64 term-shadow interpreter (SCHEMA.md §14.6).

Covers:
- record_shadow=False (default) is byte-identical with v1.0.0 on
  fully-pinned bindings — no shadow key on final_state.
- record_shadow=False with FREE raises FreeFieldNotAllowed.
- record_shadow=True records BranchEvent per conditional branch.
- record_shadow=True records MemoryAccessEvent per load/store.
- record_shadow=True accepts FREE fields; they concretize to 0.
- record_shadow=True exposes the FREE field inventory on the shadow.
"""

from __future__ import annotations

import pytest

from gurdy.pairs.aarch64_btor2.source.loader import load_aarch64_binary
from gurdy.pairs.aarch64_btor2.source_interp.bindings import (
    FREE,
    AArch64InputBinding,
    FreeFieldNotAllowed,
)
from gurdy.pairs.aarch64_btor2.source_interp.interpreter import (
    AArch64SourceInterpreter,
)
from tests.fixtures.elf_builder_aarch64 import FuncDef, build_elf

TEXT_BASE = 0x10000

# Instruction bytes (little-endian 32-bit words):
# CBNZ X0, #8 (sf=1, is_nz=1, rt=0, imm19=2):  0xB5000040
# NOP: 0xD503201F
# SVC #0: 0xD4000001
# LDR X0, [X1, #0]: 0xF9400020
# Pre-computed LE bytes for each instruction:
CBNZ_X0_8 = (0xB5000040).to_bytes(4, "little")   # CBNZ X0, +8
NOP        = (0xD503201F).to_bytes(4, "little")   # NOP
SVC0       = (0xD4000001).to_bytes(4, "little")   # SVC #0
LDR_X0_X1 = (0xF9400020).to_bytes(4, "little")   # LDR X0, [X1, #0]


def _make_source(code: bytes, tmp_path):
    p = tmp_path / "test.elf"
    p.write_bytes(
        build_elf(code, TEXT_BASE, [FuncDef("fn", TEXT_BASE, len(code))])
    )
    return load_aarch64_binary(p)


# ---------------------------------------------------------------------------
# Default (record_shadow=False) behaviour
# ---------------------------------------------------------------------------


def test_default_run_has_no_shadow_in_final_state(tmp_path):
    code = CBNZ_X0_8 + NOP + SVC0
    source = _make_source(code, tmp_path)
    interp = AArch64SourceInterpreter()
    binding = AArch64InputBinding()
    trace = interp.run(source, binding, max_steps=10)
    assert "shadow" not in (trace.final_state or {})


def test_default_run_rejects_free(tmp_path):
    code = NOP + SVC0
    source = _make_source(code, tmp_path)
    interp = AArch64SourceInterpreter()
    binding = AArch64InputBinding(register_init={1: FREE})
    with pytest.raises(FreeFieldNotAllowed):
        interp.run(source, binding, max_steps=10)


# ---------------------------------------------------------------------------
# record_shadow=True — branch events
# ---------------------------------------------------------------------------


def test_shadow_records_branch_not_taken(tmp_path):
    # CBNZ X0, +8 → NOP → SVC.  X0 default=0, so CBNZ is NOT taken.
    code = CBNZ_X0_8 + NOP + SVC0
    source = _make_source(code, tmp_path)
    interp = AArch64SourceInterpreter()
    binding = AArch64InputBinding()  # x0 = 0
    trace = interp.run(source, binding, max_steps=10, record_shadow=True)

    shadow = trace.final_state["shadow"]
    branches = shadow["branch_events"]
    assert len(branches) == 1
    ev = branches[0]
    assert ev["step"] == 0
    assert ev["pc"] == TEXT_BASE
    assert ev["mnemonic"] == "CBNZ"
    assert ev["taken"] is False


def test_shadow_records_branch_taken(tmp_path):
    # CBNZ X0, +8 → NOP → SVC.  X0=1 → CBNZ taken → jumps to SVC at +8.
    code = CBNZ_X0_8 + NOP + SVC0
    source = _make_source(code, tmp_path)
    interp = AArch64SourceInterpreter()
    binding = AArch64InputBinding(register_init={0: 1})
    trace = interp.run(source, binding, max_steps=10, record_shadow=True)

    shadow = trace.final_state["shadow"]
    branches = shadow["branch_events"]
    assert len(branches) == 1
    assert branches[0]["taken"] is True
    # Only two steps: CBNZ (taken) + SVC.
    assert len(trace.steps) == 2


# ---------------------------------------------------------------------------
# record_shadow=True — memory access events
# ---------------------------------------------------------------------------


def test_shadow_records_load_event(tmp_path):
    # LDR X0, [X1, #0]; SVC #0.  Set X1 = TEXT_BASE (valid mapped address).
    code = LDR_X0_X1 + SVC0
    source = _make_source(code, tmp_path)
    interp = AArch64SourceInterpreter()
    binding = AArch64InputBinding(register_init={1: TEXT_BASE})
    trace = interp.run(source, binding, max_steps=10, record_shadow=True)

    shadow = trace.final_state["shadow"]
    mem_events = shadow["memory_events"]
    assert len(mem_events) == 1
    ev = mem_events[0]
    assert ev["step"] == 0
    assert ev["pc"] == TEXT_BASE
    assert ev["mnemonic"] == "LDR"
    assert ev["kind"] == "load"
    assert ev["addr"] == TEXT_BASE  # [X1 + 0] = TEXT_BASE + 0


# ---------------------------------------------------------------------------
# FREE support
# ---------------------------------------------------------------------------


def test_shadow_accepts_free_fields(tmp_path):
    code = NOP + SVC0
    source = _make_source(code, tmp_path)
    interp = AArch64SourceInterpreter()
    binding = AArch64InputBinding(register_init={1: FREE})
    # Should run without raising.
    trace = interp.run(source, binding, max_steps=10, record_shadow=True)
    assert trace.final_state["shadow"]["free_fields"]["register_init"] == [1]


def test_shadow_free_concretizes_to_zero(tmp_path):
    """FREE binding cells execute as 0 — same trace steps as pinned-to-0."""
    code = NOP + SVC0
    source = _make_source(code, tmp_path)
    interp = AArch64SourceInterpreter()
    b_free = AArch64InputBinding(register_init={1: FREE, 5: FREE})
    b_zero = AArch64InputBinding(register_init={1: 0, 5: 0})
    t_free = interp.run(source, b_free, max_steps=10, record_shadow=True)
    t_zero = interp.run(source, b_zero, max_steps=10, record_shadow=False)
    # Strip shadow and inputs_hash before comparing steps.
    assert tuple(s.to_jsonable() for s in t_free.steps) == tuple(
        s.to_jsonable() for s in t_zero.steps
    )
    free_final = dict(t_free.final_state)
    free_final.pop("shadow")
    assert free_final == t_zero.final_state


def test_shadow_records_free_field_inventory(tmp_path):
    code = NOP + SVC0
    source = _make_source(code, tmp_path)
    interp = AArch64SourceInterpreter()
    binding = AArch64InputBinding(
        register_init={2: FREE, 5: 99},
        memory_init={0x2000: FREE, 0x2001: 0xAB},
        havoc_per_step=({3: FREE},),
    )
    trace = interp.run(source, binding, max_steps=10, record_shadow=True)
    free = trace.final_state["shadow"]["free_fields"]
    assert free["register_init"] == [2]
    assert free["memory_init"] == [0x2000]
    assert free["havoc_steps"] == [[0, 3]]
