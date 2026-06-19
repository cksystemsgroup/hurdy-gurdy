"""The shared SMT solver inventory (SOLVERS.md §8; solvers/inventory.py,
solvers/smt_cli.py).

The framework enumerates the registered backends and filters to those present;
corroboration dispatches over them and flags any disagreement. Tests that need a
binary are gated on it; the registry shape and the pure verdict parser are tested
unconditionally.
"""

import shutil
import unittest

from gurdy.core.solver import Result, Verdict
from gurdy.solvers import inventory, smt_cli
from gurdy.solvers.proved import corroborate
from gurdy.pairs.btor2_smtlib import translate

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


class TestVerdictParser(unittest.TestCase):
    def test_tokens(self):
        self.assertEqual(smt_cli.parse_verdict("unsat"), Verdict.UNREACHABLE)
        self.assertEqual(smt_cli.parse_verdict("sat"), Verdict.REACHABLE)
        self.assertEqual(smt_cli.parse_verdict("unknown"), Verdict.UNKNOWN)
        self.assertEqual(smt_cli.parse_verdict("(error \"x\")\nsat"), Verdict.REACHABLE)
        self.assertEqual(smt_cli.parse_verdict(""), Verdict.UNKNOWN)


class TestRegistry(unittest.TestCase):
    def test_registered_engines_and_order(self):
        ids = [b.id for b in inventory.smt_backends()]
        # z3/bitwuzla always constructible here; the CLI three are always listed.
        for eid in ("boolector", "cvc5", "yices2"):
            self.assertIn(eid, ids)
        self.assertLess(ids.index("boolector"), ids.index("cvc5"))  # stable order

    def test_available_is_subset_present(self):
        avail = {b.id for b in inventory.available_smt_backends()}
        registered = {b.id for b in inventory.smt_backends()}
        self.assertLessEqual(avail, registered)
        # an absent engine is filtered out
        for eid in ("cvc5", "yices2"):
            if not shutil.which(eid) and not shutil.which("yices-smt2"):
                self.assertNotIn(eid, avail)

    def test_cli_backend_identities(self):
        self.assertEqual(smt_cli.Cvc5SmtBackend().binaries, ("cvc5",))
        self.assertEqual(smt_cli.Yices2SmtBackend().binaries, ("yices-smt2", "yices2"))


@unittest.skipUnless(shutil.which("boolector"), "boolector not installed")
class TestBoolector(unittest.TestCase):
    def test_decide(self):
        b = smt_cli.BoolectorSmtBackend()
        self.assertEqual(b.decide(translate({"system": COUNTER, "k": 4})).verdict,
                         Verdict.UNREACHABLE)
        self.assertEqual(b.decide(translate({"system": COUNTER, "k": 6})).verdict,
                         Verdict.REACHABLE)


class TestCorroborationSpansInventory(unittest.TestCase):
    def test_disagreement_is_localized(self):
        # two engines returning different verdicts must be flagged, not silently
        # reconciled (SOLVERS.md §7 — a translator-or-solver bug).
        class _Fake:
            def __init__(self, i, v):
                self.id, self._v = i, v

            def decide(self, _a, _d=None):
                return Result(self._v)

        orig = inventory.available_smt_backends
        inventory.available_smt_backends = lambda: [
            _Fake("a", Verdict.UNREACHABLE), _Fake("b", Verdict.REACHABLE)]
        try:
            corr = corroborate(b"(check-sat)")
            self.assertFalse(corr["agree"])
            self.assertEqual(corr["verdict"], Verdict.UNKNOWN)
            self.assertEqual(corr["disagreement"], {"a": "unreachable", "b": "reachable"})
        finally:
            inventory.available_smt_backends = orig

    @unittest.skipUnless(len(inventory.available_smt_backends()) >= 2, "need ≥2 engines")
    def test_real_engines_agree(self):
        corr = corroborate(translate({"system": COUNTER, "k": 4}))
        self.assertTrue(corr["agree"])
        self.assertIsNone(corr["disagreement"])


if __name__ == "__main__":
    unittest.main()
