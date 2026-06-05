"""Tests for the c-riscv CBMC verifier hop (the checked-tier differential).

``to_cbmc_dialect``, ``parse_cbmc_verdict``, and ``classify_differential``
are pure and tested without docker. ``cbmc_verify`` is docker-guarded like
the rest of the hop (CBMC runs in the pinned image).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gurdy.hops.c_riscv import (
    classify_differential,
    parse_cbmc_verdict,
    to_cbmc_dialect,
    toolchain_available,
)

REPO = Path(__file__).resolve().parents[3]
CORPUS = REPO / "bench" / "riscv-btor2" / "corpus"


# ---------------------------------------------------------------------------
# Pure: dialect rewrite
# ---------------------------------------------------------------------------

_BARE_METAL = """\
extern void trap(void) __attribute__((noreturn));
void trap(void) { __asm__ volatile ("ebreak"); }
void _start(void) {
    int c = 5 + 7;
    if (c != 12) trap();
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
"""


def test_to_cbmc_dialect_rewrites_trap_def_handwritten():
    out = to_cbmc_dialect(_BARE_METAL)
    # _start -> main; the trap *definition* becomes the assertion, so every
    # path that reaches trap is a CBMC assertion failure.
    assert "int main(void)" in out
    assert "void _start(void)" not in out
    assert '__CPROVER_assert(0, "trap reachable");' in out
    # the call site is preserved (it now calls the asserting trap).
    assert "if (c != 12) trap();" in out
    # noreturn is dropped (trap returns after the assert); asm / builtin gone.
    assert "noreturn" not in out
    assert "__asm__" not in out
    assert "__builtin_unreachable" not in out


# svcomp-extracted shape: macro-based property + register-asm symbolic input.
_SVCOMP = """\
extern void trap(void) __attribute__((noreturn));
#define reach_error()        trap()
#define abort()              trap()
#define __VERIFIER_assert(c) do { if (!(c)) trap(); } while (0)

int task_main(unsigned int v0) {
    __VERIFIER_assert(v0 != 0U);
    if (v0 == 1U) { goto ERROR; }
    return 0;
    ERROR: {reach_error();abort();}
}

void _start(void) {
    register unsigned int v0 __asm__("a0");
    __asm__ volatile ("" : "=r"(v0));
    task_main(v0);
    __asm__ volatile ("ebreak");
}

void trap(void) {
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
"""


def test_to_cbmc_dialect_handles_svcomp_shape():
    out = to_cbmc_dialect(_SVCOMP)
    # Entry + asserting trap def.
    assert "int main(void)" in out
    assert "void _start(void)" not in out
    assert '__CPROVER_assert(0, "trap reachable");' in out
    # The property macros are preserved (they resolve to the asserting trap),
    # so CBMC checks the real reach_error/__VERIFIER_assert paths.
    assert "#define __VERIFIER_assert(c)" in out
    assert "reach_error()" in out
    # The register-asm binding is stripped, leaving an uninitialised (=> nondet
    # in CBMC) local; no inline asm or register-binding survives.
    assert 'register unsigned int v0 ;' in out or "register unsigned int v0;" in out
    assert '__asm__("a0")' not in out
    assert "volatile" not in out
    assert "noreturn" not in out


# ---------------------------------------------------------------------------
# Pure: verdict parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("...\nVERIFICATION SUCCESSFUL\n", "unreachable"),
        ("...\nVERIFICATION FAILED\n", "reachable"),
        ("VERIFICATION INCONCLUSIVE: unwinding assertion\n", "unknown"),
        ("nothing useful here\n", "unknown"),
    ],
)
def test_parse_cbmc_verdict(text, expected):
    verdict, _notes = parse_cbmc_verdict(text)
    assert verdict == expected


def test_parse_cbmc_verdict_failed_beats_successful():
    # A multi-property run can print both; FAILED (any violation) wins.
    text = "VERIFICATION SUCCESSFUL\n...\nVERIFICATION FAILED\n"
    assert parse_cbmc_verdict(text)[0] == "reachable"


# ---------------------------------------------------------------------------
# Pure: differential classification truth table
# ---------------------------------------------------------------------------


def test_classify_agree():
    assert classify_differential("unreachable", "unreachable", lowering_sensitive=False) == "agree"
    assert classify_differential("reachable", "reachable", lowering_sensitive=True) == "agree"


def test_classify_expected_divergence_only_when_lowering_sensitive():
    # Disagreement on a lowering-sensitive task is the documented C-UB vs
    # RV64-defined gap, not a fault.
    assert (
        classify_differential("unreachable", "reachable", lowering_sensitive=True)
        == "expected-divergence"
    )


def test_classify_fault_when_not_lowering_sensitive():
    # Disagreement on a non-lowering-sensitive task is a real fault.
    assert (
        classify_differential("unreachable", "reachable", lowering_sensitive=False)
        == "fault"
    )


def test_classify_inconclusive_on_nondefinite():
    assert classify_differential("unknown", "reachable", lowering_sensitive=False) == "inconclusive"
    assert classify_differential("reachable", "unknown", lowering_sensitive=True) == "inconclusive"


# ---------------------------------------------------------------------------
# Docker-guarded: cbmc_verify in the pinned image
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not toolchain_available(),
    reason="pinned bench Docker image not available (CBMC verify needs it)",
)
class TestCbmcVerify:
    def _verify(self, task: str, bound: int):
        from gurdy.hops.c_riscv import cbmc_verify

        return cbmc_verify((CORPUS / task / "task.c").read_bytes(), bound=bound)

    def test_unreachable_task(self):
        r = self._verify("0100-c-add-trap-correct", 20)
        assert r.verdict == "unreachable"
        assert r.provenance.tool == "cbmc"
        assert r.provenance.digest.startswith("sha256:")
        assert r.provenance.unwind >= 30

    def test_reachable_task(self):
        r = self._verify("0101-c-add-trap-bug", 20)
        assert r.verdict == "reachable"

    def test_lowering_sensitive_task_diverges_as_expected(self):
        # CBMC flags the C-level signed overflow as UB -> reachable, while the
        # chain proves the trap unreachable via RV64 addw semantics.
        r = self._verify("0115-c-int-overflow", 60)
        assert r.verdict == "reachable"
        assert (
            classify_differential("unreachable", r.verdict, lowering_sensitive=True)
            == "expected-divergence"
        )

    # --- svcomp-extracted tasks: the dialect must handle the macro / goto /
    # register-asm shape, and CBMC must agree with the chain on the ones that
    # aren't lowering-sensitive UB. ---

    def test_svcomp_goto_idiom_reachable(self):
        # signext-1: the ERROR path (reach_error/abort macros via goto) is
        # taken -> assertion fails -> reachable, matching SV-COMP false.
        r = self._verify("0254-svcomp-signext-1", 60)
        assert r.verdict == "reachable"

    def test_svcomp_infinite_loop_macro_assert_unreachable(self):
        # jain-1-1: while(1) with __VERIFIER_assert(y!=0). The macro property
        # holds; --no-unwinding-assertions keeps the non-terminating loop from
        # producing a spurious FAILED, so CBMC agrees unreachable.
        r = self._verify("0275-svcomp-jain-1-1", 48)
        assert r.verdict == "unreachable"
        assert (
            classify_differential("unreachable", r.verdict, lowering_sensitive=True)
            == "agree"
        )

    def test_svcomp_macro_assert_agrees(self):
        r = self._verify("0279-svcomp-byte-add-1-1", 64)
        assert r.verdict == "unreachable"
