"""Spec for the ``btor2-smtlib`` bridge: just the BMC depth.

Unlike a source-language pair, the *question* (the ``bad`` properties) already
lives in the BTOR2 source. The only thing the caller chooses is how deep to
unroll, plus the solver engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gurdy.core.diagnostics import Diagnostic, Severity
from gurdy.core.spec.base import BaseAnalysisDirective, BaseSpec

PAIR_ID = "btor2-smtlib"


@dataclass(frozen=True)
class Btor2SmtAnalysis(BaseAnalysisDirective):
    engine: str = "z3-smt"


@dataclass(frozen=True)
class Btor2SmtSpec(BaseSpec):
    pair = PAIR_ID

    bound: int = 20
    analysis: Btor2SmtAnalysis = field(default_factory=Btor2SmtAnalysis)

    @classmethod
    def from_jsonable(cls, obj: dict[str, Any]) -> "Btor2SmtSpec":
        f = obj["fields"]
        a = f.get("analysis", {})
        return cls(
            bound=int(f.get("bound", 20)),
            analysis=Btor2SmtAnalysis(
                engine=a.get("engine", "z3-smt"), timeout=a.get("timeout")
            ),
        )


def validate_btor2_smt_spec(spec: Btor2SmtSpec, source: Any):
    if spec.bound < 0:
        return [
            Diagnostic(
                Severity.ERROR, "btor2-smtlib/spec/bad-bound", "bound must be >= 0"
            )
        ]
    return []


__all__ = ["PAIR_ID", "Btor2SmtAnalysis", "Btor2SmtSpec", "validate_btor2_smt_spec"]
