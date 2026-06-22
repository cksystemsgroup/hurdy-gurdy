"""Python-subset language tests: the loader's subset enforcement (typed
``unsupported: python:<construct>`` aborts), the pinned-CPython executor's
post-step trace, and its determinism (twice-and-diff across ``PYTHONHASHSEED``).

The interpreter is the shared source ``I_s`` — pinned real CPython restricted to
the subset (languages/python brief; PAIRING.md §6/§9). The slice is a
straight-line integer function (assignment + linear arithmetic + a trailing
assert); everything else hard-aborts.
"""

import ast
import os
import subprocess
import sys
import unittest

from gurdy.core.errors import Unsupported
from gurdy.languages.python import PYTHON_PIN, interpret, load
from gurdy.languages.python.subset import Program

OK = "def f(x):\n    y = 2 * x + 1\n    z = y - x\n    assert z == x + 1\n"


class TestLoaderAccepts(unittest.TestCase):
    def test_loads_straightline_program(self):
        prog = load(OK)
        self.assertIsInstance(prog, Program)
        self.assertEqual(prog.name, "f")
        self.assertEqual(prog.params, ("x",))
        self.assertEqual(prog.source, OK)  # byte-exact source preserved

    def test_multi_param_declaration_order(self):
        prog = load("def g(a, b, c):\n    s = a + b - c\n    assert s == s\n")
        self.assertEqual(prog.params, ("a", "b", "c"))

    def test_int_annotations_allowed(self):
        prog = load("def f(x: int, y: int):\n    z = x - y\n    assert z == z\n")
        self.assertEqual(prog.params, ("x", "y"))

    def test_const_times_var_and_var_times_const_both_linear(self):
        load("def f(x):\n    y = 3 * x\n    z = x * 4\n    assert y == y\n")  # no raise

    def test_pass_statement_is_a_noop(self):
        prog = load("def f(x):\n    pass\n    y = x\n    assert y == x\n")
        self.assertEqual(prog.params, ("x",))


class TestLoaderAborts(unittest.TestCase):
    def _abort(self, src):
        with self.assertRaises(Unsupported) as cm:
            load(src)
        self.assertEqual(cm.exception.language, "python")
        return cm.exception

    # NOTE: ``if`` / ``else`` is now IN SCOPE (slice 2) — its acceptance and the
    # branch-boundary rejections live in TestLoaderIfElse below.

    def test_while(self):
        self.assertEqual(self._abort("def f(x):\n    while x > 0:\n        x = x - 1\n    assert x == 0\n").construct, "While")

    def test_for_nonconstant_range(self):
        # NOTE: a *bounded* `for i in range(<const>)` is now IN SCOPE (slice 3) —
        # its acceptance and the loop-boundary rejections live in TestLoaderForLoop
        # below. A non-constant range bound has no static trip count -> aborts.
        self.assertEqual(self._abort("def f(x):\n    for i in range(x):\n        pass\n    assert x == x\n").construct, "nonconst-range")

    def test_floordiv(self):
        self.assertEqual(self._abort("def f(x):\n    y = x // 2\n    assert y == y\n").construct, "FloorDiv")

    def test_modulo(self):
        self.assertEqual(self._abort("def f(x):\n    y = x % 3\n    assert y == y\n").construct, "Mod")

    def test_truediv(self):
        self.assertEqual(self._abort("def f(x):\n    y = x / 2\n    assert y == y\n").construct, "Div")

    def test_power(self):
        self.assertEqual(self._abort("def f(x):\n    y = x ** 2\n    assert y == y\n").construct, "Pow")

    def test_nonlinear_mul(self):
        self.assertEqual(self._abort("def f(x):\n    y = x * x\n    assert y == y\n").construct, "nonlinear-mul")

    def test_boolop(self):
        self.assertEqual(self._abort("def f(x):\n    assert x > 0 and x < 10\n").construct, "BoolOp")

    def test_call(self):
        self.assertEqual(self._abort("def f(x):\n    y = abs(x)\n    assert y == y\n").construct, "Call")

    def test_list_literal(self):
        self.assertEqual(self._abort("def f(x):\n    y = [x]\n    assert x == x\n").construct, "List")

    def test_return_value(self):
        self.assertEqual(self._abort("def f(x):\n    return x\n    assert x == x\n").construct, "Return")

    def test_import(self):
        self.assertEqual(self._abort("import os\ndef f(x):\n    assert x == x\n").construct, "Import")

    def test_no_assert(self):
        self.assertEqual(self._abort("def f(x):\n    y = x + 1\n").construct, "no-assert")

    def test_post_assert_statement(self):
        self.assertEqual(self._abort("def f(x):\n    assert x == x\n    y = x\n").construct, "post-assert-statement")

    def test_chained_compare(self):
        self.assertEqual(self._abort("def f(x):\n    assert 0 < x < 10\n").construct, "chained-compare")

    def test_multiple_targets(self):
        self.assertEqual(self._abort("def f(x):\n    a = b = x\n    assert a == a\n").construct, "multiple-targets")

    def test_tuple_target(self):
        self.assertEqual(self._abort("def f(x):\n    a, b = x, x\n    assert a == a\n").construct, "Tuple")

    def test_augmented_assign(self):
        # AugAssign is not Assign/Assert/Pass -> the straight-line statement abort.
        e = self._abort("def f(x):\n    x += 1\n    assert x == x\n")
        self.assertEqual(e.construct, "AugAssign")

    def test_undefined_name(self):
        self.assertEqual(self._abort("def f(x):\n    y = z + 1\n    assert y == y\n").construct, "undefined-name")

    def test_float_constant(self):
        self.assertEqual(self._abort("def f(x):\n    y = x + 1.5\n    assert y == y\n").construct, "Constant")

    def test_two_functions(self):
        self.assertEqual(self._abort("def f(x):\n    assert x == x\ndef g(y):\n    assert y == y\n").construct, "module-shape")

    def test_varargs(self):
        self.assertEqual(self._abort("def f(*args):\n    assert 1 == 1\n").construct, "param-shape")

    def test_top_level_code(self):
        # a bare top-level statement (not the single def) aborts at module shape.
        self._abort("x = 1\ndef f(y):\n    assert y == y\n")


class TestLoaderIfElse(unittest.TestCase):
    """if/else is in scope (slice 2): the loader accepts a branch whose guard is a
    single integer comparison and whose arms are in-scope statements, and rejects
    the branch boundary (one-arm definitions read at the join, asserts/loops in an
    arm, a non-comparison guard)."""

    def _abort(self, src):
        with self.assertRaises(Unsupported) as cm:
            load(src)
        self.assertEqual(cm.exception.language, "python")
        return cm.exception

    def test_accepts_if_else(self):
        prog = load("def f(x):\n    if x > 0:\n        y = 1\n    else:\n        y = -1\n    assert y == y\n")
        self.assertEqual(prog.params, ("x",))

    def test_accepts_bare_if(self):
        # bare if with a pre-initialized variable (the empty-else case).
        load("def f(x):\n    y = 0\n    if x > 0:\n        y = x\n    assert y >= 0\n")

    def test_accepts_nested_if(self):
        load(
            "def f(x):\n    if x > 0:\n        if x > 10:\n            y = 2\n"
            "        else:\n            y = 1\n    else:\n        y = 0\n    assert y == y\n"
        )

    def test_both_arm_variable_readable_after_join(self):
        # y is assigned on both arms -> readable after the if.
        load("def f(x):\n    if x > 0:\n        y = 1\n    else:\n        y = 2\n    z = y + 1\n    assert z == y + 1\n")

    def test_one_arm_variable_not_readable(self):
        # y assigned only on the then-arm: may be undefined on the else path.
        self.assertEqual(
            self._abort("def f(x):\n    if x > 0:\n        y = 1\n    assert y == 1\n").construct,
            "undefined-name",
        )

    def test_else_only_variable_not_readable(self):
        self.assertEqual(
            self._abort(
                "def f(x):\n    if x > 0:\n        z = 1\n    else:\n        y = 2\n    assert y == 2\n"
            ).construct,
            "undefined-name",
        )

    def test_non_comparison_guard_aborts(self):
        self.assertEqual(
            self._abort(
                "def f(x):\n    if x > 0 and x < 5:\n        y = 1\n    else:\n        y = 0\n    assert y == y\n"
            ).construct,
            "BoolOp",
        )

    def test_assert_in_arm_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    if x > 0:\n        assert x > 0\n    assert x == x\n").construct,
            "branch-assert",
        )

    def test_while_in_arm_aborts(self):
        self.assertEqual(
            self._abort(
                "def f(x):\n    if x > 0:\n        while x > 0:\n            x = x - 1\n    assert x == x\n"
            ).construct,
            "While",
        )

    def test_nonconst_for_in_arm_aborts(self):
        # A *bounded* for in an arm is now in scope (TestLoaderForLoop), but a
        # non-constant range bound in an arm still has no static trip count.
        self.assertEqual(
            self._abort(
                "def f(x):\n    if x > 0:\n        for i in range(x):\n            pass\n    assert x == x\n"
            ).construct,
            "nonconst-range",
        )

    def test_bounded_for_in_arm_accepted(self):
        # A bounded for inside an if arm is in scope (slice 3): s initialised
        # before the if, accumulated in the arm's loop, read after the join.
        load(
            "def f(x):\n    s = x\n    if x > 0:\n        for i in range(2):\n"
            "            s = s + i\n    assert s >= x\n"
        )

    def test_nonlinear_in_arm_aborts(self):
        self.assertEqual(
            self._abort(
                "def f(x):\n    if x > 0:\n        y = x * x\n    else:\n        y = 0\n    assert y == y\n"
            ).construct,
            "nonlinear-mul",
        )


class TestLoaderForLoop(unittest.TestCase):
    """A bounded loop ``for i in range(<const>)`` is in scope (slice 3): the loader
    accepts a constant-trip-count range over an in-scope body, and rejects the
    loop boundary (a nested loop, a non-constant / start-step / negative range,
    ``break`` / ``continue``, an assert in the body, a body-only or loop-variable
    read after the loop)."""

    def _abort(self, src):
        with self.assertRaises(Unsupported) as cm:
            load(src)
        self.assertEqual(cm.exception.language, "python")
        return cm.exception

    def test_accepts_bounded_loop(self):
        prog = load("def f(x):\n    s = x\n    for i in range(3):\n        s = s + i\n    assert s == x + 3\n")
        self.assertEqual(prog.params, ("x",))

    def test_accepts_zero_trip_count(self):
        load("def f(x):\n    s = x\n    for i in range(0):\n        s = s + i\n    assert s == x\n")

    def test_accepts_loop_variable_read_in_body(self):
        load("def f(x):\n    s = x\n    for i in range(4):\n        s = s + 2 * i\n    assert s == s\n")

    def test_accepts_if_inside_loop_body(self):
        load(
            "def f(x):\n    c = 0\n    for i in range(4):\n        if i > 0:\n"
            "            c = c + 1\n    assert c == 3\n"
        )

    def test_nested_loop_aborts(self):
        self.assertEqual(
            self._abort(
                "def f(x):\n    for i in range(2):\n        for j in range(2):\n"
                "            x = x + 1\n    assert x == x\n"
            ).construct,
            "For",
        )

    def test_nonconstant_range_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    for i in range(x):\n        pass\n    assert x == x\n").construct,
            "nonconst-range",
        )

    def test_start_step_range_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    for i in range(1, 5):\n        x = x + 1\n    assert x == x\n").construct,
            "range-shape",
        )

    def test_negative_range_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    for i in range(-1):\n        x = x + 1\n    assert x == x\n").construct,
            "negative-range",
        )

    def test_non_range_iterable_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    for i in [1, 2, 3]:\n        x = x + 1\n    assert x == x\n").construct,
            "nonrange-loop",
        )

    def test_break_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    for i in range(3):\n        break\n    assert x == x\n").construct,
            "Break",
        )

    def test_continue_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    for i in range(3):\n        continue\n    assert x == x\n").construct,
            "Continue",
        )

    def test_assert_in_loop_body_aborts(self):
        self.assertEqual(
            self._abort("def f(x):\n    for i in range(3):\n        assert x == x\n    assert x == x\n").construct,
            "branch-assert",
        )

    def test_loop_variable_not_readable_after_loop(self):
        self.assertEqual(
            self._abort("def f(x):\n    for i in range(3):\n        x = x + i\n    assert i == 2\n").construct,
            "undefined-name",
        )

    def test_body_only_variable_not_readable_after_loop(self):
        self.assertEqual(
            self._abort("def f(x):\n    for i in range(3):\n        y = i\n    assert y == 2\n").construct,
            "undefined-name",
        )


class TestExecutorForLoop(unittest.TestCase):
    """The pinned-CPython executor unrolls a bounded loop: the body runs once per
    i = 0..n-1, recording one row per body statement; the loop variable is live in
    those rows but dropped after the loop."""

    def test_unrolls_accumulator(self):
        # s = x + (0 + 1 + 2) = x + 3. Three body rows + the assert.
        tr = interpret("def f(x):\n    s = x\n    for i in range(3):\n        s = s + i\n    assert s == x + 3\n", {"x": 10})
        self.assertEqual(len(tr), 5)               # s=x, +0, +1, +2, assert
        self.assertEqual(tr[0]["s"], 10)           # s = x
        self.assertEqual(tr[1]["s"], 10)           # + 0
        self.assertEqual(tr[2]["s"], 11)           # + 1
        self.assertEqual(tr[3]["s"], 13)           # + 2
        self.assertEqual(tr[3]["i"], 2)            # loop variable live in the body row
        self.assertEqual(tr[-1]["s"], 13)
        self.assertTrue(tr[-1]["__cond__"])

    def test_loop_variable_absent_after_loop(self):
        # i is dropped after the loop -> the trailing assert row carries no i.
        tr = interpret("def f(x):\n    s = x\n    for i in range(2):\n        s = s + i\n    assert s == x + 1\n", {"x": 0})
        self.assertNotIn("i", tr[-1])
        self.assertIn("s", tr[-1])

    def test_zero_iterations_runs_no_body(self):
        # range(0): no body row; s keeps its pre-loop value.
        tr = interpret("def f(x):\n    s = x\n    for i in range(0):\n        s = s + i\n    assert s == x\n", {"x": 7})
        self.assertEqual(len(tr), 2)               # s = x, then the assert
        self.assertEqual(tr[-1]["s"], 7)
        self.assertTrue(tr[-1]["__cond__"])

    def test_if_inside_loop(self):
        # c counts the positive indices in range(4): i = 1,2,3 -> c = 3.
        tr = interpret(
            "def f(x):\n    c = 0\n    for i in range(4):\n        if i > 0:\n"
            "            c = c + 1\n    assert c == 3\n",
            {"x": 0},
        )
        self.assertEqual(tr[-1]["c"], 3)
        self.assertTrue(tr[-1]["__cond__"])

    def test_violated_loop_assert_recorded(self):
        # off-by-one invariant: s = x + 3 but assert s == x + 4 -> fires.
        tr = interpret("def f(x):\n    s = x\n    for i in range(3):\n        s = s + i\n    assert s == x + 4\n", {"x": 0})
        self.assertTrue(tr[-1]["__violated__"])

    def test_loop_determinism_twice_and_diff(self):
        src = "def f(x):\n    s = x\n    for i in range(5):\n        s = s + i\n    assert s == x + 10\n"
        self.assertEqual(interpret(src, {"x": 3}), interpret(src, {"x": 3}))


class TestExecutor(unittest.TestCase):
    def test_post_step_trace(self):
        tr = interpret(OK, {"x": 5})
        self.assertEqual(len(tr), 3)  # two assigns + the assert
        self.assertEqual(tr[0], {"x": 5, "y": 11, "__stmt__": "assign", "__assigned__": "y"})
        self.assertEqual(tr[1]["z"], 6)
        self.assertEqual(tr[-1]["__stmt__"], "assert")
        self.assertTrue(tr[-1]["__cond__"])
        self.assertFalse(tr[-1]["__violated__"])

    def test_violated_assert_recorded_not_raised(self):
        # y = x + 1; assert y < x  — never holds; the executor records, not raises.
        tr = interpret("def g(x):\n    y = x + 1\n    assert y < x\n", {"x": 3})
        self.assertFalse(tr[-1]["__cond__"])
        self.assertTrue(tr[-1]["__violated__"])

    def test_unbound_param_defaults_to_zero(self):
        tr = interpret("def f(a, b):\n    s = a + b\n    assert s == a + b\n", {"a": 5})
        self.assertEqual(tr[0]["b"], 0)
        self.assertEqual(tr[0]["s"], 5)

    def test_arbitrary_precision_int(self):
        # Python's unbounded int: 2 * a stays exact past 64 bits.
        big = 10 ** 40
        tr = interpret("def f(a):\n    y = 2 * a\n    assert y == a + a\n", {"a": big})
        self.assertEqual(tr[0]["y"], 2 * big)
        self.assertTrue(tr[-1]["__cond__"])

    def test_negative_arithmetic(self):
        tr = interpret("def f(x):\n    y = -x - 1\n    assert y == y\n", {"x": -4})
        self.assertEqual(tr[0]["y"], 3)

    def test_no_builtins_in_namespace(self):
        # The restricted namespace empties __builtins__; a program that slipped a
        # call past the loader (it can't, but as a runtime backstop) would fail.
        # Here we just confirm a clean program runs with no builtin leakage.
        tr = interpret(OK, {"x": 0})
        self.assertEqual(tr[0]["y"], 1)

    def test_pin_is_host_cpython(self):
        self.assertTrue(PYTHON_PIN.startswith("CPython "))
        self.assertIn(".".join(map(str, sys.version_info[:2])), PYTHON_PIN)

    def test_if_takes_then_branch(self):
        # x > 0 -> then arm (y = 1); only the taken arm's row is recorded.
        src = "def f(x):\n    if x > 0:\n        y = 1\n    else:\n        y = -1\n    assert y == 1\n"
        tr = interpret(src, {"x": 5})
        self.assertEqual(tr[0]["y"], 1)            # then arm ran
        self.assertEqual(tr[0]["__assigned__"], "y")
        self.assertTrue(tr[-1]["__cond__"])        # assert y == 1 holds
        self.assertFalse(tr[-1]["__violated__"])

    def test_if_takes_else_branch(self):
        src = "def f(x):\n    if x > 0:\n        y = 1\n    else:\n        y = -1\n    assert y == 1\n"
        tr = interpret(src, {"x": -3})
        self.assertEqual(tr[0]["y"], -1)           # else arm ran
        self.assertTrue(tr[-1]["__violated__"])    # assert y == 1 fires

    def test_bare_if_skipped_keeps_incoming(self):
        # x <= 0 skips the (empty-else) if; y keeps its pre-if value.
        src = "def f(x):\n    y = 0\n    if x > 0:\n        y = x\n    assert y >= 0\n"
        tr = interpret(src, {"x": -7})
        self.assertEqual(tr[-1]["y"], 0)           # y unchanged by the skipped arm
        self.assertTrue(tr[-1]["__cond__"])

    def test_nested_if_branch(self):
        src = (
            "def f(x):\n    if x > 0:\n        if x > 10:\n            y = 2\n"
            "        else:\n            y = 1\n    else:\n        y = 0\n    assert y == 1\n"
        )
        self.assertEqual(interpret(src, {"x": 5})[-1]["y"], 1)    # 0<x<=10 -> inner else
        self.assertEqual(interpret(src, {"x": 50})[-1]["y"], 2)   # x>10 -> inner then
        self.assertEqual(interpret(src, {"x": -1})[-1]["y"], 0)   # x<=0 -> outer else


class TestDeterminism(unittest.TestCase):
    def test_twice_and_diff_same_process(self):
        self.assertEqual(interpret(OK, {"x": 9}), interpret(OK, {"x": 9}))

    def test_byte_identical_across_hashseed(self):
        # The loader + executor must be byte-reproducible regardless of hash
        # randomization (ARCHITECTURE.md §4).
        prog = "def f(x, y):\n    a = 2 * x + y - 1\n    b = a - x\n    assert b == x + y - 1\n"
        code = (
            "from gurdy.languages.python import interpret;"
            f"tr = interpret({prog!r}, {{'x': 7, 'y': 3}});"
            "print(repr(tr))"
        )
        outs = []
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            out = subprocess.check_output([sys.executable, "-c", code], env=env)
            outs.append(out)
        self.assertEqual(len(set(outs)), 1, "interpreter trace not byte-stable across PYTHONHASHSEED")

    def test_loop_trace_byte_identical_across_hashseed(self):
        # The unrolled-loop trace (with the loop variable cleaned up after the
        # loop) must be byte-reproducible across hash randomization too.
        prog = "def f(x):\n    s = x\n    for i in range(4):\n        s = s + i\n    assert s == x + 6\n"
        code = (
            "from gurdy.languages.python import interpret;"
            f"tr = interpret({prog!r}, {{'x': 5}});"
            "print(repr(tr))"
        )
        outs = []
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outs.append(subprocess.check_output([sys.executable, "-c", code], env=env))
        self.assertEqual(len(set(outs)), 1, "loop trace not byte-stable across PYTHONHASHSEED")


if __name__ == "__main__":
    unittest.main()
