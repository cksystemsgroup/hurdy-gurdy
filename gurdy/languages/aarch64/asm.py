"""Minimal A64 instruction encoders for tests and coverage probes.

The in-scope constructs are encoded faithfully — ``ADD (immediate)``,
``SUB (immediate)``, ``MOVZ`` (interpreter ``0.2``), and ``SUBS``/``CMP``
(immediate) + ``B.cond`` (interpreter ``0.3``) — and a handful of out-of-scope
encodings (the flag-setting ``ADDS``, the 32-bit forms, the sibling move-wide
variants ``MOVN``/``MOVK``) are provided so the coverage inventory and rejection
tests can exercise the typed ``Unsupported`` aborts (BENCHMARKS.md §3). All words
are 32-bit little-endian A64 instructions; the interpreter reads them as
integers, so these helpers return the integer word.
"""

from __future__ import annotations

# Register field value 31 means SP for the Add/subtract (immediate) class
# (and the zero register XZR for the Move-wide class).
SP = 31
XZR = 31

# A64 condition codes (the 4-bit `cond` field of B.cond).
COND = {
    "EQ": 0b0000, "NE": 0b0001, "CS": 0b0010, "HS": 0b0010, "CC": 0b0011,
    "LO": 0b0011, "MI": 0b0100, "PL": 0b0101, "VS": 0b0110, "VC": 0b0111,
    "HI": 0b1000, "LS": 0b1001, "GE": 0b1010, "LT": 0b1011, "GT": 0b1100,
    "LE": 0b1101, "AL": 0b1110, "NV": 0b1111,
}


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


def subs_imm(rd: int, rn: int, imm12: int, lsl12: bool = False) -> int:
    """``SUBS Xd, Xn|SP, #imm12{, LSL #12}`` — in scope (interp 0.3): the
    flag-setting subtract (``op = 1, S = 1``)."""
    return _add_sub_imm(1, 1, 1, 1 if lsl12 else 0, imm12, rn, rd)


def cmp_imm(rn: int, imm12: int, lsl12: bool = False) -> int:
    """``CMP Xn|SP, #imm12{, LSL #12}`` = ``SUBS XZR, Xn, #imm12`` — in scope
    (interp 0.3): the result is discarded (Rd = XZR), only NZCV is set."""
    return subs_imm(XZR, rn, imm12, lsl12=lsl12)


def _bcond_word(cond: int, off_bytes: int) -> int:
    """``B.cond`` (conditional branch): ``0101010 0 imm19 0 cond``.

    ``off_bytes`` is the signed byte displacement from the branch's own pc; it
    must be a multiple of 4 and fit a signed 19-bit instruction offset."""
    if off_bytes % 4 != 0:
        raise ValueError(f"branch offset must be 4-byte aligned: {off_bytes}")
    imm19 = off_bytes // 4
    if not (-(1 << 18) <= imm19 < (1 << 18)):
        raise ValueError(f"branch offset out of range: {off_bytes}")
    return (
        0b01010100 << 24
        | (imm19 & 0x7FFFF) << 5
        | (cond & 0xF)
    )


def b_cond(cond: str | int, off_bytes: int) -> int:
    """``B.cond <label>`` — in scope (interp 0.3). ``cond`` is a name
    (``"EQ"``/``"NE"``/…) or a 4-bit code; ``off_bytes`` is the signed byte
    offset from this instruction to the target."""
    c = COND[cond] if isinstance(cond, str) else int(cond)
    return _bcond_word(c, off_bytes)


# --- out-of-scope encodings (used only to drive the Unsupported aborts) -----
def adds_imm(rd: int, rn: int, imm12: int) -> int:
    """Flag-setting ``ADDS`` (``S = 1, op = 0``) — out of scope (this round adds
    the NZCV write for subtraction only; ``ADDS`` stays a typed abort)."""
    return _add_sub_imm(1, 0, 1, 0, imm12, rn, rd)


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
