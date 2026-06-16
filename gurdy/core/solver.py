"""The ``SolverBackend`` protocol and the normalized ``Result``
(FRAMEWORK.md §2; SOLVERS.md §3).

A solver is the one component the platform admits may be non-deterministic —
it is the quarantined oracle (SOLVERS.md §1). It only *proposes* a model; the
deterministic core (interpreter + carry-back, checked by the oracle)
*disposes*. Witness checkers, by contrast, sit on the deterministic side and
are a later increment (SOLVERS.md §5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Verdict(str, Enum):
    REACHABLE = "reachable"      # sat — a model exists
    UNREACHABLE = "unreachable"  # unsat / holds-for-all
    UNKNOWN = "unknown"          # gave up (incompleteness)
    RESOURCE_OUT = "resource-out"  # hit a time / memory limit


@dataclass(frozen=True)
class Result:
    verdict: Verdict
    # A concrete input binding / model (an observable->value map), present on
    # REACHABLE. NOT a trusted trace: feed it to the target interpreter to
    # regrow the trace, then carry it back (SOLVERS.md §4).
    model: dict[str, Any] | None = None
    certificate: Any | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


class SolverBackend(Protocol):
    """Decide a question over *all* inputs of an artifact."""

    def decide(self, artifact: bytes, directive: dict[str, Any] | None = None) -> Result:
        ...
