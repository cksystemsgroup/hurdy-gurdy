"""The fault-injection harness (tools/fault_injection.py), one mutant end
to end: a systematic sext->uext mis-lowering (incident I2's family) must be
caught by the square gate — the conjoined probe suite — and a mutation that
changes nothing must be reported inapplicable.

The full 55-mutant experiment is the harvest's job (--only escape); this
keeps the mechanism honest in the suite at ~seconds cost."""

import importlib.util
import unittest
from pathlib import Path


def _load_tool(name: str):
    path = Path(__file__).resolve().parent.parent / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name] = mod   # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(mod)
    return mod


class TestFaultInjection(unittest.TestCase):
    def test_sext_to_uext_mutant_is_caught_by_the_square_gate(self):
        fi = _load_tool("fault_injection")
        import gurdy.pairs.riscv_btor2  # noqa: F401 (registers the pair)
        from gurdy.core import registry

        probes = registry.get_pair("riscv-btor2").probes
        mutant = fi.Mutation("uniform:sext->uext", "op-swap", "sext", "uext")
        self.assertTrue(fi._applicable(mutant, probes))
        caught = fi._gate_square(mutant, probes)
        self.assertIsNotNone(caught)
        self.assertTrue(caught.startswith("square:"), caught)

    def test_unmatched_rule_is_inapplicable(self):
        fi = _load_tool("fault_injection")
        import gurdy.pairs.riscv_btor2  # noqa: F401
        from gurdy.core import registry

        probes = registry.get_pair("riscv-btor2").probes
        mutant = fi.Mutation("uniform:nosuch", "op-swap", "nosuchop", "add")
        self.assertFalse(fi._applicable(mutant, probes))

    def test_srl_to_sra_mutant_is_caught_since_probe_hardening(self):
        # I23's regression: the round-1 escape. With mixed-sign operands the
        # SRLI/SRL probes distinguish logical from arithmetic shifts.
        fi = _load_tool("fault_injection")
        import gurdy.pairs.riscv_btor2  # noqa: F401
        from gurdy.core import registry

        probes = registry.get_pair("riscv-btor2").probes
        mutant = fi.Mutation("uniform:srl->sra", "op-swap", "srl", "sra")
        caught = fi._gate_square(mutant, probes)
        self.assertIsNotNone(caught)
        self.assertTrue(caught.startswith("square:"), caught)


if __name__ == "__main__":
    unittest.main()
