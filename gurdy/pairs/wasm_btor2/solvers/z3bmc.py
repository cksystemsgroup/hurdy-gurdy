"""Z3 BMC solver adapter for ``wasm-btor2``.

Consumes a ``CompiledArtifact`` (its ``flattened`` BTOR2 bytes), runs
bounded model checking via the z3 Python API, and returns a
``RawSolverResult`` with ``verdict ∈ {reachable, unreachable, unknown}``.
A witness text is included in ``payload`` when the verdict is ``reachable``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from gurdy.core.dispatch.backend import InProcessSolverBackend
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.btor2.parser import from_text
from gurdy.pairs.wasm_btor2.solvers.btor2_to_z3 import Z3Backend, compile_btor2
from gurdy.core.btor2._bmc import bmc


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
                reason="failed to parse BTOR2 artifact: "
                + "; ".join(d.render() for d in result.diagnostics[:3]),
            )

        comp = compile_btor2(result.model)
        bound = getattr(directive, "bound", None) or 1
        try:
            verdict, solver = bmc(comp, int(bound), Z3Backend())
        except NotImplementedError as e:
            return RawSolverResult(
                verdict="unknown",
                elapsed=time.monotonic() - start,
                engine=self.name,
                reason=f"unsupported BTOR2 op: {e}",
            )

        payload: Any = None
        if verdict == "reachable" and solver is not None:
            model = solver.model()
            payload = {"witness_text": str(model)}

        return RawSolverResult(
            verdict=verdict,
            elapsed=time.monotonic() - start,
            engine=self.name,
            payload=payload,
        )


__all__ = ["Z3BMCSolver"]
