"""Trace / observable / projection types — the contract an interpreter plugs
into (ARCHITECTURE.md §5; FRAMEWORK.md §6 "trace / observable types").

A *behavior* is a ``Trace``: an ordered sequence of post-step ``State``s, each
a mapping from a named observable to a value. A ``Projection`` selects the
subset of observables a pair promises to preserve — the bottom edge of the
commuting square is an equality *up to* this projection.

These types are deliberately minimal and language-agnostic; richer observable
value types are a later increment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

# A post-step state: observable name -> value. Values are kept simple
# (ints/strings) in MVP-1; the framework never interprets them.
State = Mapping[str, Any]
Trace = Sequence[State]


@dataclass(frozen=True)
class Projection:
    """The observable fields a pair preserves (its ``π``)."""

    fields: tuple[str, ...]

    def select(self, state: State) -> dict[str, Any]:
        """Project a single state onto the preserved observables."""
        return {f: state[f] for f in self.fields if f in state}


@dataclass(frozen=True)
class Divergence:
    """A point where two behaviors disagree under a projection."""

    step: int
    field: str
    left: Any
    right: Any

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"diverge@step={self.step} observable={self.field!r} "
            f"left={self.left!r} right={self.right!r}"
        )


@dataclass(frozen=True)
class AlignResult:
    """Outcome of the commuting-square check."""

    ok: bool
    divergence: Divergence | None = None
