"""The cost-calibration benchmark (tools/cost_calibration.py; the
paper's tab:costs): repeated capped route-grader runs seed per-hop cost
profiles, the route report's dominance mark is checked for coherence
(never against the measured totals) and counted for stability, and the
honesty invariants run executable — an empty ledger reads unmeasured
(never zero) and computes no dominance; partial measurement computes no
dominance either. The test asserts only host-independent properties: it
never expects a particular route to win (at µs margins the totals may
tie, which is the benchmark's finding, not a failure)."""

import importlib.util
import os
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "cost_calibration", os.path.join(_ROOT, "tools", "cost_calibration.py"))
cost_calibration = importlib.util.module_from_spec(_spec)
sys.modules["cost_calibration"] = cost_calibration
_spec.loader.exec_module(cost_calibration)


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_z3(), "z3 absent")
class TestCalibration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="cost-cal-test-")
        cls.report = cost_calibration.run_experiment(
            reps=2, max_probes=6, workdir=cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_experiment_ok(self):
        self.assertTrue(self.report["ok"], msg=str(self.report["dominance"]))

    def test_both_routes_listed_at_equal_axes(self):
        dom = self.report["dominance"]
        self.assertTrue(dom["both_listed"])
        self.assertTrue(dom["equal_assurance"])
        self.assertTrue(dom["equal_direction"])

    def test_every_hop_measured(self):
        for pid, prof in self.report["profiles"]["translate"].items():
            self.assertIsNotNone(prof, msg=pid)
            self.assertGreater(prof["n"], 0, msg=pid)

    def test_mark_is_coherent(self):
        # whatever direction the mark takes (or none), it may never point
        # against the measured totals — pooled and per repetition
        self.assertTrue(self.report["dominance"]["coherent_all"],
                        msg=str(self.report["dominance"]))

    def test_unmeasured_reads_unmeasured_never_zero(self):
        self.assertTrue(all(self.report["unmeasured_invariant"].values()),
                        msg=str(self.report["unmeasured_invariant"]))

    def test_partial_measurement_computes_no_dominance(self):
        self.assertTrue(all(self.report["partial_invariant"].values()),
                        msg=str(self.report["partial_invariant"]))

    def test_stability_recorded_per_route(self):
        for name, s in self.report["stability"].items():
            self.assertIsNotNone(s, msg=name)
            self.assertIn("rel_spread", s)


if __name__ == "__main__":
    unittest.main()
