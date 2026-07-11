"""The coordinator merge queue (tools/merge_queue.py) — Phase 6 of the scaling
rollout (SCALING.md §6–§7). The engine is pure (plain dicts in, plan out), so
these tests are git-free.
"""

import importlib.util
import pathlib
import sys
import unittest


def _load():
    path = pathlib.Path(__file__).resolve().parent.parent / "tools" / "merge_queue.py"
    spec = importlib.util.spec_from_file_location("merge_queue", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["merge_queue"] = mod
    spec.loader.exec_module(mod)
    return mod


def _manifest(changed, pairs=(), langs=(), shared=False, protected=(),
              lane=None, errors=(), det=(), nc=()):
    return {
        "scope": {
            "changed_files": list(changed),
            "touched_pairs": list(pairs),
            "touched_languages": list(langs),
            "touches_shared_layer": shared,
            "touches_protected": list(protected),
        },
        "verdict": {
            "measurement_errors": list(errors),
            "determinism_failures": list(det),
            "negative_control_failures": list(nc),
            "shared_lane": lane,
            "shared_non_additive": [],
        },
    }


PAIRS = {
    "evm-btor2": {"source": "evm", "target": "btor2"},
    "riscv-btor2": {"source": "riscv", "target": "btor2"},
    "btor2-smtlib": {"source": "btor2", "target": "smtlib"},
}


class TestClassify(unittest.TestCase):
    def setUp(self):
        self.mq = _load()

    def cand(self, ref, **kw):
        return self.mq.Candidate.from_manifest(ref, _manifest(**kw),
                                               shared_change=kw.get("shared_change"))

    def test_independent_green_is_merge(self):
        c = self.mq.Candidate.from_manifest(
            "p", _manifest(["gurdy/pairs/evm_btor2/translate.py"], pairs=["evm-btor2"]))
        kind, _ = self.mq.classify_candidate(c)
        self.assertEqual(kind, self.mq.MERGE)

    def test_lane_a_shared_is_merge(self):
        c = self.mq.Candidate.from_manifest(
            "s", _manifest(["gurdy/languages/evm/interp.py"], langs=["evm"],
                           shared=True, lane="A"))
        kind, _ = self.mq.classify_candidate(c)
        self.assertEqual(kind, self.mq.MERGE)

    def test_lane_b_with_manifest_is_fan_out(self):
        c = self.mq.Candidate.from_manifest(
            "s", _manifest(["gurdy/languages/evm/interp.py"], langs=["evm"],
                           shared=True, lane="B"),
            shared_change={"symbol": "evm:_execute", "expect": {}})
        kind, _ = self.mq.classify_candidate(c)
        self.assertEqual(kind, self.mq.FAN_OUT)

    def test_lane_b_without_manifest_is_reject(self):
        c = self.mq.Candidate.from_manifest(
            "s", _manifest(["gurdy/languages/evm/interp.py"], langs=["evm"],
                           shared=True, lane="B"))
        kind, reason = self.mq.classify_candidate(c)
        self.assertEqual(kind, self.mq.REJECT)
        self.assertIn("shared-change manifest", reason)

    def test_protected_change_is_escalate(self):
        c = self.mq.Candidate.from_manifest(
            "s", _manifest(["gurdy/languages/evm/inventory.py"], langs=["evm"],
                           shared=True, protected=["gurdy/languages/evm/inventory.py"],
                           lane="A"))
        kind, _ = self.mq.classify_candidate(c)
        self.assertEqual(kind, self.mq.ESCALATE)

    def test_gate_red_is_reject(self):
        for kw in ({"errors": ["evm-btor2: boom"]},
                   {"det": ["evm-btor2"]},
                   {"nc": ["evm-btor2"]}):
            c = self.mq.Candidate.from_manifest(
                "p", _manifest(["gurdy/pairs/evm_btor2/translate.py"],
                               pairs=["evm-btor2"], **kw))
            kind, _ = self.mq.classify_candidate(c)
            self.assertEqual(kind, self.mq.REJECT, kw)


class TestOrdering(unittest.TestCase):
    def setUp(self):
        self.mq = _load()

    def _c(self, ref, changed, pairs=(), langs=(), shared=False):
        return self.mq.Candidate.from_manifest(
            ref, _manifest(changed, pairs=pairs, langs=langs, shared=shared))

    def test_shared_serialized_framework_before_interpreter(self):
        core = self._c("z-core", ["gurdy/core/oracle.py"], shared=True)
        lang = self._c("a-lang", ["gurdy/languages/evm/interp.py"], langs=["evm"],
                       shared=True)
        waves = self.mq.order_waves([lang, core])
        # framework (core) merges before the interpreter, each in its own wave,
        # despite the interpreter's ref sorting first.
        self.assertEqual(waves, [["z-core"], ["a-lang"]])

    def test_independents_pack_parallel_but_same_pair_serializes(self):
        a = self._c("a-p1", ["gurdy/pairs/x/t.py"], pairs=["p1"])
        b = self._c("b-p2", ["gurdy/pairs/y/t.py"], pairs=["p2"])
        c = self._c("c-p1", ["gurdy/pairs/x/u.py"], pairs=["p1"])
        waves = self.mq.order_waves([a, b, c])
        self.assertEqual(waves, [["a-p1", "b-p2"], ["c-p1"]])

    def test_shared_waves_precede_independent_waves(self):
        s = self._c("s", ["gurdy/languages/evm/interp.py"], langs=["evm"], shared=True)
        i = self._c("i", ["gurdy/pairs/x/t.py"], pairs=["p1"])
        self.assertEqual(self.mq.order_waves([i, s]), [["s"], ["i"]])


class TestFanOut(unittest.TestCase):
    def setUp(self):
        self.mq = _load()

    def test_dependents_of_language_change(self):
        scope = _manifest(["gurdy/languages/evm/interp.py"], langs=["evm"],
                          shared=True)["scope"]
        self.assertEqual(self.mq.dependents_of(scope, PAIRS), ["evm-btor2"])

    def test_dependents_of_hub_language_change(self):
        scope = _manifest(["gurdy/languages/btor2/interp.py"], langs=["btor2"],
                          shared=True)["scope"]
        # every pair whose source or target is btor2
        self.assertEqual(self.mq.dependents_of(scope, PAIRS),
                         ["btor2-smtlib", "evm-btor2", "riscv-btor2"])

    def test_dependents_of_core_change_is_all_pairs(self):
        scope = _manifest(["gurdy/core/coverage.py"], shared=True)["scope"]
        self.assertEqual(self.mq.dependents_of(scope, PAIRS), sorted(PAIRS))

    def test_reconcile_accepts_unchanged(self):
        base = {"evm-btor2": {"conjoined": [91, 144], "gate": "pass"}}
        res = self.mq.reconcile(base, {}, dict(base), ["evm-btor2"])
        self.assertTrue(res["accept"])
        self.assertEqual(res["mismatches"], [])

    def test_reconcile_rejects_undeclared_change(self):
        base = {"evm-btor2": {"conjoined": [91, 144], "gate": "pass"}}
        observed = {"evm-btor2": {"conjoined": [80, 144], "gate": "pass"}}
        res = self.mq.reconcile(base, {}, observed, ["evm-btor2"])
        self.assertFalse(res["accept"])
        self.assertEqual(res["mismatches"][0]["pair"], "evm-btor2")

    def test_reconcile_accepts_declared_change(self):
        base = {"evm-btor2": {"conjoined": [91, 144], "gate": "pass"}}
        expected = {"evm-btor2": {"conjoined": [80, 144], "gate": "pass"}}
        res = self.mq.reconcile(base, expected, dict(expected), ["evm-btor2"])
        self.assertTrue(res["accept"])

    def test_reconcile_rejects_unmeasured_dependent(self):
        base = {"evm-btor2": {"conjoined": [91, 144], "gate": "pass"}}
        res = self.mq.reconcile(base, {}, {}, ["evm-btor2"])
        self.assertFalse(res["accept"])
        self.assertIn("not measured", res["mismatches"][0]["reason"])


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.mq = _load()

    def test_plan_is_propose_mode_and_attaches_fanout(self):
        laneb = self.mq.Candidate.from_manifest(
            "fix", _manifest(["gurdy/languages/evm/interp.py"], langs=["evm"],
                             shared=True, lane="B"),
            shared_change={"symbol": "evm:_execute",
                           "expect": {"evm-btor2": {"conjoined": [90, 144]}}})
        indep = self.mq.Candidate.from_manifest(
            "widen", _manifest(["gurdy/pairs/riscv_btor2/translate.py"],
                               pairs=["riscv-btor2"]))
        plan = self.mq.build_plan([laneb, indep], PAIRS)
        self.assertEqual(plan["mode"], "propose")
        self.assertEqual(plan["schema"], "hg-merge-plan/v1")
        self.assertEqual(plan["decisions"]["fix"]["decision"], self.mq.FAN_OUT)
        self.assertEqual(plan["decisions"]["widen"]["decision"], self.mq.MERGE)
        fo = plan["fanouts"]["fix"]
        self.assertEqual(fo["dependents"], ["evm-btor2"])
        self.assertEqual(fo["expected"], {"evm-btor2": {"conjoined": [90, 144]}})
        # shared (fix) serialized first, then the independent widen.
        self.assertEqual(plan["waves"], [["fix"], ["widen"]])

    def test_render_is_readable(self):
        c = self.mq.Candidate.from_manifest(
            "p", _manifest(["gurdy/pairs/x/t.py"], pairs=["p1"]))
        text = self.mq.render(self.mq.build_plan([c], PAIRS))
        self.assertIn("propose mode", text)
        self.assertIn("merge", text)


if __name__ == "__main__":
    unittest.main()
