"""crn-smtlib pair tests (z3-backed where a decision is needed): the
schema-determined unrolling, the typed unsupported aborts, the commuting-square
cross-check, and the firing-flag witness carry-back.

The pair is a widened vertical slice (PAIRING.md §1 "start thin, then widen"):
five in-scope reaction classes — the unimolecular ``A -> B``, both bimolecular
shapes (``A + B -> C`` and ``2 A -> B``), and both catalysis / multi-product
shapes (``A -> 2 B`` and ``A -> B + C``) — translated end-to-end; everything else
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
# Bimolecular networks: hetero (A + B -> C) and homo / dimerization (2 A -> B).
BI_HETERO = "species A B C\ninit A 2 B 2 C 0\nrxn A + B -> C\n"
BI_HOMO = "species A B\ninit A 4 B 0\nrxn 2 A -> B\n"
# Catalysis / multi-product networks: amplification (A -> 2 B) and a product pair
# (A -> B + C), each a single unit reactant with a molecularity-2 product.
CAT_AMP = "species A B\ninit A 3 B 0\nrxn A -> 2 B\n"
CAT_PAIR = "species A B C\ninit A 3 B 0 C 0\nrxn A -> B + C\n"


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

    def test_unimolecular_schema_unchanged_by_widening(self):
        # the widening must leave the unimolecular bytes identical (the net-update
        # / single-conjunct enabledness reduces to exactly the old emission)
        text = translate({"crn": UNI, "k": 1, "target": {"B": 3}}).decode()
        self.assertIn("(assert (=> f0_0 (>= xA_0 1)))", text)
        self.assertIn("(assert (= xA_1 (ite f0_0 (- xA_0 1) xA_0)))", text)
        self.assertIn("(assert (= xB_1 (ite f0_0 (+ xB_0 1) xB_0)))", text)

    def test_bimolecular_homo_schema_byte_exact(self):
        # 2 A -> B : enabledness needs xA>=2, the net update on A is -2
        text = translate({"crn": "species A B\ninit A 2 B 0\nrxn 2 A -> B\n",
                          "k": 1, "target": {"B": 1}}).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun xA_0 () Int)\n(declare-fun xB_0 () Int)\n"
            "(declare-fun xA_1 () Int)\n(declare-fun xB_1 () Int)\n"
            "(declare-fun f0_0 () Bool)\n"
            "(assert (= xA_0 2))\n(assert (= xB_0 0))\n"
            "(assert (>= xA_0 0))\n(assert (>= xB_0 0))\n"
            "(assert (>= xA_1 0))\n(assert (>= xB_1 0))\n"
            "(assert (=> f0_0 (>= xA_0 2)))\n"
            "(assert (= xA_1 (ite f0_0 (- xA_0 2) xA_0)))\n"
            "(assert (= xB_1 (ite f0_0 (+ xB_0 1) xB_0)))\n"
            "(assert (or (= xB_0 1) (= xB_1 1)))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_bimolecular_hetero_schema_byte_exact(self):
        # A + B -> C : enabledness is a two-conjunct (and ...), each reactant -1
        text = translate({"crn": "species A B C\ninit A 1 B 1 C 0\nrxn A + B -> C\n",
                          "k": 1, "target": {"C": 1}}).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun xA_0 () Int)\n(declare-fun xB_0 () Int)\n(declare-fun xC_0 () Int)\n"
            "(declare-fun xA_1 () Int)\n(declare-fun xB_1 () Int)\n(declare-fun xC_1 () Int)\n"
            "(declare-fun f0_0 () Bool)\n"
            "(assert (= xA_0 1))\n(assert (= xB_0 1))\n(assert (= xC_0 0))\n"
            "(assert (>= xA_0 0))\n(assert (>= xB_0 0))\n(assert (>= xC_0 0))\n"
            "(assert (>= xA_1 0))\n(assert (>= xB_1 0))\n(assert (>= xC_1 0))\n"
            "(assert (=> f0_0 (and (>= xA_0 1) (>= xB_0 1))))\n"
            "(assert (= xA_1 (ite f0_0 (- xA_0 1) xA_0)))\n"
            "(assert (= xB_1 (ite f0_0 (- xB_0 1) xB_0)))\n"
            "(assert (= xC_1 (ite f0_0 (+ xC_0 1) xC_0)))\n"
            "(assert (or (= xC_0 1) (= xC_1 1)))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_catalysis_amplification_schema_byte_exact(self):
        # A -> 2 B : unimolecular enabledness (xA>=1), net +2 increment on B
        text = translate({"crn": "species A B\ninit A 1 B 0\nrxn A -> 2 B\n",
                          "k": 1, "target": {"B": 2}}).decode()
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
            "(assert (= xB_1 (ite f0_0 (+ xB_0 2) xB_0)))\n"
            "(assert (or (= xB_0 2) (= xB_1 2)))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_catalysis_pair_schema_byte_exact(self):
        # A -> B + C : unimolecular enabledness, +1 on each of two products
        text = translate({"crn": "species A B C\ninit A 1 B 0 C 0\nrxn A -> B + C\n",
                          "k": 1, "target": {"B": 1, "C": 1}}).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun xA_0 () Int)\n(declare-fun xB_0 () Int)\n(declare-fun xC_0 () Int)\n"
            "(declare-fun xA_1 () Int)\n(declare-fun xB_1 () Int)\n(declare-fun xC_1 () Int)\n"
            "(declare-fun f0_0 () Bool)\n"
            "(assert (= xA_0 1))\n(assert (= xB_0 0))\n(assert (= xC_0 0))\n"
            "(assert (>= xA_0 0))\n(assert (>= xB_0 0))\n(assert (>= xC_0 0))\n"
            "(assert (>= xA_1 0))\n(assert (>= xB_1 0))\n(assert (>= xC_1 0))\n"
            "(assert (=> f0_0 (>= xA_0 1)))\n"
            "(assert (= xA_1 (ite f0_0 (- xA_0 1) xA_0)))\n"
            "(assert (= xB_1 (ite f0_0 (+ xB_0 1) xB_0)))\n"
            "(assert (= xC_1 (ite f0_0 (+ xC_0 1) xC_0)))\n"
            "(assert (or (and (= xB_0 1) (= xC_0 1)) (and (= xB_1 1) (= xC_1 1))))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_bimolecular_deterministic_twice_and_diff(self):
        for crn, k, target in [(BI_HOMO, 2, {"B": 2}), (BI_HETERO, 2, {"C": 2})]:
            prog = {"crn": crn, "k": k, "target": target}
            self.assertEqual(translate(prog), translate(prog))

    def test_catalysis_deterministic_twice_and_diff(self):
        for crn, k, target in [(CAT_AMP, 2, {"B": 4}), (CAT_PAIR, 2, {"B": 2, "C": 2})]:
            prog = {"crn": crn, "k": k, "target": target}
            self.assertEqual(translate(prog), translate(prog))

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

    def test_trimolecular(self):
        # molecularity 3 (>2) is out of scope; both shapes abort crn:trimolecular
        e = self._abort("species A B C D\nrxn A + B + C -> D\n", {"D": 1})
        self.assertEqual(e.construct, "trimolecular")
        self.assertEqual(self._abort("species A B\nrxn 3 A -> B\n").construct, "trimolecular")

    def test_bimolecular_self_loop(self):
        # the product also appears among the reactants (A + B -> A) -> self-loop
        self.assertEqual(
            self._abort("species A B\nrxn A + B -> A\n", {"A": 1}).construct, "self-loop")

    def test_catalysis_product_molecularity_three(self):
        # product molecularity 3 (A -> 3 B) is out of scope -> crn:catalysis
        self.assertEqual(self._abort("species A B\nrxn A -> 3 B\n", {"B": 3}).construct, "catalysis")

    def test_catalysis_on_nonunit_reactant(self):
        # a molecularity-2 product is only admitted on a single unit reactant;
        # 2 A -> 2 B (and A + B -> 2 C) stay out of scope -> crn:catalysis
        self.assertEqual(self._abort("species A B\nrxn 2 A -> 2 B\n", {"B": 2}).construct, "catalysis")
        self.assertEqual(
            self._abort("species A B C\nrxn A + B -> 2 C\n", {"C": 2}).construct, "catalysis")

    def test_catalysis_self_loop(self):
        # a multi-product reaction whose product is also a reactant -> self-loop
        self.assertEqual(
            self._abort("species A C\nrxn A -> A + C\n", {"A": 1}).construct, "self-loop")

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
    def test_covered_rest_itemized(self):
        report = coverage()
        # the widened slice covers unimolecular + both bimolecular shapes + both
        # catalysis / multi-product shapes
        self.assertEqual(
            report.covered,
            {
                "unimolecular",
                "bimolecular-hetero",
                "bimolecular-homo",
                "catalysis",
                "catalyst-pair",
            },
        )
        # the ratchet only grew: every previously-covered class stays covered
        for prev in ("unimolecular", "bimolecular-hetero", "bimolecular-homo"):
            self.assertIn(prev, report.covered)
        # the unsupported histogram: every other reaction class blocked, named
        self.assertEqual(
            report.histogram,
            {
                "synthesis": 1,
                "degradation": 1,
                "self-loop": 1,
                "multiple-reactions": 1,
                "empty-network": 1,
            },
        )
        self.assertEqual(report.total, 10)            # denominator unchanged
        self.assertAlmostEqual(report.fraction, 0.5)  # 5/10 — honest partial
        self.assertLess(report.fraction, 1.0)         # not a false built

    def test_a_real_gap_is_typed(self):
        # 0 -> A is synthesis (empty reactant side) — still an honest unsupported
        bogus = {"WIDGET": {"crn": "species A B\nrxn 0 -> A\n", "k": 1, "target": {"A": 1}}}
        report = measure(translate, bogus)
        self.assertEqual(report.fraction, 0.0)
        self.assertIn("synthesis", report.histogram)


class TestCarryBack(unittest.TestCase):
    def test_decode_schedule_from_flags(self):
        model = {"f0_0": "True", "f0_1": "False", "f0_2": True}
        self.assertEqual(decode_schedule(3, model), [0, None, 0])

    def test_lift_replays_to_population_trajectory(self):
        # a hand-built witness (all three steps fire) replays to A:3->0, B:0->3
        model = {f"f0_{t}": "True" for t in range(3)}
        behavior = lift({"crn": UNI, "k": 3, "model": model})
        self.assertEqual(behavior, [{"A": 2, "B": 1}, {"A": 1, "B": 2}, {"A": 0, "B": 3}])

    def test_lift_replays_bimolecular_homo(self):
        # 2 A -> B fired twice from A=4: A:4->2->0, B:0->1->2 (each firing eats 2 A)
        model = {f"f0_{t}": "True" for t in range(2)}
        behavior = lift({"crn": BI_HOMO, "k": 2, "model": model})
        self.assertEqual(behavior, [{"A": 2, "B": 1}, {"A": 0, "B": 2}])

    def test_lift_replays_bimolecular_hetero(self):
        # A + B -> C fired twice from A=2 B=2: each firing eats one A and one B
        model = {f"f0_{t}": "True" for t in range(2)}
        behavior = lift({"crn": BI_HETERO, "k": 2, "model": model})
        self.assertEqual(behavior, [{"A": 1, "B": 1, "C": 1}, {"A": 0, "B": 0, "C": 2}])

    def test_lift_replays_catalysis_amplification(self):
        # A -> 2 B fired three times from A=3: each firing makes 2 B (B 0->2->4->6)
        model = {f"f0_{t}": "True" for t in range(3)}
        behavior = lift({"crn": CAT_AMP, "k": 3, "model": model})
        self.assertEqual(
            behavior, [{"A": 2, "B": 2}, {"A": 1, "B": 4}, {"A": 0, "B": 6}])

    def test_lift_replays_catalysis_pair(self):
        # A -> B + C fired three times from A=3: each firing makes one B and one C
        model = {f"f0_{t}": "True" for t in range(3)}
        behavior = lift({"crn": CAT_PAIR, "k": 3, "model": model})
        self.assertEqual(
            behavior,
            [{"A": 2, "B": 1, "C": 1}, {"A": 1, "B": 2, "C": 2}, {"A": 0, "B": 3, "C": 3}])

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


@unittest.skipUnless(_z3(), "z3 not installed")
class TestBimolecularWithZ3(unittest.TestCase):
    """Per-reaction-class decision for the two bimolecular shapes: each decided
    for bounded reachability (REACHABLE with a schedule + UNREACHABLE), with the
    authoritative SMT-level witness check (smt_model_ok) agreeing with the
    CRN-interpreter replay (witness_ok)."""

    def _assert_witnessed(self, info):
        # the authoritative SMT-level check agrees with the interpreter replay
        self.assertTrue(info["smt_model_ok"])
        self.assertTrue(info["witness_ok"])
        self.assertTrue(info["model_matches_replay"])
        self.assertEqual(info["smt_model_ok"], info["witness_ok"])

    def test_homo_reachable_with_schedule(self):
        # 2 A -> B from A=4: B=2 needs two firings; reachable within k=2
        info = reach(BI_HOMO, 2, {"B": 2})
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self._assert_witnessed(info)
        self.assertEqual(info["schedule"], [0, 0])           # a firing schedule
        self.assertEqual(info["behavior"][-1], {"A": 0, "B": 2})

    def test_homo_unreachable_at_low_bound(self):
        # B=2 needs two firings of 2 A -> B; within k=1 it cannot be reached
        self.assertEqual(reach(BI_HOMO, 1, {"B": 2})["verdict"], Verdict.UNREACHABLE)

    def test_homo_unreachable_enabledness(self):
        # 2 A -> B needs two A per firing; from A=1 no firing is enabled, so B=1
        # is unreachable for any k (the >= coefficient precondition bites)
        crn = "species A B\ninit A 1 B 0\nrxn 2 A -> B\n"
        self.assertEqual(reach(crn, 5, {"B": 1})["verdict"], Verdict.UNREACHABLE)

    def test_hetero_reachable_with_schedule(self):
        # A + B -> C from A=2 B=2: C=2 needs two firings; reachable within k=2
        info = reach(BI_HETERO, 2, {"C": 2})
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self._assert_witnessed(info)
        self.assertEqual(info["schedule"], [0, 0])
        self.assertEqual(info["behavior"][-1], {"A": 0, "B": 0, "C": 2})

    def test_hetero_unreachable_short_supply(self):
        # A + B -> C with A=1 B=5: C is capped by the scarcer reactant (A) at 1,
        # so C=2 is unreachable for any k
        crn = "species A B C\ninit A 1 B 5 C 0\nrxn A + B -> C\n"
        self.assertEqual(reach(crn, 4, {"C": 2})["verdict"], Verdict.UNREACHABLE)
        self.assertEqual(reach(crn, 4, {"C": 1})["verdict"], Verdict.REACHABLE)

    def test_bimolecular_commuting_square_holds(self):
        # I_s(p) vs L(I_t(T(p))) under π on a bimolecular corpus, incl. spectators
        for crn, k, target in [
            (BI_HOMO, 2, {"B": 2}),
            (BI_HETERO, 2, {"C": 2}),
            ("species A B C\ninit A 4 B 0 C 9\nrxn 2 A -> B\n", 2, {"B": 2, "C": 9}),
            ("species A B C D\ninit A 3 B 2 C 0 D 5\nrxn A + B -> C\n", 2, {"C": 2, "D": 5}),
        ]:
            verdict, result = cross_check(crn, k, target)
            self.assertEqual(verdict, Verdict.REACHABLE, crn)
            self.assertTrue(result.ok, f"{crn}: {result.divergence}")

    def test_bimolecular_unreachable_cross_check_aligns(self):
        verdict, result = cross_check(BI_HOMO, 1, {"B": 2})
        self.assertEqual(verdict, Verdict.UNREACHABLE)
        self.assertTrue(result.ok)


@unittest.skipUnless(_z3(), "z3 not installed")
class TestCatalysisWithZ3(unittest.TestCase):
    """Per-reaction-class decision for the two catalysis / multi-product shapes:
    each decided for bounded reachability (REACHABLE with a schedule + UNREACHABLE),
    with the authoritative SMT-level witness check (smt_model_ok) agreeing with the
    CRN-interpreter replay (witness_ok)."""

    def _assert_witnessed(self, info):
        # the authoritative SMT-level check agrees with the interpreter replay
        self.assertTrue(info["smt_model_ok"])
        self.assertTrue(info["witness_ok"])
        self.assertTrue(info["model_matches_replay"])
        self.assertEqual(info["smt_model_ok"], info["witness_ok"])

    def test_amplification_reachable_with_schedule(self):
        # A -> 2 B from A=3: B=4 needs two firings (each makes 2 B); reachable k=2
        info = reach(CAT_AMP, 2, {"B": 4})
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self._assert_witnessed(info)
        self.assertEqual(info["schedule"], [0, 0])           # a firing schedule
        self.assertEqual(info["behavior"][-1], {"A": 1, "B": 4})

    def test_amplification_unreachable_at_low_bound(self):
        # B=4 needs two firings of A -> 2 B; within k=1 it cannot be reached
        self.assertEqual(reach(CAT_AMP, 1, {"B": 4})["verdict"], Verdict.UNREACHABLE)

    def test_amplification_unreachable_parity(self):
        # each firing makes 2 B, so B is always even; B=3 is unreachable for any k
        self.assertEqual(reach(CAT_AMP, 5, {"B": 3})["verdict"], Verdict.UNREACHABLE)

    def test_amplification_unreachable_supply_cap(self):
        # B is capped at 2 * initial A = 6; B=8 is unreachable for any k
        self.assertEqual(reach(CAT_AMP, 9, {"B": 8})["verdict"], Verdict.UNREACHABLE)

    def test_pair_reachable_with_schedule(self):
        # A -> B + C from A=3: B=2 C=2 needs two firings; reachable within k=2
        info = reach(CAT_PAIR, 2, {"B": 2, "C": 2})
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self._assert_witnessed(info)
        self.assertEqual(info["schedule"], [0, 0])
        self.assertEqual(info["behavior"][-1], {"A": 1, "B": 2, "C": 2})

    def test_pair_unreachable_at_low_bound(self):
        # B=2 C=2 needs two firings of A -> B + C; within k=1 it cannot be reached
        self.assertEqual(reach(CAT_PAIR, 1, {"B": 2, "C": 2})["verdict"], Verdict.UNREACHABLE)

    def test_pair_unreachable_coupled_products(self):
        # each firing makes one B and one C together, so B and C stay equal;
        # B=2 C=1 is unreachable for any k
        self.assertEqual(reach(CAT_PAIR, 5, {"B": 2, "C": 1})["verdict"], Verdict.UNREACHABLE)

    def test_catalysis_commuting_square_holds(self):
        # I_s(p) vs L(I_t(T(p))) under π on a catalysis corpus, incl. spectators
        for crn, k, target in [
            (CAT_AMP, 2, {"B": 4}),
            (CAT_PAIR, 2, {"B": 2, "C": 2}),
            ("species A B C\ninit A 3 B 0 C 7\nrxn A -> 2 B\n", 2, {"B": 4, "C": 7}),
            ("species A B C D\ninit A 3 B 0 C 0 D 5\nrxn A -> B + C\n", 2, {"B": 2, "C": 2, "D": 5}),
        ]:
            verdict, result = cross_check(crn, k, target)
            self.assertEqual(verdict, Verdict.REACHABLE, crn)
            self.assertTrue(result.ok, f"{crn}: {result.divergence}")

    def test_catalysis_unreachable_cross_check_aligns(self):
        verdict, result = cross_check(CAT_AMP, 1, {"B": 4})
        self.assertEqual(verdict, Verdict.UNREACHABLE)
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
