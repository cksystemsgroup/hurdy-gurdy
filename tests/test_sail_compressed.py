"""RV64C on the Sail route (languages/sail/compressed, the fetch rework).

Adding the compressed extension brings the Sail-mediated route to RV64IMC
parity with the direct riscv-btor2 route, so the branch cross-check
(riscv-btor2 vs riscv-sail -> sail-btor2) is full-width. Covers: the independent
decompressor (agrees with the RISC-V one on the fixed RV64C encoding), the
pair's RV64C coverage, a direct interp differential (riscv vs Sail) on a
compressed program, and (gated on z3) branch agreement.
"""

import json
import struct
import unittest

from gurdy.languages.riscv import asm, casm
from gurdy.languages.riscv import compressed as rv_compressed
from gurdy.languages.riscv.interp import image_from_bytes
from gurdy.languages.riscv.interp import run as riscv_run
from gurdy.languages.sail import compressed as sail_compressed
from gurdy.languages.sail.interp import run as sail_run
from gurdy.pairs.btor2_smtlib import reach
from gurdy.pairs.riscv_btor2 import translate as rv_btor2
from gurdy.pairs.riscv_sail import translate as riscv_sail
from gurdy.pairs.sail_btor2 import translate as sail_btor2
from gurdy.pairs.sail_btor2.inventory import RV64C_PROBES, coverage

_RV64C = {
    "C.ADDI4SPN": casm.c_addi4spn(8, 16), "C.LW": casm.c_lw(8, 9, 8), "C.LD": casm.c_ld(8, 9, 16),
    "C.SW": casm.c_sw(8, 9, 8), "C.SD": casm.c_sd(8, 9, 16), "C.ADDI": casm.c_addi(10, -3),
    "C.ADDIW": casm.c_addiw(10, 7), "C.LI": casm.c_li(10, 5), "C.LUI": casm.c_lui(10, 1),
    "C.ADDI16SP": casm.c_addi16sp(32), "C.SRLI": casm.c_srli(8, 3), "C.SRAI": casm.c_srai(8, 3),
    "C.ANDI": casm.c_andi(8, 6), "C.SUB": casm.c_sub(8, 9), "C.XOR": casm.c_xor(8, 9),
    "C.OR": casm.c_or(8, 9), "C.AND": casm.c_and(8, 9), "C.SUBW": casm.c_subw(8, 9),
    "C.ADDW": casm.c_addw(8, 9), "C.J": casm.c_j(0x40), "C.BEQZ": casm.c_beqz(8, 0x20),
    "C.BNEZ": casm.c_bnez(8, -0x10), "C.SLLI": casm.c_slli(10, 4), "C.LWSP": casm.c_lwsp(10, 16),
    "C.LDSP": casm.c_ldsp(10, 32), "C.SWSP": casm.c_swsp(10, 16), "C.SDSP": casm.c_sdsp(10, 32),
    "C.JR": casm.c_jr(5), "C.MV": casm.c_mv(11, 10), "C.JALR": casm.c_jalr(5),
    "C.ADD": casm.c_add(11, 10), "C.EBREAK": casm.c_ebreak(),
}


def _image(*halfs: int):
    code = b"".join(struct.pack("<H", h & 0xFFFF) for h in halfs) + struct.pack("<I", asm.ecall())
    return image_from_bytes(code)


def _z3() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except ImportError:
        return False


class TestDecompressor(unittest.TestCase):
    def test_independent_expansion_matches_riscv(self):
        # the RV64C encoding is a fixed spec, so the Sail realization's own
        # decompressor must agree with the RISC-V one on every construct.
        for name, c in _RV64C.items():
            self.assertTrue(sail_compressed.is_compressed(c), name)
            self.assertEqual(sail_compressed.expand(c), rv_compressed.expand(c), name)

    def test_reserved_aborts(self):
        from gurdy.core.errors import Unsupported
        with self.assertRaises(Unsupported):
            sail_compressed.expand(0x0000)  # illegal


class TestCoverage(unittest.TestCase):
    def test_rv64c_covered(self):
        report = coverage()
        self.assertEqual(report.missing, {})
        self.assertEqual(report.total, 95)  # 63 RV64IM + 32 RV64C
        for name in RV64C_PROBES:
            self.assertIn(name, report.covered)


class TestInterpDifferential(unittest.TestCase):
    def test_riscv_vs_sail_on_compressed_program(self):
        # c.li x10,5 ; c.li x11,3 ; c.add x10,x11 ; c.mv x12,x10 ; ecall
        image = _image(casm.c_li(10, 5), casm.c_li(11, 3),
                       casm.c_add(10, 11), casm.c_mv(12, 10))
        rv = list(riscv_run(image))
        sail = list(sail_run(json.loads(riscv_sail({"image": image, "init_regs": {}}).decode())))
        obs = ("pc", "halted", *(f"x{r}" for r in range(1, 32)))
        proj = lambda t: [{k: s[k] for k in obs if k in s} for s in t]
        self.assertEqual(proj(rv), proj(sail))          # full trace agreement
        self.assertEqual(sail[-2]["x10"], 8)            # 5 + 3
        self.assertEqual(sail[-2]["x12"], 8)            # mv


@unittest.skipUnless(_z3(), "z3 not installed")
class TestBranchAgreement(unittest.TestCase):
    def _both(self, val):
        image = _image(casm.c_li(10, 5), casm.c_addi(10, 3))   # x10 = 8
        prop = {"reg_eq": [10, val]}
        direct = reach(rv_btor2({"image": image, "init_regs": {}, "property": prop}), 4)
        via = reach(sail_btor2(riscv_sail({"image": image, "init_regs": {}, "property": prop})), 4)
        return direct["verdict"], via["verdict"]

    def test_compressed_branch_agrees(self):
        d, v = self._both(8)
        self.assertEqual(d, v)                          # both reachable
        self.assertEqual(d.value, "reachable")
        d2, v2 = self._both(99)
        self.assertEqual(d2, v2)                        # both unreachable
        self.assertEqual(d2.value, "unreachable")


if __name__ == "__main__":
    unittest.main()
