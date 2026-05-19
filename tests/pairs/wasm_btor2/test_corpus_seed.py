"""Corpus seed tests for 0001-i32-add-wrap (P6).

Verifies that the seed task files are internally consistent and that
both the alignment oracle and the BTOR2 reasoning interpreter confirm
the expected verdict: reach_trap is unreachable at bound 8.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

_SEED_DIR = Path(__file__).resolve().parents[3] / "bench/wasm-btor2/corpus/seed/0001-i32-add-wrap"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    wasm = _load_wasm()
    assert wasm[:4] == b"\x00asm", "WASM magic header missing"


def test_module_wasm_version():
    wasm = _load_wasm()
    assert wasm[4:8] == b"\x01\x00\x00\x00", "WASM version must be 1"


def test_module_wasm_size():
    assert len(_load_wasm()) == 42


def test_spec_json_pair():
    spec_obj = _load_spec()
    assert spec_obj["pair"] == "wasm-btor2"


def test_spec_json_entry_function():
    spec_obj = _load_spec()
    assert spec_obj["fields"]["scope"]["entry_function"] == "main"


def test_spec_json_question_kind():
    spec_obj = _load_spec()
    assert spec_obj["fields"]["question"]["kind"] == "reach_trap"


def test_spec_json_negate_false():
    spec_obj = _load_spec()
    assert spec_obj["fields"]["question"]["negate"] is False


def test_spec_json_bound_8():
    spec_obj = _load_spec()
    assert spec_obj["fields"]["analysis"]["bound"] == 8


def test_spec_json_content_hash_matches_wasm():
    wasm = _load_wasm()
    actual = hashlib.sha256(wasm).hexdigest()
    spec_obj = _load_spec()
    recorded = spec_obj["fields"]["module"]["content_hash"]
    assert actual == recorded, f"content_hash mismatch: {actual!r} != {recorded!r}"


# ---------------------------------------------------------------------------
# Spec round-trip
# ---------------------------------------------------------------------------


def test_spec_from_jsonable_round_trip():
    from gurdy.pairs.wasm_btor2.spec import WasmBtor2Spec

    spec_obj = _load_spec()
    spec = WasmBtor2Spec.from_jsonable(spec_obj)
    assert spec.pair == "wasm-btor2"
    assert spec.scope.entry_function == "main"
    assert spec.analysis.bound == 8


# ---------------------------------------------------------------------------
# Oracle alignment: source ↔ BTOR2
# ---------------------------------------------------------------------------


def _load_oracle():
    """Import oracle_align from bench/wasm-btor2/ (directory has a dash, so not a package)."""
    import importlib.util
    import sys as _sys

    oracle_path = Path(__file__).resolve().parents[3] / "bench/wasm-btor2/oracle_align.py"
    mod_name = "oracle_align"
    if mod_name in _sys.modules:
        return _sys.modules[mod_name]
    spec_ = importlib.util.spec_from_file_location(mod_name, oracle_path)
    oracle_mod = importlib.util.module_from_spec(spec_)
    _sys.modules[mod_name] = oracle_mod  # register before exec so @dataclass finds the module
    spec_.loader.exec_module(oracle_mod)
    return oracle_mod


@pytest.mark.parametrize("params", [
    (0, 0),
    (3, 5),
    (1, 0xFFFFFFFF),
    (0x7FFFFFFF, 1),
    (0xFFFFFFFF, 0xFFFFFFFF),
])
def test_oracle_agreement(params):
    oracle_mod = _load_oracle()
    wasm = _load_wasm()
    report = oracle_mod.run_oracle(params, bound=8, wasm_bytes=wasm)
    assert report.agrees, f"alignment diverged for params={params}: {report.summary()}"
    assert report.steps_checked > 0


# ---------------------------------------------------------------------------
# Reasoning interpreter: bad_fired never True at bound 8
# ---------------------------------------------------------------------------


def _make_artifact(wasm: bytes):
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

    source = load_wasm_source(wasm)
    spec = WasmBtor2Spec(
        module=WasmModuleRef(path="module.wasm"),
        scope=AnalysisScope(entry_function="main"),
        question=QuestionSpec(kind=PropertyKind.REACH_TRAP),
    )
    sidecar = AnnotationSidecar(schema_version=SCHEMA_VERSION, spec_hash="")
    emitter = AnnotationEmitter(sidecar)
    return Translator().translate(spec, source, emitter)


@pytest.mark.parametrize("p0,p1", [
    (0, 0),
    (3, 5),
    (1, 0xFFFFFFFF),
    (0x7FFFFFFF, 1),
    (0xFFFFFFFF, 0xFFFFFFFF),
    (0x80000000, 0x80000000),
])
def test_reasoning_interp_no_bad_fired(p0, p1):
    from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
    from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import Btor2ReasoningInterpreter

    wasm = _load_wasm()
    artifact = _make_artifact(wasm)
    rbinding = Btor2ReasoningBinding(
        state_init_by_symbol={"local_0": p0 & 0xFFFFFFFF, "local_1": p1 & 0xFFFFFFFF}
    )
    rtrace = Btor2ReasoningInterpreter().run(artifact, rbinding, max_steps=8)
    assert len(rtrace.steps) == 8
    assert not any(s.bad_fired for s in rtrace.steps), (
        f"bad_fired=True at step for params=({p0:#x}, {p1:#x})"
    )
