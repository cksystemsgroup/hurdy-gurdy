"""Pretty-printer for ``Decoded`` instructions.

Produces compact disassembly with common pseudo-instruction shorthand
(``mv`` for ``addi rd, rs1, 0``; ``nop`` for ``addi x0, x0, 0``; ``ret``
for ``jalr x0, 0(x1)``; ``j label`` for ``jal x0, label``).
"""

from __future__ import annotations

from gurdy.pairs.riscv_btor2.source.decoder import Decoded


_ABI = {
    0: "zero",
    1: "ra",
    2: "sp",
    3: "gp",
    4: "tp",
    5: "t0",
    6: "t1",
    7: "t2",
    8: "s0",
    9: "s1",
    10: "a0",
    11: "a1",
    12: "a2",
    13: "a3",
    14: "a4",
    15: "a5",
    16: "a6",
    17: "a7",
    18: "s2",
    19: "s3",
    20: "s4",
    21: "s5",
    22: "s6",
    23: "s7",
    24: "s8",
    25: "s9",
    26: "s10",
    27: "s11",
    28: "t3",
    29: "t4",
    30: "t5",
    31: "t6",
}


def reg(n: int) -> str:
    return _ABI.get(n, f"x{n}")


def disasm(d: Decoded) -> str:
    m = d.mnemonic
    if m in {"LUI", "AUIPC"}:
        return f"{m.lower()} {reg(d.rd)}, 0x{(d.imm >> 12) & 0xFFFFF:x}"
    if m == "JAL":
        if d.rd == 0:
            return f"j 0x{(d.pc + d.imm) & 0xFFFFFFFFFFFFFFFF:x}"
        if d.rd == 1:
            return f"jal 0x{(d.pc + d.imm) & 0xFFFFFFFFFFFFFFFF:x}"
        return f"jal {reg(d.rd)}, 0x{(d.pc + d.imm) & 0xFFFFFFFFFFFFFFFF:x}"
    if m == "JALR":
        if d.rd == 0 and d.rs1 == 1 and d.imm == 0:
            return "ret"
        return f"jalr {reg(d.rd)}, {d.imm}({reg(d.rs1)})"
    if m in {"BEQ", "BNE", "BLT", "BGE", "BLTU", "BGEU"}:
        return f"{m.lower()} {reg(d.rs1)}, {reg(d.rs2)}, 0x{(d.pc + d.imm) & 0xFFFFFFFFFFFFFFFF:x}"
    if m in {"LB", "LH", "LW", "LD", "LBU", "LHU", "LWU"}:
        return f"{m.lower()} {reg(d.rd)}, {d.imm}({reg(d.rs1)})"
    if m in {"SB", "SH", "SW", "SD"}:
        return f"{m.lower()} {reg(d.rs2)}, {d.imm}({reg(d.rs1)})"
    if m in {"ADDI", "ADDIW"}:
        if m == "ADDI" and d.rd == 0 and d.rs1 == 0 and d.imm == 0:
            return "nop"
        if m == "ADDI" and d.imm == 0:
            return f"mv {reg(d.rd)}, {reg(d.rs1)}"
        return f"{m.lower()} {reg(d.rd)}, {reg(d.rs1)}, {d.imm}"
    if m in {"SLTI", "SLTIU", "XORI", "ORI", "ANDI"}:
        return f"{m.lower()} {reg(d.rd)}, {reg(d.rs1)}, {d.imm}"
    if m in {"SLLI", "SRLI", "SRAI", "SLLIW", "SRLIW", "SRAIW"}:
        return f"{m.lower()} {reg(d.rd)}, {reg(d.rs1)}, {d.imm}"
    if m in {
        "ADD",
        "SUB",
        "SLL",
        "SLT",
        "SLTU",
        "XOR",
        "SRL",
        "SRA",
        "OR",
        "AND",
        "ADDW",
        "SUBW",
        "SLLW",
        "SRLW",
        "SRAW",
        "MUL",
        "MULH",
        "MULHSU",
        "MULHU",
        "DIV",
        "DIVU",
        "REM",
        "REMU",
        "MULW",
        "DIVW",
        "DIVUW",
        "REMW",
        "REMUW",
    }:
        return f"{m.lower()} {reg(d.rd)}, {reg(d.rs1)}, {reg(d.rs2)}"
    if m in {"FENCE", "FENCE.I", "ECALL", "EBREAK"}:
        return m.lower()
    if m.startswith("CSRR"):
        return f"{m.lower()} {reg(d.rd)}, csr_0x{d.imm:x}, {reg(d.rs1)}"
    return f"{m.lower()} ?"


__all__ = ["disasm", "reg"]
