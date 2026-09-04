"""The kernel cannot forge a result (KERNEL.md §4, §6, §9). On the toy
registry, the only way to *certified* is an interpreter run where the
question lives: a lying search, a broken carry-back, a bogus
certificate, and a route missing a channel each lose a grade and
never gain one; whatever a search writes about its own result is
ignored; and ``regrade`` lifts a stored proof to certified by check
time alone once the pair learns to carry certificates."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from kernel import driver, registry, results
from kernel.tests import toy

LIAR_WITNESS = '''\
import json
print(json.dumps({"kind": "witness", "payload": {"x": 0},
                  "grade": "certified", "gap": 0, "trust": []}))
'''

LIAR_BOGUS_CERT = '''\
import json, sys
prog = json.load(open(sys.argv[1]))
print(json.dumps({"kind": "all", "bound": "inf", "grade": "certified",
                  "cert": {"schema": "tm-proof",
                           "payload": {"m": 0, "t": 99}}}, sort_keys=True))
'''

LIAR_BARE_CLAIM = '''\
import json
print(json.dumps({"kind": "all", "bound": "inf", "cert": None,
                  "grade": "certified", "gap": 0}))
'''

LIAR_TRUE_NUMBERS = '''\
import json, sys
prog = json.load(open(sys.argv[1]))
print(json.dumps({"kind": "all", "bound": "inf",
                  "cert": {"schema": "tm-proof",
                           "payload": {"m": prog["m"], "t": prog["t"]}}},
                 sort_keys=True))
'''


class CannotForge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.reg_root = toy.build(cls.tmp)
        cls.reg = registry.load(cls.reg_root)
        cls.run_dir = os.path.join(cls.tmp, "run")
        toy.write_benchmark(cls.run_dir)
        cls.unsafe = toy.question(cls.run_dir, "q-unsafe")
        cls.safe = toy.question(cls.run_dir, "q-safe")
        cls.pair = cls.reg["pairs"]["toy--toy2"]
        cls.search = cls.reg["searches"]["toy2-search"]
        cls.toy_lineage = sorted(cls.reg["languages"]["toy"]["lineage"])
        cls.toy2_lineage = sorted(cls.reg["languages"]["toy2"]["lineage"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def _route(self, *parts):
        return driver.run_route(self.reg, list(parts[:-1]), parts[-1], 10.0)

    # -- honest evidence, graded by where it was judged ---------------------

    def test_witness_comes_home_and_replays_certified_gap_0(self):
        rec = self._route(self.pair, self.search, self.unsafe)
        self.assertEqual(rec["value"]["kind"], "witness")
        self.assertEqual(rec["value"]["payload"], {"x": 6})
        self.assertEqual((rec["grade"], rec["gap"]), ("certified", 0))
        # route-independence: the residual is the judge alone
        self.assertEqual(rec["trust"], self.toy_lineage)
        self.assertNotIn("toy2-search-g1", rec["trust"])

    def test_proof_discharged_one_hop_away_is_checked_gap_1(self):
        rec = self._route(self.pair, self.search, self.safe)
        self.assertEqual(rec["value"]["kind"], "all")
        self.assertEqual(rec["value"]["bound"], "inf")
        self.assertEqual((rec["grade"], rec["gap"]), ("checked", 1))
        self.assertEqual(rec["discharge"]["at"], "toy2")
        # the meet over the gap segment plus the judge: the pair and
        # toy2's judge, never the search
        self.assertEqual(rec["trust"], sorted(set(self.pair["lineage"])
                                              | set(self.toy2_lineage)))
        self.assertNotIn("toy2-search-g1", rec["trust"])

    def test_direct_route_certifies_where_the_question_lives(self):
        run2 = os.path.join(self.tmp, "run2")
        os.makedirs(run2, exist_ok=True)
        prog = toy._prog2(5, 3)
        with open(os.path.join(run2, "p.json"), "wb") as fh:
            fh.write(prog)
        import hashlib
        q = {"id": "q2", "language": "toy2", "program": "p.json",
             "sha256": hashlib.sha256(prog).hexdigest(), "mode": "forall",
             "observable": "fired", "bound": "inf"}
        json.dump({"name": "b2", "questions": [q]},
                  open(os.path.join(run2, "benchmark.json"), "w"))
        q = toy.question(run2, "q2")
        rec = self._route(self.search, q)
        self.assertEqual((rec["grade"], rec["gap"]), ("certified", 0))
        self.assertEqual(rec["trust"], self.toy2_lineage)

    # -- lies lose grades, never gain them ----------------------------------

    def test_lying_witness_never_becomes_a_result(self):
        liar = toy.unstamped_search(self.tmp, "liar-wit", LIAR_WITNESS,
                                    ["liar-g1"])
        rec = self._route(self.pair, liar, self.unsafe)
        self.assertEqual(rec["value"]["kind"], "partial")
        self.assertIn("witness did not come home", rec["value"]["progress"]["note"])
        self.assertEqual((rec["grade"], rec["gap"], rec["trust"]),
                         ("", None, []))
        # the search's own words about its grade never reach the record
        self.assertNotEqual(rec.get("grade"), "certified")

    def test_bogus_certificate_floors_at_claimed(self):
        liar = toy.unstamped_search(self.tmp, "liar-cert", LIAR_BOGUS_CERT,
                                    ["liar-g1"])
        rec = self._route(self.pair, liar, self.safe)
        self.assertEqual(rec["value"]["kind"], "all")
        self.assertEqual((rec["grade"], rec["gap"]), ("claimed", None))
        # nothing checked: the residual is the whole chain, liar included
        self.assertIn("liar-g1", rec["trust"])
        self.assertEqual(rec["trust"], rec["lineage"])

    def test_bare_claim_is_the_checkless_channel(self):
        liar = toy.unstamped_search(self.tmp, "liar-bare", LIAR_BARE_CLAIM,
                                    ["liar-g1"])
        rec = self._route(self.pair, liar, self.safe)
        self.assertEqual((rec["grade"], rec["gap"]), ("claimed", None))
        self.assertIn("liar-g1", rec["trust"])

    def test_true_numbers_on_an_unsafe_program_do_not_discharge(self):
        liar = toy.unstamped_search(self.tmp, "liar-numbers",
                                    LIAR_TRUE_NUMBERS, ["liar-g1"])
        rec = self._route(self.pair, liar, self.unsafe)
        self.assertEqual(rec["value"]["kind"], "all")
        self.assertEqual((rec["grade"], rec["gap"]), ("claimed", None))
        # and beside the honest witness, that claim is a contradiction
        honest = self._route(self.pair, self.search, self.unsafe)
        bench = results.load_benchmark(os.path.join(self.run_dir,
                                                    "benchmark.json"))
        found = results.contradictions(bench, [rec, honest])
        self.assertEqual(len(found), 1)
        self.assertEqual(results.best(bench, [rec, honest])["q-unsafe"],
                         honest)

    def test_broken_carry_back_only_loses_the_witness(self):
        broken_dir = os.path.join(self.tmp, "broken-pair")
        shutil.copytree(self.pair["_dir"], broken_dir)
        with open(os.path.join(broken_dir, "lam_wit.py"), "w") as fh:
            fh.write(toy.PAIR_LAM_WIT_MUTANT_DROP)
        broken = dict(self.pair, _dir=broken_dir)
        rec = self._route(broken, self.search, self.unsafe)
        self.assertEqual(rec["value"]["kind"], "partial")
        self.assertIn("did not replay", rec["value"]["progress"]["note"])
        # the target-level witness survives as evidence, not as a result
        self.assertEqual(rec["value"]["progress"]["witness"], {"x": 6})

    def test_missing_channel_is_a_partial_never_an_answer(self):
        noclaim = dict(self.pair, channels=["prog", "wit", "obs"])
        rec = self._route(noclaim, self.search, self.safe)
        self.assertEqual(rec["value"]["kind"], "partial")
        self.assertIn("no claim channel", rec["value"]["progress"]["note"])
        nowit = dict(self.pair, channels=["prog", "obs", "claim"])
        rec = self._route(nowit, self.search, self.unsafe)
        self.assertEqual(rec["value"]["kind"], "partial")
        self.assertIn("no wit channel", rec["value"]["progress"]["note"])

    def test_observable_not_kept_is_a_partial(self):
        blind = dict(self.pair, keeps=["depth"])
        rec = self._route(blind, self.search, self.unsafe)
        self.assertEqual(rec["value"]["kind"], "partial")
        self.assertIn("does not keep", rec["value"]["progress"]["note"])

    def test_no_route_books_an_open_partial(self):
        self.assertEqual(driver.enumerate_routes(
            {"pairs": {}, "searches": {}}, "toy"), [])


class RegradeLiftsWithoutResolving(unittest.TestCase):
    """The grade-raising replay (KERNEL.md §5), end to end: play, then
    admit a `cert` carry-back by revision, then regrade — the map
    re-graded without being re-solved."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.reg_root = toy.build(cls.tmp)
        cls.run_dir = os.path.join(cls.tmp, "run")
        cls.bench = toy.write_benchmark(cls.run_dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def _log(self):
        return results.load(os.path.join(self.run_dir, "log.jsonl"))

    def test_play_then_regrade(self):
        board = driver.play(self.run_dir, self.reg_root, wall_s=10.0)
        self.assertIn("2 of 2 settled; frontier holds 0.", board)
        before = self._log()
        bests = results.best(self.bench, before)
        self.assertEqual((bests["q-unsafe"]["grade"], bests["q-unsafe"]["gap"]),
                         ("certified", 0))
        self.assertEqual((bests["q-safe"]["grade"], bests["q-safe"]["gap"]),
                         ("checked", 1))
        self.assertEqual(results.frontier(self.bench, before), [])
        # the board and graph regenerate byte-identically
        self.assertEqual(driver.report(self.run_dir, self.reg_root), board)
        # a regrade with nothing new changes nothing on the board
        self.assertEqual(driver.regrade(self.run_dir, self.reg_root,
                                        wall_s=10.0), board)
        # the (b)-move: the pair learns to carry certificates home
        toy.admit_cert_revision(self.reg_root)
        driver.regrade(self.run_dir, self.reg_root, wall_s=10.0)
        after = self._log()
        bests = results.best(self.bench, after)
        self.assertEqual((bests["q-safe"]["grade"], bests["q-safe"]["gap"]),
                         ("certified", 0))
        self.assertTrue(bests["q-safe"].get("regrade"))
        self.assertEqual(bests["q-safe"]["value"],
                         results.best(self.bench, before)["q-safe"]["value"])
        self.assertEqual(bests["q-safe"]["revisions"], {"toy--toy2": 2})
        self.assertEqual(bests["q-safe"]["trust"],
                         sorted(registry.load(self.reg_root)["languages"]
                                ["toy"]["lineage"]))
        self.assertEqual(results.expanded(self.bench, after, before),
                         ["q-safe"])
        # the log only grew, and the old record is still there
        self.assertEqual(after[:len(before)], before)
