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


# ---------------------------------------------------------------------------
# INVALID opcode (0xFE) direct routing test
# ---------------------------------------------------------------------------


def test_invalid_opcode_sets_trap():
    """0xFE (INVALID): trap=1 fires at step 0 (revert property)."""
    spec = _spec("fe", "revert")
    text = translate_bytecode(bytes.fromhex("fe"), spec)
    trace = _run(text, max_steps=2)
    assert trace.bad_fired_at == 0


# ---------------------------------------------------------------------------
# Seed 0018: invalid-trap (P21)
# ---------------------------------------------------------------------------
# Bytecode (14 bytes): PUSH1 0x00 / CALLDATALOAD / PUSH1 0x07 / JUMPI /
#                      INVALID / JUMPDEST / PUSH1 0x01 / PUSH1 0x00 /
#                      SSTORE / STOP
#
# SAT path (calldata[31]=1):
#   Step 0 (pc=0):  PUSH1 0x00 → sp=1, stack[0]=0
#   Step 1 (pc=2):  CALLDATALOAD → stack[0]=1
#   Step 2 (pc=3):  PUSH1 0x07 → sp=2, stack[1]=7
#   Step 3 (pc=5):  JUMPI(dest=7, cond=1) → sp=0, pc=7
#   Step 4 (pc=7):  JUMPDEST → pc=8
#   Step 5 (pc=8):  PUSH1 0x01 → sp=1, stack[0]=1
#   Step 6 (pc=10): PUSH1 0x00 → sp=2, stack[1]=0
#   Step 7 (pc=12): SSTORE(slot=0, val=1) → sto[0]=1
#   Step 8 (pc=13): STOP → halted=1, trap=0
#   Bad = halted AND NOT trap AND sto[0]==1 → fires at step 8
#
# UNSAT path (calldata=0):
#   JUMPI falls through to pc6 (INVALID) → trap=1 → bad requires ¬trap → UNSAT.
# ---------------------------------------------------------------------------


def test_translate_seed_0018_round_trips():
    """Full seed 0018 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex("600035600757fe5b600160005500")
    spec = _spec("600035600757fe5b600160005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0018_bad_fires_at_step_8():
    """Full seed 0018: storage_eq bad fires at step 8 (after STOP on SAT path)."""
    bytecode = bytes.fromhex("600035600757fe5b600160005500")
    spec = _spec("600035600757fe5b600160005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12, calldata={31: 1})
    assert trace.bad_fired_at == 8


def test_seed_0018_bad_not_before_step_8():
    """Bad must not fire before step 8 on the SAT path."""
    bytecode = bytes.fromhex("600035600757fe5b600160005500")
    spec = _spec("600035600757fe5b600160005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=8, calldata={31: 1})
    assert trace.bad_fired_at is None


def test_seed_0018_zero_calldata_never_fires():
    """calldata=0 → INVALID traps → bad (storage_eq) never fires."""
    bytecode = bytes.fromhex("600035600757fe5b600160005500")
    spec = _spec("600035600757fe5b600160005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# REVERT opcode (0xFD) direct routing test
# ---------------------------------------------------------------------------


def test_revert_opcode_sets_trap():
    """0xFD (REVERT): trap=1 fires at step 0 (revert property).

    Bytecode: PUSH1 0x00 / PUSH1 0x00 / REVERT
    Stack has offset=0, length=0 before REVERT; trap=1 after.
    """
    spec = _spec("600060 00fd".replace(" ", ""), "revert")
    text = translate_bytecode(bytes.fromhex("60006000fd"), spec)
    trace = _run(text, max_steps=3)
    assert trace.bad_fired_at == 2


# ---------------------------------------------------------------------------
# Seed 0019: revert-trap (P22)
# ---------------------------------------------------------------------------
# Bytecode (18 bytes): PUSH1 0x00 / CALLDATALOAD / PUSH1 0x0b / JUMPI /
#                      PUSH1 0x00 / PUSH1 0x00 / REVERT /
#                      JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP
#
# SAT path (calldata[31]=1):
#   Step 0 (pc=0):  PUSH1 0x00 → sp=1, stack[0]=0
#   Step 1 (pc=2):  CALLDATALOAD → stack[0]=1
#   Step 2 (pc=3):  PUSH1 0x0b → sp=2, stack[1]=11
#   Step 3 (pc=5):  JUMPI(dest=11, cond=1) → sp=0, pc=11
#   Step 4 (pc=11): JUMPDEST → pc=12
#   Step 5 (pc=12): PUSH1 0x01 → sp=1, stack[0]=1
#   Step 6 (pc=14): PUSH1 0x00 → sp=2, stack[1]=0
#   Step 7 (pc=16): SSTORE(slot=0, val=1) → sto[0]=1
#   Step 8 (pc=17): STOP → halted=1, trap=0
#   Bad = halted AND NOT trap AND sto[0]==1 → fires at step 8
#
# REVERT path (calldata=0):
#   JUMPI falls through to pc6; PUSH1 0/PUSH1 0/REVERT → trap=1 → bad never fires.
# ---------------------------------------------------------------------------

_SEED_0019_HEX = "600035600b5760006000fd5b600160005500"


def test_translate_seed_0019_round_trips():
    """Full seed 0019 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0019_HEX)
    spec = _spec(_SEED_0019_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0019_bad_fires_at_step_8():
    """Full seed 0019: storage_eq bad fires at step 8 (after STOP on SAT path)."""
    bytecode = bytes.fromhex(_SEED_0019_HEX)
    spec = _spec(_SEED_0019_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12, calldata={31: 1})
    assert trace.bad_fired_at == 8


def test_seed_0019_bad_not_before_step_8():
    """Bad must not fire before step 8 on the SAT path."""
    bytecode = bytes.fromhex(_SEED_0019_HEX)
    spec = _spec(_SEED_0019_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=8, calldata={31: 1})
    assert trace.bad_fired_at is None


def test_seed_0019_zero_calldata_never_fires():
    """calldata=0 → REVERT traps → bad (storage_eq) never fires."""
    bytecode = bytes.fromhex(_SEED_0019_HEX)
    spec = _spec(_SEED_0019_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# RETURNDATASIZE opcode (0x3D) direct routing test
# ---------------------------------------------------------------------------


def test_returndatasize_opcode_pushes_zero_at_init():
    """0x3D (RETURNDATASIZE): pushes returndatasize=0 at init; ISZERO is 1; STOP halts.

    Bytecode: RETURNDATASIZE / ISZERO / STOP
    At init, returndatasize=0. RETURNDATASIZE pushes 0. ISZERO(0)=1. STOP → halted.
    Bad (stop property) fires at step 2.
    """
    spec = _spec("3d1500", "stop")
    text = translate_bytecode(bytes.fromhex("3d1500"), spec)
    trace = _run(text, max_steps=4)
    assert trace.bad_fired_at == 2


def test_returndatasize_opcode_routes_correctly():
    """0x3D routes to lower_returndatasize: sp increments from 0 to 1, then STOP."""
    spec = _spec("3d50 00".replace(" ", ""), "stop")
    text = translate_bytecode(bytes.fromhex("3d5000"), spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# RETURNDATACOPY opcode (0x3E) direct routing test
# ---------------------------------------------------------------------------


def test_returndatacopy_opcode_routes_correctly():
    """0x3E routes to lower_returndatacopy: PUSH0/PUSH0/PUSH0/RETURNDATACOPY is valid BTOR2."""
    # PUSH0 / PUSH0 / PUSH0 / RETURNDATACOPY (dest=0, offset=0, length=0 → no oob; sp=0 after)
    # Then STOP.
    spec = _spec("5f5f5f3e00", "stop")
    text = translate_bytecode(bytes.fromhex("5f5f5f3e00"), spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# Seed 0020: returndatasize-baseline (P23)
# ---------------------------------------------------------------------------
# Bytecode (17 bytes): RETURNDATASIZE / ISZERO / PUSH1 0x0a / JUMPI /
#                      PUSH1 0x01 / PUSH1 0x00 / SSTORE / JUMPDEST /
#                      PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP
#
# At init returndatasize=0; ISZERO(0)=1 → JUMPI always takes the branch.
#
# SAT path (unconditional — returndatasize=0 always at init):
#   Step 0 (pc=0):  RETURNDATASIZE → sp=1, stack[0]=0
#   Step 1 (pc=1):  ISZERO → stack[0]=(0==0)=1, sp=1
#   Step 2 (pc=2):  PUSH1 0x0a → sp=2, stack[1]=10
#   Step 3 (pc=4):  JUMPI(dest=10, cond=1) → sp=0, pc=10
#   Step 4 (pc=10): JUMPDEST → pc=11
#   Step 5 (pc=11): PUSH1 0x01 → sp=1, stack[0]=1
#   Step 6 (pc=13): PUSH1 0x00 → sp=2, stack[1]=0
#   Step 7 (pc=15): SSTORE(slot=0, val=1) → sto[0]=1
#   Step 8 (pc=16): STOP → halted=1, trap=0
#   Bad (storage_eq slot=0 val=1) fires at step 8.
# ---------------------------------------------------------------------------

_SEED_0020_HEX = "3d15600a5760016000555b6001600055 00".replace(" ", "")


def test_translate_seed_0020_round_trips():
    """Full seed 0020 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0020_HEX)
    spec = _spec(_SEED_0020_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0020_bad_fires_at_step_8():
    """Full seed 0020: storage_eq bad fires at step 8 (RETURNDATASIZE=0 → always taken)."""
    bytecode = bytes.fromhex(_SEED_0020_HEX)
    spec = _spec(_SEED_0020_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12)
    assert trace.bad_fired_at == 8


def test_seed_0020_bad_not_before_step_8():
    """Bad must not fire before step 8 (SSTORE + STOP complete at step 8)."""
    bytecode = bytes.fromhex(_SEED_0020_HEX)
    spec = _spec(_SEED_0020_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=8)
    assert trace.bad_fired_at is None
