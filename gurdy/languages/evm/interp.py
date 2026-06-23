"""A deterministic EVM interpreter (the shared EVM source interpreter).

Scope (interpreter v0.7 — ``languages/evm`` brief): the pure stack/arithmetic
slice of the EVM stack machine — the full push family ``PUSH1`` .. ``PUSH32``,
the binary arithmetic ``ADD`` / ``MUL`` / ``SUB``, the unsigned ``DIV`` /
``MOD`` and the **signed** ``SDIV`` / ``SMOD`` (each division/modulo with the EVM
by-zero ``= 0`` special case, and ``SDIV`` additionally with the ``INT_MIN / -1``
wrap-to-``INT_MIN`` case), the stack shuffles ``POP``, the duplications ``DUP1``
.. ``DUP16`` and the swaps ``SWAP1`` .. ``SWAP16``, ``STOP`` — over 256-bit
(bv256) words — the byte-addressed memory ops ``MLOAD`` / ``MSTORE`` /
``MSTORE8`` (v0.6) **and the persistent storage ops ``SLOAD`` / ``SSTORE``**
(v0.7). Every other opcode hard-aborts with ``Unsupported`` (BENCHMARKS.md §3);
KEVM is the recommended external oracle. ``PUSH0``, control flow, and ``MSIZE``
stay out of scope; they keep hard-aborting.

Machine model (ARCHITECTURE.md §5, post-step state):

- ``pc`` — a **byte** offset into the bytecode. A ``PUSH{n}`` carries an inline
  ``n``-byte big-endian immediate, so it advances ``pc`` by ``n + 1``; every
  other in-scope opcode advances ``pc`` by 1.
- A bounded operand stack of ``STACK_SIZE`` 256-bit cells ``s0..s{N-1}`` and a
  depth ``sp`` (the number of live items). ``s{i}`` holds the item at depth
  ``i``; ``s0`` is the bottom, ``s{sp-1}`` the top.
  - ``PUSH{n}`` writes ``s{sp}`` and increments ``sp``.
  - ``ADD`` / ``MUL`` / ``SUB`` / ``DIV`` / ``MOD`` / ``SDIV`` / ``SMOD`` read
    the top two (``a = s{sp-1}`` the top, ``b = s{sp-2}`` the next), write
    ``s{sp-2} = (a OP b) mod 2**256`` (``SUB`` is ``a - b``, top minus next;
    ``DIV`` is unsigned ``a // b`` and ``MOD`` unsigned ``a % b``, **both
    defined as ``0`` when ``b == 0``** — the EVM by-zero special case, not a
    trap), and decrement ``sp`` by one. ``SDIV`` / ``SMOD`` interpret both
    operands as two's-complement signed 256-bit and use **truncating** (C-style,
    round-toward-zero) division: ``SDIV`` is ``trunc(a / b)`` with ``b == 0 -> 0``
    *and* ``a == INT_MIN ∧ b == -1 -> INT_MIN`` (it wraps, since ``2**255``
    truncated to 256 bits is ``INT_MIN``); ``SMOD`` is the remainder taking the
    **sign of the dividend** with ``b == 0 -> 0`` (``INT_MIN = 2**255``).
  - ``POP`` drops the top (``sp`` decremented; the cell is left stale).
  - ``DUP{n}`` reads the n-th item from the top ``s{sp-n}``, writes ``s{sp}``,
    and increments ``sp`` (``DUP1`` duplicates the top itself).
  - ``SWAP{n}`` swaps the top ``s{sp-1}`` with the (n+1)-th item ``s{sp-1-n}``;
    the depth ``sp`` is unchanged (``SWAP1`` swaps the top two).
  **Popped/overwritten cells are left with their stale value** (never cleared)
  so the translator can mirror the cell-update rule exactly.
- **Memory** — a **byte-addressed, zero-initialized, unbounded** region
  ``mem`` (a ``{byte_addr: byte}`` map). ``MSTORE off, value`` pops the offset
  (top) then the value (next) and writes the **32-byte big-endian** encoding of
  ``value`` to ``mem[off .. off+31]`` (the most significant byte at ``mem[off]``).
  ``MLOAD off`` pops the offset and pushes the 32-byte big-endian word read from
  ``mem[off .. off+31]`` (bytes never written read as 0). ``MSTORE8 off, value``
  pops the offset (top) then the value (next) and writes only the **low byte** of
  ``value`` to ``mem[off]``. Each of these needs two stack items (offset + value
  for the stores, offset for the load); too few -> exceptional halt. EVM gas /
  memory-expansion cost is out of scope (the data is modeled, not the cost).
  The post-step **memory observable** is a fixed window ``m0 .. m{MEM_WINDOW-1}``
  of the lowest ``MEM_WINDOW`` memory bytes (each a byte ``0..255``) — a
  bit-vector projection of the byte map the BTOR2 target can mirror as
  bit-vector state (the shared BTOR2 trace exposes bit-vector, not array, state).
- **Storage** — a **persistent, zero-initialized** 256-bit-key -> 256-bit-value
  map ``storage`` (a ``{key: value}`` dict; both key and value are full bv256
  words, unlike the byte-addressed memory). ``SSTORE`` pops the key (top) then the
  value (next) and sets ``storage[key] := value``; ``SLOAD`` pops the key and
  pushes ``storage[key]`` (``0`` if the key was never written). ``SSTORE`` needs
  two stack items (key + value), ``SLOAD`` one (key); too few -> exceptional halt.
  EVM gas / warm-cold accounting / refunds are out of scope (the data is modeled,
  not the cost). The post-step **storage observable** is a fixed window
  ``s_at_0 .. s_at_{STORE_WINDOW-1}`` of the values at keys ``0 .. STORE_WINDOW-1``
  (each a full bv256 word) — the word-keyed analogue of the memory window, a
  bit-vector projection of the storage dict the BTOR2 target mirrors as bit-vector
  state. A store/load at a key *outside* the window is still validated because an
  ``SLOAD`` value lands on the stack (already an observable).
- ``halted`` — set by ``STOP`` or by running off the end of the bytecode.

Stack underflow / overflow are EVM *exceptional halts*; in this slice they set
``halted`` (a defined, deterministic edge) rather than trapping with a typed
error, which is reserved for *unsupported opcodes*. Behavior is a ``Trace`` of
post-step ``{"pc", "sp", "s0".."s{N-1}", "m0".."m{MEM_WINDOW-1}",
"s_at_0".."s_at_{STORE_WINDOW-1}", "halted"}`` states. Pure and deterministic.

Interpreter version (the shared deliverable's contract — AGENTS.md §3): a
versioned bump is required for any additive semantics change so dependent pairs
re-validate their square.
- ``0.7`` — added the persistent storage ops ``SLOAD`` / ``SSTORE`` over a
  zero-initialized 256-bit-key -> 256-bit-value map, with a fixed
  ``STORE_WINDOW``-key storage observable (``s_at_0 .. s_at_{STORE_WINDOW-1}``).
- ``0.6`` — added the byte-addressed memory ops ``MLOAD`` / ``MSTORE`` /
  ``MSTORE8`` over a zero-initialized unbounded byte map, with a fixed
  ``MEM_WINDOW``-byte memory observable (``m0 .. m{MEM_WINDOW-1}``).
- ``0.5`` — added the signed ``SDIV`` / ``SMOD`` (truncating two's-complement).
- ``0.4`` — added the full stack-manipulation family (PUSH3/5..32, DUP2..16,
  SWAP1..16).
- ``0.3`` — added the unsigned ``DIV`` / ``MOD``.
- ``0.2`` — added ``PUSH2``/``PUSH4``, ``MUL``/``SUB``, ``POP``/``DUP1``.
- ``0.1`` — ``PUSH1`` / ``ADD`` / ``STOP`` (initial vertical slice).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...core.errors import Unsupported
from ...core.types import Trace
from . import asm

INTERP_VERSION = "0.7"  # AGENTS.md §3: bumped when SLOAD/SSTORE were added.

WORD = 256
MASK256 = (1 << WORD) - 1
STACK_SIZE = 16  # bounded operand-stack depth for the slice
INT_MIN = 1 << (WORD - 1)  # 2**255 — the two's-complement minimum (only top bit set)
MEM_WINDOW = 64  # bytes of memory exposed as the observable m0..m{MEM_WINDOW-1}
STORE_WINDOW = 8  # storage keys 0..STORE_WINDOW-1 exposed as the observable s_at_0..


def _to_signed(v: int) -> int:
    """Interpret a masked bv256 word as a two's-complement signed integer."""
    return v - (1 << WORD) if v >= INT_MIN else v


@dataclass
class EvmProgram:
    """A loaded EVM contract: the raw bytecode (``pc`` is a byte offset) plus
    the initial entry point, a zero-initialized byte-addressed memory, and a
    zero-initialized persistent 256-bit-key -> 256-bit-value storage map."""

    code: bytes = b""
    entry: int = 0
    mem: dict[int, int] = field(default_factory=dict)
    storage: dict[int, int] = field(default_factory=dict)

    def byte(self, offset: int) -> int:
        return self.code[offset] if 0 <= offset < len(self.code) else 0

    def sload(self, key: int) -> int:
        """Read ``storage[key]`` (a full bv256 word); keys never written read as 0
        (zero-initialized persistent storage)."""
        return self.storage.get(key & MASK256, 0) & MASK256

    def sstore(self, key: int, value: int) -> None:
        """Set ``storage[key] := value`` (both are full bv256 words)."""
        self.storage[key & MASK256] = value & MASK256

    def mload(self, offset: int) -> int:
        """Read the 32-byte **big-endian** word at ``mem[offset .. offset+31]``;
        bytes never written read as 0 (zero-initialized memory)."""
        word = 0
        for i in range(32):
            word = (word << 8) | (self.mem.get(offset + i, 0) & 0xFF)
        return word

    def mstore(self, offset: int, value: int) -> None:
        """Write the 32-byte **big-endian** encoding of ``value`` to
        ``mem[offset .. offset+31]`` (most significant byte at ``offset``)."""
        value &= MASK256
        for i in range(32):
            self.mem[offset + i] = (value >> (8 * (31 - i))) & 0xFF

    def mstore8(self, offset: int, value: int) -> None:
        """Write the **low byte** of ``value`` to ``mem[offset]``."""
        self.mem[offset] = value & 0xFF


def program_from_bytes(code: bytes, entry: int = 0,
                       mem: dict[int, int] | None = None,
                       storage: dict[int, int] | None = None) -> EvmProgram:
    return EvmProgram(code=bytes(code), entry=entry, mem=dict(mem or {}),
                      storage=dict(storage or {}))


def _state(pc: int, sp: int, stack: list[int], mem: dict[int, int],
           storage: dict[int, int], halted: bool) -> dict[str, Any]:
    s: dict[str, Any] = {"pc": pc, "sp": sp, "halted": halted}
    for i in range(STACK_SIZE):
        s[f"s{i}"] = stack[i]
    for i in range(MEM_WINDOW):                # the fixed memory-window observable
        s[f"m{i}"] = mem.get(i, 0) & 0xFF
    for i in range(STORE_WINDOW):              # the fixed storage-window observable
        s[f"s_at_{i}"] = storage.get(i, 0) & MASK256
    return s


def _execute(prog: EvmProgram, pc: int, sp: int, stack: list[int]) -> tuple[int, int, bool]:
    """Execute one opcode; return ``(next_pc, next_sp, halted)`` and mutate
    ``stack`` (and ``prog.mem`` / ``prog.storage`` for the memory / storage ops)
    in place. Popped cells keep their stale value."""
    op = prog.byte(pc)

    if op == asm.STOP:
        return pc + 1, sp, True

    if op in asm.PUSH_WIDTH:                        # PUSH1 .. PUSH32
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

    if op in (asm.SDIV, asm.SMOD):                 # signed division / modulo
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, True
        # Interpret both operands as two's-complement signed bv256 and use
        # TRUNCATING (round-toward-zero, C-style) division — NOT Python's
        # flooring ``//`` / ``%``. EVM by-zero is 0 (not a trap).
        sa = _to_signed(stack[sp - 1])             # top (dividend)
        sb = _to_signed(stack[sp - 2])             # next (divisor)
        if op == asm.SDIV:
            if sb == 0:
                r = 0
            elif sa == -INT_MIN and sb == -1:      # INT_MIN / -1 wraps to INT_MIN
                r = -INT_MIN                        # (2**255 truncated to 256 bits)
            else:                                  # truncating quotient (toward zero)
                q = abs(sa) // abs(sb)
                r = -q if (sa < 0) != (sb < 0) else q
        else:                                      # SMOD: remainder, sign of dividend
            if sb == 0:
                r = 0
            else:
                rem = abs(sa) % abs(sb)
                r = -rem if sa < 0 else rem
        stack[sp - 2] = r & MASK256
        return pc + 1, sp - 1, False

    if op == asm.POP:
        if sp < 1:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, True
        return pc + 1, sp - 1, False               # drop top; cell left stale

    if op in asm.DUP_N:                            # DUP1..DUP16
        n = asm.DUP_N[op]
        if sp < n:                                 # nothing at depth n -> underflow
            return pc + 1, sp, True
        if sp >= STACK_SIZE:                       # overflow -> exceptional halt
            return pc + 1, sp, True
        stack[sp] = stack[sp - n]                  # copy the n-th item onto the top
        return pc + 1, sp + 1, False

    if op in asm.SWAP_N:                           # SWAP1..SWAP16
        n = asm.SWAP_N[op]
        if sp < n + 1:                             # need the top and the (n+1)-th item
            return pc + 1, sp, True
        top, deep = sp - 1, sp - 1 - n             # swap s{sp-1} <-> s{sp-1-n}
        stack[top], stack[deep] = stack[deep], stack[top]
        return pc + 1, sp, False                   # depth unchanged

    if op == asm.MLOAD:                            # MLOAD: pop off, push mem word
        if sp < 1:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, True
        offset = stack[sp - 1]                     # top is the byte offset
        stack[sp - 1] = prog.mload(offset)         # offset popped, word pushed: sp net 0
        return pc + 1, sp, False

    if op in (asm.MSTORE, asm.MSTORE8):            # MSTORE / MSTORE8: pop off, value
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, True
        offset = stack[sp - 1]                     # top is the byte offset
        value = stack[sp - 2]                      # next is the value
        if op == asm.MSTORE:
            prog.mstore(offset, value)             # 32-byte big-endian word
        else:                                      # MSTORE8: low byte only
            prog.mstore8(offset, value)
        return pc + 1, sp - 2, False               # both operands consumed

    if op == asm.SLOAD:                            # SLOAD: pop key, push storage word
        if sp < 1:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, True
        key = stack[sp - 1]                        # top is the 256-bit key
        stack[sp - 1] = prog.sload(key)            # key popped, value pushed: sp net 0
        return pc + 1, sp, False

    if op == asm.SSTORE:                           # SSTORE: pop key, value; write storage
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, True
        key = stack[sp - 1]                        # top is the key
        value = stack[sp - 2]                      # next is the value
        prog.sstore(key, value)
        return pc + 1, sp - 2, False               # both operands consumed

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
    map over cells ``0..STACK_SIZE-1``), ``sp``, an initial ``mem`` (a
    ``{byte_addr: byte}`` map), and an initial ``storage`` (a ``{key: value}``
    map of bv256 words). Returns the post-step trace. Pure: the run works on
    private copies of the memory and storage maps, never mutating ``prog``.
    """
    stack = [0] * STACK_SIZE
    pc = prog.entry
    sp = 0
    mem = dict(prog.mem)
    storage = dict(prog.storage)
    if binding:
        pc = int(binding.get("pc", pc))
        sp = int(binding.get("sp", sp))
        for i, v in binding.get("stack", {}).items():
            stack[int(i)] = int(v) & MASK256
        for a, v in binding.get("mem", {}).items():
            mem[int(a)] = int(v) & 0xFF
        for key, v in binding.get("storage", {}).items():
            storage[int(key) & MASK256] = int(v) & MASK256
    # private mem / storage copies (purity)
    prog = EvmProgram(code=prog.code, entry=prog.entry, mem=mem, storage=storage)

    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        if not (0 <= pc < len(prog.code)):
            # ran off the end -> halt
            trace.append(_state(pc, sp, stack, mem, storage, True))
            break
        pc, sp, halt = _execute(prog, pc, sp, stack)
        steps += 1
        trace.append(_state(pc, sp, stack, mem, storage, halt))
        if halt:
            break
    return trace
