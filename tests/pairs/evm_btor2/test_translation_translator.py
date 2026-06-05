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


# ---------------------------------------------------------------------------
# P28 opcode routing round-trips
# ---------------------------------------------------------------------------


def test_translate_address_round_trips():
    """ADDRESS (0x30) STOP → valid BTOR2."""
    spec = _spec("3000")
    assert not from_text(translate_bytecode(bytes.fromhex("3000"), spec)).has_errors()


def test_translate_msize_round_trips():
    """MSIZE (0x59) STOP → valid BTOR2."""
    spec = _spec("5900")
    assert not from_text(translate_bytecode(bytes.fromhex("5900"), spec)).has_errors()


def test_translate_address_stop_fires_at_step_1():
    """ADDRESS / STOP with STOP reachability: bad fires at step 1."""
    spec = _spec("3000", "stop")
    text = translate_bytecode(bytes.fromhex("3000"), spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


def test_translate_msize_stop_fires_at_step_1():
    """MSIZE / STOP with STOP reachability: bad fires at step 1."""
    spec = _spec("5900", "stop")
    text = translate_bytecode(bytes.fromhex("5900"), spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


# ---------------------------------------------------------------------------
# Seed 0025: msize-gated SSTORE (P28)
# ---------------------------------------------------------------------------
# Bytecode (20 bytes):
#   PUSH1 0x00 / PUSH1 0x00 / MSTORE8 / MSIZE / PUSH1 0x00 / LT /
#   PUSH1 0x0d / JUMPI / STOP / JUMPDEST / PUSH1 0x01 / PUSH1 0x00 /
#   SSTORE / STOP
#
# mem_words expands to 1 after MSTORE8(offset=0, val=0).
# MSIZE pushes 32 (= 1 * 32). LT(0, 32) = 1 → JUMPI taken.
# → SSTORE(slot=0, val=1) → STOP → bad fires.
#
# SAT path:
#   Step 0 (pc=0):  PUSH1 0x00 → sp=1, stack[0]=0  (value for MSTORE8)
#   Step 1 (pc=2):  PUSH1 0x00 → sp=2, stack[1]=0  (offset for MSTORE8)
#   Step 2 (pc=4):  MSTORE8(offset=0, val=0) → mem[0]=0, mem_words=1, sp=0
#   Step 3 (pc=5):  MSIZE → sp=1, stack[0]=32
#   Step 4 (pc=6):  PUSH1 0x00 → sp=2, stack[1]=0
#   Step 5 (pc=8):  LT(0, 32) = 1 → sp=1, stack[0]=1
#   Step 6 (pc=9):  PUSH1 0x0d → sp=2, stack[1]=13
#   Step 7 (pc=11): JUMPI(dest=13, cond=1) → sp=0, pc=13
#   Step 8 (pc=13): JUMPDEST
#   Step 9 (pc=14): PUSH1 0x01 → sp=1, stack[0]=1
#   Step 10 (pc=16): PUSH1 0x00 → sp=2, stack[1]=0
#   Step 11 (pc=18): SSTORE(slot=0, val=1) → sto[0]=1
#   Step 12 (pc=19): STOP → halted=1; bad fires.
# ---------------------------------------------------------------------------

_SEED_0025_HEX = "600060005359600010600d57005b600160005500"


def test_translate_seed_0025_round_trips():
    """Full seed 0025 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0025_HEX)
    spec = _spec(_SEED_0025_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0025_bad_fires_at_step_12():
    """Seed 0025: msize-gated SSTORE; bad fires at step 12."""
    bytecode = bytes.fromhex(_SEED_0025_HEX)
    spec = _spec(_SEED_0025_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=15)
    assert trace.bad_fired_at == 12


def test_seed_0025_bad_not_before_step_12():
    """Bad must not fire before step 12."""
    bytecode = bytes.fromhex(_SEED_0025_HEX)
    spec = _spec(_SEED_0025_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# P29 opcode routing round-trips
# ---------------------------------------------------------------------------


def test_translate_pc_round_trips():
    """PC (0x58) STOP → valid BTOR2."""
    spec = _spec("5800")
    assert not from_text(translate_bytecode(bytes.fromhex("5800"), spec)).has_errors()


def test_translate_pc_stop_fires_at_step_1():
    """PC / STOP with STOP reachability: bad fires at step 1."""
    spec = _spec("5800", "stop")
    text = translate_bytecode(bytes.fromhex("5800"), spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


# ---------------------------------------------------------------------------
# Seed 0026: pc-gated SSTORE (P29)
# ---------------------------------------------------------------------------
# Bytecode (15 bytes):
#   PC / PUSH1 0x00 / EQ / PUSH1 0x08 / JUMPI / STOP /
#   JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP
#
# PC at bytecode offset 0 pushes 0. PUSH1 0x00 pushes 0 (TOS).
# EQ(0, 0) = 1 → condition is always true → JUMPI taken.
# → SSTORE(slot=0, val=1) → STOP → bad fires.
#
# SAT path:
#   Step 0 (pc=0):  PC → sp=1, stack[0]=0
#   Step 1 (pc=1):  PUSH1 0x00 → sp=2, stack[1]=0 (TOS)
#   Step 2 (pc=3):  EQ(0, 0) = 1 → sp=1, stack[0]=1
#   Step 3 (pc=4):  PUSH1 0x08 → sp=2, stack[1]=8 (TOS)
#   Step 4 (pc=6):  JUMPI(dest=8, cond=1) → sp=0, pc=8
#   Step 5 (pc=8):  JUMPDEST
#   Step 6 (pc=9):  PUSH1 0x01 → sp=1
#   Step 7 (pc=11): PUSH1 0x00 → sp=2
#   Step 8 (pc=13): SSTORE(slot=0, val=1) → sto[0]=1
#   Step 9 (pc=14): STOP → halted=1; bad fires.
# ---------------------------------------------------------------------------

_SEED_0026_HEX = "58600014600857005b600160005500"


def test_translate_seed_0026_round_trips():
    """Full seed 0026 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0026_HEX)
    spec = _spec(_SEED_0026_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0026_bad_fires_at_step_9():
    """Seed 0026 pc-gated SSTORE: bad fires at step 9."""
    bytecode = bytes.fromhex(_SEED_0026_HEX)
    spec = _spec(_SEED_0026_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=12)
    assert trace.bad_fired_at == 9


def test_seed_0026_bad_not_before_step_9():
    """Bad must not fire before step 9."""
    bytecode = bytes.fromhex(_SEED_0026_HEX)
    spec = _spec(_SEED_0026_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=9)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# P30: TLOAD (0x5C) / TSTORE (0x5D) round-trips and stop-fires
# ---------------------------------------------------------------------------


def test_translate_tload_round_trips():
    """TLOAD (0x5C) bytecode BTOR2 model parses without errors."""
    # PUSH1 0x00 / TLOAD / STOP  →  3 bytes
    bytecode = bytes.fromhex("60005c00")
    spec = _spec("60005c00", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_translate_tstore_round_trips():
    """TSTORE (0x5D) bytecode BTOR2 model parses without errors."""
    # PUSH1 0x2A / PUSH1 0x00 / TSTORE / STOP  →  5 bytes
    bytecode = bytes.fromhex("602a60005d00")
    spec = _spec("602a60005d00", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_translate_tload_stop_fires():
    """TLOAD followed by STOP: bad fires at step 2."""
    # PUSH1 0x00 / TLOAD / STOP — pops key=0, pushes transient_sto[0]=0, then halts
    bytecode = bytes.fromhex("60005c00")
    spec = _spec("60005c00", "stop")
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 2


def test_translate_tstore_stop_fires():
    """TSTORE followed by STOP: bad fires at step 3."""
    # PUSH1 0x2A / PUSH1 0x00 / TSTORE / STOP — pushes 42 and 0, TSTORE, halts
    bytecode = bytes.fromhex("602a60005d00")
    spec = _spec("602a60005d00", "stop")
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 3


# ---------------------------------------------------------------------------
# Seed 0027: TSTORE/TLOAD-gated SSTORE (P30)
# ---------------------------------------------------------------------------
# Bytecode (22 bytes):
#   PUSH1 0x01 / PUSH1 0x00 / TSTORE /   (write 1 to transient slot 0)
#   PUSH1 0x00 / TLOAD /                  (read back transient slot 0 → 1)
#   PUSH1 0x01 / EQ /                     (1 == 1 → 1)
#   PUSH1 0x13 / JUMPI /                  (jump to 0x13=19 if 1)
#   STOP /                                (not taken)
#   JUMPDEST /                            (offset 19)
#   PUSH1 0x01 / PUSH1 0x00 / SSTORE /   (sto[0] = 1)
#   STOP
#
# Hex: 6001 6000 5d 6000 5c 6001 14 6013 57 00 5b 6001 6000 55 00
# Layout:
#   00: PUSH1 0x01
#   02: PUSH1 0x00
#   04: TSTORE
#   05: PUSH1 0x00
#   07: TLOAD
#   08: PUSH1 0x01
#   0A: EQ
#   0B: PUSH1 0x13
#   0D: JUMPI
#   0E: STOP
#   0F: JUMPDEST
#   10: PUSH1 0x01
#   12: PUSH1 0x00
#   14: SSTORE
#   15: STOP
#
# Wait — let's recount. JUMPDEST at 0x0F=15, SSTORE path ends at 0x15=21 (STOP).
# JUMPI dest must be 0x0F=15. Let's redo:
#   0x00 PUSH1 0x01 → bytes [0x60, 0x01]
#   0x02 PUSH1 0x00 → bytes [0x60, 0x00]
#   0x04 TSTORE     → byte  [0x5D]
#   0x05 PUSH1 0x00 → bytes [0x60, 0x00]
#   0x07 TLOAD      → byte  [0x5C]
#   0x08 PUSH1 0x01 → bytes [0x60, 0x01]
#   0x0A EQ         → byte  [0x14]
#   0x0B PUSH1 0x0F → bytes [0x60, 0x0F]
#   0x0D JUMPI      → byte  [0x57]
#   0x0E STOP       → byte  [0x00]
#   0x0F JUMPDEST   → byte  [0x5B]
#   0x10 PUSH1 0x01 → bytes [0x60, 0x01]
#   0x12 PUSH1 0x00 → bytes [0x60, 0x00]
#   0x14 SSTORE     → byte  [0x55]
#   0x15 STOP       → byte  [0x00]
#
# hex: 600160005d60005c6001146060f575b600160005500 — need to fix dest byte
# JUMPI destination = 0x0F = 15 decimal
# hex: 6001 6000 5d 6000 5c 6001 14 600f 57 00 5b 6001 6000 55 00
# = "60016000" + "5d" + "6000" + "5c" + "6001" + "14" + "600f" + "57" + "00" + "5b" + "6001" + "6000" + "55" + "00"
#
# SAT path:
#   Step 0 (pc=0):  PUSH1 0x01 → sp=1, stack[0]=1
#   Step 1 (pc=2):  PUSH1 0x00 → sp=2, stack[1]=0 (TOS=key)
#   Step 2 (pc=4):  TSTORE(key=0, val=1) → transient_sto[0]=1, sp=0
#   Step 3 (pc=5):  PUSH1 0x00 → sp=1, stack[0]=0
#   Step 4 (pc=7):  TLOAD(key=0) → sp=1, stack[0]=1
#   Step 5 (pc=8):  PUSH1 0x01 → sp=2, stack[1]=1
#   Step 6 (pc=10): EQ(1,1)=1 → sp=1, stack[0]=1
#   Step 7 (pc=11): PUSH1 0x0F → sp=2, stack[1]=15
#   Step 8 (pc=13): JUMPI(dest=15, cond=1) → sp=0, pc=15
#   Step 9 (pc=15): JUMPDEST → sp=0
#   Step 10(pc=16): PUSH1 0x01 → sp=1
#   Step 11(pc=18): PUSH1 0x00 → sp=2
#   Step 12(pc=20): SSTORE(slot=0, val=1) → sto[0]=1
#   Step 13(pc=21): STOP → halted=1; bad fires.
# ---------------------------------------------------------------------------

_SEED_0027_HEX = "60016000" + "5d" + "6000" + "5c" + "6001" + "14" + "600f" + "57" + "00" + "5b" + "6001" + "6000" + "55" + "00"


def test_translate_seed_0027_round_trips():
    """Full seed 0027 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0027_HEX)
    spec = _spec(_SEED_0027_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0027_bad_fires_at_step_13():
    """Seed 0027 TSTORE/TLOAD-gated SSTORE: bad fires at step 13."""
    bytecode = bytes.fromhex(_SEED_0027_HEX)
    spec = _spec(_SEED_0027_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=16)
    assert trace.bad_fired_at == 13


def test_seed_0027_bad_not_before_step_13():
    """Bad must not fire before step 13."""
    bytecode = bytes.fromhex(_SEED_0027_HEX)
    spec = _spec(_SEED_0027_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=13)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# P31: POP (0x50), DUP2-DUP16 (0x81-0x8f), SWAP1-SWAP16 (0x90-0x9f)
# ---------------------------------------------------------------------------


def test_translate_pop_round_trips():
    """POP (0x50) bytecode BTOR2 model parses without errors."""
    # PUSH1 0x42 / POP / STOP
    bytecode = bytes.fromhex("604250" + "00")
    spec = _spec("604250" + "00")
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_translate_pop_stop_fires():
    """PUSH1 + POP + STOP: bad fires at step 2 (STOP)."""
    bytecode = bytes.fromhex("604250" + "00")
    spec = _spec("604250" + "00", "stop")
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 2


def test_translate_dup2_round_trips():
    """DUP2 (0x81) bytecode BTOR2 model parses without errors."""
    # PUSH1 0x00 / PUSH1 0x01 / DUP2 / STOP
    bytecode = bytes.fromhex("60006001" + "8100")
    spec = _spec("60006001" + "8100")
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_translate_dup2_stop_fires():
    """PUSH1 + PUSH1 + DUP2 + STOP: bad fires at step 3 (STOP)."""
    bytecode = bytes.fromhex("60006001" + "8100")
    spec = _spec("60006001" + "8100", "stop")
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 3


def test_translate_swap1_round_trips():
    """SWAP1 (0x90) bytecode BTOR2 model parses without errors."""
    # PUSH1 0x00 / PUSH1 0x01 / SWAP1 / STOP
    bytecode = bytes.fromhex("60006001" + "9000")
    spec = _spec("60006001" + "9000")
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_translate_swap1_stop_fires():
    """PUSH1 + PUSH1 + SWAP1 + STOP: bad fires at step 3 (STOP)."""
    bytecode = bytes.fromhex("60006001" + "9000")
    spec = _spec("60006001" + "9000", "stop")
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 3


# ---------------------------------------------------------------------------
# Seed 0028: SWAP1-corrects-push-order SSTORE (P31)
# ---------------------------------------------------------------------------
# Bytecode (7 bytes):
#   0x00 PUSH1 0x00    push slot 0 (will be buried by next push)
#   0x02 PUSH1 0x01    push value 1 (TOS); stack is [slot=0, value=1]
#   0x04 SWAP1         swap TOS with depth-2: TOS→slot=0, NOS→value=1
#   0x05 SSTORE        SSTORE(slot=TOS=0, val=NOS=1); sto[0]=1
#   0x06 STOP          bad fires
#
# SWAP1 exchanges the push-order error so SSTORE receives (slot=0, val=1).
# Without SWAP1, SSTORE would receive (slot=1, val=0) and the property
# (storage_eq slot=0 value=1) would never fire.
#
# SAT path:
#   Step 0 (pc=0):  PUSH1 0x00 → sp=1, stack[0]=0
#   Step 1 (pc=2):  PUSH1 0x01 → sp=2, stack[1]=1 (TOS)
#   Step 2 (pc=4):  SWAP1 → TOS=0 (slot), NOS=1 (value); sp=2
#   Step 3 (pc=5):  SSTORE(slot=0, val=1) → sto[0]=1; sp=0
#   Step 4 (pc=6):  STOP → halted=1; bad fires at step 4
# ---------------------------------------------------------------------------

_SEED_0028_HEX = "6000600190" + "5500"


def test_translate_seed_0028_round_trips():
    """Full seed 0028 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0028_HEX)
    spec = _spec(_SEED_0028_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0028_bad_fires_at_step_4():
    """Seed 0028 SWAP1-corrected SSTORE: bad fires at step 4."""
    bytecode = bytes.fromhex(_SEED_0028_HEX)
    spec = _spec(_SEED_0028_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=8)
    assert trace.bad_fired_at == 4


def test_seed_0028_bad_not_before_step_4():
    """Bad must not fire before step 4."""
    bytecode = bytes.fromhex(_SEED_0028_HEX)
    spec = _spec(_SEED_0028_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=4)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# P32: PUSH2-PUSH32 multi-byte push opcodes (0x61-0x7f)
# ---------------------------------------------------------------------------


def test_translate_push2_round_trips():
    """PUSH2 (0x61) bytecode BTOR2 model parses without errors."""
    # PUSH2 0x00 0x01 / STOP  — 4 bytes
    bytecode = bytes.fromhex("61000100")
    spec = _spec("61000100")
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_translate_push2_stop_fires():
    """PUSH2 + STOP: bad fires at step 1 (STOP at pc=3)."""
    # PUSH2 advances pc by 3 (opcode + 2 immediates); STOP at offset 3
    bytecode = bytes.fromhex("61000100")
    spec = _spec("61000100", "stop")
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


def test_translate_push32_round_trips():
    """PUSH32 (0x7f) bytecode BTOR2 model parses without errors."""
    # PUSH32 0x00..0x01 / STOP  — 34 bytes: opcode + 32 bytes + STOP
    imm = (1).to_bytes(32, "big").hex()
    hex_str = "7f" + imm + "00"
    bytecode = bytes.fromhex(hex_str)
    spec = _spec(hex_str)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_translate_push32_stop_fires():
    """PUSH32 + STOP: bad fires at step 1 (STOP at pc=33)."""
    # PUSH32 advances pc by 33 (opcode + 32 immediates); STOP at offset 33
    imm = (1).to_bytes(32, "big").hex()
    hex_str = "7f" + imm + "00"
    bytecode = bytes.fromhex(hex_str)
    spec = _spec(hex_str, "stop")
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


def test_translate_push2_pc_advances_by_3():
    """PUSH2 opcodes advance pc by 3 (opcode byte + 2 immediates).

    Verifies the translator correctly routes to lower_pushn with n=2,
    producing pc_next = pc + 3 rather than pc + 2 (as PUSH1 would).
    """
    # PUSH2 0x00 0x01 / PUSH1 0x00 / SSTORE / STOP
    # If pc advance were wrong (2 instead of 3), 0x01 byte would be
    # decoded as PUSH1 and subsequent bytes would shift, causing a trap
    # rather than SSTORE firing the bad property.
    bytecode = bytes.fromhex("61000160005500")
    spec = _spec("61000160005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=6)
    assert trace.bad_fired_at == 3


# ---------------------------------------------------------------------------
# Seed 0029: PUSH2-based value SSTORE (P32)
# ---------------------------------------------------------------------------
# Bytecode (7 bytes):
#   0x00 PUSH2 0x00 0x01   push 1 as a 2-byte immediate (pc advances by 3)
#   0x03 PUSH1 0x00        push slot 0
#   0x05 SSTORE            SSTORE(slot=0, val=1) → sto[0]=1
#   0x06 STOP              bad fires
#
# Key property: PUSH2's pc advance of 3 (not 2) places PUSH1 0x00 at
# offset 0x03. If the translator incorrectly advanced by 2, the 0x01 byte
# would be decoded as PUSH1 0x60 causing wrong program behaviour.
#
# SAT path:
#   Step 0 (pc=0): PUSH2 0x0001 → sp=1, stack[0]=1; pc=3
#   Step 1 (pc=3): PUSH1 0x00  → sp=2, stack[1]=0 (TOS=slot); pc=5
#   Step 2 (pc=5): SSTORE(slot=0, val=1) → sto[0]=1; sp=0; pc=6
#   Step 3 (pc=6): STOP → halted=1; bad fires at step 3
# ---------------------------------------------------------------------------

_SEED_0029_HEX = "61000160005500"


def test_translate_seed_0029_round_trips():
    """Full seed 0029 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0029_HEX)
    spec = _spec(_SEED_0029_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0029_bad_fires_at_step_3():
    """Seed 0029 PUSH2-value SSTORE: bad fires at step 3."""
    bytecode = bytes.fromhex(_SEED_0029_HEX)
    spec = _spec(_SEED_0029_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=6)
    assert trace.bad_fired_at == 3


def test_seed_0029_bad_not_before_step_3():
    """Bad must not fire before step 3."""
    bytecode = bytes.fromhex(_SEED_0029_HEX)
    spec = _spec(_SEED_0029_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=3)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# P33: SLOAD (0x54) — cold/warm gas + sto_warm marking
# ---------------------------------------------------------------------------


def test_translate_sload_round_trips():
    """SLOAD (0x54) bytecode BTOR2 model parses without errors."""
    # PUSH1 0x00 / SLOAD / STOP — key=0, push sto[0]=0, halt
    bytecode = bytes.fromhex("60005400")
    spec = _spec("60005400")
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_translate_sload_stop_fires():
    """PUSH1 + SLOAD + STOP: bad fires at step 2 (STOP)."""
    bytecode = bytes.fromhex("60005400")
    spec = _spec("60005400", "stop")
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 2


# ---------------------------------------------------------------------------
# Seed 0030: SSTORE then SLOAD round-trip (P33)
# ---------------------------------------------------------------------------
# Bytecode (14 bytes):
#   0x00 PUSH1 0x01    push value 1
#   0x02 PUSH1 0x00    push slot 0 (TOS)
#   0x04 SSTORE        sto[0] = 1; sp=0
#   0x05 PUSH1 0x00    push key 0
#   0x07 SLOAD         push sto[0]=1 (WARM: slot 0 already warm); sp=1
#   0x08 PUSH1 0x00    push slot 0 (TOS)
#   0x0a SSTORE        sto[0] = sto[0] = 1 (re-write, slot warm); sp=0
#   0x0b STOP          bad fires (storage_eq slot=0 value=1)
#
# This seed demonstrates: SSTORE marks slot warm → SLOAD reads value back
# → second SSTORE uses the loaded value. The property (sto[0]==1) holds
# after both SSTOREs and fires when STOP halts.
#
# SAT path:
#   Step 0 (pc=0):  PUSH1 0x01 → sp=1
#   Step 1 (pc=2):  PUSH1 0x00 → sp=2 (TOS=slot=0)
#   Step 2 (pc=4):  SSTORE(slot=0, val=1) → sto[0]=1; sp=0
#   Step 3 (pc=5):  PUSH1 0x00 → sp=1 (TOS=key=0)
#   Step 4 (pc=7):  SLOAD(key=0) → push sto[0]=1; sp=1; sto_warm[0]=1
#   Step 5 (pc=8):  PUSH1 0x00 → sp=2 (TOS=slot=0)
#   Step 6 (pc=10): SSTORE(slot=0, val=1) → warm; sp=0
#   Step 7 (pc=11): STOP → bad fires at step 7 (sto[0]=1)
# ---------------------------------------------------------------------------

_SEED_0030_HEX = "6001" + "6000" + "55" + "6000" + "54" + "6000" + "55" + "00"


def test_translate_seed_0030_round_trips():
    """Full seed 0030 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0030_HEX)
    spec = _spec(_SEED_0030_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0030_bad_fires_at_step_7():
    """Seed 0030 SSTORE/SLOAD/SSTORE: bad fires at step 7."""
    bytecode = bytes.fromhex(_SEED_0030_HEX)
    spec = _spec(_SEED_0030_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=10)
    assert trace.bad_fired_at == 7


def test_seed_0030_bad_not_before_step_7():
    """Bad must not fire before step 7."""
    bytecode = bytes.fromhex(_SEED_0030_HEX)
    spec = _spec(_SEED_0030_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=7)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# P34: LOG0-LOG4 event opcodes (0xa0-0xa4)
# ---------------------------------------------------------------------------


def test_translate_log0_round_trips():
    """LOG0 (0xa0) bytecode BTOR2 model parses without errors."""
    # PUSH1 0x00 (size=0) / PUSH1 0x00 (offset=0) / LOG0 / STOP — 5 bytes
    bytecode = bytes.fromhex("6000" + "6000" + "a000")
    spec = _spec("6000" + "6000" + "a000")
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_translate_log0_stop_fires():
    """LOG0 with size=0 + STOP: bad fires at step 3 (STOP at pc=5)."""
    # 2× PUSH1 (steps 0,1) + LOG0 (step 2) + STOP (step 3)
    bytecode = bytes.fromhex("6000" + "6000" + "a000")
    spec = _spec("6000" + "6000" + "a000", "stop")
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 3


def test_translate_log1_round_trips():
    """LOG1 (0xa1) bytecode BTOR2 model parses without errors."""
    # PUSH1 0x00 (topic) / PUSH1 0x00 (size=0) / PUSH1 0x00 (offset=0) / LOG1 / STOP
    bytecode = bytes.fromhex("6000" + "6000" + "6000" + "a100")
    spec = _spec("6000" + "6000" + "6000" + "a100")
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_translate_log4_round_trips():
    """LOG4 (0xa4) bytecode BTOR2 model parses without errors."""
    # 4 topics + size + offset (6 PUSH1s) + LOG4 + STOP
    prefix = "6000" * 6
    bytecode = bytes.fromhex(prefix + "a400")
    spec = _spec(prefix + "a400")
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


# ---------------------------------------------------------------------------
# Seed 0031: LOG1-gated SSTORE (P34)
# ---------------------------------------------------------------------------
# Bytecode (16 bytes):
#   0x00 PUSH1 0x00    push topic 0x00
#   0x02 PUSH1 0x00    push size 0 (TOS)
#   0x04 PUSH1 0x00    push offset 0 (TOS)  — wait, wrong order
#
# LOG1 stack: TOS=offset, NOS=size, 3rd=topic1
# So we push: topic first (deepest), then size, then offset (TOS)
#
#   0x00 PUSH1 0x00    topic (deepest)
#   0x02 PUSH1 0x00    size = 0
#   0x04 PUSH1 0x00    offset = 0 (TOS)
#   0x06 LOG1          emit log; sp -= 3 → sp=0
#   0x07 PUSH1 0x01    push value 1
#   0x09 PUSH1 0x00    push slot 0 (TOS)
#   0x0b SSTORE        sto[0] = 1; sp=0
#   0x0c STOP          bad fires
#
# SAT path:
#   Step 0 (pc=0):  PUSH1 0x00 → sp=1
#   Step 1 (pc=2):  PUSH1 0x00 → sp=2
#   Step 2 (pc=4):  PUSH1 0x00 → sp=3
#   Step 3 (pc=6):  LOG1(offset=0, size=0, topic=0) → sp=0; gas-=375+375
#   Step 4 (pc=7):  PUSH1 0x01 → sp=1
#   Step 5 (pc=9):  PUSH1 0x00 → sp=2
#   Step 6 (pc=11): SSTORE(slot=0, val=1) → sto[0]=1; sp=0
#   Step 7 (pc=12): STOP → bad fires at step 7
# ---------------------------------------------------------------------------

_SEED_0031_HEX = "6000" + "6000" + "6000" + "a1" + "6001" + "6000" + "55" + "00"


def test_translate_seed_0031_round_trips():
    """Full seed 0031 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0031_HEX)
    spec = _spec(_SEED_0031_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0031_bad_fires_at_step_7():
    """Seed 0031 LOG1-gated SSTORE: bad fires at step 7."""
    bytecode = bytes.fromhex(_SEED_0031_HEX)
    spec = _spec(_SEED_0031_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=10)
    assert trace.bad_fired_at == 7


def test_seed_0031_bad_not_before_step_7():
    """Bad must not fire before step 7."""
    bytecode = bytes.fromhex(_SEED_0031_HEX)
    spec = _spec(_SEED_0031_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=7)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# SHA3 / KECCAK256 (0x20) — P35
# ---------------------------------------------------------------------------


def test_translate_sha3_round_trips():
    """PUSH1 0x20 / PUSH1 0x00 / SHA3 / STOP → valid BTOR2."""
    hex_bc = "60206000" + "20" + "00"
    spec = _spec(hex_bc)
    text = translate_bytecode(bytes.fromhex(hex_bc), spec)
    result = from_text(text)
    assert not result.has_errors(), result.diagnostics


def test_translate_sha3_stop_fires():
    """SHA3 then STOP: bad fires at step 3 (0-indexed)."""
    hex_bc = "60206000" + "20" + "00"
    spec = _spec(hex_bc)
    text = translate_bytecode(bytes.fromhex(hex_bc), spec)
    trace = _run(text, max_steps=10)
    assert trace.bad_fired_at == 3


# ---------------------------------------------------------------------------
# Seed 0032: SHA3-then-SSTORE (P35)
# ---------------------------------------------------------------------------
# Bytecode (9 bytes):
#   0x00 PUSH1 0x20    size = 32 (deepest)
#   0x02 PUSH1 0x00    offset = 0 (TOS)
#   0x04 SHA3          hash mem[0..31] → symbolic result; sp=1
#   0x05 PUSH1 0x00    slot = 0 (TOS)
#   0x07 SSTORE        sto[0] = keccak256(mem[0..31]); sp=0
#   0x08 STOP          bad fires (stop property)
#
# SAT path:
#   Step 1 (pc=0):  PUSH1 0x20 → sp=1
#   Step 2 (pc=2):  PUSH1 0x00 → sp=2
#   Step 3 (pc=4):  SHA3(offset=0, size=32) → push symbolic hash; sp=1
#   Step 4 (pc=5):  PUSH1 0x00 → sp=2
#   Step 5 (pc=7):  SSTORE(slot=0, val=hash) → sp=0; cold gas=2200
#   Step 6 (pc=8):  STOP → bad fires at step 6
#
# Gas budget:
#   2× PUSH1 = 6
#   SHA3 (base=30 + word=6 + Cmem word1=3) = 39
#   PUSH1 = 3
#   SSTORE cold = 2200
#   Total ≈ 2248 gas (within GasLimitPin 1000000)
# ---------------------------------------------------------------------------

_SEED_0032_HEX = "6020" + "6000" + "20" + "6000" + "55" + "00"


def test_translate_seed_0032_round_trips():
    """Full seed 0032 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0032_HEX)
    spec = _spec(_SEED_0032_HEX)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0032_bad_fires_at_step_5():
    """Seed 0032 SHA3-then-SSTORE: bad fires at step 5 (0-indexed)."""
    bytecode = bytes.fromhex(_SEED_0032_HEX)
    spec = _spec(_SEED_0032_HEX)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=10)
    assert trace.bad_fired_at == 5


def test_seed_0032_bad_not_before_step_5():
    """Bad must not fire before step 5."""
    bytecode = bytes.fromhex(_SEED_0032_HEX)
    spec = _spec(_SEED_0032_HEX)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# EXTCODEHASH (0x3F) — P36
# ---------------------------------------------------------------------------


def test_translate_extcodehash_round_trips():
    """PUSH1 0x00 / EXTCODEHASH / STOP → valid BTOR2."""
    hex_bc = "6000" + "3f" + "00"
    spec = _spec(hex_bc)
    text = translate_bytecode(bytes.fromhex(hex_bc), spec)
    result = from_text(text)
    assert not result.has_errors(), result.diagnostics


def test_translate_extcodehash_stop_fires():
    """EXTCODEHASH then STOP: bad fires at step 2 (0-indexed)."""
    hex_bc = "6000" + "3f" + "00"
    spec = _spec(hex_bc)
    text = translate_bytecode(bytes.fromhex(hex_bc), spec)
    trace = _run(text, max_steps=10)
    assert trace.bad_fired_at == 2


# ---------------------------------------------------------------------------
# Seed 0033: EXTCODEHASH-then-SSTORE (P36)
# ---------------------------------------------------------------------------
# Bytecode (9 bytes):
#   0x00 PUSH1 0x00    address = 0 (deepest)
#   0x02 EXTCODEHASH   keccak256(code[0]) → symbolic bv256; sp=1
#   0x03 PUSH1 0x00    slot = 0 (TOS)
#   0x05 SSTORE        sto[0] = extcodehash(addr=0); sp=0; cold gas=2200
#   0x06 STOP          bad fires (stop property)
#
# SAT path:
#   Step 0 (pc=0):  PUSH1 0x00 → sp=1
#   Step 1 (pc=2):  EXTCODEHASH(addr=0) → symbolic hash; sp=1
#   Step 2 (pc=3):  PUSH1 0x00 → sp=2
#   Step 3 (pc=5):  SSTORE(slot=0, val=hash) → sp=0; cold gas=2200
#   Step 4 (pc=6):  STOP → bad fires at step 4
#
# Gas budget:
#   PUSH1 = 3
#   EXTCODEHASH cold = 2600
#   PUSH1 = 3
#   SSTORE cold = 2200
#   Total ≈ 4806 gas (within GasLimitPin 1000000)
# ---------------------------------------------------------------------------

_SEED_0033_HEX = "6000" + "3f" + "6000" + "55" + "00"


def test_translate_seed_0033_round_trips():
    """Full seed 0033 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0033_HEX)
    spec = _spec(_SEED_0033_HEX)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0033_bad_fires_at_step_4():
    """Seed 0033 EXTCODEHASH-then-SSTORE: bad fires at step 4."""
    bytecode = bytes.fromhex(_SEED_0033_HEX)
    spec = _spec(_SEED_0033_HEX)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=10)
    assert trace.bad_fired_at == 4


def test_seed_0033_bad_not_before_step_4():
    """Bad must not fire before step 4."""
    bytecode = bytes.fromhex(_SEED_0033_HEX)
    spec = _spec(_SEED_0033_HEX)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=4)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# P37: PUSH-range completeness — PUSH3 / PUSH16 / PUSH31 + corpus seed 0034
# ---------------------------------------------------------------------------
# Systematic coverage for PUSH3..PUSH31 pc-advance correctness.
# PUSH{n} must advance pc by n+1 (opcode byte + n immediate bytes).
# P32 covered PUSH2 (n=2) and PUSH32 (n=32); P37 covers the interior.


def test_translate_push3_round_trips():
    """PUSH3 (0x62) bytecode BTOR2 model parses without errors."""
    # PUSH3 0x00 0x00 0x01 / STOP — 5 bytes
    bytecode = bytes.fromhex("6200000100")
    spec = _spec("6200000100")
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_translate_push3_stop_fires_at_step_1():
    """PUSH3 + STOP: bad fires at step 1 (STOP at pc=4, advance = 3+1)."""
    bytecode = bytes.fromhex("6200000100")
    spec = _spec("6200000100", "stop")
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=5)
    assert trace.bad_fired_at == 1


def test_translate_push3_pc_advances_by_4():
    """PUSH3 opcodes advance pc by 4 (opcode byte + 3 immediates).

    If the advance were 3 instead of 4, the 0x01 byte at offset 3 would
    be decoded as PUSH1 0x60, shifting subsequent instructions and causing
    a wrong trace (trap rather than SSTORE).
    """
    # PUSH3 0x00 0x00 0x01 / PUSH1 0x00 / SSTORE / STOP  — 8 bytes
    bytecode = bytes.fromhex("6200000160005500")
    spec = _spec("6200000160005500", "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=6)
    assert trace.bad_fired_at == 3


def test_translate_push16_pc_advances_by_17():
    """PUSH16 (0x6f) opcodes advance pc by 17 (opcode + 16 immediates)."""
    # PUSH16 <15 zero bytes> 0x01 / PUSH1 0x00 / SSTORE / STOP — 21 bytes
    imm = (1).to_bytes(16, "big").hex()
    hex_str = "6f" + imm + "60005500"
    bytecode = bytes.fromhex(hex_str)
    spec = _spec(hex_str, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=6)
    assert trace.bad_fired_at == 3


def test_translate_push31_pc_advances_by_32():
    """PUSH31 (0x7e) opcodes advance pc by 32 (opcode + 31 immediates)."""
    # PUSH31 <30 zero bytes> 0x01 / PUSH1 0x00 / SSTORE / STOP — 36 bytes
    imm = (1).to_bytes(31, "big").hex()
    hex_str = "7e" + imm + "60005500"
    bytecode = bytes.fromhex(hex_str)
    spec = _spec(hex_str, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=6)
    assert trace.bad_fired_at == 3


# ---------------------------------------------------------------------------
# Seed 0034: PUSH3-based value SSTORE (P37)
# ---------------------------------------------------------------------------
# Bytecode (8 bytes):
#   0x00 PUSH3 0x00 0x00 0x01   push 1 as a 3-byte immediate; pc += 4
#   0x04 PUSH1 0x00             push slot 0
#   0x06 SSTORE                 SSTORE(slot=0, val=1); sto[0]=1
#   0x07 STOP                   halted
#
# Key property: PUSH3 (0x62) uses a 3-byte immediate, advancing pc by 4.
# If the translator incorrectly advanced by 3, the 0x01 byte at offset 3
# would be decoded as PUSH1 0x60 and the trace would diverge (trap, not SSTORE).
#
# bad fires at step 3 (sto[0]==1 first holds after the SSTORE transition).

_SEED_0034_HEX = "62" + "000001" + "6000" + "55" + "00"


def test_translate_seed_0034_round_trips():
    """Full seed 0034 BTOR2 model parses without errors."""
    bytecode = bytes.fromhex(_SEED_0034_HEX)
    spec = _spec(_SEED_0034_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    parsed = from_text(text)
    assert not parsed.has_errors(), parsed.diagnostics


def test_seed_0034_bad_fires_at_step_3():
    """Seed 0034 PUSH3-value SSTORE: bad fires at step 3."""
    bytecode = bytes.fromhex(_SEED_0034_HEX)
    spec = _spec(_SEED_0034_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=6)
    assert trace.bad_fired_at == 3


def test_seed_0034_bad_not_before_step_3():
    """Bad must not fire before step 3."""
    bytecode = bytes.fromhex(_SEED_0034_HEX)
    spec = _spec(_SEED_0034_HEX, "storage_eq",
                 kind=ReachKind.STORAGE_EQ, slot=0, value=1)
    text = translate_bytecode(bytecode, spec)
    trace = _run(text, max_steps=3)
    assert trace.bad_fired_at is None
