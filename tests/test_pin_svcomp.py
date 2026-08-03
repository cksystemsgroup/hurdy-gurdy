"""Authoring a pinned SV-COMP benchmark from task-definition families
(the second benchmark act; FRONTIER.md §5, BENCHMARKS.md §4). No
network anywhere: the fetcher is injected.

* The strict task-definition parser handles exactly the block-style
  shape the suite uses — comments, quoted and bare scalars, booleans,
  list-valued ``input_files`` — and aborts on everything else (flow
  collections, tabs, unknown top-level keys, unterminated quotes):
  it can decline to author, never mislabel. Where PyYAML is
  installed, every parse is cross-checked against it.
* Selection is typed: no ``unreach-call`` property or a multi-file
  task is a *counted skip*, an unreach task without a verdict is
  pinned unlabeled, and ``expected_verdict`` maps true→unreachable /
  false→reachable.
* The instance pins the program bytes; the task definition rides in
  ``meta`` with its own sha256 — the label's provenance is pinned too.
* Authoring is all-or-nothing (empty family, overlapping families,
  fetch failure, API error reply, parser disagreement all raise), the
  GitLab tree listing paginates, and the emitted suite round-trips
  through ``core/benchmark.py::fetch`` with the ``gitlab:`` source.
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
from pin_svcomp import (list_tasks, parse_task, pin,  # noqa: E402
                        program_path, select_unreach)

PROJECT, COMMIT = "example/group/mirror", "c0ffee"

TASK_REACH = """\
format_version: '2.0'

# old file name: add_false-unreach-call.i
input_files: 'add-1.i'

properties:
  - property_file: ../properties/no-overflow.prp
    expected_verdict: true
  - property_file: ../properties/unreach-call.prp
    expected_verdict: false
  - property_file: ../properties/coverage-branches.prp

options:
  language: C
  data_model: ILP32
"""

TASK_UNREACH = """\
format_version: '2.0'
input_files: 'safe.i'
properties:
  - property_file: ../properties/unreach-call.prp
    expected_verdict: true
options:
  language: C
  data_model: LP64
"""

TASK_UNLABELED = """\
format_version: '2.0'
input_files: 'open.i'
properties:
  - property_file: ../properties/unreach-call.prp
options:
  language: C
"""

TASK_TERMINATION = """\
format_version: '2.0'
input_files: 'loop.i'
properties:
  - property_file: ../properties/termination.prp
    expected_verdict: true
options:
  language: C
"""

TASK_MULTIFILE = """\
format_version: '2.0'
input_files:
  - main.c
  - lib.c
properties:
  - property_file: ../properties/unreach-call.prp
    expected_verdict: true
options:
  language: C
"""

TREE = {
    "c/fam/add-1.yml": TASK_REACH.encode(),
    "c/fam/add-1.i": b"int main() { /* reach */ }\n",
    "c/fam/safe.yml": TASK_UNREACH.encode(),
    "c/fam/safe.i": b"int main() { /* safe */ }\n",
    "c/fam/open.yml": TASK_UNLABELED.encode(),
    "c/fam/open.i": b"int main() { /* open */ }\n",
    "c/fam/loop.yml": TASK_TERMINATION.encode(),
    "c/fam/loop.i": b"int main() { /* loop */ }\n",
    "c/other/multi.yml": TASK_MULTIFILE.encode(),
    "c/other/README.md": b"not a task\n",
    "c/other/safe.yml": TASK_UNREACH.encode(),
    "c/other/safe.i": b"int main() { /* other safe */ }\n",
}


def _fetcher(tree=TREE, fail=frozenset()):
    """Serves the paginated GitLab tree API and raw blobs from
    ``tree``."""
    def fetch_bytes(url: str) -> bytes:
        if "/api/v4/" in url:
            q = dict(kv.split("=") for kv in url.split("?")[1].split("&"))
            under = q["path"].rstrip("/") + "/"
            blobs = [{"path": p, "type": "blob"}
                     for p in sorted(tree) if p.startswith(under)]
            per, page = int(q["per_page"]), int(q["page"])
            return json.dumps(blobs[(page - 1) * per:page * per]).encode()
        path = url.split(f"{COMMIT}/", 1)[1]
        if path in fail:
            raise RuntimeError(f"fetch failed: {url}")
        return tree[path]
    return fetch_bytes


class TestParser(unittest.TestCase):
    def test_parses_the_suite_shape(self):
        task = parse_task(TASK_REACH)
        self.assertEqual(task["format_version"], "2.0")
        self.assertEqual(task["input_files"], ["add-1.i"])
        self.assertEqual(task["properties"], [
            {"property_file": "../properties/no-overflow.prp",
             "expected_verdict": True},
            {"property_file": "../properties/unreach-call.prp",
             "expected_verdict": False},
            {"property_file": "../properties/coverage-branches.prp"},
        ])
        self.assertEqual(task["options"],
                         {"language": "C", "data_model": "ILP32"})

    def test_list_valued_input_files(self):
        self.assertEqual(parse_task(TASK_MULTIFILE)["input_files"],
                         ["main.c", "lib.c"])

    def test_strictness_aborts(self):
        for bad in (
            "format_version: '2.0'\ninput_files: [a.c]\n",   # flow list
            "format_version: '2.0'\n\tinput_files: 'a.c'\n",  # tab
            "wat: 1\ninput_files: 'a.c'\n",       # unknown top-level
            "input_files: 'a.c\n",                # unterminated quote
            "format_version: '2.0'\n",            # no input_files
            "input_files: 'a.c'\nproperties:\n"
            "    expected_verdict: true\n",       # entry before '- '
        ):
            with self.assertRaises(ValueError, msg=bad):
                parse_task(bad)

    def test_agrees_with_pyyaml_where_installed(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML not installed")
        from pin_svcomp import _crosscheck
        for text in (TASK_REACH, TASK_UNREACH, TASK_UNLABELED,
                     TASK_TERMINATION, TASK_MULTIFILE):
            _crosscheck(text, parse_task(text), where="t")


class TestSelection(unittest.TestCase):
    def test_verdict_mapping(self):
        self.assertEqual(select_unreach(parse_task(TASK_REACH), "t"),
                         ("reachable", None))
        self.assertEqual(select_unreach(parse_task(TASK_UNREACH), "t"),
                         ("unreachable", None))

    def test_unlabeled_unreach_is_selected_unlabeled(self):
        self.assertEqual(select_unreach(parse_task(TASK_UNLABELED), "t"),
                         (None, None))

    def test_typed_skips(self):
        self.assertEqual(
            select_unreach(parse_task(TASK_TERMINATION), "t"),
            (None, "no-unreach-call-property"))
        self.assertEqual(
            select_unreach(parse_task(TASK_MULTIFILE), "t"),
            (None, "multi-file-task"))

    def test_program_path_stays_inside_the_repo(self):
        self.assertEqual(program_path("c/fam/x.yml", "x.i"), "c/fam/x.i")
        self.assertEqual(program_path("c/fam/x.yml", "../shared/x.i"),
                         "c/shared/x.i")
        with self.assertRaises(ValueError):
            program_path("c/x.yml", "../../etc/passwd")


class TestListing(unittest.TestCase):
    def test_paginates(self):
        fams = list_tasks(PROJECT, COMMIT, ["c/fam"], _fetcher(),
                          per_page=2)
        self.assertEqual(fams, [("c/fam", [
            "c/fam/add-1.yml", "c/fam/loop.yml", "c/fam/open.yml",
            "c/fam/safe.yml"])])

    def test_empty_family_aborts(self):
        with self.assertRaises(ValueError):
            list_tasks(PROJECT, COMMIT, ["c/no-such"], _fetcher())

    def test_overlapping_families_abort(self):
        with self.assertRaises(ValueError):
            list_tasks(PROJECT, COMMIT, ["c", "c/fam"], _fetcher())

    def test_api_error_reply_aborts(self):
        def err(url: str) -> bytes:
            return json.dumps({"message": "404 not found"}).encode()
        with self.assertRaises(RuntimeError):
            list_tasks(PROJECT, COMMIT, ["c/fam"], err)


def _pin(**kw):
    defaults = dict(suite="toy-svcomp", project=PROJECT, commit=COMMIT,
                    families=["c/fam", "c/other"],
                    fetch_bytes=_fetcher())
    defaults.update(kw)
    return pin(**defaults)


class TestPin(unittest.TestCase):
    def test_assembles_the_suite_with_typed_skips(self):
        bench, skips = _pin()
        self.assertEqual(bench.source, f"gitlab:{PROJECT}@{COMMIT}")
        # 6 tasks listed: 4 selected, termination + multi-file skipped;
        # colliding basenames parent-qualified.
        self.assertEqual([i.name for i in bench.instances],
                         ["add-1", "open", "fam-safe", "other-safe"])
        self.assertEqual(skips, {"no-unreach-call-property": 1,
                                 "multi-file-task": 1})
        by_name = {i.name: i for i in bench.instances}
        add = by_name["add-1"]
        self.assertEqual(add.path, "c/fam/add-1.i")
        self.assertEqual(add.sha256, hashlib.sha256(
            TREE["c/fam/add-1.i"]).hexdigest())
        self.assertEqual(add.expected, "reachable")
        self.assertEqual(add.meta["task"], "c/fam/add-1.yml")
        self.assertEqual(add.meta["task_sha256"], hashlib.sha256(
            TREE["c/fam/add-1.yml"]).hexdigest())
        self.assertEqual(add.meta["data_model"], "ILP32")
        self.assertEqual(add.meta["family"], "fam")
        self.assertEqual((add.question.source, add.question.shape,
                          add.question.program),
                         ("c", "reachability", "add-1"))
        self.assertEqual(by_name["fam-safe"].expected, "unreachable")
        self.assertIsNone(by_name["open"].expected)
        self.assertNotIn("data_model", by_name["open"].meta)

    def test_fetch_failure_aborts(self):
        with self.assertRaises(RuntimeError):
            _pin(fetch_bytes=_fetcher(fail={"c/fam/safe.i"}))

    def test_all_tasks_skipped_aborts(self):
        tree = {"c/t/loop.yml": TASK_TERMINATION.encode()}
        with self.assertRaises(ValueError):
            _pin(families=["c/t"], fetch_bytes=_fetcher(tree=tree))

    def test_deterministic_and_json_round_trip(self):
        (a, _), (b, _) = _pin(), _pin()
        self.assertEqual(a.to_json(), b.to_json())
        back = Benchmark.from_json(a.to_json())
        self.assertEqual(back.to_json(), a.to_json())

    def test_cache_replays_through_the_loops_ingestion(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench, _ = _pin(cache_dir=tmp)
            # gitlab: source, but every read is a verified cache hit —
            # no network in this test, so a miss would return None.
            for inst in bench.instances:
                data = fetch(bench, inst.name, cache_dir=tmp)
                self.assertIsNotNone(data)


if __name__ == "__main__":
    unittest.main()
