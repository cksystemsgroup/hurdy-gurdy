"""Corpus seed tests for 0002-div-trap (P9).

Verifies that the seed task files are internally consistent and that the
BTOR2 reasoning interpreter confirms the expected verdict: reach_trap is
reachable (divisor==0 triggers trap at step 3 within bound 8).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_SEED_DIR = Path(__file__).resolve().parents[3] / "bench/wasm-btor2/corpus/seed/0002-div-trap"


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


def test_spec_json_pair():
    assert _load_spec()["pair"] == "wasm-btor2"


def test_spec_json_entry_function():
    assert _load_spec()["fields"]["scope"]["entry_function"] == "main"


def test_spec_json_question_kind():
    assert _load_spec()["fields"]["question"]["kind"] == "reach_trap"


def test_spec_json_negate_false():
    assert _load_spec()["fields"]["question"]["negate"] is False


def test_spec_json_bound_8():
    assert _load_spec()["fields"]["analysis"]["bound"] == 8


def test_spec_json_content_hash_matches_wasm():
    actual = hashlib.sha256(_load_wasm()).hexdigest()
    recorded = _load_spec()["fields"]["module"]["content_hash"]
    assert actual == recorded, f"content_hash mismatch: {actual!r} != {recorded!r}"


# ---------------------------------------------------------------------------
# Spec round-trip
# ---------------------------------------------------------------------------


def test_spec_from_jsonable_round_trip():
    from gurdy.pairs.wasm_btor2.spec import WasmBtor2Spec

    spec = WasmBtor2Spec.from_jsonable(_load_spec())
    assert spec.pair == "wasm-btor2"
    assert spec.scope.entry_function == "main"
    assert spec.analysis.bound == 8


# ---------------------------------------------------------------------------
# Translation: i32.div_s module compiles and contains sdiv
# ---------------------------------------------------------------------------


def _make_artifact():
    from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
    from gurdy.pairs.wasm_btor2.source import load_wasm_source
    from gurdy.pairs.wasm_btor2.spec import (
        AnalysisScope,
        PropertyKind,
        QuestionSpec,
        WasmBtor2Spec,
        WasmModuleRef,
    )
    from gurdy.pairs.wasm_btor2.translation import SCHEMA_VERSION, Translator

    wasm = _load_wasm()
    source = load_wasm_source(wasm)
    spec = WasmBtor2Spec(
        module=WasmModuleRef(path="module.wasm"),
        scope=AnalysisScope(entry_function="main"),
        question=QuestionSpec(kind=PropertyKind.REACH_TRAP),
    )
    sidecar = AnnotationSidecar(schema_version=SCHEMA_VERSION, spec_hash="")
    emitter = AnnotationEmitter(sidecar)
    return Translator().translate(spec, source, emitter)


def test_artifact_compiles():
    art = _make_artifact()
    assert art is not None


def test_artifact_contains_sdiv():
    art = _make_artifact()
    assert "sdiv" in art.flattened.decode("utf-8")


# ---------------------------------------------------------------------------
# Reasoning interpreter: trap is reachable (divisor==0 → bad_fired at step 3)
# ---------------------------------------------------------------------------


def test_reasoning_interp_zero_divisor_traps():
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _make_artifact()
    # param_0 (dividend) = 42, param_1 (divisor) = 0 → trap
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 42, "local_1": 0})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert any(s.bad_fired for s in rtrace.steps), "expected bad_fired for divisor==0"


def test_reasoning_interp_overflow_traps():
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _make_artifact()
    # INT32_MIN / -1 → signed overflow trap
    rbinding = Btor2ReasoningBinding(
        state_init_by_symbol={"local_0": 0x80000000, "local_1": 0xFFFFFFFF}
    )
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert any(s.bad_fired for s in rtrace.steps), "expected bad_fired for INT32_MIN/-1"


def test_reasoning_interp_nonzero_divisor_no_trap():
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _make_artifact()
    # 10 / 2 = 5, no trap
    rbinding = Btor2ReasoningBinding(state_init_by_symbol={"local_0": 10, "local_1": 2})
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)


def test_reasoning_interp_negative_divisor_no_trap():
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    art = _make_artifact()
    # -10 / -3 = 3 (truncated toward zero), no trap
    rbinding = Btor2ReasoningBinding(
        state_init_by_symbol={"local_0": (-10) & 0xFFFFFFFF, "local_1": (-3) & 0xFFFFFFFF}
    )
    rtrace = Btor2ReasoningInterpreter().run(art, rbinding, max_steps=8)
    assert not any(s.bad_fired for s in rtrace.steps)
