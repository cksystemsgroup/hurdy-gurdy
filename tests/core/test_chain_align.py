"""Tests for the chain alignment oracle (gurdy.core.interp.chain_align)."""

from __future__ import annotations

from gurdy.core.interp.align import ProjectedField
from gurdy.core.interp.chain_align import (
    AlignmentSegment,
    SkippedHop,
    align_chain,
    segment_from_joined,
)
from gurdy.core.interp.types import (
    CrossCheckOutcome,
    JoinedStep,
    JoinedTrace,
    ReasoningStep,
    ReasoningTrace,
    SourceStep,
    SourceTrace,
)


def _proj(s, r):
    sv = s.location["v"]
    rv = r.layer_values["L"][0]
    return [ProjectedField(label="v", source_view=sv, reasoning_view=rv, agree=(sv == rv))]


def _segment(hop, pairs):
    src = SourceTrace(
        pair=hop,
        interpreter_version="",
        inputs_hash="",
        steps=tuple(SourceStep(step=i, location={"v": a}) for i, (a, _b) in enumerate(pairs)),
    )
    rsn = ReasoningTrace(
        pair=hop,
        interpreter_version="",
        artifact_hash="",
        bindings_hash="",
        steps=tuple(ReasoningStep(step=i, layer_values={"L": {0: b}}) for i, (_a, b) in enumerate(pairs)),
    )
    return AlignmentSegment(hop=hop, source=src, reasoning=rsn, projection=_proj)


def test_single_segment_agreement():
    rep = align_chain([_segment("h1", [(1, 1), (2, 2), (3, 3)])])
    assert rep.aligned is True
    assert rep.outcome is CrossCheckOutcome.AGREEMENT
    assert rep.diverging_hop is None
    assert [h for h, _ in rep.segments] == ["h1"]


def test_single_segment_divergence_localizes_step_and_label():
    rep = align_chain([_segment("h1", [(1, 1), (2, 9), (3, 3)])])  # step 1 differs
    assert rep.aligned is False
    assert rep.diverging_hop == "h1"
    assert rep.divergence_step == 1
    assert rep.divergence_label == "v"


def test_first_diverging_hop_wins_and_stops_the_walk():
    good = _segment("h1", [(1, 1), (2, 2)])
    bad = _segment("h2", [(5, 5), (6, 99)])  # diverges at step 1
    later = _segment("h3", [(0, 123)])  # would also diverge, but is never reached
    rep = align_chain([good, bad, later])
    assert rep.diverging_hop == "h2"
    assert rep.divergence_step == 1
    assert [h for h, _ in rep.segments] == ["h1", "h2"]  # h3 not walked


def test_skipped_hops_recorded():
    rep = align_chain([_segment("h1", [(1, 1)])], skipped=[SkippedHop(hop="c0", reason="opaque")])
    assert rep.aligned is True
    assert [(s.hop, s.reason) for s in rep.skipped] == [("c0", "opaque")]


def test_segment_from_joined_trace():
    joined = JoinedTrace(
        pair="h",
        inputs_hash="",
        artifact_hash="",
        steps=(
            JoinedStep(
                step=0,
                source=SourceStep(step=0, location={"v": 7}),
                reasoning=ReasoningStep(step=0, layer_values={"L": {0: 7}}),
            ),
            JoinedStep(
                step=1,
                source=SourceStep(step=1, location={"v": 7}),
                reasoning=ReasoningStep(step=1, layer_values={"L": {0: 8}}),  # diverge
            ),
        ),
    )
    rep = align_chain([segment_from_joined("h", joined, _proj)])
    assert rep.diverging_hop == "h"
    assert rep.divergence_step == 1
    assert rep.divergence_label == "v"


def test_report_is_jsonable():
    rep = align_chain(
        [_segment("h1", [(1, 1), (2, 9)])], skipped=[SkippedHop("c0", "opaque")]
    )
    j = rep.to_jsonable()
    assert j["aligned"] is False
    assert j["diverging_hop"] == "h1"
    assert j["divergence_step"] == 1
    assert j["skipped"] == [{"hop": "c0", "reason": "opaque"}]
    assert j["segments"][0]["hop"] == "h1"
