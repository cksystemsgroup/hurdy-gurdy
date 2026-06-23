"""The shared SMILES language + interpreter (languages/smiles brief).

Registers the ``smiles`` language with its deterministic **source** interpreter
(``I_s``): an OpenSMILES-subset reader that parses the in-scope organic-subset
graph of bare atoms joined by single / double / triple bonds (chains, with
branches and rings) — and now **bracket atoms** ``[...]`` (any element, explicit
H) — to a molecular graph and exposes its atom multiset. Shared by every SMILES
pair (currently ``smiles-formula``). Out-of-scope constructs hard-abort with a
typed ``Unsupported`` (BENCHMARKS.md §3).

Interpreter version (the shared deliverable's contract — AGENTS.md §3): a
versioned bump is required for any *additive* semantics change so dependent
pairs (currently ``smiles-formula``) re-validate their commuting square against
this version. Each widening is additive — every string accepted at the previous
version is still accepted and parses identically — but bumping the version is a
versioned event regardless.
- ``0.6`` — *additive* widening to **bracket atoms** ``[...]``: the OpenSMILES
  bracket-atom syntax ``[ isotope? symbol chirality? hcount? charge? class? ]``.
  A bracket atom may name **any element** (``[Se]``, ``[Na]``, ``[Fe]``, plus the
  organic ones in brackets), gets **no implicit hydrogen** (its H count is the
  explicit ``H<n>`` field — ``[NH4+]`` -> 4 H, ``[CH3]`` -> 3 H, ``[C]`` -> 0 H),
  and is *exempt from the valence rule* (its bond-order sum is never checked). The
  isotope (``[13C]`` is still carbon), charge (``+``/``-``/``+2``…), chirality
  (``@``/``@@``) and atom class (``:n``) are parsed and validated but do **not**
  change the atom multiset, so for the molecular-formula projection only the
  symbol and the explicit H count matter (``[NH4+]`` -> ``H4N``, ``[13C]`` ->
  ``C``, ``[OH-]`` -> ``HO``, ``[C@H]`` -> ``CH``, ``[Se]`` -> ``Se``). A bracket
  atom bonds in chains/branches/rings exactly like a bare atom, but those bonds
  neither add nor remove its (explicit) hydrogen. Behavior on any string with no
  bracket atom is byte-for-byte identical to ``0.5``. **Aromatic (lowercase)
  atoms still hard-abort** ``aromatic-atom`` — bare (``c``) *and* in brackets
  (``[se]``, ``[n]``); aromaticity is a separate later round. A malformed bracket
  (unclosed ``[``, empty ``[]``, unknown element ``[Xx]``, or a bad
  H-count/charge/isotope/class field) is a typed abort (``bracket-atom-unclosed``
  / ``bracket-atom-empty`` / ``bracket-atom-element`` / ``bracket-atom-malformed``),
  never a silent wrong formula.
- ``0.5`` — *additive* widening to **ring-closure bonds**: a digit ``1``-``9``,
  or a two-digit ``%nn`` label, written after an atom marks a ring-bond endpoint,
  and the second occurrence of the same label closes the ring by bonding the two
  endpoint atoms. The ring bond's order is 1 by default, or the order of a bond
  token (``=``/``#``/``-``) written immediately before the label (``C=1...C1``);
  the two ends' explicit orders must agree. A ring-closure bond counts toward
  *both* endpoints' degree, so implicit H = ``normal_valence − Σ bond_orders`` as
  before (cyclohexane ``C1CCCCC1`` -> ``C6H12``, cyclopropane ``C1CC1`` ->
  ``C3H6``, cyclohexene ``C1=CCCCC1`` -> ``C6H10``, 1,4-dioxane ``O1CCOCC1`` ->
  ``C4H8O2``). Behavior on any string with no ring label is byte-for-byte
  identical to ``0.4``. A malformed ring closure — an unclosed label
  (``ring-bond-unclosed``), a label with no atom on its left
  (``ring-bond-no-atom``), a self-ring (``ring-bond-self``), mismatched bond
  orders on the two ends (``ring-bond-order-mismatch``), or a ``%`` not followed
  by two digits (``ring-bond-malformed``) — is a typed abort, never a silent
  wrong formula; a ring bond exceeding an atom's valence still aborts
  ``valence-exceeded``. Aromatic (lowercase) and bracket atoms still hard-abort.
- ``0.4`` — *additive* widening to **double** ``=`` (order 2) and **triple**
  ``#`` (order 3) bonds, plus the **explicit single bond** ``-`` (order 1, same
  as implicit). A bond token between two atoms sets the order of the bond joining
  them; an atom's degree is now the *sum of its bond orders*, and the implicit-H
  rule becomes ``normal_valence - Σ bond_orders`` (single still = 1): ethene
  ``C=C`` -> ``C2H4``, ethyne ``C#C`` -> ``C2H2``, formaldehyde ``C=O`` ->
  ``CH2O``, carbon dioxide ``O=C=O`` -> ``CO2``, acetonitrile ``CC#N`` ->
  ``C2H3N``. Single-bond/branch behavior (every string with no bond token) is
  byte-for-byte identical to ``0.3``. A dangling bond token (no atom on one side)
  hard-aborts ``dangling-bond``; a bond order exceeding an atom's valence (e.g.
  ``F=C``) hard-aborts ``valence-exceeded``, never a silently clamped formula.
  Rings (added at 0.5), the quadruple/aromatic bonds, aromatic and bracket atoms
  still hard-abort at this version.
- ``0.3`` — *additive* widening to **branches** ``(...)``: a parenthesized
  sub-chain bonds its first atom to the parent atom it follows, and the main
  chain resumes from that parent, possibly nested (``C(C)C`` -> ``C3H8``,
  ``CC(C)C`` -> ``C4H10`` isobutane, ``C(C)(C)C`` -> ``C4H10``, ``C(O)C`` ->
  ``C2H6O``). Still single bonds only; an atom's degree now counts its branch
  bonds, and the implicit-H rule ``max(0, normal_valence - degree)`` is
  unchanged. Branch-free behavior is byte-for-byte identical to ``0.2``. A
  malformed branch (unbalanced/empty parens, ``(`` with no parent) hard-aborts.
  Rings, multiple/explicit bonds, aromatic and bracket atoms still hard-abort.
- ``0.2`` — *additive* widening from carbon-only to the full **organic subset**
  of bare atoms with their OpenSMILES normal valences (``B`` 3, ``C`` 4, ``N``
  3, ``O`` 2, ``P`` 3, ``S`` 2, ``F``/``Cl``/``Br``/``I`` 1), so a linear
  single-bonded chain may mix elements (``CCO`` -> ``C2H6O``, ``O`` -> ``H2O``,
  ``CCl`` -> ``CH3Cl``). The implicit-H rule generalizes to
  ``max(0, normal_valence - single-bond degree)``. Carbon-chain behavior is
  unchanged. Branches, rings, multiple/explicit bonds, aromatic and bracket
  atoms still hard-abort.
- ``0.1`` — the organic-subset *carbon* chain with implicit-hydrogen valence
  filling (``C``, ``CC``, ...; carbon valence 4).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from .graph import Atom, MolGraph, parse
from .interp import run

# AGENTS.md §3: bumped to 0.6 when bracket-atom support ``[...]`` was added (an
# additive parse change reading the bracket grammar — any element, explicit H, no
# valence fill or check; isotope/charge/chirality/class parsed but not counted;
# strings with no bracket atom parse byte-for-byte as at 0.5). 0.5 had bumped for
# ring-closure bonds, 0.4 for double ``=`` / triple ``#`` (and explicit single
# ``-``) bonds, 0.3 for branch ``(...)`` support, 0.2 from carbon-only to the
# whole organic subset.
INTERPRETER_VERSION = "0.6"

__all__ = ["run", "parse", "Atom", "MolGraph", "INTERPRETER_VERSION"]

register_language(Language("smiles", source_interpreter=run))
