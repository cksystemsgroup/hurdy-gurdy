"""Tests for the P5 alignment oracle (bench/wasm-btor2/oracle_align.py).

Imports the oracle module via importlib so it can live in bench/ as a
standalone script while still being covered by the test suite.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest


# ---------------------------------------------------------------------------
# Import the oracle module
# ---------------------------------------------------------------------------

_ORACLE_PATH = (
    pathlib.Path(__file__).parents[3] / "bench" / "wasm-btor2" / "oracle_align.py"
)


def _load_oracle():
    import sys

    spec = importlib.util.spec_from_file_location("oracle_align", _ORACLE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["oracle_align"] = mod
    spec.loader.exec_module(mod)
    return mod


_oracle = _load_oracle()

run_oracle = _oracle.run_oracle
make_add_wasm = _oracle.make_add_wasm
AlignmentReport = _oracle.AlignmentReport
AlignmentMismatch = _oracle.AlignmentMismatch
ORACLE_VERSION = _oracle.ORACLE_VERSION


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


def test_oracle_version():
    assert ORACLE_VERSION == "1.0.0"


def test_make_add_wasm_returns_bytes():
    assert isinstance(make_add_wasm(), bytes)


def test_make_add_wasm_has_wasm_magic():
    assert make_add_wasm()[:4] == b"\x00asm"


# ---------------------------------------------------------------------------
# 0001-i32-add-wrap: agreement cases
# ---------------------------------------------------------------------------


def test_agreement_zero_zero():
    report = run_oracle((0, 0), bound=8)
    assert report.agrees, report.summary()


def test_agreement_small_ints():
    report = run_oracle((3, 5), bound=8)
    assert report.agrees, report.summary()


def test_agreement_wrap_max():
    # 0x7FFFFFFF + 1 wraps to 0x80000000
    report = run_oracle((0x7FFFFFFF, 1), bound=8)
    assert report.agrees, report.summary()


def test_agreement_all_ones():
    # 0xFFFFFFFF + 0xFFFFFFFF = 0xFFFFFFFE (wrap)
    report = run_oracle((0xFFFFFFFF, 0xFFFFFFFF), bound=8)
    assert report.agrees, report.summary()


def test_agreement_negative_param():
    # -1 interpreted as 0xFFFFFFFF in i32
    report = run_oracle((1, -1), bound=8)
    assert report.agrees, report.summary()


def test_agreement_asymmetric():
    report = run_oracle((100, 200), bound=8)
    assert report.agrees, report.summary()


# ---------------------------------------------------------------------------
# Report shape and properties
# ---------------------------------------------------------------------------


def test_steps_checked_positive():
    report = run_oracle((3, 5), bound=8)
    assert report.steps_checked > 0


def test_no_mismatches_on_agreement():
    report = run_oracle((0, 0), bound=8)
    assert report.mismatches == []


def test_report_agrees_property():
    report = run_oracle((3, 5))
    assert report.agrees is True


def test_summary_string_on_agreement():
    report = run_oracle((3, 5))
    s = report.summary()
    assert "agreement" in s
    assert "step" in s


def test_report_has_required_fields():
    report = run_oracle((0, 0))
    assert hasattr(report, "outcome")
    assert hasattr(report, "steps_checked")
    assert hasattr(report, "mismatches")


# ---------------------------------------------------------------------------
# Trap agreement: unreachable function
# ---------------------------------------------------------------------------


def _make_trap_wasm() -> bytes:
    """Single-param (i32 -> i32) function: unreachable; end."""

    def _uleb128(v: int) -> bytes:
        if v == 0:
            return bytes([0])
        result = []
        while v > 0:
            low7 = v & 0x7F
            v >>= 7
            if v > 0:
                low7 |= 0x80
            result.append(low7)
        return bytes(result)

    def _section(sid: int, data: bytes) -> bytes:
        return bytes([sid]) + _uleb128(len(data)) + data

    I32 = 0x7F
    body = b"\x00\x0B"  # unreachable; end
    type_body = bytes([1, 0x60, 1, I32, 1, I32])
    func_body = bytes([1, 0])
    name = b"main"
    export_body = bytes([1]) + _uleb128(len(name)) + name + bytes([0, 0])
    func_bytes = bytes([0]) + body
    code_body = bytes([1]) + _uleb128(len(func_bytes)) + func_bytes
    return (
        b"\x00asm\x01\x00\x00\x00"
        + _section(1, type_body)
        + _section(3, func_body)
        + _section(7, export_body)
        + _section(10, code_body)
    )


def test_trap_agrees():
    """Source traps at step 0; BTOR2 also fires trap at step 0."""
    wasm = _make_trap_wasm()
    report = run_oracle((42,), bound=4, wasm_bytes=wasm)
    assert report.agrees, report.summary()


def test_trap_steps_checked_is_one():
    """Source interpreter emits exactly 1 step for unreachable."""
    wasm = _make_trap_wasm()
    report = run_oracle((42,), bound=4, wasm_bytes=wasm)
    assert report.steps_checked == 1


def test_trap_no_mismatches():
    wasm = _make_trap_wasm()
    report = run_oracle((0,), bound=4, wasm_bytes=wasm)
    assert report.mismatches == []


# ---------------------------------------------------------------------------
# Bound parameter
# ---------------------------------------------------------------------------


def test_bound_limits_reasoning_steps():
    # The 4-instruction add function runs 4 source steps; bound=4 covers all.
    report = run_oracle((1, 2), bound=4)
    assert report.steps_checked <= 4
    assert report.agrees


def test_bound_one_still_agrees():
    report = run_oracle((7, 3), bound=1)
    assert report.agrees
