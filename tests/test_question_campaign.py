"""The question-campaign benchmark (tools/question_campaign.py; the
paper's tab:campaign): 25 authored questions whose first failing
obstacle is known by construction, run through why_not against the live
registry with a temp ledger — diagnosis accuracy, zero false demand on
the answerable controls, board dedup by question identity, and origin
separation. No solvers, no gating: the diagnosis is static."""

import importlib.util
import os
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "question_campaign", os.path.join(_ROOT, "tools", "question_campaign.py"))
question_campaign = importlib.util.module_from_spec(_spec)
sys.modules["question_campaign"] = question_campaign
_spec.loader.exec_module(question_campaign)


class TestCorpusShape(unittest.TestCase):
    def test_all_five_obstacles_and_controls_present(self):
        corpus = question_campaign.build_corpus()
        self.assertEqual(len(corpus), 25)
        by = {}
        for e in corpus:
            by[e["expected"]] = by.get(e["expected"], 0) + 1
        self.assertEqual(by, {"connectivity": 4, "loss": 4, "shape": 4,
                              "cost": 3, "trust": 3, None: 7})

    def test_questions_are_distinct(self):
        corpus = question_campaign.build_corpus()
        keys = {repr(sorted(e["kwargs"].items())) for e in corpus}
        self.assertEqual(len(keys), len(corpus))

    def test_reask_sets_are_failing_questions(self):
        corpus = {e["qid"]: e for e in question_campaign.build_corpus()}
        for qid in (question_campaign.DEDUP_QIDS
                    + question_campaign.ORGANIC_QIDS):
            self.assertIsNotNone(corpus[qid]["expected"], msg=qid)


class TestCampaign(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="campaign-test-")
        cls.report = question_campaign.run_experiment(workdir=cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_experiment_ok(self):
        self.assertTrue(self.report["ok"], msg=str(self.report["checks"]))

    def test_every_failing_question_diagnosed_correctly(self):
        for r in self.report["rows"]:
            if r["expected"] is not None:
                self.assertEqual(r["diagnosed"], r["expected"], msg=r["qid"])
                self.assertEqual(r["recorded"], 1, msg=r["qid"])

    def test_controls_answerable_and_never_recorded(self):
        for r in self.report["rows"]:
            if r["expected"] is None:
                self.assertIsNone(r["diagnosed"], msg=r["qid"])
                self.assertEqual(r["recorded"], 0, msg=r["qid"])

    def test_dedup_by_question_identity(self):
        d = self.report["checks"]["dedup"]
        self.assertTrue(d["ok"], msg=str(d))
        self.assertEqual(d["distinct_before"], 18)

    def test_origins_displayed_apart(self):
        o = self.report["checks"]["origins"]
        self.assertTrue(o["ok"], msg=str(o))
        self.assertEqual(o["rows_showing_both"], 3)

    def test_board_groups_cost_demands_to_one_reduction_target(self):
        # three cost questions from three sources share the reduction
        # target — the board's compression, not three parallel asks
        rows = [r for r in self.report["board"]
                if (r["target"] or {}).get("kind") == "reduction"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["distinct_questions"], 3)

    def test_diagnosis_is_read_only(self):
        self.assertTrue(self.report["checks"]["read_only"])


if __name__ == "__main__":
    unittest.main()
