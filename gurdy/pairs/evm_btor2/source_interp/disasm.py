"""EVM bytecode disassembler for the P1 opcode set."""

from __future__ import annotations

from dataclasses import dataclass

_PUSH1 = 0x60
_PUSH32 = 0x7F


@dataclass(frozen=True)
class Instruction:
    """A single decoded EVM instruction."""

    pc: int
    opcode: int
    immediate: bytes  # non-empty only for PUSH1..PUSH32


def disassemble(bytecode: bytes) -> list[Instruction]:
    """Decode bytecode into a flat list of Instructions.

    PUSH immediates are embedded in the Instruction; bytes inside a PUSH
    immediate do not produce their own Instruction entries.  Truncated
    immediates at the end of bytecode are zero-padded.
    """
    instructions: list[Instruction] = []
    i = 0
    n = len(bytecode)
    while i < n:
        op = bytecode[i]
        if _PUSH1 <= op <= _PUSH32:
            imm_len = op - _PUSH1 + 1
            raw = bytecode[i + 1 : i + 1 + imm_len]
            if len(raw) < imm_len:
                raw = raw + bytes(imm_len - len(raw))
            instructions.append(Instruction(pc=i, opcode=op, immediate=bytes(raw)))
            i += 1 + imm_len
        else:
            instructions.append(Instruction(pc=i, opcode=op, immediate=b""))
            i += 1
    return instructions


def compute_jumpdest_table(bytecode: bytes) -> frozenset[int]:
    """Return the set of valid JUMPDEST positions (SCHEMA.md §5.1).

    Positions that fall inside PUSH immediates are excluded even if the
    byte value is 0x5B.
    """
    valid: set[int] = set()
    i = 0
    n = len(bytecode)
    while i < n:
        op = bytecode[i]
        if op == 0x5B:  # JUMPDEST
            valid.add(i)
        if _PUSH1 <= op <= _PUSH32:
            i += op - _PUSH1 + 2
        else:
            i += 1
    return frozenset(valid)
