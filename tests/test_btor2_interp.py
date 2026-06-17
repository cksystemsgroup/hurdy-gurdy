"""BTOR2 interpreter tests: canonical round-trip (I/O first) + evaluation."""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.languages.btor2 import canonicalize, from_text, interpret, to_text
from gurdy.languages.btor2.build import Builder

# A 3-bit counter that increments each cycle and flags `bad` when it reaches 5.
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


class TestRoundTrip(unittest.TestCase):
    def test_canonical_roundtrip_is_byte_exact(self):
        sys = from_text(COUNTER)
        self.assertEqual(to_text(sys), COUNTER)

    def test_parse_is_idempotent(self):
        once = to_text(from_text(COUNTER))
        twice = to_text(from_text(once))
        self.assertEqual(once, twice)

    def test_unsupported_op_aborts(self):
        with self.assertRaises(Unsupported):
            from_text("1 sort bitvec 8\n2 state 1\n3 rotate 1 2 2\n")


class TestCanonicalize(unittest.TestCase):
    """The builder allocates a state before the constant it is initialized to,
    which native checkers (pono/btormc) reject ("state id must be greater than
    id of second operand"). ``Builder.to_text`` must emit through
    ``canonicalize`` so every ``init`` value precedes its state."""

    def _counter_builder(self) -> Builder:
        b = Builder()
        c = b.state(8, "c")              # state first (low id) ...
        b.init(c, b.zero(8))             # ... init value created after (high id)
        b.next(c, b.op2("add", 8, c, b.one(8)))
        b.bad(b.op2("eq", 1, c, b.constd(8, 5)))
        return b

    def _init_state_gt_value(self, text: str) -> bool:
        for line in text.splitlines():
            toks = line.split()
            if len(toks) >= 5 and toks[1] == "init":
                if int(toks[3]) <= int(toks[4]):   # state id must exceed value id
                    return False
        return True

    def test_builder_output_is_conformant(self):
        text = self._counter_builder().to_text()
        self.assertTrue(self._init_state_gt_value(text), msg=text)

    def test_canonicalize_is_idempotent_and_round_trips(self):
        text = self._counter_builder().to_text()
        self.assertEqual(canonicalize(text), text)            # already canonical
        self.assertEqual(to_text(from_text(text)), text)      # model round-trips it

    def test_canonicalize_preserves_behavior(self):
        # the renumbered system evaluates identically: the 8-bit counter reaches
        # bad (== 5) at cycle 5.
        sys = from_text(self._counter_builder().to_text())
        trace = interpret(sys, {"steps": 7})
        reached = [i for i, row in enumerate(trace)
                   if any(v == 1 for k, v in row.items() if k.startswith("bad"))]
        self.assertEqual(reached, [5])


class TestEval(unittest.TestCase):
    def test_counter_increments(self):
        trace = interpret(COUNTER, {"steps": 7})
        counts = [row["count"] for row in trace]
        self.assertEqual(counts, [0, 1, 2, 3, 4, 5, 6])

    def test_bad_fires_at_five(self):
        trace = interpret(COUNTER, {"steps": 7})
        bad = [row["bad11"] for row in trace]
        # bad asserts in the cycle where count == 5 (the 6th cycle, index 5)
        self.assertEqual(bad, [0, 0, 0, 0, 0, 1, 0])

    def test_deterministic(self):
        a = interpret(COUNTER, {"steps": 6})
        b = interpret(COUNTER, {"steps": 6})
        self.assertEqual(a, b)

    def test_bv256_arithmetic(self):
        # the evaluator is arbitrary-precision with width masking, so wide
        # vectors (bv256, for evm-btor2) work with no special casing.
        big = 1 << 200
        sysrc = f"""\
1 sort bitvec 256
2 zero 1
3 state 1 acc
4 constd 1 {big}
5 add 1 3 4
6 init 1 3 2
7 next 1 3 5
8 sort bitvec 1
9 constd 1 {big}
10 eq 8 3 9
11 bad 10
"""
        trace = interpret(sysrc, {"steps": 3})
        self.assertEqual(trace[1]["acc"], big)
        self.assertEqual([r["bad11"] for r in trace], [0, 1, 0])  # acc==1<<200 at cycle 1

    def test_array_write_then_read(self):
        # mem starts mem[5]=9 via the binding; read it back, and a written cell
        # survives a transition.
        sysrc = """\
1 sort bitvec 8
2 sort array 1 1
3 state 2 mem
4 constd 1 5
5 read 1 3 4
6 sort bitvec 1
7 constd 1 9
8 eq 6 5 7
9 bad 8
"""
        trace = interpret(sysrc, {"steps": 1, "state": {"mem": {5: 9, "default": 0}}})
        self.assertEqual(trace[0]["bad9"], 1)   # mem[5] == 9
        miss = interpret(sysrc, {"steps": 1, "state": {"mem": {5: 8, "default": 0}}})
        self.assertEqual(miss[0]["bad9"], 0)

    def test_inputs_and_ops(self):
        # out = (a + 2) where a is an input; check ult comparison too.
        sysrc = """\
1 sort bitvec 8
2 input 1 a
3 constd 1 2
4 add 1 2 3
5 state 1 out
6 init 1 5 3
7 next 1 5 4
8 sort bitvec 1
9 constd 1 100
10 ugt 8 5 9
11 bad 10
"""
        # a = 40 in cycle 0; out starts 2, becomes 40+2=42 next cycle
        trace = interpret(sysrc, {"steps": 2, "inputs": {0: {2: 40}}})
        self.assertEqual(trace[0]["out"], 2)
        self.assertEqual(trace[1]["out"], 42)


if __name__ == "__main__":
    unittest.main()
