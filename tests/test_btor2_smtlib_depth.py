"""btor2-smtlib depth: array-witness decoding (a witness that depends on
initial memory replays faithfully) and the native-vs-bridged corroboration
(the native btormc verdict must match the bridged z3 verdict)."""

import unittest

from gurdy.core.solver import Verdict
from gurdy.languages.btor2.build import Builder
from gurdy.pairs.btor2_smtlib import native_vs_bridged, reach
from gurdy.solvers.btormc import Btor2McBackend, NativeUnavailable, find_btormc, parse_verdict


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


def _mem_read_system(constraints):
    """A 1-step BTOR2 system: bad iff the (free) initial memory has the given
    byte values at the given indices."""
    b = Builder()
    mem = b.state_array(64, 8, "mem")
    conds = [b.op2("eq", 1, b.read(8, mem, b.constd(64, i)), b.constd(8, v))
             for i, v in constraints]
    bad = conds[0]
    for c in conds[1:]:
        bad = b.op2("and", 1, bad, c)
    b.bad(bad)
    b.next_array(mem, mem)
    return b.to_text()


@unittest.skipUnless(_z3(), "z3 not installed")
class TestArrayWitnessDecoding(unittest.TestCase):
    def test_initial_memory_witness_replays(self):
        # const-array default carries one cell, an explicit store the other;
        # both must be decoded for the replay to reproduce the bad.
        info = reach(_mem_read_system([(0, 42), (8, 7)]), 1)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"], "array-valued initial state must replay")

    def test_single_cell_default(self):
        info = reach(_mem_read_system([(0, 0xAB)]), 1)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])


class TestNativeCorroboration(unittest.TestCase):
    def test_parse_verdict(self):
        self.assertEqual(parse_verdict("sat\nb0 ...\n"), Verdict.REACHABLE)
        self.assertEqual(parse_verdict("unsat\n"), Verdict.UNREACHABLE)
        self.assertEqual(parse_verdict("; comment only\n"), Verdict.UNKNOWN)

    def test_missing_btormc_raises(self):
        oracle = Btor2McBackend(binary="/nonexistent/btormc")
        self.assertFalse(oracle.available())
        with self.assertRaises(NativeUnavailable):
            oracle.decide(_mem_read_system([(0, 1)]), 1)

    @unittest.skipUnless(find_btormc() and _z3(), "btormc and/or z3 not installed")
    def test_native_agrees_with_bridged(self):
        result = native_vs_bridged(_mem_read_system([(0, 42), (8, 7)]), 1)
        self.assertTrue(result["agree"])
        self.assertEqual(result["bridged"], Verdict.REACHABLE)


if __name__ == "__main__":
    unittest.main()
