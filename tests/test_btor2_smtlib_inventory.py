"""btor2-smtlib construct-coverage tests (BENCHMARKS.md §2, §5).

The bridge is a finite reasoning bridge, so its floor is 100% of BTOR2's
operator/sort/directive inventory. These tests pin that the inventory is fully
covered, that the two formerly-leaky constructs (redxor used to hard-abort,
constraint used to be silently dropped) are now genuinely bridged, and that a
real gap would be itemized rather than hidden.
"""

import unittest

from gurdy.core.coverage import measure
from gurdy.core.registry import get_pair
from gurdy.pairs.btor2_smtlib import translate
from gurdy.pairs.btor2_smtlib.inventory import ALL_PROBES, coverage


class TestBtor2SmtlibCoverage(unittest.TestCase):
    def test_full_operator_coverage(self):
        report = coverage()
        self.assertEqual(report.missing, {})
        self.assertEqual(report.fraction, 1.0)
        self.assertTrue(report.meets(1.0))
        self.assertGreaterEqual(report.total, 50)  # ~56 sorts+leaves+directives+ops

    def test_redxor_and_constraint_are_covered(self):
        # the two gaps this work closed: redxor (was Unsupported) and constraint
        # (was silently dropped, violating the honest-failure rule).
        covered = coverage().covered
        self.assertIn("redxor", covered)
        self.assertIn("constraint", covered)
        self.assertIn("(bvxor", translate(ALL_PROBES["redxor"]).decode("utf-8"))
        # constraint emits one assertion per state in 0..k (k=1 -> two)
        self.assertEqual(translate(ALL_PROBES["constraint"]).decode("utf-8").count("(assert (= i"), 2)

    def test_a_real_gap_is_itemized(self):
        # an operator the parser doesn't know is a typed Unsupported, surfaced in
        # the histogram (not a silent pass).
        bogus = {"WIDGET": {"system": "1 sort bitvec 8\n2 widget 1 2 3\n", "k": 1}}
        report = measure(translate, bogus)
        self.assertEqual(report.fraction, 0.0)
        self.assertIn("WIDGET", report.missing)
        self.assertIn("op.widget", report.histogram)

    def test_pair_exposes_probes(self):
        self.assertIs(get_pair("btor2-smtlib").probes, ALL_PROBES)


if __name__ == "__main__":
    unittest.main()
