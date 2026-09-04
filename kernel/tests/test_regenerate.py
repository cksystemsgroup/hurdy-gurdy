"""The honesty rule (KERNEL.md §11): the board and the graph of every
pinned run regenerate byte-identically from the log, and the trusted
base prints the same list twice."""

from __future__ import annotations

import glob
import os
import unittest

from kernel import driver, registry, results


class Regenerate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = registry.load("registry")
        cls.runs = sorted(d for d in glob.glob("runs/*")
                          if os.path.isfile(os.path.join(d, "benchmark.json")))
        assert cls.runs, "no pinned runs"

    def test_board_and_graph_are_pure_functions_of_the_log(self):
        for run in self.runs:
            with self.subTest(run=run):
                bench = results.load_benchmark(
                    os.path.join(run, "benchmark.json"))
                log = results.load(os.path.join(run, "log.jsonl"))
                board = results.report(bench, log)
                graph = results.dot(self.reg, bench, log)
                self.assertEqual(board, results.report(bench, log))
                self.assertEqual(graph, results.dot(self.reg, bench, log))
                with open(os.path.join(run, "frontier.md"),
                          encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), board)
                with open(os.path.join(run, "frontier.dot"),
                          encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), graph)

    def test_base_is_a_list(self):
        text = driver.base("registry")
        self.assertEqual(text, driver.base("registry"))
        for name, m in self.reg["languages"].items():
            if "admission" in m:
                self.assertIn(f"`{name}", text)
        self.assertIn("judges only", text)
