"""The hop interface every pair implements.

A hop carries the three edges of the commuting square that core cares about:
``translate`` (T), ``interpret_out`` (I_out, realized by a solver/dispatch),
and ``lift`` (L). The skeleton defines the *shape*; the per-hop bodies are
``TODO(agent)`` stubs to be filled by the autonomous builder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class NotYetImplemented(NotImplementedError):
    """Raised by stub hop bodies. The F0 gate treats a hop that *imports and
    types* cleanly as F0-passing even while bodies raise this."""


@dataclass
class TranslateResult:
    artifact: Any                       # the reasoning-language artifact (e.g. BTOR2 bytes)
    annotation: dict = field(default_factory=dict)
    path: str = "own"                   # "own" | "machine"  (which reasoning path produced it)


@dataclass
class LiftResult:
    facts: dict = field(default_factory=dict)
    witness: Any = None


class Hop:
    """Base class. Subclasses set the class attributes and implement the
    three methods (or leave them as stubs raising ``NotYetImplemented``)."""

    id: str
    kind: str
    in_lang: str
    out_lang: str

    # ---- the commuting-square edges -------------------------------------
    def translate(self, source: Any, question: dict, *, path: str = "own") -> TranslateResult:
        raise NotYetImplemented(f"{self.id}.translate [TODO(agent)]")

    def lift(self, artifact: Any, raw_solver_result: Any) -> LiftResult:
        raise NotYetImplemented(f"{self.id}.lift [TODO(agent)]")

    # ---- F0 self-description (real; used by the typed gate) -------------
    def describe(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "in_lang": self.in_lang,
            "out_lang": self.out_lang,
            "paths": self.paths(),
        }

    def paths(self) -> tuple[str, ...]:
        return ("own",)
