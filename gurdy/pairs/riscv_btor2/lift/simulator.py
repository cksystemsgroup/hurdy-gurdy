"""Concrete RV64 simulator — the soundness ground truth.

This module mirrors the per-instruction lowering in
``translation/library.py`` exactly. Witness replay (phase 13) runs
both the simulator and the library inside BMC and asserts they
agree on every cycle; any divergence is a schema/library bug.

Architectural state:

- 32 64-bit registers (``x0`` always reads zero).
- Byte-addressable 64-bit memory (sparse dict).
- 64-bit PC.
- ``halted`` flag set on ECALL / EBREAK.

The simulator is deliberately written in straightforward Python; we
favour clarity over speed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from gurdy.pairs.riscv_btor2.source.decoder import Decoded, decode, decode_compressed


XLEN = 64
MASK64 = (1 << 64) - 1
MASK32 = (1 << 32) - 1
SIGN64 = 1 << 63
SIGN32 = 1 << 31


def _u64(x: int) -> int:
    return x & MASK64


def _s64(x: int) -> int:
    x &= MASK64
    return x - (1 << 64) if x & SIGN64 else x


def _u32(x: int) -> int:
    return x & MASK32


def _s32(x: int) -> int:
    x &= MASK32
    return x - (1 << 32) if x & SIGN32 else x


def _sext(value: int, width: int) -> int:
    sign = 1 << (width - 1)
    return (value ^ sign) - sign


@dataclass
class State:
    regs: list[int] = field(default_factory=lambda: [0] * 32)
    mem: dict[int, int] = field(default_factory=dict)
    pc: int = 0
    halted: bool = False

    def read_reg(self, n: int) -> int:
        return 0 if n == 0 else _u64(self.regs[n])

    def write_reg(self, n: int, v: int) -> None:
        if n == 0:
            return
        self.regs[n] = _u64(v)

    def load_byte(self, addr: int) -> int:
        return self.mem.get(_u64(addr), 0) & 0xFF

    def store_byte(self, addr: int, value: int) -> None:
        self.mem[_u64(addr)] = value & 0xFF

    def load_bytes_le(self, addr: int, n: int) -> int:
        v = 0
        for i in range(n):
            v |= self.load_byte(addr + i) << (8 * i)
        return v

    def store_bytes_le(self, addr: int, value: int, n: int) -> None:
        for i in range(n):
            self.store_byte(addr + i, (value >> (8 * i)) & 0xFF)

    def clone(self) -> "State":
        return State(
            regs=list(self.regs),
            mem=dict(self.mem),
            pc=self.pc,
            halted=self.halted,
        )


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------


def step(state: State, d: Decoded) -> State:
    """Apply one decoded instruction. Mutates a clone, returns it."""

    s = state.clone()
    if s.halted:
        return s
    m = d.mnemonic
    pc = s.pc
    next_pc = _u64(pc + d.length)
    rs1_v = s.read_reg(d.rs1)
    rs2_v = s.read_reg(d.rs2)
    imm = d.imm  # already sign-extended in decoder

    if m == "LUI":
        s.write_reg(d.rd, _u64(imm))
    elif m == "AUIPC":
        s.write_reg(d.rd, _u64(pc + imm))
    elif m == "JAL":
        s.write_reg(d.rd, next_pc)
        next_pc = _u64(pc + imm)
    elif m == "JALR":
        target = _u64((rs1_v + imm) & ~1)
        s.write_reg(d.rd, _u64(pc + d.length))
        next_pc = target
    elif m in {"BEQ", "BNE", "BLT", "BGE", "BLTU", "BGEU"}:
        if m == "BEQ":
            taken = rs1_v == rs2_v
        elif m == "BNE":
            taken = rs1_v != rs2_v
        elif m == "BLT":
            taken = _s64(rs1_v) < _s64(rs2_v)
        elif m == "BGE":
            taken = _s64(rs1_v) >= _s64(rs2_v)
        elif m == "BLTU":
            taken = rs1_v < rs2_v
        elif m == "BGEU":
            taken = rs1_v >= rs2_v
        if taken:
            next_pc = _u64(pc + imm)
    elif m in {"LB", "LH", "LW", "LD", "LBU", "LHU", "LWU"}:
        addr = _u64(rs1_v + imm)
        if m in {"LB", "LBU"}:
            v = s.load_bytes_le(addr, 1)
            v = _sext(v, 8) if m == "LB" else v
        elif m in {"LH", "LHU"}:
            v = s.load_bytes_le(addr, 2)
            v = _sext(v, 16) if m == "LH" else v
        elif m in {"LW", "LWU"}:
            v = s.load_bytes_le(addr, 4)
            v = _sext(v, 32) if m == "LW" else v
        else:  # LD
            v = s.load_bytes_le(addr, 8)
        s.write_reg(d.rd, _u64(v))
    elif m in {"SB", "SH", "SW", "SD"}:
        addr = _u64(rs1_v + imm)
        n = {"SB": 1, "SH": 2, "SW": 4, "SD": 8}[m]
        s.store_bytes_le(addr, rs2_v, n)
    elif m == "ADDI":
        s.write_reg(d.rd, _u64(rs1_v + imm))
    elif m == "SLTI":
        s.write_reg(d.rd, 1 if _s64(rs1_v) < imm else 0)
    elif m == "SLTIU":
        s.write_reg(d.rd, 1 if rs1_v < _u64(imm) else 0)
    elif m == "XORI":
        s.write_reg(d.rd, rs1_v ^ _u64(imm))
    elif m == "ORI":
        s.write_reg(d.rd, rs1_v | _u64(imm))
    elif m == "ANDI":
        s.write_reg(d.rd, rs1_v & _u64(imm))
    elif m == "SLLI":
        s.write_reg(d.rd, _u64(rs1_v << (imm & 0x3F)))
    elif m == "SRLI":
        s.write_reg(d.rd, rs1_v >> (imm & 0x3F))
    elif m == "SRAI":
        s.write_reg(d.rd, _u64(_s64(rs1_v) >> (imm & 0x3F)))
    elif m == "ADDIW":
        s.write_reg(d.rd, _u64(_sext(_u32(rs1_v + imm), 32)))
    elif m == "SLLIW":
        s.write_reg(d.rd, _u64(_sext(_u32(rs1_v << (imm & 0x1F)), 32)))
    elif m == "SRLIW":
        s.write_reg(d.rd, _u64(_sext(_u32(_u32(rs1_v) >> (imm & 0x1F)), 32)))
    elif m == "SRAIW":
        s.write_reg(d.rd, _u64(_sext(_u32(_s32(rs1_v) >> (imm & 0x1F)), 32)))
    elif m == "ADD":
        s.write_reg(d.rd, _u64(rs1_v + rs2_v))
    elif m == "SUB":
        s.write_reg(d.rd, _u64(rs1_v - rs2_v))
    elif m == "SLL":
        s.write_reg(d.rd, _u64(rs1_v << (rs2_v & 0x3F)))
    elif m == "SLT":
        s.write_reg(d.rd, 1 if _s64(rs1_v) < _s64(rs2_v) else 0)
    elif m == "SLTU":
        s.write_reg(d.rd, 1 if rs1_v < rs2_v else 0)
    elif m == "XOR":
        s.write_reg(d.rd, rs1_v ^ rs2_v)
    elif m == "SRL":
        s.write_reg(d.rd, rs1_v >> (rs2_v & 0x3F))
    elif m == "SRA":
        s.write_reg(d.rd, _u64(_s64(rs1_v) >> (rs2_v & 0x3F)))
    elif m == "OR":
        s.write_reg(d.rd, rs1_v | rs2_v)
    elif m == "AND":
        s.write_reg(d.rd, rs1_v & rs2_v)
    elif m == "ADDW":
        s.write_reg(d.rd, _u64(_sext(_u32(rs1_v + rs2_v), 32)))
    elif m == "SUBW":
        s.write_reg(d.rd, _u64(_sext(_u32(rs1_v - rs2_v), 32)))
    elif m == "SLLW":
        s.write_reg(d.rd, _u64(_sext(_u32(rs1_v << (rs2_v & 0x1F)), 32)))
    elif m == "SRLW":
        s.write_reg(d.rd, _u64(_sext(_u32(_u32(rs1_v) >> (rs2_v & 0x1F)), 32)))
    elif m == "SRAW":
        s.write_reg(d.rd, _u64(_sext(_u32(_s32(rs1_v) >> (rs2_v & 0x1F)), 32)))
    # ----- M extension -----
    elif m == "MUL":
        s.write_reg(d.rd, _u64(rs1_v * rs2_v))
    elif m == "MULH":
        s.write_reg(d.rd, _u64((_s64(rs1_v) * _s64(rs2_v)) >> 64))
    elif m == "MULHSU":
        s.write_reg(d.rd, _u64((_s64(rs1_v) * rs2_v) >> 64))
    elif m == "MULHU":
        s.write_reg(d.rd, _u64((rs1_v * rs2_v) >> 64))
    elif m == "DIV":
        if rs2_v == 0:
            q = (1 << 64) - 1  # all-ones
        elif rs1_v == SIGN64 and _s64(rs2_v) == -1:
            q = SIGN64  # signed overflow
        else:
            a, b = _s64(rs1_v), _s64(rs2_v)
            # truncate toward zero
            q = -(-a // b) if (a < 0) ^ (b < 0) and a % b != 0 else a // b
            q = _u64(q)
        s.write_reg(d.rd, q)
    elif m == "DIVU":
        s.write_reg(d.rd, ((1 << 64) - 1) if rs2_v == 0 else (rs1_v // rs2_v))
    elif m == "REM":
        if rs2_v == 0:
            r = rs1_v
        elif rs1_v == SIGN64 and _s64(rs2_v) == -1:
            r = 0
        else:
            a, b = _s64(rs1_v), _s64(rs2_v)
            # Truncate toward zero so signs follow dividend.
            q = -(-a // b) if (a < 0) ^ (b < 0) and a % b != 0 else a // b
            r = a - q * b
            r = _u64(r)
        s.write_reg(d.rd, r)
    elif m == "REMU":
        s.write_reg(d.rd, rs1_v if rs2_v == 0 else rs1_v % rs2_v)
    elif m == "MULW":
        s.write_reg(d.rd, _u64(_sext(_u32(rs1_v * rs2_v), 32)))
    elif m in {"DIVW", "DIVUW", "REMW", "REMUW"}:
        a32 = _u32(rs1_v)
        b32 = _u32(rs2_v)
        if m == "DIVW":
            sa, sb = _s32(a32), _s32(b32)
            if b32 == 0:
                q = (1 << 32) - 1
            elif a32 == SIGN32 and sb == -1:
                q = SIGN32
            else:
                q = -(-sa // sb) if (sa < 0) ^ (sb < 0) and sa % sb != 0 else sa // sb
                q = _u32(q)
            s.write_reg(d.rd, _u64(_sext(q, 32)))
        elif m == "DIVUW":
            q = (1 << 32) - 1 if b32 == 0 else (a32 // b32)
            s.write_reg(d.rd, _u64(_sext(q, 32)))
        elif m == "REMW":
            sa, sb = _s32(a32), _s32(b32)
            if b32 == 0:
                r = sa
            elif a32 == SIGN32 and sb == -1:
                r = 0
            else:
                q = -(-sa // sb) if (sa < 0) ^ (sb < 0) and sa % sb != 0 else sa // sb
                r = sa - q * sb
            s.write_reg(d.rd, _u64(_sext(_u32(r), 32)))
        elif m == "REMUW":
            r = a32 if b32 == 0 else a32 % b32
            s.write_reg(d.rd, _u64(_sext(r, 32)))
    elif m in {"FENCE", "FENCE.I"}:
        pass  # no-op at this schema level
    elif m in {"ECALL", "EBREAK"}:
        s.halted = True
        next_pc = pc  # halted state freezes pc per SCHEMA.md
    elif m.startswith("CSRR"):
        # CSR reads return a fresh nondet at the schema; for the
        # simulator we model them as zero (deterministic stand-in;
        # specs that pin a CSR will configure this). CSR writes drop.
        if d.rd != 0:
            s.write_reg(d.rd, 0)
    else:
        raise NotImplementedError(f"simulator: unsupported {m!r}")

    s.pc = next_pc
    return s


def simulate(
    state: State,
    fetch: callable,
    max_steps: int = 1000,
) -> tuple[State, list[Decoded]]:
    """Run until halted, max_steps reached, or fetch returns None.

    ``fetch(pc) -> Decoded | None``: how to obtain the next decoded
    instruction. Returning ``None`` terminates the simulator.
    """
    trace: list[Decoded] = []
    s = state.clone()
    for _ in range(max_steps):
        if s.halted:
            break
        d = fetch(s.pc)
        if d is None:
            break
        trace.append(d)
        s = step(s, d)
    return s, trace


def simulate_with_regs(
    state: State,
    fetch: callable,
    max_steps: int = 1000,
) -> tuple[State, list[Decoded], list[tuple[int, ...]]]:
    """Like ``simulate`` but also returns a per-step register snapshot.

    Returned ``per_step_regs[i]`` is the tuple of register values
    *before* the i-th decoded instruction executes — i.e., the state
    visible *at* PC = ``decoded_trace[i].pc``. This is the right
    semantics for audit_anchors' property-at-PC check (the values you
    read at that PC, before the instruction at that PC writes).

    Same termination conditions as ``simulate``.
    """
    trace: list[Decoded] = []
    per_step_regs: list[tuple[int, ...]] = []
    s = state.clone()
    for _ in range(max_steps):
        if s.halted:
            break
        d = fetch(s.pc)
        if d is None:
            break
        trace.append(d)
        per_step_regs.append(tuple(s.regs))
        s = step(s, d)
    return s, trace, per_step_regs


def fetch_from_memory_map(byte_map: dict[int, int]):
    """Build a fetch function that reads bytes from a dict and decodes."""

    def _fetch(pc: int) -> Decoded | None:
        b0 = byte_map.get(pc)
        b1 = byte_map.get(pc + 1)
        if b0 is None or b1 is None:
            return None
        half = b0 | (b1 << 8)
        if (half & 3) != 3:
            return decode_compressed(half, pc)
        b2 = byte_map.get(pc + 2, 0)
        b3 = byte_map.get(pc + 3, 0)
        word = half | (b2 << 16) | (b3 << 24)
        d = decode(word, pc, length=4)
        return d

    return _fetch


__all__ = ["State", "step", "simulate", "fetch_from_memory_map"]
