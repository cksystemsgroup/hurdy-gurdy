"""Alignment oracle for the evm-btor2 pair (P5).

``AlignmentOracle.check`` runs the full translation pipeline and then
exercises the concrete reasoning interpreter up to the spec's BMC bound.
It returns an ``AlignmentResult`` indicating whether the bad property fired
(SAT witness found within bound) or not (UNSAT up to bound).
"""

from __future__ import annotations

from dataclasses import dataclass

from gurdy.core.annotation.sidecar import AnnotationSidecar
from gurdy.core.pair import CompiledArtifact, Layer
from gurdy.pairs.evm_btor2.reasoning_interp import (
    Btor2ReasoningBinding,
    Btor2ReasoningInterpreter,
)
from gurdy.pairs.evm_btor2.translation.translator import translate_bytecode

_DEFAULT_BOUND = 100


@dataclass(frozen=True)
class AlignmentResult:
    """Result of one oracle alignment check.

    ``bad_fired`` is True when the bad property fired within ``bound`` steps.
    ``witness_step`` is the 0-based step index at which bad fired, or None.
    ``btor2_model`` is the BTOR2 text produced by the translator.
    """

    bad_fired: bool
    witness_step: int | None
    btor2_model: str


class AlignmentOracle:
    """Concrete alignment oracle: translate → interpret → report."""

    def check(
        self,
        spec,
        witness_binding: dict | None = None,
    ) -> AlignmentResult:
        """Translate ``spec`` and run the reasoning interpreter.

        ``witness_binding`` is an optional mapping from state symbol to
        initial value (e.g. ``{"calldata": {31: 1}}``), forwarded to
        ``Btor2ReasoningBinding.state_init_by_symbol``.

        The BMC bound comes from ``spec.analysis.bound`` (defaulting to
        ``_DEFAULT_BOUND`` when None).
        """
        bytecode = bytes.fromhex(spec.bytecode.hex)
        btor2_text = translate_bytecode(bytecode, spec)

        body = btor2_text.encode("utf-8")
        artifact = CompiledArtifact(
            pair="evm-btor2",
            layers={"all": Layer(name="all", body=body, content_hash="")},
            annotation=AnnotationSidecar(),
            flattened=body,
            schema_version="1.0.0",
            spec_hash="",
        )

        binding = Btor2ReasoningBinding(
            state_init_by_symbol=witness_binding or {}
        )

        bound = (
            spec.analysis.bound
            if spec.analysis.bound is not None
            else _DEFAULT_BOUND
        )

        trace = Btor2ReasoningInterpreter().run(artifact, binding, max_steps=bound)

        return AlignmentResult(
            bad_fired=trace.bad_fired_at is not None,
            witness_step=trace.bad_fired_at,
            btor2_model=btor2_text,
        )


__all__ = ["AlignmentOracle", "AlignmentResult"]
