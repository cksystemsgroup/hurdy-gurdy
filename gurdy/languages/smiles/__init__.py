"""The shared SMILES language + interpreter (languages/smiles brief).

Registers the ``smiles`` language with its deterministic **source** interpreter
(``I_s``): an OpenSMILES-subset reader that parses the in-scope organic-subset
single-bonded tree (chains, with branches) to a molecular graph and exposes its
atom multiset. Shared by every SMILES pair (currently ``smiles-formula``).
Out-of-scope constructs hard-abort with a typed ``Unsupported`` (BENCHMARKS.md
§3).

Interpreter version (the shared deliverable's contract — AGENTS.md §3): a
versioned bump is required for any *additive* semantics change so dependent
pairs (currently ``smiles-formula``) re-validate their commuting square against
this version. Each widening is additive — every string accepted at the previous
version is still accepted and parses identically — but bumping the version is a
versioned event regardless.
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

# AGENTS.md §3: bumped to 0.3 when branch ``(...)`` support was added (an additive
# parse change; branch-free chains parse byte-for-byte as at 0.2). 0.2 had bumped
# from carbon-only to the whole organic subset (an additive valence-table change).
INTERPRETER_VERSION = "0.3"

__all__ = ["run", "parse", "Atom", "MolGraph", "INTERPRETER_VERSION"]

register_language(Language("smiles", source_interpreter=run))
