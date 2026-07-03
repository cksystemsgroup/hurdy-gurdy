"""The language-owned RV64IMC construct inventory (BENCHMARKS.md §2).

One minimal probe per RV64IMC construct — the spec-derived yardstick owned by
the *language*, not by any pair (Definition 4.6 fixes the inventory per
language): every pair whose source is RISC-V is measured against this same
denominator, and composed routes headed by RISC-V share it too, so two routes
from the same source cannot quote different totals.

Derived from the RISC-V unprivileged spec: the RV64I base (§2, §4-5 of the
ISA manual), the M extension (§7), and the C extension (§16). Probes are
memory images (``image_from_words`` / 16-bit ``image_from_bytes`` for the
compressed forms, so a route exercises real decompression).
"""

from __future__ import annotations

import struct

from . import asm, casm
from .interp import image_from_bytes, image_from_words


def _p(*words: int) -> dict:
    return {"image": image_from_words([*words, asm.ecall()]), "init_regs": {}}


# Distinguishing operands for ALU/compare probes: x2 = -5 (sign bit set,
# huge unsigned), x3 = 3. Degenerate operands (x0, x0) cannot separate
# signed from unsigned or logical from arithmetic — the fault-injection
# experiment measured exactly that escape (a translator emitting SRA for
# SRL passes an all-zeros probe), so the probes carry values on which the
# construct's semantics is *observable* (incident I23).
_NEG, _POS = -5, 3


def _pr(op_word_fn) -> dict:
    """R-type probe: x1 := op(x2 = -5, x3 = 3)."""
    return _p(asm.addi(2, 0, _NEG), asm.addi(3, 0, _POS), op_word_fn(1, 2, 3))


def _pi(op_word_fn, imm: int = _POS) -> dict:
    """I-type probe: x1 := op(x2 = -5, imm)."""
    return _p(asm.addi(2, 0, _NEG), op_word_fn(1, 2, imm))


def _pcmp(op_word_fn) -> dict:
    """Comparison probe: an *equal-operand* instance first (strict vs
    non-strict is observable only at equality — the second hardening round;
    the fault-injection experiment's ult->ulte mutants escaped mixed-sign
    operands), then the mixed-sign instance (signedness)."""
    return _p(asm.addi(2, 0, _NEG), asm.addi(3, 0, _POS),
              op_word_fn(4, 2, 2), op_word_fn(1, 2, 3))


def _pcmpi(op_word_fn) -> dict:
    """Compare-immediate probe: equal (x2 = -5 vs imm -5), then mixed."""
    return _p(asm.addi(2, 0, _NEG),
              op_word_fn(4, 2, _NEG), op_word_fn(1, 2, _POS))


def _pbr(op_word_fn) -> dict:
    """Branch probe: an equal-operand instance then a mixed-sign instance,
    each skipping a marker write when taken, so strictness and signedness
    are both observable in the marker registers (x5, x6)."""
    return _p(asm.addi(2, 0, _NEG), asm.addi(3, 0, _POS),
              op_word_fn(2, 2, 8), asm.addi(5, 0, 1),
              op_word_fn(2, 3, 8), asm.addi(6, 0, 1))


def _pc(*halfwords: int) -> dict:
    """A compressed-instruction probe: 16-bit instrs then a 32-bit ECALL."""
    code = b"".join(struct.pack("<H", h & 0xFFFF) for h in halfwords)
    return {"image": image_from_bytes(code + struct.pack("<I", asm.ecall())), "init_regs": {}}


RV64I_PROBES: dict[str, dict] = {
    "LUI": _p(asm.lui(1, 0x1000)),
    "AUIPC": _p(asm.auipc(1, 0x1000)),
    "JAL": _p(asm.jal(1, 8)),
    "JALR": _p(asm.jalr(1, 2, 0)),
    # Branch probes run an equal-operand and a mixed-sign (-5 vs 3)
    # instance, so the signed/unsigned variants take opposite arms and the
    # strict/non-strict variants differ at equality (see _pbr).
    "BEQ": _pbr(asm.beq), "BNE": _pbr(asm.bne),
    "BLT": _pbr(asm.blt), "BGE": _pbr(asm.bge),
    "BLTU": _pbr(asm.bltu), "BGEU": _pbr(asm.bgeu),
    "LB": _p(asm.lb(1, 2, 0)), "LH": _p(asm.lh(1, 2, 0)), "LW": _p(asm.lw(1, 2, 0)),
    "LD": _p(asm.ld(1, 2, 0)), "LBU": _p(asm.lbu(1, 2, 0)),
    "LHU": _p(asm.lhu(1, 2, 0)), "LWU": _p(asm.lwu(1, 2, 0)),
    # Stores write past the code (offset 16): SD's 8-byte store at offset 0
    # would overwrite its own ECALL terminator, making the probe unrunnable by
    # the reference interpreter — invisible to acceptance-only measurement,
    # caught the first time the square ran on it.
    "SB": _p(asm.sb(1, 2, 16)), "SH": _p(asm.sh(1, 2, 16)),
    "SW": _p(asm.sw(1, 2, 16)), "SD": _p(asm.sd(1, 2, 16)),
    "ADDI": _pi(asm.addi), "SLTI": _pcmpi(asm.slti),
    "SLTIU": _pcmpi(asm.sltiu), "XORI": _pi(asm.xori),
    "ORI": _pi(asm.ori), "ANDI": _pi(asm.andi),
    "SLLI": _pi(asm.slli), "SRLI": _pi(asm.srli), "SRAI": _pi(asm.srai),
    "ADD": _pr(asm.add), "SUB": _pr(asm.sub), "SLL": _pr(asm.sll),
    "SLT": _pcmp(asm.slt), "SLTU": _pcmp(asm.sltu), "XOR": _pr(asm.xor),
    "SRL": _pr(asm.srl), "SRA": _pr(asm.sra),
    "OR": _pr(asm.or_), "AND": _pr(asm.and_),
    "ADDIW": _pi(asm.addiw), "SLLIW": _pi(asm.slliw),
    "SRLIW": _pi(asm.srliw), "SRAIW": _pi(asm.sraiw),
    "ADDW": _pr(asm.addw), "SUBW": _pr(asm.subw), "SLLW": _pr(asm.sllw),
    "SRLW": _pr(asm.srlw), "SRAW": _pr(asm.sraw),
    "FENCE": _p(asm.fence()),
    "ECALL": _p(),
}

RV64M_PROBES: dict[str, dict] = {
    "MUL": _pr(asm.mul), "MULH": _pr(asm.mulh),
    "MULHSU": _pr(asm.mulhsu), "MULHU": _pr(asm.mulhu),
    "DIV": _pr(asm.div), "DIVU": _pr(asm.divu),
    "REM": _pr(asm.rem), "REMU": _pr(asm.remu),
    "MULW": _pr(asm.mulw), "DIVW": _pr(asm.divw),
    "DIVUW": _pr(asm.divuw), "REMW": _pr(asm.remw),
    "REMUW": _pr(asm.remuw),
}

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

# RV64IMC — the language-owned denominator every RISC-V-headed pair and route
# is measured against.
ALL_PROBES: dict[str, dict] = {**RV64I_PROBES, **RV64M_PROBES, **RV64C_PROBES}
