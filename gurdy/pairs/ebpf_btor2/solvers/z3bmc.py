"""Z3 BMC solver adapter for ebpf-btor2.

Reuses riscv_btor2's btor2_to_z3 backend verbatim — BTOR2 is pair-agnostic.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from gurdy.core.dispatch.backend import InProcessSolverBackend
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.btor2.parser import from_text
from gurdy.core.btor2.btor2_to_z3 import bmc, compile_btor2


@dataclass
class Z3BMCSolver(InProcessSolverBackend):
    name: str = "z3-bmc"

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

        result = from_text(artifact_bytes.decode("utf-8"))
        if result.has_errors():
            return RawSolverResult(
                verdict="error",
                elapsed=time.monotonic() - start,
                engine=self.name,
                reason="BTOR2 parse error: "
                + "; ".join(d.render() for d in result.diagnostics[:3]),
            )

        comp = compile_btor2(result.model)
        bound = getattr(directive, "bound", None)
        if bound is None:
            bound = 1
        try:
            verdict, solver = bmc(comp, int(bound))
        except NotImplementedError as e:
            return RawSolverResult(
                verdict="unknown",
                elapsed=time.monotonic() - start,
                engine=self.name,
                reason=f"unsupported BTOR2 op: {e}",
            )

        payload: Any = None
        if verdict == "reachable" and solver is not None:
            payload = {"witness_text": str(solver.model())}
        return RawSolverResult(
            verdict=verdict,
            elapsed=time.monotonic() - start,
            engine=self.name,
            payload=payload,
        )


__all__ = ["Z3BMCSolver"]
