"""Tests for verify_kind_certificate — k-induction proved-path checker.

Uses hand-crafted BTOR2 models so no ELF, corpus, or Docker is needed.
"""

from textwrap import dedent

from gurdy.pairs.riscv_btor2.lift.kind_certificate import (
    KindCertificateReport,
    verify_kind_certificate,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Safe model: r stays 0 forever.  bad: r != 0 (never reachable).
# k=0 is sufficient because the property is directly inductive.
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

# Unsafe model: 8-bit counter starts at 0, increments by 1.
# bad: c == 5 — reachable at step 5.
_COUNTER_REACHES_5 = dedent("""\
    1 sort bitvec 1
    2 sort bitvec 8
    3 state 2 c
    4 zero 2
    5 init 2 3 4
    6 one 2
    7 add 2 3 6
    8 next 2 3 7
    9 constd 2 5
    10 eq 1 3 9
    11 bad 10
""").encode()

# Model with no bad clause: trivially safe for any k.
_NO_BAD = dedent("""\
    1 sort bitvec 8
    2 state 1 r
    3 zero 1
    4 init 1 2 3
    5 next 1 2 2
""").encode()


# ---------------------------------------------------------------------------
# Passing cases
# ---------------------------------------------------------------------------

def test_k0_safe_model_accepted():
    report = verify_kind_certificate(_STAYS_ZERO, k=0)
    assert report.accepted
    assert report.k == 0
    assert report.base_case_unsat
    assert report.step_case_unsat


def test_no_bad_clause_accepted_vacuously():
    report = verify_kind_certificate(_NO_BAD, k=0)
    assert report.accepted


# ---------------------------------------------------------------------------
# Failing cases
# ---------------------------------------------------------------------------

def test_reachable_bad_step_fails_at_k0():
    # BASE passes (init trace 0 can't hit bad=5).
    # STEP fails: arbitrary c_0=4 → c_1=5 witnesses bad reachability.
    report = verify_kind_certificate(_COUNTER_REACHES_5, k=0)
    assert not report.accepted
    assert report.base_case_unsat
    assert not report.step_case_unsat


def test_negative_k_rejected():
    report = verify_kind_certificate(_STAYS_ZERO, k=-1)
    assert not report.accepted
    assert report.reason is not None


# ---------------------------------------------------------------------------
# KindCertificateReport.summary()
# ---------------------------------------------------------------------------

def test_summary_pass_contains_k():
    report = verify_kind_certificate(_STAYS_ZERO, k=0)
    assert "PASS" in report.summary()
    assert "k=0" in report.summary()


def test_summary_fail_step_contains_step_failed():
    report = verify_kind_certificate(_COUNTER_REACHES_5, k=0)
    s = report.summary()
    assert "FAIL" in s
    assert "STEP" in s


def test_summary_fail_base_contains_base_failed():
    report = KindCertificateReport(
        accepted=False, k=3,
        base_case_unsat=False, step_case_unsat=True,
    )
    s = report.summary()
    assert "BASE FAILED" in s


def test_summary_reason_included():
    report = KindCertificateReport(
        accepted=False, k=0,
        base_case_unsat=False, step_case_unsat=False,
        reason="timeout",
    )
    assert "timeout" in report.summary()
