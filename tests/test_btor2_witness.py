"""BTOR2 ``.wit`` witness parsing + replay (languages/btor2; SOLVERS.md §4).

Replaying a native checker's witness through the shared interpreter is the
*positive*-side validation of a ``reachable`` claim — the commuting square on the
witness. These tests cover the parser, replay over states / inputs / arrays,
``corroborate_unreach`` (the bounded-unreachable replay corroboration, with
its deterministic and sampled negative controls), and
(gated on a real ``btormc``) the full native-decide -> replay loop.
"""

import unittest

from gurdy.languages.btor2 import check_witness, parse_witness, replay
from gurdy.languages.riscv.interp import image_from_words
from gurdy.pairs.riscv_btor2 import translate as rv_translate
from gurdy.solvers.native_btor2 import NativeBtor2Checker, find_btormc
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


class TestCorroborateUnreach(unittest.TestCase):
    """`corroborate_unreach` — the interpreter-replay surrogate for the
    solver-artifact-to-target-semantics hypothesis behind bounded-unreachable
    verdicts (paper Thm 4.9; SOLVERS.md §5). Deterministic systems get the
    single k-step run; input-carrying systems get seeded sampling. Each
    positive check is paired with its negative control."""

    def test_deterministic_unreach_within_bound(self):
        # COUNTER's bad fires at count == 5; within k=3 it cannot.
        from gurdy.languages.btor2 import corroborate_unreach
        self.assertTrue(corroborate_unreach(COUNTER, k=3))

    def test_deterministic_negative_control(self):
        # ... and at k=8 the single replay reaches it: must NOT corroborate.
        from gurdy.languages.btor2 import corroborate_unreach
        self.assertFalse(corroborate_unreach(COUNTER, k=8))

    def test_sampled_inputs_unreach(self):
        # The proved tier's E1 shape: r6 = (helper() & 0xFFF + 2)^2 can never
        # be 3 (no square is 3); sampled random helper returns corroborate.
        from gurdy.languages.btor2 import corroborate_unreach
        from gurdy.languages.ebpf import asm as e
        from gurdy.languages.ebpf.interp import program_from_words
        from gurdy.pairs.ebpf_btor2 import translate as ebpf_translate
        AND, ADD, MUL = 0x5, 0x0, 0x2
        words = [e.call(7), e.alu64_imm(AND, 0, 0xFFF),
                 e.alu64_imm(ADD, 0, 2), e.mov64_reg(6, 0),
                 e.alu64_reg(MUL, 6, 6), e.exit_()]
        head = {"prog": program_from_words(words), "init_regs": {},
                "property": {"reg_eq": [6, 3]}}
        art = ebpf_translate(head)
        self.assertTrue(corroborate_unreach(art, k=7, samples=20))

    def test_sampled_inputs_negative_control(self):
        # Mask the helper return to zero: r6 == 0 fires for EVERY input, so
        # sampling must refuse to corroborate "unreachable".
        from gurdy.languages.btor2 import corroborate_unreach
        from gurdy.languages.ebpf import asm as e
        from gurdy.languages.ebpf.interp import program_from_words
        from gurdy.pairs.ebpf_btor2 import translate as ebpf_translate
        AND = 0x5
        words = [e.call(7), e.alu64_imm(AND, 0, 0x0),
                 e.mov64_reg(6, 0), e.exit_()]
        head = {"prog": program_from_words(words), "init_regs": {},
                "property": {"reg_eq": [6, 0]}}
        art = ebpf_translate(head)
        self.assertFalse(corroborate_unreach(art, k=5, samples=3))


@unittest.skipUnless(find_btormc(), "no btormc (the .wit witness producer)")
class TestNativeWitnessRoundtrip(unittest.TestCase):
    """The real loop: btormc decides reachable and emits a ``.wit``; replaying it
    through the shared interpreter must reach the same bad."""

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
