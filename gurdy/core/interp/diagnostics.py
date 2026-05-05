"""Stable diagnostic codes used by the interpreter framework and the
``check`` tool. Pairs may emit additional codes; these are the
framework-level taxonomy.
"""

from __future__ import annotations

from gurdy.core.diagnostics import Diagnostic, Severity


CODE_INTERPRETER_DIVERGENCE = "interp/divergence"
CODE_INTERPRETER_TIMEOUT = "interp/timeout"
CODE_INTERPRETER_HALTED_EARLY = "interp/halted_early"
CODE_ASSUMPTION_VACUOUS = "check/assumption_vacuous"
CODE_ASSUMPTION_VIOLATED = "check/assumption_violated"
CODE_OBSERVABLE_NEVER_FIRES = "check/observable_never_fires"
CODE_PROPERTY_VIOLATED_CONCRETELY = "check/property_violated_concretely"
CODE_PROPERTY_HOLDS_CONCRETELY = "check/property_holds_concretely"
CODE_PROPERTY_UNSUPPORTED = "check/property_unsupported"
CODE_ASSUMPTION_UNSUPPORTED = "check/assumption_unsupported"


def warning(code: str, message: str, **detail) -> Diagnostic:
    return Diagnostic(
        Severity.WARNING, code, message, detail=detail or None
    )


def info(code: str, message: str, **detail) -> Diagnostic:
    return Diagnostic(
        Severity.INFO, code, message, detail=detail or None
    )


def error(code: str, message: str, **detail) -> Diagnostic:
    return Diagnostic(
        Severity.ERROR, code, message, detail=detail or None
    )


__all__ = [
    "CODE_INTERPRETER_DIVERGENCE",
    "CODE_INTERPRETER_TIMEOUT",
    "CODE_INTERPRETER_HALTED_EARLY",
    "CODE_ASSUMPTION_VACUOUS",
    "CODE_ASSUMPTION_VIOLATED",
    "CODE_OBSERVABLE_NEVER_FIRES",
    "CODE_PROPERTY_VIOLATED_CONCRETELY",
    "CODE_PROPERTY_HOLDS_CONCRETELY",
    "CODE_PROPERTY_UNSUPPORTED",
    "CODE_ASSUMPTION_UNSUPPORTED",
    "warning",
    "info",
    "error",
]
