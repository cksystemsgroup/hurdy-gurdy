"""The btor2-havoc take-up player (the promotion of board entry
9c26710bf77f, played).

* Routing is the books' recommendation: a pin with a standing cost
  demand goes abstraction-first; everything else exact-first with the
  abstraction as the fallback on a spent verdict.
* CEGAR verdicts map onto the loop's currency: ``unreachable``
  transfers on the direction, ``reachable`` only after source replay,
  a spent round or wall budget is ``resource-out`` with the cap cited,
  a spurious counterexample at the exact cone stays ``unknown``.
* Probes (a call below the iteration's k) play a single abstraction
  round — the curve measures the route's first leg.
* Gated on btormc: the wired ``--engine havoc`` iteration end-to-end.
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
import havoc_player  # noqa: E402
from abstraction_bench import decoy_system  # noqa: E402
from frontier_loop import run_iteration  # noqa: E402
from havoc_player import (CEGAR_MAX_ROUNDS, blocked_hashes,  # noqa: E402
                          make_decide)


def _chain_text(depth: int = 8) -> str:
    """A chain s0 <- s1 <- … <- s_{depth-1}: every state in the cone
    (free set empty), ladder farthest-first — the refinement-budget
    fixture."""
    lines = ["1 sort bitvec 1", "2 sort bitvec 8", "3 zero 2", "4 one 2"]
    nid = 5
    sids = []
    for i in range(depth):
        lines.append(f"{nid} state 2 s{i}")
        sids.append(nid)
        nid += 1
    for sid in sids:
        lines.append(f"{nid} init 2 {sid} 3")
        nid += 1
    for i, sid in enumerate(sids[:-1]):
        lines.append(f"{nid} next 2 {sid} {sids[i + 1]}")
        nid += 1
    lines.append(f"{nid} next 2 {sids[-1]} 4")
    nid += 1
    lines.append(f"{nid} constd 2 200")
    c200 = nid
    nid += 1
    lines.append(f"{nid} eq 1 {sids[0]} {c200}")
    eq = nid
    nid += 1
    lines.append(f"{nid} bad {eq}")
    return "\n".join(lines) + "\n"


def _bench(tmp: str, texts: dict[str, str],
           suite: str = "toy-havoc") -> Benchmark:
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


class TestRouting(unittest.TestCase):
    def test_standing_demand_goes_abstraction_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            native, calls = _recording([(Verdict.UNREACHABLE, None)])
            decide = make_decide(bench, books, k=8, native=native)
            v, meta = decide(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["pair"], "btor2-havoc")
            self.assertEqual(meta["transfers"], "over")
            self.assertEqual(meta["rounds"], 1)
            # one call, and it decided the ABSTRACTION, not the source
            self.assertEqual(len(calls), 1)
            self.assertIn("havoc_", calls[0][0])

    def test_unblocked_goes_exact_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"easy": text})
            books = _books(tmp, bench.suite, [])
            native, calls = _recording([(Verdict.REACHABLE, "wit")])
            decide = make_decide(bench, books, k=8, native=native)
            v, meta = decide(text, 8)
            self.assertIs(v, Verdict.REACHABLE)
            self.assertEqual(meta, {"engine": "btormc"})
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], text)

    def test_spent_exact_falls_back_to_abstraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"newly-hard": text})
            books = _books(tmp, bench.suite, [])
            native, calls = _recording([(Verdict.RESOURCE_OUT, None),
                                        (Verdict.UNREACHABLE, None)])
            decide = make_decide(bench, books, k=8, native=native)
            v, meta = decide(text, 8)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertEqual(meta["transfers"], "over")
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0][0], text)          # the spent exact
            self.assertIn("havoc_", calls[1][0])         # then the route

    def test_blocked_hashes_selects_the_cited_pins(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = _bench(tmp, {"a": decoy_system(2),
                                 "b": _chain_text()})
            books = _books(tmp, bench.suite, ["b"])
            hashes = blocked_hashes(bench, books)
            (b,) = [i for i in bench.instances if i.name == "b"]
            self.assertEqual(hashes, {b.sha256})


class TestVerdictMapping(unittest.TestCase):
    def _spurious(self, replay_hits: bool):
        self._saved = havoc_player._source_replay_hits_bad
        havoc_player._source_replay_hits_bad = (
            lambda _t, _w, _k: replay_hits)
        self.addCleanup(
            lambda: setattr(havoc_player, "_source_replay_hits_bad",
                            self._saved))

    def test_reachable_only_after_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            self._spurious(replay_hits=True)
            native, _ = _recording([(Verdict.REACHABLE, "wit")])
            v, meta = make_decide(bench, books, k=8, native=native)(text, 8)
            self.assertIs(v, Verdict.REACHABLE)
            self.assertTrue(meta["replay_confirms"])

    def test_spurious_at_exact_cone_stays_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)   # ladder ['c']: one refinement rung
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            self._spurious(replay_hits=False)
            native, _ = _recording([(Verdict.REACHABLE, "wit")])
            v, meta = make_decide(bench, books, k=8, native=native)(text, 8)
            self.assertIs(v, Verdict.UNKNOWN)
            self.assertEqual(meta["note"], "spurious-at-exact-cone")
            self.assertGreaterEqual(meta["spurious"], 1)

    def test_round_limit_is_resource_out_with_the_cap_cited(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = _chain_text(8)    # prefix of 4: the budget binds
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            self._spurious(replay_hits=False)
            native, _ = _recording([(Verdict.REACHABLE, "wit")])
            v, meta = make_decide(bench, books, k=8, native=native)(text, 8)
            self.assertIs(v, Verdict.RESOURCE_OUT)
            self.assertEqual(meta["capped"],
                             f"cegar rounds {CEGAR_MAX_ROUNDS}")
            self.assertEqual(meta["rounds"], CEGAR_MAX_ROUNDS)

    def test_wall_cap_inside_the_route_is_resource_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            native, _ = _recording([(Verdict.RESOURCE_OUT, None)])
            v, meta = make_decide(bench, books, k=8, native=native)(text, 8)
            self.assertIs(v, Verdict.RESOURCE_OUT)
            self.assertIn("wall", meta["capped"])

    def test_probe_plays_a_single_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = decoy_system(2)
            bench = _bench(tmp, {"hard": text})
            books = _books(tmp, bench.suite, ["hard"])
            native, calls = _recording([(Verdict.UNREACHABLE, None)])
            v, meta = make_decide(bench, books, k=8, native=native)(text, 4)
            self.assertIs(v, Verdict.UNREACHABLE)
            self.assertTrue(meta["probe"])
            self.assertNotIn("rounds", meta)
            self.assertEqual(len(calls), 1)
            self.assertIn("havoc_", calls[0][0])


class TestWiredIteration(unittest.TestCase):
    def test_engine_havoc_iteration_end_to_end(self):
        from gurdy.solvers.native_btor2 import find_btormc

        if not find_btormc():
            self.skipTest("btormc absent")
        with tempfile.TemporaryDirectory() as tmp:
            bench = _bench(tmp, {"misses": decoy_system(2, bad_at=200)})
            work = os.path.join(tmp, "work")
            rec = run_iteration(bench, work, k=12, probe=False,
                                engine="havoc", cache_dir=os.path.join(
                                    tmp, "cache"))
            self.assertEqual(rec["caps"]["engine"], "native+havoc")
            self.assertEqual(rec["caps"]["cegar_max_rounds"],
                             CEGAR_MAX_ROUNDS)
            self.assertIn("decide_wall_s", rec["caps"])
            self.assertEqual(rec["verdicts"]["misses"]["verdict"],
                             "unreachable")
            self.assertTrue(rec["saturation"]["saturated"])


if __name__ == "__main__":
    unittest.main()
