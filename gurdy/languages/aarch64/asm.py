"""Minimal A64 instruction encoders for tests and coverage probes.

The in-scope constructs are encoded faithfully — ``ADD (immediate)``,
``SUB (immediate)``, and ``MOVZ`` (interpreter ``0.2``) — and a handful of
out-of-scope encodings (the flag-setting ``ADDS``/``SUBS``, the 32-bit forms,
the sibling move-wide variants ``MOVN``/``MOVK``) are provided so the coverage
inventory and rejection tests can exercise the typed ``Unsupported`` aborts
(BENCHMARKS.md §3). All words are 32-bit little-endian A64 instructions; the
interpreter reads them as integers, so these helpers return the integer word.
"""

from __future__ import annotations

# Register field value 31 means SP for the Add/subtract (immediate) class
# (and the zero register XZR for the Move-wide class).
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


def _move_wide(sf: int, opc: int, hw: int, imm16: int, rd: int) -> int:
    if not (0 <= imm16 < (1 << 16)):
        raise ValueError(f"imm16 out of range: {imm16}")
    return (
        (sf & 0x1) << 31
        | (opc & 0x3) << 29
        | 0b100101 << 23
        | (hw & 0x3) << 21
        | (imm16 & 0xFFFF) << 5
        | (rd & 0x1F)
    )


# --- in-scope encodings -----------------------------------------------------
def add_imm(rd: int, rn: int, imm12: int, lsl12: bool = False) -> int:
    """``ADD Xd|SP, Xn|SP, #imm12{, LSL #12}`` — in scope."""
    return _add_sub_imm(1, 0, 0, 1 if lsl12 else 0, imm12, rn, rd)


def sub_imm(rd: int, rn: int, imm12: int, lsl12: bool = False) -> int:
    """``SUB Xd|SP, Xn|SP, #imm12{, LSL #12}`` — in scope (interp 0.2)."""
    return _add_sub_imm(1, 1, 0, 1 if lsl12 else 0, imm12, rn, rd)


def movz(rd: int, imm16: int, hw: int = 0) -> int:
    """``MOVZ Xd, #imm16{, LSL #(16*hw)}`` for ``hw ∈ {0,1,2,3}`` — in scope
    (interp 0.2). ``opc = 0b10`` is MOVZ in the Move-wide class."""
    if hw not in (0, 1, 2, 3):
        raise ValueError(f"hw out of range: {hw}")
    return _move_wide(1, 0b10, hw, imm16, rd)


# --- out-of-scope encodings (used only to drive the Unsupported aborts) -----
def adds_imm(rd: int, rn: int, imm12: int) -> int:
    """Flag-setting ``ADDS`` (``S = 1``) — out of scope."""
    return _add_sub_imm(1, 0, 1, 0, imm12, rn, rd)


def subs_imm(rd: int, rn: int, imm12: int) -> int:
    """Flag-setting ``SUBS`` (``S = 1``) — out of scope."""
    return _add_sub_imm(1, 1, 1, 0, imm12, rn, rd)


def add_imm_w(rd: int, rn: int, imm12: int) -> int:
    """32-bit ``ADD Wd, Wn, #imm12`` (out of scope: ``sf = 0``)."""
    return _add_sub_imm(0, 0, 0, 0, imm12, rn, rd)


def sub_imm_w(rd: int, rn: int, imm12: int) -> int:
    """32-bit ``SUB Wd, Wn, #imm12`` (out of scope: ``sf = 0``)."""
    return _add_sub_imm(0, 1, 0, 0, imm12, rn, rd)


def movz_w(rd: int, imm16: int, hw: int = 0) -> int:
    """32-bit ``MOVZ Wd, #imm16`` (out of scope: ``sf = 0``)."""
    return _move_wide(0, 0b10, hw, imm16, rd)


def movn(rd: int, imm16: int, hw: int = 0) -> int:
    """``MOVN Xd, #imm16`` (out of scope: ``opc = 0b00``)."""
    return _move_wide(1, 0b00, hw, imm16, rd)


def movk(rd: int, imm16: int, hw: int = 0) -> int:
    """``MOVK Xd, #imm16`` (out of scope: ``opc = 0b11``; keeps other bits)."""
    return _move_wide(1, 0b11, hw, imm16, rd)
