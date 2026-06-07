"""Tests for ``Btor2ReasoningInterpreter`` — wasm-btor2 multi-step BTOR2 evaluator.

Builds tiny BTOR2 artifacts directly (without going through the WASM
translator) and confirms that the multi-step interpreter applies
``next`` clauses correctly across cycles, and that PAIR_ID and
INTERPRETER_VERSION are wasm-specific.
"""

from __future__ import annotations

from gurdy.core.pair import CompiledArtifact, Layer
from gurdy.core.annotation.sidecar import AnnotationSidecar
from gurdy.pairs.wasm_btor2.reasoning_interp import (
    Btor2ReasoningBinding,
    Btor2ReasoningInterpreter,
    INTERPRETER_VERSION,
)
from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import PAIR_ID


def _make_artifact(text: str) -> CompiledArtifact:
    body = text.encode("utf-8")
    return CompiledArtifact(
        pair="wasm-btor2",
        layers={"all": Layer(name="all", body=body, content_hash="x")},
        annotation=AnnotationSidecar(),
        flattened=body,
        schema_version="1.0.0",
        spec_hash="x",
    )


def test_pair_id_is_wasm():
    assert PAIR_ID == "wasm-btor2"


def test_interpreter_version_exported():
    interp = Btor2ReasoningInterpreter()
    assert interp.version == INTERPRETER_VERSION
    assert INTERPRETER_VERSION == "1.1.0"


def test_pure_counter_advances_each_step():
    text = "\n".join([
        "1 sort bitvec 8",
        "2 state 1 counter",
        "3 zero 1",
        "4 init 1 2 3",
        "5 one 1",
        "6 add 1 2 5",
        "7 next 1 2 6",
    ]) + "\n"
    art = _make_artifact(text)
    interp = Btor2ReasoningInterpreter()
    trace = interp.run(art, Btor2ReasoningBinding(), max_steps=5)
    assert trace.pair == "wasm-btor2"
    assert trace.interpreter_version == INTERPRETER_VERSION
    assert len(trace.steps) == 5
    # POST-step recording: step 0 = after first transition (0 → 1).
    seen = [s.layer_values["machine"][2] for s in trace.steps]
    assert seen == [1, 2, 3, 4, 5]


def test_state_init_by_symbol_overrides_init_clause():
    text = "\n".join([
        "1 sort bitvec 8",
        "2 state 1 counter",
        "3 zero 1",
        "4 init 1 2 3",
        "5 one 1",
        "6 add 1 2 5",
        "7 next 1 2 6",
    ]) + "\n"
    art = _make_artifact(text)
    interp = Btor2ReasoningInterpreter()
    binding = Btor2ReasoningBinding(state_init_by_symbol={"counter": 100})
    trace = interp.run(art, binding, max_steps=3)
    seen = [s.layer_values["machine"][2] for s in trace.steps]
    assert seen == [101, 102, 103]


def test_bad_clause_fires_at_correct_step():
    # state c (bv8); init 0; next = c+1; bad when c == 2 (post-step).
    text = "\n".join([
        "1 sort bitvec 1",
        "2 sort bitvec 8",
        "3 state 2 c",
        "4 zero 2",
        "5 init 2 3 4",
        "6 one 2",
        "7 add 2 3 6",
        "8 next 2 3 7",
        "9 constd 2 2",
        "10 eq 1 3 9",
        "11 bad 10",
    ]) + "\n"
    art = _make_artifact(text)
    interp = Btor2ReasoningInterpreter()
    trace = interp.run(art, Btor2ReasoningBinding(), max_steps=5)
    # c: 0→1 (step 0), 1→2 (step 1); bad fires at step 1.
    assert trace.bad_fired_at == 1
    assert trace.steps[1].bad_fired
    assert not trace.steps[0].bad_fired


def test_no_bad_clause_no_firing():
    text = "\n".join([
        "1 sort bitvec 8",
        "2 state 1 x",
        "3 zero 1",
        "4 init 1 2 3",
        "5 one 1",
        "6 add 1 2 5",
        "7 next 1 2 6",
    ]) + "\n"
    art = _make_artifact(text)
    interp = Btor2ReasoningInterpreter()
    trace = interp.run(art, Btor2ReasoningBinding(), max_steps=4)
    assert trace.bad_fired_at is None
    assert all(not s.bad_fired for s in trace.steps)


def test_input_per_step_feeds_into_state():
    # state s; input i; next s = s + i.  Feed i=10 at step 0, i=1 at step 1.
    text = "\n".join([
        "1 sort bitvec 8",
        "2 state 1 acc",
        "3 zero 1",
        "4 init 1 2 3",
        "5 input 1 delta",
        "6 add 1 2 5",
        "7 next 1 2 6",
    ]) + "\n"
    art = _make_artifact(text)
    interp = Btor2ReasoningInterpreter()
    binding = Btor2ReasoningBinding(
        input_per_step_by_symbol=[{"delta": 10}, {"delta": 1}]
    )
    trace = interp.run(art, binding, max_steps=3)
    # step 0: acc 0+10=10; step 1: 10+1=11; step 2: 11+0=11 (no more inputs).
    seen = [s.layer_values["machine"][2] for s in trace.steps]
    assert seen == [10, 11, 11]


def test_from_jsonable_round_trip():
    obj = {
        "state_init_by_symbol": {"pc": 0},
        "input_per_step_by_symbol": [{"x": 1}, {"x": 2}],
    }
    b = Btor2ReasoningBinding.from_jsonable(obj)
    assert b.state_init_by_symbol == {"pc": 0}
    assert b.input_per_step_by_symbol == ({"x": 1}, {"x": 2})
    assert b.pair == "wasm-btor2"


def test_zero_steps_returns_empty_trace():
    text = "1 sort bitvec 8\n2 state 1 s\n"
    art = _make_artifact(text)
    interp = Btor2ReasoningInterpreter()
    trace = interp.run(art, Btor2ReasoningBinding(), max_steps=0)
    assert trace.steps == ()
    assert trace.bad_fired_at is None


def test_btor2_subpackage_is_independent():
    from gurdy.core.btor2.parser import from_text
    from gurdy.core.btor2.evaluator import evaluate
    from gurdy.core.btor2.printer import to_text

    src = "1 sort bitvec 32\n2 state 1 val\n3 zero 1\n4 init 1 2 3\n"
    result = from_text(src)
    assert not result.has_errors()
    vals = evaluate(result.model, bindings={})
    assert vals[2] == 0
    out = to_text(result.model)
    assert "sort bitvec 32" in out


def test_artifact_hash_in_trace():
    text = "1 sort bitvec 8\n2 state 1 s\n3 zero 1\n4 init 1 2 3\n5 one 1\n6 add 1 2 5\n7 next 1 2 6\n"
    art = _make_artifact(text)
    interp = Btor2ReasoningInterpreter()
    trace = interp.run(art, Btor2ReasoningBinding(), max_steps=1)
    import hashlib
    expected = hashlib.sha256(text.encode()).hexdigest()
    assert trace.artifact_hash == expected
