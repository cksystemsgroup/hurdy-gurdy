"""Top-level lifter implementing the framework's ``Lifter`` protocol.

Adapted from gurdy/pairs/riscv_btor2/lift/lift.py (v2-bootstrap).
Routes raw solver verdicts through the right lift path:

- ``reachable`` -> witness replay through the AArch64 simulator.
- ``proved`` -> SMT-LIB invariant with an AArch64 glossary.
- ``unreachable`` / ``unknown`` / ``error`` -> structured pass-through.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.pair import CompiledArtifact
from gurdy.pairs.aarch64_btor2.lift.invariant import LiftedInvariant, lift_invariant
from gurdy.pairs.aarch64_btor2.lift.witness import WitnessTrace, lift_witness
from gurdy.pairs.aarch64_btor2.source.loader import AArch64Source, load_aarch64_binary


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
    def lift(
        self,
        artifact: CompiledArtifact,
        raw: RawSolverResult,
        *,
        source: AArch64Source | None = None,
    ) -> LiftedResult:
        result = LiftedResult(
            pair=artifact.pair,
            verdict=raw.verdict,
            engine=raw.engine,
            elapsed=raw.elapsed,
            reason=raw.reason,
        )
        if raw.verdict == "reachable":
            if source is None:
                source = _try_load_source_from_annotation(artifact)
            if source is not None:
                btor2_text = artifact.flattened.decode("utf-8", "replace")
                result.trace = lift_witness(
                    source,
                    raw.payload if isinstance(raw.payload, dict) else None,
                    btor2_text=btor2_text,
                )
        elif raw.verdict == "proved":
            payload = raw.payload
            if isinstance(payload, dict) and "invariant_text" in payload:
                result.invariant = lift_invariant(str(payload["invariant_text"]))
            elif isinstance(payload, str):
                result.invariant = lift_invariant(payload)
        return result


def _try_load_source_from_annotation(artifact: CompiledArtifact) -> AArch64Source | None:
    # Annotation does not store the binary path; the CLI lift path
    # supplies the source via spec replay. Graceful degradation: verdict
    # and reason pass through without a source-grounded trace.
    return None


lift = Lifter()


__all__ = ["LiftedResult", "Lifter", "lift"]
