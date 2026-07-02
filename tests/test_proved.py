"""The `proved`-tier pipeline for certified unreachability (SOLVERS.md §5-6;
solvers/proved.py, solvers/bitwuzla_smt.py).

Two strengths of evidence, each gated on the tools it needs:
  - multi-engine corroboration (z3 + bitwuzla agree `unsat`) -> `checked`;
  - a bit-blasted DRAT certificate (bitwuzla -> CNF, cadical -> DRAT) that an
    independent checker (drat-trim/cake_lpr) would verify -> `proved` (the check
    is gated to the dev image; on host the certificate is produced, unchecked).
The pure verdict parser is tested unconditionally.
"""

import shutil
import unittest

from gurdy.core.solver import Verdict
from gurdy.solvers import bitwuzla_smt
from gurdy.solvers.proved import (CheckerUnavailable, bitblast_cnf, check_drat,
                                  corroborate, drat_proof, prove_unreachable)
from gurdy.pairs.btor2_smtlib import prove, translate

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

# bad iff x*x == 3 (no 8-bit solution) -> unsat, and input-driven so it reaches
# the SAT layer (a real bit-blasted CNF, unlike a closed system z3 folds away).
SQUARE = """\
1 sort bitvec 8
2 input 1 x
3 mul 1 2 2
4 constd 1 3
5 sort bitvec 1
6 eq 5 3 4
7 bad 6
"""


def _have(*names: str) -> bool:
    return any(shutil.which(n) for n in names)


def _z3() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except ImportError:
        return False


class TestVerdictParser(unittest.TestCase):
    def test_bitwuzla_tokens(self):
        self.assertEqual(bitwuzla_smt.parse_verdict("unsat\n"), Verdict.UNREACHABLE)
        self.assertEqual(bitwuzla_smt.parse_verdict("sat\n"), Verdict.REACHABLE)
        self.assertEqual(bitwuzla_smt.parse_verdict("unknown\n"), Verdict.UNKNOWN)
        self.assertEqual(bitwuzla_smt.parse_verdict(""), Verdict.UNKNOWN)


@unittest.skipUnless(_have("bitwuzla"), "bitwuzla not installed")
class TestBitwuzlaBackend(unittest.TestCase):
    def test_decide_unsat_and_sat(self):
        backend = bitwuzla_smt.BitwuzlaSmtBackend()
        self.assertEqual(backend.decide(translate({"system": COUNTER, "k": 4})).verdict,
                         Verdict.UNREACHABLE)  # count==5 not reachable within 4
        self.assertEqual(backend.decide(translate({"system": COUNTER, "k": 6})).verdict,
                         Verdict.REACHABLE)    # reachable at step 5


@unittest.skipUnless(_z3() and _have("bitwuzla"), "needs z3 + bitwuzla")
class TestCorroboration(unittest.TestCase):
    def test_engines_agree_unreachable(self):
        corr = corroborate(translate({"system": COUNTER, "k": 4}))
        self.assertTrue(corr["agree"])
        self.assertEqual(corr["verdict"], Verdict.UNREACHABLE)
        self.assertIsNone(corr["disagreement"])
        self.assertLessEqual({"z3", "bitwuzla"}, set(corr["verdicts"]))  # at least these

    def test_prove_unreachable_is_checked(self):
        r = prove(COUNTER, 4)
        self.assertEqual(r.verdict, Verdict.UNREACHABLE)
        self.assertEqual(r.tier, "checked")         # ≥2 independent solvers agree
        self.assertLessEqual({"z3", "bitwuzla"}, set(r.engines))
        self.assertIn("z3", r.tcb)

    def test_prove_reports_reachable(self):
        r = prove(COUNTER, 6)
        self.assertEqual(r.verdict, Verdict.REACHABLE)


@unittest.skipUnless(_have("bitwuzla"), "bitwuzla not installed")
class TestBitblast(unittest.TestCase):
    def test_closed_system_has_no_cnf(self):
        # a closed counter is decided in preprocessing -> nothing bit-blasted.
        self.assertIsNone(bitblast_cnf(translate({"system": COUNTER, "k": 4})))

    def test_input_driven_unsat_bitblasts(self):
        cnf = bitblast_cnf(translate({"system": SQUARE, "k": 1}))
        self.assertIsNotNone(cnf)
        self.assertTrue(cnf.lstrip().startswith("p cnf"))


@unittest.skipUnless(_have("bitwuzla") and _have("cadical"), "needs bitwuzla + cadical")
class TestDratCertificate(unittest.TestCase):
    def test_cadical_refutes_and_emits_drat(self):
        cnf = bitblast_cnf(translate({"system": SQUARE, "k": 1}))
        is_unsat, drat = drat_proof(cnf)
        self.assertTrue(is_unsat)
        self.assertIsNotNone(drat)

    def test_prove_produces_certificate(self):
        r = prove(SQUARE, 1)
        self.assertEqual(r.verdict, Verdict.UNREACHABLE)
        self.assertEqual(r.method, "bitblast-drat")
        self.assertIsNotNone(r.certificate)
        if _have("drat-trim", "cake_lpr"):
            # dev image: the independent checker certifies it -> proved
            self.assertTrue(r.checker_ok)
            self.assertEqual(r.tier, "proved")
            self.assertIn("drat-trim", " ".join(r.tcb))
        else:
            # host: certificate produced but not independently checked (issue #2)
            self.assertIsNone(r.checker_ok)
            self.assertEqual(r.tier, "checked")
            self.assertIn("proved_pending", r.provenance)


class TestCheckerGating(unittest.TestCase):
    @unittest.skipIf(_have("drat-trim", "cake_lpr"), "a checker is present")
    def test_check_drat_unavailable_on_host(self):
        with self.assertRaises(CheckerUnavailable):
            check_drat("p cnf 0 1\n0\n", b"0\n")


@unittest.skipUnless(_have("drat-trim", "cake_lpr"), "no checker installed")
class TestCheckerControls(unittest.TestCase):
    """Positive/negative controls for the checker *adapter* (SOLVERS.md §5).

    The negative control is load-bearing: drat-trim reports failure as
    "s NOT VERIFIED", which contains the substring "VERIFIED" — a naive
    match reports every outcome as verified. A bogus refutation of a
    *satisfiable* CNF can never verify, so it must come back False."""

    SAT_CNF = "p cnf 2 2\n1 2 0\n-1 2 0\n"          # satisfiable (2 = true)
    UNSAT_CNF = "p cnf 1 2\n1 0\n-1 0\n"            # x and not-x

    def test_rejects_refutation_of_satisfiable_cnf(self):
        self.assertFalse(check_drat(self.SAT_CNF, b"0\n"))

    def test_accepts_trivial_refutation(self):
        # formula + propagation already conflicts, so "0" is a valid proof.
        self.assertTrue(check_drat(self.UNSAT_CNF, b"0\n"))


if __name__ == "__main__":
    unittest.main()
