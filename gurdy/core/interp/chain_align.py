"""Chain-level alignment: compose per-hop alignment squares (the paste lemma).

:func:`gurdy.core.interp.align.align_traces` checks ONE pair's commuting square
and localizes a divergence to ``(step, label)``. A chain pastes such squares
along a shared edge (``DESIGN_generalized_pairs.md`` Appendix A): the chain
aligns iff every hop's square commutes, and a broken outer rectangle traces to
whichever inner square fails — per-hop error localization, for free
(``DESIGN_generalized_pairs.md`` §6; ``DESIGN_pair_taxonomy.md`` §11, Stage 5).

Not every hop is alignment-capable. An opaque compile hop (e.g. ``c-riscv``,
``reproducible`` tier) has no interpreters/projection, so its faithfulness rests
on its tier (reproducible/checked), not on trace alignment. Such hops are
recorded as :class:`SkippedHop` with a reason rather than silently dropped, so a
chain's alignment coverage is explicit.

This module reuses ``align_traces`` per segment (tagging each trace pair with the
hop id, so the per-segment report is already hop-localized); it adds only the
composition, first-divergence localization, and skipped-hop accounting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from gurdy.core.interp.align import Projection, align_traces
from gurdy.core.interp.types import (
    CrossCheckOutcome,
    CrossCheckReport,
    JoinedTrace,
    ReasoningTrace,
    SourceTrace,
)


@dataclass(frozen=True)
class AlignmentSegment:
    """One alignment-capable hop's square: the hop id plus the two traces and
    the pair-supplied projection that compares them step-by-step."""

    hop: str
    source: SourceTrace
    reasoning: ReasoningTrace
    projection: Projection


@dataclass(frozen=True)
class SkippedHop:
    """A hop the oracle did not align (e.g. an opaque compile hop with no
    interpreters). Its faithfulness rests on its tier, not on trace alignment."""

    hop: str
    reason: str


@dataclass(frozen=True)
class ChainAlignmentReport:
    """Outcome of pasting per-hop squares: ``AGREEMENT`` iff every aligned
    segment commutes; otherwise ``DIVERGENCE`` localized to a hop, step, and
    label. ``segments`` holds the per-hop sub-reports walked (in order, up to
    and including the diverging one); ``skipped`` lists hops not aligned."""

    outcome: CrossCheckOutcome
    segments: tuple[tuple[str, CrossCheckReport], ...]
    skipped: tuple[SkippedHop, ...] = ()
    diverging_hop: str | None = None
    divergence_step: int | None = None
    divergence_label: str | None = None

    @property
    def aligned(self) -> bool:
        return self.outcome is CrossCheckOutcome.AGREEMENT

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "aligned": self.aligned,
            "diverging_hop": self.diverging_hop,
            "divergence_step": self.divergence_step,
            "divergence_label": self.divergence_label,
            "segments": [
                {"hop": hop, "report": rep.to_jsonable()} for hop, rep in self.segments
            ],
            "skipped": [{"hop": s.hop, "reason": s.reason} for s in self.skipped],
        }


def segment_from_joined(
    hop: str, joined: JoinedTrace, projection: Projection
) -> AlignmentSegment:
    """Build an alignment segment from a :class:`JoinedTrace` (what witness
    replay produces): split the joined steps into a source/reasoning trace pair
    tagged with the hop id. Only ``.pair`` and ``.steps`` are read downstream,
    so the other trace envelope fields are left empty."""
    source = SourceTrace(
        pair=hop,
        interpreter_version="",
        inputs_hash="",
        steps=tuple(js.source for js in joined.steps),
    )
    reasoning = ReasoningTrace(
        pair=hop,
        interpreter_version="",
        artifact_hash="",
        bindings_hash="",
        steps=tuple(js.reasoning for js in joined.steps),
    )
    return AlignmentSegment(hop=hop, source=source, reasoning=reasoning, projection=projection)


def align_chain(
    segments: Sequence[AlignmentSegment],
    *,
    skipped: Sequence[SkippedHop] = (),
    max_steps: int | None = None,
) -> ChainAlignmentReport:
    """Walk each hop's alignment square; the chain aligns iff all commute.

    The first diverging segment localizes the failure to ``(hop, step, label)``
    and stops the walk — a broken outer rectangle traces to one inner square
    (the paste lemma). Hops without alignment capability are passed in
    ``skipped`` and recorded with their reason.
    """
    reports: list[tuple[str, CrossCheckReport]] = []
    for seg in segments:
        rep = align_traces(seg.source, seg.reasoning, seg.projection, max_steps=max_steps)
        reports.append((seg.hop, rep))
        if rep.outcome is CrossCheckOutcome.DIVERGENCE:
            return ChainAlignmentReport(
                outcome=CrossCheckOutcome.DIVERGENCE,
                segments=tuple(reports),
                skipped=tuple(skipped),
                diverging_hop=seg.hop,
                divergence_step=rep.divergence_step,
                divergence_label=rep.divergence_label,
            )
    return ChainAlignmentReport(
        outcome=CrossCheckOutcome.AGREEMENT,
        segments=tuple(reports),
        skipped=tuple(skipped),
    )


__all__ = [
    "AlignmentSegment",
    "SkippedHop",
    "ChainAlignmentReport",
    "segment_from_joined",
    "align_chain",
]
