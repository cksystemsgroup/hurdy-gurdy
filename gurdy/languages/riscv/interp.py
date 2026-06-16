"""A deterministic RV64I interpreter (the shared RISC-V source interpreter).

Scope (MVP, thin-first — languages/riscv "Interpreter build brief"): the
RV64I base integer set — LUI/AUIPC, JAL/JALR, the branches, the loads/stores,
OP-IMM / OP-IMM-32, OP / OP-32, FENCE (nop), and ECALL/EBREAK (halt). The
M and C extensions and ELF loading are later increments; any other
instruction hard-aborts with ``Unsupported`` (BENCHMARKS.md §3).

Behavior: a ``Trace`` of post-step states ``{"pc", "x1".."x31", "halted"}``
(ARCHITECTURE.md §5). Pure and deterministic. The dev-image acceptance is a
step-for-step differential against ``sail_riscv_sim`` (DOCKER.md); the unit
tests here are self-contained.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...core.errors import Unsupported
from ...core.types import Trace

MASK64 = (1 << 64) - 1
MASK32 = (1 << 32) - 1


def _u64(v: int) -> int:
    return v & MASK64


def _sext(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    if v >> (bits - 1):
        v -= 1 << bits
    return v


def _s64(v: int) -> int:
    return _sext(v, 64)


def _s32(v: int) -> int:
    return _sext(v, 32)


@dataclass
class RiscvImage:
    """A flat memory image: byte address -> byte (0..255), plus an entry pc.

    Code and data share memory (von Neumann), as in a real ELF. ``code_hi``
    bounds the instruction region; stepping to a pc outside ``[code_lo,
    code_hi)`` halts (program ran off the end).
    """

    mem: dict[int, int] = field(default_factory=dict)
    entry: int = 0
    code_lo: int = 0
    code_hi: int | None = None

    def load(self, addr: int, nbytes: int) -> int:
        value = 0
        for i in range(nbytes):
            value |= self.mem.get(_u64(addr + i), 0) << (8 * i)
        return value

    def store(self, addr: int, nbytes: int, value: int) -> None:
        for i in range(nbytes):
            self.mem[_u64(addr + i)] = (value >> (8 * i)) & 0xFF


def image_from_words(words: list[int], base: int = 0, entry: int | None = None) -> RiscvImage:
    """Build an image from a list of 32-bit little-endian instruction words."""
    mem: dict[int, int] = {}
    for i, word in enumerate(words):
        addr = base + 4 * i
        for b in range(4):
            mem[addr + b] = (word >> (8 * b)) & 0xFF
    return RiscvImage(
        mem=mem,
        entry=base if entry is None else entry,
        code_lo=base,
        code_hi=base + 4 * len(words),
    )


def _state(pc: int, regs: list[int], halted: bool) -> dict[str, Any]:
    s: dict[str, Any] = {"pc": pc, "halted": halted}
    for r in range(1, 32):
        s[f"x{r}"] = regs[r]
    return s


def _i_imm(instr: int) -> int:
    return _sext(instr >> 20, 12)


def _s_imm(instr: int) -> int:
    return _sext(((instr >> 25) << 5) | ((instr >> 7) & 0x1F), 12)


def _b_imm(instr: int) -> int:
    imm = (
        (((instr >> 31) & 1) << 12)
        | (((instr >> 7) & 1) << 11)
        | (((instr >> 25) & 0x3F) << 5)
        | (((instr >> 8) & 0xF) << 1)
    )
    return _sext(imm, 13)


def _u_imm(instr: int) -> int:
    return _s32(instr & 0xFFFFF000)


def _j_imm(instr: int) -> int:
    imm = (
        (((instr >> 31) & 1) << 20)
        | (((instr >> 12) & 0xFF) << 12)
        | (((instr >> 20) & 1) << 11)
        | (((instr >> 21) & 0x3FF) << 1)
    )
    return _sext(imm, 21)


def _execute(instr: int, pc: int, regs: list[int], image: RiscvImage) -> tuple[int, bool]:
    """Execute one instruction; mutate regs; return (next_pc, halt)."""
    opcode = instr & 0x7F
    rd = (instr >> 7) & 0x1F
    funct3 = (instr >> 12) & 0x7
    rs1 = (instr >> 15) & 0x1F
    rs2 = (instr >> 20) & 0x1F
    funct7 = (instr >> 25) & 0x7F
    next_pc = _u64(pc + 4)

    def w(value: int) -> None:
        if rd != 0:
            regs[rd] = _u64(value)

    a = regs[rs1]
    b = regs[rs2]

    if opcode == 0x37:  # LUI
        w(_u_imm(instr))
    elif opcode == 0x17:  # AUIPC
        w(pc + _u_imm(instr))
    elif opcode == 0x6F:  # JAL
        w(pc + 4)
        next_pc = _u64(pc + _j_imm(instr))
    elif opcode == 0x67 and funct3 == 0:  # JALR
        target = _u64((a + _i_imm(instr)) & ~1)
        w(pc + 4)
        next_pc = target
    elif opcode == 0x63:  # branches
        sa, sb = _s64(a), _s64(b)
        taken = {
            0: a == b,          # BEQ
            1: a != b,          # BNE
            4: sa < sb,         # BLT
            5: sa >= sb,        # BGE
            6: a < b,           # BLTU
            7: a >= b,          # BGEU
        }.get(funct3)
        if taken is None:
            raise Unsupported("riscv", f"branch.funct3={funct3}")
        if taken:
            next_pc = _u64(pc + _b_imm(instr))
    elif opcode == 0x03:  # loads
        addr = _u64(a + _i_imm(instr))
        if funct3 == 0:      # LB
            w(_sext(image.load(addr, 1), 8))
        elif funct3 == 1:    # LH
            w(_sext(image.load(addr, 2), 16))
        elif funct3 == 2:    # LW
            w(_sext(image.load(addr, 4), 32))
        elif funct3 == 3:    # LD
            w(image.load(addr, 8))
        elif funct3 == 4:    # LBU
            w(image.load(addr, 1))
        elif funct3 == 5:    # LHU
            w(image.load(addr, 2))
        elif funct3 == 6:    # LWU
            w(image.load(addr, 4))
        else:
            raise Unsupported("riscv", f"load.funct3={funct3}")
    elif opcode == 0x23:  # stores
        addr = _u64(a + _s_imm(instr))
        nbytes = {0: 1, 1: 2, 2: 4, 3: 8}.get(funct3)
        if nbytes is None:
            raise Unsupported("riscv", f"store.funct3={funct3}")
        image.store(addr, nbytes, b)
    elif opcode == 0x13:  # OP-IMM
        imm = _i_imm(instr)
        if funct3 == 0:      # ADDI
            w(a + imm)
        elif funct3 == 2:    # SLTI
            w(1 if _s64(a) < imm else 0)
        elif funct3 == 3:    # SLTIU
            w(1 if a < _u64(imm) else 0)
        elif funct3 == 4:    # XORI
            w(a ^ _u64(imm))
        elif funct3 == 6:    # ORI
            w(a | _u64(imm))
        elif funct3 == 7:    # ANDI
            w(a & _u64(imm))
        elif funct3 == 1:    # SLLI
            w(a << ((instr >> 20) & 0x3F))
        elif funct3 == 5:    # SRLI / SRAI
            shamt = (instr >> 20) & 0x3F
            if (instr >> 30) & 1:  # SRAI
                w(_s64(a) >> shamt)
            else:                  # SRLI
                w(a >> shamt)
    elif opcode == 0x1B:  # OP-IMM-32
        imm = _i_imm(instr)
        if funct3 == 0:      # ADDIW
            w(_s32((a + imm) & MASK32))
        elif funct3 == 1:    # SLLIW
            shamt = (instr >> 20) & 0x1F
            w(_s32((a << shamt) & MASK32))
        elif funct3 == 5:    # SRLIW / SRAIW
            shamt = (instr >> 20) & 0x1F
            if (instr >> 30) & 1:  # SRAIW
                w(_s32(_s32(a & MASK32) >> shamt))
            else:                  # SRLIW
                w(_s32((a & MASK32) >> shamt))
        else:
            raise Unsupported("riscv", f"op-imm-32.funct3={funct3}")
    elif opcode == 0x33:  # OP
        alt = funct7 == 0x20
        if funct3 == 0:      # ADD / SUB
            w(a - b if alt else a + b)
        elif funct3 == 1:    # SLL
            w(a << (b & 0x3F))
        elif funct3 == 2:    # SLT
            w(1 if _s64(a) < _s64(b) else 0)
        elif funct3 == 3:    # SLTU
            w(1 if a < b else 0)
        elif funct3 == 4:    # XOR
            w(a ^ b)
        elif funct3 == 5:    # SRL / SRA
            w(_s64(a) >> (b & 0x3F) if alt else a >> (b & 0x3F))
        elif funct3 == 6:    # OR
            w(a | b)
        elif funct3 == 7:    # AND
            w(a & b)
    elif opcode == 0x3B:  # OP-32
        alt = funct7 == 0x20
        a32, b32 = a & MASK32, b & MASK32
        if funct3 == 0:      # ADDW / SUBW
            w(_s32((a32 - b32) & MASK32) if alt else _s32((a32 + b32) & MASK32))
        elif funct3 == 1:    # SLLW
            w(_s32((a32 << (b & 0x1F)) & MASK32))
        elif funct3 == 5:    # SRLW / SRAW
            if alt:          # SRAW
                w(_s32(_s32(a32) >> (b & 0x1F)))
            else:            # SRLW
                w(_s32(a32 >> (b & 0x1F)))
        else:
            raise Unsupported("riscv", f"op-32.funct3={funct3}")
    elif opcode == 0x0F:  # FENCE (treated as nop in this scope)
        pass
    elif opcode == 0x73:  # SYSTEM
        imm = instr >> 20
        if funct3 == 0 and imm in (0, 1):  # ECALL / EBREAK
            return next_pc, True
        raise Unsupported("riscv", f"system.funct3={funct3}.imm={imm}")
    else:
        raise Unsupported("riscv", f"opcode=0x{opcode:02x}")

    return next_pc, False


def run(
    image: RiscvImage,
    binding: dict[str, Any] | None = None,
    max_steps: int = 100_000,
    **_kw: Any,
) -> Trace:
    """Run ``image`` to a halt (ECALL/EBREAK, off-the-end, or ``max_steps``).

    ``binding`` may set ``pc`` and initial ``regs`` (a ``{index: value}`` map).
    Returns the post-step trace.
    """
    regs = [0] * 32
    pc = image.entry
    if binding:
        pc = binding.get("pc", pc)
        for r, v in binding.get("regs", {}).items():
            regs[int(r)] = _u64(int(v))
    regs[0] = 0

    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        if image.code_hi is not None and not (image.code_lo <= pc < image.code_hi):
            trace.append(_state(pc, regs, True))
            break
        instr = image.load(pc, 4)
        pc, halt = _execute(instr, pc, regs, image)
        regs[0] = 0
        steps += 1
        trace.append(_state(pc, regs, halt))
        if halt:
            break
    return trace
