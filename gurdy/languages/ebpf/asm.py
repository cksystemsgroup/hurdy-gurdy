"""Minimal eBPF instruction encoders for tests and coverage probes.

One helper per encoding form (64-bit little-endian instruction word); the
op-code nibble is passed explicitly so the coverage inventory can enumerate
the ALU/JMP op space without a helper per mnemonic.
"""

from __future__ import annotations

MASK32 = (1 << 32) - 1

# eBPF instruction classes (low 3 bits of the opcode byte).
LD, LDX, ST, STX, ALU, JMP, JMP32, ALU64 = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07
SRC_X = 0x08  # operand from src register (else from imm)


def _insn(code: int, dst: int, src: int, off: int, imm: int) -> int:
    return (
        (code & 0xFF)
        | ((dst & 0xF) << 8)
        | ((src & 0xF) << 12)
        | ((off & 0xFFFF) << 16)
        | ((imm & MASK32) << 32)
    )


# --- ALU / ALU64 -----------------------------------------------------------
def alu64_imm(op: int, dst: int, imm: int) -> int:
    return _insn(ALU64 | (op << 4), dst, 0, 0, imm)


def alu64_reg(op: int, dst: int, src: int) -> int:
    return _insn(ALU64 | SRC_X | (op << 4), dst, src, 0, 0)


def alu32_imm(op: int, dst: int, imm: int) -> int:
    return _insn(ALU | (op << 4), dst, 0, 0, imm)


def alu32_reg(op: int, dst: int, src: int) -> int:
    return _insn(ALU | SRC_X | (op << 4), dst, src, 0, 0)


# --- byte-swap (BPF_END) ---------------------------------------------------
# op nibble 0xD; ALU class with SRC_X=0 -> to_le, SRC_X=1 -> to_be; ALU64 class
# (SRC_X reserved 0) -> unconditional bswap. The imm field carries the width.
END = 0xD


def end_le(dst: int, width: int) -> int:
    return _insn(ALU | (END << 4), dst, 0, 0, width)


def end_be(dst: int, width: int) -> int:
    return _insn(ALU | SRC_X | (END << 4), dst, 0, 0, width)


def bswap(dst: int, width: int) -> int:          # ALU64 unconditional byteswap
    return _insn(ALU64 | (END << 4), dst, 0, 0, width)


# named conveniences used by the tests
def mov64(dst: int, imm: int) -> int:
    return alu64_imm(0xB, dst, imm)


def mov64_reg(dst: int, src: int) -> int:
    return alu64_reg(0xB, dst, src)


def add64(dst: int, imm: int) -> int:
    return alu64_imm(0x0, dst, imm)


def add64_reg(dst: int, src: int) -> int:
    return alu64_reg(0x0, dst, src)


def sub64(dst: int, imm: int) -> int:
    return alu64_imm(0x1, dst, imm)


def mul64(dst: int, imm: int) -> int:
    return alu64_imm(0x2, dst, imm)


def div64_reg(dst: int, src: int) -> int:
    return alu64_reg(0x3, dst, src)


def mod64_reg(dst: int, src: int) -> int:
    return alu64_reg(0x9, dst, src)


def mov32(dst: int, imm: int) -> int:
    return alu32_imm(0xB, dst, imm)


# --- JMP / JMP32 -----------------------------------------------------------
def ja(off: int) -> int:
    return _insn(JMP, 0, 0, off, 0)


def jmp_imm(op: int, dst: int, imm: int, off: int) -> int:
    return _insn(JMP | (op << 4), dst, 0, off, imm)


def jmp_reg(op: int, dst: int, src: int, off: int) -> int:
    return _insn(JMP | SRC_X | (op << 4), dst, src, off, 0)


def jmp32_imm(op: int, dst: int, imm: int, off: int) -> int:
    return _insn(JMP32 | (op << 4), dst, 0, off, imm)


def jmp32_reg(op: int, dst: int, src: int, off: int) -> int:
    return _insn(JMP32 | SRC_X | (op << 4), dst, src, off, 0)


def call(helper: int) -> int:
    return _insn(JMP | (0x8 << 4), 0, 0, 0, helper)


def exit_() -> int:
    return _insn(JMP | (0x9 << 4), 0, 0, 0, 0)


# --- memory ----------------------------------------------------------------
_SZ = {1: 0x10, 2: 0x08, 4: 0x00, 8: 0x18}  # byte/half/word/double size bits


def lddw(dst: int, imm64: int) -> list[int]:
    return [
        _insn(0x18, dst, 0, 0, imm64 & MASK32),
        _insn(0x00, 0, 0, 0, (imm64 >> 32) & MASK32),
    ]


def ldx(size: int, dst: int, src: int, off: int) -> int:
    return _insn(0x61 | _SZ[size], dst, src, off, 0)


def stx(size: int, dst: int, src: int, off: int) -> int:
    return _insn(0x63 | _SZ[size], dst, src, off, 0)


def st(size: int, dst: int, imm: int, off: int) -> int:
    return _insn(0x62 | _SZ[size], dst, 0, off, imm)


# --- legacy packet loads (LD class, ABS/IND modes) -------------------------
# LD|ABS|sz reads the packet at absolute offset = imm into r0; LD|IND|sz at
# offset = src + imm. Big-endian. size is 1/2/4 (B/H/W; no double).
LD_ABS, LD_IND = 0x20, 0x40
_PKT_SZ = {1: 0x10, 2: 0x08, 4: 0x00}  # byte/half/word size bits (no double)


def ld_abs(size: int, imm: int) -> int:           # r0 = *(size*)(packet + imm)
    return _insn(LD | LD_ABS | _PKT_SZ[size], 0, 0, 0, imm)


def ld_ind(size: int, src: int, imm: int) -> int:  # r0 = *(size*)(packet+src+imm)
    return _insn(LD | LD_IND | _PKT_SZ[size], 0, src, 0, imm)
