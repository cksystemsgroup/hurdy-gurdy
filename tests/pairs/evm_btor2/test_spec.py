"""Tests for evm-btor2 spec.py — schema v1.0.0."""

from __future__ import annotations

import pytest

from gurdy.pairs.evm_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BytecodeRef,
    CalldataBytePin,
    CalldatasizePin,
    CallerPin,
    CallvaluePin,
    EvmBtor2Spec,
    EvmVersion,
    GasLimitPin,
    OriginPin,
    ReachKind,
    ReachProperty,
    SCHEMA_VERSION,
    StoragePin,
    StorageWarm,
    validate_evm_btor2_spec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIMPLE_BYTECODE = "6001600101"  # PUSH1 0x01, PUSH1 0x01, ADD (no STOP — trap)
_STOP_BYTECODE = "00"


def _valid_spec(**kwargs) -> EvmBtor2Spec:
    defaults: dict = dict(
        bytecode=BytecodeRef(hex=_SIMPLE_BYTECODE),
        property=ReachProperty(kind=ReachKind.REVERT),
    )
    defaults.update(kwargs)
    return EvmBtor2Spec(**defaults)


def _diag_codes(spec: EvmBtor2Spec) -> list[str]:
    return [d.code for d in validate_evm_btor2_spec(spec)]


# ---------------------------------------------------------------------------
# SCHEMA_VERSION
# ---------------------------------------------------------------------------


def test_schema_version():
    assert SCHEMA_VERSION == "1.0.0"


# ---------------------------------------------------------------------------
# BytecodeRef validation
# ---------------------------------------------------------------------------


def test_empty_bytecode_flagged():
    spec = _valid_spec(bytecode=BytecodeRef(hex=""))
    assert any("0010" in c for c in _diag_codes(spec))


def test_odd_hex_length_flagged():
    spec = _valid_spec(bytecode=BytecodeRef(hex="abc"))
    assert any("0011" in c for c in _diag_codes(spec))


def test_invalid_hex_chars_flagged():
    spec = _valid_spec(bytecode=BytecodeRef(hex="zzzz"))
    codes = _diag_codes(spec)
    # Both odd-length (len 4 is even) and invalid chars — only 0012 fires here.
    assert any("0012" in c for c in codes)


def test_valid_hex_no_error():
    spec = _valid_spec(bytecode=BytecodeRef(hex=_SIMPLE_BYTECODE))
    assert not _diag_codes(spec)


# ---------------------------------------------------------------------------
# AnalysisScope
# ---------------------------------------------------------------------------


def test_default_evm_version_is_london():
    assert AnalysisScope().evm_version == EvmVersion.LONDON


def test_shanghai_version_accepted():
    spec = _valid_spec(scope=AnalysisScope(evm_version=EvmVersion.SHANGHAI))
    assert not _diag_codes(spec)


# ---------------------------------------------------------------------------
# CallerPin
# ---------------------------------------------------------------------------


def test_caller_pin_valid_address():
    spec = _valid_spec(assumptions=(CallerPin(address=0xDEADBEEF),))
    assert not _diag_codes(spec)


def test_caller_pin_address_too_large():
    spec = _valid_spec(assumptions=(CallerPin(address=1 << 160),))
    assert any("0031" in c for c in _diag_codes(spec))


def test_duplicate_caller_pin():
    spec = _valid_spec(assumptions=(CallerPin(address=1), CallerPin(address=2)))
    assert any("0030" in c for c in _diag_codes(spec))


# ---------------------------------------------------------------------------
# CallvaluePin
# ---------------------------------------------------------------------------


def test_callvalue_pin_zero_accepted():
    spec = _valid_spec(assumptions=(CallvaluePin(value=0),))
    assert not _diag_codes(spec)


def test_callvalue_pin_max_accepted():
    spec = _valid_spec(assumptions=(CallvaluePin(value=(1 << 256) - 1),))
    assert not _diag_codes(spec)


def test_callvalue_pin_overflow():
    spec = _valid_spec(assumptions=(CallvaluePin(value=1 << 256),))
    assert any("0033" in c for c in _diag_codes(spec))


# ---------------------------------------------------------------------------
# OriginPin
# ---------------------------------------------------------------------------


def test_origin_pin_valid():
    spec = _valid_spec(assumptions=(OriginPin(address=0x1234),))
    assert not _diag_codes(spec)


def test_origin_pin_address_too_large():
    spec = _valid_spec(assumptions=(OriginPin(address=1 << 161),))
    assert any("0035" in c for c in _diag_codes(spec))


# ---------------------------------------------------------------------------
# CalldatasizePin
# ---------------------------------------------------------------------------


def test_calldatasize_pin_valid():
    spec = _valid_spec(assumptions=(CalldatasizePin(size=4),))
    assert not _diag_codes(spec)


def test_calldatasize_pin_zero():
    spec = _valid_spec(assumptions=(CalldatasizePin(size=0),))
    assert not _diag_codes(spec)


def test_duplicate_calldatasize():
    spec = _valid_spec(assumptions=(CalldatasizePin(size=4), CalldatasizePin(size=8)))
    assert any("0036" in c for c in _diag_codes(spec))


# ---------------------------------------------------------------------------
# CalldataBytePin
# ---------------------------------------------------------------------------


def test_calldata_byte_pin_valid():
    spec = _valid_spec(assumptions=(CalldataBytePin(offset=0, value=0xAB),))
    assert not _diag_codes(spec)


def test_calldata_byte_value_out_of_range():
    spec = _valid_spec(assumptions=(CalldataBytePin(offset=0, value=256),))
    assert any("0041" in c for c in _diag_codes(spec))


def test_calldata_byte_conflicting_pins():
    spec = _valid_spec(assumptions=(
        CalldataBytePin(offset=5, value=0x01),
        CalldataBytePin(offset=5, value=0x02),
    ))
    assert any("0042" in c for c in _diag_codes(spec))


def test_calldata_byte_same_value_no_conflict():
    spec = _valid_spec(assumptions=(
        CalldataBytePin(offset=5, value=0x01),
        CalldataBytePin(offset=5, value=0x01),
    ))
    assert not _diag_codes(spec)


# ---------------------------------------------------------------------------
# StoragePin
# ---------------------------------------------------------------------------


def test_storage_pin_valid():
    spec = _valid_spec(assumptions=(StoragePin(slot=0, value=42),))
    assert not _diag_codes(spec)


def test_duplicate_storage_pin_same_slot():
    spec = _valid_spec(assumptions=(StoragePin(slot=1, value=0), StoragePin(slot=1, value=1)))
    assert any("0050" in c for c in _diag_codes(spec))


def test_storage_pin_different_slots_ok():
    spec = _valid_spec(assumptions=(StoragePin(slot=0, value=1), StoragePin(slot=1, value=2)))
    assert not _diag_codes(spec)


# ---------------------------------------------------------------------------
# StorageWarm
# ---------------------------------------------------------------------------


def test_storage_warm_valid():
    spec = _valid_spec(assumptions=(StorageWarm(slot=7),))
    assert not _diag_codes(spec)


def test_storage_warm_slot_out_of_range():
    spec = _valid_spec(assumptions=(StorageWarm(slot=-1),))
    assert any("0055" in c for c in _diag_codes(spec))


# ---------------------------------------------------------------------------
# GasLimitPin
# ---------------------------------------------------------------------------


def test_gas_limit_pin_valid():
    spec = _valid_spec(assumptions=(GasLimitPin(gas=30_000_000),))
    assert not _diag_codes(spec)


def test_gas_limit_pin_zero():
    spec = _valid_spec(assumptions=(GasLimitPin(gas=0),))
    assert not _diag_codes(spec)


def test_gas_limit_pin_overflow():
    spec = _valid_spec(assumptions=(GasLimitPin(gas=(1 << 64)),))
    assert any("0061" in c for c in _diag_codes(spec))


def test_duplicate_gas_limit():
    spec = _valid_spec(assumptions=(GasLimitPin(gas=100), GasLimitPin(gas=200)))
    assert any("0060" in c for c in _diag_codes(spec))


# ---------------------------------------------------------------------------
# ReachProperty
# ---------------------------------------------------------------------------


def test_reach_revert_no_extra_fields_needed():
    spec = _valid_spec(property=ReachProperty(kind=ReachKind.REVERT))
    assert not _diag_codes(spec)


def test_reach_stop_no_extra_fields_needed():
    spec = _valid_spec(property=ReachProperty(kind=ReachKind.STOP))
    assert not _diag_codes(spec)


def test_reach_storage_eq_requires_slot():
    spec = _valid_spec(property=ReachProperty(kind=ReachKind.STORAGE_EQ, value=0))
    assert any("0071" in c for c in _diag_codes(spec))


def test_reach_storage_eq_requires_value():
    spec = _valid_spec(property=ReachProperty(kind=ReachKind.STORAGE_EQ, slot=0))
    assert any("0073" in c for c in _diag_codes(spec))


def test_reach_storage_eq_valid():
    spec = _valid_spec(property=ReachProperty(kind=ReachKind.STORAGE_EQ, slot=0, value=1))
    assert not _diag_codes(spec)


def test_reach_storage_eq_slot_out_of_range():
    spec = _valid_spec(property=ReachProperty(kind=ReachKind.STORAGE_EQ, slot=1 << 256, value=0))
    assert any("0072" in c for c in _diag_codes(spec))


def test_reach_returndata_eq_requires_offset():
    spec = _valid_spec(property=ReachProperty(kind=ReachKind.RETURNDATA_EQ, data=(0x01,)))
    assert any("0075" in c for c in _diag_codes(spec))


def test_reach_returndata_eq_requires_data():
    spec = _valid_spec(property=ReachProperty(kind=ReachKind.RETURNDATA_EQ, offset=0))
    assert any("0077" in c for c in _diag_codes(spec))


def test_reach_returndata_eq_valid():
    spec = _valid_spec(
        property=ReachProperty(kind=ReachKind.RETURNDATA_EQ, offset=0, data=(0x01, 0x02))
    )
    assert not _diag_codes(spec)


def test_reach_returndata_eq_bad_byte():
    spec = _valid_spec(
        property=ReachProperty(kind=ReachKind.RETURNDATA_EQ, offset=0, data=(256,))
    )
    assert any("0078" in c for c in _diag_codes(spec))


# ---------------------------------------------------------------------------
# AnalysisDirective
# ---------------------------------------------------------------------------


def test_default_engine_is_z3_bmc():
    assert AnalysisDirective().engine == "z3-bmc"


def test_unknown_engine_flagged():
    spec = _valid_spec(analysis=AnalysisDirective(engine="hevm"))
    assert any("0080" in c for c in _diag_codes(spec))


def test_negative_bound_flagged():
    spec = _valid_spec(analysis=AnalysisDirective(engine="z3-bmc", bound=-1))
    assert any("0081" in c for c in _diag_codes(spec))


def test_zero_bound_flagged():
    spec = _valid_spec(analysis=AnalysisDirective(engine="z3-bmc", bound=0))
    assert any("0081" in c for c in _diag_codes(spec))


def test_positive_bound_ok():
    spec = _valid_spec(analysis=AnalysisDirective(engine="z3-bmc", bound=50))
    assert not _diag_codes(spec)


def test_negative_timeout_flagged():
    spec = _valid_spec(analysis=AnalysisDirective(engine="z3-bmc", timeout=-5))
    assert any("0082" in c for c in _diag_codes(spec))


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_round_trip_minimal():
    spec = _valid_spec()
    obj = spec.to_jsonable()
    spec2 = EvmBtor2Spec.from_jsonable(obj)
    assert spec == spec2


def test_round_trip_with_assumptions():
    spec = _valid_spec(
        bytecode=BytecodeRef(hex=_STOP_BYTECODE),
        scope=AnalysisScope(evm_version=EvmVersion.SHANGHAI),
        assumptions=(
            CallerPin(address=0xABCD),
            CallvaluePin(value=0),
            StoragePin(slot=1, value=42),
            GasLimitPin(gas=100_000),
        ),
        property=ReachProperty(kind=ReachKind.STORAGE_EQ, slot=1, value=42),
        analysis=AnalysisDirective(engine="z3-bmc", bound=20),
    )
    obj = spec.to_jsonable()
    spec2 = EvmBtor2Spec.from_jsonable(obj)
    assert spec == spec2


def test_from_jsonable_wrong_pair():
    with pytest.raises(ValueError, match="not a evm-btor2 spec"):
        EvmBtor2Spec.from_jsonable({"pair": "riscv-btor2", "fields": {}})


def test_spec_hash_stable():
    spec = _valid_spec()
    assert spec.spec_hash() == spec.spec_hash()


def test_spec_hash_differs_on_bytecode_change():
    spec1 = _valid_spec(bytecode=BytecodeRef(hex="00"))
    spec2 = _valid_spec(bytecode=BytecodeRef(hex="6001"))
    assert spec1.spec_hash() != spec2.spec_hash()
