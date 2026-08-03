"""The pc-anchor reachability property (``pc_eq`` — ``reg_eq``'s sibling).

``pairs/riscv-btor2`` lowers ``{"property": {"pc_eq": addr}}`` to a ``bad``
that fires when control *reaches* ``addr``: pc holds it in a not-yet-halted
state. The halted guard is the semantic content — on halt the model freezes
pc at the fall-through address forever, so an unguarded ``pc == addr`` would
count an anchor that merely follows a halt as reached (exactly the layout
the SV-COMP scoping shim links: adjacent one-trap ``__assert_fail`` /
``abort``). Both lenses are exercised: the solver route (btor2-smtlib) and
the reference interpreter's post-step trace, which mirrors the same freeze.

The shim tests are the census's take-up (tools/scope_svcomp.py): the sound
anchor it identified — the shim's separate-TU ``__assert_fail``, whose call
sites ``-O2`` cannot inline away — is usable as a property today.
"""

import os
import sys
import unittest

from gurdy.core.solver import Verdict
from gurdy.languages.btor2 import corroborate_unreach
from gurdy.languages.riscv import asm, image_from_words, load_elf, run
from gurdy.pairs.c_riscv.translate import find_gcc
from gurdy.pairs.riscv_btor2 import square, translate

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir,
                                "tools"))
from scope_svcomp import compile_probe  # noqa: E402


def _has_z3() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


def _bad_lines(artifact: bytes) -> list[str]:
    return [ln for ln in artifact.decode("utf-8").splitlines()
            if ln.split()[1:2] == ["bad"]]


# [addi x1,x0,20; addi x2,x0,22; add x3,x1,x2; ecall] — straight line,
# every address executes.
_STRAIGHT = [asm.addi(1, 0, 20), asm.addi(2, 0, 22), asm.add(3, 1, 2),
             asm.ecall()]
# [beq x0,x0,+8; addi x1,x0,7; addi x2,x0,9; ecall] — the branch is always
# taken, so address 4 never executes.
_SKIPPED = [asm.beq(0, 0, 8), asm.addi(1, 0, 7), asm.addi(2, 0, 9),
            asm.ecall()]
# [addi x1,x0,1; ecall; ebreak] — the ecall halts and the model freezes pc
# at 8, the ebreak's address, without ever executing it.
_FREEZE = [asm.addi(1, 0, 1), asm.ecall(), asm.ebreak()]


def _program(words, anchor):
    return {"image": image_from_words(words),
            "property": {"pc_eq": anchor}}


class TestPcAnchorTranslate(unittest.TestCase):
    def test_bad_emitted_and_deterministic(self):
        art = translate(_program(_STRAIGHT, 8))
        self.assertEqual(len(_bad_lines(art)), 1)
        self.assertEqual(art, translate(_program(_STRAIGHT, 8)))
        self.assertEqual(_bad_lines(translate({"image": image_from_words(_STRAIGHT)})), [])

    def test_coexists_with_reg_eq(self):
        art = translate({"image": image_from_words(_STRAIGHT),
                         "property": {"reg_eq": [3, 42], "pc_eq": 8}})
        self.assertEqual(len(_bad_lines(art)), 2)

    def test_square_commutes_with_property(self):
        # The property adds a bad observable, not behavior: the commuting
        # square still holds under π.
        report = square(_program(_STRAIGHT, 8))
        self.assertTrue(report.ok, msg=str(report.divergence))


@unittest.skipUnless(_has_z3(), "z3 not installed")
class TestPcAnchorDecide(unittest.TestCase):
    def test_anchor_reached(self):
        from gurdy.pairs.btor2_smtlib import reach
        info = reach(translate(_program(_STRAIGHT, 8)), 6)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        self.assertTrue(info["witness_ok"])

    def test_entry_is_reached_by_the_initial_state(self):
        # The anchor at the entry fires in the initial state (pc starts
        # there, not-halted). The interpreter's post-step trace never shows
        # this state — a ground-truth derivation must treat the entry
        # specially, as square()'s one-cycle shift already does.
        from gurdy.pairs.btor2_smtlib import reach
        info = reach(translate(_program(_STRAIGHT, 0)), 2)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)

    def test_anchor_skipped_unreachable(self):
        from gurdy.pairs.btor2_smtlib import reach
        art = translate(_program(_SKIPPED, 4))
        self.assertEqual(reach(art, 8)["verdict"], Verdict.UNREACHABLE)
        self.assertTrue(corroborate_unreach(art, k=8))
        # Interpreter lens agrees: address 4 appears in no post-step row.
        self.assertFalse(any(row["pc"] == 4
                             for row in run(image_from_words(_SKIPPED))))

    def test_halt_freeze_is_not_reach(self):
        from gurdy.pairs.btor2_smtlib import reach
        # The trap the guard defuses, on the reference trace: pc freezes at
        # the ebreak's address in a *halted* row and never in a live one.
        trace = run(image_from_words(_FREEZE))
        self.assertTrue(any(row["pc"] == 8 and row["halted"] for row in trace))
        self.assertFalse(any(row["pc"] == 8 and not row["halted"] for row in trace))
        art = translate(_program(_FREEZE, 8))
        self.assertEqual(reach(art, 10)["verdict"], Verdict.UNREACHABLE)
        self.assertTrue(corroborate_unreach(art, k=10))
        # Positive control through the same machinery: the ecall's own
        # address is genuinely reached — the guard does not over-suppress.
        info = reach(translate(_program(_FREEZE, 4)), 10)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)


_TASK = """\
extern void __assert_fail(const char *, const char *, unsigned,
                          const char *);
void reach_error(void) {{ __assert_fail("0", "task.c", 3, "reach_error"); }}
int main(void) {{
  int x = 21;
  if (x + x == {rhs}) {{ reach_error(); }}
  return 0;
}}
"""

_SP = 1 << 20  # the pair's default stack pointer for compiled images


@unittest.skipUnless(find_gcc(), "riscv64-unknown-elf-gcc not installed")
@unittest.skipUnless(_has_z3(), "z3 not installed")
class TestSvcompShimAnchor(unittest.TestCase):
    """unreach-call in the census's own shape: task TU + scoping shim at the
    pinned FLAGS (-O2 inlines ``reach_error`` into main; the call into the
    separate-TU ``__assert_fail`` survives and anchors the property)."""

    def _elf(self, rhs: int) -> bytes:
        probe = compile_probe(_TASK.format(rhs=rhs).encode(), ".c",
                              find_gcc(), [])
        self.assertTrue(probe["link_ok"], msg=str(probe))
        return probe["elf"]

    def _decide(self, elf: bytes, k: int = 48):
        from gurdy.pairs.btor2_smtlib import reach
        image = load_elf(elf, entry_symbol="main")
        anchor = image.symbols["__assert_fail"]
        art = translate({"image": image, "init_regs": {2: _SP},
                         "property": {"pc_eq": anchor}})
        return anchor, art, reach(art, k)

    def test_called_anchor_reachable(self):
        elf = self._elf(rhs=42)
        anchor, _, info = self._decide(elf)
        self.assertEqual(info["verdict"], Verdict.REACHABLE)
        # Interpreter lens: a live (not-halted) row holds the anchor pc.
        trace = run(load_elf(elf, entry_symbol="main"), {"regs": {2: _SP}})
        self.assertTrue(any(row["pc"] == anchor and not row["halted"]
                            for row in trace))

    def test_uncalled_anchor_unreachable(self):
        elf = self._elf(rhs=43)
        anchor, art, info = self._decide(elf)
        self.assertEqual(info["verdict"], Verdict.UNREACHABLE)
        self.assertTrue(corroborate_unreach(art, k=48))
        trace = run(load_elf(elf, entry_symbol="main"), {"regs": {2: _SP}})
        self.assertFalse(any(row["pc"] == anchor and not row["halted"]
                             for row in trace))


if __name__ == "__main__":
    unittest.main()
