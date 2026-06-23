"""Construct-coverage inventory for ``smiles-formula`` (BENCHMARKS.md §2).

The denominator is the spec-enumerable set of OpenSMILES syntactic constructs
(the implementer does not get to shrink it). Each probe is a minimal SMILES
string exercising one construct; a construct is *covered* iff its probe
translates without a typed ``Unsupported`` abort, *missing* otherwise. The
missing set is the ``unsupported`` histogram — the honest gap.

This slice covers the **organic-subset graph joined by single / double / triple
bonds — chains, branches, and rings** — bare atoms ``B C N O P S F Cl Br I``
joined by implicit single bonds, the explicit single bond ``-``, **double** bonds
``=`` (order 2) or **triple** bonds ``#`` (order 3), optionally with nested
parenthesized **branches** ``(...)`` and **ring-closure bonds** (a digit
``1``-``9`` or ``%nn`` label), with implicit hydrogens filled from the per-element
normal valence over a degree that is the *sum of bond orders* (``organic-chain``,
the heteroatom probes, ``branch``, ``double-bond``, ``triple-bond``,
``explicit-single-bond``, ``ring-bond``). Every other construct (the
quadruple/aromatic bonds, aromatic and bracket atoms, charges, isotopes, stereo,
disconnection) aborts. Measured coverage: ``10/17``.
"""

from __future__ import annotations

# The in-scope constructs. ``organic-chain`` is a *mixed-element* single-bonded
# chain (ethanol ``CCO`` -> ``C2H6O``), which subsumes the old carbon-only chain
# and demonstrates element mixing in one probe; ``branch`` is the parenthesized
# sub-chain (``C(C)C`` -> ``C3H8``); ``double-bond`` / ``triple-bond`` /
# ``explicit-single-bond`` are the bond-order tokens (ethene ``C=C`` -> ``C2H4``,
# ethyne ``C#C`` -> ``C2H2``, the explicit single bond ``C-C`` -> ``C2H6``);
# ``ring-bond`` is the ring-closure construct (cyclohexane ``C1CCCCC1`` ->
# ``C6H12``). The per-element / per-molecule / branch / bond-order / ring valence
# tests live in ``tests/test_smiles_formula.py``. The four heteroatom probes (out
# of scope before the 0.2 widening), ``branch`` (before 0.3), the three bond-order
# probes (before 0.4), and ``ring-bond`` (before the 0.5 widening) are now covered.
IN_SCOPE_PROBES: dict[str, str] = {
    "organic-chain": "CCO",
    "organic-atom-N": "N",
    "organic-atom-O": "O",
    "organic-atom-Cl": "Cl",
    "organic-atom-Br": "Br",
    "branch": "C(C)C",
    "double-bond": "C=C",
    "triple-bond": "C#C",
    "explicit-single-bond": "C-C",
    "ring-bond": "C1CCCCC1",
}

# Every other spec-enumerable OpenSMILES construct, each with a probe that *must*
# hard-abort ``Unsupported``. These are the denominator's out-of-scope share. The
# denominator (17) is fixed: the ``ring-bond`` probe that moved into scope at 0.5
# left this set (it shrank from 8 to 7), exactly as the three bond-order probes
# left at 0.4; the total 17 is unchanged (the ratchet only moves probes
# covered<->missing, it never grows or shrinks the inventory).
OUT_OF_SCOPE_PROBES: dict[str, str] = {
    "aromatic-atom": "c1ccccc1",
    "bracket-atom": "[CH4]",
    "charge": "[NH4+]",
    "isotope": "[13C]",
    "stereo": "[C@H]",
    "stereo-bond": "F/C=C/F",
    "disconnection": "C.C",
}

# What the coverage harness measures (BENCHMARKS.md §5). The harness counts a
# probe as covered iff translation does not raise ``Unsupported``.
ALL_PROBES: dict[str, str] = {**IN_SCOPE_PROBES, **OUT_OF_SCOPE_PROBES}
