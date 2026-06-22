"""Construct-coverage inventory for ``smiles-formula`` (BENCHMARKS.md §2).

The denominator is the spec-enumerable set of OpenSMILES syntactic constructs
(the implementer does not get to shrink it). Each probe is a minimal SMILES
string exercising one construct; a construct is *covered* iff its probe
translates without a typed ``Unsupported`` abort, *missing* otherwise. The
missing set is the ``unsupported`` histogram — the honest gap.

This thin slice covers exactly one construct — the organic-subset carbon chain
with implicit hydrogens (``organic-carbon-chain``) — and aborts on every other
construct. That is the deliverable's measured coverage: ``1/N``.
"""

from __future__ import annotations

# The in-scope construct (one probe is enough; the chain length is covered by
# the per-construct unit tests).
IN_SCOPE_PROBES: dict[str, str] = {
    "organic-carbon-chain": "CCC",
}

# Every other spec-enumerable OpenSMILES construct, each with a probe that *must*
# hard-abort ``Unsupported``. These are the denominator's out-of-scope share.
OUT_OF_SCOPE_PROBES: dict[str, str] = {
    "branch": "C(C)C",
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
    "organic-atom-N": "N",
    "organic-atom-O": "O",
    "organic-atom-Cl": "Cl",
    "organic-atom-Br": "Br",
    "explicit-single-bond": "C-C",
}

# What the coverage harness measures (BENCHMARKS.md §5). The harness counts a
# probe as covered iff translation does not raise ``Unsupported``.
ALL_PROBES: dict[str, str] = {**IN_SCOPE_PROBES, **OUT_OF_SCOPE_PROBES}
