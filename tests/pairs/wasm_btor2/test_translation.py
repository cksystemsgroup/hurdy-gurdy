"""Tests for the wasm-btor2 P4 translator.

Each test targets one public function or invariant; the test corpus
uses hand-crafted minimal WASM binaries built inline — no external
``.wasm`` files needed.
"""

from __future__ import annotations

import pytest

from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
from gurdy.core.pair import CompiledArtifact
from gurdy.pairs.wasm_btor2.btor2.parser import from_text as btor2_parse
from gurdy.pairs.wasm_btor2.source import load_wasm_source
from gurdy.pairs.wasm_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    Comparison,
    LocalInit,
    PropertyKind,
    QuestionSpec,
    WasmBtor2Spec,
    WasmModuleRef,
)
from gurdy.pairs.wasm_btor2.translation import (
    SCHEMA_VERSION,
    TRANSLATOR_VERSION,
    Translator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uleb128(v: int) -> bytes:
    if v == 0:
        return bytes([0])
    result = []
    while v > 0:
        low7 = v & 0x7F
        v >>= 7
        if v > 0:
            low7 |= 0x80
        result.append(low7)
    return bytes(result)


def _make_wasm(
    params: list[int],
    results: list[int],
    body_bytes: bytes,
    export_name: str = "main",
) -> bytes:
    """Build a minimal single-function WASM module binary."""
    I32 = 0x7F

    # type section: 1 functype
    type_body = (
        bytes([1, 0x60, len(params)])
        + bytes(params)
        + bytes([len(results)])
        + bytes(results)
    )

    # function section: 1 function → type 0
    func_body = bytes([1, 0])

    # export section: export_name → func 0
    nb = export_name.encode("utf-8")
    export_body = bytes([1]) + _uleb128(len(nb)) + nb + bytes([0, 0])

    # code section: 1 function body
    func_bytes = bytes([0]) + body_bytes  # 0 local groups + body
    code_body = bytes([1]) + _uleb128(len(func_bytes)) + func_bytes

    def section(sec_id: int, body: bytes) -> bytes:
        return bytes([sec_id]) + _uleb128(len(body)) + body

    return (
        b"\x00asm\x01\x00\x00\x00"
        + section(1, type_body)
        + section(3, func_body)
        + section(7, export_body)
        + section(10, code_body)
    )


def _make_annotator() -> AnnotationEmitter:
    sidecar = AnnotationSidecar(schema_version=SCHEMA_VERSION, spec_hash="")
    return AnnotationEmitter(sidecar)


def _make_spec(
    entry: str = "main",
    kind: PropertyKind = PropertyKind.REACH_TRAP,
    negate: bool = False,
    assumptions: tuple = (),
) -> WasmBtor2Spec:
    return WasmBtor2Spec(
        module=WasmModuleRef(path="test.wasm"),
        scope=AnalysisScope(entry_function=entry),
        question=QuestionSpec(kind=kind, negate=negate),
        assumptions=assumptions,
    )


def _translate(wasm_bytes: bytes, spec: WasmBtor2Spec) -> CompiledArtifact:
    source = load_wasm_source(wasm_bytes)
    ann = _make_annotator()
    return Translator().translate(spec, source, ann)


# Minimal WASM bodies (instruction bytes only, no 'end' — appended below)
_BODY_ADD = b"\x20\x00\x20\x01\x6A\x0B"   # local.get 0; local.get 1; i32.add; end
_BODY_SUB = b"\x20\x00\x20\x01\x6B\x0B"   # local.get 0; local.get 1; i32.sub; end
_BODY_MUL = b"\x20\x00\x20\x01\x6C\x0B"   # local.get 0; local.get 1; i32.mul; end
_BODY_CONST = b"\x41\x2A\x0B"              # i32.const 42; end
_BODY_TRAP = b"\x00\x0B"                   # unreachable; end

_I32 = 0x7F  # WASM i32 type code

_WASM_ADD = _make_wasm([_I32, _I32], [_I32], _BODY_ADD)
_WASM_SUB = _make_wasm([_I32, _I32], [_I32], _BODY_SUB)
_WASM_MUL = _make_wasm([_I32, _I32], [_I32], _BODY_MUL)
_WASM_CONST = _make_wasm([], [_I32], _BODY_CONST)
_WASM_TRAP = _make_wasm([_I32], [_I32], _BODY_TRAP)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


def test_translator_version_exported():
    assert TRANSLATOR_VERSION == "1.0.0"


def test_schema_version_exported():
    assert SCHEMA_VERSION == "1.0.0"


# ---------------------------------------------------------------------------
# translate() returns a well-formed CompiledArtifact
# ---------------------------------------------------------------------------


def test_translate_returns_artifact():
    art = _translate(_WASM_ADD, _make_spec())
    assert isinstance(art, CompiledArtifact)


def test_artifact_pair():
    art = _translate(_WASM_ADD, _make_spec())
    assert art.pair == "wasm-btor2"


def test_artifact_schema_version():
    art = _translate(_WASM_ADD, _make_spec())
    assert art.schema_version == SCHEMA_VERSION


def test_all_layers_present():
    art = _translate(_WASM_ADD, _make_spec())
    expected = {"header", "machine", "library", "dispatch", "init", "constraint", "bad", "binding"}
    assert set(art.layers.keys()) == expected


def test_flattened_nonempty():
    art = _translate(_WASM_ADD, _make_spec())
    assert len(art.flattened) > 0


# ---------------------------------------------------------------------------
# All P4 arithmetic instructions compile without error
# ---------------------------------------------------------------------------


def test_i32_add_compiles():
    _translate(_WASM_ADD, _make_spec())  # no exception


def test_i32_sub_compiles():
    _translate(_WASM_SUB, _make_spec())  # no exception


def test_i32_mul_compiles():
    _translate(_WASM_MUL, _make_spec())  # no exception


def test_i32_const_compiles():
    _translate(_WASM_CONST, _make_spec())  # no exception


# ---------------------------------------------------------------------------
# BTOR2 output is parseable
# ---------------------------------------------------------------------------


def test_flattened_parseable_add():
    art = _translate(_WASM_ADD, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


def test_flattened_parseable_const():
    art = _translate(_WASM_CONST, _make_spec())
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


# ---------------------------------------------------------------------------
# bad layer
# ---------------------------------------------------------------------------


def test_bad_layer_nonempty_reach_trap():
    art = _translate(_WASM_ADD, _make_spec(kind=PropertyKind.REACH_TRAP))
    assert len(art.layers["bad"].body) > 0


def test_bad_layer_contains_bad_node():
    art = _translate(_WASM_TRAP, _make_spec(kind=PropertyKind.REACH_TRAP))
    btor2_text = art.flattened.decode("utf-8")
    assert " bad " in btor2_text


def test_reach_trap_negate_emits_not():
    art = _translate(_WASM_ADD, _make_spec(negate=True))
    bad_body = art.layers["bad"].body.decode("utf-8")
    assert "not" in bad_body


# ---------------------------------------------------------------------------
# Entry function errors
# ---------------------------------------------------------------------------


def test_entry_not_found_raises():
    source = load_wasm_source(_WASM_ADD)
    spec = _make_spec(entry="nonexistent")
    ann = _make_annotator()
    with pytest.raises(ValueError, match="not found"):
        Translator().translate(spec, source, ann)


# ---------------------------------------------------------------------------
# LocalInit assumption emits a constraint
# ---------------------------------------------------------------------------


def test_local_init_constraint_emitted():
    assumption = LocalInit(func_idx=0, local_idx=0, op=Comparison.EQ, value=42)
    spec = _make_spec(assumptions=(assumption,))
    art = _translate(_WASM_ADD, spec)
    constraint_body = art.layers["constraint"].body.decode("utf-8")
    assert "constraint" in constraint_body
