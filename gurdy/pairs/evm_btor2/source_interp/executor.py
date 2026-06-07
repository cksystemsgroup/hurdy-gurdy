"""Concrete EVM executor for the P1 opcode set.

Implements SCHEMA.md §§3–12, schema version 1.0.0.  This executor is
deliberately pure-Python so it can serve as the ground-truth oracle for the
BTOR2 translator: same bytecode + context must produce the same terminal
state as the symbolic model up to bound.

Public API:  MachineState, EvmContext, StepRecord, step(), run().
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .disasm import compute_jumpdest_table

_MASK256 = (1 << 256) - 1
_MASK8 = 0xFF


# ---------------------------------------------------------------------------
# Arithmetic helpers
# ---------------------------------------------------------------------------


def _u256(x: int) -> int:
    return x & _MASK256


def _s256(x: int) -> int:
    """Interpret unsigned bv256 as signed two's-complement."""
    x = x & _MASK256
    return x - (1 << 256) if x >= (1 << 255) else x


def _from_s256(x: int) -> int:
    """Encode signed int as unsigned bv256."""
    return (x + (1 << 256)) & _MASK256 if x < 0 else x & _MASK256


def _byte_len(x: int) -> int:
    """Number of bytes to represent x (0 for x == 0).  Used for EXP gas (§10.2)."""
    if x == 0:
        return 0
    n = 0
    while x:
        n += 1
        x >>= 8
    return n


def _mem_cost(words: int) -> int:
    """Memory expansion gas (§7.1): floor(n*n/512) + 3*n."""
    return words * words // 512 + 3 * words


def _new_mem_words(current: int, offset: int, size: int) -> int:
    """High-water mark in 32-byte words after accessing [offset, offset+size)."""
    if size == 0:
        return current
    required = (offset + size + 31) // 32
    return required if required > current else current


# ---------------------------------------------------------------------------
# State and context
# ---------------------------------------------------------------------------


@dataclass
class MachineState:
    """Concrete EVM machine state (SCHEMA.md §3).

    ``stack[0]`` is the oldest element; ``stack[-1]`` is TOS.
    ``mem`` is sparse: missing entries are implicitly 0.
    ``sto_original`` snapshots storage at call entry for SSTORE gas (§10.4).
    """

    stack: list[int] = field(default_factory=list)
    mem: dict[int, int] = field(default_factory=dict)
    mem_words: int = 0
    sto: dict[int, int] = field(default_factory=dict)
    sto_original: dict[int, int] = field(default_factory=dict)
    sto_warm: set[int] = field(default_factory=set)
    pc: int = 0
    gas: int = 0
    trap: bool = False
    halted: bool = False
    returndata: bytes = b""
    returndatasize: int = 0


@dataclass(frozen=True)
class EvmContext:
    """Immutable per-call inputs (SCHEMA.md §4).

    ``calldatasize=None`` means infer from ``len(calldata)``.
    ``codesize`` is set by ``run()``; callers need not supply it.
    """

    caller: int = 0
    callvalue: int = 0
    origin: int = 0
    gasprice: int = 0
    calldata: bytes = b""
    calldatasize: int | None = None
    blocknumber: int = 0
    timestamp: int = 0
    prevrandao: int = 0
    gaslimit: int = 30_000_000
    coinbase: int = 0
    basefee: int = 0
    chainid: int = 1
    this_address: int = 0
    codesize: int = 0

    def effective_calldatasize(self) -> int:
        return len(self.calldata) if self.calldatasize is None else self.calldatasize


@dataclass
class StepRecord:
    """Shadow-mode per-instruction access log (SCHEMA.md §P2 shadow mode).

    Populated only when ``shadow=True`` is passed to ``step()`` or ``run()``.
    """

    pc: int
    opcode: int
    stack_reads: list[int] = field(default_factory=list)
    stack_writes: list[int] = field(default_factory=list)
    mem_reads: list[tuple[int, int]] = field(default_factory=list)
    mem_writes: list[tuple[int, int]] = field(default_factory=list)
    sto_reads: list[tuple[int, int]] = field(default_factory=list)
    sto_writes: list[tuple[int, int]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal memory helpers
# ---------------------------------------------------------------------------


def _mem_read32(mem: dict[int, int], offset: int) -> int:
    val = 0
    for i in range(32):
        val = (val << 8) | mem.get(offset + i, 0)
    return val


def _mem_write32(mem: dict[int, int], offset: int, value: int) -> None:
    value &= _MASK256
    for i in range(31, -1, -1):
        mem[offset + i] = value & _MASK8
        value >>= 8


def _mem_slice(mem: dict[int, int], offset: int, length: int) -> bytes:
    return bytes(mem.get(offset + i, 0) for i in range(length))


def _calldata_read32(ctx: EvmContext, offset: int) -> int:
    """Read 32 bytes from calldata, zero-padding past end (§9)."""
    cd = ctx.calldata
    val = 0
    for i in range(32):
        idx = offset + i
        val = (val << 8) | (cd[idx] if idx < len(cd) else 0)
    return val


# ---------------------------------------------------------------------------
# Single-step executor
# ---------------------------------------------------------------------------


def step(
    state: MachineState,
    bytecode: bytes,
    ctx: EvmContext,
    jumpdest_table: frozenset[int],
    *,
    shadow: bool = False,
) -> StepRecord | None:
    """Execute the instruction at ``state.pc``, mutating ``state`` in place.

    Returns a ``StepRecord`` when ``shadow=True``, else ``None``.
    Returns ``None`` immediately when already halted (no-op for subsequent steps).
    """
    if state.halted:
        return None

    n_code = len(bytecode)
    pc = state.pc
    op = bytecode[pc] if pc < n_code else 0xFE  # off-end → INVALID

    rec: StepRecord | None = StepRecord(pc=pc, opcode=op) if shadow else None

    # -- stack helpers with optional shadow logging --

    def pop() -> int:
        v = state.stack.pop()
        if rec is not None:
            rec.stack_reads.append(v)
        return v

    def push(v: int) -> None:
        w = v & _MASK256
        state.stack.append(w)
        if rec is not None:
            rec.stack_writes.append(w)

    # -- gas helper: deduct cost; on failure set trap+halted and return False --

    def charge(cost: int) -> bool:
        if state.gas < cost:
            state.trap = True
            state.halted = True
            return False
        state.gas -= cost
        return True

    # -- memory expansion helper: adds expansion cost and updates mem_words --

    def mem_expand(offset: int, size: int) -> bool:
        new_words = _new_mem_words(state.mem_words, offset, size)
        if new_words > state.mem_words:
            delta = _mem_cost(new_words) - _mem_cost(state.mem_words)
            if not charge(delta):
                return False
            state.mem_words = new_words
        return True

    def trap_halt() -> StepRecord | None:
        state.trap = True
        state.halted = True
        return rec

    sp = len(state.stack)

    # ==================================================================
    # STOP (0x00) — handled first; also appears in §12.7
    # ==================================================================
    if op == 0x00:
        state.halted = True
        state.trap = False
        return rec

    # ==================================================================
    # Arithmetic (§12.1)
    # ==================================================================
    elif op == 0x01:  # ADD
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        a, b = pop(), pop()
        push(_u256(a + b))
        state.pc = pc + 1

    elif op == 0x02:  # MUL
        if sp < 2:
            return trap_halt()
        if not charge(5):
            return rec
        a, b = pop(), pop()
        push(_u256(a * b))
        state.pc = pc + 1

    elif op == 0x03:  # SUB
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        a, b = pop(), pop()
        push(_u256(a - b))
        state.pc = pc + 1

    elif op == 0x04:  # DIV
        if sp < 2:
            return trap_halt()
        if not charge(5):
            return rec
        a, b = pop(), pop()
        push(0 if b == 0 else a // b)
        state.pc = pc + 1

    elif op == 0x05:  # SDIV
        if sp < 2:
            return trap_halt()
        if not charge(5):
            return rec
        a, b = _s256(pop()), _s256(pop())
        if b == 0:
            push(0)
        elif a == -(1 << 255) and b == -1:
            push(_from_s256(-(1 << 255)))  # overflow → min_int
        else:
            sign = -1 if (a < 0) ^ (b < 0) else 1
            push(_from_s256(sign * (abs(a) // abs(b))))
        state.pc = pc + 1

    elif op == 0x06:  # MOD
        if sp < 2:
            return trap_halt()
        if not charge(5):
            return rec
        a, b = pop(), pop()
        push(0 if b == 0 else a % b)
        state.pc = pc + 1

    elif op == 0x07:  # SMOD
        if sp < 2:
            return trap_halt()
        if not charge(5):
            return rec
        a, b = _s256(pop()), _s256(pop())
        if b == 0:
            push(0)
        else:
            sign = -1 if a < 0 else 1
            push(_from_s256(sign * (abs(a) % abs(b))))
        state.pc = pc + 1

    elif op == 0x08:  # ADDMOD
        if sp < 3:
            return trap_halt()
        if not charge(8):
            return rec
        a, b, N = pop(), pop(), pop()
        push(0 if N == 0 else (a + b) % N)  # Python int; no 2^256 overflow
        state.pc = pc + 1

    elif op == 0x09:  # MULMOD
        if sp < 3:
            return trap_halt()
        if not charge(8):
            return rec
        a, b, N = pop(), pop(), pop()
        push(0 if N == 0 else (a * b) % N)
        state.pc = pc + 1

    elif op == 0x0A:  # EXP
        if sp < 2:
            return trap_halt()
        base, exp_val = pop(), pop()
        if not charge(10 + 50 * _byte_len(exp_val)):
            return rec
        push(pow(base, exp_val, 1 << 256) if exp_val else 1)
        state.pc = pc + 1

    elif op == 0x0B:  # SIGNEXTEND
        if sp < 2:
            return trap_halt()
        if not charge(5):
            return rec
        b, x = pop(), pop()
        if b < 31:
            sign_bit = 1 << (b * 8 + 7)
            mask = sign_bit - 1
            if x & sign_bit:
                push(_MASK256 & (~mask | x))
            else:
                push(x & mask)
        else:
            push(x & _MASK256)
        state.pc = pc + 1

    # ==================================================================
    # Comparison and bitwise (§12.2)
    # ==================================================================
    elif op == 0x10:  # LT
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        a, b = pop(), pop()
        push(1 if a < b else 0)
        state.pc = pc + 1

    elif op == 0x11:  # GT
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        a, b = pop(), pop()
        push(1 if a > b else 0)
        state.pc = pc + 1

    elif op == 0x12:  # SLT
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        a, b = _s256(pop()), _s256(pop())
        push(1 if a < b else 0)
        state.pc = pc + 1

    elif op == 0x13:  # SGT
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        a, b = _s256(pop()), _s256(pop())
        push(1 if a > b else 0)
        state.pc = pc + 1

    elif op == 0x14:  # EQ
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        a, b = pop(), pop()
        push(1 if a == b else 0)
        state.pc = pc + 1

    elif op == 0x15:  # ISZERO
        if sp < 1:
            return trap_halt()
        if not charge(3):
            return rec
        push(1 if pop() == 0 else 0)
        state.pc = pc + 1

    elif op == 0x16:  # AND
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        push(pop() & pop())
        state.pc = pc + 1

    elif op == 0x17:  # OR
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        push(pop() | pop())
        state.pc = pc + 1

    elif op == 0x18:  # XOR
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        push(pop() ^ pop())
        state.pc = pc + 1

    elif op == 0x19:  # NOT
        if sp < 1:
            return trap_halt()
        if not charge(3):
            return rec
        push(_MASK256 ^ pop())
        state.pc = pc + 1

    elif op == 0x1A:  # BYTE  — byte 0 = MSB (§12.2)
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        i, x = pop(), pop()
        push(0 if i >= 32 else (x >> ((31 - i) * 8)) & _MASK8)
        state.pc = pc + 1

    elif op == 0x1B:  # SHL (logical left; shift >= 256 → 0)
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        shift, val = pop(), pop()
        push(0 if shift >= 256 else _u256(val << shift))
        state.pc = pc + 1

    elif op == 0x1C:  # SHR (logical right; shift >= 256 → 0)
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        shift, val = pop(), pop()
        push(0 if shift >= 256 else val >> shift)
        state.pc = pc + 1

    elif op == 0x1D:  # SAR (arithmetic right; shift >= 256 → 0 or all-ones)
        if sp < 2:
            return trap_halt()
        if not charge(3):
            return rec
        shift, val = pop(), pop()
        signed = _s256(val)
        if shift >= 256:
            push(_MASK256 if signed < 0 else 0)
        else:
            push(_from_s256(signed >> shift))
        state.pc = pc + 1

    # ==================================================================
    # Environment (§12.3)
    # ==================================================================
    elif op == 0x30:  # ADDRESS
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.this_address)
        state.pc = pc + 1

    elif op == 0x32:  # ORIGIN
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.origin)
        state.pc = pc + 1

    elif op == 0x33:  # CALLER
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.caller)
        state.pc = pc + 1

    elif op == 0x34:  # CALLVALUE
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.callvalue)
        state.pc = pc + 1

    elif op == 0x35:  # CALLDATALOAD
        if sp < 1:
            return trap_halt()
        if not charge(3):
            return rec
        push(_calldata_read32(ctx, pop()))
        state.pc = pc + 1

    elif op == 0x36:  # CALLDATASIZE
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.effective_calldatasize())
        state.pc = pc + 1

    elif op == 0x37:  # CALLDATACOPY
        if sp < 3:
            return trap_halt()
        dest, src, length = pop(), pop(), pop()
        word_cost = 3 * ((length + 31) // 32) if length else 0
        if not charge(3 + word_cost):
            return rec
        if not mem_expand(dest, length):
            return rec
        cd, cds = ctx.calldata, ctx.effective_calldatasize()
        for i in range(length):
            idx = src + i
            b = (cd[idx] if idx < len(cd) else 0) if idx < cds else 0
            state.mem[dest + i] = b
            if rec is not None:
                rec.mem_writes.append((dest + i, b))
        state.pc = pc + 1

    elif op == 0x38:  # CODESIZE
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.codesize)
        state.pc = pc + 1

    elif op == 0x39:  # CODECOPY
        if sp < 3:
            return trap_halt()
        dest, src, length = pop(), pop(), pop()
        word_cost = 3 * ((length + 31) // 32) if length else 0
        if not charge(3 + word_cost):
            return rec
        if not mem_expand(dest, length):
            return rec
        for i in range(length):
            b = bytecode[src + i] if (src + i) < n_code else 0
            state.mem[dest + i] = b
            if rec is not None:
                rec.mem_writes.append((dest + i, b))
        state.pc = pc + 1

    elif op == 0x3A:  # GASPRICE
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.gasprice)
        state.pc = pc + 1

    elif op == 0x3D:  # RETURNDATASIZE
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(state.returndatasize)
        state.pc = pc + 1

    elif op == 0x3E:  # RETURNDATACOPY — P3+
        return trap_halt()

    elif op == 0x46:  # CHAINID
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.chainid)
        state.pc = pc + 1

    elif op == 0x48:  # BASEFEE
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.basefee)
        state.pc = pc + 1

    # ==================================================================
    # Block (§12.4)
    # ==================================================================
    elif op == 0x40:  # BLOCKHASH (uninterpreted — concrete returns 0)
        if sp < 1:
            return trap_halt()
        if not charge(20):
            return rec
        pop()
        push(0)
        state.pc = pc + 1

    elif op == 0x41:  # COINBASE
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.coinbase)
        state.pc = pc + 1

    elif op == 0x42:  # TIMESTAMP
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.timestamp)
        state.pc = pc + 1

    elif op == 0x43:  # NUMBER
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.blocknumber)
        state.pc = pc + 1

    elif op == 0x44:  # DIFFICULTY / PREVRANDAO
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.prevrandao)
        state.pc = pc + 1

    elif op == 0x45:  # GASLIMIT
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(ctx.gaslimit)
        state.pc = pc + 1

    # ==================================================================
    # Stack, memory, storage (§12.5)
    # ==================================================================
    elif op == 0x50:  # POP
        if sp < 1:
            return trap_halt()
        if not charge(2):
            return rec
        pop()
        state.pc = pc + 1

    elif op == 0x51:  # MLOAD
        if sp < 1:
            return trap_halt()
        offset = pop()
        if not charge(3):
            return rec
        if not mem_expand(offset, 32):
            return rec
        val = _mem_read32(state.mem, offset)
        if rec is not None:
            for i in range(32):
                rec.mem_reads.append((offset + i, state.mem.get(offset + i, 0)))
        push(val)
        state.pc = pc + 1

    elif op == 0x52:  # MSTORE — TOS=offset, 2nd=value
        if sp < 2:
            return trap_halt()
        offset, value = pop(), pop()
        if not charge(3):
            return rec
        if not mem_expand(offset, 32):
            return rec
        _mem_write32(state.mem, offset, value)
        if rec is not None:
            for i in range(32):
                rec.mem_writes.append((offset + i, state.mem.get(offset + i, 0)))
        state.pc = pc + 1

    elif op == 0x53:  # MSTORE8 — TOS=offset, 2nd=value (low byte stored)
        if sp < 2:
            return trap_halt()
        offset, value = pop(), pop()
        if not charge(3):
            return rec
        if not mem_expand(offset, 1):
            return rec
        b = value & _MASK8
        state.mem[offset] = b
        if rec is not None:
            rec.mem_writes.append((offset, b))
        state.pc = pc + 1

    elif op == 0x54:  # SLOAD — EIP-2929 gas (§8)
        if sp < 1:
            return trap_halt()
        slot = pop()
        gas_cost = 100 if slot in state.sto_warm else 2100
        if not charge(gas_cost):
            return rec
        state.sto_warm.add(slot)
        val = state.sto.get(slot, 0)
        if rec is not None:
            rec.sto_reads.append((slot, val))
        push(val)
        state.pc = pc + 1

    elif op == 0x55:  # SSTORE — EIP-2929/3529 gas (§10.4)
        if sp < 2:
            return trap_halt()
        slot, new_val = pop(), pop()
        warm = slot in state.sto_warm
        current = state.sto.get(slot, 0)
        original = state.sto_original.get(slot, 0)
        if warm:
            gas_cost = 100 if new_val == current else (2900 if current == original else 100)
        else:
            gas_cost = 2200 if new_val == current else (20000 if current == original else 2200)
        if not charge(gas_cost):
            return rec
        state.sto_warm.add(slot)
        if rec is not None:
            rec.sto_reads.append((slot, current))
            rec.sto_writes.append((slot, new_val & _MASK256))
        state.sto[slot] = new_val & _MASK256
        state.pc = pc + 1

    elif op == 0x59:  # MSIZE
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(state.mem_words * 32)
        state.pc = pc + 1

    elif op == 0x5A:  # GAS — remaining gas *after* this opcode's cost
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(state.gas)
        state.pc = pc + 1

    elif op == 0x5B:  # JUMPDEST
        if not charge(1):
            return rec
        state.pc = pc + 1

    elif op == 0x5F:  # PUSH0 (EIP-3855, Shanghai+)
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(0)
        state.pc = pc + 1

    elif 0x60 <= op <= 0x7F:  # PUSH1..PUSH32
        if sp >= 1024:
            return trap_halt()
        if not charge(3):
            return rec
        imm_len = op - 0x60 + 1
        raw = bytecode[pc + 1 : pc + 1 + imm_len]
        if len(raw) < imm_len:
            raw = raw + bytes(imm_len - len(raw))
        push(int.from_bytes(raw, "big"))
        state.pc = pc + 1 + imm_len

    elif 0x80 <= op <= 0x8F:  # DUP1..DUP16
        n = op - 0x80 + 1  # DUP1: n=1 → duplicates stack[-1]
        if sp < n or sp >= 1024:
            return trap_halt()
        if not charge(3):
            return rec
        push(state.stack[-n])
        state.pc = pc + 1

    elif 0x90 <= op <= 0x9F:  # SWAP1..SWAP16
        n = op - 0x90 + 1  # SWAP1: n=1 → swap TOS with stack[-2]
        if sp < n + 1:
            return trap_halt()
        if not charge(3):
            return rec
        state.stack[-1], state.stack[-(n + 1)] = state.stack[-(n + 1)], state.stack[-1]
        state.pc = pc + 1

    # ==================================================================
    # Control flow (§12.6)
    # ==================================================================
    elif op == 0x56:  # JUMP
        if sp < 1:
            return trap_halt()
        if not charge(8):
            return rec
        dest = pop()
        if dest not in jumpdest_table:
            return trap_halt()
        state.pc = dest

    elif op == 0x57:  # JUMPI
        if sp < 2:
            return trap_halt()
        if not charge(10):
            return rec
        dest, cond = pop(), pop()
        if cond != 0:
            if dest not in jumpdest_table:
                return trap_halt()
            state.pc = dest
        else:
            state.pc = pc + 1

    elif op == 0x58:  # PC — value of PC *before* this instruction (§12.6)
        if sp >= 1024:
            return trap_halt()
        if not charge(2):
            return rec
        push(pc)
        state.pc = pc + 1

    # ==================================================================
    # Termination (§12.7)
    # ==================================================================
    elif op == 0xF3:  # RETURN — TOS=offset, 2nd=length
        if sp < 2:
            return trap_halt()
        offset, length = pop(), pop()
        if not mem_expand(offset, length):
            return rec
        state.returndata = _mem_slice(state.mem, offset, length)
        state.returndatasize = length
        state.halted = True
        state.trap = False
        return rec

    elif op == 0xFD:  # REVERT — TOS=offset, 2nd=length
        if sp < 2:
            return trap_halt()
        offset, length = pop(), pop()
        if not mem_expand(offset, length):
            return rec
        state.returndata = _mem_slice(state.mem, offset, length)
        state.returndatasize = length
        state.halted = True
        state.trap = True
        return rec

    elif op == 0xFE:  # INVALID — consumes all remaining gas
        state.gas = 0
        return trap_halt()

    # LOG0..LOG4 (0xa0–0xa4) — P10, out of scope
    elif 0xA0 <= op <= 0xA4:
        return trap_halt()

    # CALL family / CREATE / SELFDESTRUCT — P11
    elif op in (0xF0, 0xF1, 0xF2, 0xF4, 0xF5, 0xFA, 0xFF):
        return trap_halt()

    # KECCAK256 (0x20) — P2
    elif op == 0x20:
        return trap_halt()

    # SELFBALANCE (0x47) / EXTCODE* / BALANCE — P11
    elif op in (0x31, 0x3B, 0x3C, 0x3F, 0x47):
        return trap_halt()

    # Everything else is out-of-scope
    else:
        return trap_halt()

    return rec


# ---------------------------------------------------------------------------
# High-level runner
# ---------------------------------------------------------------------------


def run(
    bytecode: bytes,
    ctx: EvmContext | None = None,
    *,
    initial_gas: int = 1_000_000,
    initial_sto: dict[int, int] | None = None,
    initial_sto_warm: set[int] | None = None,
    max_steps: int = 1_000,
    shadow: bool = False,
) -> tuple[MachineState, list[StepRecord]]:
    """Execute bytecode to termination (or ``max_steps`` instruction limit).

    Returns ``(final_state, records)`` where ``records`` is populated only
    when ``shadow=True``.  The ``ctx.codesize`` field is always overwritten
    with ``len(bytecode)`` so callers need not set it.
    """
    if ctx is None:
        ctx = EvmContext()
    ctx = EvmContext(
        caller=ctx.caller,
        callvalue=ctx.callvalue,
        origin=ctx.origin,
        gasprice=ctx.gasprice,
        calldata=ctx.calldata,
        calldatasize=ctx.calldatasize,
        blocknumber=ctx.blocknumber,
        timestamp=ctx.timestamp,
        prevrandao=ctx.prevrandao,
        gaslimit=ctx.gaslimit,
        coinbase=ctx.coinbase,
        basefee=ctx.basefee,
        chainid=ctx.chainid,
        this_address=ctx.this_address,
        codesize=len(bytecode),
    )

    sto = dict(initial_sto) if initial_sto else {}
    state = MachineState(
        gas=initial_gas,
        sto=sto,
        sto_original=dict(sto),
        sto_warm=set(initial_sto_warm) if initial_sto_warm else set(),
    )

    jdt = compute_jumpdest_table(bytecode)
    records: list[StepRecord] = []

    for _ in range(max_steps):
        if state.halted:
            break
        rec = step(state, bytecode, ctx, jdt, shadow=shadow)
        if rec is not None:
            records.append(rec)

    return state, records
