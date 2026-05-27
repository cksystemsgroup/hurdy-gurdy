"""Tests for EbpfBtor2Spec, its validator, and canonical serialisation.

All tests are unit tests — no solver, no ELF loading.
"""

import pytest

from gurdy.pairs.ebpf_btor2 import PAIR_ID, SCHEMA_VERSION
from gurdy.pairs.ebpf_btor2.spec import (
    AnalysisDirective,
    EbpfBtor2Spec,
    EbpfProgramRef,
    EbpfScope,
    ExitReached,
    PacketBound,
    Property,
    RegisterAt,
    RegisterBound,
    validate_ebpf_btor2_spec,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_spec(**overrides) -> EbpfBtor2Spec:
    defaults = dict(
        program=EbpfProgramRef(path="prog.bpf.o"),
        scope=EbpfScope(max_insns=64, prog_type="socket_filter"),
        observables=(),
        assumptions=(),
        property=Property(expression="exit_reached"),
        analysis=AnalysisDirective(engine="z3-bmc"),
    )
    defaults.update(overrides)
    return EbpfBtor2Spec(**defaults)


def _validate(spec: EbpfBtor2Spec) -> list:
    return list(validate_ebpf_btor2_spec(spec, source=None))


# ---------------------------------------------------------------------------
# Package-level constants
# ---------------------------------------------------------------------------

def test_pair_id():
    assert PAIR_ID == "ebpf-btor2"


def test_schema_version_format():
    parts = SCHEMA_VERSION.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_schema_version_is_1_0_0():
    assert SCHEMA_VERSION == "1.0.0"


# ---------------------------------------------------------------------------
# Spec construction
# ---------------------------------------------------------------------------

def test_minimal_spec_has_no_diagnostics():
    spec = _minimal_spec()
    diags = _validate(spec)
    assert diags == []


def test_pair_class_variable():
    assert EbpfBtor2Spec.pair == "ebpf-btor2"


def test_default_property_is_false():
    spec = _minimal_spec(property=Property(expression="false"))
    diags = _validate(spec)
    assert diags == []


# ---------------------------------------------------------------------------
# Validator — error paths
# ---------------------------------------------------------------------------

def test_empty_program_path_raises():
    spec = _minimal_spec(program=EbpfProgramRef(path=""))
    diags = _validate(spec)
    assert any("0002" in d.code for d in diags)


def test_non_positive_max_insns_raises():
    spec = _minimal_spec(scope=EbpfScope(max_insns=0))
    diags = _validate(spec)
    assert any("0003" in d.code for d in diags)


def test_negative_max_insns_raises():
    spec = _minimal_spec(scope=EbpfScope(max_insns=-1))
    diags = _validate(spec)
    assert any("0003" in d.code for d in diags)


def test_register_out_of_range():
    spec = _minimal_spec(
        assumptions=(RegisterBound(reg=11, value_lo=0, value_hi=100),)
    )
    diags = _validate(spec)
    assert any("0020" in d.code for d in diags)


def test_register_bound_lo_gt_hi():
    spec = _minimal_spec(
        assumptions=(RegisterBound(reg=0, value_lo=10, value_hi=5),)
    )
    diags = _validate(spec)
    assert any("0021" in d.code for d in diags)


def test_valid_register_bound():
    spec = _minimal_spec(
        assumptions=(RegisterBound(reg=0, value_lo=0, value_hi=0xFF),)
    )
    diags = _validate(spec)
    assert diags == []


def test_register_at_invalid_reg():
    spec = _minimal_spec(
        observables=(RegisterAt(reg=11, insn_idx=0),)
    )
    diags = _validate(spec)
    assert any("0010" in d.code for d in diags)


def test_register_at_negative_insn_idx():
    spec = _minimal_spec(
        observables=(RegisterAt(reg=0, insn_idx=-1),)
    )
    diags = _validate(spec)
    assert any("0011" in d.code for d in diags)


def test_analysis_negative_bound():
    spec = _minimal_spec(
        analysis=AnalysisDirective(engine="z3-bmc", bound=-1)
    )
    diags = _validate(spec)
    assert any("0030" in d.code for d in diags)


def test_analysis_zero_timeout():
    spec = _minimal_spec(
        analysis=AnalysisDirective(engine="z3-bmc", timeout=0.0)
    )
    diags = _validate(spec)
    assert any("0031" in d.code for d in diags)


def test_packet_bound_negative_lo():
    spec = _minimal_spec(
        assumptions=(PacketBound(len_lo=-1, len_hi=100),)
    )
    diags = _validate(spec)
    assert any("0022" in d.code for d in diags)


def test_packet_bound_lo_gt_hi():
    spec = _minimal_spec(
        assumptions=(PacketBound(len_lo=200, len_hi=100),)
    )
    diags = _validate(spec)
    assert any("0023" in d.code for d in diags)


# ---------------------------------------------------------------------------
# Round-trip serialisation
# ---------------------------------------------------------------------------

def test_round_trip_minimal():
    spec = _minimal_spec()
    spec2 = EbpfBtor2Spec.from_jsonable(spec.to_jsonable())
    assert spec == spec2


def test_round_trip_with_assumptions():
    spec = _minimal_spec(
        assumptions=(
            RegisterBound(reg=1, value_lo=0, value_hi=0xFFFF_FFFF),
            PacketBound(len_lo=14, len_hi=1500),
        )
    )
    spec2 = EbpfBtor2Spec.from_jsonable(spec.to_jsonable())
    assert spec == spec2


def test_round_trip_with_observables():
    spec = _minimal_spec(
        observables=(
            RegisterAt(reg=0, insn_idx=5),
            ExitReached(insn_idx=10),
        )
    )
    spec2 = EbpfBtor2Spec.from_jsonable(spec.to_jsonable())
    assert spec == spec2


def test_canonical_bytes_are_deterministic():
    spec = _minimal_spec(
        assumptions=(RegisterBound(reg=3, value_lo=0, value_hi=255),)
    )
    assert spec.canonical_bytes() == spec.canonical_bytes()


def test_spec_hash_differs_on_different_programs():
    spec_a = _minimal_spec(program=EbpfProgramRef(path="a.bpf.o"))
    spec_b = _minimal_spec(program=EbpfProgramRef(path="b.bpf.o"))
    assert spec_a.spec_hash() != spec_b.spec_hash()


def test_spec_hash_differs_on_different_properties():
    spec_a = _minimal_spec(property=Property(expression="exit_reached"))
    spec_b = _minimal_spec(property=Property(expression="false"))
    assert spec_a.spec_hash() != spec_b.spec_hash()


def test_wrong_pair_rejected():
    spec = _minimal_spec()
    obj = spec.to_jsonable()
    obj["pair"] = "riscv-btor2"
    with pytest.raises(ValueError, match="not a ebpf-btor2 spec"):
        EbpfBtor2Spec.from_jsonable(obj)
