"""AArch64 A64 instruction decoder.

Covers the SCHEMA.md §§5.1–5.14 instruction set: data-processing
(immediate + register), branches/exceptions/system, loads/stores.
All A64 instructions are 32 bits wide; no compressed forms.

Returns ``Decoded | None``; ``None`` means unsupported or reserved
encoding. The simulator treats ``None`` as an unrecognised-instruction
halt.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Decoded record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decoded:
    mnemonic: str
    pc: int
    raw: int
    length: int = 4        # always 4 for A64
    sf: bool = True        # True=64-bit (X reg), False=32-bit (W reg)
    rd: int = 0            # destination register (0-31)
    rn: int = 0            # first source / base register
    rm: int = 0            # second source
    ra: int = 0            # accumulate (MADD/MSUB/SMADDL)
    imm: int = 0           # sign-extended immediate
    shift_type: int = 0    # 0=LSL,1=LSR,2=ASR,3=ROR
    shift_amount: int = 0
    extend_type: int = 0   # 0=UXTB,1=UXTH,2=UXTW,3=UXTX,4=SXTB,5=SXTH,6=SXTW,7=SXTX
    cond: int = 0          # A64 condition code (4 bits)
    bit_pos: int = 0       # bit position for TBZ/TBNZ
    sets_flags: bool = False
    src_is_imm: bool = False  # True when operand 2 is an immediate (not a register)
    # Load/store addressing
    addr_mode: str = "base_imm"   # "base","base_imm","pre","post","literal","base_reg","ext_reg"
    # For LDP/STP: second transfer register
    rt2: int = 0
    # Bitfield fields (SBFM/UBFM/BFM): raw immr/imms passed to simulator
    immr: int = 0
    imms: int = 0

    def is_branch(self) -> bool:
        return self.mnemonic in {
            "B", "BL", "BR", "BLR", "RET",
            "B.cond", "CBZ", "CBNZ", "TBZ", "TBNZ",
        }

    def is_load(self) -> bool:
        return self.mnemonic in {
            "LDR", "LDRB", "LDRH", "LDRSB", "LDRSH", "LDRSW", "LDP",
        }

    def is_store(self) -> bool:
        return self.mnemonic in {"STR", "STRB", "STRH", "STP"}


# ---------------------------------------------------------------------------
# Bit helpers
# ---------------------------------------------------------------------------


def _b(word: int, hi: int, lo: int) -> int:
    """Extract bits [hi:lo] from word (inclusive, like ARM notation)."""
    mask = (1 << (hi - lo + 1)) - 1
    return (word >> lo) & mask


def _sext(value: int, width: int) -> int:
    sign = 1 << (width - 1)
    return (value ^ sign) - sign


# ---------------------------------------------------------------------------
# Top-level group dispatch
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Data Processing — Immediate  (op0[28:25] = 100x)
# ---------------------------------------------------------------------------


def _decode_dp_imm(word: int, pc: int) -> Decoded | None:
    sf = bool(_b(word, 31, 31))
    op0 = _b(word, 28, 25)
    bit24 = _b(word, 24, 24)
    bit23 = _b(word, 23, 23)

    if op0 == 0x8:  # 1000
        if bit24 == 0:
            return _decode_pc_rel(word, pc, sf)
        return _decode_add_sub_imm(word, pc, sf)

    # op0 == 0x9 (1001)
    if bit24 == 0 and bit23 == 0:
        return _decode_logical_imm(word, pc, sf)
    if bit24 == 0 and bit23 == 1:
        return _decode_move_wide(word, pc, sf)
    if bit24 == 1 and bit23 == 0:
        return _decode_bitfield(word, pc, sf)
    if bit24 == 1 and bit23 == 1:
        return _decode_extract(word, pc, sf)
    return None


def _decode_pc_rel(word: int, pc: int, sf: bool) -> Decoded | None:
    page = bool(_b(word, 31, 31))
    immlo = _b(word, 30, 29)
    immhi = _b(word, 23, 5)
    rd = _b(word, 4, 0)
    imm21 = (immhi << 2) | immlo
    if page:
        imm = _sext(imm21 << 12, 33)
        return Decoded("ADRP", pc, word, rd=rd, imm=imm, sf=True)
    else:
        imm = _sext(imm21, 21)
        return Decoded("ADR", pc, word, rd=rd, imm=imm, sf=True)


def _decode_add_sub_imm(word: int, pc: int, sf: bool) -> Decoded | None:
    op = _b(word, 30, 30)    # 0=ADD, 1=SUB
    s = bool(_b(word, 29, 29))
    shift = _b(word, 22, 22)
    imm12 = _b(word, 21, 10)
    rn = _b(word, 9, 5)
    rd = _b(word, 4, 0)
    imm = imm12 << (12 if shift else 0)
    if op == 0:
        mnem = "ADDS" if s else "ADD"
    else:
        mnem = "SUBS" if s else "SUB"
    return Decoded(mnem, pc, word, sf=sf, rd=rd, rn=rn, imm=imm, sets_flags=s,
                   src_is_imm=True)


# Bitmask immediate decoding per ARM DDI A-profile §C4.1.34
def _decode_bitmask(n: int, immr: int, imms: int, sf: bool) -> int | None:
    """Return the 64-bit bitmask pattern, or None for reserved."""
    # Determine element size from N:imms
    if n == 1:
        len_ = 6
    else:
        # find highest zero in ~imms[5:1]
        # len = highest bit set in NOT(imms[5:1]) — the leading-zero approach
        tmp = (~imms) & 0x3F
        if tmp == 0:
            return None
        len_ = tmp.bit_length() - 1
        if len_ == 0:
            return None
        # Validate: n must be 0 when len_ < 6
        # (simplified: just proceed if len_ > 0)

    esize = 1 << len_
    s = imms & (esize - 1)
    r = immr & (esize - 1)
    # Number of set bits in element = s + 1
    ones = (1 << (s + 1)) - 1
    # Rotate right by r
    if r == 0:
        elem = ones
    else:
        elem = ((ones >> r) | (ones << (esize - r))) & ((1 << esize) - 1)
    # Replicate to 64 bits
    result = 0
    reps = 64 // esize
    for _ in range(reps):
        result = (result << esize) | elem
    return result & 0xFFFFFFFFFFFFFFFF


def _decode_logical_imm(word: int, pc: int, sf: bool) -> Decoded | None:
    opc = _b(word, 30, 29)
    n = _b(word, 22, 22)
    immr = _b(word, 21, 16)
    imms = _b(word, 15, 10)
    rn = _b(word, 9, 5)
    rd = _b(word, 4, 0)
    if not sf and n == 1:
        return None  # reserved for 32-bit
    mask = _decode_bitmask(n, immr, imms, sf)
    if mask is None:
        return None
    if not sf:
        mask &= 0xFFFFFFFF
    mnem = {0: "AND", 1: "ORR", 2: "EOR", 3: "ANDS"}[opc]
    sets = (opc == 3)
    return Decoded(mnem, pc, word, sf=sf, rd=rd, rn=rn, imm=mask, sets_flags=sets,
                   src_is_imm=True)


def _decode_move_wide(word: int, pc: int, sf: bool) -> Decoded | None:
    opc = _b(word, 30, 29)
    hw = _b(word, 22, 21)
    imm16 = _b(word, 20, 5)
    rd = _b(word, 4, 0)
    if opc == 1:
        return None  # reserved
    if not sf and hw > 1:
        return None  # shift > 16 reserved for 32-bit
    shift = hw * 16
    mnem = {0: "MOVN", 2: "MOVZ", 3: "MOVK"}[opc]
    return Decoded(mnem, pc, word, sf=sf, rd=rd, imm=imm16, shift_amount=shift)


def _decode_bitfield(word: int, pc: int, sf: bool) -> Decoded | None:
    opc = _b(word, 30, 29)
    n = _b(word, 22, 22)
    immr = _b(word, 21, 16)
    imms = _b(word, 15, 10)
    rn = _b(word, 9, 5)
    rd = _b(word, 4, 0)
    if opc == 3:
        return None  # reserved
    mnem = {0: "SBFM", 1: "BFM", 2: "UBFM"}[opc]
    return Decoded(mnem, pc, word, sf=sf, rd=rd, rn=rn, immr=immr, imms=imms)


def _decode_extract(word: int, pc: int, sf: bool) -> Decoded | None:
    op21 = _b(word, 30, 29)
    n = _b(word, 22, 22)
    o0 = _b(word, 21, 21)
    rm = _b(word, 20, 16)
    imms = _b(word, 15, 10)
    rn = _b(word, 9, 5)
    rd = _b(word, 4, 0)
    if op21 != 0 or o0 != 0:
        return None
    if sf and n != 1:
        return None
    if not sf and (n != 0 or _b(imms, 5, 5) != 0):
        return None
    return Decoded("EXTR", pc, word, sf=sf, rd=rd, rn=rn, rm=rm, imm=imms)


# ---------------------------------------------------------------------------
# Branches, Exception, System  (op0[28:25] = 101x)
# ---------------------------------------------------------------------------


def _decode_branch_sys(word: int, pc: int) -> Decoded | None:
    # Unconditional branch (immediate): bits[30:26] == 00101
    # bit31 = 0: B; bit31 = 1: BL
    if _b(word, 30, 26) == 0b00101:
        imm26 = _b(word, 25, 0)
        imm = _sext(imm26 << 2, 28)
        if _b(word, 31, 31):
            return Decoded("BL", pc, word, sf=True, imm=imm)
        return Decoded("B", pc, word, sf=True, imm=imm)

    # Conditional branch (immediate): bits[31:24] == 0101_0100, bit4 == 0
    if _b(word, 31, 24) == 0b01010100 and _b(word, 4, 4) == 0:
        imm19 = _b(word, 23, 5)
        imm = _sext(imm19 << 2, 21)
        cond = _b(word, 3, 0)
        return Decoded("B.cond", pc, word, sf=True, imm=imm, cond=cond)

    # CBZ/CBNZ: bits[30:25] == x11010 → bits[30:24] distinguish
    # CBZ 64-bit: 1011 0100; CBZ 32-bit: 0011 0100
    # CBNZ 64-bit: 1011 0101; CBNZ 32-bit: 0011 0101
    top8 = _b(word, 31, 24)
    if top8 in (0xB4, 0x34, 0xB5, 0x35):
        sf = bool(top8 & 0x80)
        is_nz = bool(top8 & 0x01)
        imm19 = _b(word, 23, 5)
        imm = _sext(imm19 << 2, 21)
        rt = _b(word, 4, 0)
        return Decoded("CBNZ" if is_nz else "CBZ", pc, word, sf=sf, rd=rt, imm=imm)

    # TBZ/TBNZ: bits[30:25] = x01101 → top7 = x011010 or x011011
    # TBZ:  bit[24]=0 → bits[31:24] include 0110110x (0x36/0xB6)
    # TBNZ: bit[24]=1 → 0110111x (0x37/0xB7)
    if top8 in (0x36, 0xB6, 0x37, 0xB7):
        b5 = _b(word, 31, 31)  # high bit of bit_pos
        b40 = _b(word, 23, 19)  # low 5 bits of bit_pos
        bit_pos = (b5 << 5) | b40
        imm14 = _b(word, 18, 5)
        imm = _sext(imm14 << 2, 16)
        rt = _b(word, 4, 0)
        is_nz = bool(top8 & 0x01)
        return Decoded(
            "TBNZ" if is_nz else "TBZ", pc, word,
            sf=True, rd=rt, imm=imm, bit_pos=bit_pos,
        )

    # Unconditional branch (register): bits[31:25] == 110_1011
    if _b(word, 31, 25) == 0b1101011:
        opc = _b(word, 24, 21)
        op2 = _b(word, 20, 16)
        op3 = _b(word, 15, 10)
        rn = _b(word, 9, 5)
        op4 = _b(word, 4, 0)
        if op2 != 0b11111:
            return None
        if opc == 0b0000 and op3 == 0 and op4 == 0:
            return Decoded("BR", pc, word, sf=True, rn=rn)
        if opc == 0b0001 and op3 == 0 and op4 == 0:
            return Decoded("BLR", pc, word, sf=True, rn=rn, rd=30)
        if opc == 0b0010 and op3 == 0 and op4 == 0:
            return Decoded("RET", pc, word, sf=True, rn=rn)
        return None

    # Exception generation: bits[31:24] == 1101_0100
    if _b(word, 31, 24) == 0xD4:
        opc = _b(word, 23, 21)
        ll = _b(word, 1, 0)
        if opc == 0b000 and ll == 0b01:
            return Decoded("SVC", pc, word, sf=True)
        if opc == 0b001 and ll == 0b00:
            return Decoded("BRK", pc, word, sf=True)
        # HLT, DCPS etc. — treat as halt-like
        return Decoded("BRK", pc, word, sf=True)

    # System / hint: bits[31:24] == 1101_0101
    if _b(word, 31, 24) == 0xD5:
        crn = _b(word, 15, 12)
        op2 = _b(word, 10, 8)
        rt = _b(word, 4, 0)
        # HINT (NOP etc.): crn=3, op1=3, crm=2, op2∈{0..7}, Rt=11111
        if rt == 0b11111:
            return Decoded("NOP", pc, word, sf=True)
        # MSR/MRS — treat as NOP for now
        return Decoded("NOP", pc, word, sf=True)

    # DSB/DMB/ISB: bits[31:22] == 1101010100 0 (check top 12 including crn)
    if _b(word, 31, 22) == 0b1101010100 >> 2:
        return Decoded("NOP", pc, word, sf=True)

    return None


# ---------------------------------------------------------------------------
# Loads and Stores  (op0[28:25] & 0x5 == 0x4)
# ---------------------------------------------------------------------------


def _decode_load_store(word: int, pc: int) -> Decoded | None:
    # Load/Store register pair: bits[29:27] == 101, bit25=0
    # Detect via bits[29:25]:
    #   STP/LDP non-temporal (bit26=1 → V): skip
    #   STP/LDP offset:     bits[29:25] = 10101
    #   STP/LDP post-index: bits[29:25] = 10001
    #   STP/LDP pre-index:  bits[29:25] = 10111
    top5_29_25 = _b(word, 29, 25)
    if top5_29_25 in (0b10101, 0b10001, 0b10111):
        return _decode_load_store_pair(word, pc, top5_29_25)

    # LDR literal: bits[29:27] = 011, bit26 = 0 → bits[29:26] = 0110
    if _b(word, 29, 26) == 0b0110:
        return _decode_ldr_literal(word, pc)

    # Load/Store register (various): bits[29:27] = 111
    if _b(word, 29, 27) == 0b111:
        return _decode_load_store_reg(word, pc)

    return None


def _decode_ldr_literal(word: int, pc: int) -> Decoded | None:
    opc = _b(word, 31, 30)
    v = _b(word, 26, 26)
    if v:
        return None  # SIMD
    imm19 = _b(word, 23, 5)
    imm = _sext(imm19 << 2, 21)
    rt = _b(word, 4, 0)
    # opc=00: LDR Wt; opc=01: LDR Xt; opc=10: LDRSW Xt; opc=11: PRFM (skip)
    if opc == 0b00:
        return Decoded("LDR", pc, word, sf=False, rd=rt, imm=imm, addr_mode="literal")
    if opc == 0b01:
        return Decoded("LDR", pc, word, sf=True, rd=rt, imm=imm, addr_mode="literal")
    if opc == 0b10:
        return Decoded("LDRSW", pc, word, sf=True, rd=rt, imm=imm, addr_mode="literal")
    return None


def _decode_load_store_pair(word: int, pc: int, top5: int) -> Decoded | None:
    opc = _b(word, 31, 30)
    v = _b(word, 26, 26)
    l = _b(word, 22, 22)
    imm7 = _b(word, 21, 15)
    rt2 = _b(word, 14, 10)
    rn = _b(word, 9, 5)
    rt = _b(word, 4, 0)
    if v:
        return None  # SIMD
    # opc: 00=32-bit, 01=STGP/ldnp (skip), 10=64-bit
    if opc == 0b01:
        return None
    sf = (opc == 0b10)
    scale = 3 if sf else 2  # imm7 scaled by 8 or 4
    imm = _sext(imm7 << scale, 7 + scale)
    if top5 == 0b10001:
        mode = "post"
    elif top5 == 0b10111:
        mode = "pre"
    else:
        mode = "base_imm"
    mnem = "LDP" if l else "STP"
    return Decoded(
        mnem, pc, word, sf=sf, rd=rt, rn=rn, rt2=rt2, imm=imm, addr_mode=mode,
    )


# Size → (bytes, signed-extend-variants, mnemonic_prefix)
_LS_SIZE = {
    0b00: (1, "B"),   # STRB/LDRB/LDRSB
    0b01: (2, "H"),   # STRH/LDRH/LDRSH
    0b10: (4, ""),    # STR/LDR Wt / LDRSW
    0b11: (8, ""),    # STR/LDR Xt
}


def _decode_load_store_reg(word: int, pc: int) -> Decoded | None:
    size = _b(word, 31, 30)
    v = _b(word, 26, 26)
    opc = _b(word, 23, 22)
    bit24 = _b(word, 24, 24)
    bit21 = _b(word, 21, 21)
    rn = _b(word, 9, 5)
    rt = _b(word, 4, 0)

    if v:
        return None  # SIMD

    nbytes, suffix = _LS_SIZE[size]

    # Register offset: bit24=1, bit21=1
    if bit24 == 1 and bit21 == 1:
        rm = _b(word, 20, 16)
        option = _b(word, 15, 13)
        s = _b(word, 12, 12)
        ext_map = {2: 1, 3: 2, 6: 5, 7: 7}  # option → extend_type (UXTW/UXTX/SXTW/SXTX)
        ext = ext_map.get(option, 3)
        shift = s * (size if size <= 2 else 3)
        mnem, sf = _ls_mnem(size, opc, nbytes, suffix)
        if mnem is None:
            return None
        return Decoded(
            mnem, pc, word, sf=sf, rd=rt, rn=rn, rm=rm,
            extend_type=ext, shift_amount=shift, addr_mode="base_reg",
        )

    # Unsigned offset: bit24=1, bit21=0
    if bit24 == 1:
        imm12 = _b(word, 21, 10)
        imm = imm12 * nbytes
        mnem, sf = _ls_mnem(size, opc, nbytes, suffix)
        if mnem is None:
            return None
        return Decoded(mnem, pc, word, sf=sf, rd=rt, rn=rn, imm=imm, addr_mode="base_imm")

    # Immediate (post/pre-index): bit24=0, bit21=0
    if bit21 == 0:
        simm9 = _b(word, 20, 12)
        imm = _sext(simm9, 9)
        idx = _b(word, 11, 10)
        if idx == 0b01:
            mode = "post"
        elif idx == 0b11:
            mode = "pre"
        else:
            return None  # unallocated
        mnem, sf = _ls_mnem(size, opc, nbytes, suffix)
        if mnem is None:
            return None
        return Decoded(mnem, pc, word, sf=sf, rd=rt, rn=rn, imm=imm, addr_mode=mode)

    return None


def _ls_mnem(size: int, opc: int, nbytes: int, suffix: str) -> tuple[str | None, bool]:
    """Return (mnemonic, sf) for a load/store given size and opc."""
    # Store: opc=00
    if opc == 0b00:
        if size == 0b00:
            return "STRB", False
        if size == 0b01:
            return "STRH", False
        if size == 0b10:
            return "STR", False   # STR Wt (sf=False)
        return "STR", True        # STR Xt (sf=True)
    # Load unsigned / non-extending: opc=01
    if opc == 0b01:
        if size == 0b00:
            return "LDRB", False
        if size == 0b01:
            return "LDRH", False
        if size == 0b10:
            return "LDR", False   # LDR Wt zero-extends
        return "LDR", True        # LDR Xt
    # Sign-extending: opc=10 or opc=11
    if opc == 0b10:
        # Sign-extend to 64 bits
        if size == 0b00:
            return "LDRSB", True
        if size == 0b01:
            return "LDRSH", True
        if size == 0b10:
            return "LDRSW", True
        return None, True  # reserved (size=11 + opc=10)
    if opc == 0b11:
        # Sign-extend to 32 bits (W dest)
        if size == 0b00:
            return "LDRSB", False
        if size == 0b01:
            return "LDRSH", False
        return None, False  # reserved
    return None, False


# ---------------------------------------------------------------------------
# Data Processing — Register  (op0[28:25] & 0x5 == 0x5)
# ---------------------------------------------------------------------------


def _decode_dp_reg(word: int, pc: int) -> Decoded | None:
    sf = bool(_b(word, 31, 31))
    bit28 = _b(word, 28, 28)
    bit26 = _b(word, 26, 26)

    if bit28 == 0:
        # op0 = 0101 (bit26=0) or 0111 (bit26=1)
        if bit26 == 1:
            return _decode_dp_3src(word, pc)  # MADD/MSUB etc. at op0=0111
        # op0=0101: add/sub shifted (bit24=1) or logical shifted (bit24=0)
        if _b(word, 24, 24) == 1:
            return _decode_add_sub_reg(word, pc, sf)
        return _decode_logical_reg(word, pc, sf)

    # bit28=1: op0=1101 (bit26=0) or 1111 (bit26=1, SIMD)
    if bit26 == 1:
        return None  # SIMD/FP

    # op0=1101: 2-source, 3-source, CSEL already handled
    bit24 = _b(word, 24, 24)
    bit21 = _b(word, 21, 21)
    if bit24 == 1 and bit21 == 0:
        return _decode_dp_3src(word, pc)  # MADD/MSUB/SMADDL etc.
    op54 = _b(word, 30, 29)
    if op54 == 0b00:
        return _decode_dp_2src(word, pc, sf)
    if op54 == 0b01:
        return _decode_dp_1src(word, pc, sf)
    return None


def _decode_dp_2src(word: int, pc: int, sf: bool) -> Decoded | None:
    rm = _b(word, 20, 16)
    opcode = _b(word, 15, 10)
    rn = _b(word, 9, 5)
    rd = _b(word, 4, 0)
    # UDIV=0b000010, SDIV=0b000011
    # LSLV=0b001000, LSRV=0b001001, ASRV=0b001010, RORV=0b001011
    # MUL (MADD):  lives in dp_3src, not here
    if opcode == 0b000010:
        return Decoded("UDIV", pc, word, sf=sf, rd=rd, rn=rn, rm=rm)
    if opcode == 0b000011:
        return Decoded("SDIV", pc, word, sf=sf, rd=rd, rn=rn, rm=rm)
    if opcode == 0b001000:
        return Decoded("LSL", pc, word, sf=sf, rd=rd, rn=rn, rm=rm, shift_type=0)
    if opcode == 0b001001:
        return Decoded("LSR", pc, word, sf=sf, rd=rd, rn=rn, rm=rm, shift_type=1)
    if opcode == 0b001010:
        return Decoded("ASR", pc, word, sf=sf, rd=rd, rn=rn, rm=rm, shift_type=2)
    if opcode == 0b001011:
        return Decoded("ROR", pc, word, sf=sf, rd=rd, rn=rn, rm=rm, shift_type=3)
    # CRC, PACGA etc. — not supported
    return None


def _decode_dp_1src(word: int, pc: int, sf: bool) -> Decoded | None:
    # REV, CLZ, etc. — low priority; return None for now
    return None


def _decode_logical_reg(word: int, pc: int, sf: bool) -> Decoded | None:
    opc = _b(word, 30, 29)
    shift = _b(word, 23, 22)
    n = _b(word, 21, 21)   # N=1 inverts Rm (BIC/ORN/EON/BICS)
    rm = _b(word, 20, 16)
    imm6 = _b(word, 15, 10)
    rn = _b(word, 9, 5)
    rd = _b(word, 4, 0)
    # AND=00, ORR=01, EOR=10, ANDS=11 (+ N variants: BIC, ORN, EON, BICS)
    base = {0: "AND", 1: "ORR", 2: "EOR", 3: "ANDS"}[opc]
    inv = {0: "BIC", 1: "ORN", 2: "EON", 3: "BICS"}[opc]
    mnem = inv if n else base
    sets = mnem in ("ANDS", "BICS")
    return Decoded(
        mnem, pc, word, sf=sf, rd=rd, rn=rn, rm=rm,
        shift_type=shift, shift_amount=imm6, sets_flags=sets,
    )


def _decode_add_sub_reg(word: int, pc: int, sf: bool) -> Decoded | None:
    op = _b(word, 30, 30)
    s = bool(_b(word, 29, 29))
    # bit21: 0=shifted register, 1=extended register
    bit21 = _b(word, 21, 21)
    rm = _b(word, 20, 16)
    rn = _b(word, 9, 5)
    rd = _b(word, 4, 0)
    mnem = ("SUB" if op else "ADD") + ("S" if s else "")
    if bit21 == 0:
        shift = _b(word, 23, 22)
        imm6 = _b(word, 15, 10)
        return Decoded(
            mnem, pc, word, sf=sf, rd=rd, rn=rn, rm=rm,
            shift_type=shift, shift_amount=imm6, sets_flags=s,
        )
    else:
        option = _b(word, 15, 13)
        imm3 = _b(word, 12, 10)
        return Decoded(
            mnem, pc, word, sf=sf, rd=rd, rn=rn, rm=rm,
            extend_type=option, shift_amount=imm3, sets_flags=s,
            addr_mode="ext_reg",
        )


# Data-processing (3 source): MUL/MADD/MSUB/SMULL/UMULL etc.
# op0[28:25] & 0x5 == 0x5, bit28=1, bits[30:29]=11
# Actually DP-3-source: bits[28:23] = 0b011011
def _decode_dp_3src(word: int, pc: int) -> Decoded | None:
    sf = bool(_b(word, 31, 31))
    op54 = _b(word, 30, 29)
    op31 = _b(word, 23, 21)
    o0 = _b(word, 15, 15)
    rm = _b(word, 20, 16)
    ra = _b(word, 14, 10)
    rn = _b(word, 9, 5)
    rd = _b(word, 4, 0)

    if op54 == 0b00:
        # MADD (MUL when ra=XZR): o0=0; MSUB (MNEG when ra=XZR): o0=1
        if o0 == 0:
            return Decoded("MADD", pc, word, sf=sf, rd=rd, rn=rn, rm=rm, ra=ra)
        return Decoded("MSUB", pc, word, sf=sf, rd=rd, rn=rn, rm=rm, ra=ra)
    if op54 == 0b01 and sf:
        # SMADDL (SMULL when ra=XZR), SMSUBL: op31=0; UMADDL/UMSUBL: op31=1
        if op31 == 0b000:
            if o0 == 0:
                return Decoded("SMADDL", pc, word, sf=True, rd=rd, rn=rn, rm=rm, ra=ra)
            return Decoded("SMSUBL", pc, word, sf=True, rd=rd, rn=rn, rm=rm, ra=ra)
        if op31 == 0b010:
            if o0 == 0:
                return Decoded("UMADDL", pc, word, sf=True, rd=rd, rn=rn, rm=rm, ra=ra)
            return Decoded("UMSUBL", pc, word, sf=True, rd=rd, rn=rn, rm=rm, ra=ra)
        if op31 == 0b001 and o0 == 0:
            return Decoded("SMULH", pc, word, sf=True, rd=rd, rn=rn, rm=rm)
        if op31 == 0b101 and o0 == 0:
            return Decoded("UMULH", pc, word, sf=True, rd=rd, rn=rn, rm=rm)
    return None


def decode(word: int, pc: int = 0) -> Decoded | None:
    """Decode one A64 instruction word; returns None for unsupported encodings."""
    word &= 0xFFFFFFFF
    op0 = _b(word, 28, 25)

    if (op0 & 0xE) == 0x8:
        return _decode_dp_imm(word, pc)
    if (op0 & 0xE) == 0xA:
        return _decode_branch_sys(word, pc)
    if (op0 & 0x5) == 0x4:
        return _decode_load_store(word, pc)
    if (op0 & 0x5) == 0x5:
        # Check for conditional select before general DP-reg
        csel = _try_decode_csel(word, pc)
        if csel is not None:
            return csel
        return _decode_dp_reg(word, pc)
    return None


def _try_decode_csel(word: int, pc: int) -> Decoded | None:
    """CSEL/CSINC/CSINV/CSNEG: bits[29:21] = 011010100."""
    if _b(word, 29, 21) != 0b011010100:
        return None
    sf = bool(_b(word, 31, 31))
    rm = _b(word, 20, 16)
    cond = _b(word, 15, 12)
    op = _b(word, 11, 10)  # 00=CSEL, 01=CSINC, 10=CSINV, 11=CSNEG
    rn = _b(word, 9, 5)
    rd = _b(word, 4, 0)
    mnem = {0: "CSEL", 1: "CSINC", 2: "CSINV", 3: "CSNEG"}[op]
    return Decoded(mnem, pc, word, sf=sf, rd=rd, rn=rn, rm=rm, cond=cond)


__all__ = ["Decoded", "decode"]
