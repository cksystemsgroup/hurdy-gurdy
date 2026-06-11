"""`Builder.slice` is self-validating: a BTOR2 slice's result sort width must
equal hi - lo + 1.

This closes the 2026-06-06 pono-strictness finding: a width-mismatched slice
(e.g. `slice bv32 <op> 34 0` — a 35-bit range into a 32-bit sort) is BTOR2 that
z3/bitwuzla tolerate silently but pono rejects. The guard makes it impossible to
emit such a slice — it raises at translation time instead.
"""

from __future__ import annotations

import pytest

from gurdy.pairs.riscv_btor2.translation.builder import Builder


def _operand() -> tuple[Builder, int]:
    b = Builder()
    return b, b.const("bv64", 0)


def test_correct_slice_widths_ok():
    b, v = _operand()
    # width == hi - lo + 1 for each
    assert b.slice("bv32", v, 31, 0) > 0
    assert b.slice("bv8", v, 7, 0) > 0
    assert b.slice("bv6", v, 5, 0) > 0
    assert b.slice("bv64", v, 127, 64) > 0  # high slice of a 128-bit product


def test_width_mismatch_raises():
    b, v = _operand()
    # the finding's exact shape: 35-bit range [34:0] declared as bv32
    with pytest.raises(ValueError, match="does not match"):
        b.slice("bv32", v, 34, 0)
    # off-by-one the other way
    with pytest.raises(ValueError, match="does not match"):
        b.slice("bv8", v, 6, 0)  # 7-bit range into bv8


def test_inverted_or_negative_range_raises():
    b, v = _operand()
    with pytest.raises(ValueError, match="valid bit range"):
        b.slice("bv8", v, 0, 5)
    with pytest.raises(ValueError, match="valid bit range"):
        b.slice("bv8", v, 7, -1)
