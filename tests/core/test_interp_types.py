"""Tests for ``gurdy.core.interp.types`` and ``cache``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from gurdy.core.interp import (
    CrossCheckOutcome,
    CrossCheckReport,
    InputBinding,
    JoinedStep,
    JoinedTrace,
    PredicateKind,
    ReasoningBinding,
    ReasoningStep,
    ReasoningTrace,
    SourceStep,
    SourceTrace,
    SpecEvaluation,
    SpecPredicateResult,
    build_interpreter_key,
)


@dataclass(frozen=True)
class _Inp(InputBinding):
    pair: ClassVar[str] = "_test"
    a: int = 0
    b: tuple[int, ...] = ()


@dataclass(frozen=True)
class _ReasInp(ReasoningBinding):
    pair: ClassVar[str] = "_test"
    initial_state: tuple[tuple[int, int], ...] = ()


def test_input_binding_hash_is_deterministic_under_field_order():
    one = _Inp(a=5, b=(1, 2, 3))
    two = _Inp(a=5, b=(1, 2, 3))
    assert one.inputs_hash() == two.inputs_hash()


def test_input_binding_hash_differs_with_value():
    a = _Inp(a=5)
    b = _Inp(a=6)
    assert a.inputs_hash() != b.inputs_hash()


def test_reasoning_binding_hash_is_deterministic():
    a = _ReasInp(initial_state=((1, 7), (2, 9)))
    b = _ReasInp(initial_state=((1, 7), (2, 9)))
    assert a.bindings_hash() == b.bindings_hash()


def test_source_trace_jsonable_roundtrip_keys():
    trace = SourceTrace(
        pair="_test",
        interpreter_version="1.0.0",
        inputs_hash="abc",
        steps=(
            SourceStep(step=0, location={"pc": 0x1000}, deltas={"x1": 5}),
            SourceStep(step=1, location={"pc": 0x1004}, deltas=None, halted=False),
        ),
        final_state={"x1": 5, "pc": 0x1004},
        halted=False,
    )
    j = trace.to_jsonable()
    assert j["pair"] == "_test"
    assert j["steps"][0]["step"] == 0
    assert j["steps"][1]["halted"] is False


def test_reasoning_trace_jsonable_step_keys_string():
    rt = ReasoningTrace(
        pair="_test",
        interpreter_version="1.0.0",
        artifact_hash="art",
        bindings_hash="bnd",
        steps=(
            ReasoningStep(step=0, layer_values={"machine": {7: 0xFF}}),
        ),
    )
    j = rt.to_jsonable()
    assert "7" in j["steps"][0]["layer_values"]["machine"]


def test_joined_trace_round_trip():
    j = JoinedTrace(
        pair="_test",
        inputs_hash="i",
        artifact_hash="a",
        steps=(
            JoinedStep(
                step=0,
                source=SourceStep(step=0),
                reasoning=ReasoningStep(step=0),
            ),
        ),
    )
    assert j.to_jsonable()["steps"][0]["step"] == 0


def test_cross_check_report_predicates():
    ok = CrossCheckReport(
        pair="_test", outcome=CrossCheckOutcome.AGREEMENT, steps_checked=4
    )
    bad = CrossCheckReport(
        pair="_test",
        outcome=CrossCheckOutcome.DIVERGENCE,
        steps_checked=2,
        divergence_step=2,
        divergence_label="x5",
        source_view=10,
        reasoning_view=11,
    )
    assert ok.agrees and not bad.agrees
    assert bad.to_jsonable()["divergence_step"] == 2


def test_spec_evaluation_serialization():
    se = SpecEvaluation(
        pair="_test",
        inputs_hash="h",
        steps_executed=10,
        halted=False,
        observables=(
            SpecPredicateResult(
                name="reg_x5_at_pc_0x1000",
                kind=PredicateKind.OBSERVABLE,
                values=((3, 0xFF),),
            ),
        ),
        property_result=SpecPredicateResult(
            name="bad",
            kind=PredicateKind.PROPERTY,
            holds=True,
        ),
    )
    j = se.to_jsonable()
    assert j["observables"][0]["name"] == "reg_x5_at_pc_0x1000"
    assert j["property"]["holds"] is True


def test_interpreter_cache_key_digest_stable():
    k1 = build_interpreter_key(
        pair="x",
        interpreter_version="1.0.0",
        role="source",
        inputs_hash="abc",
        max_steps=4,
    )
    k2 = build_interpreter_key(
        pair="x",
        interpreter_version="1.0.0",
        role="source",
        inputs_hash="abc",
        max_steps=4,
    )
    assert k1.digest() == k2.digest()


def test_interpreter_cache_key_changes_on_field_change():
    k1 = build_interpreter_key(
        pair="x", interpreter_version="1.0.0", role="source", max_steps=4
    )
    k2 = build_interpreter_key(
        pair="x", interpreter_version="1.0.1", role="source", max_steps=4
    )
    assert k1.digest() != k2.digest()
