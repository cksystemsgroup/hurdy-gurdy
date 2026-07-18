"""Authoring a pinned benchmark from mirror families (the widening
step of the pre-registered protocol; FRONTIER.md §5, BENCHMARKS.md
§4). No network anywhere: the fetcher is injected.

* Names are deterministic and parent-qualified only where basenames
  collide — every member of a colliding group is qualified.
* A pin inherits the hand-pinned slice's labels where paths overlap
  and refuses bytes that disagree with a standing pin.
* Authoring is all-or-nothing: a fetch failure, an empty family, an
  overlapping family, or a bad ``--labels`` entry raises before any
  Benchmark exists.
* The emitted suite round-trips: ``to_json``/``from_json`` identical,
  and ``core/benchmark.py::fetch`` replays the authoring cache with
  the pin verified.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest

from gurdy.core.benchmark import Benchmark, fetch

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir,
                                "tools"))
from pin_family import (assign_names, family_label,  # noqa: E402
                        list_blobs, pin, select)

REPO, COMMIT = "example/mirror", "c0ffee"

TREE = {
    "bv/2024/fam-a/loops/x.btor2": b"instance ax\n",
    "bv/2024/fam-a/locks/x.btor2": b"instance ax2\n",
    "bv/2024/fam-a/loops/y.btor2": b"instance ay\n",
    "bv/2019/fam-b/z.btor2": b"instance bz\n",
    "bv/2019/fam-b/README.md": b"not an instance\n",
}


def _fetcher(tree=TREE, fail=frozenset()):
    """Serves the git-tree listing and raw blobs from ``tree``."""
    def fetch_bytes(url: str) -> bytes:
        if "api.github.com" in url:
            return json.dumps({"tree": [
                {"path": p, "type": "blob"} for p in sorted(tree)]},
            ).encode()
        path = url.split(f"{COMMIT}/", 1)[1]
        if path in fail:
            raise RuntimeError(f"fetch failed: {url}")
        return tree[path]
    return fetch_bytes


class TestNaming(unittest.TestCase):
    def test_collisions_qualify_every_member(self):
        names = assign_names(["a/b/x.btor2", "a/c/x.btor2",
                              "a/c/y.btor2"])
        self.assertEqual(names, {"a/b/x.btor2": "b-x",
                                 "a/c/x.btor2": "c-x",
                                 "a/c/y.btor2": "y"})

    def test_family_label(self):
        self.assertEqual(family_label("bv/2024/sosylab"), "sosylab'24")
        self.assertEqual(family_label("bv/2019/beem"), "beem'19")
        self.assertEqual(family_label("local/corpus"), "corpus")


class TestSelect(unittest.TestCase):
    def test_only_btor2_under_prefix_sorted(self):
        picked = select(sorted(TREE), ["bv/2019/fam-b"])
        self.assertEqual(picked, [("bv/2019/fam-b",
                                   ["bv/2019/fam-b/z.btor2"])])

    def test_empty_family_aborts(self):
        with self.assertRaises(ValueError):
            select(sorted(TREE), ["bv/2024/no-such"])

    def test_overlapping_families_abort(self):
        with self.assertRaises(ValueError):
            select(sorted(TREE), ["bv/2024", "bv/2024/fam-a"])

    def test_truncated_listing_aborts(self):
        def truncated(url: str) -> bytes:
            return json.dumps({"tree": [], "truncated": True}).encode()
        with self.assertRaises(RuntimeError):
            list_blobs(REPO, COMMIT, truncated)


def _pin(**kw):
    defaults = dict(suite="toy-pin", repo=REPO, commit=COMMIT,
                    families=["bv/2024/fam-a", "bv/2019/fam-b"],
                    fetch_bytes=_fetcher(), known={})
    defaults.update(kw)
    return pin(**defaults)


class TestPin(unittest.TestCase):
    def test_assembles_the_suite(self):
        bench = _pin()
        self.assertEqual(bench.source, f"github:{REPO}@{COMMIT}")
        self.assertEqual(
            [i.name for i in bench.instances],
            ["z", "locks-x", "loops-x", "y"])
        by_name = {i.name: i for i in bench.instances}
        self.assertEqual(by_name["z"].meta["family"], "fam-b'19")
        self.assertEqual(by_name["y"].meta["family"], "fam-a'24")
        self.assertEqual(
            by_name["z"].sha256,
            hashlib.sha256(b"instance bz\n").hexdigest())
        self.assertIsNone(by_name["z"].expected)
        q = by_name["loops-x"].question
        self.assertEqual((q.source, q.shape, q.program),
                         ("btor2", "reachability", "loops-x"))

    def test_inherits_known_labels_and_checks_the_pin(self):
        digest = hashlib.sha256(b"instance bz\n").hexdigest()
        known = {"bv/2019/fam-b/z.btor2":
                 {"sha256": digest, "expected": "unreachable",
                  "note": "kept"}}
        bench = _pin(known=known)
        by_name = {i.name: i for i in bench.instances}
        self.assertEqual(by_name["z"].expected, "unreachable")
        self.assertEqual(by_name["z"].meta["note"], "kept")

    def test_standing_pin_mismatch_aborts(self):
        known = {"bv/2019/fam-b/z.btor2":
                 {"sha256": "0" * 64, "expected": "unreachable"}}
        with self.assertRaises(AssertionError):
            _pin(known=known)

    def test_fetch_failure_aborts(self):
        with self.assertRaises(RuntimeError):
            _pin(fetch_bytes=_fetcher(
                fail={"bv/2024/fam-a/loops/y.btor2"}))

    def test_labels_apply_and_guard(self):
        bench = _pin(labels={"z": "unreachable"})
        by_name = {i.name: i for i in bench.instances}
        self.assertEqual(by_name["z"].expected, "unreachable")
        with self.assertRaises(ValueError):
            _pin(labels={"no-such-instance": "unreachable"})
        digest = hashlib.sha256(b"instance bz\n").hexdigest()
        known = {"bv/2019/fam-b/z.btor2":
                 {"sha256": digest, "expected": "unreachable"}}
        with self.assertRaises(ValueError):
            _pin(known=known, labels={"z": "reachable"})

    def test_deterministic_and_json_round_trip(self):
        a, b = _pin(), _pin()
        self.assertEqual(a.to_json(), b.to_json())
        back = Benchmark.from_json(a.to_json())
        self.assertEqual(back.to_json(), a.to_json())

    def test_cache_replays_through_the_loops_ingestion(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = _pin(cache_dir=tmp)
            # github: source, but every read is a verified cache hit —
            # no network in this test, so a miss would return None.
            for inst in bench.instances:
                data = fetch(bench, inst.name, cache_dir=tmp)
                self.assertIsNotNone(data)


if __name__ == "__main__":
    unittest.main()
