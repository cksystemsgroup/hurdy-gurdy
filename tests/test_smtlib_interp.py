"""Shared SMT-LIB interpreter tests (languages/smtlib): byte-exact text I/O
(the s-expression reader/printer) and the deterministic model evaluator over
the QF_ABV fragment the btor2-smtlib bridge emits.

The evaluator is the witness check (SOLVERS.md §4-5): given a model it computes
whether every assertion holds — fully deterministic, and *not* the solver.
"""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.core.registry import get_language
from gurdy.languages.smtlib import sexpr
from gurdy.languages.smtlib.eval import evaluate
from gurdy.languages.smtlib.interp import interpret
from gurdy.languages.smtlib.model import read_model
from gurdy.languages.smtlib.script import read_script
from gurdy.languages.riscv.interp import image_from_words
from gurdy.pairs.btor2_smtlib import translate
from gurdy.pairs.riscv_btor2 import translate as rv_translate

COUNTER = """\
1 sort bitvec 3
2 zero 1
3 state 1 count
4 one 1
5 add 1 3 4
6 init 1 3 2
7 next 1 3 5
8 sort bitvec 1
9 constd 1 5
10 eq 8 3 9
11 bad 10
"""


def _addi(d, a, im):
    return (((im & 0xFFF) << 20) | (a << 15) | (d << 7) | 0x13) & 0xFFFFFFFF


class TestSexprRoundTrip(unittest.TestCase):
    def test_parse_dumps_atoms_and_lists(self):
        self.assertEqual(sexpr.parse("(a (b c) ())"), [["a", ["b", "c"], []]])
        self.assertEqual(sexpr.dumps(["a", ["b", "c"], []]), "(a (b c) ())")

    def test_comments_normalized(self):
        self.assertEqual(sexpr.parse("(a b) ; trailing\n(c)"), [["a", "b"], ["c"]])

    def test_emitted_counter_round_trips_byte_exact(self):
        art = translate({"system": COUNTER, "k": 6})
        self.assertEqual(read_script(art).to_text().encode("utf-8"), art)

    def test_emitted_riscv_btor2_round_trips_byte_exact(self):
        program = {"image": image_from_words([_addi(1, 0, 7), 0x73]),
                   "init_regs": {}, "property": {"reg_eq": [1, 7]}}
        art = translate({"system": rv_translate(program), "k": 3})
        self.assertEqual(read_script(art).to_text().encode("utf-8"), art)


class TestModelEvaluator(unittest.TestCase):
    def _script(self, *terms):
        decls = "(declare-fun a () (_ BitVec 8))\n(declare-fun b () (_ BitVec 8))\n"
        body = "".join(f"(assert {t})\n" for t in terms)
        return (decls + body + "(check-sat)\n").encode("utf-8")

    def test_equality(self):
        s = self._script("(= a (_ bv5 8))")
        self.assertTrue(evaluate(s, {"a": 5}))
        self.assertFalse(evaluate(s, {"a": 6}))

    def test_omitted_symbol_defaults_to_zero(self):
        # a don't-care symbol the solver left out of the model defaults to 0.
        self.assertTrue(evaluate(self._script("(= a (_ bv0 8))"), {}))

    def test_arithmetic_and_unsigned_compare(self):
        s = self._script("(bvult (bvadd a b) (_ bv200 8))")
        self.assertTrue(evaluate(s, {"a": 10, "b": 20}))
        self.assertFalse(evaluate(s, {"a": 150, "b": 100}))  # wraps below 200? 250<200 false

    def test_signed_compare_and_div_rem(self):
        self.assertTrue(evaluate(self._script("(bvslt a (_ bv0 8))"), {"a": 0xFF}))  # -1 < 0
        self.assertFalse(evaluate(self._script("(bvslt a (_ bv0 8))"), {"a": 1}))
        # signed division rounds toward zero: (-6) / 4 == -1
        self.assertTrue(evaluate(self._script("(= (bvsdiv a (_ bv4 8)) (_ bv255 8))"),
                                 {"a": (-6) & 0xFF}))

    def test_extract_extend_concat(self):
        self.assertTrue(evaluate(self._script("(= ((_ extract 3 0) a) (_ bv5 4))"),
                                 {"a": 0xF5}))
        self.assertTrue(evaluate(self._script("(= ((_ zero_extend 8) a) (_ bv1 16))"),
                                 {"a": 1}))
        self.assertTrue(evaluate(self._script("(= ((_ sign_extend 8) a) (_ bv65535 16))"),
                                 {"a": 0xFF}))
        self.assertTrue(evaluate(self._script("(= (concat a b) (_ bv258 16))"),
                                 {"a": 1, "b": 2}))

    def test_boolean_connectives_and_ite(self):
        s = self._script("(or (= a (_ bv1 8)) (= b (_ bv2 8)))",
                         "(=> (= a (_ bv1 8)) (distinct a b))",
                         "(not (= a b))")
        self.assertTrue(evaluate(s, {"a": 1, "b": 99}))
        ite = self._script("(= (ite (bvult a b) a b) (_ bv3 8))")  # min(a,b) == 3
        self.assertTrue(evaluate(ite, {"a": 3, "b": 9}))   # min 3
        self.assertFalse(evaluate(ite, {"a": 9, "b": 4}))  # min 4, not 3

    def test_arrays(self):
        s = ("(declare-fun mem () (Array (_ BitVec 8) (_ BitVec 8)))\n"
             "(declare-fun i () (_ BitVec 8))\n"
             "(assert (= (select (store mem i (_ bv9 8)) i) (_ bv9 8)))\n"
             "(check-sat)\n").encode("utf-8")
        self.assertTrue(evaluate(s, {"mem": {"default": 0}, "i": 4}))
        sel = ("(declare-fun mem () (Array (_ BitVec 8) (_ BitVec 8)))\n"
               "(assert (= (select mem (_ bv3 8)) (_ bv7 8)))\n"
               "(check-sat)\n").encode("utf-8")
        self.assertTrue(evaluate(sel, {"mem": {3: 7, "default": 0}}))
        self.assertFalse(evaluate(sel, {"mem": {3: 8, "default": 0}}))

    def test_unsupported_operator_aborts_typed(self):
        s = b"(declare-fun a () (_ BitVec 8))\n(assert (= (bvfoo a a) a))\n(check-sat)\n"
        with self.assertRaises(Unsupported):
            evaluate(s, {"a": 0})


class TestModelReaderAndInterp(unittest.TestCase):
    def test_read_model_define_fun_and_get_value(self):
        self.assertEqual(read_model("(model (define-fun x () (_ BitVec 8) #x05))"),
                         {"x": 5})
        self.assertEqual(read_model("((y #b00000011))"), {"y": 3})

    def test_read_model_then_evaluate(self):
        s = b"(declare-fun x () (_ BitVec 8))\n(assert (= x (_ bv5 8)))\n(check-sat)\n"
        self.assertTrue(evaluate(s, read_model("(model (define-fun x () (_ BitVec 8) #x05))")))

    def test_interp_returns_sat_observable(self):
        s = b"(declare-fun x () (_ BitVec 8))\n(assert (= x (_ bv5 8)))\n(check-sat)\n"
        self.assertEqual(interpret(s, {"model": {"x": 5}}), [{"sat": True}])
        self.assertEqual(interpret(s, {"model": {"x": 6}}), [{"sat": False}])

    def test_language_owns_shared_target_interpreter(self):
        self.assertIsNotNone(get_language("smtlib").target_interpreter)


if __name__ == "__main__":
    unittest.main()
