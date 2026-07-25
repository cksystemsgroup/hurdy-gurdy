"""The avr take-up player (the exploration portfolio, played).

* Routing is unchanged from the pono take-up: a pin with a standing
  cost demand goes portfolio-first — AVR on the disjoint lineage
  first, then pono's exploration modes — everything else exact-first.
* Verdict currency is unchanged: unbounded ``unreachable`` books
  ``bounded: false``, ``reachable`` only after the witness replays,
  a spent portfolio is ``resource-out`` citing the caps and the
  played-and-spent dials.
* The deliberate refinement over the pono player: a ``sat`` without a
  replayable witness no longer ends the portfolio — it is recorded
  and exploration continues; a later ``unsat`` then books the
  disagreement as ``unknown``, never silently taking a side.
* Gated on avr (+ btormc/pono for the end-to-end): the real build on
  the two-sided canaries with witness replay, and the wired
  ``--engine avr`` iteration.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

import gurdy.cli  # noqa: F401  (registers the full graph)
from gurdy.core.solver import Verdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir,
                                "tools"))
import pono_player  # noqa: E402
from abstraction_bench import decoy_system  # noqa: E402
from avr_player import make_decide  # noqa: E402
from frontier_loop import run_iteration  # noqa: E402
from gurdy.solvers.pono_btor2 import EXPLORATION_MODES  # noqa: E402
from test_pono_player import (_bench, _books,  # noqa: E402
                              _recording_native, _recording_pono)


def _recording_avr(script):
    """Pops ``(verdict, witness)`` per call, recording the call."""
    calls: list[str] = []
    queue = list(script)

    def avr(text: str):
        calls.append(text)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return avr, calls


class TestRouting(unittest.TestCase):
    def test_standing_demand_plays_avr_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            native, ncalls = _recording_native([(Verdict.UNREACHABLE, None)])
            pono, pcalls = _recording_pono([(Verdict.UNREACHABLE, None)])
            avr, acalls = _recording_avr([(Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=native,
                                  pono=pono, avr=avr)(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["engine"], "avr")
            self.assertEqual(meta["mode"], "avr")
            self.assertFalse(meta["bounded"])
            self.assertEqual(meta["claim"], "unreachable-unbounded")
            self.assertEqual(ncalls, [])          # exact never spent
            self.assertEqual(pcalls, [])          # avr answered first
            self.assertEqual(len(acalls), 1)

    def test_unblocked_goes_exact_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"easy": text})
            books = _books(tmp, bench.suite, [])
            native, ncalls = _recording_native([(Verdict.REACHABLE, "wit")])
            avr, acalls = _recording_avr([(Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=native,
                                  pono=None, avr=avr)(text, 8)
            self.assertIs(v, Verdict.REACHABLE)
            self.assertEqual(meta, {"engine": "btormc"})
            self.assertEqual(len(ncalls), 1)
            self.assertEqual(acalls, [])


class TestVerdictMapping(unittest.TestCase):
    def _confirming(self, ok: bool):
        saved = pono_player.check_witness
        pono_player.check_witness = lambda _t, _w, k=None: ok
        self.addCleanup(
            lambda: setattr(pono_player, "check_witness", saved))

    def test_falls_through_avr_to_the_exploration_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            avr, _ = _recording_avr([(Verdict.RESOURCE_OUT, None)])
            pono, pcalls = _recording_pono([(Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=pono, avr=avr)(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["engine"], "pono")
            self.assertEqual(meta["mode"], EXPLORATION_MODES[0])
            self.assertFalse(meta["bounded"])
            self.assertEqual([m for m, _ in pcalls],
                             [EXPLORATION_MODES[0]])

    def test_reachable_only_after_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            self._confirming(True)
            avr, _ = _recording_avr([(Verdict.REACHABLE, "wit")])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=None, avr=avr)(text, 8)
            self.assertIs(v, Verdict.REACHABLE)
            self.assertEqual(meta["engine"], "avr")
            self.assertTrue(meta["replay_confirms"])

    def test_unreplayable_sat_continues_the_exploration(self):
        # The refinement over the pono player: AVR's degenerate
        # witness must not truncate the portfolio.
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"],
                           spent=["btor2-havoc"])
            self._confirming(False)
            avr, _ = _recording_avr([(Verdict.REACHABLE, "degenerate")])
            pono, pcalls = _recording_pono([(Verdict.RESOURCE_OUT, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=pono, avr=avr)(text, 8)
            self.assertIs(v, Verdict.RESOURCE_OUT)
            self.assertEqual(len(pcalls), len(EXPLORATION_MODES))
            self.assertIn("avr", meta["note"])
            self.assertEqual(meta["spent_pairs"], ["btor2-havoc"])
            self.assertIn("wall", meta["capped"])

    def test_unbounded_disagreement_stays_unknown(self):
        # An unevidenced sat followed by an unsat proof: the members
        # disagree — the player books the disagreement, no side taken.
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            self._confirming(False)
            avr, _ = _recording_avr([(Verdict.REACHABLE, "degenerate")])
            pono, _ = _recording_pono([(Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=pono, avr=avr)(text, 8)
            self.assertIs(v, Verdict.UNKNOWN)
            self.assertIn("disagreement", meta["note"])
            self.assertIn("avr", meta["note"])

    def test_probe_plays_bounded_bmc_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            avr, acalls = _recording_avr([(Verdict.UNREACHABLE, None)])
            pono, pcalls = _recording_pono([(Verdict.UNKNOWN, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=pono, avr=avr)(text, 4)
            self.assertEqual(pcalls, [("bmc", 4)])
            self.assertEqual(acalls, [])          # probes never spend avr
            self.assertTrue(meta["probe"])


class TestWiredAvr(unittest.TestCase):
    """Gated on the real host build — the brief's adapter end to end."""

    def _checker(self):
        from gurdy.solvers.avr_btor2 import AvrBtor2Checker, find_avr

        if not find_avr():
            self.skipTest("avr not available")
        return AvrBtor2Checker()

    def test_two_sided_canaries_on_the_real_build(self):
        from gurdy.languages.btor2.witness import check_witness

        checker = self._checker()
        reach = "1 sort bitvec 1\n2 one 1\n3 bad 2\n"
        v, wit = checker.decide(reach)
        self.assertIs(v, Verdict.REACHABLE)
        self.assertTrue(wit and check_witness(reach, wit))
        unreach = "1 sort bitvec 1\n2 zero 1\n3 bad 2\n"
        v, wit = checker.decide(unreach)
        self.assertIs(v, Verdict.UNREACHABLE)

    def test_invariant_needed_proof(self):
        # An even-counter whose bad is the odd bit: unreachable at
        # every depth, closed only by an invariant — the claim class
        # the exploration exists for.
        checker = self._checker()
        even = ("1 sort bitvec 4\n2 zero 1\n3 state 1 c\n4 init 1 3 2\n"
                "5 constd 1 2\n6 add 1 3 5\n7 next 1 3 6\n"
                "8 sort bitvec 1\n9 slice 8 3 0 0\n10 bad 9\n")
        v, _ = checker.decide(even)
        self.assertIs(v, Verdict.UNREACHABLE)

    def test_engine_avr_iteration_end_to_end(self):
        import hashlib
        import json

        from gurdy.core.benchmark import Benchmark, Instance
        from gurdy.core.question import Question
        from gurdy.solvers.avr_btor2 import find_avr
        from gurdy.solvers.native_btor2 import find_btormc
        from gurdy.solvers.pono_btor2 import find_pono

        if not (find_avr() and find_btormc() and find_pono()):
            self.skipTest("avr+btormc+pono not all available")
        with tempfile.TemporaryDirectory() as tmp:
            text = "1 sort bitvec 1\n2 one 1\n3 bad 2\n"
            path = os.path.join(tmp, "one.btor2")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            bench = Benchmark(
                suite="toy-avr-wired", source=f"dir:{tmp}",
                instances=(Instance(
                    name="one", path="one.btor2",
                    sha256=hashlib.sha256(text.encode()).hexdigest(),
                    question=Question(source="btor2",
                                      shape="reachability",
                                      program="one")),))
            work = os.path.join(tmp, "work")
            rec = run_iteration(bench, work, k=4, engine="avr",
                                cache_dir=tmp)
            self.assertEqual(rec["caps"]["engine"], "native+pono+avr")
            self.assertEqual(rec["caps"]["portfolio"][0], "avr")
            self.assertIn("already_spent_modes", rec["caps"])
            with open(os.path.join(work, "iterations.jsonl"),
                      encoding="utf-8") as f:
                row = json.loads(f.readlines()[-1])
            self.assertEqual(
                row["verdicts"]["one"]["verdict"], "reachable")


if __name__ == "__main__":
    unittest.main()
