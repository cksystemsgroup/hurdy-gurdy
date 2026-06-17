"""c-riscv tests: the pinned compiler is reproducible (byte-identical ELF), the
compiled C runs on the shared RISC-V interpreter, and a property about the C
program is decided end-to-end through the long path -- via *both* independent
backend routes, which must agree (the opaque head re-established downstream)."""

import unittest

from gurdy.core import grade, route
from gurdy.core.registry import list_pairs
from gurdy.languages.riscv import load_elf, run

# Register the full route graph (c -> riscv -> {btor2, sail->btor2} -> smtlib).
import gurdy.pairs.btor2_smtlib  # noqa: F401
import gurdy.pairs.c_riscv       # noqa: F401
import gurdy.pairs.riscv_btor2   # noqa: F401
import gurdy.pairs.riscv_sail    # noqa: F401
import gurdy.pairs.sail_btor2    # noqa: F401
from gurdy.pairs.c_riscv import c_function_at, find_gcc, reproduce, translate
from gurdy.pairs.c_riscv.translate import CompilerUnavailable, compile_c


def _csrc(expr: str) -> str:
    return ("void _start(void){ long r=(" + expr + "); "
            "__asm__ volatile(\"mv a0,%0\\n\\tecall\\n\"::\"r\"(r):\"a0\"); for(;;){} }\n")


def _z3():
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


class TestCRiscvUnit(unittest.TestCase):
    def test_registered(self):
        self.assertIn("c-riscv", list_pairs())

    def test_compiler_unavailable_raises(self):
        with self.assertRaises(CompilerUnavailable):
            compile_c("void _start(void){}", gcc="/nonexistent/riscv64-gcc")


@unittest.skipUnless(find_gcc(), "riscv64-unknown-elf-gcc not installed")
class TestCRiscvToolchain(unittest.TestCase):
    def test_reproducible(self):
        src = _csrc("5*8 + 7")
        self.assertTrue(reproduce(src))
        self.assertEqual(translate({"source": src}), translate(src))

    def test_compiled_c_runs_on_interpreter(self):
        img = load_elf(translate(_csrc("5*8 + 7")))
        final = run(img, {"regs": {2: 1 << 20}})[-1]   # sp
        self.assertTrue(final["halted"])
        self.assertEqual(final["x10"], 47)             # a0
        self.assertEqual(c_function_at(img, img.entry), "_start")

    @unittest.skipUnless(_z3(), "z3 not installed")
    def test_long_path_decides_both_routes_agree(self):
        from gurdy.solvers.z3_smt import Z3SmtBackend

        def decide(artifact):
            return Z3SmtBackend().decide(artifact).verdict

        src = _csrc("5*8 + 7")   # a0 == 47
        routes = route.routes("c", "smtlib")
        self.assertEqual(len(routes), 2)   # direct + Sail-mediated

        def params(v):
            return {"riscv-btor2": {"property": {"reg_eq": [10, v]}},
                    "riscv-sail": {"property": {"reg_eq": [10, v]}},
                    "btor2-smtlib": {"k": 6}}

        from gurdy.core.solver import Verdict
        ba = grade.branch_agreement(routes, {"source": src}, decide, params(47))
        self.assertTrue(ba.agree)
        self.assertEqual(set(ba.verdicts.values()), {Verdict.REACHABLE})
        ba2 = grade.branch_agreement(routes, {"source": src}, decide, params(99))
        self.assertEqual(set(ba2.verdicts.values()), {Verdict.UNREACHABLE})


if __name__ == "__main__":
    unittest.main()
