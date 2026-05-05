"""Interpreter framework: concrete-input source and reasoning interpreters.

This package adds a third deterministic component alongside the
translator and the lifter: per-pair *interpreters* that run source
programs and reasoning artifacts on concrete inputs. They never
search; they only execute. The five LLM-facing tools that surface
them (``simulate``, ``evaluate``, ``cross_check``, ``replay``,
``check``) live in ``gurdy.core.tools``; this package supplies the
shared types, alignment machinery, and cache key.
"""

from gurdy.core.interp.types import (
    CrossCheckOutcome,
    CrossCheckReport,
    InputBinding,
    JoinedStep,
    JoinedTrace,
    PredicateKind,
    ReasoningBinding,
    ReasoningStep,
    ReasoningTrace,
    SourceStep,
    SourceTrace,
    SpecEvaluation,
    SpecPredicateResult,
)
from gurdy.core.interp.cache import InterpreterCacheKey, build_interpreter_key
from gurdy.core.interp.align import ProjectedField, Projection, align_traces


__all__ = [
    "CrossCheckOutcome",
    "CrossCheckReport",
    "InputBinding",
    "JoinedStep",
    "JoinedTrace",
    "PredicateKind",
    "ReasoningBinding",
    "ReasoningStep",
    "ReasoningTrace",
    "SourceStep",
    "SourceTrace",
    "SpecEvaluation",
    "SpecPredicateResult",
    "InterpreterCacheKey",
    "build_interpreter_key",
    "ProjectedField",
    "Projection",
    "align_traces",
]
