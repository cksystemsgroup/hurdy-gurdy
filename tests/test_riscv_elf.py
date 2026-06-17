"""ELF loading for the RISC-V interpreter (languages/riscv brief: "a program
is an ELF image").

Two angles: a real ``riscv64-unknown-elf-gcc`` binary loads and runs in the
interpreter (toolchain-gated), and a hermetic minimal ELF — whose executable
segment is exactly the code — flows through the whole riscv-btor2 pipeline
(commuting square + z3 decide), so ELF-loaded images are first-class inputs.
"""

import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from gurdy.languages.riscv import asm, image_from_words, load_elf, run
from gurdy.pairs.riscv_btor2 import square, translate as rv_translate


def _build_elf(words, base=0x10000):
    """A minimal static RISC-V ELF64 whose single PF_R|PF_X PT_LOAD segment is
    exactly ``words`` (so code_lo == entry == base — no headers in the code)."""
    code = b"".join(struct.pack("<I", w & 0xFFFFFFFF) for w in words)
    ehsize, phentsize = 64, 56
    e_ident = b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\x00" * 8
    ehdr = e_ident + struct.pack(
        "<HHIQQQIHHHHHH",
        2, 243, 1, base,        # e_type=EXEC, e_machine=RISC-V, e_version, e_entry
        ehsize, 0, 0,           # e_phoff, e_shoff, e_flags
        ehsize, phentsize, 1,   # e_ehsize, e_phentsize, e_phnum
        0, 0, 0,                # e_shentsize, e_shnum, e_shstrndx
    )
    data_off = ehsize + phentsize
    phdr = struct.pack(
        "<IIQQQQQQ",
        1, 0x5,                 # p_type=PT_LOAD, p_flags=R|X
        data_off, base, base,   # p_offset, p_vaddr, p_paddr
        len(code), len(code), 0x1000,
    )
    return ehdr + phdr + code


def _gcc():
    return shutil.which("riscv64-unknown-elf-gcc")


class TestRiscvElf(unittest.TestCase):
    def test_rejects_non_elf(self):
        with self.assertRaises(ValueError):
            load_elf(b"not an elf at all")

    def test_rejects_elf32(self):
        from gurdy.core.errors import Unsupported
        bad = bytearray(_build_elf([asm.ecall()]))
        bad[4] = 1  # EI_CLASS = ELFCLASS32
        with self.assertRaises(Unsupported):
            load_elf(bytes(bad))

    def test_hermetic_load_matches_image_from_words(self):
        words = [asm.addi(1, 0, 20), asm.addi(2, 0, 22), asm.add(3, 1, 2),
                 asm.mul(4, 1, 2), asm.ecall()]
        img = load_elf(_build_elf(words))
        self.assertEqual(img.entry, 0x10000)
        self.assertEqual(img.code_lo, 0x10000)
        # behavior is identical to the hand-built image at the same base
        ref = run(image_from_words(words, base=0x10000))
        self.assertEqual(run(img), ref)
        self.assertEqual(run(img)[-1]["x3"], 42)
        self.assertEqual(run(img)[-1]["x4"], 440)

    def test_hermetic_elf_through_square(self):
        words = [asm.addi(1, 0, 7), asm.slli(1, 1, 3), asm.addi(2, 0, -1),
                 asm.xor(3, 1, 2), asm.add(4, 1, 2), asm.ecall()]
        report = square({"image": load_elf(_build_elf(words)), "init_regs": {}})
        self.assertTrue(report.ok, msg=str(report.divergence))

    def test_hermetic_elf_decide(self):
        try:
            import z3  # noqa: F401
        except Exception:
            self.skipTest("z3 not installed")
        from gurdy.core.solver import Verdict
        from gurdy.pairs.btor2_smtlib import reach

        words = [asm.addi(1, 0, 20), asm.addi(2, 0, 22), asm.add(3, 1, 2), asm.ecall()]
        program = {"image": load_elf(_build_elf(words)), "property": {"reg_eq": [3, 42]}}
        info = reach(rv_translate(program), 5)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])

    @unittest.skipUnless(_gcc(), "riscv64-unknown-elf-gcc not installed")
    def test_real_toolchain_elf(self):
        src = (
            ".section .text\n.globl _start\n_start:\n"
            "  li a0, 5\n  li a1, 37\n  add a2, a0, a1\n  mul a3, a0, a1\n  ecall\n"
        )
        with tempfile.TemporaryDirectory() as d:
            s, elf = Path(d) / "p.s", Path(d) / "p.elf"
            s.write_text(src)
            subprocess.run(
                [_gcc(), "-nostdlib", "-nostartfiles", "-march=rv64im", "-mabi=lp64",
                 "-o", str(elf), str(s)],
                check=True, capture_output=True,
            )
            img = load_elf(elf.read_bytes())
        final = run(img)[-1]
        self.assertTrue(final["halted"])
        self.assertEqual(final["x12"], 42)    # a2 = 5 + 37
        self.assertEqual(final["x13"], 185)   # a3 = 5 * 37  (M-extension)


if __name__ == "__main__":
    unittest.main()
