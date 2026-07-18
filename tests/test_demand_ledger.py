"""The demand side of the books (core/ledger.py; AGENTS.md §1): the
diagnosis calls record unmet demand — question verbatim, obstacle,
generation target, origin — and `demand_summary` aggregates it per
target with distinct-question dedup and per-origin counts. The economy
of scale made auditable: a pair is recommended by the demand that names
it — the failing obstacle is the one taxonomy — and choosing stays the
human act."""

import os
import tempfile
import unittest

from gurdy.core import ledger
from gurdy.core.whynot import why_not

import gurdy.pairs.btor2_smtlib   # noqa: F401  (registration)
import gurdy.pairs.riscv_btor2    # noqa: F401
import gurdy.pairs.riscv_sail     # noqa: F401
import gurdy.pairs.sail_btor2     # noqa: F401
import gurdy.pairs.smiles_formula  # noqa: F401
import gurdy.pairs.wasm_btor2     # noqa: F401


class _LedgerCase(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        ledger.configure(self.path)

    def tearDown(self):
        ledger._reset()
        os.unlink(self.path)


class TestDemandRecording(_LedgerCase):
    def test_unanswerable_records_the_question_verbatim(self):
        why_not("riscv", observables=["pc"], shape="liveness")
        recs = [r for r in ledger._records() if r["kind"] == "demand"]
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["obstacle"], "shape")
        self.assertNotIn("currency", r)  # obstacles are the one taxonomy
        self.assertEqual(r["origin"], "organic")
        self.assertEqual(r["question"],
                         {"source": "riscv", "observables": ["pc"],
                          "shape": "liveness"})
        self.assertEqual(r["target"]["kind"], "native-procedure")

    def test_answerable_records_nothing(self):
        why_not("riscv", observables=["pc"], shape="reachability")
        self.assertEqual(
            [r for r in ledger._records() if r["kind"] == "demand"], [])

    def test_trust_demand_is_the_fifth_obstacle(self):
        record = why_not("wasm", floor="universal", origin="campaign")
        self.assertFalse(record["answerable"])
        self.assertEqual(record["obstacle"], "trust")
        recs = [r for r in ledger._records() if r["kind"] == "demand"]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["obstacle"], "trust")
        self.assertEqual(recs[0]["origin"], "campaign")
        self.assertEqual(recs[0]["question"]["floor"], "universal")
        self.assertEqual(recs[0]["target"]["kind"], "independent-pair")

    def test_met_floor_records_no_demand(self):
        record = why_not("riscv", floor="checked")
        self.assertTrue(record["answerable"])
        self.assertTrue(record["met_by"])
        self.assertEqual(
            [r for r in ledger._records() if r["kind"] == "demand"], [])

    def test_corroborated_floor_is_answerable_and_records_nothing(self):
        # riscv at floor universal: no declared grade meets it, but the
        # prose-vs-Sail branch corroborates past it - not a demand.
        record = why_not("riscv", floor="universal")
        self.assertTrue(record["answerable"])
        self.assertEqual(record["met_by"], [])
        self.assertTrue(record["corroboration"])
        self.assertEqual(
            [r for r in ledger._records() if r["kind"] == "demand"], [])


class TestDemandSummary(_LedgerCase):
    def test_board_dedups_questions_and_splits_origins(self):
        # the same liveness question twice (one organic, one campaign) and
        # a distinct eBPF-flavored one, all naming the same target kind
        why_not("riscv", observables=["pc"], shape="liveness")
        why_not("riscv", observables=["pc"], shape="liveness",
                origin="campaign")
        why_not("riscv", observables=["pc", "x1"], shape="liveness")
        board = ledger.demand_summary()
        self.assertEqual(len(board), 1)
        e = board[0]
        self.assertEqual(e["target"]["kind"], "native-procedure")
        self.assertEqual(e["distinct_questions"], 2)  # dedup by identity
        self.assertEqual(e["origins"], {"campaign": 1, "organic": 2})
        self.assertEqual(e["obstacles"], ["shape"])

    def test_board_sorts_by_evidence_volume(self):
        for obs in (["pc"], ["pc", "x1"], ["x2"]):
            why_not("riscv", observables=obs, shape="liveness")
        why_not("smiles")  # one connectivity demand
        board = ledger.demand_summary()
        self.assertEqual(board[0]["target"]["kind"], "native-procedure")
        self.assertEqual(board[0]["distinct_questions"], 3)
        kinds = [e["target"]["kind"] for e in board]
        self.assertIn("pair", kinds)

    def test_demands_pool_across_hosts(self):
        why_not("smiles")
        with open(self.path, "a", encoding="utf-8") as f:
            # the same target signature from another machine still counts
            recs = ledger._records()
            other = dict(recs[-1], host="other-host", key="other-question")
            import json
            f.write(json.dumps(other) + "\n")
        board = ledger.demand_summary()
        self.assertEqual(board[0]["distinct_questions"], 2)


if __name__ == "__main__":
    unittest.main()
