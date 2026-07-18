"""Solver briefs and lineage-aware corroboration (SYNTHESIS.md §4;
solvers/brief.py, solvers/proved.py).

* Every inventoried engine carries a registered, valid brief, and the
  brief's lineage matches the backend's declared field.
* Validation is honest: uncharted shapes, missing or malformed
  certificate obligations, missing lineage or budgets all name their
  problem.
* The assurance ceiling follows the obligation: uncheckable caps at
  ``checked`` (corroboration-only), a declared checker reaches
  ``proved``.
* Corroboration counts lineages, not engines: two agreeing engines of
  one lineage are ``reproducible`` with the note on the record; a
  disjoint pair is ``checked``.
"""

from __future__ import annotations

import unittest

from gurdy.core.solver import Result, Verdict
from gurdy.solvers import inventory
from gurdy.solvers.brief import (
    BRIEFS,
    UNCHECKABLE,
    SolverBrief,
    assurance_ceiling,
    independent,
    validate,
)
from gurdy.solvers.native_btor2 import NativeBtor2Checker
from gurdy.solvers.proved import corroborate, prove_unreachable

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


def _brief(**over) -> SolverBrief:
    base = dict(
        engine="toy", language="smtlib",
        shapes=("reachability",),
        budgets={"wall_s": 60},
        certificates={"reachability/reachable": UNCHECKABLE},
        lineage=("toy",),
        intended="a toy")
    base.update(over)
    return SolverBrief(**base)


class TestRegisteredBriefs(unittest.TestCase):
    def test_every_inventory_engine_has_a_valid_brief(self):
        for backend in inventory.smt_backends():
            self.assertIn(backend.id, BRIEFS)
            brief = BRIEFS[backend.id]
            self.assertEqual(validate(brief), [], msg=backend.id)
            self.assertEqual(set(brief.lineage),
                             set(backend.lineage), msg=backend.id)

    def test_native_brief_valid_and_lineage_resolves_per_binary(self):
        self.assertEqual(validate(BRIEFS["native-btor2"]), [])
        self.assertEqual(NativeBtor2Checker(binary="/x/btormc").lineage,
                         ("boolector", "btormc"))
        self.assertEqual(NativeBtor2Checker(binary="/x/pono").lineage,
                         ("pono",))

    def test_briefs_close_the_unsupported_escape_hatch(self):
        # every declared shape carries a stated obligation for each of
        # its claims — no silent gap (SYNTHESIS.md §4).
        for brief in BRIEFS.values():
            for shape in brief.shapes:
                self.assertTrue(
                    any(k.startswith(f"{shape}/")
                        for k in brief.certificates), msg=brief.engine)


class TestValidation(unittest.TestCase):
    def test_valid_brief_has_no_problems(self):
        self.assertEqual(validate(_brief()), [])

    def test_uncharted_shape_is_a_problem(self):
        probs = validate(_brief(shapes=("epistemic-mu",),
                                certificates={"epistemic-mu/reachable":
                                              UNCHECKABLE}))
        self.assertTrue(any("uncharted" in p for p in probs))

    def test_missing_obligation_is_a_problem(self):
        probs = validate(_brief(certificates={}))
        self.assertTrue(any("obligation missing" in p for p in probs))

    def test_malformed_obligation_is_a_problem(self):
        probs = validate(_brief(certificates={
            "reachability/reachable": {"witness": "model"}}))  # no checker
        self.assertTrue(any("witness+checker" in p for p in probs))

    def test_missing_lineage_and_budgets_are_problems(self):
        probs = validate(_brief(lineage=(), budgets={}))
        self.assertTrue(any("lineage" in p for p in probs))
        self.assertTrue(any("budget" in p for p in probs))


class TestCeilingAndIndependence(unittest.TestCase):
    def test_ceiling_follows_the_obligation(self):
        z3 = assurance_ceiling(BRIEFS["z3"])
        self.assertEqual(z3["reachability/reachable"], "proved")
        self.assertEqual(z3["bounded-unreachability/unreachable"],
                         "checked")  # uncheckable: corroboration-only
        bw = assurance_ceiling(BRIEFS["bitwuzla"])
        self.assertEqual(bw["bounded-unreachability/unreachable"], "proved")

    def test_independence_is_lineage_disjointness(self):
        class _E:
            def __init__(self, lineage):
                self.lineage = lineage

        self.assertTrue(independent(_E(("z3",)), _E(("cvc",))))
        self.assertFalse(independent(_E(("boolector", "bitwuzla")),
                                     _E(("boolector",))))
        # undeclared ancestry is never independent — conservative
        self.assertFalse(independent(_E(()), _E(("z3",))))


class _Fake:
    def __init__(self, i, v, lineage=()):
        self.id, self._v, self.lineage = i, v, lineage

    def decide(self, _a, _d=None):
        return Result(self._v)


class TestLineageAwareCorroboration(unittest.TestCase):
    def _with(self, backends, fn):
        # corroborate resolves the inventory at call time
        orig = inventory.available_smt_backends
        inventory.available_smt_backends = lambda: backends
        try:
            return fn()
        finally:
            inventory.available_smt_backends = orig

    def test_one_lineage_agreeing_is_not_corroboration(self):
        backends = [_Fake("bitwuzla", Verdict.UNREACHABLE,
                          ("boolector", "bitwuzla")),
                    _Fake("boolector", Verdict.UNREACHABLE,
                          ("boolector",))]
        corr = self._with(backends, lambda: corroborate(b"(check-sat)"))
        self.assertTrue(corr["agree"])
        self.assertFalse(corr["independent"])
        r = self._with(backends,
                       lambda: prove_unreachable(COUNTER, 4))
        self.assertEqual(r.verdict, Verdict.UNREACHABLE)
        self.assertEqual(r.tier, "reproducible")
        self.assertIn("corroboration_note", r.provenance)

    def test_disjoint_lineages_agreeing_is_checked(self):
        backends = [_Fake("z3", Verdict.UNREACHABLE, ("z3",)),
                    _Fake("cvc5", Verdict.UNREACHABLE, ("cvc",))]
        corr = self._with(backends, lambda: corroborate(b"(check-sat)"))
        self.assertTrue(corr["agree"])
        self.assertTrue(corr["independent"])
        r = self._with(backends,
                       lambda: prove_unreachable(COUNTER, 4))
        self.assertEqual(r.tier, "checked")
        self.assertNotIn("corroboration_note", r.provenance)

    def test_undeclared_lineage_never_corroborates(self):
        backends = [_Fake("a", Verdict.UNREACHABLE),
                    _Fake("b", Verdict.UNREACHABLE)]
        corr = self._with(backends, lambda: corroborate(b"(check-sat)"))
        self.assertTrue(corr["agree"])
        self.assertFalse(corr["independent"])


if __name__ == "__main__":
    unittest.main()
