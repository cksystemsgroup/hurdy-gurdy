"""CRN model and parser — the source loader for the ``crn-smtlib`` pair.

A chemical reaction network: species + reactions, read under discrete
**population (Petri-net) semantics** (integer molecule counts; a reaction fires
when its reactants are available, consuming them and producing its products).

Text format — one reaction per line, ``#`` starts a comment::

    # interconversion
    r_fwd: A -> B          # optional ``name:`` prefix; coefficients default to 1
    B -> A
    2 A -> C               # stoichiometric coefficient
    -> A                   # inflow  (no reactants)
    A ->                   # outflow (no products)

Species are inferred from the reactions (declared in sorted order, so the
encoding is independent of mention order). See ``SCHEMA.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TERM = re.compile(r"\A(?:(\d+)\s*\*?\s*)?([A-Za-z_][A-Za-z0-9_]*)\Z")


class CrnParseError(ValueError):
    """Malformed CRN text / outside the supported format."""


@dataclass(frozen=True)
class Reaction:
    """One reaction: ``name`` plus reactant and product ``(species, coeff)`` lists."""

    name: str
    reactants: tuple[tuple[str, int], ...]
    products: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class CrnModel:
    """A chemical reaction network: a sorted species tuple and ordered reactions."""

    species: tuple[str, ...]
    reactions: tuple[Reaction, ...]


def _parse_side(text: str, lineno: int) -> tuple[tuple[str, int], ...]:
    text = text.strip()
    if not text:
        return ()
    terms: list[tuple[str, int]] = []
    for raw_term in text.split("+"):
        term = raw_term.strip()
        m = _TERM.match(term)
        if not m:
            raise CrnParseError(f"line {lineno}: bad term {term!r}")
        coeff = int(m.group(1)) if m.group(1) else 1
        if coeff <= 0:
            raise CrnParseError(f"line {lineno}: non-positive coefficient in {term!r}")
        terms.append((m.group(2), coeff))
    return tuple(terms)


def parse_crn(payload: bytes | str | None) -> CrnModel:
    """Parse CRN text (bytes or str) into a :class:`CrnModel`. Raises
    :class:`CrnParseError` on malformed input."""
    if payload is None:
        raise CrnParseError("no CRN source provided")
    text = (
        payload.decode("utf-8")
        if isinstance(payload, (bytes, bytearray))
        else str(payload)
    )

    reactions: list[Reaction] = []
    species: set[str] = set()
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name = ""
        if ":" in line:
            name, line = (p.strip() for p in line.split(":", 1))
        if "->" not in line:
            raise CrnParseError(f"line {lineno}: no '->' in reaction {raw!r}")
        lhs, rhs = line.split("->", 1)
        reactants = _parse_side(lhs, lineno)
        products = _parse_side(rhs, lineno)
        if not reactants and not products:
            raise CrnParseError(f"line {lineno}: empty reaction")
        reactions.append(
            Reaction(name=name or f"r{len(reactions)}", reactants=reactants, products=products)
        )
        species.update(s for s, _ in (*reactants, *products))

    if not reactions:
        raise CrnParseError("no reactions in CRN")
    return CrnModel(species=tuple(sorted(species)), reactions=tuple(reactions))


__all__ = ["CrnParseError", "Reaction", "CrnModel", "parse_crn"]
