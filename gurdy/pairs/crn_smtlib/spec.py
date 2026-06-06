"""Spec vocabulary for the ``crn-smtlib`` pair: a bounded reachability question.

The question an LLM asks of a CRN: *starting from these initial molecule
counts, can species X reach (>= / == / <=) a threshold within N reaction
firings?* That is the whole spec — the CRN itself is the source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from gurdy.core.diagnostics import Diagnostic, Severity
from gurdy.core.spec.base import BaseAnalysisDirective, BaseSpec

PAIR_ID = "crn-smtlib"
OPS = (">=", "==", "<=")


@dataclass(frozen=True)
class CrnTarget:
    """The reachability goal: ``count[species] <op> value`` at some step."""

    species: str
    op: str = ">="
    value: int = 1


@dataclass(frozen=True)
class CrnAnalysis(BaseAnalysisDirective):
    """Solver selection. ``engine`` defaults to the pair's SMT backend; the
    unrolling depth lives on the spec (``CrnSpec.bound``), not here."""

    engine: str = "z3-smt"


@dataclass(frozen=True)
class CrnSpec(BaseSpec):
    """A bounded-reachability question over a CRN."""

    pair = PAIR_ID

    initial: Mapping[str, int] = field(default_factory=dict)
    target: CrnTarget = field(default_factory=lambda: CrnTarget("X"))
    bound: int = 10
    analysis: CrnAnalysis = field(default_factory=CrnAnalysis)

    @classmethod
    def from_jsonable(cls, obj: dict[str, Any]) -> "CrnSpec":
        f = obj["fields"]
        t = f["target"]
        a = f.get("analysis", {})
        return cls(
            initial={k: int(v) for k, v in f.get("initial", {}).items()},
            target=CrnTarget(
                species=t["species"], op=t.get("op", ">="), value=int(t.get("value", 1))
            ),
            bound=int(f.get("bound", 10)),
            analysis=CrnAnalysis(
                engine=a.get("engine", "z3-smt"), timeout=a.get("timeout")
            ),
        )


def validate_crn_spec(spec: CrnSpec, source: Any):
    """Return diagnostics for ``(spec, crn)``; an empty list means valid."""
    diags: list[Diagnostic] = []
    species = set(getattr(source, "species", ()))
    for s in spec.initial:
        if s not in species:
            diags.append(
                Diagnostic(
                    Severity.ERROR,
                    "crn-smtlib/spec/unknown-initial-species",
                    f"initial references unknown species {s!r}",
                )
            )
    if spec.target.species not in species:
        diags.append(
            Diagnostic(
                Severity.ERROR,
                "crn-smtlib/spec/unknown-target-species",
                f"target species {spec.target.species!r} is not in the CRN",
            )
        )
    if spec.target.op not in OPS:
        diags.append(
            Diagnostic(
                Severity.ERROR,
                "crn-smtlib/spec/bad-op",
                f"target op {spec.target.op!r} not one of {OPS}",
            )
        )
    if spec.bound < 0:
        diags.append(
            Diagnostic(
                Severity.ERROR, "crn-smtlib/spec/bad-bound", "bound must be >= 0"
            )
        )
    return diags


__all__ = ["PAIR_ID", "OPS", "CrnTarget", "CrnAnalysis", "CrnSpec", "validate_crn_spec"]
