"""The result order (KERNEL.md §5, §9), checked against the model the
Lean development proves (``kernel/mechanization/Kernel/Key.lean``):
the key is ``(level, bound, grade, gap)``; the order is strict; the
best over an append-only log ratchets; once settled, always settled;
at a fixed level and bound, grades only move up and the gap never
grows; among equal keys the latest wins. The records here are random,
because the properties hold for every record, not only the ones the
driver would write."""

from __future__ import annotations

import random
import unittest

from kernel import results

_BOUNDS = ["inf", 0, 3, 5, 10, 20, 50]


def rand_question(rng: random.Random) -> dict:
    return {"id": "q", "language": "toy", "mode": rng.choice(
        ["exists", "forall"]), "observable": "bad",
        "bound": rng.choice(_BOUNDS)}


def rand_record(rng: random.Random, n: int, wild: bool = False) -> dict:
    kind = rng.choice(["witness", "all", "partial"])
    if kind == "witness":
        value = {"kind": "witness", "payload": {}, "depth": rng.randint(0, 30)}
        grade, gap = "certified", 0
    elif kind == "all":
        value = {"kind": "all", "bound": rng.choice(_BOUNDS), "cert": None}
        grade = rng.choice(["claimed", "checked", "certified"])
        gap = {"claimed": None, "checked": rng.randint(1, 3),
               "certified": 0}[grade]
    else:
        progress = {}
        if rng.random() < 0.7:
            progress["bound_reached"] = rng.randint(0, 40)
        value = {"kind": "partial", "progress": progress}
        grade, gap = "", None
    if wild:
        grade = rng.choice(["", "claimed", "checked", "certified"])
        gap = rng.choice([None, 0, 1, 2, 3])
    return {"question": "q", "n": n, "value": value, "grade": grade,
            "gap": gap, "route": ["r"]}


def rand_log(rng: random.Random, size: int, start: int = 0) -> list[dict]:
    return [rand_record(rng, start + i, wild=rng.random() < 0.3)
            for i in range(size)]


class OrderIsStrict(unittest.TestCase):
    def test_irreflexive_asymmetric_transitive(self):
        rng = random.Random(1)
        for _ in range(3000):
            q = rand_question(rng)
            a, b, c = (rand_record(rng, i, wild=True) for i in range(3))
            self.assertFalse(results.better(q, a, a))
            if results.better(q, a, b):
                self.assertFalse(results.better(q, b, a))
                if results.better(q, b, c):
                    self.assertTrue(results.better(q, a, c))

    def test_total_comparability(self):
        rng = random.Random(2)
        for _ in range(3000):
            q = rand_question(rng)
            a, b = rand_record(rng, 0, wild=True), rand_record(rng, 1, wild=True)
            self.assertTrue(results.better(q, a, b) or results.better(q, b, a)
                            or results.key(q, a) == results.key(q, b))


class Ratchet(unittest.TestCase):
    def _bench(self, q):
        return {"name": "t", "questions": [q]}

    def test_best_is_monotone_under_append(self):
        rng = random.Random(3)
        for _ in range(500):
            q = rand_question(rng)
            log = rand_log(rng, rng.randint(0, 6))
            more = rand_log(rng, rng.randint(0, 6), start=100)
            before = results.best(self._bench(q), log).get("q")
            after = results.best(self._bench(q), log + more).get("q")
            if before is None:
                continue
            self.assertIsNotNone(after)
            self.assertFalse(results.better(q, before, after),
                             "appending lost ground")

    def test_once_settled_always_settled(self):
        rng = random.Random(4)
        for _ in range(500):
            q = rand_question(rng)
            log = rand_log(rng, rng.randint(1, 6))
            more = rand_log(rng, rng.randint(0, 6), start=100)
            bench = self._bench(q)
            if results.frontier(bench, log):
                continue
            self.assertEqual(results.frontier(bench, log + more), [])

    def test_same_level_and_bound_only_moves_up(self):
        rng = random.Random(5)
        seen = 0
        for _ in range(3000):
            q = rand_question(rng)
            log = rand_log(rng, rng.randint(1, 5))
            more = rand_log(rng, rng.randint(1, 5), start=100)
            bench = self._bench(q)
            before = results.best(bench, log)["q"]
            after = results.best(bench, log + more)["q"]
            kb, ka = results.key(q, before), results.key(q, after)
            if kb[:2] != ka[:2]:
                continue
            seen += 1
            # grade higher, or grade equal and the gap not worse
            # (-gap larger); `None` is encoded below every finite gap
            self.assertTrue(ka[2] > kb[2] or (ka[2] == kb[2]
                                              and ka[3] >= kb[3]))
        self.assertGreater(seen, 100)

    def test_latest_wins_among_equal_keys(self):
        q = {"id": "q", "language": "toy", "mode": "forall",
             "observable": "bad", "bound": 10}
        a = {"question": "q", "n": 1, "value": {"kind": "all", "bound": 5},
             "grade": "claimed", "gap": None}
        b = dict(a, n=2)
        bench = {"name": "t", "questions": [q]}
        self.assertEqual(results.best(bench, [a, b])["q"]["n"], 2)
        self.assertEqual(results.best(bench, [b, a])["q"]["n"], 1)
        # but a strictly better incumbent survives a weaker newcomer
        c = dict(a, grade="checked", gap=1, n=3)
        self.assertEqual(results.best(bench, [c, b])["q"]["n"], 3)


class GradesAreGeometry(unittest.TestCase):
    q = {"id": "q", "language": "toy", "mode": "forall",
         "observable": "bad", "bound": "inf"}

    def _all(self, grade, gap, n=0):
        return {"question": "q", "n": n,
                "value": {"kind": "all", "bound": "inf"},
                "grade": grade, "gap": gap}

    def test_no_check_sits_below_every_finite_gap(self):
        for g in (0, 1, 5, 1000):
            self.assertTrue(results.better(
                self.q, self._all("checked", g), self._all("checked", None)))

    def test_smaller_gap_is_strictly_better(self):
        self.assertTrue(results.better(
            self.q, self._all("checked", 1), self._all("checked", 2)))
        self.assertFalse(results.better(
            self.q, self._all("checked", 2), self._all("checked", 1)))

    def test_grade_beats_gap(self):
        # a certified result (gap 0 by construction) beats any checked
        self.assertTrue(results.better(
            self.q, self._all("certified", 0), self._all("checked", 1)))
        # and a rung up beats a smaller gap at the lower rung
        self.assertTrue(results.better(
            self.q, self._all("checked", 3), self._all("claimed", None)))

    def test_ladder_is_strict(self):
        rungs = ["", "claimed", "checked", "certified"]
        for lo, hi in zip(rungs, rungs[1:]):
            self.assertLess(results.GRADES[lo], results.GRADES[hi])

    def test_levels_follow_the_spec(self):
        ask10 = dict(self.q, bound=10)
        settled_w = {"question": "q", "value": {"kind": "witness",
                     "payload": {}, "depth": 3}, "grade": "certified",
                     "gap": 0}
        covering = {"question": "q", "value": {"kind": "all", "bound": 10},
                    "grade": "claimed", "gap": None}
        below = {"question": "q", "value": {"kind": "all", "bound": 9},
                 "grade": "certified", "gap": 0}
        partial = {"question": "q", "value": {"kind": "partial",
                   "progress": {}}, "grade": "", "gap": None}
        reached = {"question": "q", "value": {"kind": "partial",
                   "progress": {"bound_reached": 4}}, "grade": "",
                   "gap": None}
        self.assertEqual(results.key(ask10, settled_w)[0], 2)
        self.assertEqual(results.key(ask10, covering)[0], 2)
        self.assertEqual(results.key(ask10, below)[0], 1)
        self.assertEqual(results.key(ask10, partial)[0], 0)
        # a witness settles either mode; a covering claim outranks a
        # certified claim below the ask; any bound reached beats none
        self.assertTrue(results.settled(dict(ask10, mode="exists"),
                                        settled_w["value"]))
        self.assertTrue(results.better(ask10, covering, below))
        self.assertTrue(results.better(ask10, reached, partial))

    def test_cap_and_covers(self):
        self.assertEqual(results.cap("inf", []), "inf")
        self.assertEqual(results.cap("inf", [5, "inf"]), 5)
        self.assertEqual(results.cap(3, ["inf", 7]), 3)
        self.assertTrue(results.covers("inf", 10))
        self.assertTrue(results.covers(10, 10))
        self.assertFalse(results.covers(9, 10))
        self.assertFalse(results.covers(5, "inf"))


class Flags(unittest.TestCase):
    q = {"id": "q", "language": "toy", "mode": "exists",
         "observable": "bad", "bound": "inf"}
    bench = {"name": "t", "questions": [q]}

    def _wit(self, lineage, depth=2):
        return {"question": "q", "value": {"kind": "witness", "payload": {},
                "depth": depth}, "grade": "certified", "gap": 0,
                "lineage": lineage}

    def test_corroborated_needs_disjoint_descent(self):
        shared = [self._wit(["a", "x"]), self._wit(["b", "x"])]
        self.assertEqual(results.corroborated(self.bench, shared), set())
        disjoint = [self._wit(["a"]), self._wit(["b"])]
        self.assertEqual(results.corroborated(self.bench, disjoint), {"q"})
        # a record without a lineage never counts
        anon = [self._wit(["a"]), dict(self._wit([]), lineage=[])]
        self.assertEqual(results.corroborated(self.bench, anon), set())

    def test_contradiction_is_recorded_never_resolved(self):
        wit = self._wit(["a"], depth=7)
        covering = {"question": "q", "value": {"kind": "all", "bound": 10},
                    "grade": "claimed", "gap": None, "lineage": ["b"]}
        short = dict(covering, value={"kind": "all", "bound": 5})
        found = results.contradictions(self.bench, [wit, covering, short])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["universal"]["value"]["bound"], 10)
        # the witness stands: it is still the best
        self.assertEqual(results.best(self.bench, [covering, wit])["q"], wit)
