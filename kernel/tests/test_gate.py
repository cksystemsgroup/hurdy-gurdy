"""The gate run against the registry's own controls (KERNEL.md §9,
§10). Two halves. First, every stamp in the registry is re-derived:
the admission of every bound entry is re-run and must produce the
evidence its stamp carries — which means every intact implementation
passes again and every supplied mutant is refused again. Second, on a
toy registry built from empty, every way of failing the gate fails
it: a missing control, a mutant that passes, a judge that accepts
anything, an implementation that reaches for a tool, a revision that
disagrees with its predecessor, an accelerator that disagrees with
its reference, a channel at the wrong direction, a vacuous search.

The fast tier re-gates the entries a name currently binds to (three
languages, two domains) and the toy; ``HG_SLOW=1`` re-gates every
admitted entry of every kind, revisions and searches included."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import unittest

from kernel import checker, driver, registry
from kernel.tests import toy

REG = "registry"
SLOW = os.environ.get("HG_SLOW") == "1"


def _rederive(reg: dict, entry_dir: str) -> tuple[dict, dict]:
    with open(os.path.join(entry_dir, "manifest.json"),
              encoding="utf-8") as fh:
        manifest = json.load(fh)
    stamped = dict(manifest["admission"])
    stamped.pop("tree")
    return checker.check(reg, entry_dir, manifest, wall_s=60.0), stamped


class StampsRederive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = registry.load(REG)

    def test_bound_languages_and_domains(self):
        for sub in ("domains", "languages"):
            for name, m in sorted(self.reg[sub].items()):
                with self.subTest(entry=f"{sub}/{name}"):
                    evidence, stamped = _rederive(self.reg, m["_dir"])
                    self.assertEqual(evidence, stamped)

    @unittest.skipUnless(SLOW, "HG_SLOW=1 re-gates every entry")
    def test_every_admitted_entry_of_every_kind(self):
        """Every stamp re-derives — with one honest allowance: a
        revision's conservativity surface is the predecessor's vectors
        plus the corpora of every pair bound to the language *at the
        time*, and the registry has only grown since, so an old
        revision's agreement counts are a floor, never an equality."""
        for sub in ("domains", "languages", "pairs", "searches"):
            base = os.path.join(REG, sub)
            for name in sorted(os.listdir(base)):
                entry = os.path.join(base, name)
                if not os.path.isfile(os.path.join(entry, "manifest.json")):
                    continue
                with self.subTest(entry=f"{sub}/{name}"):
                    evidence, stamped = _rederive(self.reg, entry)
                    now = evidence.pop("agreement", {})
                    then = stamped.pop("agreement", {})
                    self.assertEqual(evidence, stamped)
                    self.assertEqual(set(now), set(then))
                    for label, count in then.items():
                        self.assertGreaterEqual(now[label], count, label)


class FromEmpty(unittest.TestCase):
    """The toy registry: bootstrap, then every refusal."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.reg_root = toy.build(cls.tmp)
        cls.reg = registry.load(cls.reg_root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def _refused(self, manifest, files, needle: str):
        with self.assertRaises(checker.AdmissionError) as ctx:
            toy.admit(self.reg_root, manifest, files)
        self.assertIn(needle, str(ctx.exception))

    def test_bootstrap_admitted_everything_with_pins(self):
        for sub, name in (("domains", "toydom"), ("languages", "toy"),
                          ("languages", "toy2"), ("pairs", "toy--toy2"),
                          ("searches", "toy2-search")):
            self.assertIn("tree", self.reg[sub][name]["admission"])
        self.assertEqual(self.reg["pairs"]["toy--toy2"]["admission"]
                         ["channels"]["prog"], {"corpus": 2, "controls": 1})
        self.assertEqual(self.reg["languages"]["toy"]["admission"]
                         ["evidence"]["threshold-proof"],
                         {"vectors": 2, "controls": 2})
        text = driver.base(self.reg_root)
        self.assertIn("`toy`", text)
        self.assertIn("`toy:threshold-proof`", text)
        self.assertIn("anchored by toydom (1 anchors)", text)
        self.assertIn("corroborated only by its pairs' squares", text)

    # -- languages --------------------------------------------------------

    def test_language_without_controls_is_unfalsifiable(self):
        m, files = toy.language_toy()
        m["name"] = "toy-nocontrols"
        files = {k: v for k, v in files.items()
                 if not k.startswith("controls/")}
        self._refused(m, files, "no negative controls")

    def test_mutant_that_passes_means_the_vectors_are_blind(self):
        m, files = toy.language_toy()
        m["name"] = "toy-blind"
        files["controls/mutant_same.py"] = toy.TOY_INTERP.encode()
        self._refused(m, files, "passed the vectors")

    def test_wrong_vector_is_refused(self):
        m, files = toy.language_toy()
        m["name"] = "toy-wrong"
        files["vectors/003.expect"] = toy._j({"bad": True, "depth": 1})
        self._refused(m, files, "expected True")

    def test_judge_that_accepts_anything_is_refused(self):
        m, files = toy.language_toy()
        m["name"] = "toy-credulous"
        files["evidence/threshold-proof/check.py"] = (
            'import json\nprint(json.dumps({"ok": True, "obligations": {}}))\n'
        ).encode()
        self._refused(m, files, "cannot catch a wrong certificate")

    def test_judge_without_mutant_certificates_is_refused(self):
        m, files = toy.language_toy()
        m["name"] = "toy-nocertmutants"
        files = {k: v for k, v in files.items()
                 if not k.startswith("evidence/threshold-proof/controls/")}
        self._refused(m, files, "no mutant certificates")

    def test_reaching_for_a_tool_is_loud(self):
        m, files = toy.language_toy()
        m["name"] = "toy-tool"
        files["interp.py"] = (
            "import subprocess, sys\n"
            "subprocess.run(['python3', sys.argv[0], *sys.argv[1:]])\n"
        ).encode()
        self._refused(m, files, "interp.py")

    def test_reference_must_be_python_inside_the_entry(self):
        m, files = toy.language_toy()
        m["name"] = "toy-noref"
        del files["interp.py"]
        self._refused(m, files, "missing interp.py")

    def test_judges_are_never_accelerated(self):
        m, files = toy.language_toy()
        m["name"] = "toy-fast"
        m["accelerator"] = {"replaces": "interp.py", "exe": "fast",
                            "source": "fast.c", "language": "C"}
        self._refused(m, files, "cannot be accelerated")

    def test_nondeterminism_is_refused(self):
        m, files = toy.language_toy()
        m["name"] = "toy-random"
        files["interp.py"] = toy.TOY_INTERP.replace(
            '"depth": 1', '"depth": __import__("time").time_ns()')
        files["interp.py"] = files["interp.py"].encode()
        self._refused(m, files, "nondeterministic")

    # -- revisions --------------------------------------------------------

    def test_revision_must_agree_with_its_predecessor(self):
        m, files = toy.language_toy()
        m["revision"] = 2
        m["previous"] = registry.tree_hash(
            os.path.join(self.reg_root, "languages", "toy"))
        files["interp.py"] = toy.TOY_MUTANT_NOSAT.encode()
        # keep its own vectors consistent with the new semantics, so
        # that only conservativity can refuse it
        files["vectors/002.expect"] = toy._j({"bad": True, "depth": 1})
        self._refused(m, files, "disagrees with its predecessor")

    def test_revision_must_name_its_predecessor_exactly(self):
        m, files = toy.language_toy()
        m["revision"] = 3
        m["previous"] = "0" * 64
        self._refused(m, files, "predecessor")

    # -- pairs ------------------------------------------------------------

    def test_translator_mutant_that_keeps_the_square_is_refused(self):
        m, files = toy.pair()
        m["id"] = "toy--toy2-blind"
        files["controls/prog_mutant_same.py"] = toy.PAIR_T.encode()
        self._refused(m, files, "passed the square")

    def test_pair_without_translation_is_no_correspondence(self):
        m, files = toy.pair()
        m["id"] = "toy--toy2-noprog"
        m["channels"] = ["wit", "obs", "claim"]
        self._refused(m, files, "no prog channel")

    def test_channel_at_the_wrong_direction_is_refused(self):
        m, files = toy.pair()
        m["id"] = "toy--toy2-over"
        m["direction"] = "over"
        self._refused(m, files, "cannot exist at direction")

    def test_declared_channel_needs_its_transport(self):
        m, files = toy.pair()
        m["id"] = "toy--toy2-nocert"
        m["channels"] = m["channels"] + ["cert"]
        self._refused(m, files, "missing lam_cert.py")

    def test_carry_back_mutant_that_still_replays_is_refused(self):
        m, files = toy.pair()
        m["id"] = "toy--toy2-witblind"
        files["controls/wit_mutant_same.py"] = toy.PAIR_LAM_WIT.encode()
        self._refused(m, files, "passed the stimulus replay")

    def test_broken_translator_loses_squares(self):
        m, files = toy.pair()
        m["id"] = "toy--toy2-broken"
        files["T.py"] = toy.PAIR_T_MUTANT_SWAP.encode()
        self._refused(m, files, "square broken")

    def test_accelerator_admitted_only_by_byte_agreement(self):
        m, files = toy.pair()
        m["id"] = "toy--toy2-acc"
        m["accelerator"] = {"replaces": "T.py", "exe": "fast",
                            "source": "fast.sh", "language": "sh"}
        files["fast.sh"] = files["fast"] = b'#!/bin/sh\necho \'{"m": 0, "t": 0}\'\n'
        entry = toy.write_entry(self.reg_root, m, files)
        os.chmod(os.path.join(entry, "fast"),
                 os.stat(os.path.join(entry, "fast")).st_mode | stat.S_IXUSR)
        with self.assertRaises(checker.AdmissionError) as ctx:
            driver.admit(entry, self.reg_root, wall_s=20.0)
        self.assertIn("disagrees with the reference", str(ctx.exception))

    # -- searches ---------------------------------------------------------

    def test_lying_search_is_refused_because_its_witness_does_not_replay(self):
        m, files = toy.search()
        m["name"] = "toy2-liar"
        files["solve.py"] = toy.SEARCH_MUTANT_LIAR.encode()
        self._refused(m, files, "witness did not replay")

    def test_search_that_only_abstains_is_vacuous(self):
        m, files = toy.search()
        m["name"] = "toy2-mute"
        files["solve.py"] = (
            'import json\nprint(json.dumps({"kind": "partial", '
            '"progress": {"note": "no"}}))\n').encode()
        self._refused(m, files, "vacuous")

    def test_search_mutant_that_passes_is_refused(self):
        m, files = toy.search()
        m["name"] = "toy2-blind"
        files["controls/mutant_same.py"] = toy.SEARCH_SOLVE.encode()
        self._refused(m, files, "passed the corpus")

    def test_certificate_the_language_cannot_judge_is_refused(self):
        m, files = toy.search()
        m["name"] = "toy2-alien"
        files["solve.py"] = toy.SEARCH_SOLVE.replace(
            '"tm-proof"', '"no-such-schema"').encode()
        self._refused(m, files, "did not discharge")

    def test_verdict_against_label_is_refused(self):
        m, files = toy.search()
        m["name"] = "toy2-mislabelled"
        files["corpus/001.q"] = toy._j({"mode": "exists", "observable":
                                        "fired", "bound": "inf",
                                        "label": False})
        self._refused(m, files, "against label")

    # -- domains ----------------------------------------------------------

    def test_domain_enters_with_its_ground_truth_stated(self):
        m, files = toy.domain()
        m["name"] = "toydom-empty"
        m["anchors"] = []
        self._refused(m, files, "no anchors")
