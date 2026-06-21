"""RV64I -> BTOR2 translator (pairs/riscv-btor2 brief).

Emits a BTOR2 transition system modeling the machine one instruction per
cycle: state ``pc`` (bv64), ``x1..x31`` (bv64; x0 is the zero constant),
``halted`` (bv1), and — when the program touches memory — ``mem`` (an
``Array bv64 bv8``). The fixed program is lowered to a PC-keyed ITE dispatch
over the per-instruction next-state functions.

Scope: the RV64IMC user ISA the shared interpreter implements — the RV64I base
(LUI/AUIPC, JAL/JALR, the branches, the loads/stores, OP-IMM[/-32], OP[/-32],
FENCE (nop), ECALL/EBREAK (halt)), the **M** extension (mul/div/rem with the
RISC-V-defined div-by-zero and INT_MIN/-1 edges), and the **C** extension
(decompressed in the shared fetch); real ELF images load via the shared loader.
The translator mirrors ``languages/riscv/interp.py`` rule-for-rule and reuses
its immediate decoders, so the two share one source of truth and the
commuting-square oracle cross-checks them. Instructions outside the user slice
(A/F/D, privileged/CSR) hard-abort with ``Unsupported`` (BENCHMARKS.md §3).
Deterministic in ``(image, init_regs)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...core.errors import Unsupported
from ...languages.btor2.build import Builder
from ...languages.riscv.interp import (
    _b_imm,
    _i_imm,
    _j_imm,
    _s_imm,
    _u_imm,
    fetch,
)

MASK64 = (1 << 64) - 1


@dataclass
class Effect:
    next_pc: int                       # node id of this instr's next-pc value
    writes: dict[int, int] = field(default_factory=dict)  # rd -> value node
    halts: bool = False
    mem_next: int | None = None        # node id of new mem array (stores only)


def _m_lower(b: Builder, funct3: int, a: int, c: int, w: int) -> int:
    """Lower an RV64M op to BTOR2 nodes at width ``w``; return the result node.

    Signed division carries RISC-V's defined edges (div-by-zero -> -1 / rem ->
    dividend) via ITE guards; the INT_MIN/-1 overflow wraps to INT_MIN through
    ``sdiv`` / ``srem`` directly. Unsigned div/rem map straight to udiv/urem,
    whose by-zero results (ones / dividend) already match RISC-V.
    """
    def k(v: int) -> int:
        return b.constd(w, v & ((1 << w) - 1))

    if funct3 == 0:    # MUL (low)
        return b.op2("mul", w, a, c)
    if funct3 in (1, 2, 3):  # MULH / MULHSU / MULHU (high half of 2w product)
        dw = 2 * w
        ea = b.sext(dw, a, w) if funct3 in (1, 2) else b.uext(dw, a, w)
        ec = b.sext(dw, c, w) if funct3 == 1 else b.uext(dw, c, w)
        return b.slice(b.op2("mul", dw, ea, ec), dw - 1, w)
    if funct3 == 4:    # DIV (signed)
        return b.ite(w, b.op2("eq", 1, c, k(0)), k((1 << w) - 1), b.op2("sdiv", w, a, c))
    if funct3 == 5:    # DIVU
        return b.op2("udiv", w, a, c)
    if funct3 == 6:    # REM (signed)
        return b.ite(w, b.op2("eq", 1, c, k(0)), a, b.op2("srem", w, a, c))
    if funct3 == 7:    # REMU
        return b.op2("urem", w, a, c)
    raise Unsupported("riscv-btor2", f"m.funct3={funct3}")


def _uses_memory(image) -> bool:
    addr, end = image.code_lo, image.code_hi or image.code_lo
    while addr < end:
        instr, ilen = fetch(image, addr)
        if (instr & 0x7F) in (0x03, 0x23):
            return True
        addr += ilen
    return False


def _effect(instr: int, addr: int, b: Builder, regs: dict[int, int],
            zero64: int, mem: int | None, ilen: int = 4) -> Effect:
    opcode = instr & 0x7F
    rd = (instr >> 7) & 0x1F
    funct3 = (instr >> 12) & 0x7
    rs1 = (instr >> 15) & 0x1F
    rs2 = (instr >> 20) & 0x1F
    funct7 = (instr >> 25) & 0x7F

    def rr(i: int) -> int:
        return zero64 if i == 0 else regs[i]

    def c64(v: int) -> int:
        return b.constd(64, v & MASK64)

    def write(node: int) -> dict[int, int]:
        return {rd: node} if rd != 0 else {}

    fall = c64(addr + ilen)
    a = rr(rs1)

    if opcode == 0x37:  # LUI
        return Effect(fall, write(c64(_u_imm(instr))))
    if opcode == 0x17:  # AUIPC
        return Effect(fall, write(c64(addr + _u_imm(instr))))
    if opcode == 0x6F:  # JAL
        return Effect(c64(addr + _j_imm(instr)), write(c64(addr + ilen)))
    if opcode == 0x67 and funct3 == 0:  # JALR
        target = b.op2("and", 64, b.op2("add", 64, a, c64(_i_imm(instr))), c64(~1))
        return Effect(target, write(c64(addr + ilen)))
    if opcode == 0x63:  # branches
        op = {0: "eq", 1: "neq", 4: "slt", 5: "sgte", 6: "ult", 7: "ugte"}.get(funct3)
        if op is None:
            raise Unsupported("riscv-btor2", f"branch.funct3={funct3}")
        cond = b.op2(op, 1, a, rr(rs2))
        return Effect(b.ite(64, cond, c64(addr + _b_imm(instr)), fall))
    if opcode == 0x03:  # loads
        assert mem is not None
        addr_node = b.op2("add", 64, a, c64(_i_imm(instr)))

        def load(nbytes: int) -> int:
            res = b.read(8, mem, addr_node)
            w = 8
            for k in range(1, nbytes):
                byte = b.read(8, mem, b.op2("add", 64, addr_node, c64(k)))
                res = b.op2("concat", w + 8, byte, res)
                w += 8
            return res

        if funct3 == 0:    # LB
            val = b.sext(64, load(1), 56)
        elif funct3 == 1:  # LH
            val = b.sext(64, load(2), 48)
        elif funct3 == 2:  # LW
            val = b.sext(64, load(4), 32)
        elif funct3 == 3:  # LD
            val = load(8)
        elif funct3 == 4:  # LBU
            val = b.uext(64, load(1), 56)
        elif funct3 == 5:  # LHU
            val = b.uext(64, load(2), 48)
        elif funct3 == 6:  # LWU
            val = b.uext(64, load(4), 32)
        else:
            raise Unsupported("riscv-btor2", f"load.funct3={funct3}")
        return Effect(fall, write(val))
    if opcode == 0x23:  # stores
        assert mem is not None
        nbytes = {0: 1, 1: 2, 2: 4, 3: 8}.get(funct3)
        if nbytes is None:
            raise Unsupported("riscv-btor2", f"store.funct3={funct3}")
        addr_node = b.op2("add", 64, a, c64(_s_imm(instr)))
        value = rr(rs2)
        cur = mem
        for k in range(nbytes):
            byte = b.slice(value, 8 * k + 7, 8 * k)
            a_k = addr_node if k == 0 else b.op2("add", 64, addr_node, c64(k))
            cur = b.write(64, 8, cur, a_k, byte)
        return Effect(fall, mem_next=cur)
    if opcode == 0x13:  # OP-IMM
        immc = c64(_i_imm(instr))
        if funct3 == 0:    # ADDI
            val = b.op2("add", 64, a, immc)
        elif funct3 == 2:  # SLTI
            val = b.uext(64, b.op2("slt", 1, a, immc), 63)
        elif funct3 == 3:  # SLTIU
            val = b.uext(64, b.op2("ult", 1, a, immc), 63)
        elif funct3 == 4:  # XORI
            val = b.op2("xor", 64, a, immc)
        elif funct3 == 6:  # ORI
            val = b.op2("or", 64, a, immc)
        elif funct3 == 7:  # ANDI
            val = b.op2("and", 64, a, immc)
        elif funct3 == 1:  # SLLI
            val = b.op2("sll", 64, a, c64((instr >> 20) & 0x3F))
        elif funct3 == 5:  # SRLI / SRAI
            val = b.op2("sra" if (instr >> 30) & 1 else "srl", 64, a, c64((instr >> 20) & 0x3F))
        return Effect(fall, write(val))
    if opcode == 0x1B:  # OP-IMM-32
        a32 = b.slice(a, 31, 0)
        if funct3 == 0:    # ADDIW
            r32 = b.op2("add", 32, a32, b.constd(32, _i_imm(instr) & 0xFFFFFFFF))
        elif funct3 == 1:  # SLLIW
            r32 = b.op2("sll", 32, a32, b.constd(32, (instr >> 20) & 0x1F))
        elif funct3 == 5:  # SRLIW / SRAIW
            r32 = b.op2("sra" if (instr >> 30) & 1 else "srl", 32, a32,
                        b.constd(32, (instr >> 20) & 0x1F))
        else:
            raise Unsupported("riscv-btor2", f"op-imm-32.funct3={funct3}")
        return Effect(fall, write(b.sext(64, r32, 32)))
    if opcode == 0x33:  # OP / RV64M
        if funct7 == 0x01:
            return Effect(fall, write(_m_lower(b, funct3, a, rr(rs2), 64)))
        if funct7 not in (0x00, 0x20):
            raise Unsupported("riscv-btor2", f"op.funct7=0x{funct7:02x}")
        c = rr(rs2)
        alt = funct7 == 0x20
        if funct3 == 0:    # ADD / SUB
            val = b.op2("sub" if alt else "add", 64, a, c)
        elif funct3 == 1:  # SLL
            val = b.op2("sll", 64, a, b.op2("and", 64, c, c64(0x3F)))
        elif funct3 == 2:  # SLT
            val = b.uext(64, b.op2("slt", 1, a, c), 63)
        elif funct3 == 3:  # SLTU
            val = b.uext(64, b.op2("ult", 1, a, c), 63)
        elif funct3 == 4:  # XOR
            val = b.op2("xor", 64, a, c)
        elif funct3 == 5:  # SRL / SRA
            val = b.op2("sra" if alt else "srl", 64, a, b.op2("and", 64, c, c64(0x3F)))
        elif funct3 == 6:  # OR
            val = b.op2("or", 64, a, c)
        elif funct3 == 7:  # AND
            val = b.op2("and", 64, a, c)
        return Effect(fall, write(val))
    if opcode == 0x3B:  # OP-32 / RV64M
        if funct7 == 0x01:
            if funct3 in (0, 4, 5, 6, 7):
                r32 = _m_lower(b, funct3, b.slice(a, 31, 0), b.slice(rr(rs2), 31, 0), 32)
                return Effect(fall, write(b.sext(64, r32, 32)))
            raise Unsupported("riscv-btor2", f"opw.m.funct3={funct3}")
        if funct7 not in (0x00, 0x20):
            raise Unsupported("riscv-btor2", f"op-32.funct7=0x{funct7:02x}")
        a32 = b.slice(a, 31, 0)
        c32 = b.slice(rr(rs2), 31, 0)
        alt = funct7 == 0x20
        if funct3 == 0:    # ADDW / SUBW
            r32 = b.op2("sub" if alt else "add", 32, a32, c32)
        elif funct3 == 1:  # SLLW
            r32 = b.op2("sll", 32, a32, b.op2("and", 32, c32, b.constd(32, 0x1F)))
        elif funct3 == 5:  # SRLW / SRAW
            r32 = b.op2("sra" if alt else "srl", 32, a32, b.op2("and", 32, c32, b.constd(32, 0x1F)))
        else:
            raise Unsupported("riscv-btor2", f"op-32.funct3={funct3}")
        return Effect(fall, write(b.sext(64, r32, 32)))
    if opcode == 0x0F:  # FENCE (nop)
        return Effect(fall)
    if opcode == 0x73 and funct3 == 0 and (instr >> 20) in (0, 1):  # ECALL / EBREAK
        return Effect(fall, halts=True)
    raise Unsupported("riscv-btor2", f"opcode=0x{opcode:02x}")


def translate(program: dict[str, Any]) -> bytes:
    image = program["image"]
    init_regs = program.get("init_regs", {})

    b = Builder()
    pc = b.state(64, "pc")
    regs = {r: b.state(64, f"x{r}") for r in range(1, 32)}
    halted = b.state(1, "halted")
    zero64 = b.zero(64)
    mem = b.state_array(64, 8, "mem") if _uses_memory(image) else None

    b.init(pc, b.constd(64, image.entry))
    for r in range(1, 32):
        b.init(regs[r], b.constd(64, int(init_regs.get(r, 0)) & MASK64))
    b.init(halted, b.zero(1))

    not_halted = b.op1("not", 1, halted)
    next_pc = pc
    next_regs = dict(regs)
    next_halted = halted
    next_mem = mem

    addr, end = image.code_lo, image.code_hi or image.code_lo
    while addr < end:
        instr, ilen = fetch(image, addr)
        eff = _effect(instr, addr, b, regs, zero64, mem, ilen)
        at = b.op2("eq", 1, pc, b.constd(64, addr))
        active = b.op2("and", 1, at, not_halted)
        next_pc = b.ite(64, active, eff.next_pc, next_pc)
        for r, val in eff.writes.items():
            next_regs[r] = b.ite(64, active, val, next_regs[r])
        if eff.halts:
            next_halted = b.ite(1, active, b.one(1), next_halted)
        if eff.mem_next is not None:
            next_mem = b.ite_array(64, 8, active, eff.mem_next, next_mem)
        addr += ilen

    b.next(pc, next_pc)
    for r in range(1, 32):
        b.next(regs[r], next_regs[r])
    b.next(halted, next_halted)
    if mem is not None:
        b.next_array(mem, next_mem)

    # Optional reachability property -> a `bad` signal. Lets a downstream
    # reasoning bridge (btor2-smtlib) decide the question.
    prop = program.get("property")
    if prop and "reg_eq" in prop:
        reg, val = prop["reg_eq"]
        src = zero64 if reg == 0 else regs[reg]
        b.bad(b.op2("eq", 1, src, b.constd(64, int(val) & MASK64)))

    return b.to_text().encode("utf-8")
