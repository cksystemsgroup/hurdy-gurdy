"""Z3 Spacer (Horn / Fixedpoint) wrapper.

Spacer needs the transition system encoded as Horn clauses, which is
a non-trivial step beyond a BTOR2-to-Z3 BMC unrolling. For v1 we
expose the wrapper but route Spacer requests through BMC by default
when the spec doesn't explicitly require inductive reasoning. The
wrapper returns ``unknown`` with a clear ``reason`` if a true
fixed-point analysis would be required and isn't yet implemented;
this is a known v1 limitation called out in PLAN.md's worked example.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from gurdy.core.dispatch.backend import InProcessSolverBackend
from gurdy.core.dispatch.result import RawSolverResult


@dataclass
class Z3SpacerSolver(InProcessSolverBackend):
    name: str = "z3-spacer"

    def dispatch(self, artifact_bytes: bytes, directive: Any) -> RawSolverResult:
        start = time.monotonic()
        try:
            import z3  # noqa: F401
        except ImportError:
            return RawSolverResult(
                verdict="error",
                elapsed=0.0,
                engine=self.name,
                reason="z3-solver is not installed",
            )
        # v1 limitation: Spacer Horn-clause encoding is not yet wired.
        # For now we report unknown with a structured reason so the
        # LLM can decide to re-spec with engine=z3-bmc.
        return RawSolverResult(
            verdict="unknown",
            elapsed=time.monotonic() - start,
            engine=self.name,
            reason=(
                "z3-spacer Horn-clause encoding is a v1 limitation; use "
                "engine='z3-bmc' for bounded reachability. Inductive "
                "invariants will be wired in a follow-up phase."
            ),
        )


__all__ = ["Z3SpacerSolver"]
