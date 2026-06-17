"""btor2-smtlib bridge tests (z3-backed): unroll a BTOR2 system to SMT-LIB,
decide reachability with z3, and replay the witness through the BTOR2
interpreter to confirm a bad is actually reached.

Includes the end-to-end capstone: a RISC-V program -> BTOR2 (riscv-btor2) ->
SMT-LIB (btor2-smtlib) -> z3 -> witness replay.
"""

import unittest

from gurdy.core.registry import list_pairs
from gurdy.core.solver import Verdict
from gurdy.languages.riscv.interp import image_from_words
from gurdy.pairs.btor2_smtlib import reach, translate
from gurdy.pairs.riscv_btor2 import translate as rv_translate


def _z3() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except ImportError:
        return False


# 3-bit counter; bad when count == 5 (reachable at step 5).
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

# Same counter but the bad is count == 6 (not reachable within small k unless
# the loop runs far enough); used for an unreachable case at low k.
NOBAD = """\
1 sort bitvec 3
2 zero 1
3 state 1 count
4 one 1
5 add 1 3 4
6 init 1 3 2
7 next 1 3 5
"""


def ADDI(d, a, im):
    return (((im & 0xFFF) << 20) | (a << 15) | (0 << 12) | (d << 7) | 0x13) & 0xFFFFFFFF


def ADD(d, a, c):
    return ((c << 20) | (a << 15) | (0 << 12) | (d << 7) | 0x33) & 0xFFFFFFFF


def ECALL():
    return 0x73


class TestBtor2Smtlib(unittest.TestCase):
    def test_registered(self):
        self.assertIn("btor2-smtlib", list_pairs())

    def test_translate_deterministic(self):
        self.assertEqual(translate({"system": COUNTER, "k": 6}),
                         translate({"system": COUNTER, "k": 6}))

    def test_translate_emits_smtlib(self):
        text = translate({"system": COUNTER, "k": 6}).decode()
        self.assertIn("(set-logic QF_ABV)", text)
        self.assertIn("(check-sat)", text)

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_counter_reachable_with_verified_witness(self):
        info = reach(COUNTER, 6)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        # the independent SMT-level witness check (shared smtlib evaluator)
        # agrees the model satisfies the emitted script.
        self.assertTrue(info["smt_model_ok"])
        counts = [row["count"] for row in info["behavior"]]
        self.assertIn(5, counts)

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_counter_unreachable_at_low_bound(self):
        # count reaches 5 only at step 5; within k=4 it never does.
        self.assertEqual(reach(COUNTER, 4)["verdict"], Verdict.UNREACHABLE)

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_no_bad_is_unreachable(self):
        self.assertEqual(reach(NOBAD, 6)["verdict"], Verdict.UNREACHABLE)

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_capstone_riscv_to_btor2_to_smtlib(self):
        # x1=20, x2=22, x3 = x1 + x2 == 42; property: x3 == 42 reachable.
        program = {
            "image": image_from_words([ADD(3, 1, 2), ECALL()]),
            "init_regs": {1: 20, 2: 22},
            "property": {"reg_eq": [3, 42]},
        }
        artifact = rv_translate(program)  # RISC-V -> BTOR2 (with a bad)
        info = reach(artifact, 3)          # BTOR2 -> SMT-LIB -> z3
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])
        self.assertTrue(info["smt_model_ok"])
        # the replayed witness reaches x3 == 42
        self.assertTrue(any(row.get("x3") == 42 for row in info["behavior"]))

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_capstone_unreachable_property(self):
        program = {
            "image": image_from_words([ADD(3, 1, 2), ECALL()]),
            "init_regs": {1: 20, 2: 22},
            "property": {"reg_eq": [3, 999]},  # x3 is 42, never 999
        }
        info = reach(rv_translate(program), 3)
        self.assertEqual(info["verdict"], Verdict.UNREACHABLE)


if __name__ == "__main__":
    unittest.main()
