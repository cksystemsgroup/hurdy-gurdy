"""The RV64I construct-coverage inventory for riscv-btor2 (BENCHMARKS.md §2).

One minimal probe per RV64I base-integer construct (the spec-derived
denominator the agent does not choose). ``coverage()`` measures how many
translate without an ``Unsupported`` abort.
"""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from ...languages.riscv import asm
from ...languages.riscv.interp import image_from_words
from .translate import translate


def _p(*words: int) -> dict:
    return {"image": image_from_words([*words, asm.ecall()]), "init_regs": {}}


RV64I_PROBES: dict[str, dict] = {
    "LUI": _p(asm.lui(1, 0x1000)),
    "AUIPC": _p(asm.auipc(1, 0x1000)),
    "JAL": _p(asm.jal(1, 8)),
    "JALR": _p(asm.jalr(1, 2, 0)),
    "BEQ": _p(asm.beq(1, 2, 8)), "BNE": _p(asm.bne(1, 2, 8)),
    "BLT": _p(asm.blt(1, 2, 8)), "BGE": _p(asm.bge(1, 2, 8)),
    "BLTU": _p(asm.bltu(1, 2, 8)), "BGEU": _p(asm.bgeu(1, 2, 8)),
    "LB": _p(asm.lb(1, 2, 0)), "LH": _p(asm.lh(1, 2, 0)), "LW": _p(asm.lw(1, 2, 0)),
    "LD": _p(asm.ld(1, 2, 0)), "LBU": _p(asm.lbu(1, 2, 0)),
    "LHU": _p(asm.lhu(1, 2, 0)), "LWU": _p(asm.lwu(1, 2, 0)),
    "SB": _p(asm.sb(1, 2, 0)), "SH": _p(asm.sh(1, 2, 0)),
    "SW": _p(asm.sw(1, 2, 0)), "SD": _p(asm.sd(1, 2, 0)),
    "ADDI": _p(asm.addi(1, 0, 1)), "SLTI": _p(asm.slti(1, 0, 1)),
    "SLTIU": _p(asm.sltiu(1, 0, 1)), "XORI": _p(asm.xori(1, 0, 1)),
    "ORI": _p(asm.ori(1, 0, 1)), "ANDI": _p(asm.andi(1, 0, 1)),
    "SLLI": _p(asm.slli(1, 0, 1)), "SRLI": _p(asm.srli(1, 0, 1)), "SRAI": _p(asm.srai(1, 0, 1)),
    "ADD": _p(asm.add(1, 0, 0)), "SUB": _p(asm.sub(1, 0, 0)), "SLL": _p(asm.sll(1, 0, 0)),
    "SLT": _p(asm.slt(1, 0, 0)), "SLTU": _p(asm.sltu(1, 0, 0)), "XOR": _p(asm.xor(1, 0, 0)),
    "SRL": _p(asm.srl(1, 0, 0)), "SRA": _p(asm.sra(1, 0, 0)),
    "OR": _p(asm.or_(1, 0, 0)), "AND": _p(asm.and_(1, 0, 0)),
    "ADDIW": _p(asm.addiw(1, 0, 1)), "SLLIW": _p(asm.slliw(1, 0, 1)),
    "SRLIW": _p(asm.srliw(1, 0, 1)), "SRAIW": _p(asm.sraiw(1, 0, 1)),
    "ADDW": _p(asm.addw(1, 0, 0)), "SUBW": _p(asm.subw(1, 0, 0)), "SLLW": _p(asm.sllw(1, 0, 0)),
    "SRLW": _p(asm.srlw(1, 0, 0)), "SRAW": _p(asm.sraw(1, 0, 0)),
    "FENCE": _p(asm.fence()),
    "ECALL": _p(),
}


def coverage() -> CoverageReport:
    return measure(translate, RV64I_PROBES)
