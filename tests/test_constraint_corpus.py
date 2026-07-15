"""The constrained-corpus benchmark (tools/constraint_corpus.py; the
paper's tab:constraint): nine authored BTOR2 systems with
by-construction ground truth, decided natively (btormc), bridged
(per-frame encoding, z3), and corroborated by the shared evaluator, in
both verdict polarities — plus the three structural controls (masking,
additive, blocking). The corpus-shape checks run everywhere; the full
experiment is gated on btormc + z3 like the rest of the
native-vs-bridged family."""

import importlib.util
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "constraint_corpus", os.path.join(_ROOT, "tools", "constraint_corpus.py"))
constraint_corpus = importlib.util.module_from_spec(_spec)
sys.modules["constraint_corpus"] = constraint_corpus
_spec.loader.exec_module(constraint_corpus)

from gurdy.solvers.native_btor2 import find_btormc  # noqa: E402


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


class TestCorpusShape(unittest.TestCase):
    def test_both_polarities_present(self):
        corpus = constraint_corpus.build_corpus()
        truths = [e["truth"] for e in corpus]
        self.assertEqual(len(corpus), 9)
        self.assertEqual(truths.count("reachable"), 5)
        self.assertEqual(truths.count("unreachable"), 4)

    def test_every_system_is_constrained(self):
        # the corpus proper carries constraints; the unconstrained
        # siblings live only inside the controls
        for e in constraint_corpus.build_corpus():
            self.assertIn("constraint", e["text"], msg=e["name"])

    def test_corpus_is_deterministic(self):
        a = constraint_corpus.build_corpus()
        b = constraint_corpus.build_corpus()
        self.assertEqual([e["text"] for e in a], [e["text"] for e in b])

    def test_global_encoding_requires_constraints(self):
        with self.assertRaises(AssertionError):
            constraint_corpus.global_encoding(
                "1 sort bitvec 1\n2 one 1\n3 bad 2\n", 2)


@unittest.skipUnless(find_btormc() and _z3(), "btormc and/or z3 absent")
class TestExperiment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = constraint_corpus.run_experiment()

    def test_all_rows_agree_with_ground_truth(self):
        for row in self.report["rows"]:
            self.assertTrue(row["agree"], msg=str(row))

    def test_masking_control(self):
        # the historical global reading must mask the valid-prefix
        # reach that per-frame and native both find
        m = self.report["controls"]["masking"]
        self.assertTrue(m["masked"], msg=str(m))
        self.assertEqual(m["per_frame"], "reachable")

    def test_additive_and_blocking_controls(self):
        self.assertTrue(self.report["controls"]["additive"]["ok"],
                        msg=str(self.report["controls"]["additive"]))
        self.assertTrue(self.report["controls"]["blocking"]["ok"],
                        msg=str(self.report["controls"]["blocking"]))


if __name__ == "__main__":
    unittest.main()
