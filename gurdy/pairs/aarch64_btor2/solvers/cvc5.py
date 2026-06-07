"""cvc5 wrapper: in-process BMC via the cvc5 bindings.

Mirrors the bitwuzla wrapper. cvc5's Python bindings don't natively
consume BTOR2; the unrolling is done via the shared ``_bmc`` driver
with a cvc5 ``Backend`` adapter.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from gurdy.core.dispatch.backend import InProcessSolverBackend
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.btor2.parser import from_text
from gurdy.core.btor2.btor2_to_cvc5 import bmc, compile_btor2


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

        bound = getattr(directive, "bound", None)
        if bound is None:
            return RawSolverResult(
                verdict="unknown",
                elapsed=time.monotonic() - start,
                engine=self.name,
                reason="cvc5 BMC requires bound; AnalysisDirective.bound is None",
            )

        try:
            parsed = from_text(artifact_bytes.decode("utf-8", "replace"))
            comp = compile_btor2(parsed.model)
            verdict, _ = bmc(comp, int(bound))
        except Exception as e:
            return RawSolverResult(
                verdict="error",
                elapsed=time.monotonic() - start,
                engine=self.name,
                reason=f"{type(e).__name__}: {e}",
            )

        return RawSolverResult(
            verdict=verdict,
            elapsed=time.monotonic() - start,
            engine=self.name,
            reason=None if verdict != "unknown" else "solver returned unknown",
        )


__all__ = ["Cvc5Solver"]
