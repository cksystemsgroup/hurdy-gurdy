"""The one question type — ``(p, φ)`` as data (FRONTIER.md §1.1).

A question is a program and a condition over its observables:
the source language, the observables φ reads, φ's shape, the asker's
assurance floor — and, when the question comes from a benchmark, the
program's identity (an instance name or content digest). Its identity
is the sha256 of its dict with only the fields present, so questions
without a program hash exactly as they always have; ``suite`` and
``origin`` are *record* fields on the books (ledger.py), never part
of question identity.

``why_not`` builds one from its keyword surface; benchmarks carry one
per instance; the frontier derivation joins over recorded ones. One
type, one identity, no parallel vocabularies.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


def question_key(question: dict[str, Any]) -> str:
    """The identity of a question: distinct-question counts dedup on
    it. Hashes the dict with only the fields present."""
    return hashlib.sha256(
        json.dumps(question, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class Question:
    """``(p, φ)``: what is asked, of what, at what floor."""

    source: str
    observables: tuple[str, ...] | None = None
    shape: str | None = None
    floor: str | None = None
    program: str | None = None  # instance name / content digest, when known
    verdict: str | None = None  # a spent verdict the player hands in (cost)

    def asdict(self) -> dict[str, Any]:
        """The ledger dict: only the fields present, observables as a
        list — byte-compatible with every record ever written."""
        d: dict[str, Any] = {"source": self.source}
        if self.observables is not None:
            d["observables"] = list(self.observables)
        if self.shape is not None:
            d["shape"] = self.shape
        if self.floor is not None:
            d["floor"] = self.floor
        if self.program is not None:
            d["program"] = self.program
        if self.verdict is not None:
            d["verdict"] = self.verdict
        return d

    def key(self) -> str:
        return question_key(self.asdict())
