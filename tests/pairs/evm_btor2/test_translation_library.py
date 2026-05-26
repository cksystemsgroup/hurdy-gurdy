"""Tests for evm-btor2 translation library (P4) — lower_push1.

Each test builds a minimal single-opcode BTOR2 model, wires ``next``
clauses from the lowering result, adds a ``bad`` condition, then drives
it through the reasoning interpreter to verify the concrete semantics.

BTOR2 transition semantics (as implemented by Btor2ReasoningInterpreter):
- Step i applies ``next`` clauses to get new state values.
- ``bad`` is evaluated against the NEW (post-transition) state.
- "bad fires at step 0" means after the very first transition.
"""

from __future__ import annotations

import pytest

from gurdy.pairs.evm_btor2.btor2.parser import from_text
from gurdy.pairs.evm_btor2.btor2.printer import to_text
from gurdy.pairs.evm_btor2.reasoning_interp import (
    Btor2ReasoningBinding,
    Btor2ReasoningInterpreter,
)
from gurdy.core.pair import CompiledArtifact, Layer
from gurdy.core.annotation.sidecar import AnnotationSidecar
from gurdy.pairs.evm_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BytecodeRef,
    EvmBtor2Spec,
    GasLimitPin,
    ReachKind,
    ReachProperty,
)
from gurdy.pairs.evm_btor2.translation.builder import Btor2Builder, MACHINE_STATE_VARS
from gurdy.pairs.evm_btor2.translation.layers import emit_init_clauses
from gurdy.pairs.evm_btor2.translation.library import (
    EvmLoweringResult,
    lower_push1,
    PUSH1_GAS,
    PUSH1_SIZE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec(gas: int = 100) -> EvmBtor2Spec:
    return EvmBtor2Spec(
        bytecode=BytecodeRef(hex="60" + "42"),
        scope=AnalysisScope(),
        assumptions=(GasLimitPin(gas=gas),),
        property=ReachProperty(kind=ReachKind.STOP),
        analysis=AnalysisDirective(engine="z3-bmc", bound=1),
    )


def _fresh(gas: int = 100) -> tuple[Btor2Builder, EvmBtor2Spec]:
    """Return a builder with header + machine states + zero-inits."""
    b = Btor2Builder()
    b.emit_header()
    b.emit_machine_states()
    spec = _spec(gas=gas)
    emit_init_clauses(b, spec, b.state_nids)
    return b, spec


def _wire_next(b: Btor2Builder, result: EvmLoweringResult) -> None:
    """Emit ``next`` clauses for all 12 machine states from ``result``."""
    for sym, sort_name in MACHINE_STATE_VARS:
        state_nid = b.state_nids[sym]
        next_expr_nid = getattr(result, sym)
        b.next(sort_name, state_nid, next_expr_nid)


def _make_artifact(b: Btor2Builder) -> CompiledArtifact:
    body = to_text(b.model).encode("utf-8")
    return CompiledArtifact(
        pair="evm-btor2",
        layers={"all": Layer(name="all", body=body, content_hash="x")},
        annotation=AnnotationSidecar(),
        flattened=body,
        schema_version="1.0.0",
        spec_hash="x",
    )


def _binding(**kw) -> Btor2ReasoningBinding:
    return Btor2ReasoningBinding(state_init_by_symbol=kw)


def _run(b: Btor2Builder, max_steps: int = 2, **binding_kw) -> object:
    interp = Btor2ReasoningInterpreter()
    return interp.run(_make_artifact(b), _binding(**binding_kw), max_steps=max_steps)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_push1_gas_constant():
    assert PUSH1_GAS == 3


def test_push1_size_constant():
    assert PUSH1_SIZE == 2


# ---------------------------------------------------------------------------
# EvmLoweringResult structure
# ---------------------------------------------------------------------------


def test_lower_push1_returns_result():
    b, _ = _fresh()
    result = lower_push1(b, b.state_nids, 0x42)
    assert isinstance(result, EvmLoweringResult)


def test_lower_push1_all_fields_are_ints():
    b, _ = _fresh()
    result = lower_push1(b, b.state_nids, 0x42)
    for sym, _ in MACHINE_STATE_VARS:
        v = getattr(result, sym)
        assert isinstance(v, int), f"{sym} is {type(v)}, expected int"


def test_lower_push1_unchanged_states_match_machine_nids():
    """States not touched by PUSH1 should alias the input state nids."""
    b, _ = _fresh()
    result = lower_push1(b, b.state_nids, 0x42)
    for sym in ("mem", "mem_words", "sto", "sto_warm", "returndata", "returndatasize"):
        assert getattr(result, sym) == b.state_nids[sym], (
            f"{sym}: expected alias to machine nid, got different nid"
        )


def test_lower_push1_changed_states_are_new_nids():
    """States mutated by PUSH1 must have fresh (computed) nids."""
    b, _ = _fresh()
    result = lower_push1(b, b.state_nids, 0x42)
    for sym in ("sp", "stack", "pc", "gas", "trap", "halted"):
        assert getattr(result, sym) != b.state_nids[sym], (
            f"{sym} should have a new nid after lowering"
        )


# ---------------------------------------------------------------------------
# Concrete semantics: normal execution (gas=100, sp=0, pc=0, trap=0)
# ---------------------------------------------------------------------------


def test_lower_push1_sp_increments():
    """After one PUSH1 step, sp goes from 0 to 1."""
    b, _ = _fresh(gas=100)
    result = lower_push1(b, b.state_nids, 0x42)
    _wire_next(b, result)
    # bad = (sp == 1)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at == 0


def test_lower_push1_pc_advances_by_2():
    """After one PUSH1 step, pc goes from 0 to 2."""
    b, _ = _fresh(gas=100)
    result = lower_push1(b, b.state_nids, 0x42)
    _wire_next(b, result)
    # bad = (pc == 2)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 2)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at == 0


def test_lower_push1_gas_decremented_by_3():
    """After one PUSH1 step, gas decreases by PUSH1_GAS (3)."""
    b, _ = _fresh(gas=100)
    result = lower_push1(b, b.state_nids, 0x42)
    _wire_next(b, result)
    # bad = (gas == 97)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 97)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at == 0


def test_lower_push1_no_trap_on_clean_exec():
    """trap stays 0 after a clean PUSH1."""
    b, _ = _fresh(gas=100)
    result = lower_push1(b, b.state_nids, 0x42)
    _wire_next(b, result)
    # bad = (trap == 1); should NOT fire
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at is None


def test_lower_push1_stack_written():
    """After one PUSH1 0x42 step, read(stack, 0) == 0x42."""
    b, _ = _fresh(gas=100)
    result = lower_push1(b, b.state_nids, 0x42)
    _wire_next(b, result)
    # bad = (read(stack, 0) == 0x42)
    idx_nid = b.const("bv256", 0)
    read_nid = b.read("bv256", b.state_nids["stack"], idx_nid)
    b.bad(b.eq(read_nid, b.const("bv256", 0x42)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at == 0


# ---------------------------------------------------------------------------
# Trap: out-of-gas
# ---------------------------------------------------------------------------


def test_lower_push1_oog_sets_trap():
    """gas < 3 → trap=1 after step 0."""
    b, _ = _fresh(gas=2)
    result = lower_push1(b, b.state_nids, 0x42)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at == 0


def test_lower_push1_oog_sets_halted():
    """gas < 3 → halted=1 after step 0."""
    b, _ = _fresh(gas=1)
    result = lower_push1(b, b.state_nids, 0x42)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["halted"], b.const("bv1", 1)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at == 0


def test_lower_push1_oog_sp_unchanged():
    """When OOG, sp must not change (stays 0)."""
    b, _ = _fresh(gas=0)
    result = lower_push1(b, b.state_nids, 0x42)
    _wire_next(b, result)
    # bad = (sp != 0); must NOT fire (sp is frozen)
    b.bad(b.neq(b.state_nids["sp"], b.const("bv10", 0)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at is None


def test_lower_push1_oog_pc_unchanged():
    """When OOG, pc must not advance."""
    b, _ = _fresh(gas=0)
    result = lower_push1(b, b.state_nids, 0x42)
    _wire_next(b, result)
    b.bad(b.neq(b.state_nids["pc"], b.const("bv16", 0)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# Trap: already halted → no-op
# ---------------------------------------------------------------------------


def test_lower_push1_noop_when_halted():
    """If halted=1 at entry, PUSH1 must not change sp."""
    b, _ = _fresh(gas=100)
    result = lower_push1(b, b.state_nids, 0x42)
    _wire_next(b, result)
    # bad = (sp != 0); must NOT fire when execution is suppressed
    b.bad(b.neq(b.state_nids["sp"], b.const("bv10", 0)))
    # Override initial halted to 1 via binding
    trace = _run(b, max_steps=2, halted=1)
    assert trace.bad_fired_at is None


def test_lower_push1_noop_when_trapped():
    """If trap=1 at entry, PUSH1 must not change pc."""
    b, _ = _fresh(gas=100)
    result = lower_push1(b, b.state_nids, 0x42)
    _wire_next(b, result)
    b.bad(b.neq(b.state_nids["pc"], b.const("bv16", 0)))
    trace = _run(b, max_steps=2, trap=1)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# Round-trip: emitted BTOR2 parses without errors
# ---------------------------------------------------------------------------


def test_lower_push1_round_trips_btor2():
    b, _ = _fresh(gas=100)
    result = lower_push1(b, b.state_nids, 0x42)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_lower_push1_immediate_zero():
    """PUSH1 0x00 — immediate byte is zero; sp still increments."""
    b, _ = _fresh(gas=100)
    result = lower_push1(b, b.state_nids, 0x00)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at == 0


def test_lower_push1_immediate_ff():
    """PUSH1 0xFF — maximum 1-byte immediate."""
    b, _ = _fresh(gas=100)
    result = lower_push1(b, b.state_nids, 0xFF)
    _wire_next(b, result)
    idx_nid = b.const("bv256", 0)
    read_nid = b.read("bv256", b.state_nids["stack"], idx_nid)
    b.bad(b.eq(read_nid, b.const("bv256", 0xFF)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at == 0
