r"""Construct-coverage inventory for ``smiles-formula`` (BENCHMARKS.md §2).

The denominator is the spec-enumerable set of OpenSMILES syntactic constructs
(the implementer does not get to shrink it). Each probe is a minimal SMILES
string exercising one construct; a construct is *covered* iff its probe
translates without a typed ``Unsupported`` abort, *missing* otherwise. The
missing set is the ``unsupported`` histogram — the honest gap.

This slice covers the **organic-subset graph joined by single / double / triple
bonds — chains, branches, and rings — plus bracket atoms** — bare atoms
``B C N O P S F Cl Br I`` joined by implicit single bonds, the explicit single
bond ``-``, **double** bonds ``=`` (order 2) or **triple** bonds ``#`` (order 3),
optionally with nested parenthesized **branches** ``(...)`` and **ring-closure
bonds** (a digit ``1``-``9`` or ``%nn`` label), with implicit hydrogens filled
from the per-element normal valence over a degree that is the *sum of bond
orders*; **and bracket atoms** ``[...]`` (any element, with explicit H — no
implicit hydrogen, and exempt from the valence rule — carrying an optional
isotope / chirality / charge / atom class, none of which change the atom
multiset); **and the two projection-invisible constructs**: **stereo
(directional) bonds** ``/`` ``\`` (order-1 bonds whose cis/trans direction is
parsed and discarded — the multiset keeps no geometry) and the
**dot-disconnection** ``.`` (a component break that adds no bond — the multiset
is the union over components); **and aromaticity** — bare lowercase atoms
``b c n o p s``, lowercase bracket symbols (``[nH]``, ``[se]``) and the explicit
aromatic bond ``:``, with an aromatic atom spending one valence unit on its
ring's aromatic system (clamped at zero, which is what makes benzene's ``c``
carry a hydrogen and furan's ``o`` none).
In-scope probes: ``organic-chain``, the heteroatom probes, ``branch``,
``double-bond``, ``triple-bond``, ``explicit-single-bond``, ``ring-bond``, the
four bracket-atom probes ``bracket-atom`` (explicit-H, ``[CH4]``), ``charge``
(``[NH4+]``), ``isotope`` (``[13C]``), ``stereo`` (``[C@H]``), ``stereo-bond``
(``F/C=C/F``), ``disconnection`` (``C.C``), and now ``aromatic-atom``
(``c1ccccc1``). ``OUT_OF_SCOPE_PROBES`` is empty: every probe of this inventory
is covered.
Measured coverage: ``17/17``.

**What 17/17 does *not* say.** The seventeen probes are the constructs this
inventory enumerated at the 1/17 carbon-only start, and the ratchet has never
grown or shrunk that denominator. Three OpenSMILES tokens were never given a
probe of their own and still hard-abort: the **quadruple bond** ``$``, the
**wildcard atom** ``*`` / ``[*]``, and the reaction arrow ``>``/``>>``. So
17/17 means "every enumerated construct is covered", not "every OpenSMILES
string parses" — naming the residual three here is cheaper than a denominator
the ratchet cannot compare across versions (BENCHMARKS.md §2).
"""

from __future__ import annotations

# The in-scope constructs. ``organic-chain`` is a *mixed-element* single-bonded
# chain (ethanol ``CCO`` -> ``C2H6O``), which subsumes the old carbon-only chain
# and demonstrates element mixing in one probe; ``branch`` is the parenthesized
# sub-chain (``C(C)C`` -> ``C3H8``); ``double-bond`` / ``triple-bond`` /
# ``explicit-single-bond`` are the bond-order tokens (ethene ``C=C`` -> ``C2H4``,
# ethyne ``C#C`` -> ``C2H2``, the explicit single bond ``C-C`` -> ``C2H6``);
# ``ring-bond`` is the ring-closure construct (cyclohexane ``C1CCCCC1`` ->
# ``C6H12``); ``stereo-bond`` is the directional order-1 bond pair ``/`` ``\``
# (trans-difluoroethene ``F/C=C/F`` -> ``C2H2F2``; the direction is discarded —
# the multiset keeps no geometry); ``disconnection`` is the component break ``.``
# (``C.C`` -> ``C2H8``, two methanes — one H *more* than bonded ``CC``, since
# neither carbon spends a bond on the other); and the four bracket-atom probes
# exercise the OpenSMILES bracket
# syntax ``[...]`` through the fields the molecular-formula projection must read
# or skip: ``bracket-atom`` is the explicit-H base case (``[CH4]`` -> ``CH4``),
# ``charge`` a charged bracket atom (``[NH4+]`` -> ``H4N``; charge does not change
# the neutral atom multiset), ``isotope`` an isotope label (``[13C]`` -> ``C``;
# same element), and ``stereo`` a chirality marker (``[C@H]`` -> ``CH``; geometry,
# not counts). The per-element / per-molecule / branch / bond-order / ring /
# bracket valence tests live in ``tests/test_smiles_formula.py``. The four
# heteroatom probes (out of scope before the 0.2 widening), ``branch`` (before
# 0.3), the three bond-order probes (before 0.4), ``ring-bond`` (before 0.5), and
# the four bracket-atom probes (before the 0.6 widening), plus ``stereo-bond``
# and ``disconnection`` (before 0.7) and ``aromatic-atom`` (before 0.8), are now
# covered. ``aromatic-atom``'s probe is benzene ``c1ccccc1`` -> ``C6H6``: the one
# construct ``π`` does *not* discard, since an aromatic atom's implicit hydrogen
# count is not its aliphatic one (six aromatic carbons carry six hydrogens where
# six single-bonded ring carbons would carry twelve).
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
    "bracket-atom": "[CH4]",
    "charge": "[NH4+]",
    "isotope": "[13C]",
    "stereo": "[C@H]",
    "stereo-bond": "F/C=C/F",
    "disconnection": "C.C",
    "aromatic-atom": "c1ccccc1",
}

# Every other spec-enumerable OpenSMILES construct, each with a probe that *must*
# hard-abort ``Unsupported``. These are the denominator's out-of-scope share, and
# at 0.8 it is **empty**: ``aromatic-atom`` left it, exactly as ``stereo-bond``
# and ``disconnection`` did at 0.7, the four bracket-atom probes at 0.6,
# ``ring-bond`` at 0.5, and the three bond-order probes at 0.4. The denominator
# (17) is unchanged throughout — the ratchet only moves probes covered<->missing,
# it never grows or shrinks the inventory — so the coverage fraction stays
# comparable across every version from 1/17 to 17/17. An empty out-of-scope set
# is not a claim that nothing aborts: the malformed-input aborts (dangling bond,
# valence exceeded, malformed branch / ring / bracket, misplaced dot, an aromatic
# atom off a ring) are typed rejections of *ill-formed* strings, not unsupported
# constructs, and the three unprobed tokens named in the module docstring
# (``$``, ``*``, ``>``) still hard-abort.
OUT_OF_SCOPE_PROBES: dict[str, str] = {}

# What the coverage harness measures (BENCHMARKS.md §5). The harness counts a
# probe as covered iff translation does not raise ``Unsupported``.
ALL_PROBES: dict[str, str] = {**IN_SCOPE_PROBES, **OUT_OF_SCOPE_PROBES}
