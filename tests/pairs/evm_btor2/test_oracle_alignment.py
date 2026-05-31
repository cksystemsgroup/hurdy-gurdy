"""Tests for the evm-btor2 alignment oracle (P5).

Each test exercises ``AlignmentOracle.check`` end-to-end:
  translate_bytecode → CompiledArtifact → reasoning interpreter → AlignmentResult

Corpus seeds under test:
  0001 — PUSH1 0x42 / PUSH1 0x00 / SSTORE / STOP (storage_eq slot=0 value=66)
  0002 — PUSH1 0x00 / CALLDATALOAD / PUSH1 0x00 / SSTORE / STOP (storage_eq slot=0 value=1)
  0003 — PUSH1 0x42 / PUSH1 0x00 / MSTORE8 / PUSH1 0x01 / PUSH1 0x00 / RETURN
         (returndata_eq — MSTORE8+RETURN are OOS; oracle returns UNSAT)
"""

from __future__ import annotations

from gurdy.pairs.evm_btor2.oracle import AlignmentOracle, AlignmentResult
from gurdy.pairs.evm_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BytecodeRef,
    EvmBtor2Spec,
    GasLimitPin,
    ReachKind,
    ReachProperty,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec(
    hex_bytecode: str,
    reach_kind: ReachKind,
    bound: int = 10,
    **prop_kw,
) -> EvmBtor2Spec:
    return EvmBtor2Spec(
        bytecode=BytecodeRef(hex=hex_bytecode),
        scope=AnalysisScope(),
        assumptions=(GasLimitPin(gas=1_000_000),),
        property=ReachProperty(kind=reach_kind, **prop_kw),
        analysis=AnalysisDirective(engine="z3-bmc", bound=bound),
    )


_oracle = AlignmentOracle()


# ---------------------------------------------------------------------------
# Seed 0001 — PUSH1 0x42 / PUSH1 0x00 / SSTORE / STOP
# ---------------------------------------------------------------------------


def test_seed_0001_bad_fired():
    """Seed 0001: oracle reports bad_fired=True (SAT)."""
    spec = _spec("604260005500", ReachKind.STORAGE_EQ, slot=0, value=66)
    result = _oracle.check(spec)
    assert isinstance(result, AlignmentResult)
    assert result.bad_fired is True


def test_seed_0001_witness_step_3():
    """Seed 0001: bad fires at witness_step=3 (after STOP at pc=5)."""
    spec = _spec("604260005500", ReachKind.STORAGE_EQ, slot=0, value=66)
    result = _oracle.check(spec)
    assert result.witness_step == 3


def test_seed_0001_btor2_model_nonempty():
    """Seed 0001: oracle always returns a non-empty BTOR2 model string."""
    spec = _spec("604260005500", ReachKind.STORAGE_EQ, slot=0, value=66)
    result = _oracle.check(spec)
    assert result.btor2_model


def test_seed_0001_bound_too_small_unsat():
    """Seed 0001 with bound=3: bad fires at step 3, so bound=3 misses it."""
    spec = _spec("604260005500", ReachKind.STORAGE_EQ, bound=3, slot=0, value=66)
    result = _oracle.check(spec)
    assert result.bad_fired is False
    assert result.witness_step is None


def test_seed_0001_bound_just_enough():
    """Seed 0001 with bound=4: includes step 3 → bad fires."""
    spec = _spec("604260005500", ReachKind.STORAGE_EQ, bound=4, slot=0, value=66)
    result = _oracle.check(spec)
    assert result.bad_fired is True
    assert result.witness_step == 3


def test_seed_0001_wrong_value_unsat():
    """Seed 0001 with value=99: storage never equals 99 → UNSAT."""
    spec = _spec("604260005500", ReachKind.STORAGE_EQ, slot=0, value=99)
    result = _oracle.check(spec)
    assert result.bad_fired is False


# ---------------------------------------------------------------------------
# Seed 0002 — PUSH1 0x00 / CALLDATALOAD / PUSH1 0x00 / SSTORE / STOP
# ---------------------------------------------------------------------------


def test_seed_0002_no_witness_unsat():
    """Seed 0002 without witness: calldata=0 → sto[0]=0 ≠ 1 → UNSAT."""
    spec = _spec("60003560005500", ReachKind.STORAGE_EQ, slot=0, value=1)
    result = _oracle.check(spec)
    assert result.bad_fired is False


def test_seed_0002_with_witness_sat():
    """Seed 0002 with calldata[31]=1: CALLDATALOAD pushes 1 → sto[0]=1 → SAT."""
    spec = _spec("60003560005500", ReachKind.STORAGE_EQ, slot=0, value=1)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 1}})
    assert result.bad_fired is True


def test_seed_0002_witness_step_4():
    """Seed 0002 execution: PUSH1/CALLDATALOAD/PUSH1/SSTORE/STOP → bad at step 4."""
    spec = _spec("60003560005500", ReachKind.STORAGE_EQ, slot=0, value=1)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 1}})
    assert result.witness_step == 4


# ---------------------------------------------------------------------------
# Seed 0003 — PUSH1 0x42 / PUSH1 0x00 / MSTORE8 / PUSH1 0x01 / PUSH1 0x00 / RETURN
#             (returndata_eq offset=0 data=[0x42], SAT — P8 implements MSTORE8+RETURN)
# ---------------------------------------------------------------------------


def test_seed_0003_bad_fired():
    """Seed 0003: MSTORE8+RETURN are now implemented → bad_fired=True (SAT)."""
    spec = _spec(
        "604260005360016000f3",
        ReachKind.RETURNDATA_EQ,
        offset=0,
        data=(66,),
    )
    result = _oracle.check(spec)
    assert isinstance(result, AlignmentResult)
    assert result.bad_fired is True


def test_seed_0003_witness_step_5():
    """Seed 0003: bad fires at witness_step=5 (after RETURN at pc=9, 0-indexed)."""
    spec = _spec(
        "604260005360016000f3",
        ReachKind.RETURNDATA_EQ,
        offset=0,
        data=(66,),
    )
    result = _oracle.check(spec)
    assert result.witness_step == 5


def test_seed_0003_wrong_value_unsat():
    """Seed 0003 with data=[0x43]: returndata[0] != 0x43 → UNSAT."""
    spec = _spec(
        "604260005360016000f3",
        ReachKind.RETURNDATA_EQ,
        offset=0,
        data=(67,),
    )
    result = _oracle.check(spec)
    assert result.bad_fired is False


def test_seed_0003_btor2_model_nonempty():
    """Seed 0003: oracle returns a non-empty BTOR2 model string."""
    spec = _spec(
        "604260005360016000f3",
        ReachKind.RETURNDATA_EQ,
        offset=0,
        data=(66,),
    )
    result = _oracle.check(spec)
    assert result.btor2_model


# ---------------------------------------------------------------------------
# Seed 0004 — PUSH1 0x00 / CALLDATALOAD / PUSH1 0x07 / JUMPI / STOP /
#             JUMPDEST / PUSH1 0x42 / PUSH1 0x00 / SSTORE / STOP
# ---------------------------------------------------------------------------


def test_seed_0004_no_witness_unsat():
    """Seed 0004 without witness: calldata=0 → cond=0 → JUMPI falls through → STOP (no SSTORE) → UNSAT."""
    spec = _spec("600035600757005b604260005500", ReachKind.STORAGE_EQ, slot=0, value=66)
    result = _oracle.check(spec)
    assert result.bad_fired is False


def test_seed_0004_with_witness_sat():
    """Seed 0004 with calldata[31]=1: cond=1 → jump taken → SSTORE sto[0]=0x42 → SAT."""
    spec = _spec("600035600757005b604260005500", ReachKind.STORAGE_EQ, slot=0, value=66)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 1}})
    assert result.bad_fired is True


def test_seed_0004_witness_step_8():
    """Seed 0004 execution: 9 steps (PUSH1/CALLDATALOAD/PUSH1/JUMPI/JUMPDEST/PUSH1/PUSH1/SSTORE/STOP)
    → bad fires at step 8 (after STOP)."""
    spec = _spec("600035600757005b604260005500", ReachKind.STORAGE_EQ, slot=0, value=66)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 1}})
    assert result.witness_step == 8


# ---------------------------------------------------------------------------
# Seed 0005 — PUSH1 0x00 / CALLDATALOAD / DUP1 / ISZERO / PUSH1 0x0c /
#             JUMPI / PUSH1 0x00 / SSTORE / STOP / JUMPDEST / STOP
# ---------------------------------------------------------------------------
# Bytecode: 6000358015600c57600055005b00
# Property: storage_eq slot=0 value=1  (SAT — find calldata making JUMPI not taken)
#
# Execution trace with calldata[31]=1 (not-taken path):
#   step 0: PUSH1 0x00 → stack=[0]
#   step 1: CALLDATALOAD(offset=0) → stack=[1]
#   step 2: DUP1 → stack=[1,1], sp=2
#   step 3: ISZERO(1)=0 → stack=[1,0], sp=2
#   step 4: PUSH1 0x0c(=12) → stack=[1,0,12], sp=3
#   step 5: JUMPI(dest=12, cond=0) → fall through, sp=1
#   step 6: PUSH1 0x00 → stack=[1,0], sp=2
#   step 7: SSTORE(slot=0, value=1) → sto[0]=1, sp=0
#   step 8: STOP → halted=1  →  bad fires (sto[0]==1 ∧ halted ∧ ¬trap)


def test_seed_0005_no_witness_unsat():
    """Seed 0005 without witness: calldata=0 → ISZERO(0)=1 → JUMPI taken
    → JUMPDEST/STOP without SSTORE → storage stays 0 → UNSAT."""
    spec = _spec("6000358015600c57600055005b00", ReachKind.STORAGE_EQ, slot=0, value=1)
    result = _oracle.check(spec)
    assert result.bad_fired is False


def test_seed_0005_with_witness_sat():
    """Seed 0005 with calldata[31]=1: ISZERO(1)=0 → JUMPI not taken
    → PUSH1/SSTORE writes sto[0]=1 → SAT."""
    spec = _spec("6000358015600c57600055005b00", ReachKind.STORAGE_EQ, slot=0, value=1)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 1}})
    assert result.bad_fired is True


def test_seed_0005_witness_step_8():
    """Seed 0005 not-taken path: 9 opcodes → bad fires at step 8 (after STOP)."""
    spec = _spec("6000358015600c57600055005b00", ReachKind.STORAGE_EQ, slot=0, value=1)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 1}})
    assert result.witness_step == 8


# ---------------------------------------------------------------------------
# Seed 0006 — PUSH1 0x42 / PUSH1 0x00 / MSTORE / PUSH1 0x00 / MLOAD /
#             PUSH1 0x00 / SSTORE / STOP
# ---------------------------------------------------------------------------
# Bytecode: 604260005260005160005500
# Property: storage_eq slot=0 value=66 (0x42)
#
# Execution trace:
#   step 0: PUSH1 0x42 → stack=[0x42], sp=1
#   step 1: PUSH1 0x00 → stack=[0x42,0x00], sp=2
#   step 2: MSTORE(offset=0, value=0x42) → mem[31]=0x42, sp=0
#   step 3: PUSH1 0x00 → stack=[0x00], sp=1
#   step 4: MLOAD(offset=0) → stack=[0x42], sp=1  (reads mem[0..31] big-endian)
#   step 5: PUSH1 0x00 → stack=[0x42,0x00], sp=2
#   step 6: SSTORE(slot=0, value=0x42) → sto[0]=0x42, sp=0
#   step 7: STOP → halted=1 → bad fires (sto[0]==0x42 ∧ halted ∧ ¬trap)


def test_seed_0006_bad_fired():
    """Seed 0006: MLOAD+MSTORE round-trip → bad_fired=True (SAT)."""
    spec = _spec("604260005260005160005500", ReachKind.STORAGE_EQ, slot=0, value=66)
    result = _oracle.check(spec)
    assert isinstance(result, AlignmentResult)
    assert result.bad_fired is True


def test_seed_0006_witness_step_7():
    """Seed 0006: bad fires at step 7 (after STOP at pc=0x0b)."""
    spec = _spec("604260005260005160005500", ReachKind.STORAGE_EQ, slot=0, value=66)
    result = _oracle.check(spec)
    assert result.witness_step == 7


def test_seed_0006_wrong_value_unsat():
    """Seed 0006 with value=99: sto[0] never equals 99 → UNSAT."""
    spec = _spec("604260005260005160005500", ReachKind.STORAGE_EQ, slot=0, value=99)
    result = _oracle.check(spec)
    assert result.bad_fired is False


def test_seed_0006_btor2_model_nonempty():
    """Seed 0006: oracle returns a non-empty BTOR2 model string."""
    spec = _spec("604260005260005160005500", ReachKind.STORAGE_EQ, slot=0, value=66)
    result = _oracle.check(spec)
    assert result.btor2_model


# ---------------------------------------------------------------------------
# Seed 0007 — PUSH1 0x03 / PUSH1 0x00 / CALLDATALOAD / GT /
#             PUSH1 0x0a / JUMPI / STOP /
#             JUMPDEST / PUSH1 0x42 / PUSH1 0x00 / SSTORE / STOP
# ---------------------------------------------------------------------------
# Bytecode: 600360003511600a57005b604260005500
# Property: storage_eq slot=0 value=66 (0x42)
#
# Execution trace with calldata[31]=66 (cd=66 > 3):
#   step 0: PUSH1 0x03 → stack=[3], sp=1
#   step 1: PUSH1 0x00 → stack=[3, 0], sp=2
#   step 2: CALLDATALOAD(offset=0) → stack=[3, 66], sp=2  (reads calldata big-endian)
#   step 3: GT(a=66, b=3) → 1 → stack=[1], sp=1
#   step 4: PUSH1 0x0a → stack=[1, 10], sp=2
#   step 5: JUMPI(dest=10, cond=1) → jump to pc=10, sp=0
#   step 6: JUMPDEST at pc=10 → pc=11, sp=0  (no-op)
#   step 7: PUSH1 0x42 → stack=[66], sp=1
#   step 8: PUSH1 0x00 → stack=[66, 0], sp=2
#   step 9: SSTORE(slot=0, value=66) → sto[0]=66, sp=0
#   step 10: STOP → halted=1  →  bad fires (sto[0]==66 ∧ halted ∧ ¬trap)


def test_seed_0007_no_witness_unsat():
    """Seed 0007 without witness: calldata=0 → cd=0 ≤ 3 → GT=0 → JUMPI
    falls through to STOP → sto[0]=0 ≠ 66 → UNSAT."""
    spec = _spec("600360003511600a57005b604260005500", ReachKind.STORAGE_EQ,
                 bound=15, slot=0, value=66)
    result = _oracle.check(spec)
    assert result.bad_fired is False


def test_seed_0007_with_witness_sat():
    """Seed 0007 with calldata[31]=66: cd=66 > 3 → GT=1 → JUMPI taken
    → SSTORE(0, 0x42) → SAT."""
    spec = _spec("600360003511600a57005b604260005500", ReachKind.STORAGE_EQ,
                 bound=15, slot=0, value=66)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 66}})
    assert result.bad_fired is True


def test_seed_0007_witness_step_10():
    """Seed 0007 taken path: 11 instructions → bad fires at step 10."""
    spec = _spec("600360003511600a57005b604260005500", ReachKind.STORAGE_EQ,
                 bound=15, slot=0, value=66)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 66}})
    assert result.witness_step == 10


def test_seed_0007_btor2_model_nonempty():
    """Seed 0007: oracle returns a non-empty BTOR2 model string."""
    spec = _spec("600360003511600a57005b604260005500", ReachKind.STORAGE_EQ,
                 bound=15, slot=0, value=66)
    result = _oracle.check(spec)
    assert result.btor2_model


# ---------------------------------------------------------------------------
# Seed 0008 — PUSH1 0x64 / PUSH1 0x00 / CALLDATALOAD / PUSH1 0x02 / MUL /
#             GT / PUSH1 0x0d / JUMPI / STOP /
#             JUMPDEST / PUSH1 0x42 / PUSH1 0x00 / SSTORE / STOP
# ---------------------------------------------------------------------------
# Bytecode: 606460003560020211600d57005b604260005500
# Property: storage_eq slot=0 value=66 (0x42)
#
# Execution trace with calldata[31]=51 (2*51=102 > 100):
#   step 0:  PUSH1 0x64 → stack=[100], sp=1
#   step 1:  PUSH1 0x00 → stack=[100,0], sp=2
#   step 2:  CALLDATALOAD(offset=0) → stack=[100,51], sp=2
#   step 3:  PUSH1 0x02 → stack=[100,51,2], sp=3
#   step 4:  MUL(a=2,b=51) → stack=[100,102], sp=2
#   step 5:  GT(a=102,b=100) → 1 → stack=[1], sp=1
#   step 6:  PUSH1 0x0d → stack=[1,13], sp=2
#   step 7:  JUMPI(dest=13,cond=1) → pc=13, sp=0
#   step 8:  JUMPDEST at pc=13 → pc=14
#   step 9:  PUSH1 0x42 → stack=[66], sp=1
#   step 10: PUSH1 0x00 → stack=[66,0], sp=2
#   step 11: SSTORE(slot=0,value=66) → sto[0]=66, sp=0
#   step 12: STOP → halted=1  → bad fires (sto[0]==66 ∧ halted ∧ ¬trap)

_SEED_0008_HEX = "606460003560020211600d57005b604260005500"


def test_seed_0008_no_witness_unsat():
    """Seed 0008 without witness: calldata=0 → 0*2=0 ≤ 100 → GT=0 → JUMPI
    falls through to STOP → sto[0]=0 ≠ 66 → UNSAT."""
    spec = _spec(_SEED_0008_HEX, ReachKind.STORAGE_EQ, bound=20, slot=0, value=66)
    result = _oracle.check(spec)
    assert result.bad_fired is False


def test_seed_0008_with_witness_sat():
    """Seed 0008 with calldata[31]=51: 2*51=102 > 100 → GT=1 → JUMPI taken
    → SSTORE(0, 0x42) → SAT."""
    spec = _spec(_SEED_0008_HEX, ReachKind.STORAGE_EQ, bound=20, slot=0, value=66)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 51}})
    assert result.bad_fired is True


def test_seed_0008_witness_step_12():
    """Seed 0008 taken path: 13 instructions → bad fires at step 12."""
    spec = _spec(_SEED_0008_HEX, ReachKind.STORAGE_EQ, bound=20, slot=0, value=66)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 51}})
    assert result.witness_step == 12


def test_seed_0008_btor2_model_nonempty():
    """Seed 0008: oracle returns a non-empty BTOR2 model string."""
    spec = _spec(_SEED_0008_HEX, ReachKind.STORAGE_EQ, bound=20, slot=0, value=66)
    result = _oracle.check(spec)
    assert result.btor2_model


# ---------------------------------------------------------------------------
# Seed 0010 — PUSH1 0x00 / CALLDATALOAD / PUSH1 0x01 / SHR /
#             PUSH1 0x0f / LT / PUSH1 0x0d / JUMPI / STOP /
#             JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP
# ---------------------------------------------------------------------------
# Bytecode: 60003560011c600f10600d57005b600160005500
# Property: storage_eq slot=0 value=1
#
# LT is used (not GT): PUSH1 0x0f places the threshold (15) on top of the
# shifted result, so LT(TOS=15, NOS=(x>>1)) = 15 < (x>>1) = (x>>1) > 15.
#
# Execution trace with calldata[31]=32 (CALLDATALOAD reads 32 as bv256):
#   step 0:  PUSH1 0x00 → stack=[0], sp=1
#   step 1:  CALLDATALOAD(0) → stack=[32], sp=1
#   step 2:  PUSH1 0x01 → stack=[32, 1], sp=2
#   step 3:  SHR(shift=1, value=32) → 32>>1=16 → stack=[16], sp=1
#   step 4:  PUSH1 0x0f → stack=[16, 15], sp=2
#   step 5:  LT(TOS=15, NOS=16) → 15<16=1 → stack=[1], sp=1
#   step 6:  PUSH1 0x0d → stack=[1, 13], sp=2
#   step 7:  JUMPI(dest=13, cond=1) → pc=13, sp=0
#   step 8:  JUMPDEST at pc=13 → pc=14
#   step 9:  PUSH1 0x01 → stack=[1], sp=1
#   step 10: PUSH1 0x00 → stack=[1, 0], sp=2
#   step 11: SSTORE(slot=0, value=1) → sto[0]=1, sp=0
#   step 12: STOP → halted=1  → bad fires (sto[0]==1 ∧ halted ∧ ¬trap)

_SEED_0010_HEX = "60003560011c600f10600d57005b600160005500"


def test_seed_0010_no_witness_unsat():
    """Seed 0010 without witness: calldata=0 → SHR(1,0)=0, LT(15,0)=0 →
    JUMPI falls through to STOP → sto[0]=0 ≠ 1 → UNSAT."""
    spec = _spec(_SEED_0010_HEX, ReachKind.STORAGE_EQ, bound=20, slot=0, value=1)
    result = _oracle.check(spec)
    assert result.bad_fired is False


def test_seed_0010_with_witness_sat():
    """Seed 0010 with calldata[31]=32: SHR(1, 32)=16, LT(15,16)=1 →
    JUMPI taken → SSTORE(0, 1) → SAT."""
    spec = _spec(_SEED_0010_HEX, ReachKind.STORAGE_EQ, bound=20, slot=0, value=1)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 32}})
    assert result.bad_fired is True


def test_seed_0010_witness_step_12():
    """Seed 0010 taken path: 13 instructions → bad fires at step 12."""
    spec = _spec(_SEED_0010_HEX, ReachKind.STORAGE_EQ, bound=20, slot=0, value=1)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 32}})
    assert result.witness_step == 12


def test_seed_0010_btor2_model_nonempty():
    """Seed 0010: oracle returns a non-empty BTOR2 model string."""
    spec = _spec(_SEED_0010_HEX, ReachKind.STORAGE_EQ, bound=20, slot=0, value=1)
    result = _oracle.check(spec)
    assert result.btor2_model


# ---------------------------------------------------------------------------
# Seed 0011 — PUSH1 0x00 / CALLDATALOAD / PUSH1 0x00 / SIGNEXTEND /
#             PUSH1 0x30 / SLT / PUSH1 0x0d / JUMPI / STOP /
#             JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP
# ---------------------------------------------------------------------------
# Bytecode: 60003560000b603012600d57005b600160005500
# Property: storage_eq slot=0 value=1
#
# SLT is used: PUSH1 0x30 places 48 on top of the sign-extended value,
# so SLT(TOS=48, NOS=x) = 48 < x = x > 48.
#
# Execution trace with calldata[31]=49 (CALLDATALOAD reads 49 as bv256):
#   step 0:  PUSH1 0x00 → stack=[0], sp=1
#   step 1:  CALLDATALOAD(0) → stack=[49], sp=1
#   step 2:  PUSH1 0x00 → stack=[49, 0], sp=2
#   step 3:  SIGNEXTEND(bytenum=0, x=49) → 49 (bit 7 clear) → stack=[49], sp=1
#   step 4:  PUSH1 0x30 → stack=[49, 48], sp=2
#   step 5:  SLT(TOS=48, NOS=49) → 48<49=1 → stack=[1], sp=1
#   step 6:  PUSH1 0x0d → stack=[1, 13], sp=2
#   step 7:  JUMPI(dest=13, cond=1) → pc=13, sp=0
#   step 8:  JUMPDEST at pc=13 → pc=14
#   step 9:  PUSH1 0x01 → stack=[1], sp=1
#   step 10: PUSH1 0x00 → stack=[1, 0], sp=2
#   step 11: SSTORE(slot=0, value=1) → sto[0]=1, sp=0
#   step 12: STOP → halted=1  → bad fires (sto[0]==1 ∧ halted ∧ ¬trap)

_SEED_0011_HEX = "60003560000b603012600d57005b600160005500"


def test_seed_0011_no_witness_unsat():
    """Seed 0011 without witness: calldata=0 → SIGNEXTEND(0,0)=0,
    SLT(48,0)=0 → JUMPI falls through to STOP → sto[0]=0 ≠ 1 → UNSAT."""
    spec = _spec(_SEED_0011_HEX, ReachKind.STORAGE_EQ, bound=20, slot=0, value=1)
    result = _oracle.check(spec)
    assert result.bad_fired is False


def test_seed_0011_with_witness_sat():
    """Seed 0011 with calldata[31]=49: SIGNEXTEND(0,49)=49,
    SLT(48,49)=1 → JUMPI taken → SSTORE(0,1) → SAT."""
    spec = _spec(_SEED_0011_HEX, ReachKind.STORAGE_EQ, bound=20, slot=0, value=1)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 49}})
    assert result.bad_fired is True


def test_seed_0011_witness_step_12():
    """Seed 0011 taken path: 13 instructions → bad fires at step 12."""
    spec = _spec(_SEED_0011_HEX, ReachKind.STORAGE_EQ, bound=20, slot=0, value=1)
    result = _oracle.check(spec, witness_binding={"calldata": {31: 49}})
    assert result.witness_step == 12


def test_seed_0011_btor2_model_nonempty():
    """Seed 0011: oracle returns a non-empty BTOR2 model string."""
    spec = _spec(_SEED_0011_HEX, ReachKind.STORAGE_EQ, bound=20, slot=0, value=1)
    result = _oracle.check(spec)
    assert result.btor2_model
