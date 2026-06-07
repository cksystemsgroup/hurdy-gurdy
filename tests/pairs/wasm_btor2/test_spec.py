"""Tests for gurdy.pairs.wasm_btor2.spec."""

import pytest

from gurdy.pairs.wasm_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    Comparison,
    GlobalAt,
    GlobalInit,
    ImportFixed,
    LocalAt,
    LocalInit,
    MemoryByteAt,
    MemoryInit,
    PropertyKind,
    QuestionSpec,
    StackDepthAt,
    WasmBtor2Spec,
    WasmModuleRef,
    validate_wasm_btor2_spec,
)
from gurdy.core.diagnostics import Severity


# ---------------------------------------------------------------------------
# Construction defaults
# ---------------------------------------------------------------------------


def test_default_spec_is_constructible():
    spec = WasmBtor2Spec()
    assert spec.pair == "wasm-btor2"
    assert spec.module.path == ""
    assert spec.scope.entry_function == ""
    assert spec.observables == ()
    assert spec.assumptions == ()
    assert spec.question.kind == PropertyKind.REACH_TRAP
    assert spec.analysis.engine == "z3-bmc"


def test_minimal_valid_spec():
    spec = WasmBtor2Spec(
        module=WasmModuleRef(path="module.wasm"),
        scope=AnalysisScope(entry_function="main"),
    )
    diags = list(validate_wasm_btor2_spec(spec))
    assert not diags


# ---------------------------------------------------------------------------
# from_jsonable round-trip
# ---------------------------------------------------------------------------


def _make_spec() -> WasmBtor2Spec:
    return WasmBtor2Spec(
        module=WasmModuleRef(path="add.wasm", content_hash="deadbeef"),
        scope=AnalysisScope(entry_function="add", included_callees=("helper",)),
        observables=(
            LocalAt(func_idx=0, local_idx=1, step=3),
            GlobalAt(global_idx=0, step=5),
            MemoryByteAt(address=0x100, step=2),
            StackDepthAt(step=0),
        ),
        assumptions=(
            LocalInit(func_idx=0, local_idx=0, op=Comparison.EQ, value=42),
            GlobalInit(global_idx=0, op=Comparison.LT, value=100),
            MemoryInit(address=0, width=4, op=Comparison.GEU, value=0),
            ImportFixed(import_module="env", import_name="log", value=0),
        ),
        question=QuestionSpec(
            kind=PropertyKind.REACH_HOST_CALL,
            predicate="env.log",
            negate=False,
        ),
        analysis=AnalysisDirective(
            engine="z3-bmc",
            bound=10,
            timeout=30.0,
            extra_options={"tactic": "qfbv"},
        ),
    )


def test_from_jsonable_round_trip():
    original = _make_spec()
    serialised = original.to_jsonable()
    restored = WasmBtor2Spec.from_jsonable(serialised)
    assert original == restored


def test_from_jsonable_rejects_wrong_pair():
    with pytest.raises(ValueError, match="not a wasm-btor2 spec"):
        WasmBtor2Spec.from_jsonable({"pair": "riscv-btor2", "fields": {}})


def test_spec_hash_is_stable():
    spec = _make_spec()
    assert spec.spec_hash() == spec.spec_hash()


def test_spec_hash_changes_with_content():
    a = WasmBtor2Spec(
        module=WasmModuleRef(path="a.wasm"),
        scope=AnalysisScope(entry_function="main"),
    )
    b = WasmBtor2Spec(
        module=WasmModuleRef(path="b.wasm"),
        scope=AnalysisScope(entry_function="main"),
    )
    assert a.spec_hash() != b.spec_hash()


# ---------------------------------------------------------------------------
# Validator — structural errors
# ---------------------------------------------------------------------------


def test_validator_catches_empty_module_path():
    spec = WasmBtor2Spec(
        module=WasmModuleRef(path=""),
        scope=AnalysisScope(entry_function="main"),
    )
    codes = {d.code for d in validate_wasm_btor2_spec(spec)}
    assert "wasm-btor2/spec/0002" in codes


def test_validator_catches_empty_entry_function():
    spec = WasmBtor2Spec(
        module=WasmModuleRef(path="m.wasm"),
        scope=AnalysisScope(entry_function=""),
    )
    codes = {d.code for d in validate_wasm_btor2_spec(spec)}
    assert "wasm-btor2/spec/0003" in codes


def test_validator_catches_negative_observable_step():
    spec = WasmBtor2Spec(
        module=WasmModuleRef(path="m.wasm"),
        scope=AnalysisScope(entry_function="f"),
        observables=(LocalAt(func_idx=0, local_idx=0, step=-1),),
    )
    codes = {d.code for d in validate_wasm_btor2_spec(spec)}
    assert "wasm-btor2/spec/0012" in codes


def test_validator_catches_bad_memory_init_width():
    spec = WasmBtor2Spec(
        module=WasmModuleRef(path="m.wasm"),
        scope=AnalysisScope(entry_function="f"),
        assumptions=(MemoryInit(address=0, width=3, op=Comparison.EQ, value=0),),
    )
    codes = {d.code for d in validate_wasm_btor2_spec(spec)}
    assert "wasm-btor2/spec/0024" in codes


def test_validator_accepts_valid_memory_init_widths():
    for w in (1, 2, 4, 8):
        spec = WasmBtor2Spec(
            module=WasmModuleRef(path="m.wasm"),
            scope=AnalysisScope(entry_function="f"),
            assumptions=(MemoryInit(address=0, width=w, op=Comparison.EQ, value=0),),
        )
        codes = {d.code for d in validate_wasm_btor2_spec(spec)}
        assert "wasm-btor2/spec/0024" not in codes, f"width={w} should be valid"


def test_validator_catches_negative_bound():
    spec = WasmBtor2Spec(
        module=WasmModuleRef(path="m.wasm"),
        scope=AnalysisScope(entry_function="f"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=-1),
    )
    codes = {d.code for d in validate_wasm_btor2_spec(spec)}
    assert "wasm-btor2/spec/0030" in codes


def test_validator_catches_zero_timeout():
    spec = WasmBtor2Spec(
        module=WasmModuleRef(path="m.wasm"),
        scope=AnalysisScope(entry_function="f"),
        analysis=AnalysisDirective(engine="z3-bmc", timeout=0.0),
    )
    codes = {d.code for d in validate_wasm_btor2_spec(spec)}
    assert "wasm-btor2/spec/0031" in codes


def test_validator_catches_non_spec():
    diags = list(validate_wasm_btor2_spec("not a spec"))
    assert any(d.code == "wasm-btor2/spec/0001" for d in diags)
    assert all(d.severity == Severity.ERROR for d in diags)


def test_validator_with_source_checks_entry_function():
    class FakeSource:
        def export(self, name):
            return None  # nothing exported

    spec = WasmBtor2Spec(
        module=WasmModuleRef(path="m.wasm"),
        scope=AnalysisScope(entry_function="missing"),
    )
    codes = {d.code for d in validate_wasm_btor2_spec(spec, source=FakeSource())}
    assert "wasm-btor2/spec/0004" in codes


def test_validator_with_source_checks_included_callees():
    class FakeSource:
        def export(self, name):
            return "ok" if name == "main" else None

    spec = WasmBtor2Spec(
        module=WasmModuleRef(path="m.wasm"),
        scope=AnalysisScope(entry_function="main", included_callees=("ghost",)),
    )
    codes = {d.code for d in validate_wasm_btor2_spec(spec, source=FakeSource())}
    assert "wasm-btor2/spec/0005" in codes
