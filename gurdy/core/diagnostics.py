"""Structured diagnostics shared across the framework and pairs."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Iterable


class Severity(str, enum.Enum):
    """Diagnostic severity. String values keep JSON-friendly serialization."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


@dataclass(frozen=True)
class Diagnostic:
    """A single diagnostic record.

    `code` is a stable identifier (e.g. ``E001``, ``riscv-btor2/decode/0001``)
    that consumers can match against; `message` is a human-readable description.
    `location` is an opaque token (path, PC, AST node, ...) interpreted by
    whoever rendered it.
    """

    severity: Severity
    code: str
    message: str
    location: str | None = None
    detail: Mapping_str_Any | None = None  # type: ignore[name-defined]

    def __post_init__(self) -> None:  # pragma: no cover - trivial
        # Allow plain dicts; freeze nothing — consumers shouldn't mutate.
        pass

    def render(self) -> str:
        head = f"[{self.severity.value}] {self.code}"
        if self.location:
            head += f" at {self.location}"
        return f"{head}: {self.message}"

    def is_error(self) -> bool:
        return self.severity in (Severity.ERROR, Severity.FATAL)


# Help out static analysis without dragging Mapping into the public namespace
# when only used as a frozen-dataclass field hint.
from typing import Mapping  # noqa: E402

Mapping_str_Any = Mapping[str, Any]


@dataclass
class DiagnosticBag:
    """A mutable collection of diagnostics with convenience predicates."""

    diagnostics: list[Diagnostic] = field(default_factory=list)

    def add(self, diag: Diagnostic) -> None:
        self.diagnostics.append(diag)

    def extend(self, diags: Iterable[Diagnostic]) -> None:
        self.diagnostics.extend(diags)

    def has_errors(self) -> bool:
        return any(d.is_error() for d in self.diagnostics)

    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.is_error()]

    def render(self) -> str:
        return "\n".join(d.render() for d in self.diagnostics)

    def __iter__(self):
        return iter(self.diagnostics)

    def __len__(self) -> int:
        return len(self.diagnostics)

    def __bool__(self) -> bool:
        return bool(self.diagnostics)


__all__ = ["Severity", "Diagnostic", "DiagnosticBag"]
