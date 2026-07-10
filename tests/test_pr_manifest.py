"""The PR manifest emitter (tools/pr_manifest.py) — Phase 1 of the scaling
rollout (SCALING.md §12.1). The emitter *is* the fast per-change gate, so it is
dogfooded here: every registered pair measures, the conjoined numbers match the
capability snapshot, the manifest is well-formed, and the determinism check the
gate runs on touched pairs actually holds on a real pair.
"""

import importlib.util
import unittest
from pathlib import Path


PRODUCTION_PAIRS = {
    "aarch64-btor2", "aarch64-sail", "btor2-smtlib", "c-riscv", "crn-smtlib",
    "ebpf-btor2", "evm-btor2", "python-smtlib", "riscv-btor2", "riscv-sail",
    "sail-btor2", "smiles-formula", "wasm-btor2",
}


def _load_tool(name: str):
    import sys
    path = Path(__file__).resolve().parent.parent / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestPRManifest(unittest.TestCase):
    def test_manifest_measures_every_pair_and_gates_green(self):
        pm = _load_tool("pr_manifest")
        manifest, code = pm.build_manifest()
        # The fast gate passes on a clean tree: every pair measurable,
        # no touched pair (nothing under gurdy/pairs changed here).
        self.assertEqual(code, 0, manifest["verdict"])
        self.assertEqual(manifest["schema"], "hg-pr-manifest/v1")
        self.assertTrue(manifest["verdict"]["coverage_measured"])
        self.assertEqual(manifest["verdict"]["measurement_errors"], [])
        self.assertEqual(manifest["verdict"]["determinism_failures"], [])
        # The 13 production pairs are all present (order-independent: a
        # mid-suite import of the demo pair may add ambient extras).
        by_id = {r["id"]: r for r in manifest["pairs"]}
        self.assertTrue(PRODUCTION_PAIRS <= set(by_id),
                        sorted(PRODUCTION_PAIRS - set(by_id)))
        # Conjoined coverage matches the capability snapshot (Definition 4.6).
        self.assertEqual(by_id["riscv-btor2"]["conjoined"], [96, 96])
        self.assertEqual(by_id["riscv-sail"]["conjoined"], [96, 96])
        self.assertEqual(by_id["ebpf-btor2"]["conjoined"], [126, 126])
        # A predicted-grade hop into SMT-LIB has no decidable square: per-run.
        self.assertIsNone(by_id["btor2-smtlib"]["conjoined"])
        # The reproducible C head carries no construct inventory.
        self.assertIsNone(by_id["c-riscv"]["accepted"])

    def test_manifest_is_valid_and_byte_deterministic(self):
        pm = _load_tool("pr_manifest")
        manifest, _ = pm.build_manifest()
        text1 = "\n".join(pm._yaml(manifest)) + "\n"
        text2 = "\n".join(pm._yaml(manifest)) + "\n"
        self.assertEqual(text1, text2)          # the manifest twice-and-diffs
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml not installed")
        parsed = yaml.safe_load(text1)
        self.assertEqual(parsed["schema"], "hg-pr-manifest/v1")
        self.assertTrue(PRODUCTION_PAIRS <= {p["id"] for p in parsed["pairs"]})

    def test_touched_pair_determinism_check_holds(self):
        # The gate's twice-and-diff over a real pair's probes must pass — a
        # non-deterministic translator is the thing this fails on.
        pm = _load_tool("pr_manifest")
        pm._import_all_pairs()
        from gurdy.core import registry
        pair = registry.get_pair("riscv-btor2")
        self.assertTrue(pm._twice_and_diff(pair.translator, pair.probes))

    def test_gate_fails_on_nondeterminism_and_unmeasurable_pairs(self):
        # Negative control (the doc's own discipline: a gate without one is
        # unchecked). The fast gate must FAIL on the two things it exists to
        # catch — a non-deterministic translator and a pair that cannot be
        # measured — not silently pass.
        pm = _load_tool("pr_manifest")
        pm._import_all_pairs()
        from gurdy.core import registry

        real = registry.get_pair("riscv-btor2")

        # (a) determinism: a translator whose output differs run-to-run.
        counter = {"n": 0}
        def flaky(program):
            counter["n"] += 1
            return real.translator(program) + bytes([counter["n"] & 0xFF])
        self.assertFalse(pm._twice_and_diff(flaky, real.probes))

        # (b) measurability: a translator that raises a non-Unsupported error.
        def broken(program):
            raise RuntimeError("boom")
        _row, err = pm._pair_row("broken", type(real)(**{**real.__dict__,
                                 "translator": broken}), touched=False)
        self.assertIsNotNone(err)
        self.assertIn("broken", err)

    def test_scope_maps_files_to_pairs_and_flags_protected(self):
        pm = _load_tool("pr_manifest")
        scope = pm._scope([
            "gurdy/pairs/riscv_btor2/translate.py",     # -> pair riscv-btor2
            "gurdy/languages/riscv/inventory.py",        # protected instrument
            "gurdy/core/oracle.py",                      # shared layer
            "README.md",                                 # neither
        ])
        self.assertIn("riscv-btor2", scope["touched_pairs"])
        self.assertIn("riscv", scope["touched_languages"])
        self.assertTrue(scope["touches_shared_layer"])
        self.assertEqual(scope["touches_protected"],
                         ["gurdy/languages/riscv/inventory.py"])


if __name__ == "__main__":
    unittest.main()
