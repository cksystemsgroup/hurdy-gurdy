"""Tests for the evm-btor2 full translator (P4) — translate_bytecode.

Each test exercises the complete translation pipeline:
  header → machine → context → dispatch → binding → bad

The reasoning interpreter verifies concrete semantics end-to-end.
"""

from __future__ import annotations

import pathlib

from gurdy.core.annotation.sidecar import AnnotationSidecar
from gurdy.core.pair import CompiledArtifact, Layer
from gurdy.pairs.evm_btor2.btor2.parser import from_text
from gurdy.pairs.evm_btor2.reasoning_interp import (
    Btor2ReasoningBinding,
    Btor2ReasoningInterpreter,
)
from gurdy.pairs.evm_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BytecodeRef,
    EvmBtor2Spec,
    GasLimitPin,
    ReachKind,
    ReachProperty,
)
from gurdy.pairs.evm_btor2.translation.translator import translate_bytecode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec(hex_bytecode: str, reach_kind: str = "stop", **prop_kw) -> EvmBtor2Spec:
    prop_kw.setdefault("kind", ReachKind(reach_kind))
    return EvmBtor2Spec(
        bytecode=BytecodeRef(hex=hex_bytecode),
        scope=AnalysisScope(),
        assumptions=(GasLimitPin(gas=1_000_000),),
        property=ReachProperty(**prop_kw),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )


def _run(btor2_text: str, max_steps: int = 10, **binding_kw):
    body = btor2_text.encode("utf-8")
    artifact = CompiledArtifact(
        pair="evm-btor2",
        layers={"all": Layer(name="all", body=body, content_hash="x")},
        annotation=AnnotationSidecar(),
        flattened=body,
        schema_version="1.0.0",
        spec_hash="x",
    )
    binding = Btor2ReasoningBinding(state_init_by_symbol=binding_kw)
    return Btor2ReasoningInterpreter().run(artifact, binding, max_steps=max_steps)


# ---------------------------------------------------------------------------
# Round-trip: model parses cleanly
# ---------------------------------------------------------------------------


def test_translate_stop_round_trips():
    """Bytecode 0x00 (STOP) → valid BTOR2."""
    spec = _spec("00")
    text = translate_bytecode(bytes.fromhex("00"), spec)
    result = from_text(text)
    assert not result.has_errors(), result.diagnostics


def test_translate_push1_stop_round_trips():
    """PUSH1 0x42 / STOP → valid BTOR2."""
    spec = _spec("604200")
    text = translate_bytecode(bytes.fromhex("604200"), spec)
    assert not from_text(text).has_errors()


def test_translate_seed_0001_round_trips():
    """Seed 0001 bytecode (PUSH1/PUSH1/SSTORE/STOP) → valid BTOR2."""
    bytecode = bytes.fromhex("604260005500")
    spec = _spec("604260005500", "storage_eq", kind=ReachKind.STORAGE_EQ, slot=0, value=66)
    text = translate_bytecode(bytecode, spec)
    assert not from_text(text).has_errors()


def test_translate_add_round_trips():
    """ADD bytecode → valid BTOR2."""
    spec = _spec("01 00".replace(" ", ""), "stop")
    text = translate_bytecode(bytes.fromhex("0100"), spec)
    assert not from_text(text).has_errors()


# ---------------------------------------------------------------------------
# Concrete semantics: STOP sets halted
# ---------------------------------------------------------------------------


def test_stop_sets_halted():
    """0x00 (STOP): after 1 step, bad(halted AND NOT trap) fires."""
    spec = _spec("00", "stop")
    text = translate_bytecode(bytes.fromhex("00"), spec)
    trace = _run(text, max_steps=2)
    assert trace.bad_fired_at == 0


def test_stop_does_not_set_trap():
    """STOP is a clean halt; bad(halted AND trap) must NOT fire."""
    spec = _spec("00", "revert")
    text = translate_bytecode(bytes.fromhex("00"), spec)
    trace = _run(text, max_steps=2)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# Concrete semantics: PUSH1 + STOP
# ---------------------------------------------------------------------------


def test_push1_stop_bad_fires():
    """PUSH1 0x42 / STOP — bad(stop) fires at step 1."""
    spec = _spec("604200", "stop")
    text = translate_bytecode(bytes.fromhex("604200"), spec)
    trace = _run(text, max_steps=3)
    assert trace.bad_fired_at == 1


# ---------------------------------------------------------------------------
# Concrete semantics: seed 0001 — PUSH1 0x42 / PUSH1 0x00 / SSTORE / STOP
#
# Execution trace (POST-state after each step, bad checked on POST state):
#   Step 0 (pc=0): PUSH1 0x42 → sp=1, stack[0]=0x42, pc=2
#   Step 1 (pc=2): PUSH1 0x00 → sp=2, stack[1]=0x00, pc=4
#   Step 2 (pc=4): SSTORE slot=0 value=0x42 → sto[0]=0x42, sp=0, pc=5
#   Step 3 (pc=5): STOP → halted=1, trap=0
#   Bad = halted AND NOT trap AND sto[0]==0x42 → fires at step 3
# ---------------------------------------------------------------------------


def test_seed_0001_bad_fires_at_step_3():
    """Full seed 0001: storage_eq bad fires at step 3 (after STOP)."""
    bytecode = bytes.fromhex("604260005500")
    spec = _spec("604260005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=66)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=6)
    assert trace.bad_fired_at == 3


def test_seed_0001_bad_not_before_step_3():
    """Bad must not fire before step 3 (storage not written until SSTORE)."""
    bytecode = bytes.fromhex("604260005500")
    spec = _spec("604260005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=66)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=3)
    assert trace.bad_fired_at is None


def test_seed_0001_wrong_value_never_fires():
    """storage_eq with wrong value (value=99) must never fire."""
    bytecode = bytes.fromhex("604260005500")
    spec = _spec("604260005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=99)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=6)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# Out-of-scope lowering: unknown opcode traps
# ---------------------------------------------------------------------------


def test_unknown_opcode_traps():
    """0xFF (SELFDESTRUCT, out-of-scope) → trap=1 at step 0."""
    spec = _spec("ff", "revert")
    text = translate_bytecode(bytes.fromhex("ff"), spec)
    trace = _run(text, max_steps=2)
    assert trace.bad_fired_at == 0


# ---------------------------------------------------------------------------
# Seed 0009: div-sstore-on-taken (P12)
# ---------------------------------------------------------------------------
# Bytecode: PUSH1 0x0a / PUSH1 0x02 / PUSH1 0x00 / CALLDATALOAD / DIV /
#           GT / PUSH1 0x0d / JUMPI / STOP /
#           JUMPDEST / PUSH1 0x42 / PUSH1 0x00 / SSTORE / STOP
#
# Pattern: if (calldata[31] / 2 > 10) → SSTORE(0, 0x42)
# Witness: calldata[31]=22 → 22/2=11 > 10 → taken path, witness_step=12.
# ---------------------------------------------------------------------------


def test_translate_seed_0009_round_trips():
    """Full seed 0009 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex("600a60026000350411600d57005b604260005500")
    spec = _spec("600a60026000350411600d57005b604260005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=66)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0009_bad_fires_at_step_12():
    """Full seed 0009: storage_eq bad fires at step 12 (after STOP on taken path)."""
    bytecode = bytes.fromhex("600a60026000350411600d57005b604260005500")
    spec = _spec("600a60026000350411600d57005b604260005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=66)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=15, calldata={31: 22})
    assert trace.bad_fired_at == 12


def test_seed_0009_bad_not_before_step_12():
    """Bad must not fire before step 12 (storage not written until SSTORE)."""
    bytecode = bytes.fromhex("600a60026000350411600d57005b604260005500")
    spec = _spec("600a60026000350411600d57005b604260005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=66)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12, calldata={31: 22})
    assert trace.bad_fired_at is None


def test_seed_0009_zero_calldata_never_fires():
    """With calldata=0: 0/2=0, not > 10, JUMPI falls through → UNSAT."""
    bytecode = bytes.fromhex("600a60026000350411600d57005b604260005500")
    spec = _spec("600a60026000350411600d57005b604260005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=66)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=15)
    assert trace.bad_fired_at is None
