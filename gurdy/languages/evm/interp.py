"""A deterministic EVM interpreter (the shared EVM source interpreter).

Scope (interpreter v0.3 — ``languages/evm`` brief): the pure stack/arithmetic
slice of the EVM stack machine — the push immediates ``PUSH1`` / ``PUSH2`` /
``PUSH4``, the binary arithmetic ``ADD`` / ``MUL`` / ``SUB`` and the unsigned
``DIV`` / ``MOD`` (each with the EVM by-zero ``= 0`` special case), the stack
shuffles ``POP`` / ``DUP1``, and ``STOP`` — over 256-bit (bv256) words. Every
other opcode hard-aborts with ``Unsupported`` (BENCHMARKS.md §3); KEVM is the
recommended external oracle. The signed ``SDIV`` / ``SMOD`` stay out of scope
(they need the EVM ``INT_MIN / -1`` special case) and keep hard-aborting.

Machine model (ARCHITECTURE.md §5, post-step state):

- ``pc`` — a **byte** offset into the bytecode. A ``PUSH{n}`` carries an inline
  ``n``-byte big-endian immediate, so it advances ``pc`` by ``n + 1``; every
  other in-scope opcode advances ``pc`` by 1.
- A bounded operand stack of ``STACK_SIZE`` 256-bit cells ``s0..s{N-1}`` and a
  depth ``sp`` (the number of live items). ``s{i}`` holds the item at depth
  ``i``; ``s0`` is the bottom, ``s{sp-1}`` the top.
  - ``PUSH{n}`` writes ``s{sp}`` and increments ``sp``.
  - ``ADD`` / ``MUL`` / ``SUB`` / ``DIV`` / ``MOD`` read the top two
    (``a = s{sp-1}`` the top, ``b = s{sp-2}`` the next), write
    ``s{sp-2} = (a OP b) mod 2**256`` (``SUB`` is ``a - b``, top minus next;
    ``DIV`` is unsigned ``a // b`` and ``MOD`` unsigned ``a % b``, **both
    defined as ``0`` when ``b == 0``** — the EVM by-zero special case, not a
    trap), and decrement ``sp`` by one.
  - ``POP`` drops the top (``sp`` decremented; the cell is left stale).
  - ``DUP1`` reads the top ``s{sp-1}``, writes ``s{sp}``, and increments ``sp``.
  **Popped/overwritten cells are left with their stale value** (never cleared)
  so the translator can mirror the cell-update rule exactly.
- ``halted`` — set by ``STOP`` or by running off the end of the bytecode.

Stack underflow / overflow are EVM *exceptional halts*; in this slice they set
``halted`` (a defined, deterministic edge) rather than trapping with a typed
error, which is reserved for *unsupported opcodes*. Behavior is a ``Trace`` of
post-step ``{"pc", "sp", "s0".."s{N-1}", "halted"}`` states. Pure and
deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core.errors import Unsupported
from ...core.types import Trace
from . import asm

WORD = 256
MASK256 = (1 << WORD) - 1
STACK_SIZE = 16  # bounded operand-stack depth for the slice


@dataclass
class EvmProgram:
    """A loaded EVM contract: the raw bytecode (``pc`` is a byte offset) plus
    the initial entry point."""

    code: bytes = b""
    entry: int = 0

    def byte(self, offset: int) -> int:
        return self.code[offset] if 0 <= offset < len(self.code) else 0


def program_from_bytes(code: bytes, entry: int = 0) -> EvmProgram:
    return EvmProgram(code=bytes(code), entry=entry)


def _state(pc: int, sp: int, stack: list[int], halted: bool) -> dict[str, Any]:
    s: dict[str, Any] = {"pc": pc, "sp": sp, "halted": halted}
    for i in range(STACK_SIZE):
        s[f"s{i}"] = stack[i]
    return s


def _execute(prog: EvmProgram, pc: int, sp: int, stack: list[int]) -> tuple[int, int, bool]:
    """Execute one opcode; return ``(next_pc, next_sp, halted)`` and mutate
    ``stack`` in place. Popped cells keep their stale value."""
    op = prog.byte(pc)

    if op == asm.STOP:
        return pc + 1, sp, True

    if op in asm.PUSH_WIDTH:                        # PUSH1 / PUSH2 / PUSH4
        n = asm.PUSH_WIDTH[op]
        if sp >= STACK_SIZE:                       # stack overflow -> exceptional halt
            return pc + 1 + n, sp, True
        imm = 0
        for k in range(n):                         # big-endian inline immediate
            imm = (imm << 8) | prog.byte(pc + 1 + k)
        stack[sp] = imm & MASK256
        return pc + 1 + n, sp + 1, False

    if op in (asm.ADD, asm.MUL, asm.SUB):          # binary arithmetic
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, True
        a = stack[sp - 1]                          # top
        b = stack[sp - 2]                          # next
        if op == asm.ADD:
            r = a + b
        elif op == asm.MUL:
            r = a * b
        else:                                      # SUB: top minus next
            r = a - b
        stack[sp - 2] = r & MASK256
        return pc + 1, sp - 1, False

    if op in (asm.DIV, asm.MOD):                   # unsigned division / modulo
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, True
        a = stack[sp - 1]                          # top (dividend)
        b = stack[sp - 2]                          # next (divisor)
        # EVM by-zero special case is 0 (not a trap). For UNSIGNED operands a, b
        # in [0, 2**256) Python ``//`` / ``%`` (which floor) equal the truncating
        # unsigned quotient / remainder; both operands are masked non-negative.
        if op == asm.DIV:
            r = 0 if b == 0 else a // b
        else:                                      # MOD
            r = 0 if b == 0 else a % b
        stack[sp - 2] = r & MASK256
        return pc + 1, sp - 1, False

    if op == asm.POP:
        if sp < 1:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, True
        return pc + 1, sp - 1, False               # drop top; cell left stale

    if op == asm.DUP1:
        if sp < 1:                                 # nothing to duplicate -> underflow
            return pc + 1, sp, True
        if sp >= STACK_SIZE:                       # overflow -> exceptional halt
            return pc + 1, sp, True
        stack[sp] = stack[sp - 1]
        return pc + 1, sp + 1, False

    raise Unsupported("evm", asm.opcode_name(op))


def run(
    prog: EvmProgram,
    binding: dict[str, Any] | None = None,
    max_steps: int = 100_000,
    **_kw: Any,
) -> Trace:
    """Run ``prog`` to a halt (``STOP``, off-the-end, an exceptional halt, or
    ``max_steps``).

    ``binding`` may set ``pc`` and the initial ``stack`` (a ``{index: value}``
    map over cells ``0..STACK_SIZE-1``) and ``sp``. Returns the post-step trace.
    """
    stack = [0] * STACK_SIZE
    pc = prog.entry
    sp = 0
    if binding:
        pc = int(binding.get("pc", pc))
        sp = int(binding.get("sp", sp))
        for i, v in binding.get("stack", {}).items():
            stack[int(i)] = int(v) & MASK256

    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        if not (0 <= pc < len(prog.code)):
            trace.append(_state(pc, sp, stack, True))   # ran off the end -> halt
            break
        pc, sp, halt = _execute(prog, pc, sp, stack)
        steps += 1
        trace.append(_state(pc, sp, stack, halt))
        if halt:
            break
    return trace
