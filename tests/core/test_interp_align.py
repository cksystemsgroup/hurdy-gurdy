"""Tests for ``gurdy.core.interp.align.align_traces``."""

from __future__ import annotations

from gurdy.core.interp import (
    CrossCheckOutcome,
    ReasoningStep,
    ReasoningTrace,
    SourceStep,
    SourceTrace,
)
from gurdy.core.interp.align import ProjectedField, align_traces


def _src(steps):
    return SourceTrace(
        pair="_test",
        interpreter_version="1.0.0",
        inputs_hash="i",
        steps=tuple(SourceStep(step=i, location={"pc": pc}) for i, pc in enumerate(steps)),
    )


def _reas(steps):
    return ReasoningTrace(
        pair="_test",
        interpreter_version="1.0.0",
        artifact_hash="a",
        bindings_hash="b",
        steps=tuple(
            ReasoningStep(step=i, layer_values={"m": {1: pc}}) for i, pc in enumerate(steps)
        ),
    )


def _project_pc_only(s, r):
    s_pc = (s.location or {}).get("pc")
    r_pc = (r.layer_values.get("m") or {}).get(1)
    return [
        ProjectedField(
            label="pc",
            source_view=s_pc,
            reasoning_view=r_pc,
            agree=(s_pc == r_pc),
        )
    ]


def test_agreement_full_length():
    rep = align_traces(_src([0, 4, 8, 12]), _reas([0, 4, 8, 12]), _project_pc_only)
    assert rep.outcome is CrossCheckOutcome.AGREEMENT
    assert rep.steps_checked == 4
    assert rep.fields_checked == 4


def test_divergence_first_failing_step():
    rep = align_traces(_src([0, 4, 99, 12]), _reas([0, 4, 8, 12]), _project_pc_only)
    assert rep.outcome is CrossCheckOutcome.DIVERGENCE
    assert rep.divergence_step == 2
    assert rep.divergence_label == "pc"
    assert rep.source_view == 99
    assert rep.reasoning_view == 8


def test_alignment_truncates_to_shorter_trace():
    rep = align_traces(_src([0, 4]), _reas([0, 4, 8]), _project_pc_only)
    assert rep.outcome is CrossCheckOutcome.AGREEMENT
    assert rep.steps_checked == 2


def test_max_steps_caps_alignment():
    rep = align_traces(
        _src([0, 4, 99]),
        _reas([0, 4, 99]),
        _project_pc_only,
        max_steps=2,
    )
    assert rep.outcome is CrossCheckOutcome.AGREEMENT
    assert rep.steps_checked == 2


def test_pair_mismatch_reported():
    a = _src([0])
    b = ReasoningTrace(
        pair="other",
        interpreter_version="1.0.0",
        artifact_hash="a",
        bindings_hash="b",
        steps=(),
    )
    rep = align_traces(a, b, _project_pc_only)
    assert rep.outcome is CrossCheckOutcome.DIVERGENCE
    assert "pair mismatch" in (rep.note or "")


def test_empty_projection_still_advances():
    rep = align_traces(_src([0, 4]), _reas([0, 4]), lambda s, r: [])
    assert rep.outcome is CrossCheckOutcome.AGREEMENT
    assert rep.fields_checked == 0
