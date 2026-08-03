"""Scoping the c-riscv path against a pinned SV-COMP suite
(tools/scope_svcomp.py — the FRONTIER.md §5 second-act prerequisite).

* The source census is mechanical: ``__VERIFIER_nondet_*`` suffixes
  deduped and sorted, plain ``long`` counted apart from ``long long``
  (the ILP32/lp64-divergent construct), undefined-reference symbols
  parsed unique and in order.
* The scoping shim stubs exactly the referenced nondet signatures in
  its own translation unit (plus the anchor runtime); an unmapped
  suffix gets no stub and is reported, never guessed.
* Gap typing is path-ordered and honest: an upstream failure
  short-circuits (its row carries one binding gap), a clean path
  still carries the harness gaps — ``harness.property`` universally
  (the pair lowers ``pc_eq`` now, but no harness yet picks a task's
  sound anchor), ``harness.nondet`` when the
  task reads nondet, ``pin.data-model`` only when the ILP32 label
  meets detected width-divergent evidence.
* With the pinned toolchain present, a mini SV-COMP-shaped task walks
  the real path — compile, shim link, riscv-btor2 hub — with all
  three pc anchors surviving into the symbol table, a float task
  surfaces the soft-float libgcc demand at the link, and a ``dir:``
  corpus drives ``scope_bench`` end to end through ``core`` fetch.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest

from gurdy.core.benchmark import Benchmark
from gurdy.pairs.c_riscv.translate import find_gcc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir,
                                "tools"))
from scope_svcomp import (ANCHOR_SYMBOLS, compile_probe, gaps_for,  # noqa: E402
                          hub_probe, nondet_types, parse_undefined,
                          plain_long_uses, scope_bench, shim_for)

MINI = b"""
extern void __assert_fail(const char *, const char *, unsigned, const char *);
extern int __VERIFIER_nondet_int(void);
void reach_error(void) { __assert_fail("0", "mini.c", 3, "reach_error"); }
int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x > 5 && x < 3) reach_error();
  return 0;
}
"""


class TestCensus(unittest.TestCase):
    def test_nondet_extraction_dedup_sorted(self):
        src = ("int a = __VERIFIER_nondet_int(); "
               "unsigned b = __VERIFIER_nondet_uint (); "
               "int c = __VERIFIER_nondet_int();")
        self.assertEqual(nondet_types(src), ["int", "uint"])
        self.assertEqual(nondet_types("int main(void){return 0;}"), [])

    def test_plain_long_apart_from_long_long(self):
        self.assertEqual(plain_long_uses("long x; unsigned long y;"), 2)
        self.assertEqual(plain_long_uses("long long x;"), 0)
        self.assertEqual(plain_long_uses("unsigned long long x; long y;"), 1)
        self.assertEqual(plain_long_uses("belong; longs;"), 0)

    def test_shim_stubs_exactly_the_referenced_signatures(self):
        shim, unmapped = shim_for(["int", "ulong"])
        self.assertIn("int __VERIFIER_nondet_int(void)", shim)
        self.assertIn("unsigned long __VERIFIER_nondet_ulong(void)", shim)
        self.assertIn("__assert_fail", shim)
        self.assertNotIn("__VERIFIER_nondet_char", shim)
        self.assertEqual(unmapped, [])

    def test_unmapped_suffix_reported_not_guessed(self):
        shim, unmapped = shim_for(["widget"])
        self.assertEqual(unmapped, ["widget"])
        self.assertNotIn("widget", shim)

    def test_parse_undefined_unique_in_order(self):
        err = ("task.o: in function `main':\n"
               "prog.c:(.text+0x8): undefined reference to `__mulsf3'\n"
               "prog.c:(.text+0x18): undefined reference to `foo'\n"
               "prog.c:(.text+0x20): undefined reference to `__mulsf3'\n")
        self.assertEqual(parse_undefined(err), ["__mulsf3", "foo"])

    def test_gaps_path_order_short_circuits(self):
        self.assertEqual(gaps_for({"fetched": False}), ["fetch.offline"])
        self.assertEqual(gaps_for({"fetched": True, "front_ok": False}),
                         ["front.error"])
        row = {"fetched": True, "front_ok": True, "link_ok": False,
               "unresolved": ["__mulsf3"]}
        self.assertEqual(gaps_for(row), ["link.unresolved:__mulsf3"])
        row = {"fetched": True, "front_ok": True, "link_ok": True,
               "hub_ok": False, "unsupported": "riscv-btor2: opcode=0x07"}
        self.assertEqual(gaps_for(row),
                         ["hub.unsupported:riscv-btor2: opcode=0x07"])

    def test_harness_gaps_on_a_clean_path(self):
        clean = {"fetched": True, "front_ok": True, "link_ok": True,
                 "hub_ok": True, "meta": {"data_model": "ILP32"},
                 "nondet_types": [], "plain_long_uses": 0}
        self.assertEqual(gaps_for(clean), ["harness.property"])
        self.assertEqual(gaps_for({**clean, "nondet_types": ["int"]}),
                         ["harness.property", "harness.nondet"])
        # width-divergent evidence + the ILP32 label -> pin.data-model
        self.assertEqual(gaps_for({**clean, "nondet_types": ["long"]}),
                         ["harness.property", "harness.nondet",
                          "pin.data-model"])
        self.assertEqual(gaps_for({**clean, "plain_long_uses": 2}),
                         ["harness.property", "pin.data-model"])
        # no ILP32 label -> the proxy does not fire
        self.assertEqual(gaps_for({**clean, "meta": {}, "plain_long_uses": 2}),
                         ["harness.property"])

    def test_scope_bench_offline_is_typed_not_fatal(self):
        bench = Benchmark(suite="s", source="gitlab:g/p@c", instances=(
            Benchmark.from_json(json.dumps({
                "suite": "s", "source": "gitlab:g/p@c", "instances": [{
                    "name": "t", "path": "t.c", "sha256": "0" * 64,
                    "question": {"program": "t", "shape": "reachability",
                                 "source": "c"}}]})).instances))
        report = scope_bench(bench, gcc="/bin/echo",
                             fetcher=lambda b, n, cache_dir=None: None)
        self.assertEqual(report["rows"][0]["gaps"], ["fetch.offline"])
        self.assertEqual(report["aggregate"]["fetched"], 0)
        self.assertEqual(report["aggregate"]["answerable_today"], 0)
        self.assertEqual(report["aggregate"]["gap_census"],
                         {"fetch.offline": 1})


@unittest.skipUnless(find_gcc(), "riscv64-unknown-elf-gcc not installed")
class TestProbes(unittest.TestCase):
    def test_mini_task_walks_the_real_path(self):
        probe = compile_probe(MINI, ".c", find_gcc(), ["int"])
        elf = probe.pop("elf")
        self.assertTrue(probe["front_ok"] and probe["link_ok"])
        self.assertEqual(probe["unresolved"], [])
        h = hub_probe(elf)
        self.assertTrue(h["hub_ok"])
        self.assertGreater(h["btor2_lines"], 0)
        # every pc anchor survives into the linked symbol table; the
        # shim's own (__assert_fail, abort) live in a separate TU, so
        # calls to them cannot be inlined away under the pinned flags.
        self.assertEqual(h["anchors"], list(ANCHOR_SYMBOLS))

    def test_float_task_surfaces_softfloat_libgcc_demand(self):
        src = (b"float f(float a){return a*2.5f;}"
               b"int main(void){return f(1.0f)>0;}")
        probe = compile_probe(src, ".c", find_gcc(), [])
        self.assertTrue(probe["front_ok"])
        self.assertFalse(probe["link_ok"])
        self.assertIn("__mulsf3", probe["unresolved"])

    def test_unmapped_nondet_surfaces_at_the_link(self):
        src = (b"extern int __VERIFIER_nondet_widget(void);"
               b"int main(void){return __VERIFIER_nondet_widget();}")
        probe = compile_probe(src, ".c", find_gcc(),
                              nondet_types(src.decode()))
        self.assertEqual(probe["nondet_unmapped"], ["widget"])
        self.assertFalse(probe["link_ok"])
        self.assertIn("__VERIFIER_nondet_widget", probe["unresolved"])

    def test_dir_corpus_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "mini.c"), "wb") as f:
                f.write(MINI)
            bench = Benchmark.from_json(json.dumps({
                "suite": "scope-test", "source": f"dir:{d}", "instances": [{
                    "name": "mini", "path": "mini.c",
                    "sha256": hashlib.sha256(MINI).hexdigest(),
                    "expected": "unreachable",
                    "meta": {"data_model": "ILP32",
                             "property": "unreach-call"},
                    "question": {"program": "mini",
                                 "shape": "reachability", "source": "c"}}]}))
            report = scope_bench(bench, gcc=find_gcc())
        row = report["rows"][0]
        self.assertTrue(row["fetched"] and row["front_ok"]
                        and row["link_ok"] and row["hub_ok"])
        self.assertEqual(row["nondet_types"], ["int"])
        self.assertEqual(row["gaps"],
                         ["harness.property", "harness.nondet"])
        agg = report["aggregate"]
        self.assertEqual((agg["fetched"], agg["hub_ok"],
                          agg["answerable_today"]), (1, 1, 0))
        self.assertEqual(agg["nondet_census"], {"int": 1})
        self.assertEqual(agg["gap_census"],
                         {"harness.nondet": 1, "harness.property": 1})


if __name__ == "__main__":
    unittest.main()
