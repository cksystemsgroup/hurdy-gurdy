"""The btor2-interval rung on the CEGAR ladder, played
(tools/interval_player.py — the second dial's take-up).

* Routing is the havoc player's: a pin with a standing cost demand goes
  abstraction-first; everything else exact-first with the abstraction
  as the fallback on a spent verdict.
* The rung walk: a spurious counterexample tightens the ladder state
  nearest the question one notch — havoc -> its observed [min, max]
  seed -> exact — and a confinement decides nothing until the source
  provably stays in range at the same bound (escape monitors, same
  engine): an escape refutes the seed, a spent validation demotes it,
  and only a validated interval's ``unreachable`` transfers.
* ``spent_pairs`` reports the dials the route actually played: havoc
  always, interval only once a confinement was validated or refuted.
* Gated on btormc: the wired ``--engine interval`` iteration.
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
from gurdy.languages.btor2 import interpret

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir,
                                "tools"))
import interval_player  # noqa: E402
from abstraction_bench import decoy_system  # noqa: E402
from frontier_loop import run_iteration  # noqa: E402
from interval_player import (CEGAR_MAX_ROUNDS, make_decide,  # noqa: E402
                             range_monitors, usable_seeds)
from test_havoc_player import _chain_text  # noqa: E402

#: A validation witness naming monitor 0 (the parseable refutation).
_ESCAPE_WIT = "sat\nb0\n#0\n.\n"


def _bench(tmp: str, texts: dict[str, str],
           suite: str = "toy-interval") -> Benchmark:
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


def _books(tmp: str, suite: str, blocked_names: list[str]) -> str:
    path = os.path.join(tmp, "books.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for name in blocked_names:
            f.write(json.dumps({
                "kind": "demand", "suite": suite, "obstacle": "cost",
                "origin": "campaign",
                "question": {"program": name, "source": "btor2",
                             "shape": "reachability",
                             "verdict": "resource-out"}}) + "\n")
    return path


def _recording(script):
    """An injected native leg: pops verdicts off ``script`` (repeating
    the last one) and records every text it was asked to decide."""
    calls: list[tuple[str, int]] = []
    queue = list(script)

    def native(text: str, k: int):
        calls.append((text, k))
        v, wit = queue.pop(0) if len(queue) > 1 else queue[0]
        return v, wit

    return native, calls


class _PlayerCase(unittest.TestCase):
    def _spurious(self, replay_hits: bool):
        saved = interval_player._source_replay_hits_bad
        interval_player._source_replay_hits_bad = (
            lambda _t, _w, _k: replay_hits)
        self.addCleanup(
            lambda: setattr(interval_player, "_source_replay_hits_bad",
                            saved))

    def _blocked_decide(self, tmp, text, script, k=8):
        bench = _bench(tmp, {"hard": text})
        books = _books(tmp, bench.suite, ["hard"])
        native, calls = _recording(script)
        return make_decide(bench, books, k=k, native=native), calls


class TestRouting(_PlayerCase):
    def test_standing_demand_goes_abstraction_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            decide, calls = self._blocked_decide(
                tmp, text, [(Verdict.UNREACHABLE, None)])
            v, meta = decide(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["pair"], "btor2-interval")
            self.assertEqual(meta["transfers"], "over")
            self.assertEqual(meta["rounds"], 1)
            # the first rung is havoc: one call, on the abstraction, and
            # only the havoc dial was spent — the interval rung never ran
            self.assertEqual(meta["spent_pairs"], ["btor2-havoc"])
            self.assertEqual(len(calls), 1)
            self.assertIn("havoc_", calls[0][0])
            self.assertNotIn("iv_", calls[0][0])

    def test_unblocked_goes_exact_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"easy": text})
            books = _books(tmp, bench.suite, [])
            native, calls = _recording([(Verdict.REACHABLE, "wit")])
            v, meta = make_decide(bench, books, k=8, native=native)(text, 8)
            self.assertIs(v, Verdict.REACHABLE)
            self.assertEqual(meta, {"engine": "btormc"})
            self.assertEqual(calls[0][0], text)

    def test_spent_exact_falls_back_to_abstraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"newly-hard": text})
            books = _books(tmp, bench.suite, [])
            native, calls = _recording([(Verdict.RESOURCE_OUT, None),
                                        (Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=native)(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["transfers"], "over")
            self.assertEqual(calls[0][0], text)          # the spent exact
            self.assertIn("havoc_", calls[1][0])         # then the route


class TestRungWalk(_PlayerCase):
    def test_spurious_tightens_to_the_validated_seed(self):
        # havoc round spurious -> c tightens to its observed seed; the
        # validation clears (escape unreachable), the confined artifact
        # answers, and the unreachable transfers with BOTH dials spent.
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            self._spurious(replay_hits=False)
            decide, calls = self._blocked_decide(
                tmp, text, [(Verdict.REACHABLE, "wit"),
                            (Verdict.UNREACHABLE, None),
                            (Verdict.UNREACHABLE, None)])
            v, meta = decide(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["transfers"], "over")
            self.assertEqual(meta["rounds"], 2)
            self.assertEqual(meta["spent_pairs"],
                             ["btor2-havoc", "btor2-interval"])
            self.assertEqual(meta["confined"], ["c"])
            self.assertNotIn("seed_refuted", meta)
            self.assertEqual(len(calls), 3)
            self.assertIn("havoc_c", calls[0][0])        # rung 1: havoc
            self.assertIn(" ult ", calls[1][0])          # the validation
            self.assertIn(" ugt ", calls[1][0])
            self.assertIn("iv_c", calls[2][0])           # rung 2: interval
            self.assertNotIn("havoc_c", calls[2][0])
            self.assertIn("havoc_d0", calls[2][0])       # free set stays

    def test_refuted_seed_falls_to_exact(self):
        # The validation witness names the escaping monitor: the seed is
        # refuted, that rung falls to exact, and the loop continues.
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            self._spurious(replay_hits=False)
            decide, calls = self._blocked_decide(
                tmp, text, [(Verdict.REACHABLE, "wit"),
                            (Verdict.REACHABLE, _ESCAPE_WIT),
                            (Verdict.UNREACHABLE, None)])
            v, meta = decide(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["seed_refuted"], ["c"])
            self.assertEqual(meta["confined"], [])
            self.assertEqual(meta["rounds"], 3)
            # a tested-and-falsified claim still spent the interval dial
            self.assertEqual(meta["spent_pairs"],
                             ["btor2-havoc", "btor2-interval"])
            self.assertNotIn("iv_", calls[2][0])         # c is exact now
            self.assertNotIn("havoc_c", calls[2][0])

    def test_spent_validation_demotes_the_confinement(self):
        # An unvalidated confinement must not confine: a resource-out on
        # the monitors demotes the state to exact and the round plays on.
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            self._spurious(replay_hits=False)
            decide, calls = self._blocked_decide(
                tmp, text, [(Verdict.REACHABLE, "wit"),
                            (Verdict.RESOURCE_OUT, None),
                            (Verdict.UNREACHABLE, None)])
            v, meta = decide(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["unvalidated_demoted"], ["c"])
            self.assertEqual(meta["rounds"], 2)
            self.assertNotIn("iv_", calls[2][0])

    def test_spurious_at_exact_cone_stays_unknown(self):
        # Rungs exhausted (havoc spurious, seed refuted, exact spurious):
        # the abstraction has nothing left to give up — unknown, honestly.
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            self._spurious(replay_hits=False)
            decide, _ = self._blocked_decide(
                tmp, text, [(Verdict.REACHABLE, "wit")])
            v, meta = decide(text, 8)
            self.assertIs(v, Verdict.UNKNOWN)
            self.assertEqual(meta["note"], "spurious-at-exact-cone")
            self.assertEqual(meta["seed_refuted"], ["c"])
            self.assertGreaterEqual(meta["spurious"], 2)

    def test_round_limit_is_resource_out_with_the_cap_cited(self):
        # The chain's prefix holds 4 rungs at 2 notches each: the walk
        # spends the declared rounds before it runs dry.
        with tempfile.TemporaryDirectory() as tmp:
            text = _chain_text(8)
            self._spurious(replay_hits=False)
            decide, _ = self._blocked_decide(
                tmp, text, [(Verdict.REACHABLE, "wit")])
            v, meta = decide(text, 8)
            self.assertIs(v, Verdict.RESOURCE_OUT)
            self.assertEqual(meta["capped"],
                             f"cegar rounds {CEGAR_MAX_ROUNDS}")
            self.assertEqual(meta["rounds"], CEGAR_MAX_ROUNDS)

    def test_wall_cap_inside_the_route_is_resource_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            decide, _ = self._blocked_decide(
                tmp, text, [(Verdict.RESOURCE_OUT, None)])
            v, meta = decide(text, 8)
            self.assertIs(v, Verdict.RESOURCE_OUT)
            self.assertIn("wall", meta["capped"])
            self.assertEqual(meta["spent_pairs"], ["btor2-havoc"])

    def test_reachable_only_after_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            self._spurious(replay_hits=True)
            decide, _ = self._blocked_decide(
                tmp, text, [(Verdict.REACHABLE, "wit")])
            v, meta = decide(text, 8)
            self.assertIs(v, Verdict.REACHABLE)
            self.assertTrue(meta["replay_confirms"])

    def test_probe_plays_a_single_havoc_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            decide, calls = self._blocked_decide(
                tmp, text, [(Verdict.UNREACHABLE, None)])
            v, meta = decide(text, 4)                    # below the k=8
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertTrue(meta["probe"])
            self.assertNotIn("rounds", meta)
            self.assertEqual(meta["spent_pairs"], ["btor2-havoc"])
            self.assertEqual(len(calls), 1)
            self.assertIn("havoc_", calls[0][0])
            self.assertNotIn("iv_", calls[0][0])


class TestMonitorsAndSeeds(unittest.TestCase):
    def test_range_monitors_are_two_sided(self):
        # The escape monitor is the only bad, and it is semantically
        # live: the decoy counter leaves [0, 4] within 8 steps and
        # stays inside [0, 200] — checked through the shared
        # interpreter, no solver in the loop.
        text = decoy_system(2)
        mon, monitored = range_monitors(text, {"c": (0, 4)})
        self.assertEqual(monitored, ["c"])
        bad_lines = [ln for ln in mon.splitlines()
                     if len(ln.split()) >= 2 and ln.split()[1] == "bad"]
        self.assertEqual(len(bad_lines), 1)              # source bad gone
        self.assertTrue(any(
            v == 1 for row in interpret(mon, {"steps": 8})
            for key, v in row.items() if key.startswith("bad")))
        mon_wide, _ = range_monitors(text, {"c": (0, 200)})
        self.assertFalse(any(
            v == 1 for row in interpret(mon_wide, {"steps": 8})
            for key, v in row.items() if key.startswith("bad")))

    def test_full_range_seed_is_dropped(self):
        # [0, 2^w − 1] is the havoc rung already: confining to it buys
        # nothing, so it never enters the interval pot.
        text = ("1 sort bitvec 1\n2 sort bitvec 8\n"
                "3 state 1 x\n4 state 2 c\n")
        adv = {"interval_seeds": {"x": [0, 1], "c": [0, 2]}}
        self.assertEqual(usable_seeds(text, adv), {"c": (0, 2)})


class TestWiredIteration(unittest.TestCase):
    def test_engine_interval_iteration_end_to_end(self):
        from gurdy.solvers.native_btor2 import find_btormc

        if not find_btormc():
            self.skipTest("btormc absent")
        with tempfile.TemporaryDirectory() as tmp:
            bench = _bench(tmp, {"misses": decoy_system(2, bad_at=200)})
            work = os.path.join(tmp, "work")
            rec = run_iteration(bench, work, k=12, probe=False,
                                engine="interval", cache_dir=os.path.join(
                                    tmp, "cache"))
            self.assertEqual(rec["caps"]["engine"], "native+interval")
            self.assertEqual(rec["caps"]["cegar_max_rounds"],
                             CEGAR_MAX_ROUNDS)
            self.assertIn("decide_wall_s", rec["caps"])
            self.assertEqual(rec["verdicts"]["misses"]["verdict"],
                             "unreachable")
            self.assertTrue(rec["saturation"]["saturated"])


if __name__ == "__main__":
    unittest.main()
