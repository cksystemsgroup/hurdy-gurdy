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
    CallerPin,
    CallvaluePin,
    EvmBtor2Spec,
    GasLimitPin,
    OriginPin,
    ReachKind,
    ReachProperty,
    StoragePin,
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


# ---------------------------------------------------------------------------
# P24 routing: ORIGIN / CALLER / CALLVALUE / SELFBALANCE / BALANCE
# ---------------------------------------------------------------------------


def test_translate_origin_round_trips():
    """ORIGIN (0x32) STOP → valid BTOR2."""
    spec = _spec("3200")
    assert not from_text(translate_bytecode(bytes.fromhex("3200"), spec)).has_errors()


def test_translate_caller_round_trips():
    """CALLER (0x33) STOP → valid BTOR2."""
    spec = _spec("3300")
    assert not from_text(translate_bytecode(bytes.fromhex("3300"), spec)).has_errors()


def test_translate_callvalue_round_trips():
    """CALLVALUE (0x34) STOP → valid BTOR2."""
    spec = _spec("3400")
    assert not from_text(translate_bytecode(bytes.fromhex("3400"), spec)).has_errors()


def test_translate_selfbalance_round_trips():
    """SELFBALANCE (0x47) STOP → valid BTOR2."""
    spec = _spec("4700")
    assert not from_text(translate_bytecode(bytes.fromhex("4700"), spec)).has_errors()


def test_translate_balance_round_trips():
    """PUSH1 0x00 / BALANCE (0x31) / STOP → valid BTOR2."""
    # Push address 0, query balance, then stop.
    spec = _spec("60003100")
    assert not from_text(translate_bytecode(bytes.fromhex("60003100"), spec)).has_errors()


def test_translate_callvalue_stop_fires_at_step_1():
    """CALLVALUE / STOP with STOP reachability: bad fires at step 1."""
    spec = _spec("3400", "stop")
    text = translate_bytecode(bytes.fromhex("3400"), spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


def test_translate_origin_stop_fires_at_step_1():
    """ORIGIN / STOP with STOP reachability: bad fires at step 1."""
    spec = _spec("3200", "stop")
    text = translate_bytecode(bytes.fromhex("3200"), spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


def test_translate_caller_with_pin_round_trips():
    """CallerPin constrains caller in BTOR2 output (model parses cleanly)."""
    bc = bytes.fromhex("3300")
    spec = EvmBtor2Spec(
        bytecode=BytecodeRef(hex="3300"),
        scope=AnalysisScope(),
        assumptions=(GasLimitPin(gas=1_000_000), CallerPin(address=0xABCD)),
        property=ReachProperty(kind=ReachKind.STOP),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    assert not from_text(translate_bytecode(bc, spec)).has_errors()


def test_translate_callvalue_with_pin_round_trips():
    """CallvaluePin constrains callvalue in BTOR2 output (model parses cleanly)."""
    bc = bytes.fromhex("3400")
    spec = EvmBtor2Spec(
        bytecode=BytecodeRef(hex="3400"),
        scope=AnalysisScope(),
        assumptions=(GasLimitPin(gas=1_000_000), CallvaluePin(value=42)),
        property=ReachProperty(kind=ReachKind.STOP),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    assert not from_text(translate_bytecode(bc, spec)).has_errors()


# ---------------------------------------------------------------------------
# Seed 0021: callvalue-gated SSTORE (P24)
# ---------------------------------------------------------------------------
# Bytecode (14 bytes):
#   CALLVALUE ISZERO ISZERO PUSH1 0x07 JUMPI STOP JUMPDEST PUSH1 0x01 PUSH1 0x00 SSTORE STOP
#
# if callvalue != 0: jump to 0x07 (JUMPDEST), SSTORE(0, 1), STOP
# if callvalue == 0: STOP (fall-through at pc=6)
#
# SAT path (callvalue = 1):
#   Step 0 (pc=0):  CALLVALUE → sp=1, stack[0]=1
#   Step 1 (pc=1):  ISZERO → stack[0]=0
#   Step 2 (pc=2):  ISZERO → stack[0]=1
#   Step 3 (pc=3):  PUSH1 0x07 → sp=2, stack[1]=7
#   Step 4 (pc=5):  JUMPI(dest=7, cond=1) → sp=0, pc=7
#   Step 5 (pc=7):  JUMPDEST → pc=8
#   Step 6 (pc=8):  PUSH1 0x01 → sp=1, stack[0]=1
#   Step 7 (pc=10): PUSH1 0x00 → sp=2, stack[1]=0
#   Step 8 (pc=12): SSTORE(slot=0, val=1) → sto[0]=1
#   Step 9 (pc=13): STOP → halted=1; bad (storage_eq slot=0 val=1) fires.
#
# UNSAT path (callvalue = 0): JUMPI falls through → STOP at pc=6, no SSTORE.
# ---------------------------------------------------------------------------

_SEED_0021_HEX = "341515600757005b600160005500"


def test_translate_seed_0021_round_trips():
    """Full seed 0021 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0021_HEX)
    spec = _spec(_SEED_0021_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0021_bad_fires_at_step_9():
    """Seed 0021 with callvalue=1: storage_eq bad fires at step 9."""
    bytecode = bytes.fromhex(_SEED_0021_HEX)
    spec = _spec(_SEED_0021_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12, callvalue=1)
    assert trace.bad_fired_at == 9


def test_seed_0021_bad_not_before_step_9():
    """Bad must not fire before step 9."""
    bytecode = bytes.fromhex(_SEED_0021_HEX)
    spec = _spec(_SEED_0021_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=9, callvalue=1)
    assert trace.bad_fired_at is None


def test_seed_0021_zero_callvalue_never_fires():
    """callvalue=0 → JUMPI falls through → STOP, bad never fires."""
    bytecode = bytes.fromhex(_SEED_0021_HEX)
    spec = _spec(_SEED_0021_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12, callvalue=0)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# P25 routing: GAS (0x5A) / GASLIMIT (0x45)
# ---------------------------------------------------------------------------


def test_translate_gas_round_trips():
    """GAS (0x5A) STOP → valid BTOR2."""
    spec = _spec("5a00")
    assert not from_text(translate_bytecode(bytes.fromhex("5a00"), spec)).has_errors()


def test_translate_gaslimit_round_trips():
    """GASLIMIT (0x45) STOP → valid BTOR2."""
    spec = _spec("4500")
    assert not from_text(translate_bytecode(bytes.fromhex("4500"), spec)).has_errors()


def test_translate_gas_stop_fires_at_step_1():
    """GAS / STOP with STOP reachability: bad fires at step 1."""
    spec = _spec("5a00", "stop")
    text = translate_bytecode(bytes.fromhex("5a00"), spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


def test_translate_gaslimit_stop_fires_at_step_1():
    """GASLIMIT / STOP with STOP reachability: bad fires at step 1."""
    spec = _spec("4500", "stop")
    text = translate_bytecode(bytes.fromhex("4500"), spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


# ---------------------------------------------------------------------------
# Seed 0022: gas-gated SSTORE (P25)
# ---------------------------------------------------------------------------
# Bytecode (15 bytes):
#   PUSH1 0x00 / GAS / GT / PUSH1 0x08 / JUMPI / STOP /
#   JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP
#
# GAS pushes remaining gas (gas-2, always > 0 with 1M limit) to stack;
# GT(gas_remaining, 0) = 1 unconditionally → JUMPI always taken → SSTORE(0,1).
#
# SAT path (always with GasLimitPin=1_000_000):
#   Step 0 (pc=0):  PUSH1 0x00 → sp=1, stack[0]=0
#   Step 1 (pc=2):  GAS → sp=2, stack[1]=999995
#   Step 2 (pc=3):  GT(999995,0)=1 → sp=1, stack[0]=1
#   Step 3 (pc=4):  PUSH1 0x08 → sp=2, stack[1]=8
#   Step 4 (pc=6):  JUMPI(dest=8, cond=1) → sp=0, pc=8
#   Step 5 (pc=8):  JUMPDEST → pc=9
#   Step 6 (pc=9):  PUSH1 0x01 → sp=1, stack[0]=1
#   Step 7 (pc=11): PUSH1 0x00 → sp=2, stack[1]=0
#   Step 8 (pc=13): SSTORE(slot=0, val=1) → sto[0]=1
#   Step 9 (pc=14): STOP → halted=1; bad fires.
# ---------------------------------------------------------------------------

_SEED_0022_HEX = "60005a11600857005b600160005500"


def test_translate_seed_0022_round_trips():
    """Full seed 0022 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0022_HEX)
    spec = _spec(_SEED_0022_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0022_bad_fires_at_step_9():
    """Seed 0022 with GasLimitPin=1M: storage_eq bad fires at step 9."""
    bytecode = bytes.fromhex(_SEED_0022_HEX)
    spec = _spec(_SEED_0022_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12)
    assert trace.bad_fired_at == 9


def test_seed_0022_bad_not_before_step_9():
    """Bad must not fire before step 9."""
    bytecode = bytes.fromhex(_SEED_0022_HEX)
    spec = _spec(_SEED_0022_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=9)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# P26 routing: BLOCKHASH (0x40) / COINBASE (0x41) / TIMESTAMP (0x42) /
#              NUMBER (0x43) / PREVRANDAO (0x44) / BASEFEE (0x48)
# ---------------------------------------------------------------------------


def test_translate_blockhash_round_trips():
    """BLOCKHASH (0x40) STOP → valid BTOR2."""
    spec = _spec("4000")
    assert not from_text(translate_bytecode(bytes.fromhex("4000"), spec)).has_errors()


def test_translate_coinbase_round_trips():
    """COINBASE (0x41) STOP → valid BTOR2."""
    spec = _spec("4100")
    assert not from_text(translate_bytecode(bytes.fromhex("4100"), spec)).has_errors()


def test_translate_timestamp_round_trips():
    """TIMESTAMP (0x42) STOP → valid BTOR2."""
    spec = _spec("4200")
    assert not from_text(translate_bytecode(bytes.fromhex("4200"), spec)).has_errors()


def test_translate_number_round_trips():
    """NUMBER (0x43) STOP → valid BTOR2."""
    spec = _spec("4300")
    assert not from_text(translate_bytecode(bytes.fromhex("4300"), spec)).has_errors()


def test_translate_prevrandao_round_trips():
    """PREVRANDAO (0x44) STOP → valid BTOR2."""
    spec = _spec("4400")
    assert not from_text(translate_bytecode(bytes.fromhex("4400"), spec)).has_errors()


def test_translate_basefee_round_trips():
    """BASEFEE (0x48) STOP → valid BTOR2."""
    spec = _spec("4800")
    assert not from_text(translate_bytecode(bytes.fromhex("4800"), spec)).has_errors()


def test_translate_coinbase_stop_fires_at_step_1():
    """COINBASE / STOP with STOP reachability: bad fires at step 1."""
    spec = _spec("4100", "stop")
    text = translate_bytecode(bytes.fromhex("4100"), spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


def test_translate_number_stop_fires_at_step_1():
    """NUMBER / STOP with STOP reachability: bad fires at step 1."""
    spec = _spec("4300", "stop")
    text = translate_bytecode(bytes.fromhex("4300"), spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


# ---------------------------------------------------------------------------
# Seed 0023: number-gated SSTORE (P26)
# ---------------------------------------------------------------------------
# Bytecode (15 bytes):
#   PUSH1 0x00 / NUMBER / GT / PUSH1 0x08 / JUMPI / STOP /
#   JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP
#
# NUMBER is symbolic; GT(NUMBER, 0) = 1 when blocknumber > 0 → JUMPI taken
# → SSTORE(slot=0, val=1) → STOP → bad fires at step 9.
#
# SAT path (blocknumber > 0):
#   Step 0 (pc=0):  PUSH1 0x00 → sp=1, stack[0]=0
#   Step 1 (pc=2):  NUMBER → sp=2, stack[1]=blocknumber (symbolic, >0)
#   Step 2 (pc=3):  GT(blocknumber, 0) → sp=1, stack[0]=1
#   Step 3 (pc=4):  PUSH1 0x08 → sp=2, stack[1]=8
#   Step 4 (pc=6):  JUMPI(dest=8, cond=1) → sp=0, pc=8
#   Step 5 (pc=8):  JUMPDEST → pc=9
#   Step 6 (pc=9):  PUSH1 0x01 → sp=1, stack[0]=1
#   Step 7 (pc=11): PUSH1 0x00 → sp=2, stack[1]=0
#   Step 8 (pc=13): SSTORE(slot=0, val=1) → sto[0]=1
#   Step 9 (pc=14): STOP → halted=1; bad fires.
# ---------------------------------------------------------------------------

_SEED_0023_HEX = "60004311600857005b600160005500"


def test_translate_seed_0023_round_trips():
    """Full seed 0023 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0023_HEX)
    spec = _spec(_SEED_0023_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0023_bad_fires_at_step_9():
    """Seed 0023 with symbolic blocknumber > 0: storage_eq bad fires at step 9."""
    bytecode = bytes.fromhex(_SEED_0023_HEX)
    spec = _spec(_SEED_0023_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12, blocknumber=5)
    assert trace.bad_fired_at == 9


def test_seed_0023_bad_not_before_step_9():
    """Bad must not fire before step 9."""
    bytecode = bytes.fromhex(_SEED_0023_HEX)
    spec = _spec(_SEED_0023_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=9, blocknumber=5)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# P27 opcode routing round-trips
# ---------------------------------------------------------------------------


def test_translate_chainid_round_trips():
    """CHAINID (0x46) STOP → valid BTOR2."""
    spec = _spec("4600")
    assert not from_text(translate_bytecode(bytes.fromhex("4600"), spec)).has_errors()


def test_translate_codesize_round_trips():
    """CODESIZE (0x38) STOP → valid BTOR2."""
    spec = _spec("3800")
    assert not from_text(translate_bytecode(bytes.fromhex("3800"), spec)).has_errors()


def test_translate_codecopy_round_trips():
    """CODECOPY (0x39) STOP → valid BTOR2."""
    spec = _spec("3900")
    assert not from_text(translate_bytecode(bytes.fromhex("3900"), spec)).has_errors()


def test_translate_extcodesize_round_trips():
    """EXTCODESIZE (0x3B) STOP → valid BTOR2."""
    spec = _spec("3b00")
    assert not from_text(translate_bytecode(bytes.fromhex("3b00"), spec)).has_errors()


def test_translate_extcodecopy_round_trips():
    """EXTCODECOPY (0x3C) STOP → valid BTOR2."""
    spec = _spec("3c00")
    assert not from_text(translate_bytecode(bytes.fromhex("3c00"), spec)).has_errors()


def test_translate_chainid_stop_fires_at_step_1():
    """CHAINID / STOP with STOP reachability: bad fires at step 1."""
    spec = _spec("4600", "stop")
    text = translate_bytecode(bytes.fromhex("4600"), spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


def test_translate_codesize_stop_fires_at_step_1():
    """CODESIZE / STOP with STOP reachability: bad fires at step 1."""
    spec = _spec("3800", "stop")
    text = translate_bytecode(bytes.fromhex("3800"), spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


# ---------------------------------------------------------------------------
# Seed 0024: chainid-gated SSTORE (P27)
# ---------------------------------------------------------------------------
# Bytecode (15 bytes):
#   PUSH1 0x01 / CHAINID / EQ / PUSH1 0x08 / JUMPI / STOP /
#   JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP
#
# chainid is constrained to 1 by default → EQ(chainid, 1) = 1 → JUMPI taken
# → SSTORE(slot=0, val=1) → STOP → bad fires at step 9.
#
# SAT path (chainid == 1):
#   Step 0 (pc=0):  PUSH1 0x01 → sp=1, stack[0]=1
#   Step 1 (pc=2):  CHAINID → sp=2, stack[1]=1 (default chainid)
#   Step 2 (pc=3):  EQ(1, 1) → sp=1, stack[0]=1
#   Step 3 (pc=4):  PUSH1 0x08 → sp=2, stack[1]=8
#   Step 4 (pc=6):  JUMPI(dest=8, cond=1) → sp=0, pc=8
#   Step 5 (pc=8):  JUMPDEST → pc=9
#   Step 6 (pc=9):  PUSH1 0x01 → sp=1, stack[0]=1
#   Step 7 (pc=11): PUSH1 0x00 → sp=2, stack[1]=0
#   Step 8 (pc=13): SSTORE(slot=0, val=1) → sto[0]=1
#   Step 9 (pc=14): STOP → halted=1; bad fires.
# ---------------------------------------------------------------------------

_SEED_0024_HEX = "60014614600857005b600160005500"


def test_translate_seed_0024_round_trips():
    """Full seed 0024 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0024_HEX)
    spec = _spec(_SEED_0024_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0024_bad_fires_at_step_9():
    """Seed 0024 with chainid=1 (default): storage_eq bad fires at step 9."""
    bytecode = bytes.fromhex(_SEED_0024_HEX)
    spec = _spec(_SEED_0024_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12, chainid=1)
    assert trace.bad_fired_at == 9


def test_seed_0024_bad_not_before_step_9():
    """Bad must not fire before step 9."""
    bytecode = bytes.fromhex(_SEED_0024_HEX)
    spec = _spec(_SEED_0024_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=9, chainid=1)
    assert trace.bad_fired_at is None
