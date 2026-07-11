"""A deterministic EVM interpreter (the shared EVM source interpreter).

Scope (interpreter v0.9 — ``languages/evm`` brief): the stack/arithmetic
slice of the EVM stack machine — the full push family ``PUSH1`` .. ``PUSH32``,
the binary arithmetic ``ADD`` / ``MUL`` / ``SUB``, the unsigned ``DIV`` /
``MOD`` and the **signed** ``SDIV`` / ``SMOD`` (each division/modulo with the EVM
by-zero ``= 0`` special case, and ``SDIV`` additionally with the ``INT_MIN / -1``
wrap-to-``INT_MIN`` case), the stack shuffles ``POP``, the duplications ``DUP1``
.. ``DUP16`` and the swaps ``SWAP1`` .. ``SWAP16``, ``STOP``, **``PUSH0``** — over
256-bit (bv256) words — the byte-addressed memory ops ``MLOAD`` / ``MSTORE`` /
``MSTORE8`` (v0.6), the persistent storage ops ``SLOAD`` / ``SSTORE`` (v0.7),
the control-flow ops ``JUMP`` / ``JUMPI`` / ``JUMPDEST`` / ``PC`` (v0.8 — the
first non-linear control flow), **and the terminal/halt ops ``RETURN`` /
``REVERT`` / ``INVALID``** (v0.9 — the first halts that carry a *why*: a success,
revert, or exceptional ``status``). Every other opcode hard-aborts with
``Unsupported`` (BENCHMARKS.md §3); KEVM is the recommended external oracle.
``MSIZE`` and gas / ``CALL`` / ``CREATE`` / ``LOG`` stay out of scope; they keep
hard-aborting.

Halt status (v0.9). Every halt now carries a *status* — *why* the run stopped —
exposed as the observable ``status`` (a small bit-vector) alongside the existing
``halted`` flag (which stays exactly ``status != running``):

- ``running`` (0) — not halted.
- ``success`` (1) — ``STOP``, running off the end of the bytecode, or ``RETURN``.
- ``revert`` (2) — ``REVERT``.
- ``exceptional`` (3) — ``INVALID``, a stack underflow/overflow, or an invalid
  jump. (All the pre-v0.9 "exceptional halt" edges now record this status.)

The three terminal ops (v0.9):

- ``PUSH0`` (0x5f) — push the constant ``0`` (no inline immediate); ``pc += 1``,
  ``sp += 1`` (overflow ``sp >= STACK_SIZE`` -> exceptional halt). It is *not*
  part of the ``PUSH{n}`` width family — it carries no operand byte.
- ``RETURN`` (0xf3) — pop ``offset`` (top) then ``length`` (next); **halt with
  the ``success`` status**. The return data is ``memory[offset..offset+length]``,
  already observable via the memory window — no new return-data state is needed;
  the two operands are consumed and the run halts successfully.
- ``REVERT`` (0xfd) — pop ``offset`` (top) then ``length`` (next); **halt with
  the ``revert`` status** (a distinct terminal status from ``success``).
- ``INVALID`` (0xfe) — **halt with the ``exceptional`` status**; consumes no
  operands. (``RETURN``/``REVERT`` exceptional-halt on stack underflow, ``sp < 2``.)

Control flow (v0.8). The EVM is byte-addressed and its jump destinations are
**dynamic** — a ``JUMP``/``JUMPI`` pops the target *byte offset* off the stack —
but the set of **valid** targets is statically fixed by the bytecode: a jump may
only land on a ``JUMPDEST`` (0x5b) byte, and a jump to any other position
(a non-``JUMPDEST`` opcode, a byte *inside* a ``PUSH`` immediate, or out of
range) is an EVM **exceptional halt**. So the ``JUMPDEST`` byte offsets are
scanned once (skipping ``PUSH`` immediate bytes so a ``0x5b`` *inside* an
immediate is not a target), and the dynamic target is resolved against that set:

- ``JUMPDEST`` (0x5b) — a no-op marking a valid target; ``pc += 1``.
- ``JUMP`` (0x56) — pop ``dest``; if ``dest`` is a valid ``JUMPDEST`` offset set
  ``pc := dest``, else exceptional halt (``halted := 1``).
- ``JUMPI`` (0x57) — pop ``dest`` then ``cond``; if ``cond != 0`` resolve
  ``dest`` as for ``JUMP`` (valid -> ``pc := dest``, invalid -> halt); if
  ``cond == 0`` fall through (``pc += 1``).
- ``PC`` (0x58) — push the byte offset of the ``PC`` instruction itself; ``pc += 1``.

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
- ``halted`` — set by ``STOP``, by running off the end of the bytecode, by
  ``RETURN`` / ``REVERT`` / ``INVALID``, by an exceptional halt (stack
  underflow/overflow), or by a ``JUMP``/``JUMPI`` to a position that is not a
  valid ``JUMPDEST`` (an invalid-jump exceptional halt). It stays exactly
  ``status != running``.
- ``status`` — *why* the run halted: ``running`` (0), ``success`` (1, from
  ``STOP`` / off-the-end / ``RETURN``), ``revert`` (2, from ``REVERT``), or
  ``exceptional`` (3, from ``INVALID`` / underflow / overflow / invalid jump).

Stack underflow / overflow are EVM *exceptional halts*; in this slice they set
``halted`` (and ``status := exceptional``) — a defined, deterministic edge —
rather than trapping with a typed error, which is reserved for *unsupported
opcodes*. Behavior is a ``Trace`` of post-step ``{"pc", "sp", "s0".."s{N-1}",
"m0".."m{MEM_WINDOW-1}", "s_at_0".."s_at_{STORE_WINDOW-1}", "halted",
"status"}`` states. Pure and deterministic.

Interpreter version (the shared deliverable's contract — AGENTS.md §3): a
versioned bump is required for any additive semantics change so dependent pairs
re-validate their square.
- ``0.9`` — added ``PUSH0`` and the terminal/halt ops ``RETURN`` / ``REVERT`` /
  ``INVALID``, and a **halt-status observable** ``status`` (running / success /
  revert / exceptional) so a halt now records *why* it stopped. The existing
  ``halted`` flag and every pre-v0.9 opcode's behavior are unchanged: ``STOP`` /
  off-the-end stay ``success``, and the underflow/overflow/invalid-jump edges that
  set ``halted`` now also set ``status := exceptional``.
- ``0.8`` — added the control-flow ops ``JUMP`` / ``JUMPI`` / ``JUMPDEST`` /
  ``PC`` (the first non-linear control flow). Jump targets are dynamic (popped
  off the stack) but resolved against the statically-scanned set of ``JUMPDEST``
  byte offsets; a jump to a non-``JUMPDEST`` is an exceptional halt.
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

INTERP_VERSION = "0.10"  # AGENTS.md §3: 0.9->0.10 added the bitwise AND/OR/XOR/NOT + ISZERO opcodes.

WORD = 256
MASK256 = (1 << WORD) - 1
STACK_SIZE = 16  # bounded operand-stack depth for the slice
INT_MIN = 1 << (WORD - 1)  # 2**255 — the two's-complement minimum (only top bit set)
MEM_WINDOW = 64  # bytes of memory exposed as the observable m0..m{MEM_WINDOW-1}
STORE_WINDOW = 8  # storage keys 0..STORE_WINDOW-1 exposed as the observable s_at_0..

# Halt-status observable (v0.9): *why* a run halted, exposed as ``status`` (a
# small bit-vector, STATUS_WIDTH bits) alongside the existing ``halted`` flag
# (which stays exactly ``status != STATUS_RUNNING``). The four values are
# spec-derived terminal outcomes; the translator mirrors this exact encoding.
STATUS_WIDTH = 8  # bits of the ``status`` observable (a byte; values 0..3)
STATUS_RUNNING = 0      # not halted
STATUS_SUCCESS = 1      # STOP / off-the-end / RETURN — a successful halt
STATUS_REVERT = 2       # REVERT — a reverting halt (distinct terminal status)
STATUS_EXCEPTIONAL = 3  # INVALID / underflow / overflow / invalid jump


def _to_signed(v: int) -> int:
    """Interpret a masked bv256 word as a two's-complement signed integer."""
    return v - (1 << WORD) if v >= INT_MIN else v


def jumpdests(code: bytes) -> frozenset[int]:
    """The set of **valid jump-destination byte offsets** in ``code``: every byte
    offset holding a ``JUMPDEST`` (0x5b) opcode, skipping the inline immediate
    bytes of a ``PUSH{n}`` so a ``0x5b`` that happens to fall *inside* a ``PUSH``
    immediate is **not** counted (the EVM jump-destination-analysis rule). This is
    the statically-known target set ``JUMP``/``JUMPI`` resolve against; it is the
    single source of truth the translator's PC-resolution mirrors."""
    out: set[int] = set()
    i = 0
    n = len(code)
    while i < n:
        op = code[i]
        if op == asm.JUMPDEST:
            out.add(i)
            i += 1
        elif op in asm.PUSH_WIDTH:                 # skip the inline immediate bytes
            i += 1 + asm.PUSH_WIDTH[op]
        else:
            i += 1
    return frozenset(out)


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
           storage: dict[int, int], status: int) -> dict[str, Any]:
    # ``halted`` stays exactly ``status != running`` (so all pre-v0.9 observables
    # are unchanged); ``status`` (v0.9) records *why* the run halted.
    s: dict[str, Any] = {
        "pc": pc, "sp": sp,
        "halted": status != STATUS_RUNNING,
        "status": status,
    }
    for i in range(STACK_SIZE):
        s[f"s{i}"] = stack[i]
    for i in range(MEM_WINDOW):                # the fixed memory-window observable
        s[f"m{i}"] = mem.get(i, 0) & 0xFF
    for i in range(STORE_WINDOW):              # the fixed storage-window observable
        s[f"s_at_{i}"] = storage.get(i, 0) & MASK256
    return s


def _execute(prog: EvmProgram, pc: int, sp: int, stack: list[int],
             jds: frozenset[int]) -> tuple[int, int, int]:
    """Execute one opcode; return ``(next_pc, next_sp, status)`` and mutate
    ``stack`` (and ``prog.mem`` / ``prog.storage`` for the memory / storage ops)
    in place. ``status`` is ``STATUS_RUNNING`` (0, the run continues) or one of
    the halt statuses ``STATUS_SUCCESS`` / ``STATUS_REVERT`` / ``STATUS_EXCEPTIONAL``
    (v0.9); ``RUNNING`` is falsy and the halt statuses are truthy, so the caller's
    ``if status:`` halt test is unchanged. Popped cells keep their stale value.
    ``jds`` is the precomputed set of valid ``JUMPDEST`` byte offsets that
    ``JUMP``/``JUMPI`` resolve against."""
    op = prog.byte(pc)

    if op == asm.STOP:
        return pc + 1, sp, STATUS_SUCCESS

    if op == asm.PUSH0:                             # PUSH0: push the constant 0
        if sp >= STACK_SIZE:                       # stack overflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        stack[sp] = 0
        return pc + 1, sp + 1, STATUS_RUNNING

    if op in asm.PUSH_WIDTH:                        # PUSH1 .. PUSH32
        n = asm.PUSH_WIDTH[op]
        if sp >= STACK_SIZE:                       # stack overflow -> exceptional halt
            return pc + 1 + n, sp, STATUS_EXCEPTIONAL
        imm = 0
        for k in range(n):                         # big-endian inline immediate
            imm = (imm << 8) | prog.byte(pc + 1 + k)
        stack[sp] = imm & MASK256
        return pc + 1 + n, sp + 1, STATUS_RUNNING

    if op in (asm.ADD, asm.MUL, asm.SUB):          # binary arithmetic
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        a = stack[sp - 1]                          # top
        b = stack[sp - 2]                          # next
        if op == asm.ADD:
            r = a + b
        elif op == asm.MUL:
            r = a * b
        else:                                      # SUB: top minus next
            r = a - b
        stack[sp - 2] = r & MASK256
        return pc + 1, sp - 1, STATUS_RUNNING

    if op in (asm.DIV, asm.MOD):                   # unsigned division / modulo
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
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
        return pc + 1, sp - 1, STATUS_RUNNING

    if op in (asm.SDIV, asm.SMOD):                 # signed division / modulo
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
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
        return pc + 1, sp - 1, STATUS_RUNNING

    if op == asm.POP:
        if sp < 1:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        return pc + 1, sp - 1, STATUS_RUNNING      # drop top; cell left stale

    if op in asm.DUP_N:                            # DUP1..DUP16
        n = asm.DUP_N[op]
        if sp < n:                                 # nothing at depth n -> underflow
            return pc + 1, sp, STATUS_EXCEPTIONAL
        if sp >= STACK_SIZE:                       # overflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        stack[sp] = stack[sp - n]                  # copy the n-th item onto the top
        return pc + 1, sp + 1, STATUS_RUNNING

    if op in asm.SWAP_N:                           # SWAP1..SWAP16
        n = asm.SWAP_N[op]
        if sp < n + 1:                             # need the top and the (n+1)-th item
            return pc + 1, sp, STATUS_EXCEPTIONAL
        top, deep = sp - 1, sp - 1 - n             # swap s{sp-1} <-> s{sp-1-n}
        stack[top], stack[deep] = stack[deep], stack[top]
        return pc + 1, sp, STATUS_RUNNING          # depth unchanged

    if op == asm.MLOAD:                            # MLOAD: pop off, push mem word
        if sp < 1:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        offset = stack[sp - 1]                     # top is the byte offset
        stack[sp - 1] = prog.mload(offset)         # offset popped, word pushed: sp net 0
        return pc + 1, sp, STATUS_RUNNING

    if op in (asm.MSTORE, asm.MSTORE8):            # MSTORE / MSTORE8: pop off, value
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        offset = stack[sp - 1]                     # top is the byte offset
        value = stack[sp - 2]                      # next is the value
        if op == asm.MSTORE:
            prog.mstore(offset, value)             # 32-byte big-endian word
        else:                                      # MSTORE8: low byte only
            prog.mstore8(offset, value)
        return pc + 1, sp - 2, STATUS_RUNNING      # both operands consumed

    if op == asm.SLOAD:                            # SLOAD: pop key, push storage word
        if sp < 1:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        key = stack[sp - 1]                        # top is the 256-bit key
        stack[sp - 1] = prog.sload(key)            # key popped, value pushed: sp net 0
        return pc + 1, sp, STATUS_RUNNING

    if op == asm.SSTORE:                           # SSTORE: pop key, value; write storage
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        key = stack[sp - 1]                        # top is the key
        value = stack[sp - 2]                      # next is the value
        prog.sstore(key, value)
        return pc + 1, sp - 2, STATUS_RUNNING      # both operands consumed

    if op == asm.JUMPDEST:                          # JUMPDEST: a no-op marker
        return pc + 1, sp, STATUS_RUNNING          # advances pc; no stack effect

    if op == asm.JUMP:                              # JUMP: pop dest, set pc := dest
        if sp < 1:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        dest = stack[sp - 1]                       # top is the destination byte offset
        if dest in jds:                            # a valid JUMPDEST -> jump
            return dest, sp - 1, STATUS_RUNNING
        return pc + 1, sp - 1, STATUS_EXCEPTIONAL  # invalid target -> exceptional halt

    if op == asm.JUMPI:                             # JUMPI: pop dest, cond; jump iff cond
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        dest = stack[sp - 1]                       # top is the destination
        cond = stack[sp - 2]                       # next is the condition
        if cond != 0:                              # taken: resolve dest as for JUMP
            if dest in jds:                        # a valid JUMPDEST -> jump
                return dest, sp - 2, STATUS_RUNNING
            return pc + 1, sp - 2, STATUS_EXCEPTIONAL  # invalid target -> halt
        return pc + 1, sp - 2, STATUS_RUNNING      # not taken: fall through

    if op == asm.PC:                                # PC: push this instruction's offset
        if sp >= STACK_SIZE:                       # overflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        stack[sp] = pc & MASK256                    # the byte offset of THIS PC opcode
        return pc + 1, sp + 1, STATUS_RUNNING

    if op == asm.RETURN:                            # RETURN: pop offset, length; SUCCESS
        # The return data is memory[offset..offset+length], already observable
        # via the memory window — no new state is needed; consume both operands
        # and halt successfully. Stack underflow (need offset + length) -> halt.
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        return pc + 1, sp - 2, STATUS_SUCCESS      # offset + length consumed

    if op == asm.REVERT:                            # REVERT: pop offset, length; REVERT
        if sp < 2:                                 # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        return pc + 1, sp - 2, STATUS_REVERT       # offset + length consumed

    if op == asm.INVALID:                           # INVALID: halt exceptionally
        return pc + 1, sp, STATUS_EXCEPTIONAL      # consumes no operands

    if op in (asm.AND, asm.OR, asm.XOR):            # binary bitwise (v0.10)
        if sp < 2:                                  # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        a = stack[sp - 1]                           # top
        b = stack[sp - 2]                           # next
        if op == asm.AND:
            r = a & b
        elif op == asm.OR:
            r = a | b
        else:                                       # XOR
            r = a ^ b
        stack[sp - 2] = r & MASK256
        return pc + 1, sp - 1, STATUS_RUNNING

    if op == asm.NOT:                               # unary bitwise complement (v0.10)
        if sp < 1:                                  # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        a = stack[sp - 1]                           # top
        stack[sp - 1] = (~a) & MASK256              # ~a over 256 bits
        return pc + 1, sp, STATUS_RUNNING           # pop 1 + push 1: sp unchanged

    if op == asm.ISZERO:                            # unary: 1 if top==0 else 0 (v0.10)
        if sp < 1:                                  # stack underflow -> exceptional halt
            return pc + 1, sp, STATUS_EXCEPTIONAL
        a = stack[sp - 1]                           # top
        stack[sp - 1] = 1 if (a & MASK256) == 0 else 0
        return pc + 1, sp, STATUS_RUNNING           # pop 1 + push 1: sp unchanged

    raise Unsupported("evm", asm.opcode_name(op))


def run(
    prog: EvmProgram,
    binding: dict[str, Any] | None = None,
    max_steps: int = 100_000,
    **_kw: Any,
) -> Trace:
    """Run ``prog`` to a halt (``STOP``, off-the-end, ``RETURN`` / ``REVERT`` /
    ``INVALID``, an exceptional halt, or ``max_steps``). The final row's ``status``
    records *why* it stopped (success / revert / exceptional).

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
    jds = jumpdests(prog.code)  # the static set of valid JUMPDEST byte offsets

    trace: list[dict[str, Any]] = []
    steps = 0
    while steps < max_steps:
        if not (0 <= pc < len(prog.code)):
            # ran off the end -> a SUCCESS halt (an implicit STOP)
            trace.append(_state(pc, sp, stack, mem, storage, STATUS_SUCCESS))
            break
        pc, sp, status = _execute(prog, pc, sp, stack, jds)
        steps += 1
        trace.append(_state(pc, sp, stack, mem, storage, status))
        if status != STATUS_RUNNING:
            break
    return trace
