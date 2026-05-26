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
# Seed 0003 — MSTORE8 + RETURN are out-of-scope → OOS trap fires, bad never fires
# ---------------------------------------------------------------------------


def test_seed_0003_oos_unsat():
    """Seed 0003: MSTORE8(0x53) is OOS → trap=1; returndata_eq needs NOT trap → UNSAT."""
    spec = _spec(
        "604260005360016000f3",
        ReachKind.RETURNDATA_EQ,
        offset=0,
        data=(66,),
    )
    result = _oracle.check(spec)
    assert result.bad_fired is False


def test_seed_0003_btor2_model_nonempty():
    """Seed 0003: oracle still returns a BTOR2 model even when UNSAT."""
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
