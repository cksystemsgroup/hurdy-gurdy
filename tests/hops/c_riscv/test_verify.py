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


def test_to_cbmc_dialect_rewrites_trap_idiom():
    out = to_cbmc_dialect(_BARE_METAL)
    # _start -> main; trap-call -> __CPROVER_assert(!(cond), ...).
    assert "int main(void)" in out
    assert "void _start(void)" not in out
    assert '__CPROVER_assert(!(c != 12), "trap reachable");' in out
    # trap decl/def and inline asm are stripped.
    assert "extern void trap" not in out
    assert "void trap(void) {" not in out
    assert "__asm__" not in out
    assert "__builtin_unreachable" not in out


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
