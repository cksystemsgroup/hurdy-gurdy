"""Minimal A64 instruction encoders for tests and coverage probes.

The in-scope constructs are encoded faithfully — ``ADD (immediate)``,
``SUB (immediate)``, ``MOVZ`` (interpreter ``0.2``), ``SUBS``/``CMP``
(immediate) + ``B.cond`` (interpreter ``0.3``), the unconditional branch
``B``/``BL`` + the flag-setting ``ADDS``/``CMN`` (immediate) (interpreter
``0.4``), the 64-bit unsigned-offset ``LDR``/``STR`` (interpreter ``0.5``), and the
**32-bit (W-register) forms** of the ALU/flag-setting immediate instructions —
``ADD``/``SUB``/``MOVZ`` W and ``SUBS``/``CMP``/``ADDS``/``CMN`` W (interpreter
``0.6``) — and a handful of out-of-scope encodings (the move-wide siblings
``MOVN``/``MOVK``, the narrower-width loads/stores ``LDRB``/``STRB`` and the 32-bit
``LDR``/``STR``) are provided so the coverage inventory and rejection tests can
exercise the typed ``Unsupported`` aborts (BENCHMARKS.md §3). All words are 32-bit
little-endian A64 instructions; the interpreter reads them as integers, so these
helpers return the integer word.
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


def _uncond_branch_word(link: int, off_bytes: int) -> int:
    """``B``/``BL`` (unconditional branch, immediate): ``op 0 0 1 0 1 imm26``.

    ``link`` is bit[31] (0 = ``B``, 1 = ``BL``). ``off_bytes`` is the signed byte
    displacement from this instruction; it must be a multiple of 4 and fit a
    signed 26-bit instruction offset."""
    if off_bytes % 4 != 0:
        raise ValueError(f"branch offset must be 4-byte aligned: {off_bytes}")
    imm26 = off_bytes // 4
    if not (-(1 << 25) <= imm26 < (1 << 25)):
        raise ValueError(f"branch offset out of range: {off_bytes}")
    return (
        (link & 0x1) << 31
        | 0b00101 << 26
        | (imm26 & 0x3FF_FFFF)
    )


def b(off_bytes: int) -> int:
    """``B <label>`` — in scope (interp 0.4): the unconditional branch.
    ``off_bytes`` is the signed byte offset from this instruction to the target
    (always taken)."""
    return _uncond_branch_word(0, off_bytes)


def bl(off_bytes: int) -> int:
    """``BL <label>`` — in scope (interp 0.4): the branch-with-link. Same target
    as ``B`` plus the link register ``x30 := pc + 4`` (the return address)."""
    return _uncond_branch_word(1, off_bytes)


def adds_imm(rd: int, rn: int, imm12: int, lsl12: bool = False) -> int:
    """``ADDS Xd, Xn|SP, #imm12{, LSL #12}`` — in scope (interp 0.4): the
    flag-setting add (``op = 0, S = 1``). The ``C``/``V`` flags use the
    **addition** definitions (distinct from ``SUBS``'s)."""
    return _add_sub_imm(1, 0, 1, 1 if lsl12 else 0, imm12, rn, rd)


def cmn_imm(rn: int, imm12: int, lsl12: bool = False) -> int:
    """``CMN Xn|SP, #imm12{, LSL #12}`` = ``ADDS XZR, Xn, #imm12`` — in scope
    (interp 0.4): the result is discarded (Rd = XZR), only NZCV is set."""
    return adds_imm(XZR, rn, imm12, lsl12=lsl12)


# --- 32-bit (W-register) ALU/flag immediate forms — in scope (interp 0.6) ----
# The same Add/subtract-immediate / Move-wide encodings with ``sf = 0`` (the W
# variant): the operation is computed on the low 32 bits, the 32-bit result
# zero-extends into the 64-bit destination, and the flags are set at 32-bit width.
def add_imm_w(rd: int, rn: int, imm12: int, lsl12: bool = False) -> int:
    """``ADD Wd|WSP, Wn|WSP, #imm12{, LSL #12}`` — in scope (interp 0.6): the
    32-bit ADD (``sf = 0``). The result zero-extends into ``Xd``."""
    return _add_sub_imm(0, 0, 0, 1 if lsl12 else 0, imm12, rn, rd)


def sub_imm_w(rd: int, rn: int, imm12: int, lsl12: bool = False) -> int:
    """``SUB Wd|WSP, Wn|WSP, #imm12{, LSL #12}`` — in scope (interp 0.6): the
    32-bit SUB (``sf = 0``). The result zero-extends into ``Xd``."""
    return _add_sub_imm(0, 1, 0, 1 if lsl12 else 0, imm12, rn, rd)


def subs_imm_w(rd: int, rn: int, imm12: int, lsl12: bool = False) -> int:
    """``SUBS Wd, Wn|WSP, #imm12{, LSL #12}`` — in scope (interp 0.6): the
    32-bit flag-setting subtract (``sf = 0, op = 1, S = 1``). The ``N``/``Z``/``C``/
    ``V`` flags are computed at **32-bit** width."""
    return _add_sub_imm(0, 1, 1, 1 if lsl12 else 0, imm12, rn, rd)


def cmp_imm_w(rn: int, imm12: int, lsl12: bool = False) -> int:
    """``CMP Wn|WSP, #imm12{, LSL #12}`` = ``SUBS WZR, Wn, #imm12`` — in scope
    (interp 0.6): the 32-bit compare (result discarded, only NZCV set)."""
    return subs_imm_w(XZR, rn, imm12, lsl12=lsl12)


def adds_imm_w(rd: int, rn: int, imm12: int, lsl12: bool = False) -> int:
    """``ADDS Wd, Wn|WSP, #imm12{, LSL #12}`` — in scope (interp 0.6): the
    32-bit flag-setting add (``sf = 0, op = 0, S = 1``). The ``C``/``V`` use the
    **addition** definitions, at **32-bit** width."""
    return _add_sub_imm(0, 0, 1, 1 if lsl12 else 0, imm12, rn, rd)


def cmn_imm_w(rn: int, imm12: int, lsl12: bool = False) -> int:
    """``CMN Wn|WSP, #imm12{, LSL #12}`` = ``ADDS WZR, Wn, #imm12`` — in scope
    (interp 0.6): the 32-bit compare-negative (result discarded, only NZCV set)."""
    return adds_imm_w(XZR, rn, imm12, lsl12=lsl12)


def movz_w(rd: int, imm16: int, hw: int = 0) -> int:
    """``MOVZ Wd, #imm16{, LSL #(16*hw)}`` for ``hw ∈ {0,1}`` — in scope
    (interp 0.6): the 32-bit MOVZ (``sf = 0``). ``hw ∈ {2,3}`` is reserved for the
    32-bit form (LSL #32/#48 has no W variant) and is left encodable here only to
    drive the out-of-scope abort."""
    return _move_wide(0, 0b10, hw, imm16, rd)


def _ldst_uimm(size: int, opc: int, imm12: int, rn: int, rt: int) -> int:
    """Load/store register (unsigned immediate): ``size 1 1 1 0 0 1 opc imm12 Rn Rt``
    (bits[29:27] = 111, V = 0, bits[25:24] = 01)."""
    if not (0 <= imm12 < (1 << 12)):
        raise ValueError(f"imm12 out of range: {imm12}")
    return (
        (size & 0x3) << 30
        | 0b111 << 27
        | 0 << 26                       # V = 0 (integer load/store)
        | 0b01 << 24                    # unsigned-offset addressing mode
        | (opc & 0x3) << 22
        | (imm12 & 0xFFF) << 10
        | (rn & 0x1F) << 5
        | (rt & 0x1F)
    )


def str_imm(rt: int, rn: int, imm: int = 0) -> int:
    """``STR Xt, [Xn|SP, #imm]`` (64-bit, unsigned offset) — in scope (interp 0.5):
    ``size = 0b11`` (64-bit), ``opc = 0b00`` (store). ``imm`` is the **byte**
    offset; it must be a non-negative multiple of 8 (scaled by the access size),
    and is encoded as ``imm12 = imm // 8``. Base field 31 is ``SP``; transfer
    field 31 is ``XZR`` (stores 0)."""
    if imm < 0 or imm % 8 != 0:
        raise ValueError(f"STR offset must be a non-negative multiple of 8: {imm}")
    return _ldst_uimm(0b11, 0b00, imm // 8, rn, rt)


def ldr_imm(rt: int, rn: int, imm: int = 0) -> int:
    """``LDR Xt, [Xn|SP, #imm]`` (64-bit, unsigned offset) — in scope (interp 0.5):
    ``size = 0b11`` (64-bit), ``opc = 0b01`` (load). ``imm`` is the **byte** offset
    (a non-negative multiple of 8), encoded as ``imm12 = imm // 8``. Base field 31
    is ``SP``; transfer field 31 is ``XZR`` (the load is discarded)."""
    if imm < 0 or imm % 8 != 0:
        raise ValueError(f"LDR offset must be a non-negative multiple of 8: {imm}")
    return _ldst_uimm(0b11, 0b01, imm // 8, rn, rt)


# --- out-of-scope encodings (used only to drive the Unsupported aborts) -----
def movz_w_hw2(rd: int, imm16: int) -> int:
    """32-bit ``MOVZ Wd, #imm16, LSL #32`` (out of scope: ``sf = 0`` with
    ``hw = 2`` — the high shift bit is reserved for the 32-bit form)."""
    return _move_wide(0, 0b10, 2, imm16, rd)


def movn(rd: int, imm16: int, hw: int = 0) -> int:
    """``MOVN Xd, #imm16`` (out of scope: ``opc = 0b00``)."""
    return _move_wide(1, 0b00, hw, imm16, rd)


def movk(rd: int, imm16: int, hw: int = 0) -> int:
    """``MOVK Xd, #imm16`` (out of scope: ``opc = 0b11``; keeps other bits)."""
    return _move_wide(1, 0b11, hw, imm16, rd)


def ldr_imm_w(rt: int, rn: int, imm12: int = 0) -> int:
    """32-bit ``LDR Wt, [Xn, #imm]`` (out of scope: ``size = 0b10``)."""
    return _ldst_uimm(0b10, 0b01, imm12, rn, rt)


def str_imm_w(rt: int, rn: int, imm12: int = 0) -> int:
    """32-bit ``STR Wt, [Xn, #imm]`` (out of scope: ``size = 0b10``)."""
    return _ldst_uimm(0b10, 0b00, imm12, rn, rt)


def ldrb_imm(rt: int, rn: int, imm12: int = 0) -> int:
    """``LDRB Wt, [Xn, #imm]`` (out of scope: ``size = 0b00``, the byte width)."""
    return _ldst_uimm(0b00, 0b01, imm12, rn, rt)


def strb_imm(rt: int, rn: int, imm12: int = 0) -> int:
    """``STRB Wt, [Xn, #imm]`` (out of scope: ``size = 0b00``, the byte width)."""
    return _ldst_uimm(0b00, 0b00, imm12, rn, rt)
