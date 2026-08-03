"""tools/redischarge_campaign.py — the after-the-batch certificate
obligation: discovery of standing unbounded closures from a campaign's
``iterations.jsonl``, the generator-pool discipline (closers that
cannot print re-derive; walls are budgets, not retries), the typed
booking of every outcome, and — gated on the real engines — the
end-to-end run against a seeded one-instance campaign."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gurdy.solvers.certifaiger import find_certifaiger  # noqa: E402
from gurdy.solvers.inventory import available_smt_backends  # noqa: E402
from gurdy.solvers.pono_btor2 import find_pono  # noqa: E402
from tools.redischarge_campaign import (  # noqa: E402
    certify_closure,
    discover_closures,
    generator_pool,
    main,
)


def _iteration(i, verdicts):
    return {"iteration": i, "suite": "t", "verdicts": verdicts,
            "caps": {}, "decide_records": [], "saturation": {}}


UNBOUNDED = {"bounded": False, "claim": "unreachable-unbounded",
             "engine": "pono", "mode": "ind", "verdict": "unreachable",
             "wall_s": 74.0}
RESOURCE_OUT = {"bounded": True, "verdict": "resource-out",
                "engine": "avr+pono", "wall_s": 3000.0}


class TestDiscovery(unittest.TestCase):
    def test_standing_closure_survives_later_resource_out(self):
        cs = discover_closures([_iteration(3, {"a": UNBOUNDED}),
                                _iteration(5, {"a": RESOURCE_OUT})])
        self.assertEqual([c["instance"] for c in cs], ["a"])
        self.assertEqual(cs[0]["iteration"], 3)
        self.assertEqual(cs[0]["mode"], "ind")

    def test_latest_closing_iteration_wins(self):
        cs = discover_closures([
            _iteration(3, {"a": UNBOUNDED}),
            _iteration(4, {"a": {**UNBOUNDED, "wall_s": 85.9}})])
        self.assertEqual(cs[0]["iteration"], 4)
        self.assertEqual(cs[0]["wall_s"], 85.9)

    def test_bounded_verdicts_are_never_closures(self):
        cs = discover_closures([_iteration(0, {
            "a": {"bounded": True, "verdict": "unreachable",
                  "engine": "btormc"}})])
        self.assertEqual(cs, [])

    def test_contradiction_refuses(self):
        with self.assertRaises(ValueError):
            discover_closures([
                _iteration(3, {"a": UNBOUNDED}),
                _iteration(5, {"a": {"bounded": True, "verdict": "reachable",
                                     "engine": "pono"}})])

    def test_reachable_elsewhere_does_not_block(self):
        cs = discover_closures([_iteration(3, {
            "a": UNBOUNDED,
            "b": {"bounded": True, "verdict": "reachable",
                  "engine": "pono"}})])
        self.assertEqual([c["instance"] for c in cs], ["a"])


class TestGeneratorPool(unittest.TestCase):
    def test_printing_closer_leads_the_pool(self):
        pool, skipped = generator_pool(
            {"engine": "pono", "mode": "dar"}, ("ind", "ic3bits", "mbic3"))
        self.assertEqual(pool, ["dar", "ic3bits", "mbic3"])
        self.assertEqual(skipped, [])

    def test_non_printing_closer_is_typed_not_spent(self):
        pool, skipped = generator_pool(
            {"engine": "pono", "mode": "ind"}, ("ind", "ic3bits", "mbic3"))
        self.assertEqual(pool, ["ic3bits", "mbic3"])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["outcome"], "closer-cannot-print")

    def test_avr_closure_rederives_through_pono(self):
        pool, skipped = generator_pool(
            {"engine": "avr", "mode": "avr"}, ("ind", "ic3bits", "mbic3"))
        self.assertEqual(pool, ["ic3bits", "mbic3"])
        self.assertEqual(skipped, [])


# A tiny system with one unreachable bad (counter confined below 11 by
# its constraint) — the redischarge fixtures' shape, self-contained.
FIXTURE = """\
1 sort bitvec 4
2 zero 1
3 state 1 counter
4 init 1 3 2
5 one 1
6 add 1 3 5
7 next 1 3 6
8 constd 1 10
9 sort bitvec 1
10 ugt 9 3 8
11 bad 10
12 ulte 9 3 8
13 constraint 12
"""


def _seed_campaign(tmp, closure_mode="ic3bits"):
    """A one-instance campaign: pin file over a dir: source, iterations,
    empty books. Returns (pin_path, workdir, cache_dir)."""
    sha = hashlib.sha256(FIXTURE.encode()).hexdigest()
    corpus = os.path.join(tmp, "corpus")
    os.makedirs(corpus)
    with open(os.path.join(corpus, "probe.btor2"), "w") as f:
        f.write(FIXTURE)
    pin = {"suite": "t", "source": f"dir:{corpus}",
           "instances": [{"name": "probe", "path": "probe.btor2",
                          "sha256": sha,
                          "question": {"program": "probe",
                                       "shape": "reachability",
                                       "source": "btor2"}}]}
    pin_path = os.path.join(tmp, "t.json")
    with open(pin_path, "w") as f:
        json.dump(pin, f)
    cache = os.path.join(tmp, "cache")
    os.makedirs(cache)
    workdir = os.path.join(tmp, "wd")
    os.makedirs(workdir)
    with open(os.path.join(workdir, "iterations.jsonl"), "w") as f:
        f.write(json.dumps(_iteration(1, {"probe": {
            "bounded": False, "claim": "unreachable-unbounded",
            "engine": "pono", "mode": closure_mode,
            "verdict": "unreachable", "wall_s": 1.0}})) + "\n")
    open(os.path.join(workdir, "books.jsonl"), "w").close()
    return pin_path, workdir, cache


class TestBooking(unittest.TestCase):
    """The event shape, with the engines stubbed out — booking is the
    contract here, not proving."""

    def _run(self, tmp, **stubs):
        pin_path, workdir, cache = _seed_campaign(tmp)
        defaults = {
            "extract_invariant": mock.DEFAULT,
            "redischarge_invariant": mock.DEFAULT,
            "check_witness_circuit": mock.DEFAULT,
        }
        with mock.patch.multiple("tools.redischarge_campaign", **defaults) \
                as m:
            m["extract_invariant"].return_value = stubs.get(
                "invariant", "(bvule state3 #b1010)")
            smt = mock.Mock()
            smt.ok, smt.independent = stubs.get("smt_ok", True), True
            smt.engines = ["cvc5"] if smt.ok else []
            smt.refuted, smt.obligations = stubs.get("refuted", []), {
                "base": {"cvc5": "unreachable"}}
            m["redischarge_invariant"].return_value = smt
            m["check_witness_circuit"].return_value = (
                stubs.get("aiger_ok", True), {"checker": "x",
                                              "checker_exit": 0,
                                              "checker_output": "valid witness"})
            rc = main([pin_path, workdir, "--cache-dir", cache])
        self.assertEqual(rc, 0)
        with open(os.path.join(workdir, "books.jsonl")) as f:
            return [json.loads(ln) for ln in f]

    def test_certified_event_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = self._run(tmp)
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e["kind"], "certificate")
        self.assertEqual(e["key"],
                         hashlib.sha256(FIXTURE.encode()).hexdigest())
        self.assertEqual(e["claim"], "unreachable-unbounded")
        self.assertTrue(e["ok"])
        self.assertEqual(e["tier"], "proved")
        self.assertTrue(e["corroborated"])
        self.assertEqual(e["generator"], "ic3bits")
        self.assertIn("host", e)
        self.assertIn("ts", e)
        self.assertIn("btor2-smtlib:operator-mapping", e["tcb"])
        self.assertIn("kissat:sat", e["tcb"])
        self.assertEqual(e["closure"]["iteration"], 1)

    def test_one_route_still_certifies_uncorroborated(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = self._run(tmp, aiger_ok=False)
        e = events[0]
        self.assertTrue(e["ok"])
        self.assertFalse(e["corroborated"])
        self.assertNotIn("kissat:sat", e["tcb"])

    def test_no_invariant_books_typed_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = self._run(tmp, invariant=None)
        e = events[0]
        self.assertFalse(e["ok"])
        self.assertIsNone(e["tier"])
        self.assertIn("no-certificate", e["gap"])
        self.assertEqual([m["outcome"] for m in e["modes_spent"]],
                         ["no-invariant"] * len(e["modes_spent"]))

    def test_fetch_offline_books_typed_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            pin_path, workdir, cache = _seed_campaign(tmp)
            with mock.patch("tools.redischarge_campaign.fetch",
                            return_value=None):
                rc = main([pin_path, workdir, "--cache-dir", cache])
            self.assertEqual(rc, 0)
            with open(os.path.join(workdir, "books.jsonl")) as f:
                events = [json.loads(ln) for ln in f]
        self.assertEqual(events[0]["gap"], "fetch-offline")
        self.assertFalse(events[0]["ok"])

    def test_dry_run_books_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            pin_path, workdir, cache = _seed_campaign(tmp)
            rc = main([pin_path, workdir, "--cache-dir", cache, "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertEqual(
                os.path.getsize(os.path.join(workdir, "books.jsonl")), 0)


@unittest.skipUnless(find_pono() and available_smt_backends(),
                     "pono + an SMT backend required")
class TestEndToEnd(unittest.TestCase):
    """The real spine on the seeded one-instance campaign: extraction
    through the actual pono, both routes live (the checker route books
    its typed gap when certifaiger is absent)."""

    def test_certifies_seeded_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            pin_path, workdir, cache = _seed_campaign(tmp)
            rc = main([pin_path, workdir, "--cache-dir", cache,
                       "--wall", "120"])
            self.assertEqual(rc, 0)
            with open(os.path.join(workdir, "books.jsonl")) as f:
                events = [json.loads(ln) for ln in f]
        self.assertEqual(len(events), 1)
        e = events[0]
        smt = e["routes"]["invariant-redischarge"]
        self.assertTrue(smt["ok"], smt)
        self.assertTrue(e["ok"])
        self.assertIn("invariant", e)
        aig = e["routes"]["certifaiger"]
        if find_certifaiger():
            self.assertTrue(aig["ok"], aig)
            self.assertTrue(e["corroborated"])
        else:
            self.assertIn("checker-unavailable", aig.get("gap", ""))

    def test_ind_closure_rederives(self):
        # The Problem11_label26 shape: closed by ind, which cannot print
        # an invariant — the pool re-derives through ic3bits.
        with tempfile.TemporaryDirectory() as tmp:
            pin_path, workdir, cache = _seed_campaign(
                tmp, closure_mode="ind")
            rc = main([pin_path, workdir, "--cache-dir", cache,
                       "--wall", "120"])
            self.assertEqual(rc, 0)
            with open(os.path.join(workdir, "books.jsonl")) as f:
                e = json.loads(f.readline())
        self.assertTrue(e["ok"])
        self.assertEqual(e["modes_spent"][0]["outcome"],
                         "closer-cannot-print")
        self.assertNotEqual(e["generator"], "ind")


if __name__ == "__main__":
    unittest.main()
