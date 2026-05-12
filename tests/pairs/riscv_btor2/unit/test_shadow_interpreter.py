"""Phase 4: term-shadow interpreter (SCHEMA.md §14.6).

Covers:

- ``record_shadow=False`` (default) is byte-identical with v1.0.0 on
  fully-pinned bindings — no shadow key on ``final_state``.
- ``record_shadow=True`` records ``BranchEvent`` and
  ``MemoryAccessEvent`` per instruction.
- ``record_shadow=True`` accepts ``FREE`` fields; they concretize
  to 0 for execution (soundness contract §14.8 property 1).
- ``record_shadow=False`` with ``FREE`` still raises
  ``FreeFieldNotAllowed``.
"""

from __future__ import annotations

import pytest

from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
from gurdy.pairs.riscv_btor2.source_interp.bindings import (
    FREE,
    FreeFieldNotAllowed,
    RiscvInputBinding,
)
from gurdy.pairs.riscv_btor2.source_interp.interpreter import (
    RiscvSourceInterpreter,
)

from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000
# Bytes for: addi a0, x0, 1 ; beq a0, x0, +8 ; ret
BRANCH_BYTES = bytes.fromhex("13051000" "63040500" "67800000")
BEQ_PC = TEXT_BASE + 4


def _make_binary(tmp_path):
    funcs = [FuncDef(name="brfn", addr=TEXT_BASE, size=len(BRANCH_BYTES))]
    p = tmp_path / "brfn.elf"
    p.write_bytes(build_elf(BRANCH_BYTES, TEXT_BASE, funcs))
    return load_riscv_binary(p)


# ---------------------------------------------------------------------------
# Default (record_shadow=False) is byte-identical with v1.0.0
# ---------------------------------------------------------------------------


def test_default_run_has_no_shadow_in_final_state(tmp_path):
    source = _make_binary(tmp_path)
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding()
    trace = interp.run(source, binding, max_steps=10)
    assert "shadow" not in (trace.final_state or {})


def test_default_run_rejects_free(tmp_path):
    source = _make_binary(tmp_path)
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding(register_init={1: FREE})
    with pytest.raises(FreeFieldNotAllowed):
        interp.run(source, binding, max_steps=10)


# ---------------------------------------------------------------------------
# record_shadow=True records branch events
# ---------------------------------------------------------------------------


def test_shadow_records_branch_event(tmp_path):
    source = _make_binary(tmp_path)
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding()
    trace = interp.run(source, binding, max_steps=10, record_shadow=True)

    shadow = trace.final_state["shadow"]
    branches = shadow["branch_events"]
    assert len(branches) == 1
    ev = branches[0]
    assert ev["step"] == 1  # step 0 is ADDI, step 1 is BEQ
    assert ev["pc"] == BEQ_PC
    assert ev["mnemonic"] == "BEQ"
    # ADDI sets a0=1; BEQ a0, x0 → not taken (a0 != x0).
    assert ev["taken"] is False


def test_shadow_branch_taken_when_condition_true(tmp_path):
    # Pin a0 = 0 at entry so BEQ a0, x0 takes the branch.
    source = _make_binary(tmp_path)
    # Pre-zero a0 via memory; for our fixture, simply override the
    # register via havoc_per_step at step 0 (replace x10 after the
    # ADDI write).
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding(
        havoc_per_step=({10: 0},),
    )
    trace = interp.run(source, binding, max_steps=10, record_shadow=True)
    shadow = trace.final_state["shadow"]
    branches = shadow["branch_events"]
    assert len(branches) == 1
    assert branches[0]["taken"] is True


# ---------------------------------------------------------------------------
# record_shadow=True accepts FREE; default concretization is 0
# ---------------------------------------------------------------------------


def test_shadow_accepts_free_fields(tmp_path):
    source = _make_binary(tmp_path)
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding(register_init={1: FREE})
    # Should run without raising.
    trace = interp.run(source, binding, max_steps=10, record_shadow=True)
    assert trace.final_state["shadow"]["free_fields"]["register_init"] == [1]


def test_shadow_free_concretizes_to_zero(tmp_path):
    """SCHEMA.md §14.8 property 1: a binding with FREE cells produces
    the same trace (modulo shadow metadata) as the same binding with
    those cells pinned to 0."""
    source = _make_binary(tmp_path)
    interp = RiscvSourceInterpreter()
    b_free = RiscvInputBinding(register_init={1: FREE, 5: FREE})
    b_zero = RiscvInputBinding(register_init={1: 0, 5: 0})
    t_free = interp.run(source, b_free, max_steps=10, record_shadow=True)
    t_zero = interp.run(source, b_zero, max_steps=10, record_shadow=False)
    # Strip shadow and inputs_hash before comparing (they differ).
    assert tuple(s.to_jsonable() for s in t_free.steps) == tuple(
        s.to_jsonable() for s in t_zero.steps
    )
    free_final = dict(t_free.final_state)
    free_final.pop("shadow")
    assert free_final == t_zero.final_state


def test_shadow_records_free_field_inventory(tmp_path):
    source = _make_binary(tmp_path)
    interp = RiscvSourceInterpreter()
    binding = RiscvInputBinding(
        register_init={2: FREE, 5: 99},
        memory_init={0x1000: FREE, 0x1001: 0xAB},
        havoc_per_step=({1: FREE},),
    )
    trace = interp.run(source, binding, max_steps=10, record_shadow=True)
    free = trace.final_state["shadow"]["free_fields"]
    assert free["register_init"] == [2]
    assert free["memory_init"] == [0x1000]
    assert free["havoc_steps"] == [[0, 1]]
