"""Tests for the ``smiles-formula`` compile pair (PAIRING.md §7 minimum).

Covers: determinism twice-and-diff (translator + both new interpreters);
per-element / per-molecule translation against the spec; the commuting-square
check ``I_s(p) ≡_π L(I_t(T(p)))`` on a heteroatom corpus; carry-back replay
through ``L``; the registration smoke test; and the honest ``unsupported``
histogram (the organic-subset chain in scope, every other construct aborting).

This is the *organic-subset heteroatom* widening (smiles interpreter 0.2): a
linear single-bonded chain may now mix the organic-subset bare atoms
``B C N O P S F Cl Br I`` (alongside the original carbon ``C``), implicit H from
``max(0, normal_valence - degree)``.

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
        # AGENTS.md §3: the additive widening bumps the shared interpreter version.
        self.assertEqual(INTERPRETER_VERSION, "0.2")


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
            "C=C": "double-bond",
            "C#C": "triple-bond",
            "C(C)C": "branch",
            "C1CCCCC1": "ring-bond",
            "c1ccccc1": "aromatic-atom",
            "[CH4]": "bracket-atom",
            "[NH4+]": "bracket-atom",
            "C.C": "disconnection",
            "C-C": "explicit-single-bond",
            "F/C=C/F": "stereo-bond",  # F now in scope -> abort reaches the '/'
        }
        for smiles, construct in cases.items():
            with self.assertRaises(Unsupported) as cm:
                translate(smiles)
            self.assertEqual(cm.exception.construct, construct, msg=smiles)

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

    ALL = {**CARBON_CORPUS, **HETERO_CORPUS}

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


class TestCommutingSquare(unittest.TestCase):
    """I_s(p) ≡_π L(I_t(T(p))) on a heteroatom corpus (PAIRING.md §7)."""

    def test_square_commutes(self):
        for smiles in {**CARBON_CORPUS, **HETERO_CORPUS}:
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
        for smiles, formula in {**CARBON_CORPUS, **HETERO_CORPUS}.items():
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
    """Honest coverage: the organic-subset chain (+ heteroatom probes) in scope,
    every other construct aborting; the histogram is itemized (BENCHMARKS.md
    §3, §5). The ratchet only grows — 1/17 (carbon-only) -> 5/17."""

    def test_coverage_and_histogram(self):
        report = coverage.measure(translate, ALL_PROBES)
        self.assertEqual(report.covered, set(IN_SCOPE_PROBES))
        self.assertEqual(report.total, len(ALL_PROBES))
        self.assertEqual(report.total, 17)
        # The heteroatom widening: five in-scope constructs covered (was one).
        self.assertEqual(len(report.covered), 5)
        self.assertEqual(set(report.missing), set(OUT_OF_SCOPE_PROBES))
        histogram = report.histogram
        self.assertGreater(len(histogram), 0)
        # Every missing probe is itemized by its named construct.
        for construct, count in histogram.items():
            self.assertIsInstance(construct, str)
            self.assertGreaterEqual(count, 1)
        # The previously-covered carbon chain is still covered (ratchet: nothing
        # dropped); the heteroatom probes are now covered too.
        self.assertIn("organic-chain", report.covered)
        for hetero in ("organic-atom-N", "organic-atom-O",
                       "organic-atom-Cl", "organic-atom-Br"):
            self.assertIn(hetero, report.covered)


if __name__ == "__main__":
    unittest.main()
