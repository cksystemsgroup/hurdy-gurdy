"""eBPF P1 source interpreter.

Concrete executor for the P1 opcode subset (ALU64 K/X, JMP K/X, EXIT).
Returns a SourceTrace for alignment and debugging.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import ClassVar

from gurdy.core.interp.types import InputBinding, SourceStep, SourceTrace


INTERPRETER_VERSION = "1.0.0"
PAIR_ID = "ebpf-btor2"

_MASK64 = (1 << 64) - 1
_MASK32 = (1 << 32) - 1

# Read-only frame pointer constant for P1 (no stack state yet)
R10_BASE = 512

_INSN_FMT = "<BBhi"   # opcode, dst|src, off (signed 16), imm (signed 32)
_INSN_SIZE = 8

_WIDE_IMM_OPCODE = 0x18  # BPF_LD | BPF_IMM | BPF_DW — not in P1
_BPF_CLASS_ALU64 = 0x07
_BPF_CLASS_JMP = 0x05
_BPF_EXIT_OPCODE = 0x95


# ---------------------------------------------------------------------------
# Decoded instruction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BpfInsn:
    """One decoded BPF instruction (8-byte record)."""

    opcode: int
    dst_reg: int
    src_reg: int
    off: int    # signed 16-bit
    imm: int    # signed 32-bit

    @property
    def cls(self) -> int:
        return self.opcode & 0x07

    @property
    def src_flag(self) -> int:
        return (self.opcode >> 3) & 0x01

    @property
    def op_nibble(self) -> int:
        return (self.opcode >> 4) & 0x0F


# ---------------------------------------------------------------------------
# Program loading
# ---------------------------------------------------------------------------


def decode_program(bytecode: bytes) -> list[BpfInsn]:
    """Decode raw bytecode into a list of BpfInsn.

    Raises ValueError with diagnostic code on malformed or unsupported input.
    """
    if len(bytecode) % _INSN_SIZE != 0:
        raise ValueError(
            f"ebpf-btor2/load/0000: bytecode length {len(bytecode)} is not a multiple of 8"
        )
    insns: list[BpfInsn] = []
    for i in range(0, len(bytecode), _INSN_SIZE):
        raw = bytecode[i : i + _INSN_SIZE]
        opcode, dst_src, off, imm = struct.unpack(_INSN_FMT, raw)
        dst_reg = dst_src & 0x0F
        src_reg = (dst_src >> 4) & 0x0F
        if opcode == _WIDE_IMM_OPCODE:
            raise ValueError(
                f"ebpf-btor2/load/0001: wide immediate (0x18) at insn "
                f"{i // _INSN_SIZE} is not supported in P1"
            )
        insns.append(BpfInsn(opcode=opcode, dst_reg=dst_reg, src_reg=src_reg, off=off, imm=imm))
    return insns


# ---------------------------------------------------------------------------
# Machine state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EbpfMachineState:
    """Concrete machine state for P1 eBPF.

    ``regs``: 10 unsigned 64-bit registers r0-r9.
    ``insn_idx``: current instruction index (bv32, 0-based).
    ``halted``: True once BPF_EXIT_INSN executes.
    """

    regs: tuple[int, ...]   # length 10, each in [0, 2**64)
    insn_idx: int           # in [0, 2**32)
    halted: bool

    def to_dict(self) -> dict[str, object]:
        return {
            **{f"r{i}": self.regs[i] for i in range(10)},
            "insn_idx": self.insn_idx,
            "halted": self.halted,
        }


def _initial_state(initial_regs: tuple[int, ...]) -> EbpfMachineState:
    return EbpfMachineState(regs=initial_regs, insn_idx=0, halted=False)


# ---------------------------------------------------------------------------
# Input binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EbpfInputBinding(InputBinding):
    """Concrete inputs for one eBPF source-interpreter run.

    ``bytecode``: raw program bytes (flat sequence of 8-byte bpf_insn records).
    ``initial_regs``: initial unsigned 64-bit values for r0-r9 at entry.
    """

    pair: ClassVar[str] = PAIR_ID

    bytecode: bytes
    initial_regs: tuple[int, ...] = (0,) * 10


# ---------------------------------------------------------------------------
# ALU64 and JMP helpers
# ---------------------------------------------------------------------------


def _to_signed64(x: int) -> int:
    x &= _MASK64
    return x - (1 << 64) if x >= (1 << 63) else x


def _alu64_result(op: int, dst: int, src: int) -> int:
    """Compute the ALU64 result for an op nibble. Returns unsigned 64-bit int."""
    if op == 0x0:   # ADD64
        return (dst + src) & _MASK64
    if op == 0x1:   # SUB64
        return (dst - src) & _MASK64
    if op == 0x2:   # MUL64
        return (dst * src) & _MASK64
    if op == 0x3:   # DIV64 — zero divisor returns 0
        return 0 if src == 0 else dst // src
    if op == 0x4:   # OR64
        return dst | src
    if op == 0x5:   # AND64
        return dst & src
    if op == 0x6:   # LSH64
        return (dst << (src & 63)) & _MASK64
    if op == 0x7:   # RSH64
        return dst >> (src & 63)
    if op == 0x8:   # NEG64 (src ignored)
        return (-dst) & _MASK64
    if op == 0x9:   # MOD64 — zero divisor returns DST
        return dst if src == 0 else dst % src
    if op == 0xA:   # XOR64
        return dst ^ src
    if op == 0xC:   # ARSH64 — arithmetic (signed) right shift
        return _to_signed64(dst) >> (src & 63) & _MASK64
    raise ValueError(
        f"ebpf-btor2/load/0003: unknown ALU64 op nibble 0x{op:x}"
    )


def _jmp_cond(op: int, dst: int, src: int) -> bool:
    """Evaluate the branch condition for a JMP op nibble."""
    if op == 0x1:  # JEQ
        return dst == src
    if op == 0x2:  # JGT (unsigned)
        return dst > src
    if op == 0x3:  # JGE (unsigned)
        return dst >= src
    if op == 0x4:  # JSET
        return (dst & src) != 0
    if op == 0x5:  # JNE
        return dst != src
    if op == 0x6:  # JSGT (signed)
        return _to_signed64(dst) > _to_signed64(src)
    if op == 0x7:  # JSGE (signed)
        return _to_signed64(dst) >= _to_signed64(src)
    if op == 0xA:  # JLT (unsigned)
        return dst < src
    if op == 0xB:  # JLE (unsigned)
        return dst <= src
    if op == 0xC:  # JSLT (signed)
        return _to_signed64(dst) < _to_signed64(src)
    if op == 0xD:  # JSLE (signed)
        return _to_signed64(dst) <= _to_signed64(src)
    raise ValueError(
        f"ebpf-btor2/load/0003: unknown JMP op nibble 0x{op:x}"
    )


# ---------------------------------------------------------------------------
# Step function
# ---------------------------------------------------------------------------


def step(insns: list[BpfInsn], state: EbpfMachineState) -> EbpfMachineState:
    """Execute one machine cycle and return the new state.

    Frozen-state rule: if halted or insn_idx is out of bounds,
    return state unchanged (self-loop per schema §6 dispatch rule).
    """
    if state.halted or state.insn_idx >= len(insns):
        return state

    insn = insns[state.insn_idx]
    idx = state.insn_idx
    regs = list(state.regs)

    # Resolve operands
    dst = regs[insn.dst_reg]
    src_x = regs[insn.src_reg] if insn.src_reg < 10 else R10_BASE
    # sign-extend imm32 to 64-bit (Python int is already signed; mask to bv64)
    imm64 = insn.imm & _MASK64
    src = imm64 if insn.src_flag == 0 else src_x

    # EXIT
    if insn.opcode == _BPF_EXIT_OPCODE:
        return EbpfMachineState(regs=tuple(regs), insn_idx=idx, halted=True)

    # ALU64
    if insn.cls == _BPF_CLASS_ALU64:
        regs[insn.dst_reg] = _alu64_result(insn.op_nibble, dst, src)
        return EbpfMachineState(
            regs=tuple(regs),
            insn_idx=(idx + 1) & _MASK32,
            halted=False,
        )

    # JMP
    if insn.cls == _BPF_CLASS_JMP:
        if insn.op_nibble == 0x0:  # JA — unconditional
            new_idx = (idx + 1 + insn.off) & _MASK32
        else:
            cond = _jmp_cond(insn.op_nibble, dst, src)
            new_idx = (idx + 1 + insn.off) & _MASK32 if cond else (idx + 1) & _MASK32
        return EbpfMachineState(regs=tuple(regs), insn_idx=new_idx, halted=False)

    raise ValueError(
        f"ebpf-btor2/load/0003: unsupported opcode 0x{insn.opcode:02x} at insn_idx {idx}"
    )


# ---------------------------------------------------------------------------
# Run function
# ---------------------------------------------------------------------------


def run(binding: EbpfInputBinding, max_steps: int = 4096) -> SourceTrace:
    """Run the eBPF program and return a SourceTrace.

    Records one SourceStep per machine cycle. Stops when:
    - ``halted`` is True (EXIT executed), or
    - ``insn_idx`` is out of bounds (state frozen per schema §6), or
    - ``max_steps`` cycles have executed.

    Step 0 records the initial state with no deltas.
    """
    insns = decode_program(binding.bytecode)
    state = _initial_state(binding.initial_regs)
    src_steps: list[SourceStep] = []

    src_steps.append(SourceStep(
        step=0,
        location={"insn_idx": state.insn_idx},
        deltas=None,
        halted=False,
    ))

    for cycle in range(1, max_steps + 2):
        if state.halted or state.insn_idx >= len(insns):
            break

        prev = state
        insn = insns[state.insn_idx]
        state = step(insns, state)

        deltas: dict[str, object] = {}
        for i in range(10):
            if state.regs[i] != prev.regs[i]:
                deltas[f"r{i}"] = state.regs[i]
        if state.insn_idx != prev.insn_idx:
            deltas["insn_idx"] = state.insn_idx
        if state.halted != prev.halted:
            deltas["halted"] = state.halted

        src_steps.append(SourceStep(
            step=cycle,
            location={"insn_idx": prev.insn_idx, "opcode": f"0x{insn.opcode:02x}"},
            deltas=deltas or None,
            halted=state.halted,
        ))

        if state.halted:
            break

    if state.halted:
        halt_reason = "exit"
    elif state.insn_idx >= len(insns):
        halt_reason = "out_of_bounds"
    else:
        halt_reason = "max_steps"

    return SourceTrace(
        pair=PAIR_ID,
        interpreter_version=INTERPRETER_VERSION,
        inputs_hash=binding.inputs_hash(),
        steps=tuple(src_steps),
        final_state=state.to_dict(),
        halted=state.halted,
        halt_reason=halt_reason,
    )


__all__ = [
    "BpfInsn",
    "EbpfInputBinding",
    "EbpfMachineState",
    "INTERPRETER_VERSION",
    "PAIR_ID",
    "R10_BASE",
    "decode_program",
    "run",
    "step",
]
