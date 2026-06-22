"""Shared SMT-LIB interpreter — the ``QF_LIA`` (linear integer arithmetic) model
evaluator (languages/smtlib brief, the registered next increment).

This is the *additive, versioned* extension of the shared evaluator
(``gurdy/languages/smtlib/eval.py``) to the integer fragment: given a
``QF_LIA`` script and a model (an assignment to its free ``Int`` / ``Bool``
constants), evaluate the asserted formulas and report whether the model is a
valid ``sat`` witness — exactly as the ``QF_ABV`` path does for bit-vectors
(SOLVERS.md §4-5). It is **not** the solver.

All unit models below are **hand-constructed**, so the tests are deterministic
and ungated (they do not depend on a solver being present). The end-to-end
``crn-smtlib`` agreement test keeps a solver-free path; a z3-backed path runs
additionally when z3 is available.
"""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.languages.smtlib import INTERPRETER_VERSION
from gurdy.languages.smtlib.eval import evaluate, value_of
from gurdy.languages.smtlib.interp import interpret


def _script(decls, *asserts):
    """A tiny QF_LIA script: ``decls`` is ``[(name, "Int"|"Bool"), ...]``."""
    head = "(set-logic QF_LIA)\n"
    head += "".join(f"(declare-fun {n} () {s})\n" for n, s in decls)
    body = "".join(f"(assert {a})\n" for a in asserts)
    return (head + body + "(check-sat)\n").encode("utf-8")


class TestLiaLiterals(unittest.TestCase):
    def test_int_literal_arbitrary_precision(self):
        # SMT Int is unbounded; Python's int is the faithful match.
        big = 10 ** 50
        s = _script([("x", "Int")], f"(= x {big})")
        self.assertTrue(evaluate(s, {"x": big}))
        self.assertFalse(evaluate(s, {"x": big + 1}))

    def test_omitted_int_defaults_to_zero(self):
        self.assertTrue(evaluate(_script([("x", "Int")], "(= x 0)"), {}))

    def test_omitted_bool_defaults_to_false(self):
        self.assertTrue(evaluate(_script([("b", "Bool")], "(= b false)"), {}))


class TestLiaArithmetic(unittest.TestCase):
    def test_add_sub_binary_and_unary(self):
        s = _script([("x", "Int"), ("y", "Int")], "(= (+ x y) 7)", "(= (- x y) 1)")
        self.assertTrue(evaluate(s, {"x": 4, "y": 3}))
        self.assertFalse(evaluate(s, {"x": 5, "y": 3}))
        # unary minus: (- x) negates; with x=5, (- x) == -5 == (- 0 5)
        self.assertTrue(evaluate(_script([("x", "Int")], "(= (- x) (- 0 5))"), {"x": 5}))
        self.assertFalse(evaluate(_script([("x", "Int")], "(= (- x) (- 0 5))"), {"x": -5}))

    def test_add_mul_are_variadic(self):
        self.assertTrue(evaluate(_script([("x", "Int")], "(= x (+ 1 2 3 4))"), {"x": 10}))
        self.assertTrue(evaluate(_script([("x", "Int")], "(= x (* 2 3 4))"), {"x": 24}))

    def test_mul_by_constant(self):
        s = _script([("x", "Int")], "(= (* 3 x) 21)")
        self.assertTrue(evaluate(s, {"x": 7}))
        self.assertFalse(evaluate(s, {"x": 8}))

    def test_abs(self):
        self.assertTrue(evaluate(_script([("x", "Int")], "(= (abs x) 9)"), {"x": -9}))
        self.assertTrue(evaluate(_script([("x", "Int")], "(= (abs x) 9)"), {"x": 9}))
        self.assertFalse(evaluate(_script([("x", "Int")], "(= (abs x) 9)"), {"x": -8}))

    def test_div_mod_euclidean_per_smtlib(self):
        # SMT-LIB Ints theory: 0 <= (mod m n) < |n|, m = n*(div m n)+(mod m n).
        # Differs from Python //,% for negative operands. SMT-LIB writes a
        # negative integer as ``(- n)``, never ``-n``.
        def lit(v):
            return str(v) if v >= 0 else f"(- {-v})"

        cases = [
            (7, 3, 2, 1), (-7, 3, -3, 2), (7, -3, -2, 1), (-7, -3, 3, 2),
            (6, 3, 2, 0), (-6, 4, -2, 2),
        ]
        for m, n, q, r in cases:
            self.assertTrue(
                evaluate(_script([], f"(= (div {lit(m)} {lit(n)}) {lit(q)})"), {}),
                f"div {m} {n} != {q}",
            )
            self.assertTrue(
                evaluate(_script([], f"(= (mod {lit(m)} {lit(n)}) {lit(r)})"), {}),
                f"mod {m} {n} != {r}",
            )

    def test_div_by_zero_hard_aborts(self):
        with self.assertRaises(Unsupported):
            evaluate(_script([("x", "Int")], "(= (div x 0) 0)"), {"x": 5})
        with self.assertRaises(Unsupported):
            evaluate(_script([("x", "Int")], "(= (mod x 0) 0)"), {"x": 5})


class TestLiaComparisons(unittest.TestCase):
    def test_strict_and_nonstrict(self):
        for op, holds_eq in [("<", False), ("<=", True), (">", False), (">=", True)]:
            s = _script([("x", "Int")], f"({op} x 5)")
            # x == 5: strict ops fail, non-strict hold
            self.assertEqual(evaluate(s, {"x": 5}), holds_eq, op)
        self.assertTrue(evaluate(_script([("x", "Int")], "(< x 5)"), {"x": 4}))
        self.assertTrue(evaluate(_script([("x", "Int")], "(> x 5)"), {"x": 6}))

    def test_chained_comparison(self):
        # SMT-LIB < is n-ary: (< a b c) means a<b and b<c.
        s = _script([("a", "Int"), ("b", "Int"), ("c", "Int")], "(< a b c)")
        self.assertTrue(evaluate(s, {"a": 1, "b": 2, "c": 3}))
        self.assertFalse(evaluate(s, {"a": 1, "b": 3, "c": 2}))

    def test_equality_and_distinct_over_ints(self):
        eq = _script([("a", "Int"), ("b", "Int")], "(= a b)")
        self.assertTrue(evaluate(eq, {"a": 5, "b": 5}))
        self.assertFalse(evaluate(eq, {"a": 5, "b": 6}))
        di = _script([("a", "Int"), ("b", "Int"), ("c", "Int")], "(distinct a b c)")
        self.assertTrue(evaluate(di, {"a": 1, "b": 2, "c": 3}))
        self.assertFalse(evaluate(di, {"a": 1, "b": 2, "c": 1}))


class TestLiaBooleanLayer(unittest.TestCase):
    def test_connectives_over_int_atoms(self):
        s = _script([("x", "Int")],
                    "(and (>= x 0) (<= x 10))",
                    "(or (= x 3) (= x 7))",
                    "(=> (> x 5) (distinct x 3))",
                    "(not (< x 0))")
        self.assertTrue(evaluate(s, {"x": 7}))
        self.assertFalse(evaluate(s, {"x": 4}))  # neither 3 nor 7

    def test_xor(self):
        s = _script([("x", "Int")], "(xor (> x 0) (> x 10))")
        self.assertTrue(evaluate(s, {"x": 5}))     # T xor F
        self.assertFalse(evaluate(s, {"x": 20}))   # T xor T
        self.assertFalse(evaluate(s, {"x": -1}))   # F xor F

    def test_ite_returns_int(self):
        s = _script([("x", "Int"), ("y", "Int")], "(= (ite (< x y) x y) 3)")  # min == 3
        self.assertTrue(evaluate(s, {"x": 3, "y": 9}))
        self.assertFalse(evaluate(s, {"x": 9, "y": 4}))

    def test_bool_constant_assignment(self):
        # a free Bool constant the model assigns
        s = _script([("b", "Bool"), ("x", "Int")], "(=> b (>= x 1))")
        self.assertTrue(evaluate(s, {"b": True, "x": 5}))
        self.assertFalse(evaluate(s, {"b": True, "x": 0}))
        self.assertTrue(evaluate(s, {"b": False, "x": 0}))  # antecedent false
        # the z3 backend stringifies Bools; accept "True"/"False" too
        self.assertTrue(evaluate(s, {"b": "False", "x": 0}))


class TestLiaWitnessHoldsOrFails(unittest.TestCase):
    """The core witness-check contract: a valid model -> the witness holds; a
    wrong model -> it fails (SOLVERS.md §4)."""

    def test_valid_model_holds_wrong_model_fails(self):
        # A small linear system: 2x + 3y = 12, x - y = 1  =>  x=3, y=2.
        s = _script([("x", "Int"), ("y", "Int")],
                    "(= (+ (* 2 x) (* 3 y)) 12)", "(= (- x y) 1)",
                    "(>= x 0)", "(>= y 0)")
        self.assertTrue(evaluate(s, {"x": 3, "y": 2}))   # the witness
        self.assertFalse(evaluate(s, {"x": 0, "y": 4}))  # 2nd assert fails
        self.assertFalse(evaluate(s, {"x": 3, "y": -2}))  # domain fails

    def test_interp_wraps_eval_as_sat_observable(self):
        s = _script([("x", "Int")], "(= x 5)")
        self.assertEqual(interpret(s, {"model": {"x": 5}}), [{"sat": True}])
        self.assertEqual(interpret(s, {"model": {"x": 6}}), [{"sat": False}])


class TestLiaOutOfFragmentAborts(unittest.TestCase):
    def test_unknown_int_op_hard_aborts_typed(self):
        s = _script([("x", "Int")], "(= (intsqrt x) 2)")
        with self.assertRaises(Unsupported) as cm:
            evaluate(s, {"x": 4})
        self.assertIn("smtlib:", str(cm.exception))

    def test_let_is_out_of_fragment(self):
        # ``let`` is not handled in the QF_ABV path either, so it stays out of
        # fragment and hard-aborts (not silently mis-evaluated).
        s = _script([("x", "Int")], "(let ((y x)) (= y 5))")
        with self.assertRaises(Unsupported):
            evaluate(s, {"x": 5})

    def test_unknown_sort_hard_aborts(self):
        s = b"(set-logic QF_LIA)\n(declare-fun r () Real)\n(assert (= r 1))\n(check-sat)\n"
        with self.assertRaises(Unsupported):
            evaluate(s, {})


class TestLiaDeterminism(unittest.TestCase):
    """Twice-and-diff / value-stable: the evaluator is a pure function
    (ARCHITECTURE.md §4)."""

    def test_evaluate_is_value_stable(self):
        s = _script([("x", "Int"), ("y", "Int"), ("b", "Bool")],
                    "(=> b (= (+ x y) 5))", "(>= x 0)", "(< y 10)")
        model = {"x": 2, "y": 3, "b": True}
        first = evaluate(s, dict(model))
        for _ in range(5):
            self.assertEqual(evaluate(s, dict(model)), first)
        self.assertTrue(first)

    def test_value_of_pure_on_repeated_calls(self):
        term = ["+", ["*", "2", "x"], ["abs", ["-", "y"]]]
        env = {"x": 4, "y": -3}
        vals = {value_of(term, dict(env)) for _ in range(8)}
        self.assertEqual(vals, {11})  # 2*4 + |-(-3)| = 8 + 3


class TestLiaVersionBump(unittest.TestCase):
    def test_interpreter_version_records_the_lia_bump(self):
        # §6 versioned event: the QF_LIA arm bumped the shared interp version.
        self.assertEqual(INTERPRETER_VERSION, "0.2")


class TestCrnSmtlibEndToEndAgreement(unittest.TestCase):
    """End-to-end (read-only): import ``gurdy.pairs.crn_smtlib`` to produce a
    real ``QF_LIA`` script + a satisfying model, evaluate it with the new shared
    evaluator, and assert it AGREES with crn's interpreter-replay verdict. The
    crn pair is NOT modified."""

    CRN = "species A B\ninit A 2 B 0\nrxn A -> B\n"

    def _hand_model(self, crn, k, schedule):
        """Build a QF_LIA model dict from a hand-chosen firing ``schedule`` by
        replaying it through the CRN interpreter — solver-free."""
        from gurdy.languages.crn.eval import step
        from gurdy.languages.crn.model import as_network

        net = as_network(crn)
        behavior = step(net, {"steps": k, "schedule": schedule})
        model = {}
        # initial marking (step 0)
        init = net.init_map
        for s in net.species:
            model[f"x{s}_0"] = init[s]
        # post-step markings (steps 1..k) and firing flags
        for t, row in enumerate(behavior):
            for s in net.species:
                model[f"x{s}_{t + 1}"] = row[s]
            model[f"f0_{t}"] = schedule[t] == 0
        return model, behavior

    def test_solver_free_agreement(self):
        # Translate the real QF_LIA script via the (unmodified) crn translator.
        from gurdy.pairs.crn_smtlib.translate import translate

        k, target = 2, {"B": 1}
        art = translate({"crn": self.CRN, "k": k, "target": target})

        # Hand-pick a firing schedule that reaches B==1: fire R0 at step 0.
        model, behavior = self._hand_model(self.CRN, k, [0, None])
        # crn's interpreter-replay verdict (witness_ok analogue): does some
        # post-step marking hit the target?
        replay_reaches = any(
            all(row.get(sp) == c for sp, c in target.items()) for row in behavior
        )
        # the shared QF_LIA evaluator on the same model:
        smt_ok = evaluate(art, model)
        self.assertTrue(replay_reaches)
        self.assertEqual(smt_ok, replay_reaches)  # they AGREE

        # And a schedule that does NOT reach the target disagrees with a model
        # claiming it does: an honest non-witness fails the SMT evaluator.
        no_fire_model, no_fire_beh = self._hand_model(self.CRN, k, [None, None])
        self.assertFalse(
            any(all(r.get(sp) == c for sp, c in target.items()) for r in no_fire_beh)
        )
        self.assertFalse(evaluate(art, no_fire_model))

    def test_z3_backed_agreement_when_available(self):
        try:
            import z3  # noqa: F401
        except ImportError:
            self.skipTest("z3 not available on host (solver-free path covers this)")
        from gurdy.pairs.crn_smtlib import reach

        info = reach(self.CRN, k=2, target={"B": 1})
        # With the QF_LIA arm, the shared evaluator now resolves smt_model_ok
        # (previously None) and it AGREES with the interpreter-replay witness_ok.
        self.assertIsNotNone(info.get("smt_model_ok"))
        self.assertEqual(info["smt_model_ok"], info["witness_ok"])
        self.assertTrue(info["witness_ok"])


if __name__ == "__main__":
    unittest.main()
