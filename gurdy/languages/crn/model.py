"""The CRN (chemical reaction network) in-memory model + a deterministic text
loader (languages/crn brief).

A CRN is a finite set of **species** and a finite set of **reactions**; a
reaction maps a reactant multiset to a product multiset over those species.
Under the discrete (Petri-net) semantics a *marking* is a species-population
vector and a reaction fires by subtracting its reactant multiset and adding its
product multiset (``languages/crn`` brief; ARCHITECTURE.md §1).

The model here is deliberately full — it represents arbitrary stoichiometry so
that the *interpreter* (eval.py) and the *coverage probes* can name every
construct — while the ``crn-smtlib`` translator restricts to the one in-scope
reaction class and hard-aborts the rest with a typed ``Unsupported``.

Text format (one statement per non-blank, non-comment line; ``#`` starts a
comment), deterministic and order-preserving::

    species A B C            # declares species, in this order
    init A 3 B 0             # initial marking (species not named default to 0)
    rxn A -> B               # a reaction: reactant multiset -> product multiset
    rxn A + B -> C           # multisets are '+'-separated; '2 A' is a coefficient

A reaction with an empty side is written with ``0`` (e.g. ``rxn A -> 0`` for
degradation, ``rxn 0 -> A`` for synthesis).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reaction:
    """A reaction as two coefficient lists over species names.

    ``reactants`` / ``products`` are ordered ``(species, coefficient)`` pairs
    with positive integer coefficients; a species absent from a side has
    coefficient 0. Order is source order, so the model is deterministic.
    """

    reactants: tuple[tuple[str, int], ...]
    products: tuple[tuple[str, int], ...]

    @property
    def reactant_map(self) -> dict[str, int]:
        return dict(self.reactants)

    @property
    def product_map(self) -> dict[str, int]:
        return dict(self.products)

    @property
    def reactant_tokens(self) -> int:
        """Total reactant multiplicity (Σ coefficients) — the molecularity."""
        return sum(c for _, c in self.reactants)

    @property
    def product_tokens(self) -> int:
        return sum(c for _, c in self.products)

    def to_text(self) -> str:
        return f"rxn {_side_text(self.reactants)} -> {_side_text(self.products)}"


@dataclass(frozen=True)
class Network:
    """A CRN: ordered species, an initial marking, and ordered reactions."""

    species: tuple[str, ...]
    init: tuple[tuple[str, int], ...]  # (species, count), source order
    reactions: tuple[Reaction, ...]

    @property
    def init_map(self) -> dict[str, int]:
        m = {s: 0 for s in self.species}
        m.update(dict(self.init))
        return m

    def to_text(self) -> str:
        lines = ["species " + " ".join(self.species)]
        init_parts = [f"{s} {c}" for s, c in self.init]
        if init_parts:
            lines.append("init " + " ".join(init_parts))
        lines.extend(r.to_text() for r in self.reactions)
        return "\n".join(lines) + "\n"


def _side_text(side: tuple[tuple[str, int], ...]) -> str:
    if not side:
        return "0"
    return " + ".join(s if c == 1 else f"{c} {s}" for s, c in side)


class CrnSyntaxError(ValueError):
    """A malformed CRN source (a structural parse error, not an unsupported
    construct — the latter is the translator's typed ``Unsupported``)."""


def _parse_side(text: str, species: set[str]) -> tuple[tuple[str, int], ...]:
    """Parse one side of a reaction (``A + 2 B`` / ``0``) into ordered
    ``(species, coefficient)`` pairs, summing repeats deterministically."""
    text = text.strip()
    if text in ("0", ""):
        return ()
    order: list[str] = []
    coeffs: dict[str, int] = {}
    for term in text.split("+"):
        toks = term.split()
        if not toks:
            raise CrnSyntaxError(f"empty term in reaction side: {text!r}")
        if len(toks) == 1:
            coeff, name = 1, toks[0]
        elif len(toks) == 2:
            try:
                coeff = int(toks[0])
            except ValueError as exc:
                raise CrnSyntaxError(f"bad coefficient in {term!r}") from exc
            name = toks[1]
        else:
            raise CrnSyntaxError(f"malformed reaction term: {term!r}")
        if coeff <= 0:
            raise CrnSyntaxError(f"non-positive coefficient in {term!r}")
        if name not in species:
            raise CrnSyntaxError(f"undeclared species {name!r}")
        if name not in coeffs:
            coeffs[name] = 0
            order.append(name)
        coeffs[name] += coeff
    return tuple((s, coeffs[s]) for s in order)


def from_text(text: str | bytes) -> Network:
    """Parse the textual CRN format into a :class:`Network`. Deterministic:
    species, init entries, and reactions keep source order."""
    if isinstance(text, (bytes, bytearray)):
        text = text.decode("utf-8")

    species: list[str] = []
    species_set: set[str] = set()
    init: list[tuple[str, int]] = []
    reactions: list[Reaction] = []

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        head, _, rest = line.partition(" ")
        if head == "species":
            for name in rest.split():
                if name not in species_set:
                    species_set.add(name)
                    species.append(name)
        elif head == "init":
            toks = rest.split()
            if len(toks) % 2 != 0:
                raise CrnSyntaxError(f"init needs species/count pairs: {line!r}")
            for i in range(0, len(toks), 2):
                name, count = toks[i], toks[i + 1]
                if name not in species_set:
                    raise CrnSyntaxError(f"init of undeclared species {name!r}")
                try:
                    init.append((name, int(count)))
                except ValueError as exc:
                    raise CrnSyntaxError(f"bad init count {count!r}") from exc
        elif head == "rxn":
            lhs, arrow, rhs = rest.partition("->")
            if arrow != "->":
                raise CrnSyntaxError(f"reaction needs '->': {line!r}")
            reactions.append(
                Reaction(_parse_side(lhs, species_set), _parse_side(rhs, species_set))
            )
        else:
            raise CrnSyntaxError(f"unknown statement {head!r}")

    return Network(tuple(species), tuple(init), tuple(reactions))


def as_network(crn: object) -> Network:
    """Coerce ``bytes`` / ``str`` / :class:`Network` to a :class:`Network`."""
    if isinstance(crn, Network):
        return crn
    return from_text(crn)  # type: ignore[arg-type]
