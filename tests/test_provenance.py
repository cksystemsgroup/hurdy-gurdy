"""Author-diversity provenance (tools/provenance.py) — Phase 7 of the scaling
rollout (SCALING.md §9). Pure engine, git-free tests.
"""

import importlib.util
import pathlib
import sys
import unittest


def _load():
    path = pathlib.Path(__file__).resolve().parent.parent / "tools" / "provenance.py"
    spec = importlib.util.spec_from_file_location("provenance", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["provenance"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestProvenance(unittest.TestCase):
    def setUp(self):
        self.pr = _load()
        self.ledger = self.pr.Ledger(
            interpreter_contributions={"builder-B": ["riscv"]},
            external_artifacts={"sail-riscv-model", "riscv-prose-manual"},
        )

    def diverse_record(self, **over):
        rec = {
            "pair": "riscv-btor2", "source": "riscv", "target": "btor2",
            "attested_by": "coordinator", "requires_diversity": True,
            "legs": [
                {"role": "translator", "agent": "builder-A", "model_family": "claude",
                 "semantic_artifact": "riscv-prose-manual"},
                {"role": "corroborator", "agent": "builder-C", "model_family": "gpt",
                 "semantic_artifact": "sail-riscv-model"},
            ],
        }
        rec.update(over)
        return rec

    # --- OK ----------------------------------------------------------------

    def test_diverse_attested_record_is_ok(self):
        v, reasons = self.pr.check(self.diverse_record(), self.ledger)
        self.assertEqual(v, self.pr.OK, reasons)

    def test_single_leg_non_corroborated_pair_is_ok(self):
        # A single-artifact checked pair (evm-btor2) needs attestation + separation
        # but not two artifact-disjoint legs.
        rec = {"pair": "evm-btor2", "source": "evm", "target": "btor2",
               "attested_by": "coordinator", "requires_diversity": False,
               "legs": [{"role": "translator", "agent": "builder-A",
                         "model_family": "claude", "semantic_artifact": "evm-yellow-paper"}]}
        v, reasons = self.pr.check(rec, self.ledger)
        self.assertEqual(v, self.pr.OK, reasons)

    # --- REJECT ------------------------------------------------------------

    def test_self_reported_is_rejected(self):
        v, reasons = self.pr.check(self.diverse_record(attested_by="builder-A"),
                                   self.ledger)
        self.assertEqual(v, self.pr.REJECT)
        self.assertTrue(any("coordinator-attested" in r for r in reasons))

    def test_same_semantic_artifact_is_rejected(self):
        rec = self.diverse_record(legs=[
            {"role": "translator", "agent": "builder-A", "model_family": "claude",
             "semantic_artifact": "riscv-prose-manual"},
            {"role": "corroborator", "agent": "builder-C", "model_family": "gpt",
             "semantic_artifact": "riscv-prose-manual"},   # same artifact!
        ])
        v, reasons = self.pr.check(rec, self.ledger)
        self.assertEqual(v, self.pr.REJECT)
        self.assertTrue(any("same semantic artifact" in r for r in reasons))

    def test_same_model_family_is_rejected(self):
        rec = self.diverse_record(legs=[
            {"role": "translator", "agent": "builder-A", "model_family": "claude",
             "semantic_artifact": "riscv-prose-manual"},
            {"role": "corroborator", "agent": "builder-C", "model_family": "claude",
             "semantic_artifact": "sail-riscv-model"},     # same family!
        ])
        v, reasons = self.pr.check(rec, self.ledger)
        self.assertEqual(v, self.pr.REJECT)
        self.assertTrue(any("model family" in r for r in reasons))

    def test_interpreter_pair_separation_violation_is_rejected(self):
        # builder-B contributed the riscv interpreter (per the ledger) and here
        # also authors a riscv pair leg.
        rec = self.diverse_record(legs=[
            {"role": "translator", "agent": "builder-B", "model_family": "claude",
             "semantic_artifact": "riscv-prose-manual"},
            {"role": "corroborator", "agent": "builder-C", "model_family": "gpt",
             "semantic_artifact": "sail-riscv-model"},
        ])
        v, reasons = self.pr.check(rec, self.ledger)
        self.assertEqual(v, self.pr.REJECT)
        self.assertTrue(any("contributed interpreter" in r for r in reasons))

    def test_requires_diversity_with_one_leg_is_rejected(self):
        rec = self.diverse_record(legs=[self.diverse_record()["legs"][0]])
        v, reasons = self.pr.check(rec, self.ledger)
        self.assertEqual(v, self.pr.REJECT)

    # --- ESCALATE ----------------------------------------------------------

    def test_unregistered_external_artifact_escalates(self):
        rec = self.diverse_record(legs=[
            {"role": "translator", "agent": "builder-A", "model_family": "claude",
             "semantic_artifact": "riscv-prose-manual"},
            {"role": "corroborator", "agent": "builder-C", "model_family": "gpt",
             "semantic_artifact": "builder-C-private-notes"},   # not registered external
        ])
        v, reasons = self.pr.check(rec, self.ledger)
        self.assertEqual(v, self.pr.ESCALATE)
        self.assertTrue(any("not a registered external artifact" in r for r in reasons))

    def test_reject_dominates_escalate(self):
        # An unregistered artifact (ESCALATE) AND a self-report (REJECT) -> REJECT.
        rec = self.diverse_record(attested_by="builder-A", legs=[
            {"role": "translator", "agent": "builder-A", "model_family": "claude",
             "semantic_artifact": "riscv-prose-manual"},
            {"role": "corroborator", "agent": "builder-C", "model_family": "gpt",
             "semantic_artifact": "unregistered"},
        ])
        v, _ = self.pr.check(rec, self.ledger)
        self.assertEqual(v, self.pr.REJECT)


if __name__ == "__main__":
    unittest.main()
