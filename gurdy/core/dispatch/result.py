"""Raw solver result type used by the dispatch surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VERDICTS = ("reachable", "unreachable", "proved", "unknown", "error")


@dataclass(frozen=True)
class RawSolverResult:
    """The structured shape every solver returns through dispatch.

    ``payload`` is pair-specific: a witness in BTOR2 model format from
    a BTOR2 solver, an SMT-LIB invariant from Spacer, and so on. The
    framework treats it as opaque; the lifter understands it.
    """

    verdict: str
    elapsed: float
    engine: str
    payload: Any = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            object.__setattr__(self, "verdict", "unknown")


__all__ = ["RawSolverResult", "VERDICTS"]
