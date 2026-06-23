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


# if/else corpus (slice 2). REACHABLE: the assert is violable on some branch.
# UNREACHABLE: it holds on every branch for every input.
IF_REACHABLE = (
    "def f(x):\n    if x > 0:\n        y = 1\n    else:\n        y = -1\n    assert y == 1\n"
)
IF_UNREACHABLE = (
    "def f(x):\n    y = 0\n    if x > 0:\n        y = x\n    assert y >= 0\n"
)


class TestIfElseSchema(unittest.TestCase):
    """The SSA branch-merge lowering (SPEC.md): each arm lowered independently
    from the incoming SSA map, joined by an ``ite`` over the guard."""

    def test_if_else_byte_exact(self):
        text = translate(IF_REACHABLE).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun x__in () Int)\n"
            "(declare-fun y__0 () Int)\n"
            "(assert (= y__0 1))\n"
            "(declare-fun y__1 () Int)\n"
            "(assert (= y__1 (- 1)))\n"
            "(declare-fun y__2 () Int)\n"
            "(assert (= y__2 (ite (> x__in 0) y__0 y__1)))\n"
            "(assert (not (= y__2 1)))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_bare_if_uses_incoming_as_else(self):
        # the empty-else case: the else-version of y is its incoming version y__0.
        text = translate(IF_UNREACHABLE).decode()
        self.assertIn("(assert (= y__2 (ite (> x__in 0) y__1 y__0)))", text)

    def test_unmodified_variable_not_merged(self):
        # x is never reassigned in either arm -> no ite, no extra SSA for x.
        text = translate(
            "def f(x):\n    if x > 0:\n        y = 1\n    else:\n        y = 2\n    assert x == x\n"
        ).decode()
        self.assertNotIn("(ite (> x__in 0) x", text)

    def test_deterministic_twice_and_diff(self):
        self.assertEqual(translate(IF_REACHABLE), translate(IF_REACHABLE))


class TestUnsupportedAborts(unittest.TestCase):
    def _abort(self, src):
        with self.assertRaises(Unsupported) as cm:
            translate(src)
        self.assertEqual(cm.exception.language, "python")
        return cm.exception

    def test_break_in_loop(self):
        # while is in scope (slice 4), but break/continue in a loop body is not.
        self.assertEqual(self._abort("def f(x):\n    while x > 0:\n        break\n    assert x == 0\n").construct, "Break")

    def test_three_deep_loop_nesting_aborts(self):
        # if/else, a single loop in an arm, and one level of loop nesting (slice 5:
        # while inside for inside an arm is depth 2) are all in scope, but a *third*
        # level of loop nesting exceeds MAX_LOOP_DEPTH — still hard-aborts.
        self.assertEqual(
            self._abort(
                "def f(x):\n    if x > 0:\n        for i in range(2):\n            for j in range(2):\n"
                "                for k in range(2):\n                    x = x - 1\n    assert x == x\n"
            ).construct,
            "nesting-too-deep",
        )

    def test_floordiv(self):
        self.assertEqual(self._abort("def f(x):\n    y = x // 2\n    assert y == y\n").construct, "FloorDiv")

    def test_modulo(self):
        self.assertEqual(self._abort("def f(x):\n    y = x % 3\n    assert y == y\n").construct, "Mod")

    def test_nonlinear(self):
        self.assertEqual(self._abort("def f(x):\n    y = x * x\n    assert y == y\n").construct, "nonlinear-mul")

    def test_import(self):
        self.assertEqual(self._abort("import os\ndef f(x):\n    assert x == x\n").construct, "Import")


class TestCoverageHistogram(unittest.TestCase):
    def test_covered_set_and_itemized_gap(self):
        report = coverage()
        # slice 6: straight-line int + if/else (and the bare-if empty-else case)
        # + a bounded for-loop + a BMC-bounded while-loop + a NESTED loop
        # + fixed-length INTEGER LISTS (literal, const + dynamic index read/write,
        # len) — a list of length L modeled as a tuple of L Int SSA vars (QF_LIA).
        self.assertEqual(
            report.covered,
            {
                "straightline-int", "if-else", "bare-if", "for-loop", "while-loop",
                "nested-loop", "list-literal", "list-index-read", "list-index-write",
                "list-dynamic-index", "list-len",
            },
        )
        # the unsupported histogram: every still-out-of-scope construct, named —
        # including the list boundary kept out of scope (a list longer than
        # MAX_LIST_LEN aborts list-too-long; a nested list as nested-list; a
        # length-changing append as the Expr statement). ``List`` is gone (a flat
        # int list literal is now covered).
        self.assertEqual(
            report.histogram,
            {
                "nesting-too-deep": 1, "nonconst-range": 1, "Break": 1,
                "FloorDiv": 1, "Mod": 1, "Div": 1, "Pow": 1,
                "nonlinear-mul": 1, "BoolOp": 1, "Call": 1,
                "list-too-long": 1, "nested-list": 1, "Expr": 1,
                "Return": 1, "Import": 1, "no-assert": 1,
            },
        )
        self.assertNotIn("For", report.histogram)    # nested for-in-for covered (slice 5)
        self.assertNotIn("While", report.histogram)  # while covered (slice 4)
        self.assertNotIn("List", report.histogram)   # flat int list literal covered (slice 6)
        self.assertLess(report.fraction, 1.0)  # honest partial, not built

    def test_ratchet_grew_for_now_covered(self):
        # The coverage ratchet (BENCHMARKS.md §5): the five list constructs moved
        # from unsupported (List/Call/Subscript) to covered; the covered count
        # strictly grew and nothing dropped. (Earlier slices stay covered.)
        report = coverage()
        for c in ("list-literal", "list-index-read", "list-index-write",
                  "list-dynamic-index", "list-len"):
            self.assertIn(c, report.covered)               # the list constructs covered
        self.assertNotIn("List", report.histogram)         # the list-literal List gone
        self.assertNotIn("For", report.histogram)          # slice-5 nested For still gone
        self.assertNotIn("While", report.histogram)        # slice-4 While still gone
        self.assertNotIn("If", report.histogram)           # slice-2 If still gone
        self.assertIn("straightline-int", report.covered)  # the slice-1 construct stayed
        self.assertIn("if-else", report.covered)           # the slice-2 construct stayed
        self.assertIn("for-loop", report.covered)          # the slice-3 construct stayed
        self.assertIn("while-loop", report.covered)        # the slice-4 construct stayed
        self.assertIn("nested-loop", report.covered)       # the slice-5 construct stayed
        self.assertGreaterEqual(len(report.covered), 11)   # grew past slice 5's six

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
class TestIfElseWithZ3(unittest.TestCase):
    """End-to-end if/else (slice 2): reachable model is a violating input, the
    carry-back replays through the branch that fires the assert, and the
    commuting square holds on an if/else corpus."""

    def test_reachable_if_else_with_verified_witness(self):
        info = reach(IF_REACHABLE)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["smt_model_ok"])
        self.assertTrue(info["witness_ok"])
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_carry_back_input_takes_firing_branch(self):
        # The violating input must take the else arm (x <= 0 -> y = -1 -> y != 1),
        # and the CPython replay must actually walk that branch.
        info = reach(IF_REACHABLE)
        self.assertLessEqual(info["inputs"]["x"], 0)        # else-branch input
        self.assertEqual(info["behavior"][-1]["y"], -1)     # replay took the else arm
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_unreachable_if_holds_for_all(self):
        # y is 0 (else/skip) or x>0 (then) -> y >= 0 on every path and input.
        self.assertEqual(reach(IF_UNREACHABLE)["verdict"], Verdict.UNREACHABLE)

    def test_commuting_square_on_if_corpus(self):
        # I_s(p) vs L(I_t(T(p))) under π on a corpus of if/else programs that mix
        # reachable and unreachable verdicts and nested branches.
        reachable = [
            IF_REACHABLE,
            "def f(x):\n    y = 0\n    if x > 5:\n        y = x\n    assert y < 5\n",
            # m = max(a, b); m >= a + 1 is violable when a >= b (then m == a).
            "def f(a, b):\n    if a > b:\n        m = a\n    else:\n        m = b\n    assert m >= a + 1\n",
            ("def f(x):\n    if x > 0:\n        if x > 10:\n            y = 2\n"
             "        else:\n            y = 1\n    else:\n        y = 0\n    assert y == 0\n"),
        ]
        for src in reachable:
            verdict, result = cross_check(src)
            self.assertEqual(verdict, Verdict.REACHABLE, src)
            self.assertTrue(result.ok, f"{src}: {result.divergence}")
        verdict, result = cross_check(IF_UNREACHABLE)
        self.assertEqual(verdict, Verdict.UNREACHABLE)
        self.assertTrue(result.ok)


# Bounded-loop corpus (slice 3). The accumulator s is initialised before the
# loop, the body adds the iteration index i = 0,1,2 (sum 3). FOR_HOLDS encodes the
# loop invariant s == x + 3 (UNREACHABLE — holds for every x); FOR_REACHABLE is the
# off-by-one s == x + 4, violable for every x (the model is any violating input).
FOR_HOLDS = "def f(x):\n    s = x\n    for i in range(3):\n        s = s + i\n    assert s == x + 3\n"
FOR_REACHABLE = "def f(x):\n    s = x\n    for i in range(3):\n        s = s + i\n    assert s == x + 4\n"
# range(0): the body never runs; s stays x; assert s == x holds for all x.
FOR_ZERO = "def f(x):\n    s = x\n    for i in range(0):\n        s = s + i\n    assert s == x\n"


class TestForLoopSchema(unittest.TestCase):
    """The bounded-loop full unrolling (SPEC.md §"Bounded loop"): the body is
    lowered ``n`` times over the advancing SSA, the loop variable bound to the
    concrete iteration index (a literal) on each pass — no per-iteration ``ite``
    (the trip count is constant, every iteration unconditional)."""

    def test_unroll_byte_exact(self):
        text = translate(FOR_HOLDS).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun x__in () Int)\n"
            "(declare-fun s__0 () Int)\n"
            "(assert (= s__0 x__in))\n"
            "(declare-fun s__1 () Int)\n"
            "(assert (= s__1 (+ s__0 0)))\n"     # iteration i = 0
            "(declare-fun s__2 () Int)\n"
            "(assert (= s__2 (+ s__1 1)))\n"     # iteration i = 1
            "(declare-fun s__3 () Int)\n"
            "(assert (= s__3 (+ s__2 2)))\n"     # iteration i = 2
            "(assert (not (= s__3 (+ x__in 3))))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_zero_iterations_emits_no_body(self):
        # range(0): the body lowers zero times; the accumulator keeps its pre-loop
        # SSA version (no per-iteration assignment at all).
        text = translate(FOR_ZERO).decode()
        self.assertIn("(declare-fun s__0 () Int)\n(assert (= s__0 x__in))", text)
        self.assertNotIn("s__1", text)                 # no iteration emitted
        self.assertIn("(assert (not (= s__0 x__in)))", text)

    def test_loop_variable_lowers_to_iteration_literal(self):
        # i is bound to the concrete index per pass — not an Int SSA variable.
        text = translate(FOR_REACHABLE).decode()
        self.assertNotIn("i__", text)                  # no SSA var for the loop variable
        self.assertIn("(+ s__0 0)", text)              # i lowered to 0, 1, 2
        self.assertIn("(+ s__1 1)", text)
        self.assertIn("(+ s__2 2)", text)

    def test_deterministic_twice_and_diff(self):
        self.assertEqual(translate(FOR_REACHABLE), translate(FOR_REACHABLE))


class TestForLoopAborts(unittest.TestCase):
    """The bounded-loop boundary stays hard-aborting (BENCHMARKS.md §3): a loop
    nested past the depth/size cap, a non-constant / start-step range,
    break/continue, a body-only or loop-variable read after the loop. (One level of
    loop nesting is now in scope — slice 5 — see TestNestedLoopSchema.)"""

    def _abort(self, src):
        with self.assertRaises(Unsupported) as cm:
            translate(src)
        self.assertEqual(cm.exception.language, "python")
        return cm.exception

    def test_three_deep_nested_loop_aborts(self):
        # One level of nesting is covered (slice 5); a third level exceeds the cap.
        self.assertEqual(
            self._abort(
                "def f(x):\n    for i in range(2):\n        for j in range(2):\n            for k in range(2):\n"
                "                x = x + 1\n    assert x == x\n"
            ).construct,
            "nesting-too-deep",
        )

    def test_nonconstant_range_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    for i in range(x):\n        pass\n    assert x == x\n").construct,
            "nonconst-range",
        )

    def test_range_start_step_aborts(self):
        self.assertEqual(
            self._abort(
                "def f(x):\n    for i in range(1, 5):\n        x = x + 1\n    assert x == x\n"
            ).construct,
            "range-shape",
        )

    def test_negative_range_aborts(self):
        self.assertEqual(
            self._abort(
                "def f(x):\n    for i in range(-2):\n        x = x + 1\n    assert x == x\n"
            ).construct,
            "negative-range",
        )

    def test_break_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    for i in range(3):\n        break\n    assert x == x\n").construct,
            "Break",
        )

    def test_loop_variable_not_readable_after_loop(self):
        self.assertEqual(
            self._abort("def f(x):\n    for i in range(3):\n        x = x + i\n    assert i == 2\n").construct,
            "undefined-name",
        )

    def test_body_only_variable_not_readable_after_loop(self):
        # y first assigned in the body: undefined when the loop runs zero times.
        self.assertEqual(
            self._abort("def f(x):\n    for i in range(3):\n        y = i\n    assert y == 2\n").construct,
            "undefined-name",
        )


@unittest.skipUnless(_z3(), "z3 not installed")
class TestForLoopWithZ3(unittest.TestCase):
    """End-to-end bounded loop (slice 3): a violable loop yields a model that is a
    violating input (carried back through CPython to the firing assert), and a
    loop invariant is proved UNREACHABLE over all integers; the commuting square
    holds on a loop corpus."""

    def test_reachable_loop_with_verified_witness(self):
        info = reach(FOR_REACHABLE)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["smt_model_ok"])   # SMT-level model check
        self.assertTrue(info["witness_ok"])     # CPython replay fires the assert
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_carry_back_input_drives_loop_to_firing_assert(self):
        # The decoded model input, replayed through CPython, drives the unrolled
        # loop to s = x + 3, which is != x + 4 -> the assert fires.
        info = reach(FOR_REACHABLE)
        x = info["inputs"]["x"]
        self.assertEqual(info["behavior"][-1]["s"], x + 3)  # the loop accumulated 0+1+2
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_loop_invariant_is_unreachable(self):
        # s == x + 3 holds for EVERY integer x (the solver proves it over all
        # inputs — the unbounded-Int faithfulness payoff, no wraparound).
        self.assertEqual(reach(FOR_HOLDS)["verdict"], Verdict.UNREACHABLE)

    def test_zero_iteration_loop_invariant_holds(self):
        self.assertEqual(reach(FOR_ZERO)["verdict"], Verdict.UNREACHABLE)

    def test_commuting_square_on_loop_corpus(self):
        # I_s(p) vs L(I_t(T(p))) under π on loop programs mixing verdicts, an
        # accumulator, a const-multiplied index, and an if inside the loop body.
        reachable = [
            FOR_REACHABLE,
            # c counts how many of the first 4 indices are > 0 (i.e. 3); the
            # off-by-one assert c == 4 is violable for every x.
            ("def f(x):\n    c = 0\n    for i in range(4):\n        if i > 0:\n"
             "            c = c + 1\n    assert c == 4\n"),
        ]
        for src in reachable:
            verdict, result = cross_check(src)
            self.assertEqual(verdict, Verdict.REACHABLE, src)
            self.assertTrue(result.ok, f"{src}: {result.divergence}")
        # an UNREACHABLE invariant aligns trivially (no model).
        verdict, result = cross_check(FOR_HOLDS)
        self.assertEqual(verdict, Verdict.UNREACHABLE)
        self.assertTrue(result.ok)

    def test_const_multiplied_index_accumulates(self):
        # s = 2*0 + 2*1 + 2*2 = 6 over all x -> invariant s == 6 is UNREACHABLE.
        src = "def f(x):\n    s = 0\n    for i in range(3):\n        s = s + 2 * i\n    assert s == 6\n"
        self.assertEqual(reach(src)["verdict"], Verdict.UNREACHABLE)


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

    def test_if_merge_byte_identical_across_hashseed(self):
        # The branch-join iterates the variable order; assert that ordering (and
        # the whole SSA-ite lowering) is byte-stable across hash randomization —
        # a two-arm, two-variable merge is the determinism-sensitive case.
        src = (
            "def f(a, b):\n    if a > b:\n        m = a\n        n = a - b\n"
            "    else:\n        m = b\n        n = b - a\n    assert m >= n\n"
        )
        code = (
            "from gurdy.pairs.python_smtlib import translate;"
            f"import sys; sys.stdout.buffer.write(translate({src!r}))"
        )
        outs = []
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outs.append(subprocess.check_output([sys.executable, "-c", code], env=env))
        self.assertEqual(len(set(outs)), 1, "if-merge output not byte-stable across PYTHONHASHSEED")

    def test_loop_unroll_byte_identical_across_hashseed(self):
        # The bounded-loop unrolling cleans up the loop-local names after the loop
        # (iterating self.current); assert that cleanup order — and the whole
        # unrolled SSA — is byte-stable across hash randomization. Two loop-body
        # variables make the cleanup-order the determinism-sensitive case.
        src = (
            "def f(x):\n    s = x\n    t = x\n    for i in range(3):\n"
            "        s = s + i\n        t = t - i\n    assert s == t\n"
        )
        code = (
            "from gurdy.pairs.python_smtlib import translate;"
            f"import sys; sys.stdout.buffer.write(translate({src!r}))"
        )
        outs = []
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outs.append(subprocess.check_output([sys.executable, "-c", code], env=env))
        self.assertEqual(len(set(outs)), 1, "loop-unroll output not byte-stable across PYTHONHASHSEED")

    def test_while_unroll_byte_identical_across_hashseed(self):
        # The BMC unrolling threads per-iteration active flags and joins two body
        # variables (cleanup iterates self.current); assert the whole K-deep
        # unrolling — guards, ites, termination assert, and body-only cleanup — is
        # byte-stable across hash randomization.
        src = (
            "def f(x):\n    s = x\n    t = 0\n    while t < 3:\n"
            "        s = s + t\n        t = t + 1\n    assert s == x + 3\n"
        )
        code = (
            "from gurdy.pairs.python_smtlib import translate;"
            f"import sys; sys.stdout.buffer.write(translate({src!r}))"
        )
        outs = []
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outs.append(subprocess.check_output([sys.executable, "-c", code], env=env))
        self.assertEqual(len(set(outs)), 1, "while-unroll output not byte-stable across PYTHONHASHSEED")


# BMC-bounded while-loop corpus (slice 4). The bound is WHILE_BOUND = K = 8.
# WHILE_REACHABLE: a countdown whose assert x == 0 is violated for x < 0 (the loop
# skips, x stays negative — a terminating-within-K input). WHILE_HOLDS: the same
# countdown whose invariant x <= 0 holds at exit for every terminating-within-K
# input. WHILE_ACC: a bounded accumulator c reaches 5 within K (5 <= 8), so the
# invariant c == 5 is UNREACHABLE and the off-by-one c == 4 is REACHABLE.
WHILE_REACHABLE = "def f(x):\n    while x > 0:\n        x = x - 1\n    assert x == 0\n"
WHILE_HOLDS = "def f(x):\n    while x > 0:\n        x = x - 1\n    assert x <= 0\n"
WHILE_ACC_HOLDS = "def f(x):\n    c = 0\n    while c < 5:\n        c = c + 1\n    assert c == 5\n"
WHILE_ACC_REACHABLE = "def f(x):\n    c = 0\n    while c < 5:\n        c = c + 1\n    assert c == 4\n"
# A loop that needs MORE than K iterations to reach the would-be violating state:
# to reach c == 20 needs 20 > 8 iterations, so no terminating-within-K run reaches
# it — the assert c == 20 is UNREACHABLE here (the BMC under-approximation), never a
# silent wrong answer.
WHILE_BEYOND_BOUND = "def f(x):\n    c = 0\n    while c < 20:\n        c = c + 1\n    assert c == 20\n"
# A property only a non-terminating run could violate: while x > 0: x += 1 grows
# forever for x > 0, so x <= 0 can be violated only on a run needing > K iterations,
# which the termination assertion excludes -> UNREACHABLE.
WHILE_NONTERM_INVARIANT = "def f(x):\n    while x > 0:\n        x = x + 1\n    assert x <= 0\n"


class TestWhileLoopSchema(unittest.TestCase):
    """The BMC-bounded while unrolling (SPEC.md §"BMC-bounded loop"): the body is
    unrolled to the fixed bound ``K = WHILE_BOUND``, each iteration gated by an
    ``active`` flag (the conjunction of the condition holding so far) with an ``ite``
    carry-through, plus a terminated-within-``K`` assertion."""

    def test_bound_is_eight(self):
        # The bound convention is the fixed module constant (the predictability
        # test, PAIRING.md §2) — kept small (<= 8) to bound SMT size.
        from gurdy.languages.python.subset import WHILE_BOUND
        self.assertEqual(WHILE_BOUND, 8)
        self.assertLessEqual(WHILE_BOUND, 8)

    def test_unrolls_exactly_k_iterations(self):
        # Exactly K active flags (one per unrolled iteration) and K body copies.
        text = translate(WHILE_REACHABLE).decode()
        self.assertEqual(text.count("(declare-fun while__active__"), 8)
        self.assertEqual(text.count("(- x__"), 8)  # x = x - 1 lowered 8 times

    def test_first_two_iterations_byte_exact(self):
        # The active-flag conjunction and the ite carry-through, byte-for-byte.
        text = translate(WHILE_REACHABLE).decode()
        head = (
            "(set-logic QF_LIA)\n"
            "(declare-fun x__in () Int)\n"
            "(declare-fun while__active__0 () Bool)\n"
            "(assert (= while__active__0 (> x__in 0)))\n"        # cond_0
            "(declare-fun x__1 () Int)\n"
            "(assert (= x__1 (- x__in 1)))\n"                    # body iter 0
            "(declare-fun x__2 () Int)\n"
            "(assert (= x__2 (ite while__active__0 x__1 x__in)))\n"  # join 0
            "(declare-fun while__active__3 () Bool)\n"
            "(assert (= while__active__3 (and while__active__0 (> x__2 0))))\n"  # cond_0 ∧ cond_1
            "(declare-fun x__4 () Int)\n"
            "(assert (= x__4 (- x__2 1)))\n"                     # body iter 1
            "(declare-fun x__5 () Int)\n"
            "(assert (= x__5 (ite while__active__3 x__4 x__2)))\n"   # join 1
        )
        self.assertTrue(text.startswith(head), text[: len(head) + 80])

    def test_termination_assertion_then_property(self):
        # After K iterations: (not cond_final) — the loop must have terminated —
        # followed by the property negation, then check-sat.
        text = translate(WHILE_REACHABLE).decode()
        self.assertIn(
            "(assert (not (> x__23 0)))\n"   # terminated within K (cond now false)
            "(assert (not (= x__23 0)))\n"   # property: assert x == 0 violable
            "(check-sat)\n",
            text,
        )

    def test_no_active_flag_is_an_int(self):
        # The active flags are Bool, not Int (a sort error would make z3 reject).
        text = translate(WHILE_REACHABLE).decode()
        self.assertIn("(declare-fun while__active__0 () Bool)", text)
        self.assertNotIn("(declare-fun while__active__0 () Int)", text)

    def test_deterministic_twice_and_diff(self):
        self.assertEqual(translate(WHILE_REACHABLE), translate(WHILE_REACHABLE))


class TestWhileLoopAborts(unittest.TestCase):
    """The while boundary stays hard-aborting (BENCHMARKS.md §3): a loop nested past
    the depth/size cap, break/continue, a while…else, an assert in the body, a
    body-only read after the loop, a non-comparison guard. (One level of loop
    nesting is now in scope — slice 5 — see TestNestedLoopSchema.)"""

    def _abort(self, src):
        with self.assertRaises(Unsupported) as cm:
            translate(src)
        self.assertEqual(cm.exception.language, "python")
        return cm.exception

    def test_three_deep_nested_loop_aborts(self):
        # A for inside a while is now in scope (slice 5); a third level exceeds the
        # MAX_LOOP_DEPTH cap.
        self.assertEqual(
            self._abort(
                "def f(x):\n    while x > 0:\n        for i in range(2):\n            for j in range(2):\n"
                "                x = x - 1\n    assert x == 0\n"
            ).construct,
            "nesting-too-deep",
        )

    def test_nested_loop_over_size_cap_aborts(self):
        # for range(9) inside a while -> the inner for at 9 x 8 = 72 > the product
        # cap (64). (while-in-while at 8 x 8 = 64 is allowed; this overshoots.)
        self.assertEqual(
            self._abort(
                "def f(x):\n    s = 0\n    while s < 100:\n        for i in range(9):\n"
                "            s = s + 1\n    assert s == s\n"
            ).construct,
            "nesting-too-deep",
        )

    def test_break_in_while_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    while x > 0:\n        break\n    assert x == 0\n").construct,
            "Break",
        )

    def test_continue_in_while_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    while x > 0:\n        continue\n    assert x == 0\n").construct,
            "Continue",
        )

    def test_while_else_aborts(self):
        self.assertEqual(
            self._abort(
                "def f(x):\n    while x > 0:\n        x = x - 1\n    else:\n        x = 0\n    assert x == 0\n"
            ).construct,
            "while-else",
        )

    def test_assert_in_while_body_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    while x > 0:\n        assert x > 0\n    assert x == 0\n").construct,
            "branch-assert",
        )

    def test_non_comparison_guard_aborts(self):
        self.assertEqual(
            self._abort(
                "def f(x):\n    while x > 0 and x < 5:\n        x = x - 1\n    assert x == 0\n"
            ).construct,
            "BoolOp",
        )

    def test_body_only_variable_not_readable_after_loop(self):
        # y first assigned in the body: undefined when the loop runs zero times.
        self.assertEqual(
            self._abort(
                "def f(x):\n    while x > 0:\n        y = x\n        x = x - 1\n    assert y == 0\n"
            ).construct,
            "undefined-name",
        )


@unittest.skipUnless(_z3(), "z3 not installed")
class TestWhileLoopWithZ3(unittest.TestCase):
    """End-to-end BMC-bounded while (slice 4): a violable terminating-within-K loop
    yields a model that is a violating input (carried back through CPython to the
    firing assert); an invariant is UNREACHABLE; a counterexample beyond the bound
    is excluded by the termination assertion (no silent wrong answer); the commuting
    square holds on a while corpus."""

    def test_reachable_while_with_verified_witness(self):
        info = reach(WHILE_REACHABLE)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["smt_model_ok"])   # SMT-level model check
        self.assertTrue(info["witness_ok"])     # CPython replay fires the assert
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_carry_back_input_drives_loop_to_firing_assert(self):
        # The decoded model input (x < 0 — the loop skips), replayed through CPython,
        # leaves x unchanged and < 0, so assert x == 0 fires.
        info = reach(WHILE_REACHABLE)
        x = info["inputs"]["x"]
        self.assertLess(x, 0)                                  # a terminating skip input
        self.assertEqual(info["behavior"][-1]["x"], x)        # loop skipped, x unchanged
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_accumulator_carry_back_drives_loop(self):
        # Off-by-one accumulator: c counts up to 5 within K; assert c == 4 fires.
        info = reach(WHILE_ACC_REACHABLE)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertEqual(info["behavior"][-1]["c"], 5)        # loop accumulated to 5
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_loop_invariant_is_unreachable(self):
        # x <= 0 holds at exit for every terminating-within-K input.
        self.assertEqual(reach(WHILE_HOLDS)["verdict"], Verdict.UNREACHABLE)

    def test_bounded_accumulator_invariant_is_unreachable(self):
        # c == 5 holds for every input (c reaches 5 within K and the loop stops).
        self.assertEqual(reach(WHILE_ACC_HOLDS)["verdict"], Verdict.UNREACHABLE)

    def test_counterexample_beyond_bound_is_excluded(self):
        # Reaching c == 20 needs 20 > K iterations; no terminating-within-K run does,
        # so the assert c == 20 is UNREACHABLE — the BMC under-approximation, NOT a
        # silent wrong answer (the verdict reflects "no terminating-within-K
        # counterexample").
        self.assertEqual(reach(WHILE_BEYOND_BOUND)["verdict"], Verdict.UNREACHABLE)

    def test_nonterminating_property_excluded_by_termination(self):
        # x <= 0 could be violated only by a run needing > K iterations (x grows for
        # x > 0); the termination assertion excludes it -> UNREACHABLE.
        self.assertEqual(reach(WHILE_NONTERM_INVARIANT)["verdict"], Verdict.UNREACHABLE)

    def test_commuting_square_on_while_corpus(self):
        # I_s(p) vs L(I_t(T(p))) under π on while programs mixing verdicts, a
        # countdown, a bounded accumulator, and an if inside the loop body.
        reachable = [
            WHILE_REACHABLE,
            WHILE_ACC_REACHABLE,
            # c steps by 2 once past 2, else by 1; reaches >= 6 within K; the
            # off-by-one assert c == 5 is violable.
            ("def f(x):\n    c = 0\n    while c < 6:\n        if c > 2:\n"
             "            c = c + 2\n        else:\n            c = c + 1\n    assert c == 5\n"),
        ]
        for src in reachable:
            verdict, result = cross_check(src)
            self.assertEqual(verdict, Verdict.REACHABLE, src)
            self.assertTrue(result.ok, f"{src}: {result.divergence}")
        # the UNREACHABLE invariants align trivially (no model).
        for src in (WHILE_HOLDS, WHILE_ACC_HOLDS, WHILE_BEYOND_BOUND):
            verdict, result = cross_check(src)
            self.assertEqual(verdict, Verdict.UNREACHABLE, src)
            self.assertTrue(result.ok)


# Nested-loop corpus (slice 5). The inner loop is re-unrolled at each outer
# iteration over the advancing SSA, the unroll sizes multiplying (within the
# MAX_LOOP_DEPTH / MAX_UNROLL_PRODUCT caps).
# NESTED_HOLDS: a double for accumulating 1 each of 2 x 3 = 6 inner-body copies ->
# s == x + 6 holds for every integer x (the nested-loop invariant — UNREACHABLE).
# NESTED_REACHABLE: the off-by-one s == x + 7, violable for every x (REACHABLE).
NESTED_HOLDS = (
    "def f(x):\n    s = x\n    for i in range(2):\n        for j in range(3):\n"
    "            s = s + 1\n    assert s == x + 6\n"
)
NESTED_REACHABLE = (
    "def f(x):\n    s = x\n    for i in range(2):\n        for j in range(3):\n"
    "            s = s + 1\n    assert s == x + 7\n"
)
# A for inside a while (BMC outer): s steps +2 per outer iteration until s >= 4
# (within K), so s == 4 holds (UNREACHABLE) and s == 5 is REACHABLE.
NESTED_FOR_IN_WHILE_HOLDS = (
    "def f(x):\n    s = 0\n    while s < 4:\n        for i in range(2):\n"
    "            s = s + 1\n    assert s == 4\n"
)
# A while inside a for (BMC inner): the for runs twice, each running the inner while
# up to s == x + 3 (within K) -> s == x + 3 holds for every x (UNREACHABLE).
NESTED_WHILE_IN_FOR_HOLDS = (
    "def f(x):\n    s = x\n    for i in range(2):\n        while s < x + 3:\n"
    "            s = s + 1\n    assert s == x + 3\n"
)
# A loop inside an if inside a loop (one level of loop nesting — an if is not a
# loop): the inner for fires only for i = 1, 2 (i > 0), each adding 2 -> s == 4
# holds (UNREACHABLE) and s == 5 is REACHABLE.
LOOP_IN_IF_IN_LOOP_HOLDS = (
    "def f(x):\n    s = 0\n    for i in range(3):\n        if i > 0:\n"
    "            for j in range(2):\n                s = s + 1\n    assert s == 4\n"
)
LOOP_IN_IF_IN_LOOP_REACHABLE = (
    "def f(x):\n    s = 0\n    for i in range(3):\n        if i > 0:\n"
    "            for j in range(2):\n                s = s + 1\n    assert s == 5\n"
)
# Input-steered: the outer while runs `x` times (for x in 0..K), each inner for
# adding 2 -> s == 2*x. assert s != 6 is violable exactly when x == 3 (s == 6) —
# so the carry-back model must drive the nested loops the right number of times.
NESTED_INPUT_STEERED = (
    "def f(x):\n    s = 0\n    c = 0\n    while c < x:\n        for j in range(2):\n"
    "            s = s + 1\n        c = c + 1\n    assert s != 6\n"
)


class TestNestedLoopSchema(unittest.TestCase):
    """The recursive unrolling (SPEC.md §"Nested loops"): the inner loop is lowered
    by the same per-construct schema at each outer iteration over the advancing SSA,
    the shared SSA counter threaded through both levels — no new rule."""

    def test_nested_for_unroll_byte_exact(self):
        # 2 x 3 = 6 unconditional inner-body copies, no ite (both trip counts const).
        text = translate(NESTED_HOLDS).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun x__in () Int)\n"
            "(declare-fun s__0 () Int)\n"
            "(assert (= s__0 x__in))\n"
            "(declare-fun s__1 () Int)\n(assert (= s__1 (+ s__0 1)))\n"   # i=0,j=0
            "(declare-fun s__2 () Int)\n(assert (= s__2 (+ s__1 1)))\n"   # i=0,j=1
            "(declare-fun s__3 () Int)\n(assert (= s__3 (+ s__2 1)))\n"   # i=0,j=2
            "(declare-fun s__4 () Int)\n(assert (= s__4 (+ s__3 1)))\n"   # i=1,j=0
            "(declare-fun s__5 () Int)\n(assert (= s__5 (+ s__4 1)))\n"   # i=1,j=1
            "(declare-fun s__6 () Int)\n(assert (= s__6 (+ s__5 1)))\n"   # i=1,j=2
            "(assert (not (= s__6 (+ x__in 6))))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_nested_for_emits_no_ite(self):
        # Both trip counts are constant -> every iteration unconditional, no ite.
        self.assertNotIn("ite", translate(NESTED_HOLDS).decode())

    def test_for_in_while_threads_active_flags(self):
        # The inner for is unrolled inside each of K outer while body copies, the
        # outer while's active flags gating the whole body copy.
        text = translate(NESTED_FOR_IN_WHILE_HOLDS).decode()
        self.assertEqual(text.count("(declare-fun while__active__"), 8)   # K outer iters
        self.assertIn("ite while__active__", text)                        # outer joins

    def test_deterministic_twice_and_diff(self):
        self.assertEqual(translate(NESTED_REACHABLE), translate(NESTED_REACHABLE))
        self.assertEqual(translate(NESTED_WHILE_IN_FOR_HOLDS), translate(NESTED_WHILE_IN_FOR_HOLDS))


@unittest.skipUnless(_z3(), "z3 not installed")
class TestNestedLoopWithZ3(unittest.TestCase):
    """End-to-end nested loops (slice 5): a violable double loop yields a model that
    is a violating input (carried back through CPython, which runs the real nested
    loops, to the firing assert); a nested-loop invariant is UNREACHABLE; the
    commuting square holds on a nested corpus (a for in a while, a while in a for, a
    loop in an if in a loop)."""

    def test_reachable_nested_loop_with_verified_witness(self):
        info = reach(NESTED_REACHABLE)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["smt_model_ok"])   # SMT-level model check
        self.assertTrue(info["witness_ok"])     # CPython replay fires the assert
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_carry_back_drives_nested_loops_to_firing_assert(self):
        # The decoded model input, replayed through CPython's real nested loops,
        # accumulates s = x + 6 (the double loop adds 1 six times), which is
        # != x + 7 -> the assert fires.
        info = reach(NESTED_REACHABLE)
        x = info["inputs"]["x"]
        self.assertEqual(info["behavior"][-1]["s"], x + 6)
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_input_steered_nested_loop_carry_back(self):
        # The outer while runs x times, the inner for adding 2 each -> s = 2*x; the
        # assert s != 6 fires only when the model drives the loops to s == 6 (x == 3).
        info = reach(NESTED_INPUT_STEERED)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertEqual(info["inputs"]["x"], 3)              # 3 outer iterations
        self.assertEqual(info["behavior"][-1]["s"], 6)        # 3 x 2 inner additions
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_nested_loop_invariant_is_unreachable(self):
        # s == x + 6 holds for EVERY integer x (the solver proves it over all inputs).
        self.assertEqual(reach(NESTED_HOLDS)["verdict"], Verdict.UNREACHABLE)

    def test_loop_in_if_in_loop_reachable(self):
        info = reach(LOOP_IN_IF_IN_LOOP_REACHABLE)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertEqual(info["behavior"][-1]["s"], 4)        # i=1,2 each add 2
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_commuting_square_on_nested_corpus(self):
        # I_s(p) vs L(I_t(T(p))) under π on nested programs mixing the nesting shapes
        # (a for in a for, a for in a while, a loop in an if in a loop) and verdicts.
        reachable = [
            NESTED_REACHABLE,
            NESTED_INPUT_STEERED,
            LOOP_IN_IF_IN_LOOP_REACHABLE,
        ]
        for src in reachable:
            verdict, result = cross_check(src)
            self.assertEqual(verdict, Verdict.REACHABLE, src)
            self.assertTrue(result.ok, f"{src}: {result.divergence}")
        # the UNREACHABLE invariants align trivially (no model).
        for src in (NESTED_HOLDS, NESTED_FOR_IN_WHILE_HOLDS,
                    NESTED_WHILE_IN_FOR_HOLDS, LOOP_IN_IF_IN_LOOP_HOLDS):
            verdict, result = cross_check(src)
            self.assertEqual(verdict, Verdict.UNREACHABLE, src)
            self.assertTrue(result.ok)


@unittest.skipUnless(_z3(), "z3 not installed")
class TestNestedLoopDeterminismAcrossHashseed(unittest.TestCase):
    def test_nested_unroll_byte_identical_across_hashseed(self):
        # The recursive unrolling threads the shared counter through both levels and
        # cleans up each level's loop-local names; assert the whole nested unrolling
        # is byte-stable across hash randomization. Two body variables at two levels
        # make the cleanup-order the determinism-sensitive case.
        src = (
            "def f(x):\n    s = x\n    t = x\n    for i in range(2):\n        for j in range(2):\n"
            "            s = s + i\n            t = t - j\n    assert s == t\n"
        )
        code = (
            "from gurdy.pairs.python_smtlib import translate;"
            f"import sys; sys.stdout.buffer.write(translate({src!r}))"
        )
        outs = []
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outs.append(subprocess.check_output([sys.executable, "-c", code], env=env))
        self.assertEqual(len(set(outs)), 1, "nested-unroll output not byte-stable across PYTHONHASHSEED")


# Fixed-length integer-list corpus (slice 6). A list of length L is a tuple of L
# Int SSA vars (no SMT Array sort — stays in QF_LIA).
# LIST_REACHABLE: a const-index read whose assert is violable (xs[1] == x is x+1==x,
# never holds). LIST_SUM_HOLDS: the sum-of-elements invariant (UNREACHABLE for all x).
LIST_REACHABLE = "def f(x):\n    xs = [x, x + 1, x + 2]\n    y = xs[1]\n    assert y == x\n"
LIST_SUM_HOLDS = (
    "def f(x):\n    xs = [x, x, x]\n    s = xs[0] + xs[1] + xs[2]\n    assert s == 3 * x\n"
)
# A solver-chosen dynamic index hitting a specific element: xs[i] != 30 is violable
# only at i == 2 (the only position holding 30).
LIST_DYNAMIC_READ = "def f(i):\n    xs = [10, 20, 30]\n    y = xs[i]\n    assert y != 30\n"
# A dynamic index write: xs[i] = v makes xs[2] != 0 violable only at i == 2.
LIST_DYNAMIC_WRITE = "def f(i, v):\n    xs = [0, 0, 0]\n    xs[i] = v\n    assert xs[2] == 0\n"
# A list updated in a loop: each position set to its index; xs[2] == 2 holds
# (UNREACHABLE), the off-by-one xs[2] == 3 is REACHABLE.
LIST_LOOP_HOLDS = (
    "def f(x):\n    xs = [0, 0, 0]\n    for i in range(3):\n        xs[i] = i\n    assert xs[2] == 2\n"
)
LIST_LOOP_REACHABLE = (
    "def f(x):\n    xs = [0, 0, 0]\n    for i in range(3):\n        xs[i] = i\n    assert xs[2] == 3\n"
)
# len(xs) -> the static length L (UNREACHABLE invariant n == 3).
LIST_LEN_HOLDS = "def f(x):\n    xs = [x, x, x]\n    n = len(xs)\n    assert n == 3\n"


class TestIntListSchema(unittest.TestCase):
    """The tuple-of-Ints lowering (SPEC.md §"Integer lists"): a list literal -> L
    fresh Int SSA vars; a const index reads/updates a position directly; a dynamic
    index fans out into an ``ite`` chain with a ``0 <= i < L`` range constraint —
    all in QF_LIA (no ``Array`` sort)."""

    def test_list_literal_and_const_read_byte_exact(self):
        text = translate(LIST_REACHABLE).decode()
        expected = (
            "(set-logic QF_LIA)\n"
            "(declare-fun x__in () Int)\n"
            "(declare-fun xs__0 () Int)\n"
            "(assert (= xs__0 x__in))\n"
            "(declare-fun xs__1 () Int)\n"
            "(assert (= xs__1 (+ x__in 1)))\n"
            "(declare-fun xs__2 () Int)\n"
            "(assert (= xs__2 (+ x__in 2)))\n"
            "(declare-fun y__3 () Int)\n"
            "(assert (= y__3 xs__1))\n"             # const read xs[1] -> the element term
            "(assert (not (= y__3 x__in)))\n"
            "(check-sat)\n"
        )
        self.assertEqual(text, expected)

    def test_dynamic_read_ite_chain_and_range_constraint(self):
        text = translate(LIST_DYNAMIC_READ).decode()
        # the 0 <= i < L range constraint precedes the read.
        self.assertIn("(assert (and (<= 0 i__in) (< i__in 3)))", text)
        # the right-folded ite chain over the 3 positions.
        self.assertIn(
            "(ite (= i__in 0) xs__0 (ite (= i__in 1) xs__1 xs__2))", text
        )

    def test_const_index_write_updates_one_position(self):
        text = translate("def f(x):\n    xs = [0, 0, 0]\n    xs[1] = x\n    assert xs[1] == x\n").decode()
        # only position 1 gets a fresh SSA var = x__in; positions 0/2 keep xs__0/xs__2.
        self.assertIn("(declare-fun xs__3 () Int)\n(assert (= xs__3 x__in))", text)
        self.assertIn("(assert (not (= xs__3 x__in)))", text)

    def test_dynamic_write_ite_per_position(self):
        text = translate(LIST_DYNAMIC_WRITE).decode()
        self.assertIn("(assert (and (<= 0 i__in) (< i__in 3)))", text)
        # each position j becomes ite(i == j, v, old_j).
        self.assertIn("(ite (= i__in 0) v__in xs__0)", text)
        self.assertIn("(ite (= i__in 1) v__in xs__1)", text)
        self.assertIn("(ite (= i__in 2) v__in xs__2)", text)

    def test_len_lowers_to_constant(self):
        text = translate(LIST_LEN_HOLDS).decode()
        self.assertIn("(declare-fun n__3 () Int)\n(assert (= n__3 3))", text)

    def test_no_array_sort_anywhere(self):
        # The encoding stays in QF_LIA — never the SMT array theory.
        for src in (LIST_REACHABLE, LIST_SUM_HOLDS, LIST_DYNAMIC_READ,
                    LIST_DYNAMIC_WRITE, LIST_LOOP_HOLDS, LIST_LEN_HOLDS):
            text = translate(src).decode()
            self.assertIn("(set-logic QF_LIA)", text)
            self.assertNotIn("Array", text)        # no array sort
            self.assertNotIn("select", text)       # no array select
            self.assertNotIn("(store", text)       # no array store

    def test_deterministic_twice_and_diff(self):
        for src in (LIST_REACHABLE, LIST_DYNAMIC_WRITE, LIST_LOOP_HOLDS):
            self.assertEqual(translate(src), translate(src))


class TestIntListAborts(unittest.TestCase):
    """The list boundary stays hard-aborting (BENCHMARKS.md §3): an over-cap length,
    a nested list, a length-changing op, a list-as-int, an out-of-range const index,
    iterating a list."""

    def _abort(self, src):
        with self.assertRaises(Unsupported) as cm:
            translate(src)
        self.assertEqual(cm.exception.language, "python")
        return cm.exception

    def test_over_cap_length_aborts(self):
        big = "[" + ", ".join(["0"] * 17) + "]"
        self.assertEqual(self._abort(f"def f(x):\n    xs = {big}\n    assert x == x\n").construct, "list-too-long")

    def test_nested_list_aborts(self):
        self.assertEqual(self._abort("def f(x):\n    xs = [[1], [2]]\n    assert x == x\n").construct, "nested-list")

    def test_append_aborts(self):
        self.assertEqual(self._abort("def f(x):\n    xs = [x]\n    xs.append(1)\n    assert x == x\n").construct, "Expr")

    def test_for_x_in_xs_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    xs = [1, 2]\n    for v in xs:\n        pass\n    assert x == x\n").construct,
            "nonrange-loop",
        )

    def test_const_oob_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    xs = [1, 2, 3]\n    y = xs[5]\n    assert y == y\n").construct,
            "list-index-out-of-range",
        )


@unittest.skipUnless(_z3(), "z3 not installed")
class TestIntListWithZ3(unittest.TestCase):
    """End-to-end integer lists (slice 6): a violable list program yields a model
    that is a violating input (carried back through CPython's real lists to the
    firing assert); a list invariant is UNREACHABLE; the commuting square holds on a
    list corpus (incl. a list updated in a loop and a solver-steered dynamic index)."""

    def test_reachable_list_with_verified_witness(self):
        info = reach(LIST_REACHABLE)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["smt_model_ok"])   # SMT-level model check
        self.assertTrue(info["witness_ok"])     # CPython replay fires the assert
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_sum_of_elements_invariant_is_unreachable(self):
        # xs = [x, x, x]; sum == 3*x holds for every integer x (no wraparound — the
        # unbounded-Int faithfulness payoff over a tuple of Ints).
        self.assertEqual(reach(LIST_SUM_HOLDS)["verdict"], Verdict.UNREACHABLE)

    def test_dynamic_read_solver_hits_specific_element(self):
        # xs[i] != 30 is violable only at i == 2 (the position holding 30); the
        # solver must choose that index, and the carry-back must read xs[2].
        info = reach(LIST_DYNAMIC_READ)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertEqual(info["inputs"]["i"], 2)
        self.assertEqual(info["behavior"][-1]["y"], 30)
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_dynamic_write_solver_hits_specific_element(self):
        # xs[2] == 0 is violable only when the write lands on position 2 with v != 0.
        info = reach(LIST_DYNAMIC_WRITE)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertEqual(info["inputs"]["i"], 2)
        self.assertNotEqual(info["inputs"]["v"], 0)
        self.assertEqual(info["behavior"][-1]["xs"][2], info["inputs"]["v"])
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_list_updated_in_loop_invariant_unreachable(self):
        self.assertEqual(reach(LIST_LOOP_HOLDS)["verdict"], Verdict.UNREACHABLE)

    def test_list_updated_in_loop_reachable_carry_back(self):
        info = reach(LIST_LOOP_REACHABLE)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertEqual(info["behavior"][-1]["xs"], [0, 1, 2])  # the loop wrote each
        self.assertTrue(info["behavior"][-1]["__violated__"])

    def test_len_invariant_unreachable(self):
        self.assertEqual(reach(LIST_LEN_HOLDS)["verdict"], Verdict.UNREACHABLE)

    def test_commuting_square_on_list_corpus(self):
        # I_s(p) vs L(I_t(T(p))) under π on list programs mixing the shapes (literal,
        # const + dynamic read/write, len, a list updated in a loop) and verdicts.
        reachable = [
            LIST_REACHABLE,
            LIST_DYNAMIC_READ,
            LIST_DYNAMIC_WRITE,
            LIST_LOOP_REACHABLE,
        ]
        for src in reachable:
            verdict, result = cross_check(src)
            self.assertEqual(verdict, Verdict.REACHABLE, src)
            self.assertTrue(result.ok, f"{src}: {result.divergence}")
        # the UNREACHABLE invariants align trivially (no model).
        for src in (LIST_SUM_HOLDS, LIST_LOOP_HOLDS, LIST_LEN_HOLDS):
            verdict, result = cross_check(src)
            self.assertEqual(verdict, Verdict.UNREACHABLE, src)
            self.assertTrue(result.ok)


@unittest.skipUnless(_z3(), "z3 not installed")
class TestIntListDeterminismAcrossHashseed(unittest.TestCase):
    def test_list_lowering_byte_identical_across_hashseed(self):
        # The list cleanup iterates self.lists after a loop and the dynamic write
        # builds a per-position ite list; assert the whole list lowering is
        # byte-stable across hash randomization.
        src = (
            "def f(i, v):\n    xs = [0, 0, 0]\n    for k in range(3):\n        xs[k] = k\n"
            "    xs[i] = v\n    assert xs[i] == v\n"
        )
        code = (
            "from gurdy.pairs.python_smtlib import translate;"
            f"import sys; sys.stdout.buffer.write(translate({src!r}))"
        )
        outs = []
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outs.append(subprocess.check_output([sys.executable, "-c", code], env=env))
        self.assertEqual(len(set(outs)), 1, "list-lowering output not byte-stable across PYTHONHASHSEED")


if __name__ == "__main__":
    unittest.main()
