"""Corpus seed tests for 0017-select-no-trap (P25).

Verifies that the seed task files are internally consistent and that the
BTOR2 reasoning interpreter confirms the expected verdict: reach_trap is
unreachable — executing select(10, 20, 1) never causes a trap.

Module structure:
  func 0 (main, () -> ()): i32.const 10; i32.const 20; i32.const 1; select; drop; end
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_SEED_DIR = (
    Path(__file__).resolve().parents[3]
    / "bench/wasm-btor2/corpus/seed/0017-select-no-trap"
)

_EXPECTED_SHA256 = "766163fbe3e1bc2dba998342c508824fed428a027fb95bccba848618ad615a00"


def _load_wasm() -> bytes:
    return (_SEED_DIR / "module.wasm").read_bytes()


def _load_spec() -> dict:
    return json.loads((_SEED_DIR / "spec.json").read_text())


# ---------------------------------------------------------------------------
# File-shape tests
# ---------------------------------------------------------------------------


def test_module_wasm_exists():
    assert (_SEED_DIR / "module.wasm").is_file()


def test_spec_json_exists():
    assert (_SEED_DIR / "spec.json").is_file()


def test_task_toml_exists():
    assert (_SEED_DIR / "task.toml").is_file()


def test_module_wasm_magic():
    assert _load_wasm()[:4] == b"\x00asm"


def test_module_wasm_version():
    assert _load_wasm()[4:8] == b"\x01\x00\x00\x00"


def test_module_wasm_size():
    assert len(_load_wasm()) == 42


def test_module_wasm_sha256():
    digest = hashlib.sha256(_load_wasm()).hexdigest()
    assert digest == _EXPECTED_SHA256


# ---------------------------------------------------------------------------
# Spec round-trip
# ---------------------------------------------------------------------------


def test_spec_content_hash_matches():
    spec = _load_spec()
    assert spec["fields"]["module"]["content_hash"] == _EXPECTED_SHA256


def test_spec_pair():
    assert _load_spec()["pair"] == "wasm-btor2"


def test_spec_entry_function():
    assert _load_spec()["fields"]["scope"]["entry_function"] == "main"


def test_spec_question_kind():
    assert _load_spec()["fields"]["question"]["kind"] == "reach_trap"


def test_spec_question_negate():
    assert _load_spec()["fields"]["question"]["negate"] is False


# ---------------------------------------------------------------------------
# Decoder instruction-sequence validation
# ---------------------------------------------------------------------------


def test_decoder_instruction_sequence():
    from gurdy.pairs.wasm_btor2.source import load_wasm_source

    src = load_wasm_source(_load_wasm())
    code = src.code_entry(0)
    ops = [ins.op for ins in code.body]
    assert ops == ["i32.const", "i32.const", "i32.const", "select", "drop", "end"]


# ---------------------------------------------------------------------------
# Translation compiles
# ---------------------------------------------------------------------------


def test_translation_compiles():
    from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
    from gurdy.pairs.wasm_btor2.source import load_wasm_source
    from gurdy.pairs.wasm_btor2.spec import WasmBtor2Spec
    from gurdy.pairs.wasm_btor2.translation import SCHEMA_VERSION, Translator

    spec = WasmBtor2Spec.from_jsonable(_load_spec())
    source = load_wasm_source(_load_wasm())
    sidecar = AnnotationSidecar(schema_version=SCHEMA_VERSION, spec_hash="")
    ann = AnnotationEmitter(sidecar)
    art = Translator().translate(spec, source, ann)
    assert art is not None


def test_flattened_parseable():
    from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
    from gurdy.pairs.wasm_btor2.btor2.parser import from_text as btor2_parse
    from gurdy.pairs.wasm_btor2.source import load_wasm_source
    from gurdy.pairs.wasm_btor2.spec import WasmBtor2Spec
    from gurdy.pairs.wasm_btor2.translation import SCHEMA_VERSION, Translator

    spec = WasmBtor2Spec.from_jsonable(_load_spec())
    source = load_wasm_source(_load_wasm())
    sidecar = AnnotationSidecar(schema_version=SCHEMA_VERSION, spec_hash="")
    ann = AnnotationEmitter(sidecar)
    art = Translator().translate(spec, source, ann)
    model = btor2_parse(art.flattened.decode("utf-8")).model
    assert len(model.nodes()) > 0


def test_ite_op_present_in_flattened():
    """select lowering emits 'ite' in BTOR2."""
    from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
    from gurdy.pairs.wasm_btor2.source import load_wasm_source
    from gurdy.pairs.wasm_btor2.spec import WasmBtor2Spec
    from gurdy.pairs.wasm_btor2.translation import SCHEMA_VERSION, Translator

    spec = WasmBtor2Spec.from_jsonable(_load_spec())
    source = load_wasm_source(_load_wasm())
    sidecar = AnnotationSidecar(schema_version=SCHEMA_VERSION, spec_hash="")
    ann = AnnotationEmitter(sidecar)
    art = Translator().translate(spec, source, ann)
    assert "ite" in art.flattened.decode("utf-8")


# ---------------------------------------------------------------------------
# Reasoning interpreter — no trap (module has no params; empty binding)
# ---------------------------------------------------------------------------


def _make_art():
    from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
    from gurdy.pairs.wasm_btor2.source import load_wasm_source
    from gurdy.pairs.wasm_btor2.spec import WasmBtor2Spec
    from gurdy.pairs.wasm_btor2.translation import SCHEMA_VERSION, Translator

    spec = WasmBtor2Spec.from_jsonable(_load_spec())
    source = load_wasm_source(_load_wasm())
    sidecar = AnnotationSidecar(schema_version=SCHEMA_VERSION, spec_hash="")
    ann = AnnotationEmitter(sidecar)
    return Translator().translate(spec, source, ann)


def test_no_trap():
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import (
        Btor2ReasoningInterpreter,
    )

    art = _make_art()
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)
