"""The language and pair registry (FRAMEWORK.md §2 "Registry").

Languages own the shared interpreters (ARCHITECTURE.md §6); a pair references
the interpreters of the languages it touches rather than carrying its own.
Every deliverable carries a status (``registered`` / ``partial`` / ``built``).

The registry holds no semantics — it is a typed plug-board. ``decide`` aside,
everything it touches is deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .types import Projection, Trace


class Status(str, Enum):
    REGISTERED = "registered"
    PARTIAL = "partial"
    BUILT = "built"


# A source interpreter maps (program, *) -> Trace; a target interpreter maps a
# realized binding/model -> Trace. Kept as plain callables in MVP-1.
Interpreter = Callable[..., Trace]
Translator = Callable[[Any], bytes]
TargetToSource = Callable[[Trace], Trace]


@dataclass(frozen=True)
class Language:
    id: str
    source_interpreter: Interpreter | None = None
    target_interpreter: Interpreter | None = None
    status: Status = Status.REGISTERED


@dataclass(frozen=True)
class Pair:
    id: str
    source: str  # source language id
    target: str  # target language id
    translator: Translator
    target_to_source: TargetToSource
    projection: Projection
    fidelity: str = "checked"
    translator_version: str = "0"
    status: Status = Status.REGISTERED
    # Resolved from the languages at registration (interpreters are shared,
    # owned by languages — ARCHITECTURE.md §6).
    source_interpreter: Interpreter | None = field(default=None)
    target_interpreter: Interpreter | None = field(default=None)
    # Optional: how this pair wraps a predecessor's output + per-hop params
    # into its own translator input, so the path runner can compose hops with
    # distinct signatures (PATHS.md; FRAMEWORK.md §2). ``(prev_artifact,
    # params) -> program``. ``None`` => the pair is a head / takes bytes as-is.
    compose_input: Callable[[Any, dict], Any] | None = None


_languages: dict[str, Language] = {}
_pairs: dict[str, Pair] = {}


def register_language(language: Language) -> Language:
    if language.id in _languages:
        raise ValueError(f"language already registered: {language.id}")
    _languages[language.id] = language
    return language


def register_pair(pair: Pair) -> Pair:
    if pair.id in _pairs:
        raise ValueError(f"pair already registered: {pair.id}")
    for lang_id in (pair.source, pair.target):
        if lang_id not in _languages:
            raise ValueError(
                f"pair {pair.id}: language {lang_id!r} is not registered "
                "(languages are standalone deliverables, FRAMEWORK.md §1)"
            )
    # Wire the shared interpreters from the languages the pair touches.
    src = _languages[pair.source].source_interpreter
    tgt = _languages[pair.target].target_interpreter
    resolved = Pair(
        **{
            **pair.__dict__,
            "source_interpreter": pair.source_interpreter or src,
            "target_interpreter": pair.target_interpreter or tgt,
        }
    )
    _pairs[pair.id] = resolved
    return resolved


def get_language(language_id: str) -> Language:
    return _languages[language_id]


def get_pair(pair_id: str) -> Pair:
    return _pairs[pair_id]


def list_languages() -> dict[str, Language]:
    return dict(_languages)


def list_pairs() -> dict[str, Pair]:
    return dict(_pairs)


def _reset() -> None:
    """Test helper: clear the registry."""
    _languages.clear()
    _pairs.clear()
