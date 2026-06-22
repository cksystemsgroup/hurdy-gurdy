"""A deterministic EVM interpreter (the shared EVM source interpreter).

Scope (MVP, thin-first — ``languages/evm`` brief): the minimal arithmetic
vertical slice of the EVM stack machine — ``PUSH1``, ``ADD``, and ``STOP`` —
over 256-bit (bv256) words. Every other opcode hard-aborts with
``Unsupported`` (BENCHMARKS.md §3); KEVM is the recommended external oracle.

Machine model (ARCHITECTURE.md §5, post-step state):

- ``pc`` — a **byte** offset into the bytecode (``PUSH1`` carries an inline
  1-byte immediate, so it advances ``pc`` by 2; ``ADD``/``STOP`` by 1).
- A bounded operand stack of ``STACK_SIZE`` 256-bit cells ``s0..s{N-1}`` and a
  depth ``sp`` (the number of live items). ``s{i}`` holds the item at depth
  ``i``; ``s0`` is the bottom, ``s{sp-1}`` the top. ``PUSH1`` writes ``s{sp}``
  and increments ``sp``; ``ADD`` reads the top two (``a = s{sp-1}``,
  ``b = s{sp-2}``), writes ``s{sp-2} = (a + b) mod 2**256`` and decrements
  ``sp`` by one. **Popped cells are left with their stale value** (never
  cleared) so the translator can mirror the cell-update rule exactly.
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

    if op == asm.PUSH1:
        if sp >= STACK_SIZE:                       # stack overflow -> exceptional halt
            return pc + 2, sp, True
        stack[sp] = prog.byte(pc + 1) & MASK256
        return pc + 2, sp + 1, False

    if op == asm.ADD:
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, True
        a = stack[sp - 1]
        b = stack[sp - 2]
        stack[sp - 2] = (a + b) & MASK256
        return pc + 1, sp - 1, False

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
