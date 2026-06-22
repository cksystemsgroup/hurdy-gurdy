"""Tests for the ``smiles-formula`` compile pair (PAIRING.md §7 minimum).

Covers: determinism twice-and-diff (translator + both new interpreters);
per-construct translation against the spec; the commuting-square check
``I_s(p) ≡_π L(I_t(T(p)))`` on a tiny corpus; carry-back replay through ``L``;
the registration smoke test; and the honest ``unsupported`` histogram (one
in-scope construct, everything else aborting).

Run with: ``python -m unittest`` (no third-party runner).
"""

import unittest

from gurdy.core import coverage, oracle, registry
from gurdy.core.errors import Unsupported

# Importing the pair registers it (and the two shared interpreters).
from gurdy.pairs.smiles_formula import PROJECTION, lift, square, translate
from gurdy.languages.molecular_formula import canonical_atoms, parse, run as run_formula, to_hill
from gurdy.languages.molecular_formula.hill import hill_order
from gurdy.languages.smiles import run as run_smiles
from gurdy.languages.smiles.graph import parse as parse_smiles
from gurdy.pairs.smiles_formula.inventory import ALL_PROBES, IN_SCOPE_PROBES, OUT_OF_SCOPE_PROBES

# The minimal corpus: the alkane carbon chain across a few lengths.
CORPUS = {
    "C": "CH4",
    "CC": "C2H6",
    "CCC": "C3H8",
    "CCCC": "C4H10",
    "CCCCCCCCCC": "C10H22",  # n-decane: C10 H(2*10+2)
}


class TestPerConstruct(unittest.TestCase):
    """The schema is reproducible byte-for-byte (PAIRING.md §2, §7)."""

    def test_translation_matches_spec(self):
        for smiles, formula in CORPUS.items():
            self.assertEqual(translate(smiles), formula.encode("utf-8"), msg=smiles)

    def test_alkane_general_formula(self):
        # C_n -> C_n H_(2n+2), the pinned valence rule applied across lengths.
        for n in range(1, 21):
            smiles = "C" * n
            h = 2 * n + 2
            expected = f"C{'' if n == 1 else n}H{h}"
            self.assertEqual(translate(smiles).decode("utf-8"), expected, msg=smiles)

    def test_implicit_h_degrees(self):
        # Lone / terminal / interior carbons get 4 / 3 / 2 implicit H.
        self.assertEqual([a.implicit_h for a in parse_smiles("C").atoms], [4])
        self.assertEqual([a.implicit_h for a in parse_smiles("CC").atoms], [3, 3])
        self.assertEqual([a.implicit_h for a in parse_smiles("CCC").atoms], [3, 2, 3])


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
            "C.C": "disconnection",
            "N": "organic-atom:N",
            "Cl": "organic-atom:Cl",
            "C-C": "explicit-single-bond",
        }
        for smiles, construct in cases.items():
            with self.assertRaises(Unsupported) as cm:
                translate(smiles)
            self.assertEqual(cm.exception.construct, construct, msg=smiles)

    def test_empty_string_aborts(self):
        with self.assertRaises(Unsupported) as cm:
            translate("")
        self.assertEqual(cm.exception.construct, "empty-string")

    def test_chlorine_not_misread_as_carbon(self):
        # 'Cl' must abort as chlorine, NOT silently parse as carbon + 'l'.
        with self.assertRaises(Unsupported) as cm:
            translate("CCl")
        self.assertEqual(cm.exception.construct, "organic-atom:Cl")


class TestDeterminism(unittest.TestCase):
    """Twice-and-diff on the translator and BOTH new interpreters
    (PAIRING.md §5)."""

    def test_translator_byte_identical(self):
        for smiles in CORPUS:
            self.assertEqual(translate(smiles), translate(smiles), msg=smiles)

    def test_smiles_interpreter_byte_identical(self):
        for smiles in CORPUS:
            self.assertEqual(run_smiles(smiles), run_smiles(smiles), msg=smiles)

    def test_formula_interpreter_byte_identical(self):
        for formula in CORPUS.values():
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


class TestCommutingSquare(unittest.TestCase):
    """I_s(p) ≡_π L(I_t(T(p))) on the corpus (PAIRING.md §7)."""

    def test_square_commutes(self):
        for smiles in CORPUS:
            report = square(smiles)
            self.assertTrue(report.ok, msg=f"{smiles}: {report.divergence}")

    def test_square_localizes_a_planted_divergence(self):
        # Sanity: a wrong right-hand multiset is caught and localized under π.
        left = run_smiles("CC")            # C2H6
        wrong = lift(run_formula("CH4"))   # a deliberately wrong formula
        report = oracle.align(left, wrong, PROJECTION)
        self.assertFalse(report.ok)
        self.assertEqual(report.divergence.step, 0)
        self.assertIn(report.divergence.field, ("atoms", "formula"))


class TestCarryBack(unittest.TestCase):
    """The target formula behavior replays through L back to the source-level
    atom multiset (PAIRING.md §7)."""

    def test_carry_back_to_atom_multiset(self):
        for smiles, formula in CORPUS.items():
            # Target side: interpret the emitted formula.
            target_trace = run_formula(formula)
            carried = lift(target_trace)
            # The carried-back observable is exactly the source atom multiset.
            source_atoms = canonical_atoms(parse(formula))
            self.assertEqual(carried[0]["atoms"], source_atoms, msg=smiles)
            # And it equals what the source interpreter independently produced.
            self.assertEqual(carried[0]["atoms"], run_smiles(smiles)[0]["atoms"])
            # The multiset really denotes the heavy + implicit-H atoms.
            as_dict = dict(carried[0]["atoms"])
            n = len(smiles)
            self.assertEqual(as_dict, {"C": n, "H": 2 * n + 2})


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
        # Every edge-operation of the square is callable.
        artifact = pair.translator("CC")                       # T
        self.assertEqual(artifact, b"C2H6")
        src = pair.source_interpreter("CC")                    # I_s
        tgt = pair.target_interpreter(artifact.decode("utf-8"))  # I_t
        carried = pair.target_to_source(tgt)                   # L
        self.assertTrue(oracle.align(src, carried, pair.projection).ok)

    def test_languages_registered(self):
        langs = registry.list_languages()
        self.assertIn("smiles", langs)
        self.assertIn("molecular-formula", langs)


class TestCoverageHistogram(unittest.TestCase):
    """Honest coverage: one construct in scope, every other aborting; the
    unsupported histogram is itemized (BENCHMARKS.md §3, §5)."""

    def test_coverage_and_histogram(self):
        report = coverage.measure(translate, ALL_PROBES)
        self.assertEqual(report.covered, set(IN_SCOPE_PROBES))
        self.assertEqual(report.total, len(ALL_PROBES))
        # Exactly the in-scope construct is covered; the rest are the histogram.
        self.assertEqual(len(report.covered), 1)
        self.assertEqual(set(report.missing), set(OUT_OF_SCOPE_PROBES))
        histogram = report.histogram
        self.assertGreater(len(histogram), 0)
        # Every missing probe is itemized by its named construct.
        for construct, count in histogram.items():
            self.assertIsInstance(construct, str)
            self.assertGreaterEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
