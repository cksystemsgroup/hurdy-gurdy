"""python-smtlib pair tests (z3-backed where a decision is needed): the
schema-determined SSA lowering, the typed unsupported aborts, the
commuting-square cross-check, and the input-assignment witness carry-back.

The pair is the minimal vertical slice (PAIRING.md §1): one in-scope construct
class (a straight-line integer function: assignment + linear arithmetic +
trailing assert) translated end-to-end; everything else hard-aborts
``unsupported: python:<construct>``.
"""

import os
import subprocess
import sys
import unittest

import gurdy.pairs.python_smtlib  # noqa: F401  (registers the pair)
from gurdy.core.coverage import measure
from gurdy.core.errors import Unsupported
from gurdy.core.registry import get_pair, list_pairs
from gurdy.core.solver import Verdict
from gurdy.pairs.python_smtlib import (
    cross_check,
    decode_inputs,
    lift,
    projection_for,
    reach,
    translate,
)
from gurdy.pairs.python_smtlib.inventory import ALL_PROBES, coverage
from gurdy.languages.python.subset import load

# An assert that is violable for some input (y = x + 1 is never < x).
VIOLABLE = "def g(x):\n    y = x + 1\n    assert y < x\n"
# An assert that holds for every integer input (2*x always equals x + x).
HOLDS = "def h(x):\n    y = 2 * x\n    assert y == x + x\n"


def _z3() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except ImportError:
        return False


class TestRegistrationSmoke(unittest.TestCase):
    def test_pair_registered(self):
        self.assertIn("python-smtlib", list_pairs())

    def test_square_edges_callable(self):
        pair = get_pair("python-smtlib")
        self.assertEqual((pair.source, pair.target), ("python", "smtlib"))
        self.assertEqual(pair.fidelity, "predicted")
        # every edge-op of the square is wired and callable
        self.assertTrue(callable(pair.translator))          # T
        self.assertTrue(callable(pair.target_to_source))    # L
        self.assertTrue(callable(pair.source_interpreter))  # I_s (pinned CPython)
        self.assertTrue(callable(pair.target_interpreter))  # I_t (shared SMT-LIB)

    def test_exposes_probes(self):
        self.assertIs(get_pair("python-smtlib").probes, ALL_PROBES)


class TestTranslationSchema(unittest.TestCase):
    def test_deterministic_twice_and_diff(self):
        self.assertEqual(translate(VIOLABLE), translate(VIOLABLE))

    def test_emits_qf_lia(self):
        text = translate(VIOLABLE).decode()
        self.assertIn("(set-logic QF_LIA)", text)
        self.assertIn("(check-sat)", text)

    def test_schema_byte_exact(self):
        # the full SSA schema for a tiny two-assignment program, byte-for-byte.
        src = "def f(x):\n    y = 2 * x + 1\n    z = y - x\n    assert z == x + 1\n"
        text = translate(src).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun x__in () Int)\n"
            "(declare-fun y__0 () Int)\n"
            "(assert (= y__0 (+ (* 2 x__in) 1)))\n"
            "(declare-fun z__1 () Int)\n"
            "(assert (= z__1 (- y__0 x__in)))\n"
            "(assert (not (= z__1 (+ x__in 1))))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_ssa_rebinds_same_name(self):
        # x = x + 1 reads the previous SSA version, writes a fresh one.
        text = translate("def f(x):\n    x = x + 1\n    assert x > 0\n").decode()
        self.assertIn("(assert (= x__0 (+ x__in 1)))", text)
        self.assertIn("(assert (not (> x__0 0)))", text)

    def test_negative_literal_lowering(self):
        text = translate("def f(x):\n    y = x - 5\n    assert y == x + -3\n").decode()
        self.assertIn("(+ x__in (- 3))", text)  # -3 emitted as (- 3)

    def test_comparison_heads(self):
        for op, head in [("==", "(= "), ("!=", "(distinct "), ("<", "(< "),
                          ("<=", "(<= "), (">", "(> "), (">=", "(>= ")]:
            text = translate(f"def f(x):\n    assert x {op} 0\n").decode()
            self.assertIn(f"(not {head}", text, op)

    def test_accepts_program_object_and_dict(self):
        prog = load(VIOLABLE)
        self.assertEqual(translate(prog), translate(VIOLABLE))
        self.assertEqual(translate({"python": VIOLABLE}), translate(VIOLABLE))


class TestUnsupportedAborts(unittest.TestCase):
    def _abort(self, src):
        with self.assertRaises(Unsupported) as cm:
            translate(src)
        self.assertEqual(cm.exception.language, "python")
        return cm.exception

    def test_if(self):
        self.assertEqual(self._abort("def f(x):\n    if x > 0:\n        y = 1\n    assert x == x\n").construct, "If")

    def test_loop(self):
        self.assertEqual(self._abort("def f(x):\n    while x > 0:\n        x = x - 1\n    assert x == 0\n").construct, "While")

    def test_floordiv(self):
        self.assertEqual(self._abort("def f(x):\n    y = x // 2\n    assert y == y\n").construct, "FloorDiv")

    def test_modulo(self):
        self.assertEqual(self._abort("def f(x):\n    y = x % 3\n    assert y == y\n").construct, "Mod")

    def test_nonlinear(self):
        self.assertEqual(self._abort("def f(x):\n    y = x * x\n    assert y == y\n").construct, "nonlinear-mul")

    def test_import(self):
        self.assertEqual(self._abort("import os\ndef f(x):\n    assert x == x\n").construct, "Import")


class TestCoverageHistogram(unittest.TestCase):
    def test_one_covered_rest_itemized(self):
        report = coverage()
        self.assertEqual(report.covered, {"straightline-int"})
        # the unsupported histogram: every other construct blocked, named.
        self.assertEqual(
            report.histogram,
            {
                "If": 1, "While": 1, "For": 1,
                "FloorDiv": 1, "Mod": 1, "Div": 1, "Pow": 1,
                "nonlinear-mul": 1, "BoolOp": 1, "Call": 1, "List": 1,
                "Return": 1, "Import": 1, "no-assert": 1,
            },
        )
        self.assertLess(report.fraction, 1.0)  # honest partial, not built

    def test_a_real_gap_is_typed(self):
        bogus = {"WIDGET": "def f(x):\n    y = x // 2\n    assert y == y\n"}
        report = measure(translate, bogus)
        self.assertEqual(report.fraction, 0.0)
        self.assertIn("FloorDiv", report.histogram)


class TestCarryBack(unittest.TestCase):
    def test_decode_inputs_from_model(self):
        prog = load("def f(a, b):\n    s = a + b\n    assert s == s\n")
        model = {"a__in": "-2", "b__in": 7}
        self.assertEqual(decode_inputs(prog, model), {"a": -2, "b": 7})

    def test_decode_missing_input_defaults_zero(self):
        prog = load(VIOLABLE)
        self.assertEqual(decode_inputs(prog, {}), {"x": 0})

    def test_lift_replays_to_violated_state(self):
        # a hand-built witness x = -1 fires (y = 0 is not < -1).
        behavior = lift({"python": VIOLABLE, "model": {"x__in": "-1"}})
        self.assertTrue(behavior[-1]["__violated__"])
        self.assertEqual(behavior[-1]["x"], -1)

    def test_projection_lists_program_variables(self):
        pi = projection_for("def f(a):\n    b = a + 1\n    assert b == b\n")
        self.assertEqual(pi.fields, ("a", "b", "__stmt__", "__cond__", "__violated__"))


@unittest.skipUnless(_z3(), "z3 not installed")
class TestReachWithZ3(unittest.TestCase):
    def test_violable_with_verified_witness(self):
        info = reach(VIOLABLE)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["smt_model_ok"])   # SMT-level model check
        self.assertTrue(info["witness_ok"])     # CPython replay fires the assert
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_holds_for_all_is_unreachable(self):
        self.assertEqual(reach(HOLDS)["verdict"], Verdict.UNREACHABLE)

    def test_arbitrary_precision_property_holds(self):
        # 2*x == x + x over unbounded Int — no 64-bit wraparound counterexample
        # exists (the faithfulness payoff of Int over bit-vectors).
        self.assertEqual(reach(HOLDS)["verdict"], Verdict.UNREACHABLE)

    def test_decoded_input_actually_violates(self):
        info = reach(VIOLABLE)
        x = info["inputs"]["x"]
        # independently: y = x + 1 is indeed not < x
        self.assertFalse((x + 1) < x)

    def test_commuting_square_holds(self):
        # I_s(p) vs L(I_t(T(p))) under π on a tiny corpus of violable programs.
        corpus = [
            VIOLABLE,
            "def f(x):\n    y = 3 * x - 2\n    assert y > x\n",          # violable (x small)
            "def f(a, b):\n    s = a - b\n    assert s == a + b\n",      # violable (b != 0)
        ]
        for src in corpus:
            verdict, result = cross_check(src)
            self.assertEqual(verdict, Verdict.REACHABLE, src)
            self.assertTrue(result.ok, f"{src}: {result.divergence}")

    def test_unreachable_cross_check_trivially_aligns(self):
        verdict, result = cross_check(HOLDS)
        self.assertEqual(verdict, Verdict.UNREACHABLE)
        self.assertTrue(result.ok)


@unittest.skipUnless(_z3(), "z3 not installed")
class TestTranslatorDeterminismAcrossHashseed(unittest.TestCase):
    def test_byte_identical_across_hashseed(self):
        src = "def f(x, y):\n    a = 2 * x + y - 1\n    b = a - x\n    assert b == x + y - 1\n"
        code = (
            "from gurdy.pairs.python_smtlib import translate;"
            f"import sys; sys.stdout.buffer.write(translate({src!r}))"
        )
        outs = []
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outs.append(subprocess.check_output([sys.executable, "-c", code], env=env))
        self.assertEqual(len(set(outs)), 1, "translator output not byte-stable across PYTHONHASHSEED")


if __name__ == "__main__":
    unittest.main()
