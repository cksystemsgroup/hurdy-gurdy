"""The loop, the report, and the cost reading (plan C6/C7/O2;
FRONTIER.md §5).

* One iteration on a toy hub-native benchmark with an **injected**
  decide function (the same seam the general player will use):
  verdicts recorded, the iteration record self-contained, saturation
  computed, the deposit appended.
* A spent verdict books a suite-tagged **cost demand** and keeps the
  benchmark non-saturated through the standing-demand path.
* The report is a **pure function** of ``iterations.jsonl`` —
  regenerating from the same input is byte-identical.
* The failure-mode reading classifies measured curves (exponential vs
  linear in ``k``) and reads ``unmeasured`` on fewer than three
  bounds, never a guess.
* Gated on z3: the same iteration through the real bridge engine.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest

import gurdy.cli  # noqa: F401  (registers the full graph)
from gurdy.core import ledger
from gurdy.core.benchmark import Benchmark, Instance
from gurdy.core.question import Question
from gurdy.core.solver import Verdict

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir,
                                "tools"))
from frontier_loop import run_iteration  # noqa: E402
from saturation_report import (build_report, failure_modes,  # noqa: E402
                               render_markdown)


def _counter(bad_at: int) -> str:
    from gurdy.languages.btor2.build import Builder

    b = Builder()
    c = b.state(8, "c")
    b.init(c, b.zero(8))
    b.next(c, b.op2("add", 8, c, b.one(8)))
    b.bad(b.op2("eq", 1, c, b.constd(8, bad_at)))
    return b.to_text()


def _toy_bench(tmp: str) -> Benchmark:
    instances = []
    for name, bad_at, expected in (("hits", 3, "reachable"),
                                   ("misses", 200, "unreachable")):
        text = _counter(bad_at)
        path = os.path.join(tmp, f"{name}.btor2")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        instances.append(Instance(
            name=name, path=f"{name}.btor2",
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            question=Question(source="btor2", shape="reachability",
                              program=name),
            expected=expected))
    return Benchmark(suite="toy-loop", source=f"dir:{tmp}",
                     instances=tuple(instances))


def _inject(verdict_by_marker):
    """A decide function keyed on the bad constant in the text."""
    def decide(text: str, k: int):
        for marker, v in verdict_by_marker.items():
            if marker in text:
                return v, {"engine": "injected"}
        raise AssertionError("unmatched instance")
    return decide


class TestLoopIteration(unittest.TestCase):
    def test_one_iteration_deposits_and_saturates(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = _toy_bench(tmp)
            work = os.path.join(tmp, "work")
            rec = run_iteration(
                bench, work, k=8,
                decide=_inject({"constd 1 3\n": Verdict.REACHABLE,
                                "constd 1 200\n": Verdict.UNREACHABLE}))
            self.assertEqual(rec["iteration"], 0)
            self.assertTrue(rec["verdicts"]["hits"]["agree"])
            self.assertTrue(rec["verdicts"]["misses"]["agree"])
            self.assertTrue(rec["saturation"]["saturated"])
            # Self-contained deposit: the record round-trips as JSON.
            with open(os.path.join(work, "iterations.jsonl")) as f:
                lines = [json.loads(line) for line in f]
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["suite"], "toy-loop")

    def test_spent_verdict_books_cost_demand_and_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = _toy_bench(tmp)
            work = os.path.join(tmp, "work")
            rec = run_iteration(
                bench, work, k=8, probe=False,
                decide=_inject({"constd 1 3\n": Verdict.REACHABLE,
                                "constd 1 200\n": Verdict.RESOURCE_OUT}))
            sat = rec["saturation"]
            self.assertFalse(sat["saturated"])
            self.assertEqual(sat["open"], ["misses"])
            board = ledger.demand_summary(
                os.path.join(work, "books.jsonl"), suite="toy-loop")
            self.assertEqual(len(board), 1)
            self.assertEqual(board[0]["obstacles"], ["cost"])
            red = next(o for o in sat["board"] if o["kind"] == "reduction")
            self.assertIn("btor2-havoc", red["registered_matches"])

    def test_monotone_across_iterations(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = _toy_bench(tmp)
            work = os.path.join(tmp, "work")
            run_iteration(bench, work, k=8, probe=False,
                          decide=_inject(
                              {"constd 1 3\n": Verdict.REACHABLE,
                               "constd 1 200\n": Verdict.RESOURCE_OUT}))
            # Second iteration: the budget suffices (a better engine, a
            # raised cap — growth). The fresh iteration's own records
            # carry no cost demand; the first iteration's standing
            # demand is *prior* history the loop owns the freshness of.
            rec2 = run_iteration(
                bench, work, k=8,
                decide=_inject({"constd 1 3\n": Verdict.REACHABLE,
                                "constd 1 200\n": Verdict.UNREACHABLE}))
            self.assertEqual(rec2["iteration"], 1)
            with open(os.path.join(work, "iterations.jsonl")) as f:
                its = [json.loads(line) for line in f]
            report = build_report(its)
            fractions = [c["answered_fraction"] for c in report["curve"]]
            self.assertEqual(fractions, sorted(fractions))  # monotone

    def test_growth_closes_prior_standing_demand(self):
        # The freshness contract (saturate: "the loop owns freshness"):
        # once this iteration answers a question, a spent budget from a
        # PRIOR iteration must not hold it open — the record stays on
        # the cumulative books, but its hold on the fixpoint is gone.
        with tempfile.TemporaryDirectory() as tmp:
            bench = _toy_bench(tmp)
            work = os.path.join(tmp, "work")
            run_iteration(bench, work, k=8, probe=False,
                          decide=_inject(
                              {"constd 1 3\n": Verdict.REACHABLE,
                               "constd 1 200\n": Verdict.RESOURCE_OUT}))
            rec2 = run_iteration(
                bench, work, k=8,
                decide=_inject({"constd 1 3\n": Verdict.REACHABLE,
                                "constd 1 200\n": Verdict.UNREACHABLE}))
            sat = rec2["saturation"]
            self.assertTrue(sat["saturated"])
            self.assertEqual(sat["open"], [])
            self.assertEqual(sat["board"], [])
            books = os.path.join(work, "books.jsonl")
            demands = [r for r in ledger._records(books)
                       if r.get("kind") == "demand"]
            self.assertEqual(len(demands), 1)  # iteration 0's, kept
            self.assertFalse(os.path.exists(
                os.path.join(work, "books.iteration.jsonl")))


class TestReport(unittest.TestCase):
    def _iterations(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = _toy_bench(tmp)
            work = os.path.join(tmp, "work")
            run_iteration(
                bench, work, k=8,
                decide=_inject({"constd 1 3\n": Verdict.REACHABLE,
                                "constd 1 200\n": Verdict.UNREACHABLE}))
            with open(os.path.join(work, "iterations.jsonl")) as f:
                return [json.loads(line) for line in f]

    def test_report_regenerates_byte_identically(self):
        its = self._iterations()
        r1, r2 = build_report(its), build_report(its)
        self.assertEqual(json.dumps(r1, sort_keys=True, default=str),
                         json.dumps(r2, sort_keys=True, default=str))
        self.assertEqual(render_markdown(r1), render_markdown(r2))
        md = render_markdown(r1)
        self.assertIn("## The curve", md)
        self.assertIn("## Way-census", md)
        self.assertIn("byte-identical", md)

    def test_census_round_trips_through_the_report(self):
        its = self._iterations()
        report = build_report(its)
        self.assertIn("hits", report["census"])
        for route in report["census"]["hits"]:
            self.assertIn("assurance", route)


class TestFailureModes(unittest.TestCase):
    def _recs(self, walls_by_k, key="sys1"):
        return [{"kind": "decide", "key": key, "k": k, "wall_s": w,
                 "engine": "e", "size": 100}
                for k, w in walls_by_k.items()]

    def test_exponential_curve_names_the_unbounded_remedy(self):
        fm = failure_modes(self._recs({2: 0.01, 4: 0.08, 8: 5.0, 12: 300.0}))
        self.assertEqual(fm["sys1"]["fit"], "exponential-in-k")
        self.assertIn("unbounded engine", fm["sys1"]["remedy"])

    def test_linear_curve_says_raise_k(self):
        fm = failure_modes(self._recs({2: 0.1, 4: 0.2, 8: 0.4, 12: 0.6}))
        self.assertEqual(fm["sys1"]["fit"], "linear-in-k")
        self.assertIn("raise k", fm["sys1"]["remedy"])

    def test_two_points_read_unmeasured(self):
        fm = failure_modes(self._recs({2: 0.1, 8: 10.0}))
        self.assertEqual(fm["sys1"]["fit"], "unmeasured")


class TestBridgeEngine(unittest.TestCase):
    def test_real_bridge_iteration(self):
        try:
            import z3  # noqa: F401
        except Exception:
            self.skipTest("z3 unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            bench = _toy_bench(tmp)
            work = os.path.join(tmp, "work")
            rec = run_iteration(bench, work, k=8, engine="bridge")
            self.assertEqual(rec["verdicts"]["hits"]["verdict"],
                             "reachable")
            self.assertEqual(rec["verdicts"]["misses"]["verdict"],
                             "unreachable")
            self.assertTrue(rec["saturation"]["saturated"])
            self.assertTrue(rec["decide_records"])  # the books' cost side


if __name__ == "__main__":
    unittest.main()
