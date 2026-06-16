"""BTOR2 interpreter tests: canonical round-trip (I/O first) + evaluation."""

import unittest

from gurdy.core.errors import Unsupported
from gurdy.languages.btor2 import from_text, interpret, to_text

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
