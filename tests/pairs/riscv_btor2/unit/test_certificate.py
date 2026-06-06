"""Tests for verify_certificate — inductive-invariant proved-path checker.

Uses hand-crafted BTOR2 models so no ELF, corpus, or Docker is needed.
"""

from textwrap import dedent

import pytest

from gurdy.pairs.riscv_btor2.lift.certificate import CertificateReport, verify_certificate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Simplest safe model: state r (8-bit), init to 0, stays at 0 forever.
# bad clause: r != 0 (never reachable).
_STAYS_ZERO = dedent("""\
    1 sort bitvec 1
    2 sort bitvec 8
    3 state 2 r
    4 zero 2
    5 init 2 3 4
    6 next 2 3 3
    7 eq 1 3 4
    8 not 1 7
    9 bad 8
""").encode()

# The correct inductive invariant: r == 0.
_INV_CORRECT = (
    "(declare-const s_3 (_ BitVec 8))\n"
    "(assert (= s_3 (_ bv0 8)))"
)

# Wrong invariant: r == 1 (not satisfied by the init state where r=0).
_INV_WRONG = (
    "(declare-const s_3 (_ BitVec 8))\n"
    "(assert (= s_3 (_ bv1 8)))"
)

_STATE_NIDS = [3]


# ---------------------------------------------------------------------------
# Passing case
# ---------------------------------------------------------------------------

def test_accepted_with_correct_invariant():
    report = verify_certificate(_STAYS_ZERO, _INV_CORRECT, _STATE_NIDS)
    assert report.accepted
    assert report.base_case_unsat
    assert report.inductive_step_unsat
    assert report.safety_unsat
    assert report.checker == "z3"
    assert report.reason is None


# ---------------------------------------------------------------------------
# Failing cases
# ---------------------------------------------------------------------------

def test_wrong_invariant_fails_base_case():
    # r==1 is not satisfied by init (r=0): init(r=0) ∧ ¬(r==1) is SAT.
    report = verify_certificate(_STAYS_ZERO, _INV_WRONG, _STATE_NIDS)
    assert not report.accepted
    assert not report.base_case_unsat


def test_wrong_state_nid_order_returns_mismatch_error():
    report = verify_certificate(_STAYS_ZERO, _INV_CORRECT, [999])
    assert not report.accepted
    assert report.reason is not None
    assert "mismatch" in report.reason


# ---------------------------------------------------------------------------
# CertificateReport.summary()
# ---------------------------------------------------------------------------

def test_summary_pass_contains_pass_and_checker():
    report = verify_certificate(_STAYS_ZERO, _INV_CORRECT, _STATE_NIDS)
    s = report.summary()
    assert "PASS" in s
    assert "z3" in s


def test_summary_fail_contains_fail_and_flag():
    report = verify_certificate(_STAYS_ZERO, _INV_WRONG, _STATE_NIDS)
    s = report.summary()
    assert "FAIL" in s
    assert "init" in s


def test_summary_accepted_false_reason_included():
    report = CertificateReport(
        accepted=False,
        base_case_unsat=True,
        inductive_step_unsat=False,
        safety_unsat=True,
        checker="z3",
        reason="synthetic test",
    )
    s = report.summary()
    assert "synthetic test" in s
    assert "Inv∧trans⇒Inv'" in s
