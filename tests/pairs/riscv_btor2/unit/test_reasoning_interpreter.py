"""Tests for ``Btor2ReasoningInterpreter`` — multi-step BTOR2 evaluator.

Builds tiny BTOR2 artifacts directly (without going through the full
RISC-V translator) and confirms that the multi-step interpreter
applies ``next`` clauses correctly across cycles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from gurdy.core.pair import CompiledArtifact, Layer
from gurdy.core.annotation.sidecar import AnnotationSidecar
from gurdy.pairs.riscv_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
from gurdy.pairs.riscv_btor2.reasoning_interp.interpreter import (
    INTERPRETER_VERSION,
    Btor2ReasoningInterpreter,
)


def _make_artifact(text: str) -> CompiledArtifact:
    body = text.encode("utf-8")
    return CompiledArtifact(
        pair="riscv-btor2",
        layers={"all": Layer(name="all", body=body, content_hash="x")},
        annotation=AnnotationSidecar(),
        flattened=body,
        schema_version="1.0.0",
        spec_hash="x",
    )


def test_pure_counter_advances_each_step():
    # state s; init 0; next s = s + 1.
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
    assert trace.interpreter_version == INTERPRETER_VERSION
    assert len(trace.steps) == 5
    # The state nid is 2; layer "machine" carries it. We record POST-step
    # state, so step 0 = state after the first transition (counter went
    # from 0 to 1).
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
    # Post-step recording: starts at 100, then 101, 102, 103.
    seen = [s.layer_values["machine"][2] for s in trace.steps]
    assert seen == [101, 102, 103]


def test_bad_clause_firing_recorded_at_first_step():
    # state c; init 0; next = c+1; bad: c == 2.
    text = "\n".join([
        "1 sort bitvec 8",
        "2 state 1 c",
        "3 zero 1",
        "4 init 1 2 3",
        "5 one 1",
        "6 add 1 2 5",
        "7 next 1 2 6",
        "8 constd 1 2",
        "9 eq 1 2 8",
        # eq result is bv1 not bv8; rebuild with proper sort.
    ]) + "\n"
    # eq result must be bv1; declare a bv1 sort.
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
    # Post-step recording: c becomes 2 at the end of step 1 (transitioned
    # 0 → 1 in step 0, 1 → 2 in step 1). bad fires there.
    assert trace.bad_fired_at == 1
    assert trace.steps[1].bad_fired
    assert not trace.steps[0].bad_fired
