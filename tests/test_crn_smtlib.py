"""crn-smtlib pair tests (z3-backed where a decision is needed): the
schema-determined unrolling, the typed unsupported aborts, the commuting-square
cross-check, and the firing-flag witness carry-back.

The pair is the fully-widened slice (PAIRING.md §1 "start thin, then widen"):
ten in-scope reaction classes — the unimolecular ``A -> B``, both bimolecular
shapes (``A + B -> C`` and ``2 A -> B``), both catalysis / multi-product shapes
(``A -> 2 B`` and ``A -> B + C``), synthesis (``0 -> A``), degradation
(``A -> 0``), self-loop (``A -> A``), multiple-reactions (≥2 reactions whose
per-step firing selects which one fires) and empty-network (no reactions) —
translated end-to-end; the remaining out-of-scope reaction *shapes* (reactant or
product molecularity ≥3, a molecularity-2 product on a non-unit reactant side,
the both-empty ``0 -> 0``) still hard-abort ``unsupported: crn:<construct>``.
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
# Synthesis (0 -> A, empty reactant side, always enabled) and degradation
# (A -> 0, empty product side): each fits the net-stoichiometry schema unchanged.
SYNTH = "species A B\ninit A 0 B 0\nrxn 0 -> A\n"
DEGRAD = "species A B\ninit A 3 B 0\nrxn A -> 0\n"
# Self-loop (A -> A, product also a reactant): net stoichiometry 0 on A, the
# enabledness precondition (xA >= 1) still required.
SELFLOOP = "species A B\ninit A 1 B 0\nrxn A -> A\n"
# Multiple-reactions: ≥2 reactions whose per-step firing selects which one fires.
# A linear chain A -> B -> C (reach C needs both); and a branch A -> B, A -> C.
MULTI_CHAIN = "species A B C\ninit A 1 B 0 C 0\nrxn A -> B\nrxn B -> C\n"
MULTI_BRANCH = "species A B C\ninit A 2 B 0 C 0\nrxn A -> B\nrxn A -> C\n"
# Empty-network: no reactions — only stuttering, so the target is reachable iff
# it equals the initial marking.
EMPTY = "species A B\ninit A 1 B 0\n"


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

    def test_synthesis_schema_byte_exact(self):
        # 0 -> A : empty reactant side, enabledness is the literal `true`
        # (always enabled), net +1 increment on A; B is a spectator.
        text = translate({"crn": "species A B\ninit A 0 B 0\nrxn 0 -> A\n",
                          "k": 1, "target": {"A": 1}}).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun xA_0 () Int)\n(declare-fun xB_0 () Int)\n"
            "(declare-fun xA_1 () Int)\n(declare-fun xB_1 () Int)\n"
            "(declare-fun f0_0 () Bool)\n"
            "(assert (= xA_0 0))\n(assert (= xB_0 0))\n"
            "(assert (>= xA_0 0))\n(assert (>= xB_0 0))\n"
            "(assert (>= xA_1 0))\n(assert (>= xB_1 0))\n"
            "(assert (=> f0_0 true))\n"
            "(assert (= xA_1 (ite f0_0 (+ xA_0 1) xA_0)))\n"
            "(assert (= xB_1 (ite f0_0 xB_0 xB_0)))\n"
            "(assert (or (= xA_0 1) (= xA_1 1)))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_degradation_schema_byte_exact(self):
        # A -> 0 : empty product side, enabledness xA>=1, net -1 decrement on A.
        text = translate({"crn": "species A B\ninit A 1 B 0\nrxn A -> 0\n",
                          "k": 1, "target": {"A": 0}}).decode()
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
            "(assert (= xB_1 (ite f0_0 xB_0 xB_0)))\n"
            "(assert (or (= xA_0 0) (= xA_1 0)))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_multiple_reactions_schema_byte_exact(self):
        # A -> B, B -> C : two firing flags per step, a mutual-exclusion clause,
        # and a nested ite chain (one level per reaction, reaction order) for each
        # species' net-stoichiometry update.
        text = translate({"crn": MULTI_CHAIN, "k": 1, "target": {"C": 1}}).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun xA_0 () Int)\n(declare-fun xB_0 () Int)\n(declare-fun xC_0 () Int)\n"
            "(declare-fun xA_1 () Int)\n(declare-fun xB_1 () Int)\n(declare-fun xC_1 () Int)\n"
            "(declare-fun f0_0 () Bool)\n(declare-fun f1_0 () Bool)\n"
            "(assert (= xA_0 1))\n(assert (= xB_0 0))\n(assert (= xC_0 0))\n"
            "(assert (>= xA_0 0))\n(assert (>= xB_0 0))\n(assert (>= xC_0 0))\n"
            "(assert (>= xA_1 0))\n(assert (>= xB_1 0))\n(assert (>= xC_1 0))\n"
            "(assert (or (not f0_0) (not f1_0)))\n"
            "(assert (=> f0_0 (>= xA_0 1)))\n"
            "(assert (=> f1_0 (>= xB_0 1)))\n"
            "(assert (= xA_1 (ite f0_0 (- xA_0 1) (ite f1_0 xA_0 xA_0))))\n"
            "(assert (= xB_1 (ite f0_0 (+ xB_0 1) (ite f1_0 (- xB_0 1) xB_0))))\n"
            "(assert (= xC_1 (ite f0_0 xC_0 (ite f1_0 (+ xC_0 1) xC_0))))\n"
            "(assert (or (= xC_0 1) (= xC_1 1)))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_self_loop_schema_byte_exact(self):
        # A -> A : product also a reactant, so A's net stoichiometry is 0 (A is
        # preserved by the update), but the enabledness precondition xA >= 1 is
        # still required (it is a real, if no-op-ish, firing).
        text = translate({"crn": SELFLOOP, "k": 1, "target": {"A": 1}}).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun xA_0 () Int)\n(declare-fun xB_0 () Int)\n"
            "(declare-fun xA_1 () Int)\n(declare-fun xB_1 () Int)\n"
            "(declare-fun f0_0 () Bool)\n"
            "(assert (= xA_0 1))\n(assert (= xB_0 0))\n"
            "(assert (>= xA_0 0))\n(assert (>= xB_0 0))\n"
            "(assert (>= xA_1 0))\n(assert (>= xB_1 0))\n"
            "(assert (=> f0_0 (>= xA_0 1)))\n"
            "(assert (= xA_1 (ite f0_0 xA_0 xA_0)))\n"
            "(assert (= xB_1 (ite f0_0 xB_0 xB_0)))\n"
            "(assert (or (= xA_0 1) (= xA_1 1)))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_empty_network_schema_byte_exact(self):
        # no reactions: no firing flags; each species' update is a pure stutter
        # (= x_{t+1} x_t), so the marking never changes and the target is
        # reachable iff it equals the initial marking.
        text = translate({"crn": EMPTY, "k": 1, "target": {"A": 1}}).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun xA_0 () Int)\n(declare-fun xB_0 () Int)\n"
            "(declare-fun xA_1 () Int)\n(declare-fun xB_1 () Int)\n"
            "(assert (= xA_0 1))\n(assert (= xB_0 0))\n"
            "(assert (>= xA_0 0))\n(assert (>= xB_0 0))\n"
            "(assert (>= xA_1 0))\n(assert (>= xB_1 0))\n"
            "(assert (= xA_1 xA_0))\n(assert (= xB_1 xB_0))\n"
            "(assert (or (= xA_0 1) (= xA_1 1)))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_multi_self_loop_empty_deterministic_twice_and_diff(self):
        for crn, k, target in [
            (MULTI_CHAIN, 3, {"C": 1}),
            (MULTI_BRANCH, 2, {"B": 1, "C": 1}),
            (SELFLOOP, 2, {"A": 1}),
            (EMPTY, 2, {"A": 1}),
        ]:
            prog = {"crn": crn, "k": k, "target": target}
            self.assertEqual(translate(prog), translate(prog))

    def test_synthesis_degradation_deterministic_twice_and_diff(self):
        for crn, k, target in [(SYNTH, 3, {"A": 3}), (DEGRAD, 3, {"A": 0})]:
            prog = {"crn": crn, "k": k, "target": target}
            self.assertEqual(translate(prog), translate(prog))

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

    def test_trimolecular_in_multi_reaction_network(self):
        # one out-of-scope reaction in a multi-reaction network still hard-aborts
        # (each reaction is validated independently)
        self.assertEqual(
            self._abort("species A B C\nrxn A -> B\nrxn A + B + C -> A\n", {"B": 1}).construct,
            "trimolecular")

    def test_catalysis_product_molecularity_three(self):
        # product molecularity 3 (A -> 3 B) is out of scope -> crn:catalysis
        self.assertEqual(self._abort("species A B\nrxn A -> 3 B\n", {"B": 3}).construct, "catalysis")

    def test_catalysis_on_nonunit_reactant(self):
        # a molecularity-2 product is only admitted on a single unit reactant;
        # 2 A -> 2 B (and A + B -> 2 C) stay out of scope -> crn:catalysis
        self.assertEqual(self._abort("species A B\nrxn 2 A -> 2 B\n", {"B": 2}).construct, "catalysis")
        self.assertEqual(
            self._abort("species A B C\nrxn A + B -> 2 C\n", {"C": 2}).construct, "catalysis")

    def test_empty_reaction(self):
        # 0 -> 0 has both sides empty: a no-op, not a reaction class -> out of scope
        self.assertEqual(
            self._abort("species A B\nrxn 0 -> 0\n", {"A": 0}).construct, "empty-reaction")

    def test_missing_target(self):
        with self.assertRaises(Unsupported) as cm:
            translate({"crn": UNI, "k": 2})
        self.assertEqual(cm.exception.construct, "no-target")

    def test_undeclared_target_species(self):
        self.assertEqual(self._abort(UNI, {"Z": 0}).construct, "target-species")


class TestCoverageHistogram(unittest.TestCase):
    def test_all_ten_classes_covered(self):
        report = coverage()
        # the fully-widened slice covers all ten probed reaction classes
        self.assertEqual(
            report.covered,
            {
                "unimolecular",
                "bimolecular-hetero",
                "bimolecular-homo",
                "catalysis",
                "catalyst-pair",
                "synthesis",
                "degradation",
                "self-loop",
                "multiple-reactions",
                "empty-network",
            },
        )
        # the ratchet only grew: every previously-covered class stays covered, and
        # the three previously-aborting classes are now covered too
        for prev in (
            "unimolecular", "bimolecular-hetero", "bimolecular-homo",
            "catalysis", "catalyst-pair", "synthesis", "degradation",
            "self-loop", "multiple-reactions", "empty-network",
        ):
            self.assertIn(prev, report.covered)
        # no probed reaction class is blocked any more
        self.assertEqual(report.histogram, {})
        self.assertEqual(report.total, 10)            # denominator unchanged
        self.assertAlmostEqual(report.fraction, 1.0)  # 10/10 probed classes

    def test_a_real_gap_is_still_typed(self):
        # the out-of-scope reaction *shapes* (not probed in the inventory, but
        # rejection-tested) still hard-abort: a molecularity-2 product on a
        # non-unit reactant side (2 A -> 2 B) -> crn:catalysis; status stays
        # partial because such shapes remain unsupported
        bogus = {"WIDGET": {"crn": "species A B\nrxn 2 A -> 2 B\n", "k": 1, "target": {"B": 2}}}
        report = measure(translate, bogus)
        self.assertEqual(report.fraction, 0.0)
        self.assertIn("catalysis", report.histogram)


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

    def test_lift_replays_synthesis(self):
        # 0 -> A fired three times from A=0: each firing makes one A (A 0->1->2->3)
        model = {f"f0_{t}": "True" for t in range(3)}
        behavior = lift({"crn": SYNTH, "k": 3, "model": model})
        self.assertEqual(behavior, [{"A": 1, "B": 0}, {"A": 2, "B": 0}, {"A": 3, "B": 0}])

    def test_lift_replays_degradation(self):
        # A -> 0 fired three times from A=3: each firing eats one A (A 3->2->1->0)
        model = {f"f0_{t}": "True" for t in range(3)}
        behavior = lift({"crn": DEGRAD, "k": 3, "model": model})
        self.assertEqual(behavior, [{"A": 2, "B": 0}, {"A": 1, "B": 0}, {"A": 0, "B": 0}])

    def test_decode_schedule_multiple_reactions(self):
        # with two reactions, the schedule names which one fired each step (the
        # index of the true f<i>_t flag); none true -> a stutter
        model = {"f0_0": "True", "f1_0": "False",   # step 0: reaction 0
                 "f0_1": "False", "f1_1": "True",   # step 1: reaction 1
                 "f0_2": "False", "f1_2": "False"}  # step 2: stutter
        self.assertEqual(decode_schedule(3, model, 2), [0, 1, None])

    def test_lift_replays_multiple_reactions_chain(self):
        # A -> B then B -> C from A=1: fire R0 (A->B) then R1 (B->C)
        model = {"f0_0": "True", "f1_0": "False", "f0_1": "False", "f1_1": "True"}
        behavior = lift({"crn": MULTI_CHAIN, "k": 2, "model": model})
        self.assertEqual(
            behavior, [{"A": 0, "B": 1, "C": 0}, {"A": 0, "B": 0, "C": 1}])

    def test_lift_replays_multiple_reactions_branch(self):
        # A -> B, A -> C from A=2: fire R0 (A->B) then R1 (A->C), one each
        model = {"f0_0": "True", "f1_0": "False", "f0_1": "False", "f1_1": "True"}
        behavior = lift({"crn": MULTI_BRANCH, "k": 2, "model": model})
        self.assertEqual(
            behavior, [{"A": 1, "B": 1, "C": 0}, {"A": 0, "B": 1, "C": 1}])

    def test_lift_replays_self_loop(self):
        # A -> A fired once from A=1: net stoichiometry 0, so A is unchanged
        model = {"f0_0": "True"}
        behavior = lift({"crn": SELFLOOP, "k": 1, "model": model})
        self.assertEqual(behavior, [{"A": 1, "B": 0}])

    def test_lift_replays_empty_network_stutters(self):
        # no reactions: every step is a stutter, so the marking is preserved
        behavior = lift({"crn": EMPTY, "k": 2, "model": {}})
        self.assertEqual(behavior, [{"A": 1, "B": 0}, {"A": 1, "B": 0}])

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


@unittest.skipUnless(_z3(), "z3 not installed")
class TestSynthesisDegradationWithZ3(unittest.TestCase):
    """Per-reaction-class decision for synthesis (``0 -> A``) and degradation
    (``A -> 0``): each decided for bounded reachability (REACHABLE with a firing
    schedule + UNREACHABLE), with the authoritative SMT-level witness check
    (smt_model_ok) agreeing with the CRN-interpreter replay (witness_ok)."""

    def _assert_witnessed(self, info):
        self.assertTrue(info["smt_model_ok"])
        self.assertTrue(info["witness_ok"])
        self.assertTrue(info["model_matches_replay"])
        self.assertEqual(info["smt_model_ok"], info["witness_ok"])

    def test_synthesis_reachable_with_schedule(self):
        # 0 -> A from A=0: A=2 needs two firings (always enabled); reachable k=3
        info = reach(SYNTH, 3, {"A": 2})
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self._assert_witnessed(info)
        # the carried-back trajectory reaches the target marking at some step
        self.assertTrue(any(row["A"] == 2 for row in info["behavior"]))

    def test_synthesis_unreachable_at_low_bound(self):
        # A=3 needs three firings of 0 -> A; within k=2 it cannot be reached
        self.assertEqual(reach(SYNTH, 2, {"A": 3})["verdict"], Verdict.UNREACHABLE)

    def test_synthesis_only_increases(self):
        # synthesis can only grow A from its initial 0; A=0 is reachable only at
        # step 0 (init), but a strictly-smaller-than-init target is impossible —
        # here A starts at 0 and only increases, so A never returns below 0; a
        # negative-looking target is excluded by the non-negativity domain. We
        # check the monotone direction: B (a spectator) can never become 1.
        self.assertEqual(reach(SYNTH, 5, {"B": 1})["verdict"], Verdict.UNREACHABLE)

    def test_degradation_reachable_with_schedule(self):
        # A -> 0 from A=3: A=0 needs three firings; reachable within k=3
        info = reach(DEGRAD, 3, {"A": 0})
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self._assert_witnessed(info)
        self.assertEqual(info["behavior"][-1], {"A": 0, "B": 0})

    def test_degradation_unreachable_at_low_bound(self):
        # A=0 from A=3 needs three firings of A -> 0; within k=2 it cannot be reached
        self.assertEqual(reach(DEGRAD, 2, {"A": 0})["verdict"], Verdict.UNREACHABLE)

    def test_degradation_only_decreases(self):
        # degradation can only shrink A; from A=3 the target A=4 is unreachable
        # for any k (A never grows above its initial count)
        self.assertEqual(reach(DEGRAD, 5, {"A": 4})["verdict"], Verdict.UNREACHABLE)

    def test_synthesis_degradation_commuting_square_holds(self):
        # I_s(p) vs L(I_t(T(p))) under π on a synthesis/degradation corpus, incl.
        # spectators
        for crn, k, target in [
            (SYNTH, 3, {"A": 2}),
            (DEGRAD, 3, {"A": 0}),
            ("species A B C\ninit A 0 B 0 C 5\nrxn 0 -> A\n", 3, {"A": 2, "C": 5}),
            ("species A B C\ninit A 3 B 0 C 7\nrxn A -> 0\n", 3, {"A": 0, "C": 7}),
        ]:
            verdict, result = cross_check(crn, k, target)
            self.assertEqual(verdict, Verdict.REACHABLE, crn)
            self.assertTrue(result.ok, f"{crn}: {result.divergence}")

    def test_synthesis_degradation_unreachable_cross_check_aligns(self):
        for crn, k, target in [(SYNTH, 2, {"A": 3}), (DEGRAD, 2, {"A": 0})]:
            verdict, result = cross_check(crn, k, target)
            self.assertEqual(verdict, Verdict.UNREACHABLE, crn)
            self.assertTrue(result.ok)


@unittest.skipUnless(_z3(), "z3 not installed")
class TestMultipleReactionsWithZ3(unittest.TestCase):
    """Per-step reaction-selection decision for multi-reaction networks: a
    REACHABLE decision whose firing schedule uses BOTH reactions, an UNREACHABLE
    at a low bound, and the authoritative SMT-level witness check (smt_model_ok)
    agreeing with the CRN-interpreter replay (witness_ok)."""

    def _assert_witnessed(self, info):
        self.assertTrue(info["smt_model_ok"])
        self.assertTrue(info["witness_ok"])
        self.assertTrue(info["model_matches_replay"])
        self.assertEqual(info["smt_model_ok"], info["witness_ok"])

    def test_chain_reachable_uses_both_reactions(self):
        # A -> B -> C from A=1: reaching C=1 requires firing R0 (A->B) THEN R1
        # (B->C) — both reactions, selected one per step.
        info = reach(MULTI_CHAIN, 2, {"C": 1})
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self._assert_witnessed(info)
        self.assertEqual(info["schedule"], [0, 1])           # both reactions used
        self.assertEqual(set(info["schedule"]), {0, 1})
        self.assertEqual(info["behavior"][-1], {"A": 0, "B": 0, "C": 1})

    def test_chain_unreachable_at_low_bound(self):
        # C=1 needs two distinct firings (A->B then B->C); within k=1 it cannot
        # be reached (at most one reaction fires per step)
        self.assertEqual(reach(MULTI_CHAIN, 1, {"C": 1})["verdict"], Verdict.UNREACHABLE)

    def test_branch_reachable_each_reaction_once(self):
        # A -> B, A -> C from A=2: reaching B=1 C=1 requires firing each reaction
        # once (the two reactions compete for the shared reactant A)
        info = reach(MULTI_BRANCH, 2, {"B": 1, "C": 1})
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self._assert_witnessed(info)
        self.assertEqual(set(info["schedule"]), {0, 1})      # both reactions used
        self.assertEqual(info["behavior"][-1], {"A": 0, "B": 1, "C": 1})

    def test_mutual_exclusion_one_reaction_per_step(self):
        # the translator's at-most-one constraint means a single step cannot fire
        # two reactions; B=1 C=1 from A=2 needs two steps, so k=1 is unreachable
        self.assertEqual(reach(MULTI_BRANCH, 1, {"B": 1, "C": 1})["verdict"],
                         Verdict.UNREACHABLE)

    def test_multi_reaction_commuting_square_holds(self):
        # I_s(p) vs L(I_t(T(p))) under π on a multi-reaction corpus, incl. a
        # spectator species
        for crn, k, target in [
            (MULTI_CHAIN, 2, {"C": 1}),
            (MULTI_BRANCH, 2, {"B": 1, "C": 1}),
            ("species A B C D\ninit A 1 B 0 C 0 D 6\nrxn A -> B\nrxn B -> C\n",
             2, {"C": 1, "D": 6}),
        ]:
            verdict, result = cross_check(crn, k, target)
            self.assertEqual(verdict, Verdict.REACHABLE, crn)
            self.assertTrue(result.ok, f"{crn}: {result.divergence}")

    def test_multi_reaction_unreachable_cross_check_aligns(self):
        verdict, result = cross_check(MULTI_CHAIN, 1, {"C": 1})
        self.assertEqual(verdict, Verdict.UNREACHABLE)
        self.assertTrue(result.ok)


@unittest.skipUnless(_z3(), "z3 not installed")
class TestSelfLoopWithZ3(unittest.TestCase):
    """Self-loop (``A -> A``): net stoichiometry 0 on the shared species, so a
    firing preserves it, but the enabledness precondition (xA >= 1) is required."""

    def test_self_loop_target_equals_marking_reachable(self):
        # A -> A preserves A: A=1 holds at every step (init already satisfies it)
        info = reach(SELFLOOP, 2, {"A": 1})
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["smt_model_ok"])
        self.assertTrue(info["witness_ok"])
        self.assertTrue(info["model_matches_replay"])

    def test_self_loop_cannot_change_population(self):
        # a self-loop has net-zero effect: from A=1, A=2 is unreachable for any k
        self.assertEqual(reach(SELFLOOP, 5, {"A": 2})["verdict"], Verdict.UNREACHABLE)

    def test_self_loop_enabledness_required(self):
        # A -> A from A=0 is not enabled (needs xA >= 1); A can never become 1
        crn = "species A B\ninit A 0 B 0\nrxn A -> A\n"
        self.assertEqual(reach(crn, 5, {"A": 1})["verdict"], Verdict.UNREACHABLE)

    def test_self_loop_commuting_square_holds(self):
        verdict, result = cross_check(SELFLOOP, 2, {"A": 1})
        self.assertEqual(verdict, Verdict.REACHABLE)
        self.assertTrue(result.ok, result.divergence)


@unittest.skipUnless(_z3(), "z3 not installed")
class TestEmptyNetworkWithZ3(unittest.TestCase):
    """Empty network (no reactions): only stuttering is possible, so the target
    is reachable iff it equals the initial marking."""

    def test_target_equals_init_reachable(self):
        # the init marking is A=1 B=0; target A=1 holds at every (stutter) step
        info = reach(EMPTY, 2, {"A": 1})
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["smt_model_ok"])
        self.assertTrue(info["witness_ok"])
        self.assertTrue(info["model_matches_replay"])
        self.assertEqual(info["schedule"], [None, None])   # all stutter
        self.assertEqual(info["behavior"], [{"A": 1, "B": 0}, {"A": 1, "B": 0}])

    def test_target_differs_from_init_unreachable(self):
        # nothing can change the marking, so a target != init is unreachable
        self.assertEqual(reach(EMPTY, 3, {"A": 0})["verdict"], Verdict.UNREACHABLE)
        self.assertEqual(reach(EMPTY, 3, {"B": 1})["verdict"], Verdict.UNREACHABLE)

    def test_empty_network_commuting_square_holds(self):
        verdict, result = cross_check(EMPTY, 2, {"A": 1})
        self.assertEqual(verdict, Verdict.REACHABLE)
        self.assertTrue(result.ok, result.divergence)

    def test_empty_network_unreachable_cross_check_aligns(self):
        verdict, result = cross_check(EMPTY, 2, {"A": 0})
        self.assertEqual(verdict, Verdict.UNREACHABLE)
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
