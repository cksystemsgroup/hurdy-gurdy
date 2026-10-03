"""Fault injection, falsified on the toy registry (``kernel/faults``).

The harness is an instrument, so it is held to what it must be able
to tell apart. A mutant is one fault and parses; a sample is the same
sample every time. At the gate, a judge whose comparison is inverted
is refused by its own vectors and a fault that changes no judged byte
survives — and is not counted refused. At play, with the gate taken
away, a search that answers the wrong way round leaves a wrong record
that is ``claimed`` and blamed, a translator that drops a field loses
the answer, and no mutant of any transport leaves a wrong record
``certified``."""

from __future__ import annotations

import ast
import json
import os
import shutil
import tempfile
import unittest

from kernel import driver, registry
from kernel.faults import admission, harness, mutate, play
from kernel.tests import toy


def _records(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def _target(reg: dict, entry: str, file: str) -> dict:
    return next(t for t in harness.targets(reg)
                if (t["entry"], t["file"]) == (entry, file))


class Mutants(unittest.TestCase):
    SOURCES = (toy.TOY_INTERP, toy.TOY_CHECK, toy.PAIR_T, toy.SEARCH_SOLVE)

    def test_a_mutant_is_one_fault_and_parses(self):
        for source in self.SOURCES:
            same = mutate.identity(source)
            self.assertEqual(mutate.identity(same), same)
            for site in mutate.sites(source):
                text = mutate.mutant(source, site)
                ast.parse(text)
                self.assertEqual(mutate.identity(text), text)

    def test_a_sample_is_reproducible_and_never_the_identity(self):
        for source in self.SOURCES:
            first = mutate.sample(source, "x", 5, seed=1)
            self.assertEqual(first, mutate.sample(source, "x", 5, seed=1))
            self.assertLessEqual(len(first), 5)
            for site in first:
                self.assertNotEqual(mutate.mutant(source, site),
                                    mutate.identity(source))

    def test_annotations_and_text_are_left_alone(self):
        source = 'def f(x: int | None) -> int:\n    return "a" + "b"\n'
        self.assertEqual(mutate.sites(source), [])


class OnTheToyRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.reg_root = toy.build(cls.tmp)
        toy.admit_cert_revision(cls.reg_root)
        cls.reg = registry.load(cls.reg_root)
        cls.runs = os.path.join(cls.tmp, "runs")
        run_dir = os.path.join(cls.runs, "toy-bench")
        toy.write_benchmark(run_dir)
        driver.play(run_dir, cls.reg_root, wall_s=20.0)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _gate(self, entry: str, file: str) -> list[dict]:
        out = os.path.join(self.tmp, f"gate-{file}.jsonl")
        admission.gate_target(self.reg_root, self.reg,
                              _target(self.reg, entry, file), 1000, 1, out)
        return _records(out)

    def _play(self, entry: str, file: str) -> list[dict]:
        out = os.path.join(self.tmp, f"play-{file}.jsonl")
        play.play_target(self.reg_root, self.reg,
                         _target(self.reg, entry, file), 1000, 1, out,
                         self.runs)
        return [p for r in _records(out) for p in r.get("plays", [])]

    def test_the_gate_refuses_an_inverted_judge_and_not_a_silent_fault(self):
        records = self._gate("languages/toy", "interp.py")
        head, mutants = records[0], records[1:]
        self.assertEqual(head["tiers"], ["own", "dependents"])
        self.assertEqual(head["executed"], head["statements"])
        self.assertEqual(len(mutants), head["sampled"])
        by = {r["detail"]: r for r in mutants}
        inverted = by["> -> <= (operator 0)"]
        self.assertEqual((inverted["outcome"], inverted["tier"],
                          inverted["how"]), ("refused", "own", "check"))
        # ``sort_keys=True`` flipped: two keys already in order, the
        # same bytes — nothing to refuse, and nothing refused
        silent = by["True -> False"]
        self.assertEqual((silent["outcome"], silent["cover"]),
                         ("survived", True))

    def test_a_checker_that_accepts_everything_dies_on_its_controls(self):
        records = self._gate("languages/toy", "evidence/threshold-proof/"
                                              "check.py")[1:]
        self.assertTrue(any(r["outcome"] == "refused" and r["how"] == "check"
                            for r in records))
        table = admission.report([os.path.join(
            self.tmp, "gate-evidence/threshold-proof/check.py.jsonl")])
        self.assertIn("languages/toy/evidence/threshold-proof/check.py",
                      table)

    def test_no_transport_mutant_forges(self):
        wrong = []
        for entry, file in (("searches/toy2-search", "solve.py"),
                            ("pairs/toy--toy2@2", "T.py"),
                            ("pairs/toy--toy2@2", "lam_wit.py"),
                            ("pairs/toy--toy2@2", "lam_cert.py")):
            plays = self._play(entry, file)
            self.assertTrue(any(p["verdict"] == "lost" for p in plays),
                            f"{entry}/{file}: no mutant cost anything")
            wrong += [p for p in plays if p["verdict"].startswith("wrong")]
        # the search answering the wrong way round is among them
        self.assertTrue(wrong)
        for p in wrong:
            self.assertNotEqual(p["verdict"], "wrong-certified")
            self.assertTrue(p["blamed"], p)


if __name__ == "__main__":
    unittest.main()
