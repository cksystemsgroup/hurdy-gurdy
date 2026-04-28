"""RV64I + RV64M + RVC instruction decoder.

The decoder exposes:

- ``Decoded``: a frozen dataclass with the canonical operands.
- ``decode(word, pc, length=4) -> Decoded | None``: decode a single
  word into a ``Decoded`` record. Returns ``None`` for reserved or
  unsupported encodings; the caller decides how to react.
- ``decode_compressed(half, pc) -> Decoded | None``: RVC. The result's
  ``mnemonic`` is the *expanded* 32-bit equivalent so the per-mnemonic
  library lowering applies uniformly. ``length`` is 2.
- ``expand_rvc(half) -> int | None``: returns the 32-bit equivalent
  word for an RVC encoding (or ``None`` for reserved).

Operand fields not used by an instruction are zero/None. ``imm`` is
the *post-decode signed* immediate (sign extended where applicable).

The decoder follows the rotor lineage's choice of encoding RVC purely
by translating to its 32-bit equivalent before lowering — so the
library only sees RV64I+M operations. This matches SCHEMA.md.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Decoded record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decoded:
    mnemonic: str
    pc: int
    length: int  # 2 (RVC) or 4 (standard)
    raw: int
    expanded: int | None = None  # 32-bit form when RVC; None otherwise.
    rd: int = 0
    rs1: int = 0
    rs2: int = 0
    imm: int = 0
    # Some shifts encode shamt in imm; csrs use a CSR number stored in imm.
    # The SCHEMA.md library for each mnemonic determines how to interpret.

    def is_branch(self) -> bool:
        return self.mnemonic in {"BEQ", "BNE", "BLT", "BGE", "BLTU", "BGEU"}

    def is_jump(self) -> bool:
        return self.mnemonic in {"JAL", "JALR"}

    def is_load(self) -> bool:
        return self.mnemonic in {"LB", "LH", "LW", "LD", "LBU", "LHU", "LWU"}

    def is_store(self) -> bool:
        return self.mnemonic in {"SB", "SH", "SW", "SD"}


# ---------------------------------------------------------------------------
# Bit helpers
# ---------------------------------------------------------------------------


def _bits(word: int, hi: int, lo: int) -> int:
    return (word >> lo) & ((1 << (hi - lo + 1)) - 1)


def _sext(value: int, width: int) -> int:
    sign = 1 << (width - 1)
    return (value ^ sign) - sign


# ---------------------------------------------------------------------------
# RV64I/M decode
# ---------------------------------------------------------------------------


# Opcode field (bits 6:0)
OP_LUI = 0b0110111
OP_AUIPC = 0b0010111
OP_JAL = 0b1101111
OP_JALR = 0b1100111
OP_BRANCH = 0b1100011
OP_LOAD = 0b0000011
OP_STORE = 0b0100011
OP_OPIMM = 0b0010011
OP_OPIMM32 = 0b0011011  # *W
OP_OP = 0b0110011
OP_OP32 = 0b0111011  # *W
OP_FENCE = 0b0001111
OP_SYSTEM = 0b1110011


def decode(word: int, pc: int = 0, length: int = 4) -> Decoded | None:
    """Decode a 32-bit RV64I/M word."""
    word &= 0xFFFFFFFF
    op = _bits(word, 6, 0)

    if op == OP_LUI:
        rd = _bits(word, 11, 7)
        imm = _sext(_bits(word, 31, 12) << 12, 32)
        return Decoded("LUI", pc, length, word, rd=rd, imm=imm)
    if op == OP_AUIPC:
        rd = _bits(word, 11, 7)
        imm = _sext(_bits(word, 31, 12) << 12, 32)
        return Decoded("AUIPC", pc, length, word, rd=rd, imm=imm)
    if op == OP_JAL:
        rd = _bits(word, 11, 7)
        imm20 = _bits(word, 31, 31)
        imm10_1 = _bits(word, 30, 21)
        imm11 = _bits(word, 20, 20)
        imm19_12 = _bits(word, 19, 12)
        imm = (
            (imm20 << 20) | (imm19_12 << 12) | (imm11 << 11) | (imm10_1 << 1)
        )
        imm = _sext(imm, 21)
        return Decoded("JAL", pc, length, word, rd=rd, imm=imm)
    if op == OP_JALR:
        rd = _bits(word, 11, 7)
        rs1 = _bits(word, 19, 15)
        funct3 = _bits(word, 14, 12)
        if funct3 != 0:
            return None
        imm = _sext(_bits(word, 31, 20), 12)
        return Decoded("JALR", pc, length, word, rd=rd, rs1=rs1, imm=imm)
    if op == OP_BRANCH:
        rs1 = _bits(word, 19, 15)
        rs2 = _bits(word, 24, 20)
        funct3 = _bits(word, 14, 12)
        imm12 = _bits(word, 31, 31)
        imm10_5 = _bits(word, 30, 25)
        imm4_1 = _bits(word, 11, 8)
        imm11 = _bits(word, 7, 7)
        imm = (imm12 << 12) | (imm11 << 11) | (imm10_5 << 5) | (imm4_1 << 1)
        imm = _sext(imm, 13)
        mnem = {0: "BEQ", 1: "BNE", 4: "BLT", 5: "BGE", 6: "BLTU", 7: "BGEU"}.get(
            funct3
        )
        if mnem is None:
            return None
        return Decoded(mnem, pc, length, word, rs1=rs1, rs2=rs2, imm=imm)
    if op == OP_LOAD:
        rd = _bits(word, 11, 7)
        rs1 = _bits(word, 19, 15)
        funct3 = _bits(word, 14, 12)
        imm = _sext(_bits(word, 31, 20), 12)
        mnem = {0: "LB", 1: "LH", 2: "LW", 3: "LD", 4: "LBU", 5: "LHU", 6: "LWU"}.get(
            funct3
        )
        if mnem is None:
            return None
        return Decoded(mnem, pc, length, word, rd=rd, rs1=rs1, imm=imm)
    if op == OP_STORE:
        rs1 = _bits(word, 19, 15)
        rs2 = _bits(word, 24, 20)
        funct3 = _bits(word, 14, 12)
        imm = (_bits(word, 31, 25) << 5) | _bits(word, 11, 7)
        imm = _sext(imm, 12)
        mnem = {0: "SB", 1: "SH", 2: "SW", 3: "SD"}.get(funct3)
        if mnem is None:
            return None
        return Decoded(mnem, pc, length, word, rs1=rs1, rs2=rs2, imm=imm)
    if op == OP_OPIMM:
        rd = _bits(word, 11, 7)
        rs1 = _bits(word, 19, 15)
        funct3 = _bits(word, 14, 12)
        imm = _sext(_bits(word, 31, 20), 12)
        if funct3 == 0:
            return Decoded("ADDI", pc, length, word, rd=rd, rs1=rs1, imm=imm)
        if funct3 == 2:
            return Decoded("SLTI", pc, length, word, rd=rd, rs1=rs1, imm=imm)
        if funct3 == 3:
            return Decoded("SLTIU", pc, length, word, rd=rd, rs1=rs1, imm=imm)
        if funct3 == 4:
            return Decoded("XORI", pc, length, word, rd=rd, rs1=rs1, imm=imm)
        if funct3 == 6:
            return Decoded("ORI", pc, length, word, rd=rd, rs1=rs1, imm=imm)
        if funct3 == 7:
            return Decoded("ANDI", pc, length, word, rd=rd, rs1=rs1, imm=imm)
        # Shifts. RV64 uses 6-bit shamt (bits 25:20). Top 6 bits:
        # SLLI: 000000xx, SRLI: 000000xx, SRAI: 010000xx
        if funct3 == 1:
            funct6 = _bits(word, 31, 26)
            shamt = _bits(word, 25, 20)
            if funct6 == 0:
                return Decoded("SLLI", pc, length, word, rd=rd, rs1=rs1, imm=shamt)
            return None
        if funct3 == 5:
            funct6 = _bits(word, 31, 26)
            shamt = _bits(word, 25, 20)
            if funct6 == 0:
                return Decoded("SRLI", pc, length, word, rd=rd, rs1=rs1, imm=shamt)
            if funct6 == 0b010000:
                return Decoded("SRAI", pc, length, word, rd=rd, rs1=rs1, imm=shamt)
            return None
        return None
    if op == OP_OPIMM32:
        rd = _bits(word, 11, 7)
        rs1 = _bits(word, 19, 15)
        funct3 = _bits(word, 14, 12)
        imm = _sext(_bits(word, 31, 20), 12)
        if funct3 == 0:
            return Decoded("ADDIW", pc, length, word, rd=rd, rs1=rs1, imm=imm)
        if funct3 == 1:
            funct7 = _bits(word, 31, 25)
            shamt = _bits(word, 24, 20)
            if funct7 == 0:
                return Decoded("SLLIW", pc, length, word, rd=rd, rs1=rs1, imm=shamt)
            return None
        if funct3 == 5:
            funct7 = _bits(word, 31, 25)
            shamt = _bits(word, 24, 20)
            if funct7 == 0:
                return Decoded("SRLIW", pc, length, word, rd=rd, rs1=rs1, imm=shamt)
            if funct7 == 0b0100000:
                return Decoded("SRAIW", pc, length, word, rd=rd, rs1=rs1, imm=shamt)
            return None
        return None
    if op == OP_OP:
        rd = _bits(word, 11, 7)
        rs1 = _bits(word, 19, 15)
        rs2 = _bits(word, 24, 20)
        funct3 = _bits(word, 14, 12)
        funct7 = _bits(word, 31, 25)

        if funct7 == 0b0000001:
            # M extension
            mnem = {
                0: "MUL",
                1: "MULH",
                2: "MULHSU",
                3: "MULHU",
                4: "DIV",
                5: "DIVU",
                6: "REM",
                7: "REMU",
            }.get(funct3)
            if mnem is None:
                return None
            return Decoded(mnem, pc, length, word, rd=rd, rs1=rs1, rs2=rs2)

        table = {
            (0, 0): "ADD",
            (0, 0b0100000): "SUB",
            (1, 0): "SLL",
            (2, 0): "SLT",
            (3, 0): "SLTU",
            (4, 0): "XOR",
            (5, 0): "SRL",
            (5, 0b0100000): "SRA",
            (6, 0): "OR",
            (7, 0): "AND",
        }
        mnem = table.get((funct3, funct7))
        if mnem is None:
            return None
        return Decoded(mnem, pc, length, word, rd=rd, rs1=rs1, rs2=rs2)
    if op == OP_OP32:
        rd = _bits(word, 11, 7)
        rs1 = _bits(word, 19, 15)
        rs2 = _bits(word, 24, 20)
        funct3 = _bits(word, 14, 12)
        funct7 = _bits(word, 31, 25)
        if funct7 == 0b0000001:
            mnem = {0: "MULW", 4: "DIVW", 5: "DIVUW", 6: "REMW", 7: "REMUW"}.get(
                funct3
            )
            if mnem is None:
                return None
            return Decoded(mnem, pc, length, word, rd=rd, rs1=rs1, rs2=rs2)
        table = {
            (0, 0): "ADDW",
            (0, 0b0100000): "SUBW",
            (1, 0): "SLLW",
            (5, 0): "SRLW",
            (5, 0b0100000): "SRAW",
        }
        mnem = table.get((funct3, funct7))
        if mnem is None:
            return None
        return Decoded(mnem, pc, length, word, rd=rd, rs1=rs1, rs2=rs2)
    if op == OP_FENCE:
        funct3 = _bits(word, 14, 12)
        if funct3 == 0:
            return Decoded("FENCE", pc, length, word)
        if funct3 == 1:
            return Decoded("FENCE.I", pc, length, word)
        return None
    if op == OP_SYSTEM:
        rd = _bits(word, 11, 7)
        rs1 = _bits(word, 19, 15)
        funct3 = _bits(word, 14, 12)
        imm12 = _bits(word, 31, 20)
        if funct3 == 0:
            if imm12 == 0 and rd == 0 and rs1 == 0:
                return Decoded("ECALL", pc, length, word)
            if imm12 == 1 and rd == 0 and rs1 == 0:
                return Decoded("EBREAK", pc, length, word)
            return None
        # CSR: imm holds CSR address.
        mnem = {1: "CSRRW", 2: "CSRRS", 3: "CSRRC", 5: "CSRRWI", 6: "CSRRSI", 7: "CSRRCI"}.get(
            funct3
        )
        if mnem is None:
            return None
        return Decoded(mnem, pc, length, word, rd=rd, rs1=rs1, imm=imm12)
    return None


# ---------------------------------------------------------------------------
# RVC expansion
# ---------------------------------------------------------------------------


def _r_prime(reg3: int) -> int:
    """Map a 3-bit RVC register field to its 5-bit ABI register."""
    return reg3 + 8  # x8..x15


def expand_rvc(half: int) -> int | None:
    """Translate a 16-bit RVC encoding to its 32-bit equivalent.

    Returns ``None`` for reserved or HINT encodings we don't lower.
    """
    half &= 0xFFFF
    op = half & 0x3
    funct3 = (half >> 13) & 0x7

    if op == 0b00:
        if funct3 == 0:
            # C.ADDI4SPN -> addi rd', x2, nzuimm
            rd_p = _r_prime((half >> 2) & 0x7)
            uimm = (
                (((half >> 7) & 0xF) << 6)  # imm[9:6]
                | (((half >> 11) & 0x3) << 4)  # imm[5:4]
                | (((half >> 5) & 0x1) << 3)  # imm[3]
                | (((half >> 6) & 0x1) << 2)  # imm[2]
            )
            if uimm == 0:
                return None  # reserved
            return _encode_i(0, 2, uimm, 0b000, rd_p, 0b0010011)
        if funct3 == 2:
            # C.LW -> lw rd', offset(rs1')
            rs1_p = _r_prime((half >> 7) & 0x7)
            rd_p = _r_prime((half >> 2) & 0x7)
            uimm = (
                (((half >> 10) & 0x7) << 3)  # imm[5:3]
                | (((half >> 6) & 0x1) << 2)  # imm[2]
                | (((half >> 5) & 0x1) << 6)  # imm[6]
            )
            return _encode_i(0, rs1_p, uimm, 0b010, rd_p, 0b0000011)
        if funct3 == 3:
            # C.LD -> ld rd', offset(rs1')
            rs1_p = _r_prime((half >> 7) & 0x7)
            rd_p = _r_prime((half >> 2) & 0x7)
            uimm = (
                (((half >> 10) & 0x7) << 3)
                | (((half >> 5) & 0x3) << 6)
            )
            return _encode_i(0, rs1_p, uimm, 0b011, rd_p, 0b0000011)
        if funct3 == 6:
            # C.SW -> sw rs2', offset(rs1')
            rs1_p = _r_prime((half >> 7) & 0x7)
            rs2_p = _r_prime((half >> 2) & 0x7)
            uimm = (
                (((half >> 10) & 0x7) << 3)
                | (((half >> 6) & 0x1) << 2)
                | (((half >> 5) & 0x1) << 6)
            )
            return _encode_s(uimm, rs2_p, rs1_p, 0b010, 0b0100011)
        if funct3 == 7:
            # C.SD
            rs1_p = _r_prime((half >> 7) & 0x7)
            rs2_p = _r_prime((half >> 2) & 0x7)
            uimm = (
                (((half >> 10) & 0x7) << 3)
                | (((half >> 5) & 0x3) << 6)
            )
            return _encode_s(uimm, rs2_p, rs1_p, 0b011, 0b0100011)
        return None
    if op == 0b01:
        if funct3 == 0:
            # C.NOP / C.ADDI
            rd = (half >> 7) & 0x1F
            imm = (((half >> 12) & 0x1) << 5) | ((half >> 2) & 0x1F)
            imm = _sext(imm, 6)
            return _encode_i(imm & 0xFFF, rd, imm & 0xFFF, 0b000, rd, 0b0010011)
        if funct3 == 1:
            # C.ADDIW (RV64) -> addiw rd, rd, imm
            rd = (half >> 7) & 0x1F
            if rd == 0:
                return None
            imm = (((half >> 12) & 0x1) << 5) | ((half >> 2) & 0x1F)
            imm = _sext(imm, 6)
            return _encode_i(imm & 0xFFF, rd, imm & 0xFFF, 0b000, rd, 0b0011011)
        if funct3 == 2:
            # C.LI -> addi rd, x0, imm
            rd = (half >> 7) & 0x1F
            if rd == 0:
                return None
            imm = (((half >> 12) & 0x1) << 5) | ((half >> 2) & 0x1F)
            imm = _sext(imm, 6)
            return _encode_i(imm & 0xFFF, 0, imm & 0xFFF, 0b000, rd, 0b0010011)
        if funct3 == 3:
            rd = (half >> 7) & 0x1F
            if rd == 2:
                # C.ADDI16SP -> addi sp, sp, nzimm
                imm = (
                    (((half >> 12) & 0x1) << 9)
                    | (((half >> 3) & 0x3) << 7)
                    | (((half >> 5) & 0x1) << 6)
                    | (((half >> 2) & 0x1) << 5)
                    | (((half >> 6) & 0x1) << 4)
                )
                imm = _sext(imm, 10)
                if imm == 0:
                    return None
                return _encode_i(imm & 0xFFF, 2, imm & 0xFFF, 0b000, 2, 0b0010011)
            if rd != 0:
                # C.LUI rd, nzuimm
                imm17_12 = (((half >> 12) & 0x1) << 5) | ((half >> 2) & 0x1F)
                imm17_12 = _sext(imm17_12, 6)
                imm = (imm17_12 << 12) & 0xFFFFFFFF
                if imm == 0:
                    return None
                return ((imm >> 12) & 0xFFFFF) << 12 | (rd << 7) | 0b0110111
            return None
        if funct3 == 4:
            funct2 = (half >> 10) & 0x3
            rd_p = _r_prime((half >> 7) & 0x7)
            if funct2 == 0:
                # C.SRLI rd', shamt
                shamt = (((half >> 12) & 0x1) << 5) | ((half >> 2) & 0x1F)
                return _encode_i_shift(0, rd_p, shamt, 0b101, rd_p, 0b0010011, funct6=0b000000)
            if funct2 == 1:
                # C.SRAI
                shamt = (((half >> 12) & 0x1) << 5) | ((half >> 2) & 0x1F)
                return _encode_i_shift(0, rd_p, shamt, 0b101, rd_p, 0b0010011, funct6=0b010000)
            if funct2 == 2:
                # C.ANDI
                imm = (((half >> 12) & 0x1) << 5) | ((half >> 2) & 0x1F)
                imm = _sext(imm, 6)
                return _encode_i(imm & 0xFFF, rd_p, imm & 0xFFF, 0b111, rd_p, 0b0010011)
            if funct2 == 3:
                rd_p = _r_prime((half >> 7) & 0x7)
                rs2_p = _r_prime((half >> 2) & 0x7)
                bit12 = (half >> 12) & 0x1
                f2 = (half >> 5) & 0x3
                if bit12 == 0:
                    table = {
                        0b00: ("SUB", 0b000, 0b0100000, 0b0110011),
                        0b01: ("XOR", 0b100, 0b0000000, 0b0110011),
                        0b10: ("OR", 0b110, 0b0000000, 0b0110011),
                        0b11: ("AND", 0b111, 0b0000000, 0b0110011),
                    }
                else:
                    table = {
                        0b00: ("SUBW", 0b000, 0b0100000, 0b0111011),
                        0b01: ("ADDW", 0b000, 0b0000000, 0b0111011),
                    }
                ent = table.get(f2)
                if ent is None:
                    return None
                _, funct3_, funct7_, op_ = ent
                return _encode_r(funct7_, rs2_p, rd_p, funct3_, rd_p, op_)
            return None
        if funct3 == 5:
            # C.J -> jal x0, offset
            imm = (
                (((half >> 12) & 0x1) << 11)
                | (((half >> 11) & 0x1) << 4)
                | (((half >> 9) & 0x3) << 8)
                | (((half >> 8) & 0x1) << 10)
                | (((half >> 7) & 0x1) << 6)
                | (((half >> 6) & 0x1) << 7)
                | (((half >> 3) & 0x7) << 1)
                | (((half >> 2) & 0x1) << 5)
            )
            imm = _sext(imm, 12)
            return _encode_j(imm, 0, 0b1101111)
        if funct3 == 6 or funct3 == 7:
            # C.BEQZ / C.BNEZ
            rs1_p = _r_prime((half >> 7) & 0x7)
            imm = (
                (((half >> 12) & 0x1) << 8)
                | (((half >> 10) & 0x3) << 3)
                | (((half >> 5) & 0x3) << 6)
                | (((half >> 3) & 0x3) << 1)
                | (((half >> 2) & 0x1) << 5)
            )
            imm = _sext(imm, 9)
            funct3_b = 0b000 if funct3 == 6 else 0b001
            return _encode_b(imm, 0, rs1_p, funct3_b, 0b1100011)
        return None
    if op == 0b10:
        if funct3 == 0:
            # C.SLLI
            rd = (half >> 7) & 0x1F
            shamt = (((half >> 12) & 0x1) << 5) | ((half >> 2) & 0x1F)
            if rd == 0:
                return None
            return _encode_i_shift(0, rd, shamt, 0b001, rd, 0b0010011, funct6=0b000000)
        if funct3 == 2:
            # C.LWSP -> lw rd, offset(sp)
            rd = (half >> 7) & 0x1F
            if rd == 0:
                return None
            uimm = (
                (((half >> 12) & 0x1) << 5)
                | (((half >> 4) & 0x7) << 2)
                | (((half >> 2) & 0x3) << 6)
            )
            return _encode_i(uimm, 2, uimm, 0b010, rd, 0b0000011)
        if funct3 == 3:
            # C.LDSP
            rd = (half >> 7) & 0x1F
            if rd == 0:
                return None
            uimm = (
                (((half >> 12) & 0x1) << 5)
                | (((half >> 5) & 0x3) << 3)
                | (((half >> 2) & 0x7) << 6)
            )
            return _encode_i(uimm, 2, uimm, 0b011, rd, 0b0000011)
        if funct3 == 4:
            bit12 = (half >> 12) & 0x1
            rd = (half >> 7) & 0x1F
            rs2 = (half >> 2) & 0x1F
            if bit12 == 0:
                if rs2 == 0:
                    if rd == 0:
                        return None
                    # C.JR -> jalr x0, 0(rd)
                    return _encode_i(0, rd, 0, 0b000, 0, 0b1100111)
                if rd != 0:
                    # C.MV -> add rd, x0, rs2
                    return _encode_r(0, rs2, 0, 0b000, rd, 0b0110011)
                return None
            else:
                if rs2 == 0 and rd == 0:
                    # C.EBREAK
                    return 0x00100073
                if rs2 == 0:
                    # C.JALR -> jalr x1, 0(rd)
                    return _encode_i(0, rd, 0, 0b000, 1, 0b1100111)
                if rd != 0:
                    # C.ADD -> add rd, rd, rs2
                    return _encode_r(0, rs2, rd, 0b000, rd, 0b0110011)
                return None
        if funct3 == 6:
            # C.SWSP -> sw rs2, offset(sp)
            rs2 = (half >> 2) & 0x1F
            uimm = (((half >> 9) & 0xF) << 2) | (((half >> 7) & 0x3) << 6)
            return _encode_s(uimm, rs2, 2, 0b010, 0b0100011)
        if funct3 == 7:
            # C.SDSP
            rs2 = (half >> 2) & 0x1F
            uimm = (((half >> 10) & 0x7) << 3) | (((half >> 7) & 0x7) << 6)
            return _encode_s(uimm, rs2, 2, 0b011, 0b0100011)
        return None
    return None


# Encoders: produce 32-bit words from RVC fields. ``imm`` is interpreted
# as the *post-decoding* immediate.


def _encode_i(_unused: int, rs1: int, imm: int, funct3: int, rd: int, opcode: int) -> int:
    imm12 = imm & 0xFFF
    return (
        ((imm12 & 0xFFF) << 20)
        | ((rs1 & 0x1F) << 15)
        | ((funct3 & 0x7) << 12)
        | ((rd & 0x1F) << 7)
        | (opcode & 0x7F)
    )


def _encode_i_shift(
    _unused: int,
    rs1: int,
    shamt: int,
    funct3: int,
    rd: int,
    opcode: int,
    funct6: int,
) -> int:
    return (
        ((funct6 & 0x3F) << 26)
        | ((shamt & 0x3F) << 20)
        | ((rs1 & 0x1F) << 15)
        | ((funct3 & 0x7) << 12)
        | ((rd & 0x1F) << 7)
        | (opcode & 0x7F)
    )


def _encode_s(imm: int, rs2: int, rs1: int, funct3: int, opcode: int) -> int:
    imm12 = imm & 0xFFF
    return (
        (((imm12 >> 5) & 0x7F) << 25)
        | ((rs2 & 0x1F) << 20)
        | ((rs1 & 0x1F) << 15)
        | ((funct3 & 0x7) << 12)
        | ((imm12 & 0x1F) << 7)
        | (opcode & 0x7F)
    )


def _encode_b(imm: int, rs2: int, rs1: int, funct3: int, opcode: int) -> int:
    imm = imm & 0x1FFF
    return (
        (((imm >> 12) & 0x1) << 31)
        | (((imm >> 5) & 0x3F) << 25)
        | ((rs2 & 0x1F) << 20)
        | ((rs1 & 0x1F) << 15)
        | ((funct3 & 0x7) << 12)
        | (((imm >> 1) & 0xF) << 8)
        | (((imm >> 11) & 0x1) << 7)
        | (opcode & 0x7F)
    )


def _encode_j(imm: int, rd: int, opcode: int) -> int:
    imm = imm & 0x1FFFFF
    return (
        (((imm >> 20) & 0x1) << 31)
        | (((imm >> 1) & 0x3FF) << 21)
        | (((imm >> 11) & 0x1) << 20)
        | (((imm >> 12) & 0xFF) << 12)
        | ((rd & 0x1F) << 7)
        | (opcode & 0x7F)
    )


def _encode_r(funct7: int, rs2: int, rs1: int, funct3: int, rd: int, opcode: int) -> int:
    return (
        ((funct7 & 0x7F) << 25)
        | ((rs2 & 0x1F) << 20)
        | ((rs1 & 0x1F) << 15)
        | ((funct3 & 0x7) << 12)
        | ((rd & 0x1F) << 7)
        | (opcode & 0x7F)
    )


def decode_compressed(half: int, pc: int = 0) -> Decoded | None:
    word = expand_rvc(half)
    if word is None:
        return None
    d = decode(word, pc, length=2)
    if d is None:
        return None
    return Decoded(
        mnemonic=d.mnemonic,
        pc=d.pc,
        length=2,
        raw=half & 0xFFFF,
        expanded=word,
        rd=d.rd,
        rs1=d.rs1,
        rs2=d.rs2,
        imm=d.imm,
    )


__all__ = ["Decoded", "decode", "decode_compressed", "expand_rvc"]
