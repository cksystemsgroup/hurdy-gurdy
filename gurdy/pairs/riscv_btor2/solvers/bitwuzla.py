"""Bitwuzla wrapper. Optional: import-guarded."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from gurdy.core.dispatch.backend import InProcessSolverBackend
from gurdy.core.dispatch.result import RawSolverResult


@dataclass
class BitwuzlaSolver(InProcessSolverBackend):
    name: str = "bitwuzla"

    def dispatch(self, artifact_bytes: bytes, directive: Any) -> RawSolverResult:
        start = time.monotonic()
        try:
            import bitwuzla  # noqa: F401
        except ImportError:
            return RawSolverResult(
                verdict="error",
                elapsed=0.0,
                engine=self.name,
                reason="bitwuzla bindings not installed",
            )
        # The bitwuzla bindings expose a BTOR2 parser directly. Without
        # a working install in the test environment we provide the
        # plumbing but report unknown when called; future revisions
        # plug the real parser/runner in here.
        return RawSolverResult(
            verdict="unknown",
            elapsed=time.monotonic() - start,
            engine=self.name,
            reason="bitwuzla wrapper plumbing-only at v1; install bindings to enable",
        )


__all__ = ["BitwuzlaSolver"]
