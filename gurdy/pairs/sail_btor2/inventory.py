"""Construct-coverage inventory for sail-btor2 (BENCHMARKS.md §2): the
Sail-realized RV64 ALU slice. One probe per instruction the EXEC table
realizes; ``coverage()`` measures how many translate without abort."""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from ...languages.riscv import asm  # ISA-level encoders (shared); semantics stay independent
from .translate import translate


def _p(*words: int) -> dict:
    return {"words": [*words, asm.ecall()], "entry": 0, "init_regs": {}}


ALU_PROBES: dict[str, dict] = {
    "ADD": _p(asm.add(1, 0, 0)), "SUB": _p(asm.sub(1, 0, 0)), "SLL": _p(asm.sll(1, 0, 0)),
    "SLT": _p(asm.slt(1, 0, 0)), "SLTU": _p(asm.sltu(1, 0, 0)), "XOR": _p(asm.xor(1, 0, 0)),
    "SRL": _p(asm.srl(1, 0, 0)), "SRA": _p(asm.sra(1, 0, 0)), "OR": _p(asm.or_(1, 0, 0)),
    "AND": _p(asm.and_(1, 0, 0)),
    "ADDI": _p(asm.addi(1, 0, 1)), "SLTI": _p(asm.slti(1, 0, 1)), "SLTIU": _p(asm.sltiu(1, 0, 1)),
    "XORI": _p(asm.xori(1, 0, 1)), "ORI": _p(asm.ori(1, 0, 1)), "ANDI": _p(asm.andi(1, 0, 1)),
    "SLLI": _p(asm.slli(1, 0, 1)), "SRLI": _p(asm.srli(1, 0, 1)), "SRAI": _p(asm.srai(1, 0, 1)),
    "ADDW": _p(asm.addw(1, 0, 0)), "SUBW": _p(asm.subw(1, 0, 0)), "SLLW": _p(asm.sllw(1, 0, 0)),
    "SRLW": _p(asm.srlw(1, 0, 0)), "SRAW": _p(asm.sraw(1, 0, 0)),
    "ADDIW": _p(asm.addiw(1, 0, 1)), "SLLIW": _p(asm.slliw(1, 0, 1)),
    "SRLIW": _p(asm.srliw(1, 0, 1)), "SRAIW": _p(asm.sraiw(1, 0, 1)),
    "LUI": _p(asm.lui(1, 0x1000)), "AUIPC": _p(asm.auipc(1, 0x1000)),
    "MUL": _p(asm.mul(1, 0, 0)), "MULH": _p(asm.mulh(1, 0, 0)), "MULHSU": _p(asm.mulhsu(1, 0, 0)),
    "MULHU": _p(asm.mulhu(1, 0, 0)), "DIV": _p(asm.div(1, 0, 0)), "DIVU": _p(asm.divu(1, 0, 0)),
    "REM": _p(asm.rem(1, 0, 0)), "REMU": _p(asm.remu(1, 0, 0)),
    "MULW": _p(asm.mulw(1, 0, 0)), "DIVW": _p(asm.divw(1, 0, 0)), "DIVUW": _p(asm.divuw(1, 0, 0)),
    "REMW": _p(asm.remw(1, 0, 0)), "REMUW": _p(asm.remuw(1, 0, 0)),
}


def coverage() -> CoverageReport:
    return measure(translate, ALU_PROBES)
