"""Spec validation harness.

Pairs supply a ``SpecValidator`` callable that takes
``(spec, source) -> Iterable[Diagnostic]``. The framework collects the
diagnostics and exposes them through the spec validation entry point.
"""

from __future__ import annotations

from typing import Iterable, Protocol

from gurdy.core.diagnostics import Diagnostic, DiagnosticBag
from gurdy.core.spec.base import BaseSpec


class SpecValidator(Protocol):
    """Validates a pair's spec against a loaded source."""

    def __call__(self, spec: BaseSpec, source: object) -> Iterable[Diagnostic]: ...


def validate(
    spec: BaseSpec, source: object, validator: SpecValidator
) -> DiagnosticBag:
    bag = DiagnosticBag()
    bag.extend(validator(spec, source))
    return bag


__all__ = ["SpecValidator", "validate"]
