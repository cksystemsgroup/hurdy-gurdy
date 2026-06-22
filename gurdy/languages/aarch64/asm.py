"""Minimal A64 instruction encoders for tests and coverage probes.

Only the in-scope ``ADD (immediate)`` is encoded faithfully; a couple of
out-of-scope encodings (``SUB``/``ADDS``/the 32-bit form) are provided so the
coverage inventory and rejection tests can exercise the typed ``Unsupported``
aborts (BENCHMARKS.md §3). All words are 32-bit little-endian A64 instructions;
the interpreter reads them as integers, so these helpers return the integer
word.
"""

from __future__ import annotations

# Register field value 31 means SP for the Add/subtract (immediate) class.
SP = 31


def _add_sub_imm(sf: int, op: int, s: int, shift: int, imm12: int,
                 rn: int, rd: int) -> int:
    if not (0 <= imm12 < (1 << 12)):
        raise ValueError(f"imm12 out of range: {imm12}")
    return (
        (sf & 0x1) << 31
        | (op & 0x1) << 30
        | (s & 0x1) << 29
        | 0b10001 << 24
        | (shift & 0x3) << 22
        | (imm12 & 0xFFF) << 10
        | (rn & 0x1F) << 5
        | (rd & 0x1F)
    )


def add_imm(rd: int, rn: int, imm12: int, lsl12: bool = False) -> int:
    """``ADD Xd|SP, Xn|SP, #imm12{, LSL #12}`` — the one in-scope construct."""
    return _add_sub_imm(1, 0, 0, 1 if lsl12 else 0, imm12, rn, rd)


# --- out-of-scope encodings (used only to drive the Unsupported aborts) -----
def sub_imm(rd: int, rn: int, imm12: int) -> int:
    return _add_sub_imm(1, 1, 0, 0, imm12, rn, rd)


def adds_imm(rd: int, rn: int, imm12: int) -> int:
    return _add_sub_imm(1, 0, 1, 0, imm12, rn, rd)


def add_imm_w(rd: int, rn: int, imm12: int) -> int:
    """32-bit ``ADD Wd, Wn, #imm12`` (out of scope: ``sf = 0``)."""
    return _add_sub_imm(0, 0, 0, 0, imm12, rn, rd)
