"""Square direction (gurdy/core/direction.py): composition and verdict
transfer — the directional-square extension (ARCHITECTURE.md §3; ROUTES.md §3;
POTENTIAL.md §6)."""

import unittest

from gurdy.core import direction
from gurdy.core.solver import Verdict


class TestCompose(unittest.TestCase):
    def test_exact_is_the_identity(self):
        self.assertEqual(direction.compose(), "exact")
        self.assertEqual(direction.compose("exact", "exact"), "exact")

    def test_over_absorbs(self):
        self.assertEqual(direction.compose("exact", "over"), "over")
        self.assertEqual(direction.compose("over", "exact", "exact"), "over")
        self.assertEqual(direction.compose("over", "over"), "over")

    def test_unknown_direction_is_a_contract_violation(self):
        with self.assertRaises(ValueError):
            direction.compose("exact", "under")


class TestTransfers(unittest.TestCase):
    def test_unreachable_transfers_both_ways(self):
        self.assertTrue(direction.transfers(Verdict.UNREACHABLE, "exact"))
        self.assertTrue(direction.transfers(Verdict.UNREACHABLE, "over"))

    def test_reachable_transfers_only_exactly(self):
        # (And is replayed at the source regardless — SOLVERS.md §4.)
        self.assertTrue(direction.transfers(Verdict.REACHABLE, "exact"))
        self.assertFalse(direction.transfers(Verdict.REACHABLE, "over"))

    def test_non_verdicts_never_transfer(self):
        for d in ("exact", "over"):
            self.assertFalse(direction.transfers(Verdict.UNKNOWN, d))
            self.assertFalse(direction.transfers(Verdict.RESOURCE_OUT, d))

    def test_raw_strings_accepted(self):
        self.assertTrue(direction.transfers("unreachable", "over"))
        self.assertFalse(direction.transfers("reachable", "over"))

    def test_unknown_direction_is_a_contract_violation(self):
        with self.assertRaises(ValueError):
            direction.transfers(Verdict.UNREACHABLE, "lax")


if __name__ == "__main__":
    unittest.main()
