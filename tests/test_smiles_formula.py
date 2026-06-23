"""Tests for the ``smiles-formula`` compile pair (PAIRING.md §7 minimum).

Covers: determinism twice-and-diff (translator + both new interpreters);
per-element / per-molecule / per-branch / per-bond-order / per-ring translation
against the spec; the commuting-square check ``I_s(p) ≡_π L(I_t(T(p)))`` on a
heteroatom + branched + multiply-bonded + ring corpus; carry-back replay through
``L``; the registration smoke test; and the honest ``unsupported`` histogram (the
organic-subset graph of single/double/triple bonds — chains, branches, rings — in
scope, every other construct aborting).

Widenings exercised here:
- *0.2*, organic-subset heteroatoms: a linear single-bonded chain may mix the
  organic-subset bare atoms ``B C N O P S F Cl Br I`` (alongside carbon ``C``).
- *0.3*, branches ``(...)``: a parenthesized sub-chain bonds its first atom to
  the parent atom it follows, possibly nested; an atom's degree now counts its
  branch bonds. The implicit-H rule ``max(0, normal_valence - degree)`` is
  unchanged. A malformed branch (unbalanced/empty parens, ``(`` with no parent)
  is a typed abort, never a silent wrong formula.
- *0.4*, double ``=`` / triple ``#`` (and explicit single ``-``) bonds: a bond
  token between two atoms sets the order of the bond joining them; an atom's
  degree is now the *sum of its bond orders*, so ``implicit_H =
  normal_valence - Σ bond_orders`` (``C=C`` -> ``C2H4``, ``C#C`` -> ``C2H2``,
  ``C=O`` -> ``CH2O``, ``O=C=O`` -> ``CO2``, ``CC#N`` -> ``C2H3N``). A dangling
  bond token (no atom on one side) is a ``dangling-bond`` abort; a bond order
  exceeding an atom's valence (``F=C``) is a ``valence-exceeded`` abort, never a
  silent wrong formula.
- *0.5*, ring-closure bonds: a digit ``1``-``9`` or two-digit ``%nn`` label after
  an atom marks a ring-bond endpoint; the second occurrence of the same label
  closes the ring by bonding the two endpoint atoms. The ring bond's order is 1
  by default, or the order of a bond token written immediately before the label
  (``C=1...C1``); the two ends' explicit orders must agree. A ring-closure bond
  counts toward *both* endpoints' degree, so the implicit-H rule is unchanged
  (cyclohexane ``C1CCCCC1`` -> ``C6H12``, cyclopropane ``C1CC1`` -> ``C3H6``,
  cyclohexene ``C1=CCCCC1`` -> ``C6H10``, 1,4-dioxane ``O1CCOCC1`` -> ``C4H8O2``).
  An unclosed label, a label with no atom on its left, a self-ring, mismatched
  ring-bond orders, and a ``%`` not followed by two digits are each their own
  typed abort, never a silent wrong formula.

Run with: ``python -m unittest`` (no third-party runner).
"""

import unittest

from gurdy.core import coverage, oracle, registry
from gurdy.core.errors import Unsupported

# Importing the pair registers it (and the two shared interpreters).
from gurdy.pairs.smiles_formula import PROJECTION, lift, square, translate
from gurdy.languages.molecular_formula import canonical_atoms, parse, run as run_formula, to_hill
from gurdy.languages.molecular_formula.hill import hill_order
from gurdy.languages.smiles import INTERPRETER_VERSION, run as run_smiles
from gurdy.languages.smiles.graph import ORGANIC_VALENCE, parse as parse_smiles
from gurdy.pairs.smiles_formula.inventory import ALL_PROBES, IN_SCOPE_PROBES, OUT_OF_SCOPE_PROBES

# The carbon-chain corpus: the alkane series across a few lengths (the 0.1
# behavior, which 0.2 must preserve unchanged).
CARBON_CORPUS = {
    "C": "CH4",
    "CC": "C2H6",
    "CCC": "C3H8",
    "CCCC": "C4H10",
    "CCCCCCCCCC": "C10H22",  # n-decane: C10 H(2*10+2)
}

# The heteroatom corpus: lone heteroatoms and mixed-element single-bonded chains.
# Hill order is fixed by the spec — C first (if present), then H, then the rest
# alphabetically — so e.g. ammonia is ``H3N`` and borane ``H3B`` (the spec's
# "H always second" convention, NOT strict-IUPAC carbon-free alphabetization).
HETERO_CORPUS = {
    # Lone heteroatoms: H = normal_valence (one atom, degree 0).
    "N": "H3N",
    "O": "H2O",
    "P": "H3P",
    "S": "H2S",
    "F": "HF",
    "Cl": "HCl",
    "Br": "HBr",
    "I": "HI",
    "B": "H3B",
    # Mixed two-atom chains (one single bond, each atom degree 1).
    "CN": "CH5N",     # methylamine
    "CO": "CH4O",     # methanol heavy atoms (C-O)
    "CF": "CH3F",     # fluoromethane
    "CCl": "CH3Cl",   # chloromethane
    "CBr": "CH3Br",
    "CS": "CH4S",     # methanethiol
    # Longer mixed chains.
    "CCO": "C2H6O",   # ethanol
    "OCC": "C2H6O",   # same molecule written the other way -> same multiset
    "CCN": "C2H7N",   # ethylamine
    "NCO": "CH5NO",   # N-C-O: each terminal degree 1, middle C degree 2
    "OCCO": "C2H6O2",
}

# The branch corpus (0.3): parenthesized sub-chains, nested and multiple, single
# bonds only. Degree counts branch bonds; H = max(0, normal_valence - degree).
# All formulas are derived from the pinned valence rule (and match real
# chemistry: isobutane, neopentane, dimethyl ether, ...).
BRANCH_CORPUS = {
    # One branch off the first atom: C0 has degree 2 (branch C1 + chain C2).
    "C(C)C": "C3H8",      # propane (central C deg 2 -> 2H; two CH3 -> 3H each)
    "C(O)C": "C2H6O",     # dimethyl ether: C deg2, O branch deg1, C deg1
    "N(C)C": "C2H7N",     # dimethylamine: N deg2 -> 1H, two CH3
    "C(C)N": "C2H7N",     # same multiset, branch is carbon instead
    # A branch in the middle of a chain: the classic isobutane spelling.
    "CC(C)C": "C4H10",    # isobutane (the brief's canonical branch example)
    "CC(O)C": "C3H8O",    # isopropanol: central C deg3 -> 1H, OH branch
    # Multiple branches off one atom.
    "C(C)(C)C": "C4H10",  # isobutane written with two branches (central deg 3)
    "CC(C)(C)C": "C5H12", # neopentane: quaternary central C (deg 4 -> 0H)
    "C(N)(O)C": "C2H7NO", # central C deg3: NH2 + OH + CH3 branches
    # Nested branches.
    "C(C(C)C)C": "C5H12", # neopentane skeleton via a branch inside a branch
    "C(C(C)(C)C)C": "C6H14",  # deeper nesting
    "OC(C)C": "C3H8O",    # isopropanol written leading with the O
    # A branch whose sub-chain is itself multi-atom.
    "C(CC)C": "C4H10",    # n-butane spelled with a 2-atom branch (== CCCC)
    "C(CO)N": "C2H7NO",   # 2-aminoethanol skeleton: N-C-C-O
}

# The multiple-bond corpus (0.4): double ``=`` (order 2) and triple ``#`` (order
# 3) bonds, plus the explicit single bond ``-`` (order 1). Each atom's degree is
# the *sum* of its incident bond orders; H = normal_valence - degree. All
# formulas match real chemistry (ethene, ethyne, formaldehyde, CO2, ...).
MULTIBOND_CORPUS = {
    # The brief's named examples.
    "C=C": "C2H4",     # ethene: each C deg 2 -> 2H
    "C#C": "C2H2",     # ethyne: each C deg 3 -> 1H
    "C=O": "CH2O",     # formaldehyde: C deg2 -> 2H, O deg2 -> 0H
    "O=C=O": "CO2",    # carbon dioxide: central C deg 4, both O deg 2 -> 0H all
    "CC#N": "C2H3N",   # acetonitrile: CH3 (deg1), C (deg4: 1+3), N (deg3) -> 0H
    "C-C": "C2H6",     # ethane via the explicit single bond (== CC)
    # More multiply-bonded molecules.
    "N#N": "N2",       # dinitrogen: each N deg 3 -> 0H
    "C#N": "CHN",      # hydrogen cyanide: C deg3 -> 1H, N deg3 -> 0H
    "O=O": "O2",       # dioxygen: each O deg 2 -> 0H
    "C=N": "CH3N",     # methanimine: C deg2 -> 2H, N deg2 -> 1H
    "CC=O": "C2H4O",   # acetaldehyde: CH3, C deg3 (1+2) -> 1H, O deg2 -> 0H
    "C=CC=C": "C4H6",  # 1,3-butadiene: terminal C deg2 -> 2H, inner C deg3 -> 1H
    "C=CC": "C3H6",    # propene
    "CC#C": "C3H4",    # propyne
    "N=O": "HNO",      # nitrosyl H: N deg2 -> 1H, O deg2 -> 0H
    # Double/triple bonds inside a branch (the bond token sits before the branch
    # atom; the branch's first bond takes that order).
    "C(=O)O": "CH2O2",   # formic acid: C deg3 (=O is 2, -O is 1) -> 1H
    "CC(=O)O": "C2H4O2", # acetic acid
    "CC(=O)C": "C3H6O",  # acetone: central C deg4 (1+2+1) -> 0H
    "C(=O)(O)O": "CH2O3",  # carbonic acid: C deg4 -> 0H, =O deg2, two -OH
    "CC(=N)C": "C3H7N",  # an imine in a branch
    # Mixed explicit single + double in one string.
    "C-C=C": "C3H6",   # propene with a leading explicit single bond (== CC=C)
}

# The ring corpus (0.5): ring-closure bonds. A digit ``1``-``9`` or two-digit
# ``%nn`` label after an atom marks a ring-bond endpoint; the second occurrence of
# the same label closes the ring (bonding the two endpoint atoms). A ring-closure
# bond counts toward *both* endpoints' degree, so H = normal_valence - degree as
# before. All formulas match real chemistry (cyclohexane, cyclopropane, ...).
RING_CORPUS = {
    # The brief's named examples.
    "C1CCCCC1": "C6H12",   # cyclohexane: 6 ring C, each deg 2 -> 2H
    "C1CC1": "C3H6",       # cyclopropane: 3 ring C, each deg 2 -> 2H
    "C1=CCCCC1": "C6H10",  # cyclohexene: the C=C lowers two C's H by one each
    "O1CCOCC1": "C4H8O2",  # 1,4-dioxane: 2 ring O (deg2 -> 0H), 4 ring C (deg2 -> 2H)
    # More cycloalkanes (the ring closes the chain into a cycle, removing 2 H vs
    # the open chain: C_n H_2n).
    "C1CC1": "C3H6",       # cyclopropane (again, kept for the series)
    "C1CCC1": "C4H8",      # cyclobutane
    "C1CCCC1": "C5H10",    # cyclopentane
    "C1CCCCCC1": "C7H14",  # cycloheptane
    # A ring with a substituent (the ring carbon bearing the methyl has deg 3).
    "CC1CCCCC1": "C7H14",  # methylcyclohexane
    # Hetero rings.
    "O1CCCC1": "C4H8O",    # tetrahydrofuran (oxolane)
    "C1CCOCC1": "C5H10O",  # tetrahydropyran
    "N1CCCCC1": "C5H11N",  # piperidine (ring N deg2 -> 1H)
    "C1CCNCC1": "C5H11N",  # piperidine written from a ring carbon
    # Unsaturated rings (a ring double bond, written at the open or close end).
    "C1=CC1": "C3H4",      # cyclopropene
    "C=1CCCCC=1": "C6H10", # cyclohexene with the ring-bond order at *both* ends
    "C1=CC=CC=C1": "C6H6", # Kekulé benzene (three alternating ring double bonds)
    # Two-digit ``%nn`` ring label (same molecule as ``C1CCCCC1``).
    "C%10CCCCC%10": "C6H12",
    # Fused / bridged bicyclics (two ring-closure labels open at once).
    "C1CCC2CCCCC2C1": "C10H18",   # decalin (two fused 6-rings)
    "C12CCCCC1CCCCC2": "C11H20",  # a bridged bicyclic
    # Two *separate* rings in one string (the label ``1`` is reused after it
    # closes — a fresh ring, not the same one).
    "C1CCCCC1C1CCCCC1": "C12H22", # bicyclohexyl (two cyclohexanes, single bond)
    # A ring whose atoms also bear branches.
    "C1CC(C)CC1C": "C7H14",  # dimethylcyclopentane skeleton
}


class TestPerConstruct(unittest.TestCase):
    """The schema is reproducible byte-for-byte (PAIRING.md §2, §7)."""

    def test_carbon_chain_unchanged(self):
        # 0.1 behavior preserved: the carbon chain still maps as before.
        for smiles, formula in CARBON_CORPUS.items():
            self.assertEqual(translate(smiles), formula.encode("utf-8"), msg=smiles)

    def test_alkane_general_formula(self):
        # C_n -> C_n H_(2n+2), the pinned valence rule applied across lengths.
        for n in range(1, 21):
            smiles = "C" * n
            h = 2 * n + 2
            expected = f"C{'' if n == 1 else n}H{h}"
            self.assertEqual(translate(smiles).decode("utf-8"), expected, msg=smiles)

    def test_heteroatom_molecules_match_spec(self):
        for smiles, formula in HETERO_CORPUS.items():
            self.assertEqual(
                translate(smiles).decode("utf-8"), formula, msg=smiles
            )

    def test_branch_molecules_match_spec(self):
        # 0.3: branched skeletons map by the same pinned valence rule, degree
        # now counting branch bonds. Includes the brief's examples and nesting.
        for smiles, formula in BRANCH_CORPUS.items():
            self.assertEqual(
                translate(smiles).decode("utf-8"), formula, msg=smiles
            )

    def test_branch_canonical_examples(self):
        # The brief's named branch examples (chemically: propane, isobutane,
        # neopentane, dimethyl ether, dimethylamine).
        self.assertEqual(translate("C(C)C"), b"C3H8")       # propane
        self.assertEqual(translate("CC(C)C"), b"C4H10")     # isobutane
        self.assertEqual(translate("C(C)(C)C"), b"C4H10")   # isobutane (2 branches)
        self.assertEqual(translate("CC(C)(C)C"), b"C5H12")  # neopentane
        self.assertEqual(translate("C(O)C"), b"C2H6O")      # dimethyl ether
        self.assertEqual(translate("N(C)C"), b"C2H7N")      # dimethylamine

    def test_multibond_molecules_match_spec(self):
        # 0.4: double/triple/explicit-single bonds map by the same pinned valence
        # rule, degree now being the *sum of bond orders*.
        for smiles, formula in MULTIBOND_CORPUS.items():
            self.assertEqual(
                translate(smiles).decode("utf-8"), formula, msg=smiles
            )

    def test_multibond_canonical_examples(self):
        # The brief's named bond-order examples (ethene, ethyne, formaldehyde,
        # carbon dioxide, acetonitrile).
        self.assertEqual(translate("C=C"), b"C2H4")    # ethene
        self.assertEqual(translate("C#C"), b"C2H2")    # ethyne
        self.assertEqual(translate("C=O"), b"CH2O")    # formaldehyde
        self.assertEqual(translate("O=C=O"), b"CO2")   # carbon dioxide
        self.assertEqual(translate("CC#N"), b"C2H3N")  # acetonitrile

    def test_explicit_single_bond_equals_implicit(self):
        # The explicit single bond ``-`` is order 1, identical to the implicit
        # bond: every ``-`` spelling equals its bond-token-free spelling.
        self.assertEqual(translate("C-C"), translate("CC"))      # ethane
        self.assertEqual(translate("C-C-C"), translate("CCC"))   # propane
        self.assertEqual(translate("C-C=C"), translate("CC=C"))  # propene
        self.assertEqual(translate("O-C"), translate("OC"))      # methanol heavy

    def test_ring_molecules_match_spec(self):
        # 0.5: ring-closure bonds map by the same pinned valence rule, the ring
        # bond counting toward both endpoints' degree.
        for smiles, formula in RING_CORPUS.items():
            self.assertEqual(
                translate(smiles).decode("utf-8"), formula, msg=smiles
            )

    def test_ring_canonical_examples(self):
        # The brief's named ring examples (cyclohexane, cyclopropane, cyclohexene,
        # 1,4-dioxane).
        self.assertEqual(translate("C1CCCCC1"), b"C6H12")  # cyclohexane
        self.assertEqual(translate("C1CC1"), b"C3H6")      # cyclopropane
        self.assertEqual(translate("C1=CCCCC1"), b"C6H10") # cyclohexene
        self.assertEqual(translate("O1CCOCC1"), b"C4H8O2") # 1,4-dioxane

    def test_ring_two_digit_label(self):
        # A ``%nn`` label denotes the same ring bond as a one-digit label: the
        # molecule ``C%10CCCCC%10`` is cyclohexane, identical to ``C1CCCCC1``.
        self.assertEqual(translate("C%10CCCCC%10"), translate("C1CCCCC1"))
        self.assertEqual(translate("C%10CCCCC%10"), b"C6H12")
        # A two-digit label with a leading zero (``%01``) is still a valid label.
        self.assertEqual(translate("C%01CCCCC%01"), b"C6H12")

    def test_fused_and_separate_rings(self):
        # Two ring labels open at once -> a fused bicyclic (decalin). And a label
        # reused after it has closed opens a *fresh* ring, not the same one.
        self.assertEqual(translate("C1CCC2CCCCC2C1"), b"C10H18")  # decalin (fused)
        # Bicyclohexyl: two separate cyclohexanes joined by a single bond; the
        # label ``1`` is reused for the second (independent) ring.
        self.assertEqual(translate("C1CCCCC1C1CCCCC1"), b"C12H22")

    def test_ring_closes_chain_removing_two_hydrogens(self):
        # Closing an open chain into a ring removes exactly two implicit H (the two
        # terminal atoms each gain one bond): C_n chain is C_n H_(2n+2); the
        # n-membered carbon *ring* is C_n H_2n.
        for n in range(3, 9):
            ring = "C1" + "C" * (n - 1) + "1"   # C1 C...C 1, an n-membered ring
            self.assertEqual(
                translate(ring).decode("utf-8"), f"C{n}H{2 * n}", msg=ring
            )

    def test_ring_bond_order_at_either_end(self):
        # The ring bond's order may be written at the opening OR the closing end
        # (or both, if they agree); all denote the same ring double bond.
        self.assertEqual(translate("C=1CCCCC1"), b"C6H10")   # order at open end
        self.assertEqual(translate("C1CCCCC=1"), b"C6H10")   # order at close end
        self.assertEqual(translate("C=1CCCCC=1"), b"C6H10")  # both ends (agree)
        self.assertEqual(
            translate("C=1CCCCC1"), translate("C1=CCCCC1")  # cyclohexene two ways
        )

    def test_bond_inside_branch_is_covered(self):
        # A double/triple bond inside a branch is now in scope (0.4): the branch's
        # first bond takes the pending order. (Before 0.4, ``C(=O)C`` aborted.)
        self.assertEqual(translate("C(=O)O"), b"CH2O2")    # formic acid
        self.assertEqual(translate("CC(=O)O"), b"C2H4O2")  # acetic acid
        self.assertEqual(translate("CC(=O)C"), b"C3H6O")   # acetone

    def test_implicit_h_degree_is_sum_of_bond_orders(self):
        # 0.4: a double/triple bond raises the incident atoms' degree by its
        # order. C=C: each C deg 2 -> 2H. C#C: each C deg 3 -> 1H. O=C=O: the
        # central C is deg 4 (two double bonds), the two O are deg 2 -> 0H all.
        self.assertEqual(
            [(a.element, a.implicit_h) for a in parse_smiles("C=C").atoms],
            [("C", 2), ("C", 2)],
        )
        self.assertEqual(
            [(a.element, a.implicit_h) for a in parse_smiles("C#C").atoms],
            [("C", 1), ("C", 1)],
        )
        self.assertEqual(
            [(a.element, a.implicit_h) for a in parse_smiles("O=C=O").atoms],
            [("O", 0), ("C", 0), ("O", 0)],
        )
        # CC#N (acetonitrile): CH3 (deg1 -> 3H), the nitrile C (deg 1+3=4 -> 0H),
        # the nitrile N (deg3 -> 0H).
        self.assertEqual(
            [(a.element, a.implicit_h) for a in parse_smiles("CC#N").atoms],
            [("C", 3), ("C", 0), ("N", 0)],
        )

    def test_bond_orders_recorded_on_the_graph(self):
        # The graph carries the per-bond order parallel to ``bonds``; a
        # bond-token-free string is all order-1 (byte-for-byte the 0.3 shape).
        self.assertEqual(parse_smiles("C=C").orders, (2,))
        self.assertEqual(parse_smiles("C#C").orders, (3,))
        self.assertEqual(parse_smiles("O=C=O").orders, (2, 2))
        self.assertEqual(parse_smiles("CC#N").orders, (1, 3))
        # No bond token -> every order is 1, and ``bonds`` is unchanged.
        self.assertEqual(parse_smiles("CCC").orders, (1, 1))
        self.assertEqual(parse_smiles("CCC").bonds, ((0, 1), (1, 2)))
        # Explicit single bond is order 1 (same as implicit).
        self.assertEqual(parse_smiles("C-C").orders, (1,))

    def test_ring_bond_recorded_on_the_graph(self):
        # 0.5: the ring-closure bond is an ordinary entry in ``bonds``/``orders``.
        # Cyclopropane ``C1CC1``: the chain bonds (0,1),(1,2) plus the ring bond
        # (0,2) closing C2 back to C0, all order 1.
        g = parse_smiles("C1CC1")
        self.assertEqual(g.bonds, ((0, 1), (1, 2), (0, 2)))
        self.assertEqual(g.orders, (1, 1, 1))
        # Cyclohexene ``C1=CCCCC1``: here the ``=`` sits after the ring-open ``1``
        # and *before* the next atom, so the *chain* bond (0,1) is the double bond
        # and the ring bond (0,5) is a plain single bond.
        g = parse_smiles("C1=CCCCC1")
        self.assertIn((0, 5), g.bonds)
        self.assertEqual(g.orders[g.bonds.index((0, 5))], 1)  # ring bond: single
        self.assertEqual(g.orders[g.bonds.index((0, 1))], 2)  # chain bond: double
        # ``C=1CCCCC1`` instead writes the ``=`` *before* the ring digit, so the
        # *ring* bond (0,5) is the double bond.
        g2 = parse_smiles("C=1CCCCC1")
        self.assertEqual(g2.orders[g2.bonds.index((0, 5))], 2)  # ring bond: double

    def test_ring_bond_degree_counts_both_endpoints(self):
        # A ring-closure bond raises the degree (lowers the implicit-H) of *both*
        # its endpoint atoms. Cyclohexane ``C1CCCCC1``: every ring carbon is deg 2
        # (two chain/ring bonds) -> 2 implicit H each.
        self.assertEqual(
            [(a.element, a.implicit_h) for a in parse_smiles("C1CCCCC1").atoms],
            [("C", 2)] * 6,
        )
        # Cyclopropane ``C1CC1``: each of the 3 carbons deg 2 -> 2H.
        self.assertEqual(
            [a.implicit_h for a in parse_smiles("C1CC1").atoms], [2, 2, 2]
        )
        # Cyclohexene ``C1=CCCCC1``: the two double-bonded carbons are deg 3 -> 1H,
        # the other four are deg 2 -> 2H.
        self.assertEqual(
            [a.implicit_h for a in parse_smiles("C1=CCCCC1").atoms],
            [1, 1, 2, 2, 2, 2],
        )

    def test_branch_is_order_independent(self):
        # A branch off an atom and a straight chain through it denote the same
        # molecule when they have the same multiset: n-butane two ways.
        self.assertEqual(translate("C(CC)C"), translate("CCCC"))
        # Writing the OH as a branch or in-line gives the same isopropanol.
        self.assertEqual(translate("CC(O)C"), translate("OC(C)C"))

    def test_lone_heteroatom_hydrogen_count_is_normal_valence(self):
        # A lone bare atom (degree 0) carries exactly its normal valence in H.
        for element, valence in ORGANIC_VALENCE.items():
            atoms = parse_smiles(element).atoms
            self.assertEqual(len(atoms), 1, msg=element)
            self.assertEqual(atoms[0].element, element, msg=element)
            self.assertEqual(atoms[0].implicit_h, valence, msg=element)

    def test_implicit_h_degrees_carbon(self):
        # Lone / terminal / interior carbons get 4 / 3 / 2 implicit H.
        self.assertEqual([a.implicit_h for a in parse_smiles("C").atoms], [4])
        self.assertEqual([a.implicit_h for a in parse_smiles("CC").atoms], [3, 3])
        self.assertEqual([a.implicit_h for a in parse_smiles("CCC").atoms], [3, 2, 3])

    def test_implicit_h_degrees_heteroatom(self):
        # CCO: C(4-1=3), C(4-2=2), O(2-1=1).
        self.assertEqual(
            [(a.element, a.implicit_h) for a in parse_smiles("CCO").atoms],
            [("C", 3), ("C", 2), ("O", 1)],
        )
        # NCO: N(3-1=2), C(4-2=2), O(2-1=1).
        self.assertEqual(
            [(a.element, a.implicit_h) for a in parse_smiles("NCO").atoms],
            [("N", 2), ("C", 2), ("O", 1)],
        )

    def test_implicit_h_degree_counts_branch_bonds(self):
        # 0.3: a branch bond raises the parent atom's degree just like a chain
        # bond. CC(C)(C)C -> central C (atom index 1) is bonded to four carbons
        # (deg 4 -> 0 implicit H); the four terminal CH3 are deg 1 -> 3H each.
        atoms = parse_smiles("CC(C)(C)C").atoms
        self.assertEqual(
            [(a.element, a.implicit_h) for a in atoms],
            [("C", 3), ("C", 0), ("C", 3), ("C", 3), ("C", 3)],
        )
        # C(C)C: parent C0 deg 2 (branch + chain) -> 2H; both other C deg 1 -> 3H.
        self.assertEqual(
            [(a.element, a.implicit_h) for a in parse_smiles("C(C)C").atoms],
            [("C", 2), ("C", 3), ("C", 3)],
        )

    def test_branch_bond_connectivity(self):
        # The branch bonds the sub-chain's first atom to the parent, and the main
        # chain resumes from the parent. CC(C)C: atom1 is the parent of both the
        # branch (atom2) and the resumed chain (atom3).
        g = parse_smiles("CC(C)C")
        self.assertEqual(g.bonds, ((0, 1), (1, 2), (1, 3)))
        # Branch-free chains are byte-for-byte unchanged from the 0.2 behavior.
        self.assertEqual(parse_smiles("CCC").bonds, ((0, 1), (1, 2)))
        self.assertEqual(parse_smiles("CCCC").bonds, ((0, 1), (1, 2), (2, 3)))

    def test_two_letter_halogens_are_one_atom(self):
        # 'Cl' / 'Br' read as a single atom, not element + stray lowercase.
        self.assertEqual([a.element for a in parse_smiles("Cl").atoms], ["Cl"])
        self.assertEqual([a.element for a in parse_smiles("Br").atoms], ["Br"])
        # In a chain: C-Cl is two atoms (carbon, chlorine).
        self.assertEqual(
            [a.element for a in parse_smiles("CCl").atoms], ["C", "Cl"]
        )
        self.assertEqual(
            [a.element for a in parse_smiles("CBr").atoms], ["C", "Br"]
        )

    def test_interpreter_version_bumped(self):
        # AGENTS.md §3: the additive ring-closure widening bumps the shared
        # interpreter version (0.4 -> 0.5).
        self.assertEqual(INTERPRETER_VERSION, "0.5")


class TestUnsupported(unittest.TestCase):
    """Out-of-scope constructs hard-abort with a named typed error
    (BENCHMARKS.md §3) — never a silent drop or a mis-parse."""

    def test_every_out_of_scope_probe_aborts(self):
        for name, probe in OUT_OF_SCOPE_PROBES.items():
            with self.assertRaises(Unsupported, msg=f"{name}: {probe!r}") as cm:
                translate(probe)
            self.assertEqual(cm.exception.language, "smiles", msg=name)

    def test_named_constructs(self):
        cases = {
            "c1ccccc1": "aromatic-atom",
            "[CH4]": "bracket-atom",
            "[NH4+]": "bracket-atom",
            "C.C": "disconnection",
            "C$C": "quadruple-bond",     # quadruple bond still out of scope
            "C:C": "aromatic-bond",      # aromatic bond still out of scope
            "F/C=C/F": "stereo-bond",    # F in scope -> abort reaches the '/'
        }
        for smiles, construct in cases.items():
            with self.assertRaises(Unsupported) as cm:
                translate(smiles)
            self.assertEqual(cm.exception.construct, construct, msg=smiles)

    def test_dangling_bond_is_typed_abort_not_silent(self):
        # 0.4: a bond token with no atom on one side hard-aborts ``dangling-bond``
        # (never a silent drop). Both ends, doubled tokens, and before/after a
        # branch are all covered.
        cases = (
            "=C",      # token at the string start (no left atom)
            "#C",
            "-C",
            "C=",      # token at the end (no right atom)
            "C#",
            "C-",
            "C==C",    # two tokens in a row
            "C=#C",
            "C#-C",
            "C=(C)C",  # token immediately before '(' (no atom between)
            "C(=)C",   # token immediately before ')' (no atom after)
            "=",       # a lone token
        )
        for smiles in cases:
            with self.assertRaises(Unsupported, msg=smiles) as cm:
                translate(smiles)
            self.assertEqual(cm.exception.language, "smiles", msg=smiles)
            self.assertEqual(cm.exception.construct, "dangling-bond", msg=smiles)

    def test_valence_exceeded_is_typed_abort_not_silent(self):
        # 0.4: a bond order exceeding an atom's normal valence hard-aborts
        # ``valence-exceeded`` rather than silently clamping H to 0 (which would
        # be a wrong formula). Fluorine/halogens (valence 1), oxygen (2), etc.
        for smiles in ("F=C", "C=F", "Cl#C", "O#C", "C#O", "O=O=O"):
            with self.assertRaises(Unsupported, msg=smiles) as cm:
                translate(smiles)
            self.assertEqual(cm.exception.language, "smiles", msg=smiles)
            self.assertEqual(cm.exception.construct, "valence-exceeded", msg=smiles)
        # Sanity: ``F-F`` (two single-bonded fluorines) is *valid* (deg 1 each),
        # not an abort.
        self.assertEqual(translate("F-F"), b"F2")

    def test_malformed_branch_is_typed_abort_not_silent(self):
        # 0.3: branches are in scope, but a *malformed* branch must still
        # hard-abort with a typed error (never a silent wrong formula).
        cases = {
            "C(": "unbalanced-branch",       # unclosed
            "C(C": "unbalanced-branch",      # unclosed with content
            "C)": "unbalanced-branch",       # unmatched close
            "CC)": "unbalanced-branch",
            "C(C))": "unbalanced-branch",    # one extra close
            "(C)C": "branch-without-parent", # '(' with no preceding atom
            "()": "branch-without-parent",
            "((C))": "branch-without-parent",
            "C()C": "empty-branch",          # a branch that consumes no atom
        }
        for smiles, construct in cases.items():
            with self.assertRaises(Unsupported, msg=smiles) as cm:
                translate(smiles)
            self.assertEqual(cm.exception.language, "smiles", msg=smiles)
            self.assertEqual(cm.exception.construct, construct, msg=smiles)

    def test_malformed_ring_is_typed_abort_not_silent(self):
        # 0.5: rings are in scope, but a *malformed* ring closure must still
        # hard-abort with a typed error (never a silent wrong formula).
        cases = {
            "C1CC": "ring-bond-unclosed",      # an open ring digit, never closed
            "C1": "ring-bond-unclosed",        # a lone open ring digit
            "C1CCC2CC1": "ring-bond-unclosed", # label 2 opened, never closed
            "1CCC1": "ring-bond-no-atom",      # a ring digit with no atom on its left
            "%12CC%12": "ring-bond-no-atom",   # a ``%nn`` label with no left atom
            "C11": "ring-bond-self",           # a label closing onto its own atom
            "C=1CCCCC#1": "ring-bond-order-mismatch",  # open order 2, close 3
            "C#1CCCCC=1": "ring-bond-order-mismatch",
            "C%1CC": "ring-bond-malformed",    # ``%`` with only one digit
            "C%": "ring-bond-malformed",       # a bare ``%`` at end-of-string
            "C%1": "ring-bond-malformed",      # ``%`` + one digit at end
        }
        for smiles, construct in cases.items():
            with self.assertRaises(Unsupported, msg=smiles) as cm:
                translate(smiles)
            self.assertEqual(cm.exception.language, "smiles", msg=smiles)
            self.assertEqual(cm.exception.construct, construct, msg=smiles)

    def test_ring_bond_exceeding_valence_aborts(self):
        # A ring-closure bond that pushes an atom over its normal valence is a
        # ``valence-exceeded`` abort (the ring bond counts toward degree), never a
        # silent wrong formula. ``F1CC1``: fluorine (valence 1) in a ring has the
        # ring bond + a chain bond = degree 2.
        for smiles in ("F1CC1", "O1=CC1"):
            with self.assertRaises(Unsupported, msg=smiles) as cm:
                translate(smiles)
            self.assertEqual(cm.exception.language, "smiles", msg=smiles)
            self.assertEqual(cm.exception.construct, "valence-exceeded", msg=smiles)

    def test_unsupported_constructs_inside_a_branch_still_abort(self):
        # A still-unsupported construct does not become reachable just by sitting
        # inside a branch: a bracket atom / quadruple bond / aromatic atom in a
        # branch aborts. (Double/triple bonds — 0.4 — and rings — 0.5 — inside a
        # branch are now *in* scope; see test_bond_inside_branch_is_covered and
        # test_ring_inside_a_branch_is_covered.)
        cases = {
            "C([CH3])C": "bracket-atom",
            "C(C$C)C": "quadruple-bond",
            "C(c1ccccc1)C": "aromatic-atom",
        }
        for smiles, construct in cases.items():
            with self.assertRaises(Unsupported, msg=smiles) as cm:
                translate(smiles)
            self.assertEqual(cm.exception.construct, construct, msg=smiles)

    def test_ring_inside_a_branch_is_covered(self):
        # A ring closure inside a branch is in scope at 0.5 (the branch's sub-chain
        # can itself form a ring): a cyclopropyl group hung off a chain carbon.
        self.assertEqual(translate("C(C1CC1)C"), b"C5H10")  # (cyclopropyl)propane skel

    def test_lowercase_aromatic_atoms_still_abort(self):
        # The widening adds *uppercase* bare atoms only; lowercase aromatic
        # variants of the very same elements still hard-abort.
        for s in ("c", "n", "o", "s", "p", "b", "cc", "CcC"):
            with self.assertRaises(Unsupported, msg=s) as cm:
                translate(s)
            self.assertEqual(cm.exception.construct, "aromatic-atom", msg=s)

    def test_unknown_uppercase_element_named(self):
        # An uppercase symbol outside the organic subset is named, not garbage.
        with self.assertRaises(Unsupported) as cm:
            translate("X")
        self.assertEqual(cm.exception.construct, "organic-atom:X")

    def test_empty_string_aborts(self):
        with self.assertRaises(Unsupported) as cm:
            translate("")
        self.assertEqual(cm.exception.construct, "empty-string")


class TestDeterminism(unittest.TestCase):
    """Twice-and-diff on the translator and BOTH new interpreters
    (PAIRING.md §5)."""

    ALL = {**CARBON_CORPUS, **HETERO_CORPUS, **BRANCH_CORPUS, **MULTIBOND_CORPUS,
           **RING_CORPUS}

    def test_translator_byte_identical(self):
        for smiles in self.ALL:
            self.assertEqual(translate(smiles), translate(smiles), msg=smiles)

    def test_smiles_interpreter_byte_identical(self):
        for smiles in self.ALL:
            self.assertEqual(run_smiles(smiles), run_smiles(smiles), msg=smiles)

    def test_formula_interpreter_byte_identical(self):
        for formula in self.ALL.values():
            self.assertEqual(run_formula(formula), run_formula(formula), msg=formula)

    def test_hill_order_is_canonical_not_iteration_order(self):
        # Same multiset built in different dict-insertion orders -> identical Hill.
        a = {"H": 4, "C": 1}
        b = {"C": 1, "H": 4}
        self.assertEqual(to_hill(a), to_hill(b))
        self.assertEqual(to_hill(a), "CH4")
        # Other elements sort alphabetically after C, H.
        self.assertEqual(to_hill({"O": 1, "H": 2}), "H2O")
        self.assertEqual(to_hill({"Cl": 1, "Na": 1}), "ClNa")
        self.assertEqual(hill_order(["O", "C", "H", "Br"]), ["C", "H", "Br", "O"])

    def test_heteroatom_multiset_built_order_independent(self):
        # The same heteroatom molecule written two ways yields byte-identical
        # output (the multiset, not the writing order, determines the formula).
        self.assertEqual(translate("CCO"), translate("OCC"))
        self.assertEqual(translate("CN"), translate("NC"))

    def test_branch_spelling_order_independent(self):
        # A branched and a straight spelling of the same molecule (same multiset)
        # produce byte-identical output, regardless of branch order.
        self.assertEqual(translate("C(CC)C"), translate("CCCC"))     # n-butane
        self.assertEqual(translate("C(C)(C)C"), translate("CC(C)C")) # isobutane

    def test_explicit_single_bond_spelling_order_independent(self):
        # The explicit single bond ``-`` is order 1, so a string with explicit
        # single bonds is byte-identical to its implicit-bond spelling.
        self.assertEqual(translate("C-C-C"), translate("CCC"))
        self.assertEqual(translate("O=C-C"), translate("O=CC"))

    def test_ring_spelling_order_independent(self):
        # The same ring molecule written different ways (a one-digit vs ``%nn``
        # label, the ring-bond order at the open vs close end) is byte-identical;
        # the multiset, not the spelling, fixes the formula.
        self.assertEqual(translate("C1CCCCC1"), translate("C%10CCCCC%10"))  # label
        self.assertEqual(translate("C=1CCCCC1"), translate("C1CCCCC=1"))     # order end
        # A ring label is just a digit -> determinism holds across hash seeds (the
        # ``open_rings`` dict is keyed by label, consulted in parse order, so its
        # iteration order never reaches the output bytes).
        self.assertEqual(translate("C1CCC2CCCCC2C1"), translate("C1CCC2CCCCC2C1"))


class TestCommutingSquare(unittest.TestCase):
    """I_s(p) ≡_π L(I_t(T(p))) on a heteroatom + branched + multiply-bonded
    corpus (PAIRING.md §7)."""

    def test_square_commutes(self):
        for smiles in {**CARBON_CORPUS, **HETERO_CORPUS, **BRANCH_CORPUS,
                       **MULTIBOND_CORPUS, **RING_CORPUS}:
            report = square(smiles)
            self.assertTrue(report.ok, msg=f"{smiles}: {report.divergence}")

    def test_square_commutes_on_branches(self):
        # Explicit branch coverage of the commuting square (the brief's corpus).
        for smiles in BRANCH_CORPUS:
            report = square(smiles)
            self.assertTrue(report.ok, msg=f"{smiles}: {report.divergence}")

    def test_square_commutes_on_multibonds(self):
        # Explicit double/triple-bond coverage of the commuting square (the
        # brief's multi-bond corpus: ethene, ethyne, CO2, acetonitrile, ...).
        for smiles in MULTIBOND_CORPUS:
            report = square(smiles)
            self.assertTrue(report.ok, msg=f"{smiles}: {report.divergence}")

    def test_square_commutes_on_rings(self):
        # Explicit ring coverage of the commuting square (the brief's ring corpus:
        # cyclohexane, cyclopropane, cyclohexene, 1,4-dioxane, decalin, %nn, ...).
        for smiles in RING_CORPUS:
            report = square(smiles)
            self.assertTrue(report.ok, msg=f"{smiles}: {report.divergence}")

    def test_square_localizes_a_planted_divergence(self):
        # Sanity: a wrong right-hand multiset is caught and localized under π.
        left = run_smiles("CCO")           # C2H6O
        wrong = lift(run_formula("CH4"))   # a deliberately wrong formula
        report = oracle.align(left, wrong, PROJECTION)
        self.assertFalse(report.ok)
        self.assertEqual(report.divergence.step, 0)
        self.assertIn(report.divergence.field, ("atoms", "formula"))


class TestCarryBack(unittest.TestCase):
    """The target formula behavior replays through L back to the source-level
    atom multiset (PAIRING.md §7)."""

    def test_carry_back_to_atom_multiset(self):
        for smiles, formula in {**CARBON_CORPUS, **HETERO_CORPUS, **BRANCH_CORPUS,
                                **MULTIBOND_CORPUS, **RING_CORPUS}.items():
            # Target side: interpret the emitted formula.
            target_trace = run_formula(formula)
            carried = lift(target_trace)
            # The carried-back observable is exactly the source atom multiset.
            source_atoms = canonical_atoms(parse(formula))
            self.assertEqual(carried[0]["atoms"], source_atoms, msg=smiles)
            # And it equals what the source interpreter independently produced.
            self.assertEqual(
                carried[0]["atoms"], run_smiles(smiles)[0]["atoms"], msg=smiles
            )

    def test_carry_back_branch(self):
        # A branched molecule's target formula replays through L to the source
        # multiset, equalling what I_s produced directly (the brief's carry-back).
        for smiles in ("CC(C)C", "C(C)(C)C", "C(CO)N"):
            formula = translate(smiles).decode("utf-8")
            carried = lift(run_formula(formula))
            self.assertEqual(
                carried[0]["atoms"], run_smiles(smiles)[0]["atoms"], msg=smiles
            )

    def test_carry_back_multibond(self):
        # A multiply-bonded molecule's target formula replays through L to the
        # source multiset (the brief's carry-back over the multi-bond corpus).
        for smiles in ("C=C", "C#C", "O=C=O", "CC#N", "CC(=O)O"):
            formula = translate(smiles).decode("utf-8")
            carried = lift(run_formula(formula))
            self.assertEqual(
                carried[0]["atoms"], run_smiles(smiles)[0]["atoms"], msg=smiles
            )

    def test_carry_back_ring(self):
        # A ring molecule's target formula replays through L to the source
        # multiset (the brief's carry-back over the ring corpus: cyclohexane,
        # cyclopropane, cyclohexene, 1,4-dioxane, decalin, the %nn label).
        for smiles in ("C1CCCCC1", "C1CC1", "C1=CCCCC1", "O1CCOCC1",
                       "C1CCC2CCCCC2C1", "C%10CCCCC%10"):
            formula = translate(smiles).decode("utf-8")
            carried = lift(run_formula(formula))
            self.assertEqual(
                carried[0]["atoms"], run_smiles(smiles)[0]["atoms"], msg=smiles
            )

    def test_carry_back_alkane_multiset(self):
        # The carbon chain's carried-back multiset is exactly C_n H_(2n+2).
        for smiles in CARBON_CORPUS:
            formula = CARBON_CORPUS[smiles]
            carried = lift(run_formula(formula))
            as_dict = dict(carried[0]["atoms"])
            n = len(smiles)
            self.assertEqual(as_dict, {"C": n, "H": 2 * n + 2}, msg=smiles)


class TestRegistration(unittest.TestCase):
    """Registration smoke test: the pair is listed and every edge-op of its
    square is callable (PAIRING.md §7)."""

    def test_pair_registered_and_edges_callable(self):
        self.assertIn("smiles-formula", registry.list_pairs())
        pair = registry.get_pair("smiles-formula")
        self.assertEqual(pair.source, "smiles")
        self.assertEqual(pair.target, "molecular-formula")
        self.assertEqual(pair.fidelity, "predicted")
        # Shared interpreters are wired from the languages it touches.
        self.assertIsNotNone(pair.source_interpreter)   # I_s
        self.assertIsNotNone(pair.target_interpreter)   # I_t
        # Every edge-operation of the square is callable (on a heteroatom input).
        artifact = pair.translator("CCO")                      # T
        self.assertEqual(artifact, b"C2H6O")
        src = pair.source_interpreter("CCO")                   # I_s
        tgt = pair.target_interpreter(artifact.decode("utf-8"))  # I_t
        carried = pair.target_to_source(tgt)                   # L
        self.assertTrue(oracle.align(src, carried, pair.projection).ok)

    def test_languages_registered(self):
        langs = registry.list_languages()
        self.assertIn("smiles", langs)
        self.assertIn("molecular-formula", langs)


class TestCoverageHistogram(unittest.TestCase):
    """Honest coverage: the organic-subset graph of single/double/triple bonds
    (chains + branches + bond orders + rings) in scope, every other construct
    aborting; the histogram is itemized (BENCHMARKS.md §3, §5). The ratchet only
    grows — 1/17 (carbon-only) -> 5/17 (heteroatoms, 0.2) -> 6/17 (branches, 0.3)
    -> 9/17 (double/triple/explicit-single bonds, 0.4) -> 10/17 (rings, 0.5)."""

    def test_coverage_and_histogram(self):
        report = coverage.measure(translate, ALL_PROBES)
        self.assertEqual(report.covered, set(IN_SCOPE_PROBES))
        self.assertEqual(report.total, len(ALL_PROBES))
        self.assertEqual(report.total, 17)
        # The ring widening: ten in-scope constructs covered (was nine).
        self.assertEqual(len(report.covered), 10)
        self.assertEqual(set(report.missing), set(OUT_OF_SCOPE_PROBES))
        histogram = report.histogram
        self.assertGreater(len(histogram), 0)
        # Every missing probe is itemized by its named construct.
        for construct, count in histogram.items():
            self.assertIsInstance(construct, str)
            self.assertGreaterEqual(count, 1)
        # The ring-bond construct is no longer in the histogram (covered at 0.5).
        self.assertNotIn("ring-bond", histogram)
        self.assertIn("ring-bond", report.covered)
        # The three bond-order constructs (covered at 0.4) are still covered.
        for now_covered in ("double-bond", "triple-bond", "explicit-single-bond"):
            self.assertNotIn(now_covered, histogram)
            self.assertIn(now_covered, report.covered)
        # `branch` is still covered (ratchet: nothing dropped).
        self.assertNotIn("branch", histogram)
        # The previously-covered constructs are still covered (ratchet: nothing
        # dropped).
        self.assertIn("organic-chain", report.covered)
        self.assertIn("branch", report.covered)
        for hetero in ("organic-atom-N", "organic-atom-O",
                       "organic-atom-Cl", "organic-atom-Br"):
            self.assertIn(hetero, report.covered)

    def test_ratchet_did_not_drop_anything(self):
        # Coverage only grows: everything covered before the ring widening
        # (carbon chain + the four heteroatom probes + branch + the three
        # bond-order probes) is still covered.
        report = coverage.measure(translate, ALL_PROBES)
        for previously_covered in ("organic-chain", "organic-atom-N",
                                   "organic-atom-O", "organic-atom-Cl",
                                   "organic-atom-Br", "branch",
                                   "double-bond", "triple-bond",
                                   "explicit-single-bond"):
            self.assertIn(previously_covered, report.covered)


if __name__ == "__main__":
    unittest.main()
