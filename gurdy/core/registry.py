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
    # Question shapes this language's registered solvers decide (SOLVERS.md
    # §9) — declared by reasoning languages only, e.g. ("reachability",
    # "bounded-unreachability"). Empty = not a reasoning language, or shapes
    # undeclared; the route report treats undeclared as unknown, not false.
    question_shapes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pair:
    id: str
    source: str  # source language id
    target: str  # target language id
    translator: Translator
    target_to_source: TargetToSource
    projection: Projection
    fidelity: str = "checked"
    # Square direction (direction.py): "exact" — the square is the equality
    # I_s(p) ≡_π Λ(I_t(T(p))) — or "over" — the pair is an over-approximating
    # abstraction, I_s(p) ⊑_π Λ(I_t(T(p))), checked as an exact square along
    # the pair's witness embedding. Protected like π (SCALING.md §9).
    direction: str = "exact"
    translator_version: str = "0"
    status: Status = Status.REGISTERED
    # Resolved from the languages at registration (interpreters are shared,
    # owned by languages — ARCHITECTURE.md §6).
    source_interpreter: Interpreter | None = field(default=None)
    target_interpreter: Interpreter | None = field(default=None)
    # Optional: how this pair wraps a predecessor's output + per-hop params
    # into its own translator input, so the route runner can compose hops with
    # distinct signatures (ROUTES.md; FRAMEWORK.md §2). ``(prev_artifact,
    # params) -> program``. ``None`` => the pair is a head / takes bytes as-is.
    compose_input: Callable[[Any, dict], Any] | None = None
    # Optional construct-coverage inventory: {construct name -> probe program}
    # (BENCHMARKS.md §2). Lets the coverage harness measure the pair.
    probes: dict[str, Any] | None = None
    # Optional decidable square oracle, ``program -> AlignResult``: runs
    # I_s(p) =_pi L(I_t(T(p))) for one program (FRAMEWORK.md §2). Present on
    # checked-grade pairs; lets the coverage harness measure Definition 4.6's
    # accepted-AND-faithful conjunction instead of acceptance alone.
    square: Callable[[Any], Any] | None = None
    # The primary semantic artifact the translator derives from (the
    # provenance vocabulary of tools/provenance.py / SCALING.md §9, e.g.
    # "riscv-prose-manual" vs "riscv-sail-model"): what branch corroboration
    # actually rests on — two legs sharing an artifact corroborate less than
    # their count suggests. Declared, protected like π (anchors are SCALING
    # §9 protected invariants); None = undeclared, which the trust advisor
    # reports as unknown independence, never as independent.
    semantic_artifact: str | None = None


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


def attach_square(pair_id: str, square: Callable[[Any], Any]) -> Pair:
    """Wire a pair's decidable square oracle after registration.

    Pair modules define ``square()`` below their ``register_pair`` call (the
    oracle reads the resolved pair back from the registry), so the plug-board
    lets them attach it once defined. Idempotent per pair; the stored Pair is
    replaced (it is frozen) with a copy carrying the oracle.
    """
    pair = _pairs[pair_id]
    resolved = Pair(**{**pair.__dict__, "square": square})
    _pairs[pair_id] = resolved
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
