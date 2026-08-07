"""Kernel tests (KERNEL.md) — a self-contained toy stack end to end.

The toy: language ``count`` (programs count from ``start`` by ``step``,
the observable ``hit`` fires on reaching ``target``), an exact
translation to ``count2`` (all values doubled), and a bounded
brute-force solver on ``count2``. Together they exercise every kernel
seam: language admission with two-sided controls, the translation
square, solver admission with witness replay, multi-hop routes with
witness carry-back, the strict grade ladder, the frontier, and the
byte-identical report.
"""

import json
import os
import tempfile
import unittest

from kernel import checker, driver, registry, results

# -- toy executables ----------------------------------------------------------

INTERP = """\
import json, sys
prog = json.load(open(sys.argv[1])); inp = json.load(open(sys.argv[2]))
steps = int(inp.get("steps", 0))
hit, depth, v = False, 0, prog["{s}"]
for i in range(steps + 1):
    if v == prog["{t}"]:
        hit, depth = True, i
        break
    v += prog["{d}"]
print(json.dumps({{"hit": hit, "depth": depth}}, sort_keys=True))
"""

MUTANT_INTERP = """\
import json, sys
print(json.dumps({"hit": False, "depth": 0}, sort_keys=True))
"""

T_DOUBLE = """\
import json, sys
p = json.load(open(sys.argv[1]))
print(json.dumps({"s": 2 * p["start"], "d": 2 * p["step"],
                  "t": 2 * p["target"] + %d}, sort_keys=True))
"""

LAM_IDENTITY = """\
import sys
print(open(sys.argv[1]).read(), end="")
"""

SOLVE_BRUTE = """\
import json, sys
prog = json.load(open(sys.argv[1])); bound = sys.argv[4]
cap = 64 if bound == "inf" else min(int(bound), 64)
v, found = prog["s"], None
for i in range(cap + 1):
    if v == prog["t"]:
        found = i
        break
    v += prog["d"]
if found is not None:
    print(json.dumps({"kind": "witness", "payload": {"steps": found},
                      "depth": found}, sort_keys=True))
else:
    print(json.dumps({"kind": "all", "bound": cap}, sort_keys=True))
"""

MUTANT_SOLVE = """\
import json, sys
bound = sys.argv[4]
cap = 64 if bound == "inf" else min(int(bound), 64)
print(json.dumps({"kind": "all", "bound": cap}, sort_keys=True))
"""

LAM_STEPS = """\
import json, sys
p = json.load(open(sys.argv[1]))
print(json.dumps({"steps": p["steps"]}, sort_keys=True))
"""

SOLVE_BRUTE_CERT = """\
import json, sys
prog = json.load(open(sys.argv[1])); bound = sys.argv[4]
cap = 64 if bound == "inf" else min(int(bound), 64)
v, found = prog["{s}"], None
for i in range(cap + 1):
    if v == prog["{t}"]:
        found = i
        break
    v += prog["{d}"]
if found is not None:
    print(json.dumps({{"kind": "witness", "payload": {{"steps": found}},
                       "depth": found}}, sort_keys=True))
else:
    print(json.dumps({{"kind": "all", "bound": cap,
                       "cert": {{"schema": "toy-endpoint", "cap": cap,
                                 "end": v}}}}, sort_keys=True))
"""

DISCHARGE_TOY = """\
import json, sys
prog = json.load(open(sys.argv[1])); cert = json.load(open(sys.argv[2]))
ok = cert.get("schema") == "toy-endpoint"
v = prog["{s}"]
if ok:
    for i in range(int(cert["cap"]) + 1):
        if v == prog["{t}"]:
            ok = False    # a hit inside the certified bound refutes
            break
        v += prog["{d}"]
ok = ok and v == cert["end"]
print(json.dumps({{"ok": ok,
                   "obligations": {{"endpoint": "match" if ok
                                    else "mismatch"}}}}, sort_keys=True))
"""

DISCHARGE_BROKEN = """\
import sys
sys.exit(1)
"""

INTERP_RENAMED = """\
import json, sys
prog = json.load(open(sys.argv[1])); inp = json.load(open(sys.argv[2]))
steps = int(inp.get("steps", 0))
hit, v = False, prog["s"]
for i in range(steps + 1):
    if v == prog["t"]:
        hit = True
        break
    v += prog["d"]
print(json.dumps({"reached": hit}, sort_keys=True))
"""

MUTANT_RENAMED = """\
import json, sys
print(json.dumps({"reached": False}, sort_keys=True))
"""

LAM_OBS_RENAME = """\
import json, sys
obs = json.load(open(sys.argv[1]))
print(json.dumps({"hit": obs["reached"]}, sort_keys=True))
"""

LAM_OBS_LIAR = """\
import json, sys
print(json.dumps({"hit": True}, sort_keys=True))
"""


def _w(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _j(obj):
    return json.dumps(obj, sort_keys=True)


def build_registry(root):
    """Register and admit the whole toy stack; return registry.load(root)."""
    # language: count
    d = registry.register_language(root, {"kind": "language", "name": "count",
                                          "root": True, "lineage": ["toy"]},
                                   {})
    _w(d, "interp.py", INTERP.format(s="start", d="step", t="target"))
    _w(d, "vectors/001.program", _j({"start": 0, "step": 1, "target": 3}))
    _w(d, "vectors/001.input", _j({"steps": 5}))
    _w(d, "vectors/001.expect", _j({"hit": True, "depth": 3}))
    _w(d, "vectors/002.program", _j({"start": 0, "step": 2, "target": 5}))
    _w(d, "vectors/002.input", _j({"steps": 5}))
    _w(d, "vectors/002.expect", _j({"hit": False}))
    _w(d, "controls/mutant_blind.py", MUTANT_INTERP)
    registry.stamp_admission(d, checker.check_language(d, wall_s=20))

    # language: count2 (same semantics over doubled fields)
    d = registry.register_language(root, {"kind": "language",
                                          "name": "count2",
                                          "root": False, "lineage": ["toy"]},
                                   {})
    _w(d, "interp.py", INTERP.format(s="s", d="d", t="t"))
    _w(d, "vectors/001.program", _j({"s": 0, "d": 2, "t": 6}))
    _w(d, "vectors/001.input", _j({"steps": 5}))
    _w(d, "vectors/001.expect", _j({"hit": True, "depth": 3}))
    _w(d, "controls/mutant_blind.py", MUTANT_INTERP)
    registry.stamp_admission(d, checker.check_language(d, wall_s=20))

    # translation pair: count --> count2, exact on {hit}
    d = registry.register_pair(root, {"kind": "pair", "id": "count--count2",
                                      "src": "count", "tgt": "count2",
                                      "pair_kind": "translation",
                                      "direction": "exact", "keeps": ["hit"],
                                      "lineage": ["toy"]}, {})
    _w(d, "T.py", T_DOUBLE % 0)
    _w(d, "lam.py", LAM_IDENTITY)
    _w(d, "corpus/001.program", _j({"start": 0, "step": 1, "target": 3}))
    _w(d, "corpus/001.input", _j({"steps": 5}))
    _w(d, "corpus/002.program", _j({"start": 1, "step": 3, "target": 7}))
    _w(d, "corpus/002.input", _j({"steps": 4}))
    _w(d, "controls/mutant_offbyone.py", T_DOUBLE % 1)
    reg = registry.load(root)
    registry.stamp_admission(
        d, checker.check_pair(reg, d, reg["pairs"]["count--count2"],
                              wall_s=20))

    # solver pair: count2 --> result (bounded brute force, cap 64)
    d = registry.register_pair(root, {"kind": "pair", "id": "count2--brute",
                                      "src": "count2", "pair_kind": "solver",
                                      "decides": ["hit"],
                                      "lineage": ["toy-brute"]}, {})
    _w(d, "solve.py", SOLVE_BRUTE)
    _w(d, "lam.py", LAM_STEPS)
    _w(d, "corpus/001.program", _j({"s": 0, "d": 2, "t": 6}))
    _w(d, "corpus/001.q", _j({"mode": "exists", "observable": "hit",
                              "bound": 10, "label": True}))
    _w(d, "corpus/002.program", _j({"s": 0, "d": 2, "t": 5}))
    _w(d, "corpus/002.q", _j({"mode": "forall", "observable": "hit",
                              "bound": 10, "label": False}))
    _w(d, "controls/mutant_abstain.py", MUTANT_SOLVE)
    reg = registry.load(root)
    registry.stamp_admission(
        d, checker.check_pair(reg, d, reg["pairs"]["count2--brute"],
                              wall_s=20))
    return registry.load(root)


def build_benchmark(run_dir):
    programs = {
        "reach": {"start": 0, "step": 1, "target": 5},
        "miss": {"start": 0, "step": 2, "target": 5},
    }
    questions = []
    for pid, prog in programs.items():
        _w(run_dir, f"{pid}.program", _j(prog))
    import hashlib
    def sha(pid):
        return hashlib.sha256(
            open(os.path.join(run_dir, f"{pid}.program"),
                 "rb").read()).hexdigest()
    questions = [
        {"id": "q-reach", "language": "count", "program": "reach.program",
         "sha256": sha("reach"), "mode": "exists", "observable": "hit",
         "bound": 20},
        {"id": "q-miss-bounded", "language": "count",
         "program": "miss.program", "sha256": sha("miss"), "mode": "forall",
         "observable": "hit", "bound": 20},
        {"id": "q-miss-unbounded", "language": "count",
         "program": "miss.program", "sha256": sha("miss"), "mode": "exists",
         "observable": "hit", "bound": "inf"},
    ]
    _w(run_dir, "benchmark.json", _j({"name": "toy", "questions": questions}))


class KernelToyBase(unittest.TestCase):
    """One registry + one played run, built once for the class."""
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = os.path.join(cls._tmp.name, "registry")
        cls.run_dir = os.path.join(cls._tmp.name, "runs", "toy")
        os.makedirs(cls.run_dir)
        cls.reg = build_registry(cls.root)
        build_benchmark(cls.run_dir)
        cls.report_text = driver.play(cls.run_dir, cls.root, wall_s=20)
        cls.bench = results.load_benchmark(
            os.path.join(cls.run_dir, "benchmark.json"))
        cls.log = results.load(os.path.join(cls.run_dir, "log.jsonl"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()


class TestResultsCore(unittest.TestCase):
    Q = {"id": "q", "bound": 20}

    def rec(self, value, grade=""):
        return {"question": "q", "route": ["r"], "value": value,
                "grade": grade}

    def test_order_levels(self):
        partial = self.rec({"kind": "partial", "progress": {}})
        below = self.rec({"kind": "all", "bound": 10}, "claimed")
        terminal = self.rec({"kind": "all", "bound": 20}, "claimed")
        witness = self.rec({"kind": "witness", "payload": {}, "depth": 3},
                           "replayed")
        self.assertTrue(results.better(self.Q, below, partial))
        self.assertTrue(results.better(self.Q, terminal, below))
        self.assertTrue(results.better(self.Q, witness, terminal))
        self.assertFalse(results.better(self.Q, partial, partial))

    def test_grade_ladder_orders_terminals(self):
        claimed = self.rec({"kind": "all", "bound": "inf"}, "claimed")
        checked = self.rec({"kind": "all", "bound": "inf"}, "checked")
        certified = self.rec({"kind": "all", "bound": "inf"}, "certified")
        self.assertTrue(results.better(self.Q, checked, claimed))
        self.assertTrue(results.better(self.Q, certified, checked))

    def test_contradiction_detected(self):
        bench = {"name": "b", "questions": [dict(self.Q, mode="exists")]}
        wit = self.rec({"kind": "witness", "payload": {}, "depth": 5},
                       "replayed")
        allr = self.rec({"kind": "all", "bound": 10}, "claimed")
        found = results.contradictions(bench, [wit, allr])
        self.assertEqual(len(found), 1)
        below = self.rec({"kind": "all", "bound": 3}, "claimed")
        self.assertEqual(results.contradictions(bench, [wit, below]), [])

    def test_corroboration_needs_disjoint_lineage_and_agreement(self):
        bench = {"name": "b", "questions": [dict(self.Q, mode="forall")]}
        a = dict(self.rec({"kind": "all", "bound": 20}, "claimed"),
                 lineage=["x", "y"])
        same_family = dict(self.rec({"kind": "all", "bound": 20}, "claimed"),
                           lineage=["y"])
        disjoint = dict(self.rec({"kind": "all", "bound": 20}, "claimed"),
                        lineage=["z"])
        below_ask = dict(self.rec({"kind": "all", "bound": 10}, "claimed"),
                         lineage=["z"])
        witness = dict(self.rec({"kind": "witness", "payload": {},
                                 "depth": 3}, "replayed"), lineage=["z"])
        unstamped = self.rec({"kind": "all", "bound": 20}, "claimed")
        self.assertEqual(results.corroborated(bench, [a, disjoint]), {"q"})
        self.assertEqual(results.corroborated(bench, [a, same_family]),
                         set())                     # shared ancestry
        self.assertEqual(results.corroborated(bench, [a, below_ask]),
                         set())                     # not terminal
        self.assertEqual(results.corroborated(bench, [a, witness]),
                         set())     # kind mismatch is a contradiction
        self.assertEqual(results.corroborated(bench, [a, unstamped]),
                         set())                     # no recorded lineage
        # the flag belongs to the verdict: a best that predates lineage
        # stamping is corroborated by any disjoint agreeing pair
        self.assertEqual(results.corroborated(
            bench, [unstamped, a, disjoint]), {"q"})

    def test_best_is_monotone_under_append(self):
        bench = {"name": "b", "questions": [dict(self.Q)]}
        first = self.rec({"kind": "all", "bound": 10}, "claimed")
        worse = self.rec({"kind": "partial", "progress": {}})
        better_ = self.rec({"kind": "all", "bound": 20}, "claimed")
        self.assertIs(results.best(bench, [first, worse])["q"], first)
        self.assertIs(results.best(bench, [first, worse, better_])["q"],
                      better_)
        self.assertEqual(results.expanded(bench, [first, better_], [first]),
                         ["q"])
        self.assertEqual(results.expanded(bench, [first, worse], [first]), [])


class TestRegistry(unittest.TestCase):
    def test_append_only_and_single_admission(self):
        with tempfile.TemporaryDirectory() as root:
            m = {"kind": "language", "name": "x", "lineage": []}
            d = registry.register_language(root, m, {})
            with self.assertRaises(registry.RegistryError):
                registry.register_language(root, m, {})
            registry.stamp_admission(d, {"checked": "language"})
            with self.assertRaises(registry.RegistryError):
                registry.stamp_admission(d, {"checked": "again"})


class TestChecker(unittest.TestCase):
    def test_two_sided_controls_are_required(self):
        with tempfile.TemporaryDirectory() as root:
            d = registry.register_language(
                root, {"kind": "language", "name": "c", "lineage": []}, {})
            _w(d, "interp.py", INTERP.format(s="start", d="step", t="target"))
            _w(d, "vectors/001.program",
               _j({"start": 0, "step": 1, "target": 2}))
            _w(d, "vectors/001.input", _j({"steps": 3}))
            _w(d, "vectors/001.expect", _j({"hit": True}))
            with self.assertRaisesRegex(checker.AdmissionError,
                                        "no negative controls"):
                checker.check_language(d, wall_s=20)
            # a "mutant" identical to the real interpreter must be rejected:
            # vectors that cannot catch a defect check nothing.
            _w(d, "controls/mutant_same.py",
               INTERP.format(s="start", d="step", t="target"))
            with self.assertRaisesRegex(checker.AdmissionError,
                                        "passed the vectors"):
                checker.check_language(d, wall_s=20)

    def test_nondeterminism_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            d = registry.register_language(
                root, {"kind": "language", "name": "c", "lineage": []}, {})
            _w(d, "interp.py",
               "import json, random\n"
               "print(json.dumps({'hit': True, 'noise': random.random()}))\n")
            _w(d, "vectors/001.program", _j({}))
            _w(d, "vectors/001.input", _j({}))
            _w(d, "vectors/001.expect", _j({"hit": True}))
            _w(d, "controls/mutant_blind.py", MUTANT_INTERP)
            with self.assertRaisesRegex(checker.AdmissionError,
                                        "nondeterministic"):
                checker.check_language(d, wall_s=20)


class TestDischargeSeam(unittest.TestCase):
    """The universal-certificate seam (KERNEL.md §2): the kernel runs
    the pair's discharge checker itself — certified at the source,
    checked past translation hops, claimed on any failure — and
    admission requires the discharge be exercised and falsifiable."""

    FIELDS = {"count": ("start", "step", "target"),
              "count2": ("s", "d", "t")}

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = os.path.join(cls._tmp.name, "registry")
        build_registry(cls.root)
        cls.miss = _w(cls._tmp.name, "miss.program",
                      _j({"start": 0, "step": 2, "target": 5}))
        reach = {"count": {"start": 0, "step": 1, "target": 3},
                 "count2": {"s": 0, "d": 2, "t": 6}}
        miss = {"count": {"start": 0, "step": 2, "target": 5},
                "count2": {"s": 0, "d": 2, "t": 5}}
        cls.evidence = {}
        for lang, (s, d_, t) in cls.FIELDS.items():
            e = registry.register_pair(
                cls.root, {"kind": "pair", "id": f"{lang}--brutecert",
                           "src": lang, "pair_kind": "solver",
                           "decides": ["hit"],
                           "lineage": ["toy-brute"],
                           "discharge_lineage": ["toy-recompute"]}, {})
            _w(e, "solve.py", SOLVE_BRUTE_CERT.format(s=s, d=d_, t=t))
            _w(e, "discharge.py", DISCHARGE_TOY.format(s=s, d=d_, t=t))
            _w(e, "lam.py", LAM_STEPS)
            _w(e, "corpus/001.program", _j(reach[lang]))
            _w(e, "corpus/001.q", _j({"mode": "exists", "observable": "hit",
                                      "bound": 10, "label": True}))
            _w(e, "corpus/002.program", _j(miss[lang]))
            _w(e, "corpus/002.q", _j({"mode": "forall", "observable": "hit",
                                      "bound": 10, "label": False}))
            _w(e, "controls/mutant_abstain.py", MUTANT_SOLVE)
            _w(e, "controls/cert_mutant_end.json",
               _j({"schema": "toy-endpoint", "cap": 10, "end": -1}))
            reg = registry.load(cls.root)
            cls.evidence[lang] = checker.check_pair(
                reg, e, reg["pairs"][f"{lang}--brutecert"], wall_s=20)
            registry.stamp_admission(e, cls.evidence[lang])
        cls.reg = registry.load(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _q(self):
        return {"id": "q-miss", "language": "count", "mode": "forall",
                "observable": "hit", "bound": 10,
                "_program_path": self.miss}

    def test_admission_counts_the_discharge_and_its_controls(self):
        self.assertEqual(self.evidence["count"],
                         {"checked": "solver", "corpus": 2, "controls": 1,
                          "cert_mutants": 1, "discharged": 1})

    def test_certified_at_the_source(self):
        route = [self.reg["pairs"]["count--brutecert"]]
        rec = driver.run_route(self.reg, route, self._q(), 20)
        self.assertEqual(rec["value"]["kind"], "all")
        self.assertEqual(rec["grade"], "certified")
        self.assertEqual(rec["discharge"]["at"], "source")
        self.assertEqual(rec["discharge"]["lineage"], ["toy-recompute"])

    def test_checked_past_a_translation_hop(self):
        route = [self.reg["pairs"]["count--count2"],
                 self.reg["pairs"]["count2--brutecert"]]
        rec = driver.run_route(self.reg, route, self._q(), 20)
        self.assertEqual(rec["value"]["kind"], "all")
        self.assertEqual(rec["grade"], "checked")
        self.assertEqual(rec["discharge"]["at"], "target")

    def test_failsafe_broken_discharge_stays_claimed(self):
        e = registry.register_pair(
            self.root, {"kind": "pair", "id": "count--brokencert",
                        "src": "count", "pair_kind": "solver",
                        "decides": ["hit"],
                        "lineage": ["toy-brute"],
                        "discharge_lineage": ["toy-broken"]}, {})
        s, d_, t = self.FIELDS["count"]
        _w(e, "solve.py", SOLVE_BRUTE_CERT.format(s=s, d=d_, t=t))
        _w(e, "discharge.py", DISCHARGE_BROKEN)
        _w(e, "lam.py", LAM_STEPS)
        _w(e, "corpus/001.program", _j({"start": 0, "step": 2, "target": 5}))
        _w(e, "corpus/001.q", _j({"mode": "forall", "observable": "hit",
                                  "bound": 10, "label": False}))
        _w(e, "controls/mutant_abstain.py", MUTANT_SOLVE)
        _w(e, "controls/cert_mutant_end.json",
           _j({"schema": "toy-endpoint", "cap": 10, "end": -1}))
        reg = registry.load(self.root)
        with self.assertRaisesRegex(checker.AdmissionError,
                                    "did not discharge"):
            checker.check_pair(reg, e, reg["pairs"]["count--brokencert"],
                               wall_s=20)
        rec = driver.run_route(reg, [reg["pairs"]["count--brokencert"]],
                               self._q(), 20)
        self.assertEqual(rec["value"]["kind"], "all")
        self.assertEqual(rec["grade"], "claimed")
        self.assertNotIn("discharge", rec)

    def test_unfalsifiable_cert_control_is_rejected(self):
        e = registry.register_pair(
            self.root, {"kind": "pair", "id": "count--unfals",
                        "src": "count", "pair_kind": "solver",
                        "lineage": ["toy-brute"],
                        "discharge_lineage": ["toy-recompute"]}, {})
        s, d_, t = self.FIELDS["count"]
        _w(e, "solve.py", SOLVE_BRUTE_CERT.format(s=s, d=d_, t=t))
        _w(e, "discharge.py", DISCHARGE_TOY.format(s=s, d=d_, t=t))
        _w(e, "lam.py", LAM_STEPS)
        _w(e, "corpus/001.program", _j({"start": 0, "step": 2, "target": 5}))
        _w(e, "corpus/001.q", _j({"mode": "forall", "observable": "hit",
                                  "bound": 10, "label": False}))
        _w(e, "corpus/002.program", _j({"start": 0, "step": 1, "target": 3}))
        _w(e, "corpus/002.q", _j({"mode": "exists", "observable": "hit",
                                  "bound": 10, "label": True}))
        _w(e, "controls/mutant_abstain.py", MUTANT_SOLVE)
        # the "mutant" certificate is the real one — an undetectable
        # control means the discharge checker cannot be falsified
        _w(e, "controls/cert_mutant_real.json",
           _j({"schema": "toy-endpoint", "cap": 10, "end": 22}))
        reg = registry.load(self.root)
        with self.assertRaisesRegex(checker.AdmissionError,
                                    "cannot catch a wrong certificate"):
            checker.check_pair(reg, e, reg["pairs"]["count--unfals"],
                               wall_s=20)


class TestLamObs(unittest.TestCase):
    """Λ on observables (KERNEL.md §1: I_s ≡π Λ(I_t(T(p)))): a pair
    whose languages name their observables differently carries the
    target behavior back before the square compares — and the carry-
    back is itself falsified by the mutant discipline."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = os.path.join(cls._tmp.name, "registry")
        d = registry.register_language(
            cls.root, {"kind": "language", "name": "count", "root": True,
                       "lineage": ["toy"]}, {})
        _w(d, "interp.py", INTERP.format(s="start", d="step", t="target"))
        _w(d, "vectors/001.program", _j({"start": 0, "step": 1,
                                         "target": 3}))
        _w(d, "vectors/001.input", _j({"steps": 5}))
        _w(d, "vectors/001.expect", _j({"hit": True, "depth": 3}))
        _w(d, "controls/mutant_blind.py", MUTANT_INTERP)
        registry.stamp_admission(d, checker.check_language(d, wall_s=20))
        d = registry.register_language(
            cls.root, {"kind": "language", "name": "count3", "root": False,
                       "lineage": ["toy"]}, {})
        _w(d, "interp.py", INTERP_RENAMED)
        _w(d, "vectors/001.program", _j({"s": 0, "d": 2, "t": 6}))
        _w(d, "vectors/001.input", _j({"steps": 5}))
        _w(d, "vectors/001.expect", _j({"reached": True}))
        _w(d, "controls/mutant_blind.py", MUTANT_RENAMED)
        registry.stamp_admission(d, checker.check_language(d, wall_s=20))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _pair(self, pid, lam_obs, corpus, **fields):
        d = registry.register_pair(
            self.root, {"kind": "pair", "id": pid, "src": "count",
                        "tgt": "count3", "pair_kind": "translation",
                        "direction": "exact", "keeps": ["hit"],
                        "maps": {"hit": "reached"},
                        "lineage": ["toy"], **fields}, {})
        _w(d, "T.py", T_DOUBLE % 0)
        _w(d, "lam_obs.py", lam_obs)
        for i, prog in enumerate(corpus, 1):
            _w(d, f"corpus/{i:03d}.program", _j(prog))
            _w(d, f"corpus/{i:03d}.input", _j({"steps": 5}))
        _w(d, "controls/mutant_offbyone.py", T_DOUBLE % 1)
        return d

    def test_square_closes_through_the_carry_back(self):
        d = self._pair("count--count3",
                       LAM_OBS_RENAME,
                       [{"start": 0, "step": 1, "target": 3},
                        {"start": 0, "step": 2, "target": 5}])
        reg = registry.load(self.root)
        evidence = checker.check_pair(reg, d, reg["pairs"]["count--count3"],
                                      wall_s=20)
        self.assertEqual(evidence, {"checked": "translation", "corpus": 2,
                                    "controls": 1})

    def test_lying_carry_back_cannot_shield_a_mutant(self):
        # a lam_obs that invents the observable passes the (all-true)
        # corpus but lets the off-by-one mutant pass the square — the
        # two-sided controls reject the pair. (maps absent: this is
        # the pure-executable-Λ configuration; with maps declared the
        # same lie is caught earlier, by the per-program agreement.)
        d = self._pair("count--count3liar",
                       LAM_OBS_LIAR,
                       [{"start": 0, "step": 1, "target": 3}],
                       maps=None)
        reg = registry.load(self.root)
        with self.assertRaisesRegex(checker.AdmissionError,
                                    "passed the square"):
            checker.check_pair(reg, d, reg["pairs"]["count--count3liar"],
                               wall_s=20)

    def test_routing_composes_maps_decides_and_caps(self):
        self._pair("count--count3r", LAM_OBS_RENAME,
                   [{"start": 0, "step": 1, "target": 3},
                    {"start": 0, "step": 2, "target": 5}],
                   bound_cap=5)
        s = registry.register_pair(
            self.root, {"kind": "pair", "id": "count3--brute",
                        "src": "count3", "pair_kind": "solver",
                        "decides": ["reached"],
                        "lineage": ["toy-brute"]}, {})
        _w(s, "solve.py", SOLVE_BRUTE)
        _w(s, "lam.py", LAM_STEPS)
        q = {"id": "q", "language": "count", "mode": "forall",
             "observable": "hit", "bound": 10,
             "_program_path": _w(self._tmp.name, "miss2.program",
                                 _j({"start": 0, "step": 2, "target": 5}))}
        reg = registry.load(self.root)
        rec = driver.run_route(
            reg, [reg["pairs"]["count--count3r"],
                  reg["pairs"]["count3--brute"]], q, 20)
        # hit composed to reached and decided; all(64) capped at the hop
        self.assertEqual(rec["value"]["kind"], "all")
        self.assertEqual(rec["value"]["bound"], 5)
        s2 = registry.register_pair(
            self.root, {"kind": "pair", "id": "count3--undeclared",
                        "src": "count3", "pair_kind": "solver",
                        "lineage": ["toy-brute"]}, {})
        _w(s2, "solve.py", SOLVE_BRUTE)
        reg = registry.load(self.root)
        rec = driver.run_route(
            reg, [reg["pairs"]["count--count3r"],
                  reg["pairs"]["count3--undeclared"]], q, 20)
        self.assertEqual(rec["value"]["kind"], "partial")
        self.assertIn("cannot decide", rec["value"]["progress"]["note"])


class TestDriverEndToEnd(KernelToyBase):
    def _best(self):
        return results.best(self.bench, self.log)

    def test_witness_is_replayed_across_the_hop(self):
        rec = self._best()["q-reach"]
        self.assertEqual(rec["value"]["kind"], "witness")
        self.assertEqual(rec["value"]["depth"], 5)
        self.assertEqual(rec["grade"], "replayed")
        self.assertEqual(rec["route"], ["count--count2", "count2--brute"])
        self.assertEqual(rec["lineage"], ["toy", "toy-brute"])

    def test_bounded_universal_is_terminal_and_claimed(self):
        rec = self._best()["q-miss-bounded"]
        self.assertEqual(rec["value"], {"kind": "all", "bound": 20,
                                        "cert": None})
        self.assertEqual(rec["grade"], "claimed")
        q = next(q for q in self.bench["questions"]
                 if q["id"] == "q-miss-bounded")
        self.assertTrue(results.terminal(q, rec["value"]))

    def test_unbounded_ask_lands_on_the_frontier(self):
        self.assertEqual(results.frontier(self.bench, self.log),
                         ["q-miss-unbounded"])
        rec = self._best()["q-miss-unbounded"]
        self.assertEqual(rec["value"]["bound"], 64)   # the solver's cap

    def test_no_contradictions_and_report_regenerates(self):
        self.assertEqual(results.contradictions(self.bench, self.log), [])
        again = driver.report(self.run_dir)
        self.assertEqual(self.report_text, again)
        self.assertIn("2 of 3 terminal", again)

    def test_replay_ratchet_across_iterations(self):
        before = results.best(self.bench, self.log)
        driver.play(self.run_dir, self.root, wall_s=20)
        after_log = results.load(os.path.join(self.run_dir, "log.jsonl"))
        after = results.best(self.bench, after_log)
        for qid, rec in before.items():
            q = next(q for q in self.bench["questions"] if q["id"] == qid)
            self.assertFalse(results.better(q, rec, after[qid]))


if __name__ == "__main__":
    unittest.main()
