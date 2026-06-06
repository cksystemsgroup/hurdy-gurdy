"""The ``Language`` descriptor and registry.

A language is admissible in hurdy-gurdy iff it has a *formal semantics* — a
definable meaning function. This is field-blind: programming languages are one
family among many (see ``DESIGN_pair_taxonomy.md`` §4 for math/physics/chemistry
input languages). The descriptor here is deliberately thin — an id, a ``kind``,
a one-line ``semantics`` note, and (for reasoning languages) the decision
procedures that consume it. It is *not* an institution implementation; it is
supplementary metadata for introspection and route display.

Language descriptors are **optional for routing**: route enumeration
(:mod:`gurdy.core.route`) works off the registered hops' ``in_lang``/``out_lang``
strings directly, so a hop forms a graph edge whether or not its endpoints have
descriptors. By convention a language is registered by the pair/hop for which it
is most canonical (e.g. the ``riscv-btor2`` pair owns ``rv64-elf`` and
``btor2``; the ``c-riscv`` hop owns ``c``).
"""

from __future__ import annotations

from dataclasses import dataclass

KINDS = ("input", "representation", "reasoning")


@dataclass(frozen=True)
class Language:
    """A formal language usable as a hop endpoint.

    ``kind`` is one of:

    - ``input`` — a subject under study (a program, a spec, a Lagrangian, a
      molecule, ...);
    - ``representation`` — an execution / representation target (RV64 ELF,
      WASM, an ODE system, ...);
    - ``reasoning`` — a logic where a solver lives (BTOR2, SMT-LIB, ...).

    ``reasons_via`` names the decision procedures that consume a reasoning
    language; it is empty for the other kinds.
    """

    id: str
    kind: str
    semantics: str = ""
    reasons_via: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(
                f"unknown language kind {self.kind!r} for {self.id!r}; "
                f"expected one of {KINDS}"
            )


_LANGUAGES: dict[str, Language] = {}


def register_language(language: Language) -> None:
    """Register a language descriptor. Idempotent for an identical descriptor;
    re-registering the same id with a *different* descriptor is an error."""
    existing = _LANGUAGES.get(language.id)
    if existing is not None and existing != language:
        raise ValueError(
            f"language {language.id!r} already registered as {existing!r}; "
            f"cannot re-register as {language!r}"
        )
    _LANGUAGES[language.id] = language


def get_language(identifier: str) -> Language:
    try:
        return _LANGUAGES[identifier]
    except KeyError as exc:  # pragma: no cover - exercised via tests
        raise KeyError(f"no language registered with id {identifier!r}") from exc


def list_languages(kind: str | None = None) -> tuple[str, ...]:
    """Sorted ids of registered languages, optionally filtered by ``kind``."""
    if kind is not None and kind not in KINDS:
        raise ValueError(
            f"unknown language kind {kind!r}; expected one of {KINDS}"
        )
    return tuple(
        sorted(i for i, lang in _LANGUAGES.items() if kind is None or lang.kind == kind)
    )


def _clear_languages_for_tests() -> None:
    _LANGUAGES.clear()


__all__ = [
    "KINDS",
    "Language",
    "register_language",
    "get_language",
    "list_languages",
]
