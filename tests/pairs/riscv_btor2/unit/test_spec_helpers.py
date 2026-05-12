"""Tests for ``trace_to_branch_pins``."""

from __future__ import annotations

import pytest

from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
from gurdy.pairs.riscv_btor2.source_interp.bindings import RiscvInputBinding
from gurdy.pairs.riscv_btor2.source_interp.interpreter import (
    RiscvSourceInterpreter,
)
from gurdy.pairs.riscv_btor2.spec import BranchPin
from gurdy.pairs.riscv_btor2.spec_helpers import trace_to_branch_pins

from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000
# addi a0, x0, 1 ; beq a0, x0, +8 ; ret
BRANCH_BYTES = bytes.fromhex("13051000" "63040500" "67800000")
BEQ_PC = TEXT_BASE + 4


def _trace(tmp_path, **kwargs):
    p = tmp_path / "f.elf"
    p.write_bytes(
        build_elf(BRANCH_BYTES, TEXT_BASE, [FuncDef("f", TEXT_BASE, len(BRANCH_BYTES))])
    )
    source = load_riscv_binary(p)
    return RiscvSourceInterpreter().run(
        source, RiscvInputBinding(**kwargs), max_steps=10, record_shadow=True
    )


def test_empty_trace_yields_no_pins():
    # A trace with no shadow returns an empty tuple.
    from gurdy.core.interp.types import SourceTrace

    t = SourceTrace(
        pair="riscv-btor2",
        interpreter_version="1.1.0",
        inputs_hash="",
        steps=(),
        final_state={},  # no "shadow" key
    )
    assert trace_to_branch_pins(t) == ()


def test_pin_per_branch_event_preserved_order(tmp_path):
    trace = _trace(tmp_path)
    pins = trace_to_branch_pins(trace)
    # Fixture has exactly one BEQ.
    assert len(pins) == 1
    assert pins[0] == BranchPin(step=1, taken=False, pc=BEQ_PC)


def test_flip_branch_at_inverts_direction(tmp_path):
    trace = _trace(tmp_path)
    pins = trace_to_branch_pins(trace, flip_branch_at=1)
    assert len(pins) == 1
    assert pins[0] == BranchPin(step=1, taken=True, pc=BEQ_PC)


def test_flip_at_unknown_step_raises(tmp_path):
    trace = _trace(tmp_path)
    with pytest.raises(ValueError, match="no branch event at step 99"):
        trace_to_branch_pins(trace, flip_branch_at=99)


def test_pins_drop_into_spec(tmp_path):
    """The output is structurally a tuple of BaseAssumption instances
    and slots into spec.assumptions directly."""
    from gurdy.pairs.riscv_btor2.spec import (
        AnalysisDirective,
        AnalysisScope,
        BinaryRef,
        Property,
        RiscvBtor2Spec,
    )

    trace = _trace(tmp_path)
    pins = trace_to_branch_pins(trace)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path="ignored"),
        scope=AnalysisScope(entry_function="f"),
        assumptions=pins,
        property=Property(expression="false"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    assert spec.assumptions == pins
