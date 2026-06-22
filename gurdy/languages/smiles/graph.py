"""The SMILES molecular-graph reader (the in-scope thin slice).

**In scope (this slice):** an *organic-subset linear chain of carbon atoms with
implicit hydrogens* — the SMILES strings ``C``, ``CC``, ``CCC``, ... A run of
``C`` characters denotes a chain of carbons joined by single bonds; the
hydrogens are *implicit*, filled by the carbon valence rule below. This is the
smallest fragment that exercises implicit-hydrogen valence filling for one
element (carbon, normal valence 4) — methane ``C`` -> ``CH4``, ethane ``CC`` ->
``C2H6``, the alkane series CnH(2n+2).

**Out of scope -> typed abort.** Every other OpenSMILES construct hard-aborts
with ``Unsupported("smiles", <construct>)`` (BENCHMARKS.md §3) — never a silent
drop or a mis-parse. The named constructs (rings, branches, multiple bonds,
charges, isotopes, aromatic lowercase atoms, bracket atoms, stereo, non-carbon
organic atoms, dot-disconnection) are what the coverage harness turns into the
``unsupported`` histogram.

The implicit-hydrogen schema (the fixed valence model this slice pins):

  - The only atom is organic-subset carbon ``C``, with normal valence ``4``.
  - Bonds in a chain are single (order 1). A carbon at chain position ``i`` of a
    length-``L`` chain has ``deg`` single-bond neighbours: ``deg = 0`` for a lone
    atom, ``1`` at each end, ``2`` in the interior.
  - implicit H on that carbon = ``valence(C) - deg`` = ``4 - deg`` (never < 0
    here).

Pure and deterministic; no dict/iteration-order or filesystem dependence.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.errors import Unsupported

# The organic-subset carbon's normal valence (the one valence this slice pins).
CARBON_VALENCE = 4

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

# Organic-subset element symbols other than carbon. In scope is *carbon only*;
# any other organic atom is a named out-of-scope construct (so the histogram
# distinguishes "we saw nitrogen" from "we saw garbage").
_OTHER_ORGANIC = ("N", "O", "P", "S", "F", "Cl", "Br", "I", "B")


@dataclass(frozen=True)
class Atom:
    """A graph atom: element symbol, and the implicit-hydrogen count filled in
    by the valence rule."""

    element: str
    implicit_h: int


@dataclass(frozen=True)
class MolGraph:
    """A parsed molecular graph. For this slice it is a carbon chain; the
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


def parse(smiles: str) -> MolGraph:
    """Parse an in-scope SMILES string to a molecular graph; abort otherwise.

    Accepts only a non-empty run of organic-subset carbon atoms ``C`` joined by
    implicit single bonds (``C``, ``CC``, ``CCC``, ...). Every other character /
    construct hard-aborts with a named ``Unsupported`` (BENCHMARKS.md §3).
    """
    if not isinstance(smiles, str):
        raise TypeError(f"expected a SMILES string, got {type(smiles).__name__}")
    if smiles == "":
        raise Unsupported("smiles", "empty-string")

    n_carbons = 0
    i = 0
    L = len(smiles)
    while i < L:
        ch = smiles[i]
        if ch == "C":
            # Could be carbon "C" or chlorine "Cl"; chlorine is out of scope but
            # must be *named* as chlorine, not mis-read as carbon + 'l'.
            if i + 1 < L and smiles[i + 1] == "l":
                raise Unsupported("smiles", "organic-atom:Cl")
            n_carbons += 1
            i += 1
            continue
        if ch in _CONSTRUCT_BY_CHAR:
            raise Unsupported("smiles", _CONSTRUCT_BY_CHAR[ch], f"at offset {i}")
        if ch.isdigit():
            raise Unsupported("smiles", "ring-bond", f"digit {ch!r} at offset {i}")
        if ch.islower():
            # Lowercase letters start an aromatic atom (c, n, o, ...).
            raise Unsupported("smiles", "aromatic-atom", f"{ch!r} at offset {i}")
        # A two-letter organic symbol (Cl/Br) or another uppercase organic atom.
        two = smiles[i : i + 2]
        for sym in _OTHER_ORGANIC:
            if two == sym or (len(sym) == 1 and ch == sym):
                raise Unsupported("smiles", f"organic-atom:{sym}", f"at offset {i}")
        raise Unsupported("smiles", "unknown-token", f"{ch!r} at offset {i}")

    # Build the carbon chain: bonds between consecutive carbons, implicit H from
    # the valence rule (deg single bonds -> 4 - deg hydrogens).
    bonds = tuple((k, k + 1) for k in range(n_carbons - 1))
    deg = [0] * n_carbons
    for a, b in bonds:
        deg[a] += 1
        deg[b] += 1
    atoms = tuple(Atom("C", CARBON_VALENCE - deg[k]) for k in range(n_carbons))
    return MolGraph(atoms=atoms, bonds=bonds)
