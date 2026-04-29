"""Bitwuzla wrapper: in-process BMC via the bitwuzla bindings.

Bitwuzla's own Python BTOR2 parser does not handle the model-checking
extensions (init/next/bad/constraint), so we drive the unrolling
explicitly via ``btor2_to_bitwuzla.bmc``. The shape mirrors the z3-bmc
backend in ``btor2_to_z3.py``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from gurdy.core.dispatch.backend import InProcessSolverBackend
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.pairs.riscv_btor2.btor2.parser import from_text
from gurdy.pairs.riscv_btor2.solvers.btor2_to_bitwuzla import bmc, compile_to_z3


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

        bound = getattr(directive, "bound", None)
        if bound is None:
            return RawSolverResult(
                verdict="unknown",
                elapsed=time.monotonic() - start,
                engine=self.name,
                reason="bitwuzla BMC requires bound; AnalysisDirective.bound is None",
            )

        try:
            parsed = from_text(artifact_bytes.decode("utf-8", "replace"))
            comp = compile_to_z3(parsed.model)
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


__all__ = ["BitwuzlaSolver"]
