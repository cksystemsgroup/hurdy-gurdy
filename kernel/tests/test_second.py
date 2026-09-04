"""The second lineage of the kernel (KERNEL.md §9): ``kernel/second``
is generated from the specification and the data alone, never from
this kernel's source, and must agree with it byte-for-byte on the
base, the board, and the graph of every pinned run — the accelerator
discipline applied to the kernel itself."""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from kernel import results

SECOND = os.path.join("kernel", "second")
_ESCAPE = re.compile(r"^\s*(?:from\s+kernel(?!\.second\b)|import\s+kernel(?!\.second\b)"
                     r"|from\s+\.\.)")


def _run(module: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", module, *args],
                          capture_output=True, timeout=600)


def two_domain_registry(tmp: str) -> str:
    """A registry holding one admitted language and two admitted
    domains rooted at it — the base must name both anchors."""
    from kernel import registry
    root = os.path.join(tmp, "two")
    shutil.copytree(os.path.join("registry", "domains"),
                    os.path.join(root, "domains"))
    lang = sorted(d for d in os.listdir(os.path.join("registry", "languages"))
                  if d.startswith("btor2"))[-1]
    shutil.copytree(os.path.join("registry", "languages", lang),
                    os.path.join(root, "languages", lang))
    entry = registry.register(root, {"kind": "domain", "name": "hardware-2",
                                     "root": "btor2",
                                     "anchors": ["a second anchor set"]}, {})
    registry.stamp_admission(entry, {"checked": "domain", "anchors": 1})
    return root


def corner_run(tmp: str) -> str:
    """Write the synthetic run described in the test above; questions
    live at ``c`` and routes name real registry entries, so the graph
    draws real edges in every style."""
    import hashlib
    run = os.path.join(tmp, "corner")
    os.makedirs(run)
    qs = []
    for i, (qid, mode, bound) in enumerate((
            ("a-partial", "exists", "inf"), ("b-plain", "forall", 50),
            ("c-contra", "exists", "inf"), ("d-corrob", "exists", "inf"),
            ("e-nolineage", "forall", "inf"), ("f-unplayed", "exists", 10),
            ("g-ledger", "forall", 100), ("h-checked", "forall", "inf"),
            ("i-wit-vs-inf", "exists", "inf"), ("j-int-spent", "forall", 7),
            ("k-judge-only", "exists", "inf"), ("l-two-contras", "exists", 10),
            ("m-zero-spent", "forall", 30), ("n-unicode", "exists", 5))):
        data = f"int main(void) {{ return {i}; }}\n".encode()
        with open(os.path.join(run, f"{qid}.c"), "wb") as fh:
            fh.write(data)
        qs.append({"id": qid, "language": "c", "program": f"{qid}.c",
                   "sha256": hashlib.sha256(data).hexdigest(), "mode": mode,
                   "observable": "bad", "bound": bound})
    json.dump({"name": "corner", "domain": "software", "questions": qs},
              open(os.path.join(run, "benchmark.json"), "w"), indent=1)
    r1, r2 = ["c--btor2", "btor2-bmc"], ["c--riscv", "riscv--btor2", "btor2-ind"]

    def rec(qid, value, grade="", gap=None, trust=None, route=r1,
            lineage=None, budget=None, **extra):
        out = {"question": qid, "route": route, "value": value,
               "grade": grade, "gap": gap, "trust": trust or []}
        if lineage is not None:
            out["lineage"] = lineage
        if budget is not None:
            out["budget"] = budget
        out.update(extra)
        return out

    wit = lambda d: {"kind": "witness", "payload": {"x": d}, "depth": d}
    all_ = lambda b, cert=None: {"kind": "all", "bound": b, "cert": cert}
    log = [
        {"event": "play", "iteration": 0, "caps": {"wall_s": 5.0}},
        rec("a-partial", {"kind": "partial", "progress": {
            "note": "budget spent", "bound_reached": 12, "evals": 3}},
            budget={"wall_s": 5.0, "spent_s": 3}, lineage=["p"]),
        rec("b-plain", {"kind": "partial", "progress": {}}, lineage=["p"]),
        rec("b-plain", all_(20), "claimed", None, ["s", "t"], lineage=["s", "t"],
            budget={"wall_s": 5.0, "spent_s": 1.25}),
        rec("c-contra", all_("inf", {"schema": "induction", "payload": 1}),
            "certified", 0, ["j"], lineage=["y"],
            budget={"wall_s": 5.0, "spent_s": 2.0}),
        rec("c-contra", wit(3), "certified", 0, ["j"], lineage=["x"],
            budget={"wall_s": 5.0, "spent_s": 0.5}),
        rec("d-corrob", wit(2), "certified", 0, ["j"], lineage=["a", "z"],
            budget={"wall_s": 5.0, "spent_s": 0.1}),
        rec("d-corrob", wit(2), "certified", 0, ["j"], route=r2,
            lineage=["b"], budget={"wall_s": 5.0, "spent_s": 0.2}),
        rec("d-corrob", wit(5), "certified", 0, ["j"]),
        rec("e-nolineage", all_("inf"), "claimed", None, ["s"]),
        rec("e-nolineage", all_("inf"), "claimed", None, ["s"], route=r2,
            lineage=["q"]),
        rec("g-ledger", all_(40), "claimed", None, ["s"], lineage=["s"],
            budget={"wall_s": 5.0, "spent_s": 0.0},
            ledger={"B_bits": 64, "S_bits_min": 3.5}),
        rec("g-ledger", all_(60), "claimed", None, ["s"], lineage=["s"],
            route=r2, budget={"wall_s": 5.0, "spent_s": 2.0},
            ledger={"B_bits": 96.5, "S_bits_min": 7.25}),
        rec("g-ledger", {"kind": "partial", "progress": {"note": "n"}},
            ledger={"S_bits_min": 9}, budget={"wall_s": 5.0, "spent_s": 1.0}),
        rec("h-checked", all_("inf", {"schema": "induction", "payload": 2}),
            "checked", 1, ["k", "s"], lineage=["k", "s"],
            budget={"wall_s": 5.0, "spent_s": 4.0},
            ledger={"B_bits": "inf"}),
        rec("h-checked", all_("inf"), "claimed", None, ["k", "s", "u"],
            lineage=["k", "s", "u"]),
        rec("i-wit-vs-inf", wit(1), "certified", 0, ["j"], lineage=["m"],
            budget={"wall_s": 5.0, "spent_s": 0.3}),
        rec("i-wit-vs-inf", all_("inf", {"schema": "clauses", "payload": 3}),
            "certified", 0, ["j"], lineage=["n"],
            budget={"wall_s": 5.0, "spent_s": 1.0}),
        rec("j-int-spent", all_(7), "claimed", None, ["s"], lineage=["s"],
            budget={"wall_s": 5, "spent_s": 2}),
        # a graded result resting on nothing but its judge (a language
        # that declares no lineage): the trust cell says so
        rec("k-judge-only", wit(4), "certified", 0, [], lineage=["w"],
            budget={"wall_s": 5.0, "spent_s": 0.7}),
        # two universals covering one witness, one numeric, one not;
        # and one that does not cover it
        rec("l-two-contras", wit(6), "certified", 0, ["j"], lineage=["x"],
            budget={"wall_s": 5.0, "spent_s": 0.4}),
        rec("l-two-contras", all_(10), "claimed", None, ["s"], lineage=["y"]),
        rec("l-two-contras", all_("inf"), "claimed", None, ["s"], route=r2,
            lineage=["z"]),
        rec("l-two-contras", all_(5), "claimed", None, ["s"], lineage=["y"]),
        # the record that cleared the most bits spent nothing
        rec("m-zero-spent", all_(30), "claimed", None, ["s"], lineage=["s"],
            budget={"wall_s": 5.0, "spent_s": 0.0}, ledger={"B_bits": 128}),
        rec("m-zero-spent", all_(10), "claimed", None, ["s"], lineage=["s"],
            route=r2, budget={"wall_s": 5.0, "spent_s": 1.0},
            ledger={"B_bits": 32}),
        # a note carrying non-ASCII text
        rec("n-unicode", {"kind": "partial", "progress": {
            "note": "état: needle — S ≥ 12 bits", "bound_reached": 2}},
            budget={"wall_s": 5.0, "spent_s": 1.5}, lineage=["p"]),
        rec("not-a-question", wit(1), "certified", 0),
        {"question": "a-partial", "route": r1, "note": "no value here"},
        {"event": "regrade"},
        {"event": "contradiction", "question": "c-contra"},
    ]
    with open(os.path.join(run, "log.jsonl"), "w", encoding="utf-8") as fh:
        for r in log:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    return run


@unittest.skipUnless(os.path.isfile(os.path.join(SECOND, "driver.py")),
                     "kernel/second is not in the tree")
class SecondLineage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = sorted(d for d in glob.glob("runs/*")
                          if os.path.isfile(os.path.join(d, "benchmark.json")))

    def test_shares_no_source_with_the_first_kernel(self):
        for path in glob.glob(os.path.join(SECOND, "**", "*.py"),
                              recursive=True):
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    self.assertIsNone(_ESCAPE.match(line),
                                      f"{path}:{lineno}: {line.strip()}")
        self.assertTrue(os.path.isfile(os.path.join(SECOND, "README.md")))

    def test_base_agrees(self):
        first = _run("kernel.driver", "base")
        second = _run("kernel.second.driver", "base")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)

    def test_board_and_graph_agree_on_every_run(self):
        for run in self.runs:
            with self.subTest(run=run):
                bench = results.load_benchmark(
                    os.path.join(run, "benchmark.json"))
                log = results.load(os.path.join(run, "log.jsonl"))
                board = _run("kernel.second.driver", "report", run)
                graph = _run("kernel.second.driver", "graph", run)
                self.assertEqual(board.returncode, 0, board.stderr)
                self.assertEqual(graph.returncode, 0, graph.stderr)
                self.assertEqual(board.stdout.decode("utf-8"),
                                 results.report(bench, log))
                first = _run("kernel.driver", "graph", run)
                self.assertEqual(graph.stdout, first.stdout)

    def test_agree_on_the_corners_no_pinned_run_exercises(self):
        """A synthetic run whose log holds what the four pinned runs
        do not: a partial as best (with and without a note), an int
        and a missing spent, a contradiction, a corroborated verdict,
        a settled record without lineage beside one with, a witness
        beside an unbounded certified claim, ledger rows at every edge
        (zero spent, ``inf``, a float), an unplayed question, and
        records the log must ignore."""
        tmp = tempfile.mkdtemp()
        try:
            run = corner_run(tmp)
            bench = results.load_benchmark(os.path.join(run, "benchmark.json"))
            log = results.load(os.path.join(run, "log.jsonl"))
            board = _run("kernel.second.driver", "report", run)
            graph = _run("kernel.second.driver", "graph", run)
            self.assertEqual(board.returncode, 0, board.stderr)
            self.assertEqual(graph.returncode, 0, graph.stderr)
            self.assertEqual(board.stdout.decode("utf-8"),
                             results.report(bench, log))
            first = _run("kernel.driver", "graph", run)
            self.assertEqual(graph.stdout, first.stdout)
            # and the empty registry: the base the kernel ships with
            empty = os.path.join(tmp, "empty")
            os.makedirs(empty)
            self.assertEqual(_run("kernel.second.driver", "base",
                                  "--registry", empty).stdout,
                             _run("kernel.driver", "base",
                                  "--registry", empty).stdout)
            # and a language anchored by two domains
            two = two_domain_registry(tmp)
            first = _run("kernel.driver", "base", "--registry", two)
            second = _run("kernel.second.driver", "base", "--registry", two)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.stdout, first.stdout)
        finally:
            shutil.rmtree(tmp)

    def test_refuses_changed_bytes_too(self):
        tmp = tempfile.mkdtemp()
        try:
            shutil.copytree(os.path.join("registry", "domains"),
                            os.path.join(tmp, "domains"))
            ok = _run("kernel.second.driver", "base", "--registry", tmp)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            with open(os.path.join(tmp, "domains", "hardware", "x"), "w") as fh:
                fh.write("changed\n")
            bad = _run("kernel.second.driver", "base", "--registry", tmp)
            self.assertNotEqual(bad.returncode, 0)
            os.remove(os.path.join(tmp, "domains", "hardware", "x"))
            mpath = os.path.join(tmp, "domains", "hardware", "manifest.json")
            m = json.load(open(mpath, encoding="utf-8"))
            del m["admission"]["tree"]
            json.dump(m, open(mpath, "w", encoding="utf-8"))
            bad = _run("kernel.second.driver", "base", "--registry", tmp)
            self.assertNotEqual(bad.returncode, 0)
        finally:
            shutil.rmtree(tmp)
