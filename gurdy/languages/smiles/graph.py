"""The SMILES molecular-graph reader (the in-scope thin slice).

**In scope (this slice):** a *single-bonded tree of organic-subset bare atoms
with implicit hydrogens* — SMILES strings made only of the organic-subset
element symbols ``B C N O P S F Cl Br I`` written outside brackets, joined by
implicit single bonds, optionally with parenthesized **branches** ``(...)``
(possibly nested): ``C``, ``CC``, ``CCO``, ``CN``, ``C(C)C``, ``CC(C)C``,
``C(C)(C)C``, ``C(O)C``, ... A run of bare atoms denotes a chain joined by
single bonds; a branch ``(...)`` is a sub-chain bonded to the atom it follows
(the *parent*), after which the main chain resumes from that same parent. The
hydrogens are *implicit*, filled by the per-element valence rule below, where an
atom's degree now counts its branch bonds too. This exercises implicit-hydrogen
valence filling across the whole organic subset and across branched skeletons —
methane ``C`` -> ``CH4``, ethanol ``CCO`` -> ``C2H6O``, water ``O`` -> ``H2O``,
ammonia ``N`` -> ``H3N``, isobutane ``CC(C)C`` -> ``C4H10`` (Hill order).

**Out of scope -> typed abort.** Every other OpenSMILES construct hard-aborts
with ``Unsupported("smiles", <construct>)`` (BENCHMARKS.md §3) — never a silent
drop or a mis-parse. The named constructs (rings, multiple/explicit bonds,
charges, isotopes, aromatic lowercase atoms, bracket atoms, stereo,
dot-disconnection) are what the coverage harness turns into the ``unsupported``
histogram. A *malformed* branch — an unbalanced or empty parenthesis, or a ``(``
with no parent atom — is itself a typed abort (``unbalanced-branch`` /
``empty-branch`` / ``branch-without-parent``), never a silent wrong formula.

The implicit-hydrogen schema (the fixed valence model this slice pins) — the
OpenSMILES "organic subset" normal valences:

  - Each bare atom is an organic-subset element with a fixed *normal valence*:
    ``B`` 3, ``C`` 4, ``N`` 3, ``O`` 2, ``P`` 3 (the OpenSMILES default; ``P``
    also admits 5, not used in this single-bond slice), ``S`` 2, and the
    halogens ``F Cl Br I`` 1.
  - Bonds are single (order 1). Consecutive bare atoms bond in sequence; a
    branch ``(...)`` bonds its first atom to the parent and resumes the chain
    from the parent afterwards. An atom's ``deg`` is its number of single-bond
    neighbours, counting both chain and branch bonds.
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
# itemized) rather than a generic "parse error". Branch parentheses ``( )`` are
# *not* here: they are parsed (the branch construct, this slice), and a malformed
# branch raises its own typed abort in ``parse``.
_CONSTRUCT_BY_CHAR = {
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
    """A parsed molecular graph. For this slice it is a single-bonded *tree*
    (a chain, possibly with branches); the framework only ever consumes
    ``atom_multiset()``.

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

    Accepts a non-empty single-bonded *tree* of organic-subset bare atoms
    (``B C N O P S F Cl Br I``) — a chain ``C``, ``CCO``, ``CN``, ``O``,
    ``CCl``, ... optionally with nested **branches** ``(...)``: ``C(C)C``,
    ``CC(C)C``, ``C(C)(C)C``, ``C(O)C``, ... Consecutive bare atoms are joined
    by an implicit single bond; a branch is a sub-chain bonded to the atom it
    follows (its *parent*), after which the main chain resumes from that same
    parent. Every other character / construct — and any malformed branch —
    hard-aborts with a named ``Unsupported`` (BENCHMARKS.md §3).

    The parse is stack-based: a single ``prev`` index tracks the atom the next
    atom will bond to (``None`` before the first atom). ``(`` saves ``prev`` on a
    stack and opens a branch off it; the matching ``)`` restores ``prev`` so the
    main chain continues from the parent. This is byte-for-byte the old linear
    behavior on any branch-free string (``prev`` walks ``0, 1, 2, ...`` and the
    bonds come out ``(0,1), (1,2), ...`` in order).
    """
    if not isinstance(smiles, str):
        raise TypeError(f"expected a SMILES string, got {type(smiles).__name__}")
    if smiles == "":
        raise Unsupported("smiles", "empty-string")

    elements: list[str] = []
    bonds: list[tuple[int, int]] = []
    # ``prev`` is the atom index the next atom bonds to (``None`` before the
    # first atom). ``stack`` holds the ``prev`` to restore at each branch close;
    # alongside it we remember the atom count at branch-open, to reject an empty
    # branch ``()`` (no atom consumed inside) honestly rather than silently.
    prev: int | None = None
    stack: list[tuple[int, int]] = []  # (prev_to_restore, atom_count_at_open)
    i = 0
    L = len(smiles)
    while i < L:
        ch = smiles[i]
        atom = _next_atom(smiles, i)
        if atom is not None:
            idx = len(elements)
            elements.append(atom)
            if prev is not None:
                bonds.append((prev, idx))  # prev < idx always (indices grow)
            prev = idx
            i += len(atom)
            continue
        if ch == "(":
            # Open a branch off the current atom. A branch with no parent atom
            # (``(`` first, or right after another ``(``) is malformed.
            if prev is None:
                raise Unsupported(
                    "smiles", "branch-without-parent", f"'(' at offset {i}"
                )
            stack.append((prev, len(elements)))
            i += 1
            continue
        if ch == ")":
            if not stack:
                raise Unsupported(
                    "smiles", "unbalanced-branch", f"unmatched ')' at offset {i}"
                )
            restore, count_at_open = stack.pop()
            if len(elements) == count_at_open:
                raise Unsupported(
                    "smiles", "empty-branch", f"'()' closing at offset {i}"
                )
            prev = restore  # resume the main chain from the parent atom
            i += 1
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

    # A branch left open at end-of-string is unbalanced (never a silent drop).
    if stack:
        raise Unsupported(
            "smiles", "unbalanced-branch", f"{len(stack)} unclosed '(' at end"
        )

    # Implicit H from the per-element valence rule: each atom's degree counts all
    # its single bonds (chain *and* branch), then H = max(0, V - deg).
    n = len(elements)
    bonds_t = tuple(bonds)
    deg = [0] * n
    for a, b in bonds_t:
        deg[a] += 1
        deg[b] += 1
    atoms = tuple(
        Atom(elements[k], max(0, ORGANIC_VALENCE[elements[k]] - deg[k]))
        for k in range(n)
    )
    return MolGraph(atoms=atoms, bonds=bonds_t)
