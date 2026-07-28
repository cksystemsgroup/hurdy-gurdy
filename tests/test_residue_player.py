"""The residue take-up player (the last two family members, played).

* Routing unchanged: a pin with a standing cost demand goes
  portfolio-first — msat-ic3ia through the pinned container, then
  ABC's pdr — everything else exact-first; probes play bounded BMC.
* Currency unchanged: unbounded ``unreachable`` books
  ``bounded: false``; ``reachable`` only after a replayable witness
  (ABC has none yet — its sat stays unconfirmed and the portfolio
  continues); a later ``unsat`` books the disagreement as ``unknown``;
  a spent portfolio cites the caps and the played-and-spent dials.
* Gated on the real toolchains: ABC two-sided through the adapter
  (including the constraint-blocked fixture that forced the ``fold``
  rule), the containerized msat-ic3ia two-sided, and the wired
  ``--engine residue`` iteration end-to-end.
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
from frontier_loop import run_iteration  # noqa: E402
from residue_player import make_decide  # noqa: E402
from test_pono_player import (_bench, _books,  # noqa: E402
                              _recording_native, _recording_pono)


def _recording_leg(script):
    """Pops ``(verdict, witness)`` per call, recording the call."""
    calls: list[str] = []
    queue = list(script)

    def leg(text: str):
        calls.append(text)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return leg, calls


class TestRouting(unittest.TestCase):
    def test_standing_demand_plays_msat_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            native, ncalls = _recording_native([(Verdict.UNREACHABLE, None)])
            msat, mcalls = _recording_leg([(Verdict.UNREACHABLE, None)])
            abc, acalls = _recording_leg([(Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=native,
                                  pono=None, msat=msat, abc=abc)(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["engine"], "pono-msat")
            self.assertEqual(meta["mode"], "msat-ic3ia")
            self.assertFalse(meta["bounded"])
            self.assertEqual(meta["claim"], "unreachable-unbounded")
            self.assertEqual(ncalls, [])          # exact never spent
            self.assertEqual(len(mcalls), 1)
            self.assertEqual(acalls, [])          # msat answered first

    def test_unblocked_goes_exact_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"easy": text})
            books = _books(tmp, bench.suite, [])
            native, ncalls = _recording_native([(Verdict.REACHABLE, "wit")])
            msat, mcalls = _recording_leg([(Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=native,
                                  pono=None, msat=msat,
                                  abc=msat)(text, 8)
            self.assertIs(v, Verdict.REACHABLE)
            self.assertEqual(meta, {"engine": "btormc"})
            self.assertEqual(len(ncalls), 1)
            self.assertEqual(mcalls, [])


class TestVerdictMapping(unittest.TestCase):
    def _confirming(self, ok: bool):
        saved = pono_player.check_witness
        pono_player.check_witness = lambda _t, _w, k=None: ok
        self.addCleanup(
            lambda: setattr(pono_player, "check_witness", saved))

    def test_falls_through_msat_to_abc(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            msat, _ = _recording_leg([(Verdict.RESOURCE_OUT, None)])
            abc, acalls = _recording_leg([(Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=None, msat=msat, abc=abc)(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["engine"], "abc")
            self.assertEqual(meta["mode"], "pdr")
            self.assertFalse(meta["bounded"])
            self.assertEqual(len(acalls), 1)

    def test_msat_reachable_only_after_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            self._confirming(True)
            msat, _ = _recording_leg([(Verdict.REACHABLE, "wit")])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=None, msat=msat,
                                  abc=msat)(text, 8)
            self.assertIs(v, Verdict.REACHABLE)
            self.assertEqual(meta["engine"], "pono-msat")
            self.assertTrue(meta["replay_confirms"])

    def test_abc_sat_stays_unconfirmed_and_spends(self):
        # ABC carries no replayable witness yet: its sat is recorded,
        # never believed, and the spent portfolio cites it.
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"],
                           spent=["btor2-havoc"])
            self._confirming(False)
            msat, _ = _recording_leg([(Verdict.RESOURCE_OUT, None)])
            abc, _ = _recording_leg([(Verdict.REACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=None, msat=msat, abc=abc)(text, 8)
            self.assertIs(v, Verdict.RESOURCE_OUT)
            self.assertIn("pdr", meta["note"])
            self.assertEqual(meta["spent_pairs"], ["btor2-havoc"])
            self.assertIn("wall", meta["capped"])

    def test_unbounded_disagreement_stays_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            self._confirming(False)
            msat, _ = _recording_leg([(Verdict.REACHABLE, "degenerate")])
            abc, _ = _recording_leg([(Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=None, msat=msat, abc=abc)(text, 8)
            self.assertIs(v, Verdict.UNKNOWN)
            self.assertIn("disagreement", meta["note"])
            self.assertIn("msat-ic3ia", meta["note"])

    def test_probe_plays_bounded_bmc_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            msat, mcalls = _recording_leg([(Verdict.UNREACHABLE, None)])
            pono, pcalls = _recording_pono([(Verdict.UNKNOWN, None)])
            v, meta = make_decide(bench, books, k=8, native=None,
                                  pono=pono, msat=msat,
                                  abc=msat)(text, 4)
            self.assertEqual(pcalls, [("bmc", 4)])
            self.assertEqual(mcalls, [])
            self.assertTrue(meta["probe"])


class TestWiredAbc(unittest.TestCase):
    """Gated on the host abc + btor2aiger builds."""

    def _checker(self):
        from gurdy.solvers.abc_btor2 import AbcBtor2Checker

        checker = AbcBtor2Checker()
        if not checker.available():
            self.skipTest("abc/btor2aiger not available")
        return checker

    def test_two_sided_canaries(self):
        checker = self._checker()
        v, _ = checker.decide("1 sort bitvec 1\n2 one 1\n3 bad 2\n")
        self.assertIs(v, Verdict.REACHABLE)
        v, _ = checker.decide("1 sort bitvec 1\n2 zero 1\n3 bad 2\n")
        self.assertIs(v, Verdict.UNREACHABLE)

    def test_constraint_blocked_needs_fold(self):
        # The rule the discriminating fixture forced: without fold,
        # plain pdr calls this reachable.
        checker = self._checker()
        blocked = ("1 sort bitvec 1\n2 input 1 g\n3 constraint 2\n"
                   "4 not 1 2\n5 bad 4\n")
        v, _ = checker.decide(blocked)
        self.assertIs(v, Verdict.UNREACHABLE)

    def test_multibad_any_bad_per_property(self):
        checker = self._checker()
        multibad = ("1 sort bitvec 1\n2 input 1 g\n3 constraint 2\n"
                    "4 not 1 2\n5 bad 4\n6 sort bitvec 1\n7 one 6\n"
                    "8 bad 7\n")
        v, frame = checker.decide_frame(multibad)
        self.assertIs(v, Verdict.REACHABLE)
        self.assertEqual(frame, 0)


class TestWiredPonoMsat(unittest.TestCase):
    """Gated on docker + the pinned pono-msat image."""

    def _checker(self):
        from gurdy.solvers.pono_msat_btor2 import (PonoMsatBtor2Checker,
                                                   find_pono_msat)

        if not find_pono_msat():
            self.skipTest("pono-msat image not available")
        return PonoMsatBtor2Checker()

    def test_two_sided_canaries(self):
        from gurdy.languages.btor2.witness import check_witness

        checker = self._checker()
        reach = "1 sort bitvec 1\n2 one 1\n3 bad 2\n"
        v, wit = checker.decide(reach)
        self.assertIs(v, Verdict.REACHABLE)
        if wit:
            self.assertTrue(check_witness(reach, wit))
        v, _ = checker.decide("1 sort bitvec 1\n2 zero 1\n3 bad 2\n")
        self.assertIs(v, Verdict.UNREACHABLE)


class TestWiredResidue(unittest.TestCase):
    def test_engine_residue_iteration_end_to_end(self):
        import hashlib
        import json

        from gurdy.core.benchmark import Benchmark, Instance
        from gurdy.core.question import Question
        from gurdy.solvers.abc_btor2 import AbcBtor2Checker
        from gurdy.solvers.native_btor2 import find_btormc
        from gurdy.solvers.pono_btor2 import find_pono
        from gurdy.solvers.pono_msat_btor2 import find_pono_msat

        if not (AbcBtor2Checker().available() and find_pono_msat()
                and find_btormc() and find_pono()):
            self.skipTest("residue toolchain not fully available")
        with tempfile.TemporaryDirectory() as tmp:
            text = "1 sort bitvec 1\n2 one 1\n3 bad 2\n"
            path = os.path.join(tmp, "one.btor2")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            bench = Benchmark(
                suite="toy-residue-wired", source=f"dir:{tmp}",
                instances=(Instance(
                    name="one", path="one.btor2",
                    sha256=hashlib.sha256(text.encode()).hexdigest(),
                    question=Question(source="btor2",
                                      shape="reachability",
                                      program="one")),))
            work = os.path.join(tmp, "work")
            rec = run_iteration(bench, work, k=4, engine="residue",
                                cache_dir=tmp)
            self.assertEqual(rec["caps"]["engine"], "native+residue")
            self.assertEqual(rec["caps"]["portfolio"],
                             ["msat-ic3ia", "abc-pdr"])
            self.assertIn("already_spent_modes", rec["caps"])
            with open(os.path.join(work, "iterations.jsonl"),
                      encoding="utf-8") as f:
                row = json.loads(f.readlines()[-1])
            self.assertEqual(
                row["verdicts"]["one"]["verdict"], "reachable")


if __name__ == "__main__":
    unittest.main()
