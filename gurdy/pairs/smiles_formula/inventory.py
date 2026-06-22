"""Construct-coverage inventory for ``smiles-formula`` (BENCHMARKS.md §2).

The denominator is the spec-enumerable set of OpenSMILES syntactic constructs
(the implementer does not get to shrink it). Each probe is a minimal SMILES
string exercising one construct; a construct is *covered* iff its probe
translates without a typed ``Unsupported`` abort, *missing* otherwise. The
missing set is the ``unsupported`` histogram — the honest gap.

This slice covers the **organic-subset single-bonded tree** — bare atoms
``B C N O P S F Cl Br I`` joined by implicit single bonds, optionally with nested
parenthesized **branches** ``(...)``, with implicit hydrogens filled from the
per-element normal valence over a degree that counts branch bonds
(``organic-chain``, the heteroatom probes, and ``branch``). Every other
construct (rings, multiple/explicit bonds, aromatic and bracket atoms,
charges, isotopes, stereo, disconnection) aborts. Measured coverage: ``6/17``.
"""

from __future__ import annotations

# The in-scope constructs. ``organic-chain`` is a *mixed-element* single-bonded
# chain (ethanol ``CCO`` -> ``C2H6O``), which subsumes the old carbon-only chain
# and demonstrates element mixing in one probe; ``branch`` is the parenthesized
# sub-chain (``C(C)C`` -> ``C3H8``). The per-element / per-molecule / branch
# valence tests live in ``tests/test_smiles_formula.py``. The four heteroatom
# probes — out of scope (carbon-only) before the 0.2 widening — and ``branch``
# (out of scope before the 0.3 widening) are now covered too.
IN_SCOPE_PROBES: dict[str, str] = {
    "organic-chain": "CCO",
    "organic-atom-N": "N",
    "organic-atom-O": "O",
    "organic-atom-Cl": "Cl",
    "organic-atom-Br": "Br",
    "branch": "C(C)C",
}

# Every other spec-enumerable OpenSMILES construct, each with a probe that *must*
# hard-abort ``Unsupported``. These are the denominator's out-of-scope share.
OUT_OF_SCOPE_PROBES: dict[str, str] = {
    "ring-bond": "C1CCCCC1",
    "double-bond": "C=C",
    "triple-bond": "C#C",
    "aromatic-atom": "c1ccccc1",
    "bracket-atom": "[CH4]",
    "charge": "[NH4+]",
    "isotope": "[13C]",
    "stereo": "[C@H]",
    "stereo-bond": "F/C=C/F",
    "disconnection": "C.C",
    "explicit-single-bond": "C-C",
}

# What the coverage harness measures (BENCHMARKS.md §5). The harness counts a
# probe as covered iff translation does not raise ``Unsupported``.
ALL_PROBES: dict[str, str] = {**IN_SCOPE_PROBES, **OUT_OF_SCOPE_PROBES}
