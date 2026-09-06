"""Frames that do not align (KERNEL.md §2): a pair whose translation
turns one source frame into many target frames ships a stimulus map
and a bound map, both judged inside the square. On the toy registry:
the pair admits with both maps stamped; a stimulus map without its
inverse, a bound map without the claim it carries, a stimulus map
mutant that keeps the square, a bound map that agrees with itself but
not with the interpreters' depths, a bound map with no structure, and
a bound mutant that passes are each refused; the player carries an
ask forward and a claim back through the map, books a claim that ends
below the first source frame as a partial, brings a witness home
across the map, and never plays a route that revisits a language."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from kernel import driver, gate, registry
from kernel.tests import toy

CLAIMS_ZERO = '''\
import json
print(json.dumps({"kind": "all", "bound": 0, "cert": None}))
'''


class Misaligned(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.reg_root = toy.build(cls.tmp)
        toy.extend_misaligned(cls.reg_root)
        cls.reg = registry.load(cls.reg_root)
        cls.run_dir = os.path.join(cls.tmp, "run")
        toy.write_benchmark(cls.run_dir)
        cls.unsafe = toy.question(cls.run_dir, "q-unsafe")
        cls.safe = toy.question(cls.run_dir, "q-safe")
        cls.pair = cls.reg["pairs"]["toy--toy2x"]
        cls.search = cls.reg["searches"]["toy2x-search"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def _refused(self, manifest, files, needle: str):
        with self.assertRaises(gate.AdmissionError) as ctx:
            toy.admit(self.reg_root, manifest, files)
        self.assertIn(needle, str(ctx.exception))

    # -- the gate -----------------------------------------------------------

    def test_pair_admits_with_both_maps_stamped(self):
        stamp = self.pair["admission"]
        self.assertEqual(stamp["stimulus_map"], {"corpus": 2, "controls": 1})
        self.assertEqual(stamp["bound_map"], {"corpus": 2, "controls": 1})
        self.assertEqual(stamp["channels"]["prog"],
                         {"corpus": 2, "controls": 1})

    def test_stimulus_map_needs_its_inverse(self):
        m, files = toy.pair_x()
        m["id"], m["channels"] = "toy--toy2x-nowit", ["prog", "obs", "claim"]
        del files["lam_wit.py"], files["controls/wit_mutant_drop.py"]
        self._refused(m, files, "lam_in.py without wit")

    def test_bound_map_needs_the_claim_it_carries(self):
        m, files = toy.pair_x()
        m["id"], m["channels"] = "toy--toy2x-noclaim", ["prog", "wit", "obs"]
        self._refused(m, files, "lam_bound.py without claim")

    def test_stimulus_map_mutant_that_keeps_the_square_is_refused(self):
        m, files = toy.pair_x()
        m["id"] = "toy--toy2x-inblind"
        files["controls/in_mutant_same.py"] = toy.PAIR_X_LAM_IN.encode()
        self._refused(m, files, "passed the square and the stimulus round trip")

    def test_bound_map_that_disagrees_with_the_depths_is_refused(self):
        m, files = toy.pair_x()
        m["id"] = "toy--toy2x-scale"
        files["lam_bound.py"] = toy.PAIR_X_LAM_BOUND_MUTANT_SCALE.encode()
        del files["controls/bound_mutant_scale.py"]
        files["controls/bound_mutant_flat.py"] = toy.PAIR_X_LAM_BOUND_FLAT.encode()
        self._refused(m, files, "fires at source depth 1, mapped to 2, "
                                "but at target depth 3")

    def test_bound_map_without_structure_is_refused(self):
        m, files = toy.pair_x()
        m["id"] = "toy--toy2x-flat"
        files["lam_bound.py"] = toy.PAIR_X_LAM_BOUND_FLAT.encode()
        self._refused(m, files, "fwd not strictly monotone")

    def test_bound_mutant_that_passes_is_refused(self):
        m, files = toy.pair_x()
        m["id"] = "toy--toy2x-boundblind"
        files["controls/bound_mutant_same.py"] = toy.PAIR_X_LAM_BOUND.encode()
        self._refused(m, files, "passed the bound map's judgment")

    # -- the player ---------------------------------------------------------

    def _route(self, search, question):
        return driver.run_route(self.reg, [self.pair, search], question, 10.0)

    def test_ask_crosses_forward_and_the_claim_comes_back(self):
        # the search claims exactly the bound it is asked: an ask of 5
        # source frames becomes 11 target frames on the way out, and
        # the claim all(11) becomes all(5) on the way back
        rec = self._route(self.search, dict(self.safe, bound=5))
        self.assertEqual(rec["value"], {"kind": "all", "bound": 5,
                                        "cert": None})
        self.assertEqual(rec["grade"], "claimed")
        rec = self._route(self.search, self.safe)
        self.assertEqual(rec["value"]["bound"], "inf")

    def test_claim_below_the_first_source_frame_is_a_partial(self):
        search = toy.unstamped_search(self.tmp, "claims-zero", CLAIMS_ZERO,
                                      ["zero-g1"], language="toy2x")
        rec = self._route(search, self.safe)
        self.assertEqual(rec["value"]["kind"], "partial")
        self.assertIn("below the first source frame",
                      rec["value"]["progress"]["note"])
        self.assertEqual(rec["value"]["progress"]["claimed"]["bound"], 0)

    def test_witness_comes_home_across_the_map(self):
        rec = self._route(self.search, self.unsafe)
        self.assertEqual(rec["value"]["kind"], "witness")
        self.assertEqual(rec["value"]["payload"], {"x": 6})
        self.assertEqual((rec["grade"], rec["gap"]), ("certified", 0))
        self.assertEqual(rec["value"]["depth"], 1)   # measured at home

    def test_play_via_an_entry_plays_only_the_routes_it_opens(self):
        run_dir = os.path.join(self.tmp, "run-via")
        toy.write_benchmark(run_dir)
        driver.play(run_dir, self.reg_root, wall_s=10.0,
                    via={"toy2x-search"})
        log = [json.loads(line) for line in
               open(os.path.join(run_dir, "log.jsonl"), encoding="utf-8")]
        self.assertEqual(log[0]["via"], ["toy2x-search"])
        played = [r["route"] for r in log if "route" in r]
        self.assertEqual(played, [["toy--toy2x", "toy2x-search"]] * 2)
        with self.assertRaises(ValueError):
            driver.play(run_dir, self.reg_root, wall_s=10.0,
                        via={"no-such-entry"})

    def test_routes_never_revisit_a_language(self):
        def pair(src, tgt):
            return {"kind": "pair", "id": f"{src}--{tgt}", "src": src,
                    "tgt": tgt, "admission": {}}

        def search(lang):
            return {"kind": "search", "name": f"s-{lang}",
                    "language": lang, "admission": {}}
        reg = {"pairs": {p["id"]: p for p in (pair("a", "b"), pair("b", "a"),
                                              pair("b", "c"))},
               "searches": {s["name"]: s for s in (search("a"), search("b"),
                                                   search("c"))}}
        routes = [[e.get("id") or e["name"] for e in r]
                  for r in driver.enumerate_routes(reg, "a")]
        self.assertEqual(routes, [["s-a"], ["a--b", "s-b"],
                                  ["a--b", "b--c", "s-c"]])


if __name__ == "__main__":
    unittest.main()
