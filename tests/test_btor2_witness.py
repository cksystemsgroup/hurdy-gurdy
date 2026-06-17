"""BTOR2 ``.wit`` witness parsing + replay (languages/btor2; SOLVERS.md §4).

Replaying a native checker's witness through the shared interpreter is the
*positive*-side validation of a ``reachable`` claim — the commuting square on the
witness. These tests cover the parser, replay over states / inputs / arrays, and
(gated on a real ``btormc``) the full native-decide -> replay loop.
"""

import unittest

from gurdy.languages.btor2 import check_witness, parse_witness, replay
from gurdy.languages.riscv.interp import image_from_words
from gurdy.pairs.riscv_btor2 import translate as rv_translate
from gurdy.solvers.native_btor2 import NativeBtor2Checker
from gurdy.core.solver import Verdict

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

# A real btormc witness for COUNTER (bad at count == 5).
COUNTER_WIT = """\
sat
b0
#0
0 000 count#0
@0
#1
0 001 count#1
@1
#2
0 010 count#2
@2
#3
0 011 count#3
@3
#4
0 100 count#4
@4
#5
0 101 count#5
@5
.
"""

# bad iff input a == 42, in the first cycle.
INPUT_SYS = """\
1 sort bitvec 8
2 input 1 a
3 sort bitvec 1
4 constd 1 42
5 eq 3 2 4
6 bad 5
"""

# bad iff mem[addr] == 7.
ARRAY_SYS = """\
1 sort bitvec 8
2 sort array 1 1
3 state 2 mem
4 input 1 addr
5 read 1 3 4
6 sort bitvec 1
7 constd 1 7
8 eq 6 5 7
9 bad 8
"""


def _addr_wit(a_val: int) -> str:
    return f"sat\nb0\n#0\n@0\n0 {a_val:08b} a@0\n.\n"


class TestParseWitness(unittest.TestCase):
    def test_fields(self):
        w = parse_witness(COUNTER_WIT)
        self.assertEqual(w.bads, [0])
        self.assertEqual(w.frames, 6)
        self.assertEqual(w.states, [(0, "count", 0)])  # frame-0 initial state

    def test_rejects_non_sat(self):
        with self.assertRaises(ValueError):
            parse_witness("unsat\n")


class TestReplay(unittest.TestCase):
    def test_counter_replay_reaches_bad(self):
        trace = replay(COUNTER, COUNTER_WIT)
        self.assertEqual([r.get("count") for r in trace], [0, 1, 2, 3, 4, 5])
        self.assertTrue(check_witness(COUNTER, COUNTER_WIT))

    def test_replay_honors_witness_inputs(self):
        # the run only reaches bad for the input the witness supplies.
        self.assertTrue(check_witness(INPUT_SYS, _addr_wit(42), k=0))
        self.assertFalse(check_witness(INPUT_SYS, _addr_wit(1), k=0))  # not vacuous

    def test_array_witness_replays(self):
        wit = "sat\nb0\n#0\n0 [00000011] 00000111 mem#0\n@0\n0 00000011 addr@0\n.\n"
        self.assertTrue(check_witness(ARRAY_SYS, wit, k=0))      # mem[3]==7 -> bad
        miss = "sat\nb0\n#0\n0 [00000011] 00000111 mem#0\n@0\n0 00000001 addr@0\n.\n"
        self.assertFalse(check_witness(ARRAY_SYS, miss, k=0))    # mem[1]==0 -> no bad


@unittest.skipUnless(NativeBtor2Checker().available(), "no native btormc/pono")
class TestNativeWitnessRoundtrip(unittest.TestCase):
    """The real loop: a native checker decides reachable and emits a ``.wit``;
    replaying it through the shared interpreter must reach the same bad."""

    def test_counter(self):
        verdict, wit = NativeBtor2Checker().decide_witness(COUNTER, 8)
        self.assertEqual(verdict, Verdict.REACHABLE)
        self.assertIsNotNone(wit)
        self.assertTrue(check_witness(COUNTER, wit))

    def test_riscv_btor2_carry_back(self):
        def add(d, a, c):
            return ((c << 20) | (a << 15) | (d << 7) | 0x33) & 0xFFFFFFFF
        prog = {"image": image_from_words([add(3, 1, 2), 0x73]),
                "init_regs": {1: 20, 2: 22}, "property": {"reg_eq": [3, 42]}}
        system = rv_translate(prog)
        verdict, wit = NativeBtor2Checker().decide_witness(system, 3)
        self.assertEqual(verdict, Verdict.REACHABLE)
        trace = replay(system, wit, 3)
        self.assertTrue(check_witness(system, wit, 3))
        self.assertTrue(any(r.get("x3") == 42 for r in trace))  # carried back to RISC-V


if __name__ == "__main__":
    unittest.main()
