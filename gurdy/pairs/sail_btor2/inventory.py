"""Construct-coverage inventory for sail-btor2 (BENCHMARKS.md §2): the
Sail-realized RV64 core slice — the ALU/M datapaths plus control flow
(branches, JAL/JALR, FENCE). One probe per construct; ``coverage()`` measures
how many translate without an ``Unsupported`` abort."""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from ...languages.riscv import asm, casm  # ISA-level encoders (shared); semantics stay independent
from ...languages.sail import compressed
from .translate import translate


def _p(*words: int) -> dict:
    return {"words": [*words, asm.ecall()], "entry": 0, "init_regs": {}}


def _pc(*halfs: int) -> dict:
    """A compressed-instruction probe: each 16-bit unit is expanded (via the
    Sail realization's own decompressor) into the program the pair lowers, with
    ``lengths`` carrying the true 2-byte widths. ``halfs`` keeps the original
    compressed encoding so ``riscv-sail`` can build a real RV64C image."""
    words = [compressed.expand(h) for h in halfs] + [asm.ecall()]
    lengths = [2] * len(halfs) + [4]
    return {"words": words, "lengths": lengths, "entry": 0, "init_regs": {}, "halfs": list(halfs)}


CORE_PROBES: dict[str, dict] = {
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
    # control flow
    "BEQ": _p(asm.beq(1, 2, 8)), "BNE": _p(asm.bne(1, 2, 8)), "BLT": _p(asm.blt(1, 2, 8)),
    "BGE": _p(asm.bge(1, 2, 8)), "BLTU": _p(asm.bltu(1, 2, 8)), "BGEU": _p(asm.bgeu(1, 2, 8)),
    "JAL": _p(asm.jal(1, 8)), "JALR": _p(asm.jalr(1, 2, 0)), "FENCE": _p(asm.fence()),
    # loads / stores
    "LB": _p(asm.lb(1, 2, 0)), "LH": _p(asm.lh(1, 2, 0)), "LW": _p(asm.lw(1, 2, 0)),
    "LD": _p(asm.ld(1, 2, 0)), "LBU": _p(asm.lbu(1, 2, 0)), "LHU": _p(asm.lhu(1, 2, 0)),
    "LWU": _p(asm.lwu(1, 2, 0)),
    "SB": _p(asm.sb(1, 2, 0)), "SH": _p(asm.sh(1, 2, 0)), "SW": _p(asm.sw(1, 2, 0)),
    "SD": _p(asm.sd(1, 2, 0)),
}

# RV64C — the compressed extension, expanded to base instructions (the C
# extension carries no new semantics). Brings the Sail route to RV64IMC parity
# with the direct riscv-btor2 route, so the branch cross-check is full-width.
RV64C_PROBES: dict[str, dict] = {
    "C.ADDI4SPN": _pc(casm.c_addi4spn(8, 16)),
    "C.LW": _pc(casm.c_lw(8, 9, 8)), "C.LD": _pc(casm.c_ld(8, 9, 16)),
    "C.SW": _pc(casm.c_sw(8, 9, 8)), "C.SD": _pc(casm.c_sd(8, 9, 16)),
    "C.ADDI": _pc(casm.c_addi(10, -3)), "C.ADDIW": _pc(casm.c_addiw(10, 7)),
    "C.LI": _pc(casm.c_li(10, 5)), "C.LUI": _pc(casm.c_lui(10, 1)),
    "C.ADDI16SP": _pc(casm.c_addi16sp(32)),
    "C.SRLI": _pc(casm.c_srli(8, 3)), "C.SRAI": _pc(casm.c_srai(8, 3)),
    "C.ANDI": _pc(casm.c_andi(8, 6)),
    "C.SUB": _pc(casm.c_sub(8, 9)), "C.XOR": _pc(casm.c_xor(8, 9)),
    "C.OR": _pc(casm.c_or(8, 9)), "C.AND": _pc(casm.c_and(8, 9)),
    "C.SUBW": _pc(casm.c_subw(8, 9)), "C.ADDW": _pc(casm.c_addw(8, 9)),
    "C.J": _pc(casm.c_j(0x40)), "C.BEQZ": _pc(casm.c_beqz(8, 0x20)),
    "C.BNEZ": _pc(casm.c_bnez(8, -0x10)), "C.SLLI": _pc(casm.c_slli(10, 4)),
    "C.LWSP": _pc(casm.c_lwsp(10, 16)), "C.LDSP": _pc(casm.c_ldsp(10, 32)),
    "C.SWSP": _pc(casm.c_swsp(10, 16)), "C.SDSP": _pc(casm.c_sdsp(10, 32)),
    "C.JR": _pc(casm.c_jr(5)), "C.MV": _pc(casm.c_mv(11, 10)),
    "C.JALR": _pc(casm.c_jalr(5)), "C.ADD": _pc(casm.c_add(11, 10)),
    "C.EBREAK": _pc(casm.c_ebreak()),
}

ALL_PROBES: dict[str, dict] = {**CORE_PROBES, **RV64C_PROBES}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
