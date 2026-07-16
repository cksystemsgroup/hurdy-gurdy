"""The far side, derived — and the fixpoint check (FRONTIER.md §1.1).

Covers the Phase-2 acceptance criteria of FRONTIER-PLAN.md §2.1:

* **Question identity is stable** (S1): a question without the new
  ``program`` field hashes exactly as the ad-hoc dicts always have,
  and old ledgers parse (no ``suite`` → unscoped records).
* **Benchmark** (C1): JSON round-trip; pinned fetch from a local
  snapshot verifies the sha256 and a mismatch is an error, never a
  substitution.
* **Scoped books** (C2): suite-tagged demand records filter the board;
  suite is a record field, never part of question identity.
* **Frontier derivation** (C3): pure (same inputs, same output; the
  registry untouched), grouped by target signature, the required
  contract joined over citing questions, in-set vs frontier
  classification, registered-but-unbuilt matches named.
* **Saturation** (C4): a toy benchmark of answerable questions is
  saturated (exit state true); an in-set connectivity target keeps it
  non-saturated; a standing cost demand naming a registered reduction
  keeps it non-saturated with the registered pair on the board.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest

import gurdy.cli  # noqa: F401  (registers the full graph)
from gurdy.core import ledger, registry
from gurdy.core.benchmark import Benchmark, Instance, fetch
from gurdy.core.frontier import derive, saturate
from gurdy.core.question import Question, question_key
from gurdy.core.whynot import why_not


class TestQuestionIdentity(unittest.TestCase):
    def test_dict_shape_matches_legacy_records(self):
        q = Question(source="riscv", observables=("pc",),
                     shape="reachability")
        self.assertEqual(q.asdict(), {"source": "riscv",
                                      "observables": ["pc"],
                                      "shape": "reachability"})
        legacy = {"source": "riscv", "observables": ["pc"],
                  "shape": "reachability"}
        self.assertEqual(q.key(), question_key(legacy))

    def test_program_extends_identity_additively(self):
        base = Question(source="btor2", shape="reachability")
        with_p = Question(source="btor2", shape="reachability",
                          program="adding.5")
        self.assertNotEqual(base.key(), with_p.key())
        self.assertNotIn("program", base.asdict())

    def test_ledger_reexports_question_key(self):
        self.assertIs(ledger.question_key, question_key)


class TestBenchmark(unittest.TestCase):
    def _toy(self, tmp):
        data = b"1 sort bitvec 1\n"
        path = os.path.join(tmp, "one.btor2")
        with open(path, "wb") as f:
            f.write(data)
        return Benchmark(
            suite="toy",
            source=f"dir:{tmp}",
            instances=(Instance(
                name="one", path="one.btor2",
                sha256=hashlib.sha256(data).hexdigest(),
                question=Question(source="btor2", shape="reachability"),
                expected="unreachable"),))

    def test_json_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = self._toy(tmp)
            b2 = Benchmark.from_json(b.to_json())
            self.assertEqual(b2, b)
            self.assertEqual(b2.provenance(), b.provenance())

    def test_fetch_verifies_the_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = self._toy(tmp)
            self.assertEqual(fetch(b, "one"), b"1 sort bitvec 1\n")
            with open(os.path.join(tmp, "one.btor2"), "wb") as f:
                f.write(b"tampered\n")
            with self.assertRaises(AssertionError):
                fetch(b, "one")

    def test_hwmcc_slice_expresses_over_the_object(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir,
                                        "tools"))
        from abstraction_bench import HWMCC, HWMCC_COMMIT, hwmcc_benchmark

        b = hwmcc_benchmark()
        self.assertEqual(len(b.instances), len(HWMCC))
        self.assertIn(HWMCC_COMMIT, b.source)
        prov = b.provenance()
        for name, meta in HWMCC.items():
            self.assertEqual(prov["sha256"][name], meta["sha256"])


class TestScopedBooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
        self.tmp.close()
        os.unlink(self.tmp.name)
        ledger.configure(self.tmp.name)

    def tearDown(self):
        ledger.configure(None)
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_suite_scopes_the_board_but_not_identity(self):
        why_not("smiles", ["formula"], origin="campaign", suite="toy")
        why_not("smiles", ["formula"], origin="organic")  # unscoped
        board_all = ledger.demand_summary(self.tmp.name)
        board_toy = ledger.demand_summary(self.tmp.name, suite="toy")
        # One question (suite is not identity), filed from two records.
        self.assertEqual(len(board_all), 1)
        self.assertEqual(board_all[0]["distinct_questions"], 1)
        self.assertEqual(board_all[0]["origins"],
                         {"campaign": 1, "organic": 1})
        self.assertEqual(board_all[0]["suites"], ["toy"])
        self.assertEqual(len(board_toy), 1)
        self.assertEqual(board_toy[0]["origins"], {"campaign": 1})

    def test_old_ledgers_parse(self):
        # A record written before suite existed: no suite field at all.
        with open(self.tmp.name, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "kind": "demand", "key": "k", "ts": 1.0,
                "question": {"source": "smiles"},
                "obstacle": "connectivity",
                "target": {"kind": "pair", "from": "smiles",
                           "into_any_of": ["btor2"]},
                "origin": "organic"}) + "\n")
        board = ledger.demand_summary(self.tmp.name)
        self.assertEqual(board[0]["suites"], [])
        self.assertEqual(ledger.demand_summary(self.tmp.name, suite="x"), [])


class TestDerivation(unittest.TestCase):
    def _records(self):
        return [
            {"kind": "demand", "ts": 1.0, "origin": "campaign",
             "suite": "toy",
             "question": {"source": "smiles", "observables": ["formula"]},
             "obstacle": "connectivity",
             "target": {"kind": "pair", "from": "smiles",
                        "into_any_of": ["btor2", "smtlib"]}},
            {"kind": "demand", "ts": 2.0, "origin": "organic",
             "question": {"source": "smiles", "observables": ["ring_count"],
                          "floor": "universal"},
             "obstacle": "connectivity",
             "target": {"kind": "pair", "from": "smiles",
                        "into_any_of": ["btor2", "smtlib"],
                        "note": "prose differs, signature does not"}},
            {"kind": "demand", "ts": 3.0, "origin": "campaign",
             "question": {"source": "riscv", "shape": "liveness"},
             "obstacle": "shape",
             "target": {"kind": "reasoning-language", "shape": "liveness"}},
            {"kind": "demand", "ts": 4.0, "origin": "campaign",
             "question": {"source": "btor2", "shape": "reachability",
                          "verdict": "resource-out"},
             "obstacle": "cost",
             "target": {"kind": "reduction", "on_any_of": ["btor2"],
                        "registered_reductions": ["btor2-havoc",
                                                  "btor2-interval"]}},
        ]

    def test_grouping_join_and_classification(self):
        pairs = registry.list_pairs()
        board = derive(self._records(), pairs)
        by_kind = {o.kind: o for o in board}
        # Two connectivity records, one signature (note stripped).
        conn = by_kind["pair"]
        self.assertEqual(conn.evidence["distinct_questions"], 2)
        self.assertEqual(conn.required["keep"], ["formula", "ring_count"])
        self.assertEqual(conn.required["floor"], "universal")
        self.assertTrue(conn.in_known_set)
        self.assertEqual(conn.evidence["suites"], ["toy"])
        # The hypothetical language is the frontier.
        self.assertFalse(by_kind["reasoning-language"].in_known_set)
        # The reduction demand names its registered-but-unbuilt match:
        # btor2-havoc is PARTIAL in the code registry; btor2-interval is
        # a prose brief only (pairs/btor2-interval/README.md) and the
        # derivation honestly cannot see it — the registered tier
        # straddles two stores until promotion (plan C8) bridges them.
        red = by_kind["reduction"]
        self.assertTrue(red.in_known_set)
        self.assertIn("btor2-havoc", red.registered_matches)
        self.assertNotIn("btor2-interval", red.registered_matches)
        self.assertEqual(red.required["budgets"], {"resource-out": 1})

    def test_derivation_is_pure_and_deterministic(self):
        pairs_before = dict(registry.list_pairs())
        recs = self._records()
        a = derive(recs, pairs_before)
        b = derive(list(reversed(recs)), pairs_before)
        self.assertEqual([o.signature for o in a],
                         [o.signature for o in b])
        self.assertEqual(a, tuple(sorted(
            b, key=lambda o: (-o.evidence["distinct_questions"],
                              o.signature))))
        self.assertEqual(registry.list_pairs(), pairs_before)


class TestSaturation(unittest.TestCase):
    def _bench(self, instances):
        return Benchmark(suite="toy", source="dir:/nonexistent",
                         instances=tuple(instances))

    def _inst(self, name, **q):
        return Instance(name=name, path=f"{name}.x", sha256="0" * 64,
                        question=Question(**q))

    def test_toy_benchmark_saturates(self):
        bench = self._bench([
            self._inst("reach", source="riscv", observables=("pc",),
                       shape="reachability"),
            self._inst("floor", source="riscv", floor="universal"),
        ])
        report = saturate(bench)
        self.assertTrue(report["saturated"])
        self.assertEqual(report["open"], [])
        self.assertEqual(len(report["solved"]), 2)

    def test_in_set_target_blocks_saturation(self):
        bench = self._bench([
            self._inst("reach", source="riscv", observables=("pc",),
                       shape="reachability"),
            self._inst("smiles", source="smiles", observables=("formula",)),
        ])
        report = saturate(bench)
        self.assertFalse(report["saturated"])
        self.assertEqual(report["open"], ["smiles"])
        self.assertEqual(len(report["actionable"]), 1)
        self.assertTrue(all(o["in_known_set"] is not None
                            for o in report["board"]))

    def test_frontier_only_board_saturates(self):
        # A shape no hub declares: the target is a hypothetical
        # reasoning language — outside the known set, so the question
        # parks on the frontier and the benchmark still saturates.
        bench = self._bench([
            self._inst("live", source="riscv", observables=("pc",),
                       shape="liveness"),
        ])
        report = saturate(bench)
        self.assertTrue(report["saturated"])
        self.assertEqual(report["open"], ["live"])
        self.assertEqual(report["actionable"], [])
        self.assertFalse(report["board"][0]["in_known_set"])

    def test_standing_cost_demand_blocks_via_registered_reduction(self):
        bench = self._bench([
            self._inst("hw", source="btor2", shape="reachability",
                       program="hw"),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            books = os.path.join(tmp, "books.jsonl")
            # The iteration's dynamic evidence: a spent verdict on this
            # exact question, recorded by a prior player run.
            ledger.configure(books)
            try:
                why_not("btor2", None, "reachability", program="hw",
                        verdict="resource-out", origin="campaign",
                        suite="toy")
            finally:
                ledger.configure(None)
            report = saturate(bench, ledger_path=books)
            self.assertFalse(report["saturated"])
            self.assertEqual(report["open"], ["hw"])
            red = next(o for o in report["board"]
                       if o["kind"] == "reduction")
            self.assertIn("btor2-havoc", red["registered_matches"])
            # And the run itself recorded nothing new for the
            # statics-answerable question beyond the standing record.
            board = ledger.demand_summary(books, suite="toy")
            self.assertEqual(len(board), 1)


if __name__ == "__main__":
    unittest.main()
