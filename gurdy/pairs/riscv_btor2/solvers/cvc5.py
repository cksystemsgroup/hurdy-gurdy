"""cvc5 wrapper. Optional: import-guarded."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from gurdy.core.dispatch.backend import InProcessSolverBackend
from gurdy.core.dispatch.result import RawSolverResult


@dataclass
class Cvc5Solver(InProcessSolverBackend):
    name: str = "cvc5"

    def dispatch(self, artifact_bytes: bytes, directive: Any) -> RawSolverResult:
        start = time.monotonic()
        try:
            import cvc5  # noqa: F401
        except ImportError:
            return RawSolverResult(
                verdict="error",
                elapsed=0.0,
                engine=self.name,
                reason="cvc5 bindings not installed",
            )
        return RawSolverResult(
            verdict="unknown",
            elapsed=time.monotonic() - start,
            engine=self.name,
            reason="cvc5 wrapper plumbing-only at v1; install bindings to enable",
        )


__all__ = ["Cvc5Solver"]
