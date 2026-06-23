"""The SMILES molecular-graph reader (the in-scope thin slice).

**In scope (this slice):** a *graph of organic-subset bare atoms with implicit
hydrogens, joined by single / double / triple bonds — chains, branches, rings,
and now **bracket atoms*** — SMILES strings made of the organic-subset element
symbols ``B C N O P S F Cl Br I`` written *bare* (outside brackets), **or any
element written as a bracket atom** ``[...]`` (e.g. ``[Se]``, ``[Na]``,
``[NH4+]``, ``[13C]``, ``[C@H]``), joined by single bonds (implicit, or the
explicit single bond ``-``), **double bonds** ``=`` (order 2), or **triple
bonds** ``#`` (order 3), optionally with parenthesized **branches** ``(...)``
(possibly nested) and **ring-closure bonds** (a digit ``1``-``9``, or a
two-digit ``%nn`` label, after an atom — the same label later closing the ring):
``C``, ``CC``, ``CCO``, ``C=C``, ``C#C``, ``C=O``, ``O=C=O``, ``CC#N``,
``C(C)C``, ``CC(C)C``, ``C(=O)O``, ``C1CCCCC1``, ``C1CC1``, ``C1=CCCCC1``,
``O1CCOCC1``, ``[NH4+]``, ``[Se]``, ``C[N+]C``, ... A run of atoms denotes a
chain; a bond token ``= # -`` between two atoms sets the order of the bond
joining them; a branch ``(...)`` is a sub-chain bonded to the atom it follows
(the *parent*), after which the main chain resumes from that same parent; a
**ring-closure label** marks a ring-bond endpoint and the second occurrence of
the same label bonds the two endpoint atoms (closing the ring).

For a **bare** atom the hydrogens are *implicit*, filled by the per-element
valence rule below, where an atom's degree is the **sum of its bond orders** (so
a double bond contributes 2, a triple bond 3, and a ring-closure bond counts
toward *both* its endpoint atoms). For a **bracket** atom ``[...]`` the hydrogens
are *explicit*: a bracket atom gets **no implicit hydrogen** — its H count is
exactly what the ``H<n>`` field writes (``[NH4+]`` -> 4 H, ``[CH3]`` -> 3 H,
``[OH-]`` -> 1 H), and absent means **zero** (``[C]`` -> just C, ``[O]`` -> just
O). Because a bracket atom's hydrogens are fully explicit, **chain/ring/branch
bonds to it neither add nor remove hydrogen**, and it is *exempt* from the
valence rule (so any element — ``[Se]``, ``[Na]``, ``[Fe]`` — at any bond degree
is accepted on a bracket atom). For the molecular-formula projection only the
**symbol** and the **explicit H count** of a bracket atom matter; the isotope
(``[13C]`` is still carbon), charge (``+``/``-``/``+2``…), chirality
(``@``/``@@``) and atom class (``:n``) are parsed and validated but do **not**
change the atom multiset. This exercises implicit-hydrogen valence filling across
the whole organic subset, branched skeletons, bond orders, and rings, plus
explicit-hydrogen bracket atoms over the whole periodic table — methane ``C`` ->
``CH4``, ethene ``C=C`` -> ``C2H4``, cyclohexane ``C1CCCCC1`` -> ``C6H12``,
ammonium ``[NH4+]`` -> ``H4N``, selenium ``[Se]`` -> ``Se`` (Hill order).

**Out of scope -> typed abort.** Every other OpenSMILES construct hard-aborts
with ``Unsupported("smiles", <construct>)`` (BENCHMARKS.md §3) — never a silent
drop or a mis-parse. The named constructs (the quadruple/aromatic bonds
``$``/``:``, **aromatic lowercase atoms** — bare *and* in brackets, ``[se]`` /
``[n]`` — stereo bonds, dot-disconnection) are what the coverage harness turns
into the ``unsupported`` histogram. A *malformed* branch — an
unbalanced or empty parenthesis, or a ``(`` with no parent atom — is itself a
typed abort (``unbalanced-branch`` / ``empty-branch`` / ``branch-without-parent``),
never a silent wrong formula. A **dangling bond** — a bond token ``= # -`` with
no atom on one side (at the string start, before a ``)`` or ``(``, doubled, or at
end-of-string) — is a typed abort (``dangling-bond``); a **bond order exceeding a
(bare) atom's valence** (e.g. ``F=C``, fluorine valence 1) is a typed abort
(``valence-exceeded``), never a silently wrong (clamped-to-zero) formula. A
**malformed ring closure** — a ring-bond label that is never closed (an open
digit at end-of-parse), a ring digit with no atom on its left, a ring bond whose
two ends carry *different* explicit bond orders, or a self-ring (a label closing
onto its own opening atom) — is a typed abort (``ring-bond-unclosed`` /
``ring-bond-no-atom`` / ``ring-bond-order-mismatch`` / ``ring-bond-self``), never
a silent wrong formula. A **malformed bracket atom** — an unclosed ``[`` (no
matching ``]``), an empty ``[]``, an unknown element symbol (``[Xx]``), or a bad
``H``-count / charge / isotope / class field — is a typed abort
(``bracket-atom-unclosed`` / ``bracket-atom-empty`` / ``bracket-atom-element`` /
``bracket-atom-malformed``), never a silent wrong formula.

The implicit-hydrogen schema (the fixed valence model this slice pins) — the
OpenSMILES "organic subset" normal valences:

  - Each bare atom is an organic-subset element with a fixed *normal valence*:
    ``B`` 3, ``C`` 4, ``N`` 3, ``O`` 2, ``P`` 3 (the OpenSMILES default; ``P``
    also admits 5, not used in this slice), ``S`` 2, and the halogens
    ``F Cl Br I`` 1.
  - A bond carries an *order*: single (1, implicit or written ``-``), double
    (2, written ``=``), or triple (3, written ``#``). Consecutive bare atoms
    bond in sequence; a branch ``(...)`` bonds its first atom to the parent and
    resumes the chain from the parent afterwards; a **ring-closure label** (a
    digit ``1``-``9`` or ``%nn``) after an atom opens a ring-bond endpoint, and
    the second occurrence of the same label adds a bond between the two endpoint
    atoms (its order is 1, or the explicit order of a bond token written
    immediately before the label, e.g. ``C=1...C1``). An atom's ``deg`` is the
    *sum of the orders* of its incident bonds, counting chain, branch, and
    ring-closure bonds alike (a ring-closure bond counts toward *both* ends).
  - implicit H on that atom = ``max(0, normal_valence(element) - deg)`` — the
    OpenSMILES rule. The clamp at 0 is never *reached* here: an atom whose
    incident bond-order sum already exceeds its normal valence is rejected as
    ``valence-exceeded`` before any hydrogen is filled, so the clamp can never
    silently mask an over-bonded atom.
  - A **bracket** atom ``[...]`` is *exempt* from this rule entirely: its
    hydrogens are written explicitly (the ``H<n>`` field; absent = 0), so it gets
    **no implicit hydrogen**, its element need not be in the organic-valence
    table (any element, ``[Se]``/``[Na]``/``[Fe]``), and its bond-order sum is
    **never** valence-checked (a bracket atom carries no normal valence here).

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

# Bond-order tokens (this slice). A bond token written *between* two atoms sets
# the order of the bond joining them: ``-`` single (1, same as implicit), ``=``
# double (2), ``#`` triple (3). Mapped to the construct name an order-error abort
# reports against, so the ``unsupported`` histogram stays itemized by bond order.
_BOND_ORDER_BY_CHAR = {
    "-": 1,
    "=": 2,
    "#": 3,
}
_BOND_CONSTRUCT_BY_CHAR = {
    "-": "explicit-single-bond",
    "=": "double-bond",
    "#": "triple-bond",
}

# Characters that begin a *named, out-of-scope* SMILES construct. Mapping each
# to the construct it names lets the abort be specific (and the histogram
# itemized) rather than a generic "parse error". Branch parentheses ``( )`` are
# *not* here: they are parsed (the branch construct), and a malformed branch
# raises its own typed abort in ``parse``. The single/double/triple bond tokens
# ``- = #`` are *not* here either: they are parsed (the bond-order construct)
# and a misplaced one raises ``dangling-bond`` in ``parse``. Ring-closure labels
# — a digit ``1``-``9`` and the two-digit ``%nn`` — are *not* here either: they
# are parsed (the ring-bond construct) and a malformed one raises a typed
# ``ring-bond-*`` abort. The bracket atom ``[...]`` is *not* here either: it is
# parsed (the bracket-atom construct, this slice) and a malformed one raises a
# typed ``bracket-atom-*`` abort. The ``+`` (charge) and ``@`` (stereo) tokens
# stay here because outside a bracket they are still out of scope; inside a
# bracket they are consumed by ``_read_bracket_atom``. The quadruple ``$`` and
# aromatic ``:`` bonds remain out of scope.
_CONSTRUCT_BY_CHAR = {
    "$": "quadruple-bond",
    ":": "aromatic-bond",
    "/": "stereo-bond",
    "\\": "stereo-bond",
    ".": "disconnection",
    "+": "charge",
    "@": "stereo",
}

# The element symbols a *bracket* atom may name (OpenSMILES allows any element).
# Uppercase-first canonical symbols of the periodic table (through the actinides
# / superheavies), plus the wildcard ``*``. A bracket atom whose symbol is not in
# this set (e.g. ``[Xx]``) hard-aborts ``bracket-atom-element`` — never a silent
# guess. (Aromatic *lowercase* bracket symbols like ``[se]`` are handled before
# this check: they hard-abort ``aromatic-atom``, the same as a bare lowercase
# atom.) This set is data, not behavior: it only widens which symbols are legal
# inside brackets; the projection (atom multiset) treats every one the same way.
_ELEMENTS: frozenset[str] = frozenset(
    """
    H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni
    Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe
    Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg
    Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg
    Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og
    """.split()
)


@dataclass(frozen=True)
class Atom:
    """A graph atom: element symbol, and its hydrogen count.

    ``implicit_h`` is the number of hydrogens attached to this heavy atom. For a
    **bare** atom (``bracket=False``) it is the *implicit* count filled in by the
    valence rule (``normal_valence − degree``). For a **bracket** atom
    (``bracket=True``) it is the *explicit* ``H<n>`` count written in the brackets
    (``[NH4+]`` -> 4, ``[C]`` -> 0); a bracket atom gets no valence-filled
    hydrogen. Either way it is "the hydrogens this atom contributes to the
    multiset", so ``atom_multiset`` treats both uniformly. ``bracket`` records
    which kind it is, so the degree/valence pass can *skip* bracket atoms (they
    carry no normal valence and are never over-bonded)."""

    element: str
    implicit_h: int
    bracket: bool = False


@dataclass(frozen=True)
class MolGraph:
    """A parsed molecular graph. For this slice it is a chain (possibly with
    branches *and rings*) whose bonds carry an order (single / double / triple);
    the framework only ever consumes ``atom_multiset()``.

    ``bonds`` are undirected bonds as index pairs ``(i, j)`` with ``i < j``;
    ``orders`` is the parallel tuple of bond orders (``1``/``2``/``3``), so
    ``orders[k]`` is the order of ``bonds[k]``. Keeping ``bonds`` as bare index
    pairs makes single-bond/branch behavior byte-for-byte identical to the
    single-bond slice (where ``orders`` is all ``1``s); the orders are carried
    alongside so the model is honestly a *graph* even though the projection
    discards connectivity.
    """

    atoms: tuple[Atom, ...]
    bonds: tuple[tuple[int, int], ...]
    orders: tuple[int, ...] = ()

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


def _read_ring_label(smiles: str, i: int) -> tuple[str, int] | None:
    """If a ring-closure label starts at offset ``i``, return ``(label, width)``
    where ``label`` is its canonical key (the digit, or ``"%nn"`` for a two-digit
    label) and ``width`` is how many characters it consumed; else ``None``.

    A bare digit ``1``-``9`` is a one-character label (``"0"`` is not a valid
    ring-bond digit in the organic subset and aborts elsewhere). A ``%`` must be
    followed by exactly two digits (``%nn``, OpenSMILES two-digit ring numbers);
    a ``%`` not so followed is a malformed ring label (caught by the caller).
    """
    ch = smiles[i]
    if ch == "%":
        two = smiles[i + 1 : i + 3]
        if len(two) == 2 and two.isdigit():
            return f"%{two}", 3
        return None  # malformed %nn — the caller raises the typed abort
    if ch in "123456789":
        return ch, 1
    return None


def _read_bracket_atom(smiles: str, i: int) -> tuple[str, int, int]:
    """Parse a bracket atom ``[...]`` starting at the ``[`` at offset ``i``.

    Returns ``(element, explicit_h, width)`` where ``element`` is the element
    symbol, ``explicit_h`` is the explicit hydrogen count (the ``H<n>`` field; 0
    if absent), and ``width`` is how many characters the whole ``[...]`` consumed.
    Raises a typed ``Unsupported`` on any malformed bracket.

    The OpenSMILES bracket grammar is ``[ isotope? symbol chirality? hcount?
    charge? class? ]``. For the molecular-formula projection only **symbol** and
    **hcount** affect the atom multiset; the isotope, chirality, charge and class
    are parsed (and validated) but discarded. The fields, in order:

      - **isotope** — optional run of digits before the symbol (``[13C]``);
      - **symbol** — an element symbol (``C``, ``Se``, ``Na`` …) or wildcard
        ``*``. A *lowercase* leading letter (``[se]``, ``[n]``) is an aromatic
        atom and hard-aborts ``aromatic-atom`` (aromaticity is a later round),
        matching the bare-atom behavior. An unknown symbol (``[Xx]``) aborts
        ``bracket-atom-element``;
      - **chirality** — ``@`` or ``@@`` (the basic tetrahedral forms; the
        extended ``@TH1``/``@OH3``/… forms are consumed by the ``@`` + letters +
        digits run). Discarded;
      - **hcount** — ``H`` optionally followed by a single digit. ``H`` alone is
        one hydrogen; ``H0``…``H9`` is that many; absent is zero;
      - **charge** — ``+``/``-`` optionally repeated (``++``) or followed by a
        number (``+2``). Discarded (the neutral atom multiset);
      - **class** — ``:`` followed by digits. Discarded.

    Anything that does not fit (a stray character, two H-counts, a bad charge)
    aborts ``bracket-atom-malformed``; an unterminated bracket aborts
    ``bracket-atom-unclosed``; an empty ``[]`` aborts ``bracket-atom-empty``.
    Pure: a single left-to-right scan with no adaptive choice.
    """
    L = len(smiles)
    # Find the matching ``]``. A bracket atom contains no nested ``[``, so the
    # first ``]`` after the ``[`` closes it.
    close = smiles.find("]", i + 1)
    if close == -1:
        raise Unsupported(
            "smiles", "bracket-atom-unclosed",
            f"'[' at offset {i} has no matching ']'",
        )
    body = smiles[i + 1 : close]
    width = close - i + 1
    if body == "":
        raise Unsupported(
            "smiles", "bracket-atom-empty", f"empty '[]' at offset {i}"
        )

    p = 0
    n = len(body)

    # isotope: an optional leading run of digits.
    while p < n and body[p].isdigit():
        p += 1

    # symbol: the wildcard ``*`` or an element symbol. A lowercase leading letter
    # is an aromatic atom (out of scope) — abort exactly as a bare lowercase atom.
    if p >= n:
        raise Unsupported(
            "smiles", "bracket-atom-malformed",
            f"bracket atom at offset {i} has no element symbol",
        )
    ch = body[p]
    if ch == "*":
        raise Unsupported(
            "smiles", "bracket-atom-malformed",
            f"wildcard atom '*' in bracket at offset {i} is out of scope",
        )
    if ch.islower():
        raise Unsupported(
            "smiles", "aromatic-atom",
            f"aromatic bracket atom {ch!r} at offset {i + 1 + p}",
        )
    if not ch.isupper():
        raise Unsupported(
            "smiles", "bracket-atom-malformed",
            f"unexpected {ch!r} where an element symbol was expected "
            f"at offset {i + 1 + p}",
        )
    # Prefer a two-letter symbol (uppercase + lowercase) when it is a real
    # element, else take the one-letter symbol. ``[Co]`` is cobalt, but a
    # one-letter element followed by a field letter (``[CH4]`` -> ``C`` then
    # ``H4``) must read as the one-letter element.
    two = body[p : p + 2]
    if len(two) == 2 and two[1].islower() and two in _ELEMENTS:
        element = two
        p += 2
    elif ch in _ELEMENTS:
        element = ch
        p += 1
    else:
        # An uppercase symbol that names no element (``[Xx]`` — taking the
        # two-letter ``Xx`` — or a lone ``[X]``). Report the offending symbol.
        bad = two if (len(two) == 2 and two[1].islower()) else ch
        raise Unsupported(
            "smiles", "bracket-atom-element",
            f"unknown element symbol {bad!r} in bracket at offset {i + 1}",
        )

    # chirality: ``@`` or ``@@``, plus the extended ``@TH1``/``@OH12``/… forms
    # (``@`` followed by two uppercase letters then digits). Discarded.
    if p < n and body[p] == "@":
        p += 1
        if p < n and body[p] == "@":
            p += 1
        else:
            # Extended chirality class: two uppercase letters + digits (optional).
            if p + 1 < n and body[p].isupper() and body[p + 1].isupper():
                p += 2
                while p < n and body[p].isdigit():
                    p += 1

    # hcount: ``H`` optionally followed by a single digit. ``H`` alone = 1.
    explicit_h = 0
    if p < n and body[p] == "H":
        p += 1
        if p < n and body[p].isdigit():
            explicit_h = int(body[p])
            p += 1
        else:
            explicit_h = 1

    # charge: ``+``/``-``, optionally repeated (``++``/``--``) or followed by a
    # number (``+2``/``-3``). Either the repeated or the numeric form, not both.
    # Discarded (the multiset is the neutral atom count).
    if p < n and body[p] in "+-":
        sign = body[p]
        p += 1
        if p < n and body[p] == sign:
            # Repeated-sign form (``++`` / ``--``); OpenSMILES allows a run.
            while p < n and body[p] == sign:
                p += 1
        else:
            while p < n and body[p].isdigit():
                p += 1

    # class: ``:`` followed by one or more digits. Discarded.
    if p < n and body[p] == ":":
        p += 1
        start = p
        while p < n and body[p].isdigit():
            p += 1
        if p == start:
            raise Unsupported(
                "smiles", "bracket-atom-malformed",
                f"atom class ':' with no digits in bracket at offset {i + 1}",
            )

    # Anything left over is an unparsed field — a malformed bracket atom.
    if p != n:
        raise Unsupported(
            "smiles", "bracket-atom-malformed",
            f"unexpected {body[p:]!r} in bracket atom at offset {i + 1 + p}",
        )
    return element, explicit_h, width


def parse(smiles: str) -> MolGraph:
    """Parse an in-scope SMILES string to a molecular graph; abort otherwise.

    Accepts a non-empty organic-subset graph of bare atoms
    (``B C N O P S F Cl Br I``) **and bracket atoms** ``[...]`` (any element,
    explicit H — ``[NH4+]``, ``[Se]``, ``[13C]``, ``[C@H]``) joined by single /
    double / triple bonds — a chain ``C``, ``CCO``, ``C=C``, ``C#C``, ``C=O``,
    ``O=C=O``, ``CC#N``, ``C[N+]C``, ... optionally with nested **branches**
    ``(...)`` (``C(C)C``, ``C(=O)O``, ``CC(=O)C``, ...) and **ring-closure bonds**
    (``C1CCCCC1``, ``C1CC1``, ``C1=CCCCC1``, ``O1CCOCC1``, ...). Consecutive atoms
    are joined by an implicit single bond; a bond token ``-``/``=``/``#`` between
    two atoms makes the bond joining them single/double/triple; a branch is a
    sub-chain bonded to the atom it follows (its *parent*), after which the main
    chain resumes from that same parent; a **ring-closure label** (a digit
    ``1``-``9`` or ``%nn``) after an atom opens a ring-bond endpoint, and the
    second occurrence of the same label adds a bond between the two endpoint atoms.
    A **bracket atom** ``[...]`` is an atom like any other for bonding/branch/ring
    purposes (it bonds to ``prev`` and becomes the new ``prev``), but its hydrogen
    count is *explicit* (no valence fill) and it is exempt from the valence check.
    Every other character / construct — and any malformed branch, misplaced bond
    token, malformed ring closure, or malformed bracket atom — hard-aborts with a
    named ``Unsupported`` (BENCHMARKS.md §3).

    The parse is stack-based: a single ``prev`` index tracks the atom the next
    atom will bond to (``None`` before the first atom), and ``pending_order``
    carries the order of the next bond (``1`` by default, or set by a ``-``/``=``
    /``#`` token; ``pending_tok`` flags "a bond token is open and an atom — or a
    ring label — must follow", so a dangling bond is caught). ``(`` saves
    ``prev`` on a stack and opens a branch off it; the matching ``)`` restores
    ``prev`` so the main chain continues from the parent. A **ring label** after
    an atom is recorded in ``open_rings`` keyed by its label (the opening atom,
    plus the explicit order — if a bond token was open — and the offset); the
    second occurrence of the same label pops it and adds the ring bond, with the
    two ends' explicit orders reconciled. This is byte-for-byte the old behavior
    on any string with no ring label (``open_rings`` stays empty and is never
    consulted), and on any string with no bond token (``prev`` walks
    ``0, 1, 2, ...``, every order is ``1``, the bonds come out ``(0,1), (1,2),
    ...`` in order).
    """
    if not isinstance(smiles, str):
        raise TypeError(f"expected a SMILES string, got {type(smiles).__name__}")
    if smiles == "":
        raise Unsupported("smiles", "empty-string")

    elements: list[str] = []
    bonds: list[tuple[int, int]] = []
    orders: list[int] = []
    # Parallel per-atom state (index-aligned with ``elements``). ``is_bracket[k]``
    # flags a bracket atom ``[...]`` — exempt from the valence rule, with an
    # *explicit* hydrogen count in ``explicit_h[k]`` (0 for a bare atom, whose
    # hydrogens are filled by valence later). A string with no bracket atom leaves
    # ``is_bracket`` all-``False`` and ``explicit_h`` all-``0``, so the valence
    # fill at the end is byte-for-byte the old behavior.
    is_bracket: list[bool] = []
    explicit_h: list[int] = []
    # ``prev`` is the atom index the next atom bonds to (``None`` before the
    # first atom). ``pending_order`` is the order the next bond will carry: ``1``
    # by default, or a value set by a bond token ``- = #`` awaiting its right-hand
    # atom. ``pending_tok`` records the offset/construct of an *open* bond token
    # (an order set but not yet consumed by an atom), so a dangling bond — a token
    # with no atom on the right — is a typed abort, never a silent drop. ``stack``
    # holds the ``prev`` to restore at each branch close; alongside it the atom
    # count at branch-open, to reject an empty branch ``()`` honestly.
    prev: int | None = None
    pending_order: int = 1
    pending_tok: tuple[int, str] | None = None  # (offset, construct) of open bond
    stack: list[tuple[int, int]] = []  # (prev_to_restore, atom_count_at_open)
    # ``open_rings`` maps a ring-closure label (the digit, or ``"%nn"``) to the
    # endpoint that opened it: (atom_index, explicit_order_or_None, offset). An
    # explicit order is the order carried by a bond token written immediately
    # before the label (``None`` for the default order-1 bond); the offset is for
    # the diagnostic if the label is never closed. Ring labels are matched in
    # *pairs* — the second occurrence of a label closes the ring.
    open_rings: dict[str, tuple[int, int | None, int]] = {}
    i = 0
    L = len(smiles)
    while i < L:
        ch = smiles[i]
        atom = _next_atom(smiles, i)
        if atom is not None:
            idx = len(elements)
            elements.append(atom)
            is_bracket.append(False)
            explicit_h.append(0)  # bare atom: H filled by valence at the end
            if prev is not None:
                bonds.append((prev, idx))  # prev < idx always (indices grow)
                orders.append(pending_order)
            elif pending_tok is not None:
                # A bond token with no atom on its *left* (string start, or just
                # after a branch-open ``(``): the order has no bond to attach to.
                off, construct = pending_tok
                raise Unsupported(
                    "smiles", "dangling-bond",
                    f"{construct} token at offset {off} has no atom on its left",
                )
            prev = idx
            pending_order = 1
            pending_tok = None
            i += len(atom)
            continue
        if ch == "[":
            # A bracket atom ``[...]``: any element, explicit hydrogens, no
            # valence fill. It bonds to ``prev`` (with the pending order) and
            # becomes the new ``prev`` exactly like a bare atom; only its
            # hydrogen handling and valence exemption differ.
            element, h, width = _read_bracket_atom(smiles, i)
            idx = len(elements)
            elements.append(element)
            is_bracket.append(True)
            explicit_h.append(h)
            if prev is not None:
                bonds.append((prev, idx))
                orders.append(pending_order)
            elif pending_tok is not None:
                off, construct = pending_tok
                raise Unsupported(
                    "smiles", "dangling-bond",
                    f"{construct} token at offset {off} has no atom on its left",
                )
            prev = idx
            pending_order = 1
            pending_tok = None
            i += width
            continue
        if ch == "]":
            # A ``]`` with no open ``[`` is a malformed bracket (never reached
            # inside ``_read_bracket_atom``, which consumes its own ``]``).
            raise Unsupported(
                "smiles", "bracket-atom-malformed",
                f"unmatched ']' at offset {i}",
            )
        if ch in _BOND_ORDER_BY_CHAR:
            # A bond-order token. It must sit *between* two atoms: there must be a
            # left atom (``prev`` set) and no other open bond token, and an atom
            # must follow (checked when the next atom — or a non-atom — is seen).
            if prev is None:
                raise Unsupported(
                    "smiles", "dangling-bond",
                    f"{_BOND_CONSTRUCT_BY_CHAR[ch]} token at offset {i} "
                    "has no atom on its left",
                )
            if pending_tok is not None:
                raise Unsupported(
                    "smiles", "dangling-bond",
                    f"two bond tokens in a row at offset {i}",
                )
            pending_order = _BOND_ORDER_BY_CHAR[ch]
            pending_tok = (i, _BOND_CONSTRUCT_BY_CHAR[ch])
            i += 1
            continue
        if ch == "(":
            # Open a branch off the current atom. A branch with no parent atom
            # (``(`` first, or right after another ``(``) is malformed; a bond
            # token immediately before the ``(`` is a dangling bond.
            if pending_tok is not None:
                off, construct = pending_tok
                raise Unsupported(
                    "smiles", "dangling-bond",
                    f"{construct} token at offset {off} followed by '(' "
                    f"at offset {i}, no atom between",
                )
            if prev is None:
                raise Unsupported(
                    "smiles", "branch-without-parent", f"'(' at offset {i}"
                )
            stack.append((prev, len(elements)))
            i += 1
            continue
        if ch == ")":
            if pending_tok is not None:
                off, construct = pending_tok
                raise Unsupported(
                    "smiles", "dangling-bond",
                    f"{construct} token at offset {off} followed by ')' "
                    f"at offset {i}, no atom after it",
                )
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
        if ch in "123456789" or ch == "%":
            # A ring-closure label after an atom. A bare digit ``1``-``9`` is a
            # one-character label; ``%nn`` is a two-digit label. The label must
            # follow an atom (``prev`` set); the second occurrence of the same
            # label closes the ring, bonding the two endpoint atoms. An explicit
            # bond token written immediately before the label (``pending_tok``
            # open, e.g. ``C=1``) gives the ring bond that order; otherwise it is
            # an order-1 bond. ``0`` is not a valid ring digit (it falls through
            # to ``ring-bond-no-atom``/``organic-atom`` handling via ``%``-only).
            read = _read_ring_label(smiles, i)
            if read is None:
                # A ``%`` not followed by two digits is a malformed ring label.
                raise Unsupported(
                    "smiles", "ring-bond-malformed",
                    f"'%' at offset {i} is not followed by two digits",
                )
            label, width = read
            if prev is None:
                raise Unsupported(
                    "smiles", "ring-bond-no-atom",
                    f"ring-closure label {label!r} at offset {i} has no atom "
                    "on its left",
                )
            # An open bond token feeds its explicit order into *this* ring bond
            # (and is thereby consumed — it is not a dangling bond).
            explicit_order: int | None = pending_order if pending_tok is not None else None
            pending_order = 1
            pending_tok = None
            if label in open_rings:
                open_atom, open_order, _off = open_rings.pop(label)
                if open_atom == prev:
                    raise Unsupported(
                        "smiles", "ring-bond-self",
                        f"ring-closure label {label!r} at offset {i} closes onto "
                        "its own opening atom",
                    )
                # Reconcile the two ends' explicit orders: if both ends wrote an
                # explicit order they must agree; otherwise the explicit one (or
                # the default 1) wins. Mismatch is a typed abort, not a silent pick.
                if (
                    open_order is not None
                    and explicit_order is not None
                    and open_order != explicit_order
                ):
                    raise Unsupported(
                        "smiles", "ring-bond-order-mismatch",
                        f"ring-closure label {label!r} opened with bond order "
                        f"{open_order} but closed with order {explicit_order} "
                        f"at offset {i}",
                    )
                order = explicit_order if explicit_order is not None else open_order
                if order is None:
                    order = 1
                a, b = (open_atom, prev) if open_atom < prev else (prev, open_atom)
                bonds.append((a, b))
                orders.append(order)
            else:
                open_rings[label] = (prev, explicit_order, i)
            i += width
            continue
        if ch.islower():
            # Lowercase letters start an aromatic atom (c, n, o, ...). (A trailing
            # 'l'/'r' of Cl/Br was already consumed by ``_next_atom`` above.)
            raise Unsupported("smiles", "aromatic-atom", f"{ch!r} at offset {i}")
        # An uppercase symbol that is not an in-scope organic atom: name it as an
        # out-of-scope element rather than as garbage, so the histogram is honest.
        raise Unsupported("smiles", f"organic-atom:{ch}", f"at offset {i}")

    # A bond token left open at end-of-string has no right-hand atom: dangling.
    if pending_tok is not None:
        off, construct = pending_tok
        raise Unsupported(
            "smiles", "dangling-bond",
            f"{construct} token at offset {off} is the last token, no atom after it",
        )
    # A branch left open at end-of-string is unbalanced (never a silent drop).
    if stack:
        raise Unsupported(
            "smiles", "unbalanced-branch", f"{len(stack)} unclosed '(' at end"
        )
    # A ring-closure label opened but never closed is malformed (never a silent
    # drop). Report the first such label by its *opening offset* (a deterministic,
    # host-independent order, not dict-iteration order).
    if open_rings:
        label, (_atom, _ord, off) = min(open_rings.items(), key=lambda kv: kv[1][2])
        raise Unsupported(
            "smiles", "ring-bond-unclosed",
            f"ring-closure label {label!r} opened at offset {off} is never closed",
        )

    # Hydrogen count per atom:
    #  - a **bare** atom gets *implicit* H from the per-element valence rule: its
    #    degree is the *sum of its bond orders* (chain, branch, *and ring-closure*
    #    bonds), then H = max(0, V - deg). A ring-closure bond is an ordinary
    #    entry in ``bonds``/``orders``, so it adds to the degree of *both* its
    #    endpoints just like any other bond. Before filling, any bare atom whose
    #    incident bond-order sum exceeds its normal valence is rejected
    #    (``valence-exceeded``) so the ``max(0, ...)`` clamp can never silently
    #    turn an over-bonded atom into a wrong (H-free) formula.
    #  - a **bracket** atom keeps its *explicit* H (``explicit_h[k]``) and is
    #    exempt from the valence rule and the valence check: any element at any
    #    bond degree is accepted (its hydrogens are written, not inferred), so the
    #    degree is computed for completeness but never compared to a valence.
    n = len(elements)
    bonds_t = tuple(bonds)
    orders_t = tuple(orders)
    deg = [0] * n
    for (a, b), order in zip(bonds_t, orders_t):
        deg[a] += order
        deg[b] += order
    for k in range(n):
        if is_bracket[k]:
            continue  # bracket atom: no normal valence, never over-bonded here
        valence = ORGANIC_VALENCE[elements[k]]
        if deg[k] > valence:
            raise Unsupported(
                "smiles", "valence-exceeded",
                f"atom {elements[k]} (#{k}) has bond-order sum {deg[k]} > "
                f"normal valence {valence}",
            )
    atoms = tuple(
        Atom(
            elements[k],
            explicit_h[k] if is_bracket[k] else ORGANIC_VALENCE[elements[k]] - deg[k],
            is_bracket[k],
        )
        for k in range(n)
    )
    return MolGraph(atoms=atoms, bonds=bonds_t, orders=orders_t)
