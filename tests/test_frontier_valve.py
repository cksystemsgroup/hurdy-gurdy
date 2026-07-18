"""The valve, widened — in shadow (plan Phase 5: C9, O3, O4).

* The mandate's scope judgment: in-scope needs the benchmark's
  evidence, obstacles inside the region, languages admissible, and an
  in-set target; everything else escalates with a reason.
* The design line: only mechanical designs instantiate (a widening, a
  registered brief taken up); an in-scope connectivity pair escalates.
* The shadow score: zero would-be false-gos earns (on top of L3), one
  burns the window; a scope rejection burns the attained rung.
* Scouting: growth classified from measured sizes; records carry the
  scout origin; no verdict ever, and a demand in exactly one case —
  the question supplied and every embedding explosive
  (SYNTHESIS.md §3: the native-procedure target, justified by the
  scout rows).
* Closure calibration: predictions and realizations live in the one
  ledger; a still-blocked question counts against precision, honestly.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

import gurdy.cli  # noqa: F401  (registers the full graph)
from gurdy.core import ledger, registry
from gurdy.core.frontier import derive

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir,
                                "tools"))
import autonomy  # noqa: E402
import closure_calibration  # noqa: E402
import mandate as mandate_mod  # noqa: E402
import scout as scout_mod  # noqa: E402
from mandate import Mandate  # noqa: E402


def _board(records):
    return [o.asdict() for o in derive(records, registry.list_pairs())]


def _cost_record(suite="hwmcc-slice"):
    return {"kind": "demand", "ts": 1.0, "origin": "campaign",
            "suite": suite,
            "question": {"source": "btor2", "shape": "reachability",
                         "program": "hw", "verdict": "resource-out"},
            "obstacle": "cost",
            "target": {"kind": "reduction", "on_any_of": ["btor2"],
                       "registered_reductions": ["btor2-havoc"]}}


def _widening_record(suite="hwmcc-slice"):
    return {"kind": "demand", "ts": 2.0, "origin": "campaign",
            "suite": suite,
            "question": {"source": "riscv", "observables": ["pc", "fflags"]},
            "obstacle": "loss",
            "target": {"kind": "wider-projection", "pairs": ["riscv-btor2"],
                       "missing_observables": ["fflags"]}}


def _connectivity_record(suite="hwmcc-slice"):
    return {"kind": "demand", "ts": 3.0, "origin": "campaign",
            "suite": suite,
            "question": {"source": "smiles", "observables": ["formula"]},
            "obstacle": "connectivity",
            "target": {"kind": "pair", "from": "smiles",
                       "into_any_of": ["btor2"]}}


MANDATE = Mandate(name="hwmcc-cost", benchmark="hwmcc-slice",
                  obstacles=("cost", "loss"),
                  languages=("btor2", "smtlib", "riscv"),
                  floors={"coverage_target": "existing inventory",
                          "direction": "over ships witness embedding"})


class TestScope(unittest.TestCase):
    def test_in_scope_and_escalations(self):
        board = _board([_cost_record(), _widening_record(),
                        _connectivity_record(),
                        _cost_record(suite="other-suite")])
        shadow = mandate_mod.would_register(MANDATE, board)
        registered = {e["id"] for e in shadow["register"]}
        reasons = {e["id"]: e["reason"] for e in shadow["escalate"]}
        by_kind = {o["kind"]: o for o in board}
        # The widening and the reduction-with-registered-match go.
        self.assertIn(by_kind["wider-projection"]["id"], registered)
        self.assertIn(by_kind["reduction"]["id"], registered)
        # Connectivity is in-set and suite-matched but its obstacle is
        # outside the mandate's region.
        conn = by_kind["pair"]
        self.assertIn("obstacle", reasons[conn["id"]])

    def test_wrong_suite_escalates(self):
        board = _board([_cost_record(suite="other-suite")])
        ok, reason = mandate_mod.in_scope(MANDATE, board[0])
        self.assertFalse(ok)
        self.assertIn("benchmark", reason)

    def test_out_of_set_always_escalates(self):
        board = _board([{
            "kind": "demand", "ts": 1.0, "origin": "campaign",
            "suite": "hwmcc-slice",
            "question": {"source": "btor2", "shape": "liveness"},
            "obstacle": "shape",
            "target": {"kind": "reasoning-language", "shape": "liveness"}}])
        ok, reason = mandate_mod.in_scope(
            Mandate(name="m", benchmark="hwmcc-slice",
                    obstacles=("shape",), languages=()), board[0])
        self.assertFalse(ok)
        self.assertIn("known set", reason)

    def test_design_line_holds(self):
        # Connectivity inside a mandate that scopes it: in scope, but
        # the design is a creative act — escalate.
        m = Mandate(name="wide", benchmark="hwmcc-slice",
                    obstacles=("connectivity",),
                    languages=("smiles", "btor2"))
        board = _board([_connectivity_record()])
        shadow = mandate_mod.would_register(m, board)
        self.assertEqual(shadow["register"], [])
        self.assertIn("creative act", shadow["escalate"][0]["reason"])

    def test_stamped_brief_carries_floors_and_valve(self):
        board = _board([_widening_record()])
        shadow = mandate_mod.would_register(MANDATE, board)
        brief = shadow["register"][0]["brief"]
        self.assertIn("Mandate-fixed floors", brief)
        self.assertIn("hwmcc-cost", brief)
        self.assertIn("revocable", brief)
        self.assertIn("registration is a human act", brief)


class TestShadowScore(unittest.TestCase):
    def _l3_ledger(self):
        return {"negative_control_catches": 5, "independent_shadow_seen": 20,
                "additive_shared_shadow_seen": 15,
                "fanout_regressions_caught": 3, "fanout_shadow_seen": 10}

    def test_clean_window_earns_l4_on_top_of_l3(self):
        led = self._l3_ledger()
        board = _board([_widening_record()])
        shadow = mandate_mod.would_register(MANDATE, board)
        oid = shadow["register"][0]["id"]
        for _ in range(10):
            trials = mandate_mod.shadow_trials(shadow, {oid: "registered"})
            led = mandate_mod.fold(led, trials)
        self.assertEqual(autonomy.attained_level(autonomy.ledger_from(led)),
                         autonomy.L4)

    def test_false_go_blocks_and_scope_rejection_burns(self):
        led = self._l3_ledger()
        board = _board([_widening_record()])
        shadow = mandate_mod.would_register(MANDATE, board)
        oid = shadow["register"][0]["id"]
        for _ in range(9):
            led = mandate_mod.fold(
                led, mandate_mod.shadow_trials(shadow, {oid: "registered"}))
        led = mandate_mod.fold(
            led, mandate_mod.shadow_trials(shadow, {oid: "declined"}))
        self.assertEqual(autonomy.attained_level(autonomy.ledger_from(led)),
                         autonomy.L3)  # a would-be false-go blocks
        clean = self._l3_ledger()
        clean["mandate_shadow_seen"] = 10
        self.assertEqual(
            autonomy.attained_level(autonomy.ledger_from(clean)),
            autonomy.L4)
        burned = mandate_mod.scope_rejection(clean)
        self.assertEqual(
            autonomy.attained_level(autonomy.ledger_from(burned)),
            autonomy.L3)  # the burn drops L4 alone

    def test_missed_go_is_not_a_disagreement(self):
        board = _board([_widening_record(), _connectivity_record()])
        shadow = mandate_mod.would_register(MANDATE, board)
        conn_id = next(o["id"] for o in board if o["kind"] == "pair")
        trials = mandate_mod.shadow_trials(shadow,
                                           {conn_id: "registered"})
        self.assertEqual(trials[0]["disagreement"], "missed-go")
        led = mandate_mod.fold({}, trials)
        self.assertEqual(led.get("mandate_shadow_disagreements", 0), 0)


class TestScout(unittest.TestCase):
    def test_growth_classified_and_recorded_as_scout(self):
        with tempfile.TemporaryDirectory() as tmp:
            books = os.path.join(tmp, "books.jsonl")
            ledger.configure(books)
            try:
                report = scout_mod.scout(
                    "toy",
                    lambda s, p: b"x" * (2 ** p if s == "boom" else 10 * p),
                    {"boom": "boom", "tame": "tame"},
                    params=[2, 4, 6, 8])
            finally:
                ledger.configure(None)
            self.assertEqual(report["readings"]["boom"]["growth"],
                             "explosive")
            self.assertEqual(report["readings"]["tame"]["growth"],
                             "polynomial-ish")
            self.assertIn("split the cluster", report["recommendation"])
            recs = ledger._records(books)
            self.assertTrue(all(r["kind"] == "scout" for r in recs))
            self.assertTrue(all(r.get("origin") == "scout" for r in recs))

    def test_bridge_demo_reads_affordable(self):
        report = scout_mod.demo()
        for r in report["readings"].values():
            self.assertEqual(r["growth"], "polynomial-ish")
        self.assertIn("reduction pair", report["recommendation"])
        self.assertIsNone(report["demand"])  # no question, no demand

    def test_unanimous_explosion_files_the_native_procedure_demand(self):
        with tempfile.TemporaryDirectory() as tmp:
            books = os.path.join(tmp, "books.jsonl")
            ledger.configure(books)
            try:
                report = scout_mod.scout(
                    "hyper-probe",
                    lambda s, p: b"x" * (2 ** p),
                    {"only": "x"}, params=[2, 4, 6, 8],
                    question={"source": "riscv",
                              "shape": "hypersafety-2"},
                    suite="toy")
            finally:
                ledger.configure(None)
            self.assertIsNotNone(report["demand"])
            demands = [r for r in ledger._records(books)
                       if r["kind"] == "demand"]
            self.assertEqual(len(demands), 1)
            d = demands[0]
            self.assertEqual(d["obstacle"], "cost")
            self.assertEqual(d["origin"], "scout")
            self.assertEqual(d["suite"], "toy")
            self.assertEqual(d["target"]["kind"], "native-procedure")
            self.assertEqual(d["target"]["scout"], "hyper-probe")
            # the atlas names the family for a charted shape
            self.assertIn("product-program", d["target"]["family"])

    def test_affordable_sample_files_nothing_even_with_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            books = os.path.join(tmp, "books.jsonl")
            ledger.configure(books)
            try:
                report = scout_mod.scout(
                    "tame-probe",
                    lambda s, p: b"x" * (10 * p),
                    {"only": "x"}, params=[2, 4, 6, 8],
                    question={"source": "riscv", "shape": "ltl"})
            finally:
                ledger.configure(None)
            self.assertIsNone(report["demand"])
            self.assertEqual([r for r in ledger._records(books)
                              if r["kind"] == "demand"], [])


class TestClosureCalibration(unittest.TestCase):
    def test_predict_realize_summary_in_one_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            books = os.path.join(tmp, "books.jsonl")
            board = _board([_connectivity_record()])
            ledger.configure(books)
            try:
                closure_calibration.predict(board[0])
                # The pair is not built: realized honestly reads 0.
                out = closure_calibration.realize(board[0]["id"], books)
            finally:
                ledger.configure(None)
            self.assertEqual(out["predicted"], 1)
            self.assertEqual(out["realized"], 0)
            self.assertEqual(out["precision"], 0.0)
            rows = closure_calibration.summary(books)
            self.assertEqual(rows[0]["status"], "realized")
            self.assertEqual(rows[0]["precision"], 0.0)

    def test_realized_full_when_questions_answer(self):
        # A prediction whose questions ARE answerable (as they would be
        # after the target lands): precision 1.0.
        with tempfile.TemporaryDirectory() as tmp:
            books = os.path.join(tmp, "books.jsonl")
            obj = {"id": "abc123", "signature": "sig",
                   "citing": [{"source": "riscv", "observables": ["pc"],
                               "shape": "reachability"}]}
            ledger.configure(books)
            try:
                closure_calibration.predict(obj)
                out = closure_calibration.realize("abc123", books)
            finally:
                ledger.configure(None)
            self.assertEqual(out["precision"], 1.0)


if __name__ == "__main__":
    unittest.main()
