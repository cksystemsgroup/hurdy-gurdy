"""The pono take-up player (the promotion of board entry
d4c59dafc402, played).

* Routing is the books' recommendation: a pin with a standing cost
  demand goes unbounded-first; everything else exact-first with the
  procedure as the fallback on a spent verdict.
* Portfolio verdicts map onto the loop's currency: an unbounded
  ``unreachable`` books ``bounded: false``, ``reachable`` only after
  the dumped witness replays through the shared interpreter, a spent
  wall is ``resource-out`` with the cap cited — and it re-cites the
  dials the books already hold as played-and-spent (``spent_pairs``),
  so the advanced target survives the engine change.
* Probes (a call below the iteration's k) play bounded BMC — one
  engine per curve.
* Gated on pono + btormc: the wired ``--engine pono`` iteration
  end-to-end, and the real binary on the two-sided canaries.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest

import gurdy.cli  # noqa: F401  (registers the full graph)
from gurdy.core.benchmark import Benchmark, Instance
from gurdy.core.question import Question
from gurdy.core.solver import Verdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir,
                                "tools"))
import pono_player  # noqa: E402
from abstraction_bench import decoy_system  # noqa: E402
from frontier_loop import run_iteration  # noqa: E402
from pono_player import (UNBOUNDED_MODES, make_decide,  # noqa: E402
                         spent_reductions_from_books)


def _bench(tmp: str, texts: dict[str, str],
           suite: str = "toy-pono") -> Benchmark:
    instances = []
    for name, text in texts.items():
        path = os.path.join(tmp, f"{name}.btor2")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        instances.append(Instance(
            name=name, path=f"{name}.btor2",
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            question=Question(source="btor2", shape="reachability",
                              program=name)))
    return Benchmark(suite=suite, source=f"dir:{tmp}",
                     instances=tuple(instances))


def _books(tmp: str, suite: str, blocked_names: list[str],
           spent: list[str] | None = None) -> str:
    path = os.path.join(tmp, "books.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for name in blocked_names:
            f.write(json.dumps({
                "kind": "demand", "suite": suite, "obstacle": "cost",
                "origin": "campaign",
                "question": {"program": name, "source": "btor2",
                             "shape": "reachability",
                             "verdict": "resource-out"},
                "target": {"kind": "native-procedure",
                           "spent_reductions": spent or []}}) + "\n")
    return path


def _recording_native(script):
    calls: list[tuple[str, int]] = []
    queue = list(script)

    def native(text: str, k: int):
        calls.append((text, k))
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return native, calls


def _recording_pono(script):
    """Pops ``(verdict, witness)`` per call, recording ``(mode, k)``."""
    calls: list[tuple[str, int]] = []
    queue = list(script)

    def pono(text: str, mode: str, k: int):
        calls.append((mode, k))
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return pono, calls


class TestRouting(unittest.TestCase):
    def test_standing_demand_goes_unbounded_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            native, ncalls = _recording_native([(Verdict.UNREACHABLE, None)])
            pono, pcalls = _recording_pono([(Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=native,
                                  pono=pono)(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["mode"], UNBOUNDED_MODES[0])
            self.assertFalse(meta["bounded"])
            self.assertEqual(meta["claim"], "unreachable-unbounded")
            self.assertEqual(ncalls, [])          # exact never spent
            self.assertEqual(len(pcalls), 1)

    def test_unblocked_goes_exact_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"easy": text})
            books = _books(tmp, bench.suite, [])
            native, ncalls = _recording_native([(Verdict.REACHABLE, "wit")])
            pono, pcalls = _recording_pono([(Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=native,
                                  pono=pono)(text, 8)
            self.assertIs(v, Verdict.REACHABLE)
            self.assertEqual(meta, {"engine": "btormc"})
            self.assertEqual(len(ncalls), 1)
            self.assertEqual(pcalls, [])

    def test_spent_exact_falls_back_to_the_procedure(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"newly-hard": text})
            books = _books(tmp, bench.suite, [])
            native, ncalls = _recording_native([(Verdict.RESOURCE_OUT, None)])
            pono, pcalls = _recording_pono([(Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=native,
                                  pono=pono)(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertFalse(meta["bounded"])
            self.assertEqual(len(ncalls), 1)
            self.assertEqual(len(pcalls), 1)

    def test_spent_from_books_reads_the_latest_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = _bench(tmp, {"a": decoy_system(2)})
            path = os.path.join(tmp, "books.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                for spent in ([], ["btor2-havoc"]):
                    f.write(json.dumps({
                        "kind": "demand", "suite": bench.suite,
                        "obstacle": "cost",
                        "question": {"program": "a", "source": "btor2"},
                        "target": {"spent_reductions": spent}}) + "\n")
            (a,) = bench.instances
            spent = spent_reductions_from_books(bench, path)
            self.assertEqual(spent[a.sha256], ("btor2-havoc",))


class TestVerdictMapping(unittest.TestCase):
    def _confirming(self, ok: bool):
        saved = pono_player.check_witness
        pono_player.check_witness = lambda _t, _w, k=None: ok
        self.addCleanup(
            lambda: setattr(pono_player, "check_witness", saved))

    def test_portfolio_falls_through_to_the_second_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            pono, pcalls = _recording_pono([(Verdict.UNKNOWN, None),
                                            (Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=pono)(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["mode"], UNBOUNDED_MODES[1])
            self.assertEqual([m for m, _ in pcalls],
                             list(UNBOUNDED_MODES[:2]))

    def test_portfolio_reaches_the_widened_third_mode(self):
        # The 2026-07-24 amendment's widening: a question the first two
        # modes cannot close falls through to mbic3, and its closure
        # books the same unbounded currency.
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            pono, pcalls = _recording_pono([(Verdict.UNKNOWN, None),
                                            (Verdict.RESOURCE_OUT, None),
                                            (Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=pono)(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["mode"], UNBOUNDED_MODES[2])
            self.assertFalse(meta["bounded"])
            self.assertEqual([m for m, _ in pcalls],
                             list(UNBOUNDED_MODES))

    def test_reachable_only_after_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            self._confirming(True)
            pono, _ = _recording_pono([(Verdict.REACHABLE, "wit")])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=pono)(text, 8)
            self.assertIs(v, Verdict.REACHABLE)
            self.assertTrue(meta["replay_confirms"])

    def test_sat_without_replayable_witness_stays_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"],
                           spent=["btor2-havoc"])
            pono, _ = _recording_pono([(Verdict.REACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=pono)(text, 8)
            self.assertIs(v, Verdict.UNKNOWN)
            self.assertIn("witness", meta["note"])
            self.assertEqual(meta["spent_pairs"], ["btor2-havoc"])

    def test_spent_walls_cite_the_cap_and_the_spent_dials(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"],
                           spent=["btor2-havoc"])
            pono, pcalls = _recording_pono([(Verdict.RESOURCE_OUT, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=pono)(text, 8)
            self.assertIs(v, Verdict.RESOURCE_OUT)
            self.assertIn("wall", meta["capped"])
            self.assertEqual(meta["spent_pairs"], ["btor2-havoc"])
            self.assertEqual(len(pcalls), len(UNBOUNDED_MODES))

    def test_probe_plays_bounded_bmc(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            pono, pcalls = _recording_pono([(Verdict.UNKNOWN, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=pono)(text, 4)
            self.assertIs(v, Verdict.UNKNOWN)
            self.assertTrue(meta["probe"])
            self.assertEqual(pcalls, [("bmc", 4)])


class TestWiredPono(unittest.TestCase):
    def _pono(self):
        from gurdy.solvers.pono_btor2 import PonoBtor2Checker, find_pono

        if not find_pono():
            self.skipTest("pono absent")
        return PonoBtor2Checker()

    def test_two_sided_canaries_on_the_real_binary(self):
        checker = self._pono()
        reachable = "1 sort bitvec 1\n2 one 1\n3 bad 2\n"
        v, wit = checker.decide(reachable, mode="bmc", k=2)
        self.assertIs(v, Verdict.REACHABLE)
        unreachable = "1 sort bitvec 1\n2 zero 1\n3 bad 2\n"
        for mode in UNBOUNDED_MODES:
            v, _ = checker.decide(unreachable, mode=mode)
            self.assertIs(v, Verdict.UNREACHABLE, mode)

    def test_multi_bad_aggregates_any_bad(self):
        # Pono is per-property; the question is any-bad (btormc's
        # reading). A constraint-unreachable b0 must not mask an
        # always-firing b1 — the solver gate's forced-bad shape.
        checker = self._pono()
        forced = ("1 sort bitvec 1\n2 input 1 g\n3 constraint 2\n"
                  "4 not 1 2\n5 bad 4\n"
                  "6 sort bitvec 1\n7 one 6\n8 bad 7\n")
        v, _ = checker.decide(forced, mode="bmc", k=3)
        self.assertIs(v, Verdict.REACHABLE)
        for mode in UNBOUNDED_MODES:
            v, _ = checker.decide(forced, mode=mode)
            self.assertIs(v, Verdict.REACHABLE, mode)

    def test_engine_pono_iteration_end_to_end(self):
        from gurdy.solvers.native_btor2 import find_btormc
        from gurdy.solvers.pono_btor2 import find_pono

        if not find_pono() or not find_btormc():
            self.skipTest("pono or btormc absent")
        with tempfile.TemporaryDirectory() as tmp:
            bench = _bench(tmp, {"misses": decoy_system(2, bad_at=200)})
            work = os.path.join(tmp, "work")
            rec = run_iteration(bench, work, k=12, probe=False,
                                engine="pono",
                                cache_dir=os.path.join(tmp, "cache"))
            self.assertEqual(rec["caps"]["engine"], "native+pono")
            self.assertEqual(rec["caps"]["pono_portfolio"],
                             list(UNBOUNDED_MODES))
            self.assertIn("decide_wall_s", rec["caps"])
            self.assertEqual(rec["verdicts"]["misses"]["verdict"],
                             "unreachable")
            self.assertTrue(rec["saturation"]["saturated"])


if __name__ == "__main__":
    unittest.main()
