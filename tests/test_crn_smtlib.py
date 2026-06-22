"""crn-smtlib pair tests (z3-backed where a decision is needed): the
schema-determined unrolling, the typed unsupported aborts, the commuting-square
cross-check, and the firing-flag witness carry-back.

The pair is the minimal vertical slice (PAIRING.md §1): one in-scope reaction
class (the unimolecular ``A -> B``) translated end-to-end; everything else
hard-aborts ``unsupported: crn:<construct>``.
"""

import unittest

import gurdy.pairs.crn_smtlib  # noqa: F401  (registers the pair)
from gurdy.core.coverage import measure
from gurdy.core.errors import Unsupported
from gurdy.core.registry import get_pair, list_pairs
from gurdy.core.solver import Verdict
from gurdy.pairs.crn_smtlib import (
    cross_check,
    decode_schedule,
    lift,
    projection_for,
    reach,
    translate,
)
from gurdy.pairs.crn_smtlib.inventory import ALL_PROBES, coverage

UNI = "species A B\ninit A 3 B 0\nrxn A -> B\n"


def _z3() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except ImportError:
        return False


class TestRegistrationSmoke(unittest.TestCase):
    def test_pair_registered(self):
        self.assertIn("crn-smtlib", list_pairs())

    def test_square_edges_callable(self):
        pair = get_pair("crn-smtlib")
        self.assertEqual((pair.source, pair.target), ("crn", "smtlib"))
        self.assertEqual(pair.fidelity, "predicted")
        # every edge-op of the square is wired and callable
        self.assertTrue(callable(pair.translator))          # T
        self.assertTrue(callable(pair.target_to_source))    # L
        self.assertTrue(callable(pair.source_interpreter))  # I_s (shared CRN)
        self.assertTrue(callable(pair.target_interpreter))  # I_t (shared SMT-LIB)

    def test_exposes_probes(self):
        self.assertIs(get_pair("crn-smtlib").probes, ALL_PROBES)


class TestTranslationSchema(unittest.TestCase):
    def test_deterministic_twice_and_diff(self):
        prog = {"crn": UNI, "k": 3, "target": {"A": 0, "B": 3}}
        self.assertEqual(translate(prog), translate(prog))

    def test_emits_qf_lia(self):
        text = translate({"crn": UNI, "k": 2, "target": {"B": 2}}).decode()
        self.assertIn("(set-logic QF_LIA)", text)
        self.assertIn("(check-sat)", text)

    def test_schema_byte_exact(self):
        # the full schema for a k=1 unimolecular network, byte-for-byte
        text = translate({"crn": "species A B\ninit A 1 B 0\nrxn A -> B\n",
                          "k": 1, "target": {"B": 1}}).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun xA_0 () Int)\n(declare-fun xB_0 () Int)\n"
            "(declare-fun xA_1 () Int)\n(declare-fun xB_1 () Int)\n"
            "(declare-fun f0_0 () Bool)\n"
            "(assert (= xA_0 1))\n(assert (= xB_0 0))\n"
            "(assert (>= xA_0 0))\n(assert (>= xB_0 0))\n"
            "(assert (>= xA_1 0))\n(assert (>= xB_1 0))\n"
            "(assert (=> f0_0 (>= xA_0 1)))\n"
            "(assert (= xA_1 (ite f0_0 (- xA_0 1) xA_0)))\n"
            "(assert (= xB_1 (ite f0_0 (+ xB_0 1) xB_0)))\n"
            "(assert (or (= xB_0 1) (= xB_1 1)))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_spectator_species_preserved_in_schema(self):
        text = translate({"crn": "species A B C\ninit A 1 B 0 C 4\nrxn A -> B\n",
                          "k": 1, "target": {"B": 1}}).decode()
        # C is neither reactant nor product: its next value is itself
        self.assertIn("(assert (= xC_1 (ite f0_0 xC_0 xC_0)))", text)

    def test_k_zero_init_only(self):
        text = translate({"crn": UNI, "k": 0, "target": {"A": 3}}).decode()
        self.assertNotIn("f0_", text)               # no firing flags at k=0
        self.assertIn("(assert (= xA_0 3))", text)  # bare conjunct, no disjunction
        self.assertTrue(text.rstrip().endswith("(check-sat)"))


class TestUnsupportedAborts(unittest.TestCase):
    def _abort(self, src, target=None):
        with self.assertRaises(Unsupported) as cm:
            translate({"crn": src, "k": 2, "target": target or {"A": 0}})
        return cm.exception

    def test_bimolecular_hetero(self):
        e = self._abort("species A B C\nrxn A + B -> C\n", {"C": 1})
        self.assertEqual(e.construct, "bimolecular")

    def test_bimolecular_homo(self):
        self.assertEqual(self._abort("species A B\nrxn 2 A -> B\n").construct, "bimolecular")

    def test_catalysis_nonunit_product(self):
        self.assertEqual(self._abort("species A B\nrxn A -> 2 B\n").construct, "catalysis")

    def test_two_products(self):
        self.assertEqual(
            self._abort("species A B C\nrxn A -> B + C\n", {"B": 1}).construct, "catalysis")

    def test_multiple_reactions(self):
        e = self._abort("species A B C\nrxn A -> B\nrxn B -> C\n", {"C": 1})
        self.assertEqual(e.construct, "multiple-reactions")

    def test_empty_network(self):
        self.assertEqual(self._abort("species A B\n").construct, "empty-network")

    def test_synthesis(self):
        self.assertEqual(self._abort("species A B\nrxn 0 -> A\n", {"A": 1}).construct, "synthesis")

    def test_degradation(self):
        self.assertEqual(self._abort("species A B\nrxn A -> 0\n").construct, "degradation")

    def test_self_loop(self):
        self.assertEqual(self._abort("species A B\nrxn A -> A\n", {"A": 1}).construct, "self-loop")

    def test_missing_target(self):
        with self.assertRaises(Unsupported) as cm:
            translate({"crn": UNI, "k": 2})
        self.assertEqual(cm.exception.construct, "no-target")

    def test_undeclared_target_species(self):
        self.assertEqual(self._abort(UNI, {"Z": 0}).construct, "target-species")


class TestCoverageHistogram(unittest.TestCase):
    def test_one_covered_rest_itemized(self):
        report = coverage()
        self.assertEqual(report.covered, {"unimolecular"})
        # the unsupported histogram: every other reaction class blocked, named
        self.assertEqual(
            report.histogram,
            {
                "bimolecular": 2,        # hetero + homo
                "catalysis": 2,          # non-unit product + two products
                "synthesis": 1,
                "degradation": 1,
                "self-loop": 1,
                "multiple-reactions": 1,
                "empty-network": 1,
            },
        )
        self.assertLess(report.fraction, 1.0)  # honest partial, not built

    def test_a_real_gap_is_typed(self):
        bogus = {"WIDGET": {"crn": "species A B\nrxn A + B -> A\n", "k": 1, "target": {"A": 1}}}
        report = measure(translate, bogus)
        self.assertEqual(report.fraction, 0.0)
        self.assertIn("bimolecular", report.histogram)


class TestCarryBack(unittest.TestCase):
    def test_decode_schedule_from_flags(self):
        model = {"f0_0": "True", "f0_1": "False", "f0_2": True}
        self.assertEqual(decode_schedule(3, model), [0, None, 0])

    def test_lift_replays_to_population_trajectory(self):
        # a hand-built witness (all three steps fire) replays to A:3->0, B:0->3
        model = {f"f0_{t}": "True" for t in range(3)}
        behavior = lift({"crn": UNI, "k": 3, "model": model})
        self.assertEqual(behavior, [{"A": 2, "B": 1}, {"A": 1, "B": 2}, {"A": 0, "B": 3}])

    def test_projection_is_species(self):
        self.assertEqual(projection_for(UNI).fields, ("A", "B"))


@unittest.skipUnless(_z3(), "z3 not installed")
class TestReachWithZ3(unittest.TestCase):
    def test_reachable_with_verified_witness(self):
        info = reach(UNI, 3, {"A": 0, "B": 3})
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(info["model_matches_replay"])
        # the carried-back trajectory reaches the target marking
        self.assertEqual(info["behavior"][-1], {"A": 0, "B": 3})

    def test_unreachable_at_low_bound(self):
        # B=3 needs three firings; within k=2 it cannot be reached
        self.assertEqual(reach(UNI, 2, {"A": 0, "B": 3})["verdict"], Verdict.UNREACHABLE)

    def test_intermediate_target_reachable(self):
        info = reach(UNI, 3, {"B": 1})  # reachable at step 1
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(any(row["B"] == 1 for row in info["behavior"]))

    def test_impossible_target_unreachable(self):
        # B can never exceed the initial A (3); B=4 is unreachable for any k
        self.assertEqual(reach(UNI, 5, {"B": 4})["verdict"], Verdict.UNREACHABLE)

    def test_commuting_square_holds(self):
        # I_s(p) vs L(I_t(T(p))) under π on a tiny corpus
        for crn, k, target in [
            (UNI, 3, {"A": 0, "B": 3}),
            ("species A B C\ninit A 2 B 0 C 5\nrxn A -> B\n", 4, {"B": 1, "C": 5}),
            ("species A B\ninit A 1 B 0\nrxn A -> B\n", 1, {"B": 1}),
        ]:
            verdict, result = cross_check(crn, k, target)
            self.assertEqual(verdict, Verdict.REACHABLE, crn)
            self.assertTrue(result.ok, f"{crn}: {result.divergence}")

    def test_unreachable_cross_check_trivially_aligns(self):
        verdict, result = cross_check(UNI, 2, {"B": 3})
        self.assertEqual(verdict, Verdict.UNREACHABLE)
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
