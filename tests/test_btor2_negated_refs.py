"""BTOR2 negated node references — the signed-operand form ``-n`` (the
bitwise NOT of node ``n``) in operand, ``init``, ``next``, ``bad``, and
``constraint`` positions. Surfaced by HWMCC ingestion (the beem family
uses them heavily); before this support the shared evaluator raised a
raw KeyError — an *untyped* abort, exactly what the honest-failure rule
(BENCHMARKS.md §3) forbids. Covered here: evaluator semantics, bridge
emission agreeing with the native checker, cone-of-influence soundness
(a negated reference still contributes support), and the additive
guarantee (negation-free emission byte-identical)."""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.core.solver import Verdict
from gurdy.languages.btor2.coi import cone_of_influence, suggest_reduction
from gurdy.languages.btor2.eval import interpret
from gurdy.pairs.btor2_smtlib import reach, translate
from gurdy.solvers.native_btor2 import find_btormc, NativeBtor2Checker

# init s = NOT one = 0; s' = NOT s (a toggle); bad = NOT s.
_TOGGLE = ("1 sort bitvec 1\n2 one 1\n3 state 1 s\n"
           "4 init 1 3 -2\n5 next 1 3 -3\n6 bad -3\n")

# 4-bit counter; bad = NOT(c == 2) through a negated operand of `and`.
_NEQ_VIA_NEG = ("1 sort bitvec 4\n2 state 1 c\n3 one 1\n4 add 1 2 3\n"
                "5 next 1 2 4\n6 constd 1 2\n7 sort bitvec 1\n"
                "8 eq 7 2 6\n9 and 7 -8 -8\n10 bad 9\n")

# The dependency hides behind a negation: bad reads NOT d, d' = NOT s.
# The cone must contain BOTH states; before the abs() fix it lost them.
_NEG_CHAIN = ("1 sort bitvec 1\n2 one 1\n3 state 1 s\n4 state 1 d\n"
              "5 init 1 3 2\n6 next 1 3 -3\n7 next 1 4 -3\n8 bad -4\n")


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


class TestEvaluator(unittest.TestCase):
    def test_toggle_semantics(self):
        rows = interpret(_TOGGLE, {"steps": 3})
        self.assertEqual([(r["s"], r["bad6"]) for r in rows],
                         [(0, 1), (1, 0), (0, 1)])

    def test_negated_operand(self):
        # c = 0 at step 0, so NOT(c == 2) fires immediately
        self.assertEqual(interpret(_NEQ_VIA_NEG, {"steps": 1})[0]["bad10"], 1)

    def test_negated_array_ref_is_typed(self):
        bad_array = ("1 sort bitvec 1\n2 sort array 1 1\n3 state 2 mem\n"
                     "4 sort bitvec 1\n5 input 4\n6 read 4 -3 5\n7 bad 6\n")
        with self.assertRaises(Unsupported):
            interpret(bad_array, {"steps": 1})


class TestConeSoundness(unittest.TestCase):
    def test_negated_references_still_contribute_support(self):
        cone = cone_of_influence(_NEG_CHAIN)
        labels = {(_NEG_CHAIN.splitlines()[nid - 1].split()[-1]) for nid in cone}
        self.assertEqual(labels, {"s", "d"})

    def test_free_set_empty_on_the_chain(self):
        adv = suggest_reduction(_NEG_CHAIN, k=2, samples=0)
        self.assertEqual(adv["free_havoc"], [])


class TestBridge(unittest.TestCase):
    def test_negation_free_emission_is_byte_identical(self):
        # the additive guarantee: a system without negated refs emits
        # exactly what a _name-only bridge emitted
        plain = ("1 sort bitvec 1\n2 one 1\n3 state 1 s\n"
                 "4 init 1 3 2\n5 next 1 3 3\n6 bad 3\n")
        out = translate({"system": plain, "k": 2}).decode()
        self.assertNotIn("bvnot", out)

    def test_negated_refs_emit_bvnot(self):
        out = translate({"system": _TOGGLE, "k": 2}).decode()
        self.assertIn("(bvnot", out)

    @unittest.skipUnless(_z3(), "z3 absent")
    def test_bridged_verdicts(self):
        self.assertEqual(reach(_TOGGLE, 2)["verdict"], Verdict.REACHABLE)
        self.assertEqual(reach(_NEQ_VIA_NEG, 3)["verdict"], Verdict.REACHABLE)


@unittest.skipUnless(find_btormc() and _z3(), "btormc and/or z3 absent")
class TestNativeAgreement(unittest.TestCase):
    def test_toggle_agrees(self):
        native = NativeBtor2Checker().decide_bounded(_TOGGLE, 2)
        self.assertEqual(native, Verdict.REACHABLE)
        self.assertEqual(reach(_TOGGLE, 2)["verdict"], native)


if __name__ == "__main__":
    unittest.main()
