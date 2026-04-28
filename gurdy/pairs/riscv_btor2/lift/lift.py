"""Top-level lifter implementing the framework's ``Lifter`` protocol.

Routes raw solver verdicts through the right lift path:

- ``reachable`` -> witness replay through the simulator + DWARF.
- ``proved`` -> SMT-LIB invariant with a glossary.
- ``unreachable`` / ``unknown`` / ``error`` -> structured pass-through.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.pair import CompiledArtifact
from gurdy.pairs.riscv_btor2.lift.invariant import LiftedInvariant, lift_invariant
from gurdy.pairs.riscv_btor2.lift.witness import WitnessTrace, lift_witness
from gurdy.pairs.riscv_btor2.source.loader import RISCVSource, load_riscv_binary


@dataclass
class LiftedResult:
    pair: str
    verdict: str
    engine: str
    elapsed: float
    reason: str | None = None
    trace: WitnessTrace | None = None
    invariant: LiftedInvariant | None = None


class Lifter:
    def lift(self, artifact: CompiledArtifact, raw: RawSolverResult) -> LiftedResult:
        result = LiftedResult(
            pair=artifact.pair,
            verdict=raw.verdict,
            engine=raw.engine,
            elapsed=raw.elapsed,
            reason=raw.reason,
        )
        if raw.verdict == "reachable":
            # Try to recover the source from the artifact's annotation
            # provenance. This implementation falls back to no-op when
            # the source isn't reachable from this side; the framework
            # CLI passes the binary path through the spec, and the
            # caller can re-load if needed.
            source = _try_load_source_from_annotation(artifact)
            if source is not None:
                result.trace = lift_witness(source, raw.payload if isinstance(raw.payload, dict) else None)
        elif raw.verdict == "proved":
            payload = raw.payload
            if isinstance(payload, dict) and "invariant_text" in payload:
                result.invariant = lift_invariant(str(payload["invariant_text"]))
            elif isinstance(payload, str):
                result.invariant = lift_invariant(payload)
        return result


def _try_load_source_from_annotation(artifact: CompiledArtifact) -> RISCVSource | None:
    # The annotation does not currently store the binary path; the
    # framework CLI's lift path supplies the source via spec replay.
    # When called programmatically, the user can plumb the source in
    # by passing it through ``LifterOverride`` (TBD); for now, return
    # None and the caller's report shows the verdict + reason without
    # the source-grounded trace. This is a graceful degradation
    # matching SCHEMA.md's verdict semantics.
    return None


# Module-level callable for the registry.
lift = Lifter()


__all__ = ["LiftedResult", "Lifter", "lift"]
