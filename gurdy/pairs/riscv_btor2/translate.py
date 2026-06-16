"""RV64I -> BTOR2 translator (thin slice; pairs/riscv-btor2 brief).

Emits a BTOR2 transition system that models the machine one instruction per
cycle: state ``pc`` (bv64), ``x1..x31`` (bv64; x0 is the zero constant), and
``halted`` (bv1). The fixed program is lowered to a PC-keyed ITE dispatch over
the next-state functions.

Scope (thin-first): the register-register / register-immediate
arithmetic-logic core (ADD/SUB/AND/OR/XOR and their ADDI/ANDI/ORI/XORI
immediates) and ECALL/EBREAK (halt). Branches, loads/stores, shifts, the
W-variants, and the M/C extensions are deferred and hard-abort with
``Unsupported`` (BENCHMARKS.md §3).

Determinism: the artifact is a pure function of ``(image, init_regs)``.
"""

from __future__ import annotations

from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.build import Builder

MASK64 = (1 << 64) - 1


def _sext(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    if v >> (bits - 1):
        v -= 1 << bits
    return v


def _effect(instr: int, addr: int, b: Builder, regs: dict[int, int], zero64: int):
    """Return (writes: {rd: value_node}, next_pc_node, halts)."""
    opcode = instr & 0x7F
    rd = (instr >> 7) & 0x1F
    funct3 = (instr >> 12) & 0x7
    rs1 = (instr >> 15) & 0x1F
    rs2 = (instr >> 20) & 0x1F
    funct7 = (instr >> 25) & 0x7F

    def rderef(i: int) -> int:
        return zero64 if i == 0 else regs[i]

    npc = b.constd(64, (addr + 4) & MASK64)

    if opcode == 0x13:  # OP-IMM
        imm = _sext(instr >> 20, 12) & MASK64
        immc = b.constd(64, imm)
        a = rderef(rs1)
        op = {0: "add", 7: "and", 6: "or", 4: "xor"}.get(funct3)
        if op is None:
            raise Unsupported("riscv-btor2", f"op-imm.funct3={funct3}")
        val = b.op2(op, 64, a, immc)
        return ({rd: val} if rd != 0 else {}), npc, False

    if opcode == 0x33:  # OP
        a, c = rderef(rs1), rderef(rs2)
        alt = funct7 == 0x20
        if funct3 == 0:
            val = b.op2("sub" if alt else "add", 64, a, c)
        elif funct3 in (7, 6, 4):
            val = b.op2({7: "and", 6: "or", 4: "xor"}[funct3], 64, a, c)
        else:
            raise Unsupported("riscv-btor2", f"op.funct3={funct3}")
        return ({rd: val} if rd != 0 else {}), npc, False

    if opcode == 0x73 and funct3 == 0 and (instr >> 20) in (0, 1):  # ECALL / EBREAK
        return {}, npc, True

    raise Unsupported("riscv-btor2", f"opcode=0x{opcode:02x}")


def translate(program: dict[str, Any]) -> bytes:
    image = program["image"]
    init_regs = program.get("init_regs", {})

    b = Builder()
    pc = b.state(64, "pc")
    regs = {r: b.state(64, f"x{r}") for r in range(1, 32)}
    halted = b.state(1, "halted")
    zero64 = b.zero(64)

    b.init(pc, b.constd(64, image.entry))
    for r in range(1, 32):
        b.init(regs[r], b.constd(64, int(init_regs.get(r, 0)) & MASK64))
    b.init(halted, b.zero(1))

    not_halted = b.op1("not", 1, halted)
    next_pc = pc
    next_regs = dict(regs)
    next_halted = halted

    for addr in range(image.code_lo, image.code_hi or image.code_lo, 4):
        instr = image.load(addr, 4)
        writes, npc, halts = _effect(instr, addr, b, regs, zero64)
        at = b.op2("eq", 1, pc, b.constd(64, addr))
        active = b.op2("and", 1, at, not_halted)
        next_pc = b.ite(64, active, npc, next_pc)
        for r, val in writes.items():
            next_regs[r] = b.ite(64, active, val, next_regs[r])
        if halts:
            next_halted = b.ite(1, active, b.one(1), next_halted)

    b.next(pc, next_pc)
    for r in range(1, 32):
        b.next(regs[r], next_regs[r])
    b.next(halted, next_halted)
    return b.to_text().encode("utf-8")
