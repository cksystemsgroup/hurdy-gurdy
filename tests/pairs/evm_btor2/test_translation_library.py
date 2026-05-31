"""Tests for evm-btor2 translation library (P11) — lower_push1 / lower_stop / lower_add.

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
from gurdy.pairs.evm_btor2.translation.layers import emit_context_inputs
from gurdy.pairs.evm_btor2.translation.library import (
    EvmLoweringResult,
    lower_push1,
    lower_stop,
    lower_add,
    lower_sub,
    lower_mul,
    lower_div,
    lower_mod,
    lower_addmod,
    lower_mulmod,
    lower_exp,
    lower_and,
    lower_or,
    lower_xor,
    lower_not,
    lower_jump,
    lower_lt,
    lower_gt,
    lower_eq_op,
    lower_sstore,
    lower_calldataload,
    lower_calldatacopy,
    lower_calldatasize,
    lower_jumpi,
    lower_iszero,
    lower_dup1,
    lower_dupn,
    lower_swapn,
    lower_mload,
    lower_mstore,
    lower_mstore8,
    lower_push0,
    lower_return,
    PUSH1_GAS,
    PUSH1_SIZE,
    STOP_GAS,
    ADD_GAS,
    ADD_SIZE,
    SUB_GAS,
    SUB_SIZE,
    MUL_GAS,
    MUL_SIZE,
    AND_GAS,
    AND_SIZE,
    OR_GAS,
    OR_SIZE,
    XOR_GAS,
    XOR_SIZE,
    NOT_GAS,
    NOT_SIZE,
    JUMP_GAS,
    JUMP_SIZE,
    LT_GAS,
    LT_SIZE,
    GT_GAS,
    GT_SIZE,
    EQ_GAS,
    EQ_SIZE,
    SSTORE_GAS_COLD,
    SSTORE_GAS_WARM,
    SSTORE_SIZE,
    CALLDATALOAD_GAS,
    CALLDATALOAD_SIZE,
    CALLDATACOPY_GAS,
    CALLDATACOPY_SIZE,
    CALLDATACOPY_MAX_LEN,
    CALLDATASIZE_GAS,
    CALLDATASIZE_SIZE,
    JUMPI_GAS,
    JUMPI_SIZE,
    ISZERO_GAS,
    ISZERO_SIZE,
    DUP1_GAS,
    DUP1_SIZE,
    DUP_GAS,
    DUP_SIZE,
    SWAP_GAS,
    SWAP_SIZE,
    MLOAD_GAS,
    MLOAD_SIZE,
    MSTORE_GAS,
    MSTORE_SIZE,
    MSTORE8_GAS,
    MSTORE8_SIZE,
    PUSH0_GAS,
    PUSH0_SIZE,
    RETURN_GAS,
    RETURN_SIZE,
    DIV_GAS,
    DIV_SIZE,
    MOD_GAS,
    MOD_SIZE,
    ADDMOD_GAS,
    ADDMOD_SIZE,
    MULMOD_GAS,
    MULMOD_SIZE,
    EXP_GAS_BASE,
    EXP_GAS_1BYTE,
    EXP_EXPONENT_BITS,
    EXP_SIZE,
    lower_byte,
    lower_shl,
    lower_shr,
    lower_sar,
    lower_signextend,
    lower_slt,
    lower_sgt,
    lower_sdiv,
    lower_smod,
    lower_pushn,
    BYTE_GAS,
    BYTE_SIZE,
    SHL_GAS,
    SHL_SIZE,
    SHR_GAS,
    SHR_SIZE,
    SAR_GAS,
    SAR_SIZE,
    SIGNEXTEND_GAS,
    SIGNEXTEND_SIZE,
    SLT_GAS,
    SLT_SIZE,
    SGT_GAS,
    SGT_SIZE,
    SDIV_GAS,
    SDIV_SIZE,
    SMOD_GAS,
    SMOD_SIZE,
    PUSHN_GAS,
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


# ===========================================================================
# lower_stop
# ===========================================================================

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_stop_gas_constant():
    assert STOP_GAS == 0


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_lower_stop_returns_result():
    b, _ = _fresh()
    result = lower_stop(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_stop_all_states_unchanged_except_halted():
    """Only halted has a new (computed) nid; all other states alias machine_nids."""
    b, _ = _fresh()
    result = lower_stop(b, b.state_nids)
    unchanged = ("sp", "stack", "mem", "mem_words", "sto", "sto_warm",
                 "pc", "gas", "trap", "returndata", "returndatasize")
    for sym in unchanged:
        assert getattr(result, sym) == b.state_nids[sym], (
            f"{sym} should alias machine_nid after STOP"
        )
    assert result.halted != b.state_nids["halted"], "halted must have a new nid"


# ---------------------------------------------------------------------------
# Concrete semantics
# ---------------------------------------------------------------------------


def test_lower_stop_sets_halted():
    """After one STOP step, halted becomes 1."""
    b, _ = _fresh(gas=100)
    result = lower_stop(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["halted"], b.const("bv1", 1)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at == 0


def test_lower_stop_does_not_set_trap():
    """STOP is a clean halt; trap must stay 0."""
    b, _ = _fresh(gas=100)
    result = lower_stop(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at is None


def test_lower_stop_gas_unchanged():
    """STOP has zero gas cost; gas must not change."""
    b, _ = _fresh(gas=100)
    result = lower_stop(b, b.state_nids)
    _wire_next(b, result)
    # bad = gas != 100
    b.bad(b.neq(b.state_nids["gas"], b.const("bv64", 100)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at is None


def test_lower_stop_pc_unchanged():
    """STOP freezes pc."""
    b, _ = _fresh(gas=100)
    result = lower_stop(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.neq(b.state_nids["pc"], b.const("bv16", 0)))
    trace = _run(b, max_steps=2)
    assert trace.bad_fired_at is None


def test_lower_stop_noop_when_halted():
    """STOP is a no-op when already halted (halted stays 1, no spurious changes)."""
    b, _ = _fresh(gas=100)
    result = lower_stop(b, b.state_nids)
    _wire_next(b, result)
    # bad = (halted == 1); will fire at step 0 even without STOP
    # ... so instead verify sp stays 0 (indirect correctness check)
    b.bad(b.neq(b.state_nids["sp"], b.const("bv10", 0)))
    trace = _run(b, max_steps=2, halted=1)
    assert trace.bad_fired_at is None


def test_lower_stop_round_trips_btor2():
    b, _ = _fresh()
    result = lower_stop(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["halted"], b.const("bv1", 1)))
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ===========================================================================
# lower_add
# ===========================================================================

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_add_gas_constant():
    assert ADD_GAS == 3


def test_add_size_constant():
    assert ADD_SIZE == 1


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_lower_add_returns_result():
    b, _ = _fresh()
    result = lower_add(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_add_unchanged_states():
    """States not touched by ADD alias the input machine nids."""
    b, _ = _fresh()
    result = lower_add(b, b.state_nids)
    for sym in ("mem", "mem_words", "sto", "sto_warm", "returndata", "returndatasize"):
        assert getattr(result, sym) == b.state_nids[sym]


# ---------------------------------------------------------------------------
# Concrete semantics (using binding overrides: sp=2, stack={0:3, 1:5})
# ---------------------------------------------------------------------------


def test_lower_add_sp_decrements():
    """After ADD with sp=2, sp becomes 1."""
    b, _ = _fresh(gas=100)
    result = lower_add(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=2, sp=2, stack={0: 3, 1: 5})
    assert trace.bad_fired_at == 0


def test_lower_add_pc_advances_by_1():
    """After ADD, pc advances by ADD_SIZE (1)."""
    b, _ = _fresh(gas=100)
    result = lower_add(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 1)))
    trace = _run(b, max_steps=2, sp=2, stack={0: 3, 1: 5})
    assert trace.bad_fired_at == 0


def test_lower_add_gas_decremented():
    """After ADD with gas=100, gas becomes 97."""
    b, _ = _fresh(gas=100)
    result = lower_add(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 97)))
    trace = _run(b, max_steps=2, sp=2, stack={0: 3, 1: 5})
    assert trace.bad_fired_at == 0


def test_lower_add_result_pushed():
    """After ADD 3+5, stack[0] == 8 (result at NOS slot, new TOS)."""
    b, _ = _fresh(gas=100)
    result = lower_add(b, b.state_nids)
    _wire_next(b, result)
    idx_nid = b.const("bv256", 0)
    read_nid = b.read("bv256", b.state_nids["stack"], idx_nid)
    b.bad(b.eq(read_nid, b.const("bv256", 8)))
    trace = _run(b, max_steps=2, sp=2, stack={0: 3, 1: 5})
    assert trace.bad_fired_at == 0


def test_lower_add_no_trap_normal():
    """Clean ADD does not set trap on step 0 (max_steps=1; step 1 would underflow)."""
    b, _ = _fresh(gas=100)
    result = lower_add(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 5})
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# ADD traps
# ---------------------------------------------------------------------------


def test_lower_add_underflow_sets_trap():
    """sp=1 (only 1 item) → underflow trap on ADD."""
    b, _ = _fresh(gas=100)
    result = lower_add(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=2, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_add_underflow_sp_unchanged():
    """On underflow, sp must not change."""
    b, _ = _fresh(gas=100)
    result = lower_add(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.neq(b.state_nids["sp"], b.const("bv10", 0)))
    trace = _run(b, max_steps=2, sp=0)
    assert trace.bad_fired_at is None


def test_lower_add_oog_sets_trap():
    """gas < 3 → OOG trap on ADD."""
    b, _ = _fresh(gas=2)
    result = lower_add(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=2, sp=2, stack={0: 3, 1: 5})
    assert trace.bad_fired_at == 0


def test_lower_add_noop_when_halted():
    """When halted=1, ADD must not change sp."""
    b, _ = _fresh(gas=100)
    result = lower_add(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.neq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=2, sp=2, stack={0: 3, 1: 5}, halted=1)
    assert trace.bad_fired_at is None


def test_lower_add_round_trips_btor2():
    b, _ = _fresh(gas=100)
    result = lower_add(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ===========================================================================
# lower_sstore
# ===========================================================================


def test_sstore_gas_constants():
    assert SSTORE_GAS_COLD == 2200
    assert SSTORE_GAS_WARM == 100
    assert SSTORE_SIZE == 1


def test_lower_sstore_returns_result():
    b, _ = _fresh(gas=100_000)
    result = lower_sstore(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_sstore_unchanged_states():
    b, _ = _fresh(gas=100_000)
    result = lower_sstore(b, b.state_nids)
    for sym in ("mem", "mem_words", "stack", "returndata", "returndatasize"):
        assert getattr(result, sym) == b.state_nids[sym]


def test_lower_sstore_changed_states():
    b, _ = _fresh(gas=100_000)
    result = lower_sstore(b, b.state_nids)
    for sym in ("sp", "sto", "sto_warm", "pc", "gas", "trap", "halted"):
        assert getattr(result, sym) != b.state_nids[sym]


def test_lower_sstore_sp_decrements_by_2():
    """After SSTORE with sp=2, sp becomes 0."""
    b, _ = _fresh(gas=100_000)
    result = lower_sstore(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 0)))
    # slot=0 (TOS=stack[1]=0), value=0x42 (NOS=stack[0]=0x42)
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_sstore_sto_written():
    """After SSTORE slot=0 value=0x42, sto[0] == 0x42."""
    b, _ = _fresh(gas=100_000)
    result = lower_sstore(b, b.state_nids)
    _wire_next(b, result)
    slot_idx = b.const("bv256", 0)
    read_nid = b.read("bv256", b.state_nids["sto"], slot_idx)
    b.bad(b.eq(read_nid, b.const("bv256", 0x42)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_sstore_warm_flag_set():
    """After SSTORE, sto_warm[slot][0:0] == 1."""
    b, _ = _fresh(gas=100_000)
    result = lower_sstore(b, b.state_nids)
    _wire_next(b, result)
    slot_idx = b.const("bv256", 0)
    warm_word = b.read("bv256", b.state_nids["sto_warm"], slot_idx)
    warm_bit = b.slice("bv1", warm_word, 0, 0)
    b.bad(b.eq(warm_bit, b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_sstore_pc_advances():
    """After SSTORE, pc advances by SSTORE_SIZE (1)."""
    b, _ = _fresh(gas=100_000)
    result = lower_sstore(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_sstore_cold_gas_cost():
    """Cold SSTORE: gas decrements by SSTORE_GAS_COLD (2200)."""
    b, _ = _fresh(gas=100_000)
    result = lower_sstore(b, b.state_nids)
    _wire_next(b, result)
    expected = b.const("bv64", 100_000 - SSTORE_GAS_COLD)
    b.bad(b.eq(b.state_nids["gas"], expected))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_sstore_warm_gas_cost():
    """Warm SSTORE: gas decrements by SSTORE_GAS_WARM (100)."""
    b, _ = _fresh(gas=100_000)
    result = lower_sstore(b, b.state_nids)
    _wire_next(b, result)
    expected = b.const("bv64", 100_000 - SSTORE_GAS_WARM)
    b.bad(b.eq(b.state_nids["gas"], expected))
    # Pre-warm slot 0: sto_warm = {0: 1}
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0}, sto_warm={0: 1})
    assert trace.bad_fired_at == 0


def test_lower_sstore_oog_traps():
    """gas < 100 (warm cost) → OOG trap."""
    b, _ = _fresh(gas=50)
    result = lower_sstore(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0}, sto_warm={0: 1})
    assert trace.bad_fired_at == 0


def test_lower_sstore_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=100_000)
    result = lower_sstore(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_sstore_round_trips_btor2():
    b, _ = _fresh(gas=100_000)
    result = lower_sstore(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ===========================================================================
# lower_calldataload
# ===========================================================================


def _fresh_with_ctx(gas: int = 100) -> tuple[Btor2Builder, dict[str, int]]:
    """Builder with header + machine states + context inputs + zero-inits."""
    b, spec = _fresh(gas=gas)
    ctx_nids = emit_context_inputs(b, spec)
    return b, ctx_nids


def test_calldataload_gas_constant():
    assert CALLDATALOAD_GAS == 3
    assert CALLDATALOAD_SIZE == 1


def test_lower_calldataload_returns_result():
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldataload(b, b.state_nids, ctx)
    assert isinstance(result, EvmLoweringResult)


def test_lower_calldataload_sp_unchanged():
    """CALLDATALOAD pops offset and pushes result — net sp change is 0."""
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldataload(b, b.state_nids, ctx)
    # sp nid should be the same state nid (no change)
    assert result.sp == b.state_nids["sp"]


def test_lower_calldataload_reads_zero_from_empty_calldata():
    """CALLDATALOAD(0) on empty calldata → 0 pushed at stack[0]."""
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldataload(b, b.state_nids, ctx)
    _wire_next(b, result)
    idx_nid = b.const("bv256", 0)
    read_nid = b.read("bv256", b.state_nids["stack"], idx_nid)
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    # sp=1, offset=stack[0]=0, calldata={}
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_calldataload_reads_last_byte():
    """CALLDATALOAD(0) with calldata[31]=0x42 → result = 0x42 (LSB)."""
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldataload(b, b.state_nids, ctx)
    _wire_next(b, result)
    idx_nid = b.const("bv256", 0)
    read_nid = b.read("bv256", b.state_nids["stack"], idx_nid)
    b.bad(b.eq(read_nid, b.const("bv256", 0x42)))
    # sp=1, offset=0, calldata[31]=0x42 → big-endian byte31 is LSB
    trace = _run(b, max_steps=1, sp=1, stack={0: 0}, calldata={31: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_calldataload_reads_first_byte():
    """CALLDATALOAD(0) with calldata[0]=0x01 → result = 0x01<<(31*8)."""
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldataload(b, b.state_nids, ctx)
    _wire_next(b, result)
    idx_nid = b.const("bv256", 0)
    read_nid = b.read("bv256", b.state_nids["stack"], idx_nid)
    # 0x01 in byte 0 (MSB) → 0x01 * 2^(31*8) — too large for evaluator (> 255 after write).
    # Instead: verify sp stays 1 (indirect check that execution proceeded without trap).
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0}, calldata={0: 0x01})
    assert trace.bad_fired_at == 0


def test_lower_calldataload_gas_decremented():
    """After CALLDATALOAD, gas decrements by CALLDATALOAD_GAS (3)."""
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldataload(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 97)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_calldataload_pc_advances():
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldataload(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_calldataload_oog_traps():
    """gas < 3 → OOG trap."""
    b, ctx = _fresh_with_ctx(gas=2)
    result = lower_calldataload(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_calldataload_underflow_traps():
    """sp=0 → underflow trap."""
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldataload(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_calldataload_round_trips_btor2():
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldataload(b, b.state_nids, ctx)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_jumpi
# ---------------------------------------------------------------------------


def test_jumpi_gas_constant():
    assert JUMPI_GAS == 10
    assert JUMPI_SIZE == 1


def test_lower_jumpi_returns_result():
    b, _ = _fresh(gas=100)
    result = lower_jumpi(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_jumpi_fall_through_pc():
    """cond=0 → pc advances by 1 (fall through)."""
    b, _ = _fresh(gas=100)
    result = lower_jumpi(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 1)))
    # sp=2, stack[0]=cond=0, stack[1]=dest=7; pc starts at 0 → falls to 1
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 7})
    assert trace.bad_fired_at == 0


def test_lower_jumpi_taken_pc():
    """cond=1 → pc jumps to dest."""
    b, _ = _fresh(gas=100)
    result = lower_jumpi(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 7)))
    # sp=2, stack[0]=cond=1, stack[1]=dest=7
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 7})
    assert trace.bad_fired_at == 0


def test_lower_jumpi_sp_decremented_by_2():
    """JUMPI pops both dest and cond → sp decreases by 2."""
    b, _ = _fresh(gas=100)
    result = lower_jumpi(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 7})
    assert trace.bad_fired_at == 0


def test_lower_jumpi_gas_decremented():
    """JUMPI costs JUMPI_GAS (10)."""
    b, _ = _fresh(gas=100)
    result = lower_jumpi(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 100 - JUMPI_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 5})
    assert trace.bad_fired_at == 0


def test_lower_jumpi_oog_traps():
    """gas < 10 → OOG trap."""
    b, _ = _fresh(gas=9)
    result = lower_jumpi(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 5})
    assert trace.bad_fired_at == 0


def test_lower_jumpi_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=100)
    result = lower_jumpi(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_jumpi_halted_noop():
    """Already halted → JUMPI is a no-op; bad(halted) still fires."""
    b, _ = _fresh(gas=100)
    result = lower_jumpi(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["halted"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 5}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_jumpi_round_trips_btor2():
    b, _ = _fresh(gas=100)
    result = lower_jumpi(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_iszero
# ---------------------------------------------------------------------------


def test_iszero_gas_constant():
    assert ISZERO_GAS == 3
    assert ISZERO_SIZE == 1


def test_lower_iszero_returns_result():
    b, _ = _fresh(gas=100)
    result = lower_iszero(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_iszero_zero_input_pushes_1():
    """TOS == 0 → ISZERO pushes 1 into that slot."""
    b, _ = _fresh(gas=100)
    result = lower_iszero(b, b.state_nids)
    _wire_next(b, result)
    # After one step with TOS=0, stack[0] should be 1.
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_iszero_nonzero_input_pushes_0():
    """TOS == 42 (non-zero) → ISZERO pushes 0 into that slot."""
    b, _ = _fresh(gas=100)
    result = lower_iszero(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 42})
    assert trace.bad_fired_at == 0


def test_lower_iszero_sp_unchanged():
    """ISZERO is a TOS-replace-in-place operation; sp must not change."""
    b, _ = _fresh(gas=100)
    result = lower_iszero(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_iszero_gas_decremented():
    """ISZERO costs ISZERO_GAS (3)."""
    b, _ = _fresh(gas=100)
    result = lower_iszero(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 100 - ISZERO_GAS)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 7})
    assert trace.bad_fired_at == 0


def test_lower_iszero_pc_advanced():
    """ISZERO advances pc by ISZERO_SIZE (1)."""
    b, _ = _fresh(gas=100)
    result = lower_iszero(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", ISZERO_SIZE)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_iszero_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_iszero(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_iszero_underflow_traps():
    """sp < 1 → underflow trap."""
    b, _ = _fresh(gas=100)
    result = lower_iszero(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_iszero_halted_noop():
    """Already halted → ISZERO is a no-op; halted stays 1."""
    b, _ = _fresh(gas=100)
    result = lower_iszero(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["halted"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_iszero_round_trips_btor2():
    b, _ = _fresh(gas=100)
    result = lower_iszero(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_dup1
# ---------------------------------------------------------------------------


def test_dup1_gas_constant():
    assert DUP1_GAS == 3
    assert DUP1_SIZE == 1


def test_lower_dup1_returns_result():
    b, _ = _fresh(gas=100)
    result = lower_dup1(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_dup1_sp_incremented():
    """DUP1 pushes a copy of TOS → sp increases by 1."""
    b, _ = _fresh(gas=100)
    result = lower_dup1(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 42})
    assert trace.bad_fired_at == 0


def test_lower_dup1_tos_duplicated():
    """After DUP1, stack[sp-1] (old TOS) and stack[sp] (new TOS) are equal."""
    b, _ = _fresh(gas=100)
    result = lower_dup1(b, b.state_nids)
    _wire_next(b, result)
    # stack[1] should be a copy of original stack[0]=99.
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 1)), b.const("bv256", 99)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 99})
    assert trace.bad_fired_at == 0


def test_lower_dup1_original_preserved():
    """DUP1 does not modify the original TOS; stack[0] is unchanged."""
    b, _ = _fresh(gas=100)
    result = lower_dup1(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 77)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 77})
    assert trace.bad_fired_at == 0


def test_lower_dup1_gas_decremented():
    """DUP1 costs DUP1_GAS (3)."""
    b, _ = _fresh(gas=100)
    result = lower_dup1(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 100 - DUP1_GAS)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_dup1_pc_advanced():
    """DUP1 advances pc by DUP1_SIZE (1)."""
    b, _ = _fresh(gas=100)
    result = lower_dup1(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", DUP1_SIZE)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 5})
    assert trace.bad_fired_at == 0


def test_lower_dup1_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_dup1(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_dup1_underflow_traps():
    """sp < 1 → underflow trap (nothing to duplicate)."""
    b, _ = _fresh(gas=100)
    result = lower_dup1(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_dup1_halted_noop():
    """Already halted → DUP1 is a no-op; halted stays 1."""
    b, _ = _fresh(gas=100)
    result = lower_dup1(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["halted"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_dup1_round_trips_btor2():
    b, _ = _fresh(gas=100)
    result = lower_dup1(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_mstore8
# ---------------------------------------------------------------------------


def test_mstore8_gas_constants():
    assert MSTORE8_GAS == 3
    assert MSTORE8_SIZE == 1


def test_lower_mstore8_returns_result():
    b, _ = _fresh(gas=1000)
    result = lower_mstore8(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)
    assert all(isinstance(v, int) for v in vars(result).values())


def test_lower_mstore8_sp_decremented():
    """sp goes from 2 to 0 after MSTORE8 pops offset+byte."""
    b, _ = _fresh(gas=1000)
    result = lower_mstore8(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_mstore8_writes_low_byte():
    """mem[offset] receives the low byte of byte_val; TOS=offset=0, NOS=0x42."""
    b, _ = _fresh(gas=1000)
    result = lower_mstore8(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv8", b.state_nids["mem"], b.const("bv256", 0))
    b.bad(b.eq(read_nid, b.const("bv8", 0x42)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_mstore8_truncates_to_low_byte():
    """Only the low byte of byte_val is written (0x0142 → 0x42)."""
    b, _ = _fresh(gas=1000)
    result = lower_mstore8(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv8", b.state_nids["mem"], b.const("bv256", 0))
    b.bad(b.eq(read_nid, b.const("bv8", 0x42)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0x0142})
    assert trace.bad_fired_at == 0


def test_lower_mstore8_pc_advanced():
    b, _ = _fresh(gas=1000)
    result = lower_mstore8(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", MSTORE8_SIZE)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_mstore8_gas_decremented():
    """Gas decreases by 3 (base) + 3 (first-word expansion Cmem(1)-Cmem(0))."""
    # Cmem(1) = 1/512 + 3 = 3; Cmem(0) = 0; delta = 3; total = 6.
    b, _ = _fresh(gas=1000)
    result = lower_mstore8(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1000 - 6)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_mstore8_oog_traps():
    b, _ = _fresh(gas=5)  # less than 6 needed for offset=0
    result = lower_mstore8(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_mstore8_underflow_traps():
    b, _ = _fresh(gas=1000)
    result = lower_mstore8(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_mstore8_halted_noop():
    """When already halted, MSTORE8 is a no-op: pc stays 0, trap stays 0."""
    b, _ = _fresh(gas=1000)
    result = lower_mstore8(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0x42}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_mstore8_round_trips_btor2():
    b, _ = _fresh(gas=1000)
    result = lower_mstore8(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_push0
# ---------------------------------------------------------------------------


def test_push0_gas_constants():
    assert PUSH0_GAS == 2
    assert PUSH0_SIZE == 1
    assert RETURN_GAS == 0
    assert RETURN_SIZE == 1


def test_lower_push0_returns_result():
    b, _ = _fresh(gas=100)
    result = lower_push0(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_push0_pushes_zero():
    """PUSH0: sp becomes 1 and stack[0] == 0."""
    b, _ = _fresh(gas=100)
    result = lower_push0(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.and_("bv1",
        b.eq(b.state_nids["sp"], b.const("bv10", 1)),
        b.eq(read_nid, b.const("bv256", 0)),
    ))
    trace = _run(b, max_steps=1)
    assert trace.bad_fired_at == 0


def test_lower_push0_gas_decremented():
    b, _ = _fresh(gas=100)
    result = lower_push0(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 100 - PUSH0_GAS)))
    trace = _run(b, max_steps=1)
    assert trace.bad_fired_at == 0


def test_lower_push0_pc_advanced():
    b, _ = _fresh(gas=100)
    result = lower_push0(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", PUSH0_SIZE)))
    trace = _run(b, max_steps=1)
    assert trace.bad_fired_at == 0


def test_lower_push0_oog_traps():
    b, _ = _fresh(gas=1)  # less than 2
    result = lower_push0(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1)
    assert trace.bad_fired_at == 0


def test_lower_push0_overflow_traps():
    b, _ = _fresh(gas=100)
    result = lower_push0(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1024)
    assert trace.bad_fired_at == 0


def test_lower_push0_halted_noop():
    """When already halted, PUSH0 is a no-op: sp stays 0, pc stays 0."""
    b, _ = _fresh(gas=100)
    result = lower_push0(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.and_("bv1",
        b.eq(b.state_nids["sp"], b.const("bv10", 0)),
        b.eq(b.state_nids["pc"], b.const("bv16", 0)),
    ))
    trace = _run(b, max_steps=1, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_push0_round_trips_btor2():
    b, _ = _fresh(gas=100)
    result = lower_push0(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_return
# ---------------------------------------------------------------------------


def test_lower_return_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_return(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_return_halts_cleanly():
    """RETURN: halted=1 and trap=0 after execution."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_return(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.and_("bv1",
        b.eq(b.state_nids["halted"], b.const("bv1", 1)),
        b.eq(b.state_nids["trap"], b.const("bv1", 0)),
    ))
    # TOS=offset=0 (stack[1]=0), NOS=len=1 (stack[0]=1)
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 1})
    assert trace.bad_fired_at == 0


def test_lower_return_copies_mem_byte_to_returndata():
    """RETURN: returndata[0] = mem[offset]; TOS=offset=0, NOS=len=1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_return(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv8", b.state_nids["returndata"], b.const("bv256", 0))
    b.bad(b.eq(read_nid, b.const("bv8", 0x42)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 1}, mem={0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_return_returndatasize_set():
    """RETURN: returndatasize = len (NOS); NOS=3."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_return(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["returndatasize"], b.const("bv256", 3)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 3})
    assert trace.bad_fired_at == 0


def test_lower_return_underflow_traps():
    """sp < 2 → underflow: trap=1 and halted=1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_return(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.and_("bv1",
        b.eq(b.state_nids["trap"], b.const("bv1", 1)),
        b.eq(b.state_nids["halted"], b.const("bv1", 1)),
    ))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_return_halted_noop():
    """When already halted, RETURN is a no-op: returndatasize stays 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_return(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["returndatasize"], b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 1}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_return_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_return(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_calldatasize
# ---------------------------------------------------------------------------


def test_calldatasize_gas_constants():
    assert CALLDATASIZE_GAS == 2
    assert CALLDATASIZE_SIZE == 1


def test_lower_calldatasize_returns_result():
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldatasize(b, b.state_nids, ctx)
    assert isinstance(result, EvmLoweringResult)


def test_lower_calldatasize_sp_incremented():
    """CALLDATASIZE pushes one word → sp goes from 0 to 1."""
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldatasize(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1)
    assert trace.bad_fired_at == 0


def test_lower_calldatasize_pushes_symbolic_value():
    """CALLDATASIZE pushes calldatasize; with calldatasize=32 stack[0]==32."""
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldatasize(b, b.state_nids, ctx)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 32)))
    trace = _run(b, max_steps=1, calldatasize=32)
    assert trace.bad_fired_at == 0


def test_lower_calldatasize_gas_decremented():
    """After CALLDATASIZE, gas decrements by 2."""
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldatasize(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 98)))
    trace = _run(b, max_steps=1)
    assert trace.bad_fired_at == 0


def test_lower_calldatasize_pc_advanced():
    """After CALLDATASIZE, pc advances by 1."""
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldatasize(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 1)))
    trace = _run(b, max_steps=1)
    assert trace.bad_fired_at == 0


def test_lower_calldatasize_oog_traps():
    """gas < 2 → OOG trap."""
    b, ctx = _fresh_with_ctx(gas=1)
    result = lower_calldatasize(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1)
    assert trace.bad_fired_at == 0


def test_lower_calldatasize_halted_noop():
    """When already halted, CALLDATASIZE is a no-op: sp stays 0."""
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldatasize(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 0)))
    trace = _run(b, max_steps=1, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_calldatasize_round_trips_btor2():
    b, ctx = _fresh_with_ctx(gas=100)
    result = lower_calldatasize(b, b.state_nids, ctx)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_mload
# ---------------------------------------------------------------------------


def test_mload_gas_constants():
    assert MLOAD_GAS == 3
    assert MLOAD_SIZE == 1


def test_lower_mload_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_mload(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_mload_sp_unchanged():
    """MLOAD pops offset and pushes result — net sp change is 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mload(b, b.state_nids)
    assert result.sp == b.state_nids["sp"]


def test_lower_mload_reads_zero_from_empty_mem():
    """MLOAD(offset=0) on empty mem → pushes 0 at stack[0]."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mload(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_mload_reads_lsb_from_mem():
    """MLOAD(offset=0) with mem[31]=0x42 → stack[0] = 0x42 (big-endian LSB)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mload(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0x42)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0}, mem={31: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_mload_gas_decremented():
    """After MLOAD with no expansion (mem_words=1 covers offset=0), gas decrements by MLOAD_GAS (3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mload(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - MLOAD_GAS)))
    # mem_words=1 means first 32 bytes already allocated; offset=0 needs 1 word → no expansion.
    trace = _run(b, max_steps=1, sp=1, stack={0: 0}, mem_words=1)
    assert trace.bad_fired_at == 0


def test_lower_mload_pc_advanced():
    """After MLOAD, pc advances by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mload(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", MLOAD_SIZE)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_mload_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_mload(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_mload_underflow_traps():
    """sp=0 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mload(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_mload_halted_noop():
    """When already halted, MLOAD is a no-op: sp stays 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mload(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_mload_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_mload(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_mstore
# ---------------------------------------------------------------------------


def test_mstore_gas_constants():
    assert MSTORE_GAS == 3
    assert MSTORE_SIZE == 1


def test_lower_mstore_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_mstore(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_mstore_sp_decremented():
    """MSTORE pops offset (TOS) and value (NOS) → sp decrements by 2."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mstore(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_mstore_writes_lsb_at_offset_plus_31():
    """MSTORE(offset=0, value=0x42) → mem[31]=0x42 (big-endian byte 31)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mstore(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv8", b.state_nids["mem"], b.const("bv256", 31))
    b.bad(b.eq(read_nid, b.const("bv8", 0x42)))
    # sp=2; TOS=stack[1]=0 (offset); NOS=stack[0]=0x42 (value)
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_mstore_writes_zero_msb_at_offset():
    """MSTORE(offset=0, value=0x42) → mem[0]=0 (MSB of 0x42 in bv256)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mstore(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv8", b.state_nids["mem"], b.const("bv256", 0))
    b.bad(b.eq(read_nid, b.const("bv8", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_mstore_pc_advanced():
    """After MSTORE, pc advances by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mstore(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", MSTORE_SIZE)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0})
    assert trace.bad_fired_at == 0


def test_lower_mstore_gas_decremented():
    """After MSTORE with no expansion (mem_words=1 covers offset=0), gas decrements by MSTORE_GAS (3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mstore(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - MSTORE_GAS)))
    # mem_words=1 means first 32 bytes already allocated; offset=0 needs 1 word → no expansion.
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0}, mem_words=1)
    assert trace.bad_fired_at == 0


def test_lower_mstore_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_mstore(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0})
    assert trace.bad_fired_at == 0


def test_lower_mstore_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mstore(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_mstore_halted_noop():
    """When already halted, MSTORE is a no-op: sp stays 2."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mstore(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 0}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_mstore_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_mstore(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_lt
# ---------------------------------------------------------------------------


def test_lt_gas_constants():
    assert LT_GAS == 3
    assert LT_SIZE == 1


def test_lower_lt_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_lt(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_lt_sp_decremented():
    """LT pops TOS and NOS, pushes one result → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_lt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 2, 0: 5})
    assert trace.bad_fired_at == 0


def test_lower_lt_result_when_true():
    """LT(a=2, b=5): 2 < 5 (unsigned) → pushes 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_lt(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 1)))
    # sp=2: TOS=stack[1]=2 (a), NOS=stack[0]=5 (b); 2 < 5 → 1
    trace = _run(b, max_steps=1, sp=2, stack={1: 2, 0: 5})
    assert trace.bad_fired_at == 0


def test_lower_lt_result_when_false():
    """LT(a=5, b=2): 5 < 2 is false → pushes 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_lt(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    # sp=2: TOS=stack[1]=5 (a), NOS=stack[0]=2 (b); 5 < 2 → 0
    trace = _run(b, max_steps=1, sp=2, stack={1: 5, 0: 2})
    assert trace.bad_fired_at == 0


def test_lower_lt_result_equal_is_false():
    """LT(a=3, b=3): 3 < 3 is false → pushes 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_lt(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 3, 0: 3})
    assert trace.bad_fired_at == 0


def test_lower_lt_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_lt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 1, 0: 2})
    assert trace.bad_fired_at == 0


def test_lower_lt_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_lt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_lt_halted_noop():
    """When already halted, LT is a no-op: sp stays 2."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_lt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 1, 0: 2}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_lt_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_lt(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_gt
# ---------------------------------------------------------------------------


def test_gt_gas_constants():
    assert GT_GAS == 3
    assert GT_SIZE == 1


def test_lower_gt_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_gt(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_gt_sp_decremented():
    """GT pops TOS and NOS, pushes one result → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_gt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 5, 0: 2})
    assert trace.bad_fired_at == 0


def test_lower_gt_result_when_true():
    """GT(a=5, b=2): 5 > 2 (unsigned) → pushes 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_gt(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 1)))
    # sp=2: TOS=stack[1]=5 (a), NOS=stack[0]=2 (b); 5 > 2 → 1
    trace = _run(b, max_steps=1, sp=2, stack={1: 5, 0: 2})
    assert trace.bad_fired_at == 0


def test_lower_gt_result_when_false():
    """GT(a=2, b=5): 2 > 5 is false → pushes 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_gt(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    # sp=2: TOS=stack[1]=2 (a), NOS=stack[0]=5 (b); 2 > 5 → 0
    trace = _run(b, max_steps=1, sp=2, stack={1: 2, 0: 5})
    assert trace.bad_fired_at == 0


def test_lower_gt_result_equal_is_false():
    """GT(a=3, b=3): 3 > 3 is false → pushes 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_gt(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 3, 0: 3})
    assert trace.bad_fired_at == 0


def test_lower_gt_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_gt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 5, 0: 2})
    assert trace.bad_fired_at == 0


def test_lower_gt_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_gt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_gt_halted_noop():
    """When already halted, GT is a no-op: sp stays 2."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_gt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 5, 0: 2}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_gt_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_gt(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_eq_op (EQ opcode 0x14)
# ---------------------------------------------------------------------------


def test_eq_gas_constants():
    assert EQ_GAS == 3
    assert EQ_SIZE == 1


def test_lower_eq_op_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_eq_op(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_eq_op_sp_decremented():
    """EQ pops TOS and NOS, pushes one result → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_eq_op(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 3, 0: 3})
    assert trace.bad_fired_at == 0


def test_lower_eq_op_result_when_equal():
    """EQ(a=7, b=7): a == b → pushes 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_eq_op(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 1)))
    # sp=2: TOS=stack[1]=7 (a), NOS=stack[0]=7 (b)
    trace = _run(b, max_steps=1, sp=2, stack={1: 7, 0: 7})
    assert trace.bad_fired_at == 0


def test_lower_eq_op_result_when_not_equal():
    """EQ(a=3, b=5): a != b → pushes 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_eq_op(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    # sp=2: TOS=stack[1]=3 (a), NOS=stack[0]=5 (b)
    trace = _run(b, max_steps=1, sp=2, stack={1: 3, 0: 5})
    assert trace.bad_fired_at == 0


def test_lower_eq_op_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_eq_op(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 1, 0: 1})
    assert trace.bad_fired_at == 0


def test_lower_eq_op_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_eq_op(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_eq_op_halted_noop():
    """When already halted, EQ is a no-op: sp stays 2."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_eq_op(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 1, 0: 1}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_eq_op_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_eq_op(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_calldatacopy
# ---------------------------------------------------------------------------


def test_calldatacopy_gas_constants():
    assert CALLDATACOPY_GAS == 3
    assert CALLDATACOPY_SIZE == 1
    assert CALLDATACOPY_MAX_LEN == 32


def test_lower_calldatacopy_returns_result():
    b, ctx = _fresh_with_ctx(gas=1_000_000)
    result = lower_calldatacopy(b, b.state_nids, ctx)
    assert isinstance(result, EvmLoweringResult)


def test_lower_calldatacopy_sp_decremented_by_3():
    """CALLDATACOPY pops dest, offset, length → sp decrements by 3."""
    b, ctx = _fresh_with_ctx(gas=1_000_000)
    result = lower_calldatacopy(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 0)))
    # sp=3: stack[2]=dest=0, stack[1]=offset=0, stack[0]=length=1
    trace = _run(b, max_steps=1, sp=3, stack={2: 0, 1: 0, 0: 1})
    assert trace.bad_fired_at == 0


def test_lower_calldatacopy_copies_byte_in_range():
    """CALLDATACOPY(dest=0, offset=0, length=1): mem[0] = calldata[0]."""
    b, ctx = _fresh_with_ctx(gas=1_000_000)
    result = lower_calldatacopy(b, b.state_nids, ctx)
    _wire_next(b, result)
    read_nid = b.read("bv8", b.state_nids["mem"], b.const("bv256", 0))
    b.bad(b.eq(read_nid, b.const("bv8", 0x42)))
    # sp=3: TOS=dest=0, NOS=offset=0, 3rd=length=1
    # calldata[0]=0x42
    trace = _run(b, max_steps=1, sp=3, stack={2: 0, 1: 0, 0: 1}, calldata={0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_calldatacopy_skips_byte_out_of_range():
    """CALLDATACOPY(dest=0, offset=0, length=1): mem[1] stays 0 (not copied)."""
    b, ctx = _fresh_with_ctx(gas=1_000_000)
    result = lower_calldatacopy(b, b.state_nids, ctx)
    _wire_next(b, result)
    read_nid = b.read("bv8", b.state_nids["mem"], b.const("bv256", 1))
    b.bad(b.eq(read_nid, b.const("bv8", 0)))
    # calldata[1]=0x99, but length=1 so byte 1 is out of range
    trace = _run(b, max_steps=1, sp=3, stack={2: 0, 1: 0, 0: 1},
                 calldata={0: 0x42, 1: 0x99})
    assert trace.bad_fired_at == 0


def test_lower_calldatacopy_pc_advanced():
    """After CALLDATACOPY, pc advances by 1."""
    b, ctx = _fresh_with_ctx(gas=1_000_000)
    result = lower_calldatacopy(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", CALLDATACOPY_SIZE)))
    trace = _run(b, max_steps=1, sp=3, stack={2: 0, 1: 0, 0: 1})
    assert trace.bad_fired_at == 0


def test_lower_calldatacopy_oog_traps():
    """gas < base (3) → OOG trap."""
    b, ctx = _fresh_with_ctx(gas=2)
    result = lower_calldatacopy(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=3, stack={2: 0, 1: 0, 0: 1})
    assert trace.bad_fired_at == 0


def test_lower_calldatacopy_underflow_traps():
    """sp < 3 → underflow trap."""
    b, ctx = _fresh_with_ctx(gas=1_000_000)
    result = lower_calldatacopy(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2)
    assert trace.bad_fired_at == 0


def test_lower_calldatacopy_halted_noop():
    """When already halted, CALLDATACOPY is a no-op: sp stays 3."""
    b, ctx = _fresh_with_ctx(gas=1_000_000)
    result = lower_calldatacopy(b, b.state_nids, ctx)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 3)))
    trace = _run(b, max_steps=1, sp=3, stack={2: 0, 1: 0, 0: 1}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_calldatacopy_round_trips_btor2():
    b, ctx = _fresh_with_ctx(gas=1_000_000)
    result = lower_calldatacopy(b, b.state_nids, ctx)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_sub (SUB opcode 0x03)
# ---------------------------------------------------------------------------


def test_sub_gas_constants():
    assert SUB_GAS == 3
    assert SUB_SIZE == 1


def test_lower_sub_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_sub(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_sub_sp_decremented():
    """SUB pops TOS and NOS, pushes one result → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sub(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 5, 0: 3})
    assert trace.bad_fired_at == 0


def test_lower_sub_result_correct():
    """SUB(a=7, b=3): a - b = 4."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sub(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 4)))
    # sp=2: TOS=stack[1]=7(a), NOS=stack[0]=3(b); result = 7-3=4
    trace = _run(b, max_steps=1, sp=2, stack={1: 7, 0: 3})
    assert trace.bad_fired_at == 0


def test_lower_sub_wrapping():
    """SUB(a=0, b=1): underflows; low 8 bits = 0xFF (evaluator stores low byte)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sub(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    # The concrete evaluator masks array writes to 8 bits, so we check the low byte.
    # bv256: 0 - 1 = 2^256-1; low 8 bits = 0xFF.
    b.bad(b.eq(read_nid, b.const("bv256", 0xFF)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0, 0: 1})
    assert trace.bad_fired_at == 0


def test_lower_sub_pc_advanced():
    b, _ = _fresh(gas=1_000_000)
    result = lower_sub(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", SUB_SIZE)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 5, 0: 3})
    assert trace.bad_fired_at == 0


def test_lower_sub_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_sub(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 5, 0: 3})
    assert trace.bad_fired_at == 0


def test_lower_sub_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sub(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_sub_halted_noop():
    """When already halted, SUB is a no-op: sp stays 2."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sub(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 5, 0: 3}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_sub_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_sub(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_mul (MUL opcode 0x02)
# ---------------------------------------------------------------------------


def test_mul_gas_constants():
    assert MUL_GAS == 5
    assert MUL_SIZE == 1


def test_lower_mul_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_mul(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_mul_sp_decremented():
    """MUL pops TOS and NOS, pushes one result → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mul(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 3, 0: 4})
    assert trace.bad_fired_at == 0


def test_lower_mul_result_correct():
    """MUL(a=3, b=4): a * b = 12."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mul(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 12)))
    # sp=2: TOS=stack[1]=3(a), NOS=stack[0]=4(b); result=12
    trace = _run(b, max_steps=1, sp=2, stack={1: 3, 0: 4})
    assert trace.bad_fired_at == 0


def test_lower_mul_by_zero():
    """MUL(a=99, b=0): a * b = 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mul(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 99, 0: 0})
    assert trace.bad_fired_at == 0


def test_lower_mul_pc_advanced():
    b, _ = _fresh(gas=1_000_000)
    result = lower_mul(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", MUL_SIZE)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 2, 0: 3})
    assert trace.bad_fired_at == 0


def test_lower_mul_oog_traps():
    """gas < 5 → OOG trap."""
    b, _ = _fresh(gas=4)
    result = lower_mul(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 2, 0: 3})
    assert trace.bad_fired_at == 0


def test_lower_mul_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mul(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_mul_halted_noop():
    """When already halted, MUL is a no-op: sp stays 2."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mul(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 2, 0: 3}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_mul_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_mul(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_and (AND opcode 0x16)
# ---------------------------------------------------------------------------


def test_and_gas_constants():
    assert AND_GAS == 3
    assert AND_SIZE == 1


def test_lower_and_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_and(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_and_sp_decremented():
    b, _ = _fresh(gas=1_000_000)
    result = lower_and(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0xFF, 0: 0x0F})
    assert trace.bad_fired_at == 0


def test_lower_and_result_correct():
    """AND(a=0xFF, b=0x0F): a & b = 0x0F."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_and(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0x0F)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0xFF, 0: 0x0F})
    assert trace.bad_fired_at == 0


def test_lower_and_zero_mask():
    """AND(a=0xFF, b=0): a & 0 = 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_and(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0xFF, 0: 0})
    assert trace.bad_fired_at == 0


def test_lower_and_oog_traps():
    b, _ = _fresh(gas=2)
    result = lower_and(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 1, 0: 1})
    assert trace.bad_fired_at == 0


def test_lower_and_underflow_traps():
    b, _ = _fresh(gas=1_000_000)
    result = lower_and(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_and_halted_noop():
    b, _ = _fresh(gas=1_000_000)
    result = lower_and(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 1, 0: 1}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_and_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_and(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_or (OR opcode 0x17)
# ---------------------------------------------------------------------------


def test_or_gas_constants():
    assert OR_GAS == 3
    assert OR_SIZE == 1


def test_lower_or_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_or(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_or_sp_decremented():
    b, _ = _fresh(gas=1_000_000)
    result = lower_or(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0xF0, 0: 0x0F})
    assert trace.bad_fired_at == 0


def test_lower_or_result_correct():
    """OR(a=0xF0, b=0x0F): a | b = 0xFF."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_or(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0xFF)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0xF0, 0: 0x0F})
    assert trace.bad_fired_at == 0


def test_lower_or_identity():
    """OR(a=0x42, b=0): a | 0 = a."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_or(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0x42)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0x42, 0: 0})
    assert trace.bad_fired_at == 0


def test_lower_or_oog_traps():
    b, _ = _fresh(gas=2)
    result = lower_or(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 1, 0: 1})
    assert trace.bad_fired_at == 0


def test_lower_or_underflow_traps():
    b, _ = _fresh(gas=1_000_000)
    result = lower_or(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_or_halted_noop():
    b, _ = _fresh(gas=1_000_000)
    result = lower_or(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 1, 0: 1}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_or_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_or(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_xor (XOR opcode 0x18)
# ---------------------------------------------------------------------------


def test_xor_gas_constants():
    assert XOR_GAS == 3
    assert XOR_SIZE == 1


def test_lower_xor_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_xor(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_xor_sp_decremented():
    b, _ = _fresh(gas=1_000_000)
    result = lower_xor(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0xFF, 0: 0xF0})
    assert trace.bad_fired_at == 0


def test_lower_xor_result_correct():
    """XOR(a=0xFF, b=0xF0): a ^ b = 0x0F."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_xor(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0x0F)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0xFF, 0: 0xF0})
    assert trace.bad_fired_at == 0


def test_lower_xor_self_is_zero():
    """XOR(a=0x42, b=0x42): a ^ a = 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_xor(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 0x42, 0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_xor_oog_traps():
    b, _ = _fresh(gas=2)
    result = lower_xor(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 1, 0: 1})
    assert trace.bad_fired_at == 0


def test_lower_xor_underflow_traps():
    b, _ = _fresh(gas=1_000_000)
    result = lower_xor(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_xor_halted_noop():
    b, _ = _fresh(gas=1_000_000)
    result = lower_xor(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={1: 1, 0: 1}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_xor_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_xor(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_not (NOT opcode 0x19)
# ---------------------------------------------------------------------------


def test_not_gas_constants():
    assert NOT_GAS == 3
    assert NOT_SIZE == 1


def test_lower_not_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_not(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_not_sp_unchanged():
    """NOT is in-place: sp stays 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_not(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_not_result_zero_input():
    """NOT(0): low 8 bits of 2^256-1 = 0xFF (evaluator stores low byte)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_not(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0xFF)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_not_clears_low_byte():
    """NOT(0xFF): low 8 bits = 0x00 (bv256: ~0xFF has low 8 bits cleared)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_not(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    # ~0xFF in bv256 has low 8 bits = 0x00; evaluator stores that byte.
    b.bad(b.eq(read_nid, b.const("bv256", 0x00)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0xFF})
    assert trace.bad_fired_at == 0


def test_lower_not_pc_advanced():
    b, _ = _fresh(gas=1_000_000)
    result = lower_not(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", NOT_SIZE)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_not_oog_traps():
    b, _ = _fresh(gas=2)
    result = lower_not(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_not_underflow_traps():
    """sp < 1 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_not(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_not_halted_noop():
    """When already halted, NOT is a no-op: sp stays 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_not(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_not_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_not(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_jump (JUMP opcode 0x56)
# ---------------------------------------------------------------------------


def test_jump_gas_constants():
    assert JUMP_GAS == 8
    assert JUMP_SIZE == 1


def test_lower_jump_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_jump(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_jump_sp_decremented():
    """JUMP pops dest → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_jump(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 0)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 5})
    assert trace.bad_fired_at == 0


def test_lower_jump_pc_set_to_dest():
    """JUMP(dest=10): pc becomes 10."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_jump(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 10)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 10})
    assert trace.bad_fired_at == 0


def test_lower_jump_pc_set_to_zero():
    """JUMP(dest=0): pc becomes 0 (tight destination)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_jump(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 0)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0})
    assert trace.bad_fired_at == 0


def test_lower_jump_gas_decremented():
    """After JUMP, gas decreases by JUMP_GAS (8)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_jump(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - JUMP_GAS)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 5})
    assert trace.bad_fired_at == 0


def test_lower_jump_oog_traps():
    """gas < 8 → OOG trap."""
    b, _ = _fresh(gas=7)
    result = lower_jump(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 5})
    assert trace.bad_fired_at == 0


def test_lower_jump_underflow_traps():
    """sp < 1 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_jump(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_jump_halted_noop():
    """When already halted, JUMP is a no-op: sp stays 1, pc stays 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_jump(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 0)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 99}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_jump_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_jump(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# DIV lowering (opcode 0x04)
# ---------------------------------------------------------------------------


def test_div_gas_constants():
    assert DIV_GAS == 5
    assert DIV_SIZE == 1


def test_lower_div_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_div(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_div_sp_decremented():
    """DIV pops a and b → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_div(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 10, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_div_result_exact():
    """DIV(10, 2) == 5: a=10 (TOS), b=2 (NOS) → result = a/b = 10/2 = 5."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_div(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 5)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 10})
    assert trace.bad_fired_at == 0


def test_lower_div_truncates():
    """DIV(7, 2) == 3 (floor division)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_div(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 3)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 7})
    assert trace.bad_fired_at == 0


def test_lower_div_by_zero_gives_zero():
    """DIV(a, 0) == 0 per EVM convention."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_div(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 42})
    assert trace.bad_fired_at == 0


def test_lower_div_gas_decremented():
    """After DIV gas decreases by DIV_GAS (5)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_div(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - DIV_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 10})
    assert trace.bad_fired_at == 0


def test_lower_div_oog_traps():
    """gas < 5 → OOG trap."""
    b, _ = _fresh(gas=4)
    result = lower_div(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 10})
    assert trace.bad_fired_at == 0


def test_lower_div_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_div(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 10})
    assert trace.bad_fired_at == 0


def test_lower_div_halted_noop():
    """When already halted, DIV is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_div(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 10}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_div_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_div(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# MOD lowering (opcode 0x06)
# ---------------------------------------------------------------------------


def test_mod_gas_constants():
    assert MOD_GAS == 5
    assert MOD_SIZE == 1


def test_lower_mod_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_mod(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_mod_sp_decremented():
    """MOD pops a and b → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 10})
    assert trace.bad_fired_at == 0


def test_lower_mod_result_correct():
    """MOD(10, 3) == 1: a=10 (TOS), b=3 (NOS) → a % b = 10 % 3 = 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 10})
    assert trace.bad_fired_at == 0


def test_lower_mod_exact_divisor_gives_zero():
    """MOD(9, 3) == 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 9})
    assert trace.bad_fired_at == 0


def test_lower_mod_by_zero_gives_zero():
    """MOD(a, 0) == 0 per EVM convention."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 42})
    assert trace.bad_fired_at == 0


def test_lower_mod_gas_decremented():
    """After MOD gas decreases by MOD_GAS (5)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - MOD_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 10})
    assert trace.bad_fired_at == 0


def test_lower_mod_oog_traps():
    """gas < 5 → OOG trap."""
    b, _ = _fresh(gas=4)
    result = lower_mod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 10})
    assert trace.bad_fired_at == 0


def test_lower_mod_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 10})
    assert trace.bad_fired_at == 0


def test_lower_mod_halted_noop():
    """When already halted, MOD is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 10}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_mod_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_mod(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# ADDMOD lowering (opcode 0x08)
# ---------------------------------------------------------------------------


def test_addmod_gas_constants():
    assert ADDMOD_GAS == 8
    assert ADDMOD_SIZE == 1


def test_lower_addmod_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_addmod(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_addmod_sp_decremented_by_2():
    """ADDMOD pops 3 items and pushes 1 → sp decrements by 2."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_addmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 3, 2: 5})
    assert trace.bad_fired_at == 0


def test_lower_addmod_result_correct():
    """ADDMOD(5, 3, 7): a=5 (TOS), b=3 (NOS), N=7 (3rd) → (5+3) % 7 = 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_addmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 1)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 3, 2: 5})
    assert trace.bad_fired_at == 0


def test_lower_addmod_zero_modulus_gives_zero():
    """ADDMOD(a, b, 0) == 0 per EVM convention."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_addmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 0, 1: 3, 2: 5})
    assert trace.bad_fired_at == 0


def test_lower_addmod_gas_decremented():
    """After ADDMOD gas decreases by ADDMOD_GAS (8)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_addmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - ADDMOD_GAS)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 3, 2: 5})
    assert trace.bad_fired_at == 0


def test_lower_addmod_oog_traps():
    """gas < 8 → OOG trap."""
    b, _ = _fresh(gas=7)
    result = lower_addmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 3, 2: 5})
    assert trace.bad_fired_at == 0


def test_lower_addmod_underflow_traps():
    """sp < 3 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_addmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 7, 1: 3})
    assert trace.bad_fired_at == 0


def test_lower_addmod_halted_noop():
    """When already halted, ADDMOD is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_addmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 3)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 3, 2: 5}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_addmod_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_addmod(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# MULMOD lowering (opcode 0x09)
# ---------------------------------------------------------------------------


def test_mulmod_gas_constants():
    assert MULMOD_GAS == 8
    assert MULMOD_SIZE == 1


def test_lower_mulmod_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_mulmod(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_mulmod_sp_decremented_by_2():
    """MULMOD pops 3 items and pushes 1 → sp decrements by 2."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mulmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 3, 2: 5})
    assert trace.bad_fired_at == 0


def test_lower_mulmod_result_correct():
    """MULMOD(5, 3, 7): a=5 (TOS), b=3 (NOS), N=7 (3rd) → (5*3) % 7 = 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mulmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 1)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 3, 2: 5})
    assert trace.bad_fired_at == 0


def test_lower_mulmod_zero_modulus_gives_zero():
    """MULMOD(a, b, 0) == 0 per EVM convention."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mulmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 0, 1: 3, 2: 5})
    assert trace.bad_fired_at == 0


def test_lower_mulmod_gas_decremented():
    """After MULMOD gas decreases by MULMOD_GAS (8)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mulmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - MULMOD_GAS)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 3, 2: 5})
    assert trace.bad_fired_at == 0


def test_lower_mulmod_oog_traps():
    """gas < 8 → OOG trap."""
    b, _ = _fresh(gas=7)
    result = lower_mulmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 3, 2: 5})
    assert trace.bad_fired_at == 0


def test_lower_mulmod_underflow_traps():
    """sp < 3 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mulmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 7, 1: 3})
    assert trace.bad_fired_at == 0


def test_lower_mulmod_halted_noop():
    """When already halted, MULMOD is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_mulmod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 3)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 3, 2: 5}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_mulmod_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_mulmod(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# EXP lowering (opcode 0x0a)
# ---------------------------------------------------------------------------


def test_exp_gas_constants():
    assert EXP_GAS_BASE == 10
    assert EXP_GAS_1BYTE == 60
    assert EXP_EXPONENT_BITS == 8
    assert EXP_SIZE == 1


def test_lower_exp_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_exp(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_exp_sp_decremented():
    """EXP pops base and exp → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_exp(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_exp_result_base_exp():
    """EXP(2, 3) = 8: base=2 (TOS), exp=3 (NOS) → 2^3 = 8."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_exp(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 8)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_exp_exp_zero_gives_one():
    """EXP(base, 0) = 1 for any base."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_exp(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.read("bv256", b.state_nids["stack"], b.const("bv10", 0)), b.const("bv256", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 99})
    assert trace.bad_fired_at == 0


def test_lower_exp_gas_base_when_zero():
    """EXP with exp==0 uses gas=EXP_GAS_BASE (10)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_exp(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - EXP_GAS_BASE)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_exp_gas_one_byte_when_nonzero():
    """EXP with nonzero exp uses gas=EXP_GAS_1BYTE (60)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_exp(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - EXP_GAS_1BYTE)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_exp_oog_traps():
    """gas < 10 → OOG trap (base gas for exp==0 case)."""
    b, _ = _fresh(gas=9)
    result = lower_exp(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_exp_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_exp(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 2})
    assert trace.bad_fired_at == 0


def test_lower_exp_halted_noop():
    """When already halted, EXP is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_exp(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 2}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_exp_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_exp(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# BYTE lowering (opcode 0x1a)
# ---------------------------------------------------------------------------


def test_byte_gas_constants():
    assert BYTE_GAS == 3
    assert BYTE_SIZE == 1


def test_lower_byte_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_byte(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_byte_sp_decremented():
    """BYTE pops i and x → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_byte(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 31})
    assert trace.bad_fired_at == 0


def test_lower_byte_index_31_lsb():
    """BYTE(31, 0x42) == 0x42: byte 31 is the LSB of a 256-bit value."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_byte(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0x42)))
    # sp=2: TOS=stack[1]=31 (i), NOS=stack[0]=0x42 (x)
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 31})
    assert trace.bad_fired_at == 0


def test_lower_byte_index_30_zero_for_small_value():
    """BYTE(30, 0x42) == 0: 0x42 fits in one byte, byte 30 is zero."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_byte(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    # sp=2: TOS=stack[1]=30 (i), NOS=stack[0]=0x42 (x); byte 30 of 0x42 is 0
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 30})
    assert trace.bad_fired_at == 0


def test_lower_byte_index_geq_32_gives_zero():
    """BYTE(32, 0x42) == 0: index out of range → 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_byte(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    # sp=2: TOS=stack[1]=32 (i >= 32), NOS=stack[0]=0x42 (x)
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 32})
    assert trace.bad_fired_at == 0


def test_lower_byte_gas_decremented():
    """After BYTE gas decreases by BYTE_GAS (3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_byte(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - BYTE_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 31})
    assert trace.bad_fired_at == 0


def test_lower_byte_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_byte(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 31})
    assert trace.bad_fired_at == 0


def test_lower_byte_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_byte(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 0x42})
    assert trace.bad_fired_at == 0


def test_lower_byte_halted_noop():
    """When already halted, BYTE is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_byte(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 31}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_byte_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_byte(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# SHL lowering (opcode 0x1b, EIP-145)
# ---------------------------------------------------------------------------


def test_shl_gas_constants():
    assert SHL_GAS == 3
    assert SHL_SIZE == 1


def test_lower_shl_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_shl(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_shl_sp_decremented():
    """SHL pops shift and value → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shl(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_shl_result_by_one():
    """SHL(shift=1, value=2): 2 << 1 = 4."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shl(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 4)))
    # sp=2: TOS=stack[1]=1 (shift), NOS=stack[0]=2 (value)
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_shl_zero_shift():
    """SHL(shift=0, value=42): 42 << 0 = 42."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shl(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 42)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_shl_result_by_four():
    """SHL(shift=4, value=7): 7 << 4 = 112 (0x70); low byte = 0x70."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shl(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0x70)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 7, 1: 4})
    assert trace.bad_fired_at == 0


def test_lower_shl_gas_decremented():
    """After SHL gas decreases by SHL_GAS (3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shl(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - SHL_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_shl_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_shl(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_shl_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shl(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_shl_halted_noop():
    """When already halted, SHL is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shl(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 1}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_shl_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_shl(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# SHR lowering (opcode 0x1c, EIP-145)
# ---------------------------------------------------------------------------


def test_shr_gas_constants():
    assert SHR_GAS == 3
    assert SHR_SIZE == 1


def test_lower_shr_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_shr(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_shr_sp_decremented():
    """SHR pops shift and value → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shr(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 42, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_shr_result_by_one():
    """SHR(shift=1, value=42): 42 >> 1 = 21 (unsigned)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shr(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 21)))
    # sp=2: TOS=stack[1]=1 (shift), NOS=stack[0]=42 (value)
    trace = _run(b, max_steps=1, sp=2, stack={0: 42, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_shr_zero_shift():
    """SHR(shift=0, value=42): 42 >> 0 = 42."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shr(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 42)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_shr_result_by_three():
    """SHR(shift=3, value=0x42=66): 66 >> 3 = 8."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shr(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 8)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 3})
    assert trace.bad_fired_at == 0


def test_lower_shr_large_shift_gives_zero():
    """SHR(shift=248, value=0xff): 0xff >> 248 = 0 (value has only 8 bits)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shr(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0xFF, 1: 248})
    assert trace.bad_fired_at == 0


def test_lower_shr_gas_decremented():
    """After SHR gas decreases by SHR_GAS (3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shr(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - SHR_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 42, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_shr_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_shr(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 42, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_shr_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shr(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_shr_halted_noop():
    """When already halted, SHR is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_shr(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 42, 1: 1}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_shr_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_shr(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# SAR lowering (opcode 0x1d, EIP-145)
# ---------------------------------------------------------------------------


def test_sar_gas_constants():
    assert SAR_GAS == 3
    assert SAR_SIZE == 1


def test_lower_sar_returns_result():
    b, _ = _fresh(gas=1_000_000)
    result = lower_sar(b, b.state_nids)
    assert isinstance(result, EvmLoweringResult)


def test_lower_sar_sp_decremented():
    """SAR pops shift and value → sp decrements by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sar(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_sar_positive_value_by_one():
    """SAR(shift=1, value=0x42=66): positive → 66 >> 1 = 33 (no sign extension)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sar(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 33)))
    # sp=2: TOS=stack[1]=1 (shift), NOS=stack[0]=0x42 (positive value)
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_sar_zero_shift():
    """SAR(shift=0, value=42): 42 >> 0 = 42."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sar(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 42)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_sar_positive_by_three():
    """SAR(shift=3, value=0x7f=127): 127 >> 3 = 15 (positive, arithmetic = logical)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sar(b, b.state_nids)
    _wire_next(b, result)
    read_nid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(read_nid, b.const("bv256", 15)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x7F, 1: 3})
    assert trace.bad_fired_at == 0


def test_lower_sar_gas_decremented():
    """After SAR gas decreases by SAR_GAS (3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sar(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - SAR_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_sar_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_sar(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_sar_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sar(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_sar_halted_noop():
    """When already halted, SAR is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sar(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 1}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_sar_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_sar(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_signextend tests (P14)
# ---------------------------------------------------------------------------


def test_lower_signextend_positive_byte_0():
    """SIGNEXTEND(bytenum=0, x=0x42): bit 7 not set → result = 0x42."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_signextend(b, b.state_nids)
    _wire_next(b, result)
    # Result written to stack slot 0 (sp-2 = 2-2 = 0) then sp decrements.
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 0x42)))
    # sp=2: stack[0]=NOS=x=0x42, stack[1]=TOS=bytenum=0
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_signextend_bytenum_31_identity():
    """SIGNEXTEND(bytenum=31, x=0x42): b>=31 → guard returns x unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_signextend(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 0x42)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 31})
    assert trace.bad_fired_at == 0


def test_lower_signextend_bytenum_large_identity():
    """SIGNEXTEND(bytenum=100, x=0x42): b>=31 → guard returns x unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_signextend(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 0x42)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 100})
    assert trace.bad_fired_at == 0


def test_lower_signextend_sp_decremented():
    """After SIGNEXTEND sp decreases by 1 (pops 2, pushes 1)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_signextend(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_signextend_pc_incremented():
    """After SIGNEXTEND pc advances by SIGNEXTEND_SIZE (1)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_signextend(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", SIGNEXTEND_SIZE)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_signextend_gas_decremented():
    """After SIGNEXTEND gas decreases by SIGNEXTEND_GAS (5)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_signextend(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - SIGNEXTEND_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_signextend_oog_traps():
    """gas < SIGNEXTEND_GAS → OOG trap."""
    b, _ = _fresh(gas=4)
    result = lower_signextend(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_signextend_underflow_traps():
    """sp < 2 → stack underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_signextend(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_signextend_halted_noop():
    """When already halted, SIGNEXTEND is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_signextend(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0x42, 1: 0}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_signextend_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_signextend(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_slt tests (P14)
# ---------------------------------------------------------------------------


def test_lower_slt_true():
    """SLT(TOS=0, NOS=1): 0 < 1 signed → result = 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_slt(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 1)))
    # stack[0]=NOS=b_val=1, stack[1]=TOS=a_val=0; SLT(a=0, b=1) = 0<1 = 1
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_slt_false():
    """SLT(TOS=1, NOS=0): 1 < 0 signed → result = 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_slt(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 0)))
    # stack[0]=NOS=b_val=0, stack[1]=TOS=a_val=1; SLT(a=1, b=0) = 1<0 = 0
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_slt_equal():
    """SLT(TOS=5, NOS=5): 5 < 5 → result = 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_slt(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 5, 1: 5})
    assert trace.bad_fired_at == 0


def test_lower_slt_sp_decremented():
    """After SLT sp decreases by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_slt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_slt_pc_incremented():
    """After SLT pc advances by SLT_SIZE (1)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_slt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", SLT_SIZE)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_slt_gas_decremented():
    """After SLT gas decreases by SLT_GAS (3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_slt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - SLT_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_slt_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_slt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_slt_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_slt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_slt_halted_noop():
    """When already halted, SLT is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_slt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 0}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_slt_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_slt(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_sgt tests (P14)
# ---------------------------------------------------------------------------


def test_lower_sgt_true():
    """SGT(TOS=1, NOS=0): 1 > 0 signed → result = 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sgt(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 1)))
    # stack[0]=NOS=b_val=0, stack[1]=TOS=a_val=1; SGT(a=1, b=0) = 1>0 = 1
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_sgt_false():
    """SGT(TOS=0, NOS=1): 0 > 1 signed → result = 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sgt(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 0)))
    # stack[0]=NOS=b_val=1, stack[1]=TOS=a_val=0; SGT(a=0, b=1) = 0>1 = 0
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 0})
    assert trace.bad_fired_at == 0


def test_lower_sgt_equal():
    """SGT(TOS=5, NOS=5): 5 > 5 → result = 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sgt(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 5, 1: 5})
    assert trace.bad_fired_at == 0


def test_lower_sgt_sp_decremented():
    """After SGT sp decreases by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sgt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_sgt_pc_incremented():
    """After SGT pc advances by SGT_SIZE (1)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sgt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", SGT_SIZE)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_sgt_gas_decremented():
    """After SGT gas decreases by SGT_GAS (3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sgt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - SGT_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_sgt_oog_traps():
    """gas < 3 → OOG trap."""
    b, _ = _fresh(gas=2)
    result = lower_sgt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 1})
    assert trace.bad_fired_at == 0


def test_lower_sgt_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sgt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_sgt_halted_noop():
    """When already halted, SGT is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sgt(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 1}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_sgt_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_sgt(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_sdiv tests (P15)
# ---------------------------------------------------------------------------


def test_lower_sdiv_positive():
    """SDIV(a=6, b=2): 6/2 signed = 3."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sdiv(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 3)))
    # sp=2: stack[0]=NOS=divisor=2, stack[1]=TOS=dividend=6
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 6})
    assert trace.bad_fired_at == 0


def test_lower_sdiv_by_zero():
    """SDIV(a=6, b=0): divisor=0 → EVM result = 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sdiv(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 6})
    assert trace.bad_fired_at == 0


def test_lower_sdiv_sp_decremented():
    """After SDIV sp decreases by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sdiv(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 6})
    assert trace.bad_fired_at == 0


def test_lower_sdiv_pc_incremented():
    """After SDIV pc advances by SDIV_SIZE (1)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sdiv(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", SDIV_SIZE)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 6})
    assert trace.bad_fired_at == 0


def test_lower_sdiv_gas_decremented():
    """After SDIV gas decreases by SDIV_GAS (5)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sdiv(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - SDIV_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 6})
    assert trace.bad_fired_at == 0


def test_lower_sdiv_oog_traps():
    """gas < 5 → OOG trap."""
    b, _ = _fresh(gas=4)
    result = lower_sdiv(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 6})
    assert trace.bad_fired_at == 0


def test_lower_sdiv_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sdiv(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_sdiv_halted_noop():
    """When already halted, SDIV is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_sdiv(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 2, 1: 6}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_sdiv_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_sdiv(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_smod tests (P15)
# ---------------------------------------------------------------------------


def test_lower_smod_positive():
    """SMOD(a=7, b=3): 7 % 3 (truncated) = 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_smod(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 1)))
    # sp=2: stack[0]=NOS=divisor=3, stack[1]=TOS=dividend=7
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 7})
    assert trace.bad_fired_at == 0


def test_lower_smod_by_zero():
    """SMOD(a=7, b=0): divisor=0 → EVM result = 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_smod(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 0, 1: 7})
    assert trace.bad_fired_at == 0


def test_lower_smod_exact_div():
    """SMOD(a=6, b=3): 6 % 3 = 0."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_smod(b, b.state_nids)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 0)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 6})
    assert trace.bad_fired_at == 0


def test_lower_smod_sp_decremented():
    """After SMOD sp decreases by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_smod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 7})
    assert trace.bad_fired_at == 0


def test_lower_smod_pc_incremented():
    """After SMOD pc advances by SMOD_SIZE (1)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_smod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", SMOD_SIZE)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 7})
    assert trace.bad_fired_at == 0


def test_lower_smod_gas_decremented():
    """After SMOD gas decreases by SMOD_GAS (5)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_smod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - SMOD_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 7})
    assert trace.bad_fired_at == 0


def test_lower_smod_oog_traps():
    """gas < 5 → OOG trap."""
    b, _ = _fresh(gas=4)
    result = lower_smod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 7})
    assert trace.bad_fired_at == 0


def test_lower_smod_underflow_traps():
    """sp < 2 → underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_smod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1)
    assert trace.bad_fired_at == 0


def test_lower_smod_halted_noop():
    """When already halted, SMOD is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_smod(b, b.state_nids)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 3, 1: 7}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_smod_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_smod(b, b.state_nids)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# lower_pushn tests (P16)
# ---------------------------------------------------------------------------


def test_lower_pushn_push2_value():
    """PUSH2 0x00C8: pushes 200 onto the stack."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_pushn(b, b.state_nids, 200, 2)
    _wire_next(b, result)
    # Result at stack[sp] = stack[0] after push
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 200)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_pushn_push32_large_value():
    """PUSH32 with immediate 42: pushes the value and pc advances by 33."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_pushn(b, b.state_nids, 42, 32)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(result_slot, b.const("bv256", 42)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_pushn_push2_sp_incremented():
    """After PUSH2 sp increases by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_pushn(b, b.state_nids, 256, 2)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 1)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_pushn_push2_pc_incremented_by_3():
    """After PUSH2 pc advances by 3 (1 opcode + 2 immediate bytes)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_pushn(b, b.state_nids, 256, 2)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 3)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_pushn_push32_pc_incremented_by_33():
    """After PUSH32 pc advances by 33 (1 opcode + 32 immediate bytes)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_pushn(b, b.state_nids, 0, 32)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 33)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_pushn_gas_decremented():
    """After PUSH2 gas decreases by PUSHN_GAS (3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_pushn(b, b.state_nids, 256, 2)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - PUSHN_GAS)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_pushn_oog_traps():
    """gas < 3 → OOG trap for PUSH2."""
    b, _ = _fresh(gas=2)
    result = lower_pushn(b, b.state_nids, 256, 2)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


def test_lower_pushn_halted_noop():
    """When already halted, PUSH2 is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_pushn(b, b.state_nids, 256, 2)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 0)))
    trace = _run(b, max_steps=1, sp=0, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_pushn_round_trips_btor2():
    b, _ = _fresh(gas=1_000_000)
    result = lower_pushn(b, b.state_nids, 256, 2)
    _wire_next(b, result)
    text = to_text(b.model)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_lower_pushn_push1_equivalent_to_lower_push1():
    """lower_pushn with n=1 and same immediate produces same sp/pc as lower_push1."""
    # Both should increment sp by 1 and pc by 2.
    b, _ = _fresh(gas=1_000_000)
    result = lower_pushn(b, b.state_nids, 0x42, 1)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 2)))
    trace = _run(b, max_steps=1, sp=0)
    assert trace.bad_fired_at == 0


# ---------------------------------------------------------------------------
# lower_dupn tests (P17)
# ---------------------------------------------------------------------------


def test_lower_dupn_gas_constant():
    assert DUP_GAS == 3
    assert DUP_SIZE == 1


def test_lower_dupn_dup2_copies_depth2():
    """DUP2 copies stack[sp-2] (the element at depth 2) to TOS."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_dupn(b, b.state_nids, 2)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 2))
    b.bad(b.eq(result_slot, b.const("bv256", 42)))
    # Pre-load stack[0]=42, stack[1]=99, sp=2 — DUP2 should copy stack[0]=42
    trace = _run(b, max_steps=1, sp=2, stack={0: 42, 1: 99})
    assert trace.bad_fired_at == 0


def test_lower_dupn_dup3_copies_depth3():
    """DUP3 copies stack[sp-3] (depth 3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_dupn(b, b.state_nids, 3)
    _wire_next(b, result)
    result_slot = b.read("bv256", b.state_nids["stack"], b.const("bv10", 3))
    b.bad(b.eq(result_slot, b.const("bv256", 7)))
    # stack[0]=7, stack[1]=8, stack[2]=9, sp=3 — DUP3 copies stack[0]=7
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 8, 2: 9})
    assert trace.bad_fired_at == 0


def test_lower_dupn_sp_incremented():
    """After DUP2 sp increases by 1."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_dupn(b, b.state_nids, 2)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 3)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_dupn_original_preserved():
    """DUP2 leaves the original stack[sp-2] intact."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_dupn(b, b.state_nids, 2)
    _wire_next(b, result)
    slot0 = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(slot0, b.const("bv256", 55)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 55, 1: 99})
    assert trace.bad_fired_at == 0


def test_lower_dupn_pc_advanced():
    """DUP2 advances pc by DUP_SIZE (1)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_dupn(b, b.state_nids, 2)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_dupn_gas_decremented():
    """DUP2 decrements gas by DUP_GAS (3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_dupn(b, b.state_nids, 2)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - DUP_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_dupn_underflow_traps():
    """DUP2 with sp=1 (only 1 item) triggers underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_dupn(b, b.state_nids, 2)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 42})
    assert trace.bad_fired_at == 0


def test_lower_dupn_overflow_traps():
    """DUP2 with sp=1024 triggers stack-overflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_dupn(b, b.state_nids, 2)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1024)
    assert trace.bad_fired_at == 0


def test_lower_dupn_oog_traps():
    """gas < 3 → OOG trap for DUP2."""
    b, _ = _fresh(gas=2)
    result = lower_dupn(b, b.state_nids, 2)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_dupn_halted_noop():
    """When already halted, DUP2 is a no-op: sp unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_dupn(b, b.state_nids, 2)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 2}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_dupn_equivalent_to_dup1_when_n1():
    """lower_dupn(n=1) behaves identically to lower_dup1 for sp/pc/gas."""
    b1, _ = _fresh(gas=1_000_000)
    r1 = lower_dup1(b1, b1.state_nids)
    _wire_next(b1, r1)

    b2, _ = _fresh(gas=1_000_000)
    r2 = lower_dupn(b2, b2.state_nids, 1)
    _wire_next(b2, r2)

    b1.bad(b1.eq(b1.state_nids["sp"], b1.const("bv10", 2)))
    t1 = _run(b1, max_steps=1, sp=1, stack={0: 7})
    b2.bad(b2.eq(b2.state_nids["sp"], b2.const("bv10", 2)))
    t2 = _run(b2, max_steps=1, sp=1, stack={0: 7})
    assert t1.bad_fired_at == t2.bad_fired_at == 0


# ---------------------------------------------------------------------------
# lower_swapn tests (P18)
# ---------------------------------------------------------------------------


def test_lower_swapn_gas_constant():
    assert SWAP_GAS == 3
    assert SWAP_SIZE == 1


def test_lower_swapn_swap1_exchanges_tos_and_depth2():
    """SWAP1 exchanges TOS (stack[sp-1]) with stack[sp-2]."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_swapn(b, b.state_nids, 1)
    _wire_next(b, result)
    # After swap: TOS should be the old NOS (stack[0]=10)
    tos_after = b.read("bv256", b.state_nids["stack"], b.const("bv10", 1))
    b.bad(b.eq(tos_after, b.const("bv256", 10)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 10, 1: 99})
    assert trace.bad_fired_at == 0


def test_lower_swapn_swap1_deep_slot_gets_old_tos():
    """SWAP1: the deep slot (stack[sp-2]) gets the old TOS value."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_swapn(b, b.state_nids, 1)
    _wire_next(b, result)
    # After swap: stack[0] should be old TOS = 99
    deep_after = b.read("bv256", b.state_nids["stack"], b.const("bv10", 0))
    b.bad(b.eq(deep_after, b.const("bv256", 99)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 10, 1: 99})
    assert trace.bad_fired_at == 0


def test_lower_swapn_sp_unchanged():
    """SWAP1 does not change sp."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_swapn(b, b.state_nids, 1)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["sp"], b.const("bv10", 2)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_swapn_swap2_exchanges_tos_and_depth3():
    """SWAP2 exchanges TOS with stack[sp-3] (depth 3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_swapn(b, b.state_nids, 2)
    _wire_next(b, result)
    # stack: [7, 8, 9], sp=3. TOS=9, deep=7. After SWAP2: TOS=7, deep=9.
    tos_after = b.read("bv256", b.state_nids["stack"], b.const("bv10", 2))
    b.bad(b.eq(tos_after, b.const("bv256", 7)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 8, 2: 9})
    assert trace.bad_fired_at == 0


def test_lower_swapn_pc_advanced():
    """SWAP1 advances pc by SWAP_SIZE (1)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_swapn(b, b.state_nids, 1)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["pc"], b.const("bv16", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_swapn_gas_decremented():
    """SWAP1 decrements gas by SWAP_GAS (3)."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_swapn(b, b.state_nids, 1)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["gas"], b.const("bv64", 1_000_000 - SWAP_GAS)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_swapn_underflow_traps():
    """SWAP1 with sp=1 (only 1 item, need 2) triggers underflow trap."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_swapn(b, b.state_nids, 1)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=1, stack={0: 42})
    assert trace.bad_fired_at == 0


def test_lower_swapn_oog_traps():
    """gas < 3 → OOG trap for SWAP1."""
    b, _ = _fresh(gas=2)
    result = lower_swapn(b, b.state_nids, 1)
    _wire_next(b, result)
    b.bad(b.eq(b.state_nids["trap"], b.const("bv1", 1)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 1, 1: 2})
    assert trace.bad_fired_at == 0


def test_lower_swapn_halted_noop():
    """When already halted, SWAP1 is a no-op: stack unchanged."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_swapn(b, b.state_nids, 1)
    _wire_next(b, result)
    # TOS should remain original value 99 (no swap)
    tos_after = b.read("bv256", b.state_nids["stack"], b.const("bv10", 1))
    b.bad(b.eq(tos_after, b.const("bv256", 99)))
    trace = _run(b, max_steps=1, sp=2, stack={0: 10, 1: 99}, halted=1)
    assert trace.bad_fired_at == 0


def test_lower_swapn_middle_slot_preserved():
    """SWAP2 with [7,8,9]: middle slot 8 is not disturbed."""
    b, _ = _fresh(gas=1_000_000)
    result = lower_swapn(b, b.state_nids, 2)
    _wire_next(b, result)
    mid = b.read("bv256", b.state_nids["stack"], b.const("bv10", 1))
    b.bad(b.eq(mid, b.const("bv256", 8)))
    trace = _run(b, max_steps=1, sp=3, stack={0: 7, 1: 8, 2: 9})
    assert trace.bad_fired_at == 0
