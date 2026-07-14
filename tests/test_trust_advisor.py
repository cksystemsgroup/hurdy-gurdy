"""The trust advisor (core/trust.py): branch independence over declared
semantic artifacts, the anchor census, and honest saturation/demand
records when a player's assurance floor is unmet.

Real-registry cases: the RISC-V and AArch64 branches are genuinely
independent (prose manual vs Sail model — the SCALING.md §9 discipline,
now declared on the pairs); python->smtlib has one route only. The
not-independent and unknown verdicts are pinned on the pure core
(shared-artifact and undeclared inputs) so no synthetic registration
pollutes the shared registry.
"""

import unittest

from gurdy.core import registry
from gurdy.core.trust import _independence, independence, trust_options

import gurdy.pairs.aarch64_btor2  # noqa: F401  (registration)
import gurdy.pairs.aarch64_sail   # noqa: F401
import gurdy.pairs.btor2_smtlib   # noqa: F401
import gurdy.pairs.python_smtlib  # noqa: F401
import gurdy.pairs.riscv_btor2    # noqa: F401
import gurdy.pairs.wasm_btor2     # noqa: F401
import gurdy.pairs.riscv_sail     # noqa: F401
import gurdy.pairs.sail_btor2     # noqa: F401

DIRECT = ["riscv-btor2", "btor2-smtlib"]
SAIL = ["riscv-sail", "sail-btor2", "btor2-smtlib"]


class TestIndependence(unittest.TestCase):
    def test_riscv_branch_is_independent_with_shared_suffix_removed(self):
        rec = independence(DIRECT, SAIL)
        self.assertIs(rec["independent"], True)
        self.assertEqual(rec["shared_pairs"], ["btor2-smtlib"])
        self.assertEqual(rec["diverse_a"], ["riscv-btor2"])
        self.assertEqual(rec["diverse_b"], ["riscv-sail", "sail-btor2"])
        self.assertEqual(rec["anchors_a"], ["riscv-prose-manual"])
        self.assertEqual(rec["anchors_b"], ["riscv-sail-model", "sail-models"])

    def test_shared_artifact_is_never_independent(self):
        rec = _independence({"p1": "sail-models"},
                            {"p2": "sail-models", "p3": "arm-sail-model"})
        self.assertIs(rec["independent"], False)
        self.assertEqual(rec["shared_anchors"], ["sail-models"])

    def test_undeclared_is_unknown_never_silently_independent(self):
        rec = _independence({"p1": "riscv-prose-manual"}, {"p2": None})
        self.assertIsNone(rec["independent"])
        self.assertEqual(rec["undeclared_pairs"], ["p2"])

    def test_shared_artifact_outranks_undeclared(self):
        rec = _independence({"p1": "sail-models", "p2": None},
                            {"p3": "sail-models"})
        self.assertIs(rec["independent"], False)


class TestTrustOptions(unittest.TestCase):
    def test_riscv_floor_met_stops_at_the_declared_grade(self):
        record = trust_options("riscv", "smtlib", floor="checked")
        self.assertEqual(len(record["met_by"]), 2)
        self.assertNotIn("generation_target", record)

    def test_riscv_floor_unmet_offers_the_independent_branch(self):
        record = trust_options("riscv", "smtlib", floor="universal")
        self.assertEqual(record["met_by"], [])
        self.assertTrue(record["corroboration"]["available"])
        self.assertEqual(len(record["corroboration"]["branches"]), 1)
        self.assertIn("riscv-prose-manual", record["anchors"])
        self.assertIn("riscv-sail-model", record["anchors"])

    def test_aarch64_branch_is_independent_too(self):
        record = trust_options("aarch64", "smtlib", floor="universal")
        self.assertTrue(record["corroboration"]["available"])

    def test_single_route_demands_an_independent_pair(self):
        record = trust_options("wasm", "smtlib", floor="universal")
        self.assertEqual(record["met_by"], [])
        self.assertNotIn("corroboration", record)
        target = record["generation_target"]
        self.assertEqual(target["kind"], "independent-pair")
        self.assertEqual(target["from"], "wasm")
        self.assertIn("no second route exists", target["note"])
        # the sole route's pairs are undeclared: named, not glossed over
        self.assertIn("wasm-btor2", target["undeclared_pairs"])

    def test_declared_universal_grade_meets_the_floor(self):
        # python-smtlib declares predicted (spec-foreseeable = universal
        # class): the floor is met by the declared grade, no demand raised.
        record = trust_options("python", "smtlib", floor="universal")
        self.assertEqual(record["met_by"], ["python-smtlib"])
        self.assertNotIn("generation_target", record)

    def test_floor_accepts_grade_and_class_spellings(self):
        by_grade = trust_options("riscv", "smtlib", floor="checked")["met_by"]
        by_class = trust_options("riscv", "smtlib", floor="per-run")["met_by"]
        self.assertEqual(by_grade, by_class)
        with self.assertRaises(ValueError):
            trust_options("riscv", "smtlib", floor="platinum")

    def test_advisor_is_read_only(self):
        before = {pid: getattr(p, "semantic_artifact", None)
                  for pid, p in registry.list_pairs().items()}
        trust_options("riscv", "smtlib", floor="universal")
        trust_options("python", "smtlib", floor="universal")
        after = {pid: getattr(p, "semantic_artifact", None)
                 for pid, p in registry.list_pairs().items()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
