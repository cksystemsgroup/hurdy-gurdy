"""The SMILES molecular-graph reader (the in-scope thin slice).

**In scope (this slice):** a *linear single-bonded chain of organic-subset
bare atoms with implicit hydrogens* — SMILES strings made only of the
organic-subset element symbols ``B C N O P S F Cl Br I`` written outside
brackets, joined by implicit single bonds: ``C``, ``CC``, ``CCO``, ``CN``,
``CF``, ``O``, ``N``, ``CCl``, ... A run of bare atoms denotes a chain joined by
single bonds; the hydrogens are *implicit*, filled by the per-element valence
rule below. This exercises implicit-hydrogen valence filling across the whole
organic subset — methane ``C`` -> ``CH4``, ethanol ``CCO`` -> ``C2H6O``, water
``O`` -> ``H2O``, ammonia ``N`` -> ``H3N`` (Hill order).

**Out of scope -> typed abort.** Every other OpenSMILES construct hard-aborts
with ``Unsupported("smiles", <construct>)`` (BENCHMARKS.md §3) — never a silent
drop or a mis-parse. The named constructs (rings, branches, multiple/explicit
bonds, charges, isotopes, aromatic lowercase atoms, bracket atoms, stereo,
dot-disconnection) are what the coverage harness turns into the ``unsupported``
histogram.

The implicit-hydrogen schema (the fixed valence model this slice pins) — the
OpenSMILES "organic subset" normal valences:

  - Each bare atom is an organic-subset element with a fixed *normal valence*:
    ``B`` 3, ``C`` 4, ``N`` 3, ``O`` 2, ``P`` 3 (the OpenSMILES default; ``P``
    also admits 5, not used in this single-bond slice), ``S`` 2, and the
    halogens ``F Cl Br I`` 1.
  - Bonds in a chain are single (order 1). An atom at chain position ``i`` of a
    length-``L`` chain has ``deg`` single-bond neighbours: ``deg = 0`` for a
    lone atom, ``1`` at each end, ``2`` in the interior.
  - implicit H on that atom = ``max(0, normal_valence(element) - deg)`` — the
    OpenSMILES rule, with the clamp at 0 so an over-bonded atom (none arises in
    this single-bond slice) contributes no negative hydrogens.

Pure and deterministic; no dict/iteration-order or filesystem dependence.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.errors import Unsupported

# The organic-subset normal valences (OpenSMILES). These are the elements that
# may be written *bare* (outside brackets) and get implicit hydrogens filled by
# ``normal_valence - bond_order_sum``. ``P`` uses 3 (the OpenSMILES default;
# ``P`` also admits a valence of 5, irrelevant to this single-bond slice).
ORGANIC_VALENCE: dict[str, int] = {
    "B": 3,
    "C": 4,
    "N": 3,
    "O": 2,
    "P": 3,
    "S": 2,
    "F": 1,
    "Cl": 1,
    "Br": 1,
    "I": 1,
}

# Kept for backward compatibility with callers that referenced the single-element
# slice's constant; the table above is the source of truth.
CARBON_VALENCE = ORGANIC_VALENCE["C"]

# Two-letter organic-subset symbols (must be recognized as one atom, not split
# into an element plus a stray lowercase letter).
_TWO_LETTER = ("Cl", "Br")

# Characters that begin a *named, out-of-scope* SMILES construct. Mapping each
# to the construct it names lets the abort be specific (and the histogram
# itemized) rather than a generic "parse error".
_CONSTRUCT_BY_CHAR = {
    "(": "branch",
    ")": "branch",
    "[": "bracket-atom",
    "]": "bracket-atom",
    "=": "double-bond",
    "#": "triple-bond",
    "$": "quadruple-bond",
    ":": "aromatic-bond",
    "/": "stereo-bond",
    "\\": "stereo-bond",
    "-": "explicit-single-bond",
    ".": "disconnection",
    "+": "charge",
    "@": "stereo",
    "%": "ring-closure",
}


@dataclass(frozen=True)
class Atom:
    """A graph atom: element symbol, and the implicit-hydrogen count filled in
    by the valence rule."""

    element: str
    implicit_h: int


@dataclass(frozen=True)
class MolGraph:
    """A parsed molecular graph. For this slice it is a linear chain; the
    framework only ever consumes ``atom_multiset()``.

    ``bonds`` are undirected single bonds as index pairs ``(i, j)`` with
    ``i < j``; kept so the model is honestly a *graph* even though the
    projection discards connectivity.
    """

    atoms: tuple[Atom, ...]
    bonds: tuple[tuple[int, int], ...]

    def atom_multiset(self) -> dict[str, int]:
        """The atom multiset: heavy atoms plus the implicit hydrogens. This is
        the projected observable ``π`` preserves (connectivity is discarded)."""
        counts: dict[str, int] = {}
        for atom in self.atoms:
            counts[atom.element] = counts.get(atom.element, 0) + 1
            if atom.implicit_h:
                counts["H"] = counts.get("H", 0) + atom.implicit_h
        return counts


def _next_atom(smiles: str, i: int) -> str | None:
    """If an organic-subset bare atom starts at offset ``i``, return its element
    symbol (``"Cl"`` / ``"Br"`` consume two characters); else ``None``.

    A two-letter symbol is preferred over its one-letter prefix, so ``Cl`` reads
    as chlorine (not carbon + ``l``) and ``Br`` as bromine (not boron + ``r``).
    """
    two = smiles[i : i + 2]
    if two in _TWO_LETTER:
        return two
    ch = smiles[i]
    if ch in ORGANIC_VALENCE and len(ch) == 1:
        return ch
    return None


def parse(smiles: str) -> MolGraph:
    """Parse an in-scope SMILES string to a molecular graph; abort otherwise.

    Accepts only a non-empty linear single-bonded chain of organic-subset bare
    atoms (``B C N O P S F Cl Br I``) — ``C``, ``CCO``, ``CN``, ``O``, ``CCl``,
    ... Consecutive atoms are joined by an implicit single bond. Every other
    character / construct hard-aborts with a named ``Unsupported``
    (BENCHMARKS.md §3).
    """
    if not isinstance(smiles, str):
        raise TypeError(f"expected a SMILES string, got {type(smiles).__name__}")
    if smiles == "":
        raise Unsupported("smiles", "empty-string")

    elements: list[str] = []
    i = 0
    L = len(smiles)
    while i < L:
        ch = smiles[i]
        atom = _next_atom(smiles, i)
        if atom is not None:
            elements.append(atom)
            i += len(atom)
            continue
        if ch in _CONSTRUCT_BY_CHAR:
            raise Unsupported("smiles", _CONSTRUCT_BY_CHAR[ch], f"at offset {i}")
        if ch.isdigit():
            raise Unsupported("smiles", "ring-bond", f"digit {ch!r} at offset {i}")
        if ch.islower():
            # Lowercase letters start an aromatic atom (c, n, o, ...). (A trailing
            # 'l'/'r' of Cl/Br was already consumed by ``_next_atom`` above.)
            raise Unsupported("smiles", "aromatic-atom", f"{ch!r} at offset {i}")
        # An uppercase symbol that is not an in-scope organic atom: name it as an
        # out-of-scope element rather than as garbage, so the histogram is honest.
        raise Unsupported("smiles", f"organic-atom:{ch}", f"at offset {i}")

    # Build the linear chain: single bonds between consecutive atoms, implicit H
    # from the per-element valence rule (deg single bonds -> max(0, V - deg)).
    n = len(elements)
    bonds = tuple((k, k + 1) for k in range(n - 1))
    deg = [0] * n
    for a, b in bonds:
        deg[a] += 1
        deg[b] += 1
    atoms = tuple(
        Atom(elements[k], max(0, ORGANIC_VALENCE[elements[k]] - deg[k]))
        for k in range(n)
    )
    return MolGraph(atoms=atoms, bonds=bonds)
