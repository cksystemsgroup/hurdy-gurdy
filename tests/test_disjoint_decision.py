"""The disjoint-decision branch (paper §6.2, Assumption 2): the same
question decided with fully disjoint stacks after the head — the direct
route's BTOR2 system natively by btormc, the via-Sail route through the
bridge and z3 — must agree; and the native adapter's bounded reading
(clean kmax exhaustion = unreachable within the bound) must never fire
on malformed input.

Gated on a native BTOR2 checker and z3."""

import unittest

from gurdy.core import route
from gurdy.core.solver import Verdict
from gurdy.languages.riscv import asm
from gurdy.languages.riscv.interp import image_from_words
from gurdy.solvers.native_btor2 import NativeBtor2Checker, find_btormc

import gurdy.pairs.riscv_btor2   # noqa: F401  (registers the pairs)
import gurdy.pairs.riscv_sail    # noqa: F401
import gurdy.pairs.sail_btor2    # noqa: F401
import gurdy.pairs.btor2_smtlib  # noqa: F401


def _z3() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(find_btormc(), "btormc not installed")
class TestDecideBounded(unittest.TestCase):
    def test_garbage_input_is_never_unreachable(self):
        # The exhaustion reading requires a CLEAN empty run; a parse error
        # must stay UNKNOWN (a malformed system silently reading as
        # unreachable would be a vacuous-check bug of the I9 family).
        v = NativeBtor2Checker().decide_bounded(b"this is not btor2\n", k=5)
        self.assertIsNot(v, Verdict.UNREACHABLE)

    def test_silently_broken_binary_is_not_trusted(self):
        # The exhaustion signal is SILENCE (exit 0, no output) — also what
        # a broken btormc build that swallows everything would produce. The
        # reachable canary (negative control) must reject it: a stub that
        # exits 0 with no output on every input yields UNKNOWN, never
        # bounded-unreachable.
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            stub = Path(d) / "btormc"
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
            old = os.environ.get("BTORMC")
            os.environ["BTORMC"] = str(stub)
            try:
                v = NativeBtor2Checker().decide_bounded(
                    "1 sort bitvec 1\n2 zero 1\n3 bad 2\n", k=2)
            finally:
                if old is None:
                    del os.environ["BTORMC"]
                else:
                    os.environ["BTORMC"] = old
        self.assertIs(v, Verdict.UNKNOWN)

    def test_real_btormc_passes_the_canary(self):
        # The control's dual: the real binary answers sat on the canary, so
        # genuine exhaustions are still trusted — a truly unreachable
        # one-bit system reads bounded-unreachable.
        v = NativeBtor2Checker().decide_bounded(
            "1 sort bitvec 1\n2 zero 1\n3 bad 2\n", k=2)
        self.assertIs(v, Verdict.UNREACHABLE)

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_native_direct_agrees_with_bridged_sail(self):
        native = NativeBtor2Checker()
        const = [asm.addi(1, 0, 42), 0x73]
        for target, expected in ((42, Verdict.REACHABLE),
                                 (99, Verdict.UNREACHABLE)):
            head = {"image": image_from_words(const), "init_regs": {},
                    "property": {"reg_eq": [1, target]}}
            btor = route.run_route(["riscv-btor2"], head)["artifact"]
            nv = native.decide_bounded(btor, k=4)
            from gurdy.solvers.z3_smt import Z3SmtBackend
            smt = route.run_route(
                ["riscv-sail", "sail-btor2", "btor2-smtlib"], head,
                {"btor2-smtlib": {"k": 4}})["artifact"]
            zv = Z3SmtBackend().decide(smt).verdict
            self.assertEqual(nv, expected)
            self.assertEqual(zv, expected)


if __name__ == "__main__":
    unittest.main()
