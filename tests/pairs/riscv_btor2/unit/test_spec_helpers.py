"""Tests for ``trace_to_branch_pins``."""

from __future__ import annotations

from typing import Iterable

import pytest

from gurdy.core.interp.types import SourceTrace
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


def _synthetic_trace(branch_events: Iterable[dict] | None) -> SourceTrace:
    """Build a SourceTrace whose shadow has the given branch events.

    ``branch_events=None`` produces a trace with no shadow key at all.
    """
    final_state: dict | None = {}
    if branch_events is not None:
        final_state = {
            "shadow": {
                "branch_events": tuple(branch_events),
                "memory_events": (),
                "free_fields": {"register_init": [], "memory_init": []},
            }
        }
    return SourceTrace(
        pair="riscv-btor2",
        interpreter_version="1.1.0",
        inputs_hash="",
        steps=(),
        final_state=final_state,
    )


def test_empty_trace_yields_no_pins():
    # A trace with no shadow returns an empty tuple.
    assert trace_to_branch_pins(_synthetic_trace(None)) == ()


def test_final_state_none_yields_no_pins():
    # Defensive: the helper guards `if trace.final_state else None`.
    t = SourceTrace(
        pair="riscv-btor2",
        interpreter_version="1.1.0",
        inputs_hash="",
        steps=(),
        final_state=None,
    )
    assert trace_to_branch_pins(t) == ()


def test_shadow_with_empty_branch_events_yields_no_pins():
    assert trace_to_branch_pins(_synthetic_trace(())) == ()


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


# ---------------------------------------------------------------------------
# Multi-event behaviour (synthetic traces — no ELF needed)
# ---------------------------------------------------------------------------


def _events(*specs):
    """Build a tuple of branch-event dicts from (step, pc, taken) tuples."""
    return tuple(
        {"step": s, "pc": p, "mnemonic": "BEQ", "taken": t}
        for (s, p, t) in specs
    )


def test_multiple_events_preserve_order():
    trace = _synthetic_trace(
        _events((3, 0x2000, True), (1, 0x1000, False), (5, 0x3000, True))
    )
    pins = trace_to_branch_pins(trace)
    # Order is recording order, not sorted by step.
    assert pins == (
        BranchPin(step=3, taken=True, pc=0x2000),
        BranchPin(step=1, taken=False, pc=0x1000),
        BranchPin(step=5, taken=True, pc=0x3000),
    )


def test_flip_inverts_only_the_target_pin():
    trace = _synthetic_trace(
        _events((1, 0x1000, False), (3, 0x2000, True), (5, 0x3000, False))
    )
    pins = trace_to_branch_pins(trace, flip_branch_at=3)
    # Only the step-3 pin flips; neighbours are untouched.
    assert pins == (
        BranchPin(step=1, taken=False, pc=0x1000),
        BranchPin(step=3, taken=False, pc=0x2000),
        BranchPin(step=5, taken=False, pc=0x3000),
    )


def test_flip_branch_at_zero_is_honored():
    # Regression guard: ``flip_branch_at=0`` must not be treated as
    # "no flip" by an accidental ``if flip_branch_at:`` check.
    trace = _synthetic_trace(_events((0, 0x1000, True)))
    pins = trace_to_branch_pins(trace, flip_branch_at=0)
    assert pins == (BranchPin(step=0, taken=False, pc=0x1000),)


def test_flip_at_unknown_step_lists_available_steps():
    trace = _synthetic_trace(_events((1, 0x1000, False), (5, 0x3000, True)))
    with pytest.raises(ValueError, match=r"available: \[1, 5\]"):
        trace_to_branch_pins(trace, flip_branch_at=99)


def test_pins_have_normalized_scalar_types():
    # Justifies the int(...)/bool(...) casts in the helper: even if
    # the shadow leaks numpy ints or truthy non-bools, the pins are
    # plain Python int/bool so frozen-dataclass equality stays sane.
    trace = _synthetic_trace(
        ({"step": True, "pc": 0x1000, "mnemonic": "BEQ", "taken": 1},)
    )
    (pin,) = trace_to_branch_pins(trace)
    assert type(pin.step) is int and pin.step == 1
    assert type(pin.pc) is int and pin.pc == 0x1000
    assert type(pin.taken) is bool and pin.taken is True


def test_no_shadow_integration(tmp_path):
    # End-to-end: a record_shadow=False run produces no shadow key,
    # and the helper degrades to an empty tuple rather than raising.
    p = tmp_path / "f.elf"
    p.write_bytes(
        build_elf(BRANCH_BYTES, TEXT_BASE, [FuncDef("f", TEXT_BASE, len(BRANCH_BYTES))])
    )
    source = load_riscv_binary(p)
    trace = RiscvSourceInterpreter().run(
        source, RiscvInputBinding(), max_steps=10
    )
    assert trace_to_branch_pins(trace) == ()
