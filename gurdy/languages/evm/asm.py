"""Minimal EVM bytecode encoders for tests and coverage probes.

One helper per in-scope opcode. The EVM is a byte-addressed bytecode machine:
``pc`` indexes the byte stream, and ``PUSH1`` carries its 1-byte immediate
*inline* (the byte after the opcode), so it occupies two bytes. The encoders
return a ``bytes`` fragment; concatenate them to form a program.

Opcode bytes (Ethereum Yellow Paper / London + Shanghai ``PUSH0``):

    0x00 STOP
    0x01 ADD
    0x02 MUL
    0x03 SUB
    0x04 DIV
    0x05 SDIV
    0x06 MOD
    0x07 SMOD
    0x50 POP
    0x51 MLOAD                 (pop offset; push the 32-byte BE word at mem[off..])
    0x52 MSTORE                (pop offset, value; write the 32-byte BE value)
    0x53 MSTORE8               (pop offset, value; write value's low byte)
    0x60..0x7F PUSH1..PUSH32   (PUSH{n} carries an n-byte inline immediate)
    0x80..0x8F DUP1..DUP16     (duplicate the n-th item onto the top)
    0x90..0x9F SWAP1..SWAP16   (swap the top with the (n+1)-th item)
"""

from __future__ import annotations

# In-scope opcode bytes.
STOP = 0x00
ADD = 0x01
MUL = 0x02
SUB = 0x03
DIV = 0x04
SDIV = 0x05
MOD = 0x06
SMOD = 0x07
POP = 0x50
MLOAD = 0x51
MSTORE = 0x52
MSTORE8 = 0x53
PUSH1 = 0x60
PUSH2 = 0x61
PUSH4 = 0x63
PUSH32 = 0x7F
DUP1 = 0x80
DUP16 = 0x8F
SWAP1 = 0x90
SWAP16 = 0x9F

# The push immediates ``PUSH1..PUSH32`` (0x60..0x7F) and their inline-immediate
# byte width: a ``PUSH{n}`` occupies ``n + 1`` bytes (the opcode plus an
# ``n``-byte big-endian operand). This map is the single source of truth both the
# interpreter and the translator key on — the full push family in one place, so
# adding a width is a data change, not a code change. (``PUSH0`` (0x5F) carries
# no immediate and stays out of scope; it is not in this map.)
PUSH_WIDTH: dict[int, int] = {0x60 + (n - 1): n for n in range(1, 33)}

# ``DUP{n}`` (0x80..0x8F) duplicates the n-th item from the top onto the top;
# ``SWAP{n}`` (0x90..0x9F) swaps the top with the (n+1)-th item. The opcode byte
# encodes ``n`` directly: ``DUP{n} = 0x80 + (n-1)``, ``SWAP{n} = 0x90 + (n-1)``.
# These maps are the single source of truth the interpreter and translator key on.
DUP_N: dict[int, int] = {DUP1 + (n - 1): n for n in range(1, 17)}
SWAP_N: dict[int, int] = {SWAP1 + (n - 1): n for n in range(1, 17)}

# The spec-derived EVM opcode names (London baseline + Shanghai ``PUSH0``), so a
# typed ``unsupported: evm:<MNEMONIC>`` abort names the real opcode rather than a
# bare byte. Undefined byte values fall back to ``0x..`` in ``opcode_name``.
OPCODE_NAMES: dict[int, str] = {
    0x00: "STOP", 0x01: "ADD", 0x02: "MUL", 0x03: "SUB", 0x04: "DIV",
    0x05: "SDIV", 0x06: "MOD", 0x07: "SMOD", 0x08: "ADDMOD", 0x09: "MULMOD",
    0x0A: "EXP", 0x0B: "SIGNEXTEND",
    0x10: "LT", 0x11: "GT", 0x12: "SLT", 0x13: "SGT", 0x14: "EQ",
    0x15: "ISZERO", 0x16: "AND", 0x17: "OR", 0x18: "XOR", 0x19: "NOT",
    0x1A: "BYTE", 0x1B: "SHL", 0x1C: "SHR", 0x1D: "SAR",
    0x20: "KECCAK256",
    0x30: "ADDRESS", 0x31: "BALANCE", 0x32: "ORIGIN", 0x33: "CALLER",
    0x34: "CALLVALUE", 0x35: "CALLDATALOAD", 0x36: "CALLDATASIZE",
    0x37: "CALLDATACOPY", 0x38: "CODESIZE", 0x39: "CODECOPY", 0x3A: "GASPRICE",
    0x3B: "EXTCODESIZE", 0x3C: "EXTCODECOPY", 0x3D: "RETURNDATASIZE",
    0x3E: "RETURNDATACOPY", 0x3F: "EXTCODEHASH",
    0x40: "BLOCKHASH", 0x41: "COINBASE", 0x42: "TIMESTAMP", 0x43: "NUMBER",
    0x44: "PREVRANDAO", 0x45: "GASLIMIT", 0x46: "CHAINID", 0x47: "SELFBALANCE",
    0x48: "BASEFEE",
    0x50: "POP", 0x51: "MLOAD", 0x52: "MSTORE", 0x53: "MSTORE8", 0x54: "SLOAD",
    0x55: "SSTORE", 0x56: "JUMP", 0x57: "JUMPI", 0x58: "PC", 0x59: "MSIZE",
    0x5A: "GAS", 0x5B: "JUMPDEST", 0x5F: "PUSH0",
    0xA0: "LOG0", 0xA1: "LOG1", 0xA2: "LOG2", 0xA3: "LOG3", 0xA4: "LOG4",
    0xF0: "CREATE", 0xF1: "CALL", 0xF2: "CALLCODE", 0xF3: "RETURN",
    0xF4: "DELEGATECALL", 0xF5: "CREATE2", 0xFA: "STATICCALL",
    0xFD: "REVERT", 0xFE: "INVALID", 0xFF: "SELFDESTRUCT",
}
for _n in range(1, 33):       # PUSH1..PUSH32 (0x60..0x7F)
    OPCODE_NAMES[0x5F + _n] = f"PUSH{_n}"
for _n in range(1, 17):       # DUP1..DUP16 (0x80..0x8F), SWAP1..SWAP16 (0x90..0x9F)
    OPCODE_NAMES[0x7F + _n] = f"DUP{_n}"
    OPCODE_NAMES[0x8F + _n] = f"SWAP{_n}"


def opcode_name(op: int) -> str:
    """The mnemonic for an opcode byte, or ``0x..`` for an undefined byte."""
    return OPCODE_NAMES.get(op, f"0x{op:02x}")


def pushn(n: int, value: int) -> bytes:
    """``PUSH{n} value`` — push an ``n``-byte big-endian immediate (``1 ≤ n ≤
    32``) as a 256-bit word. The opcode byte is ``0x60 + (n-1)`` and ``value``
    must fit in ``n`` bytes; the generic encoder ``push1``/``push2``/``push4``
    specialize."""
    if not 1 <= n <= 32:
        raise ValueError(f"PUSH width out of range: {n}")
    if not 0 <= value < (1 << (8 * n)):
        raise ValueError(f"PUSH{n} immediate out of range: {value}")
    return bytes((0x60 + (n - 1),)) + value.to_bytes(n, "big")


def push1(value: int) -> bytes:
    """``PUSH1 value`` — push a single byte (0..255) as a 256-bit word."""
    return pushn(1, value)


def push2(value: int) -> bytes:
    """``PUSH2 value`` — push a 2-byte big-endian immediate as a 256-bit word."""
    return pushn(2, value)


def push4(value: int) -> bytes:
    """``PUSH4 value`` — push a 4-byte big-endian immediate as a 256-bit word."""
    return pushn(4, value)


def add() -> bytes:
    """``ADD`` — pop ``a``, pop ``b``, push ``(a + b) mod 2**256``."""
    return bytes((ADD,))


def mul() -> bytes:
    """``MUL`` — pop ``a``, pop ``b``, push ``(a * b) mod 2**256``."""
    return bytes((MUL,))


def sub() -> bytes:
    """``SUB`` — pop ``a``, pop ``b``, push ``(a - b) mod 2**256`` (top minus next)."""
    return bytes((SUB,))


def div() -> bytes:
    """``DIV`` — unsigned: pop ``a`` (top), pop ``b`` (next), push ``a // b``, with
    the defining special case ``b == 0 -> 0`` (not a trap)."""
    return bytes((DIV,))


def mod() -> bytes:
    """``MOD`` — unsigned: pop ``a`` (top), pop ``b`` (next), push ``a % b``, with
    the defining special case ``b == 0 -> 0`` (not a trap)."""
    return bytes((MOD,))


def sdiv() -> bytes:
    """``SDIV`` — two's-complement signed division: pop ``a`` (top), pop ``b``
    (next), push the truncating (C-style) quotient, with the EVM special cases
    ``b == 0 -> 0`` and ``a == INT_MIN ∧ b == -1 -> INT_MIN`` (it wraps, no trap)."""
    return bytes((SDIV,))


def smod() -> bytes:
    """``SMOD`` — two's-complement signed modulo: pop ``a`` (top), pop ``b``
    (next), push the truncating remainder (taking the **sign of the dividend**),
    with the defining special case ``b == 0 -> 0`` (not a trap)."""
    return bytes((SMOD,))


def pop() -> bytes:
    """``POP`` — discard the top stack item."""
    return bytes((POP,))


def mload() -> bytes:
    """``MLOAD`` — pop a byte ``offset`` (top), push the 32-byte big-endian word
    read from ``mem[offset .. offset+31]`` (zero-filled where never written)."""
    return bytes((MLOAD,))


def mstore() -> bytes:
    """``MSTORE`` — pop a byte ``offset`` (top), pop a ``value`` (next); write the
    32-byte big-endian encoding of ``value`` to ``mem[offset .. offset+31]``."""
    return bytes((MSTORE,))


def mstore8() -> bytes:
    """``MSTORE8`` — pop a byte ``offset`` (top), pop a ``value`` (next); write
    the **low byte** of ``value`` to ``mem[offset]``."""
    return bytes((MSTORE8,))


def dupn(n: int) -> bytes:
    """``DUP{n}`` — duplicate the n-th stack item (1-indexed from the top) onto
    the top (``1 ≤ n ≤ 16``); ``DUP1`` is the top itself."""
    if not 1 <= n <= 16:
        raise ValueError(f"DUP index out of range: {n}")
    return bytes((DUP1 + (n - 1),))


def dup1() -> bytes:
    """``DUP1`` — duplicate the top stack item."""
    return dupn(1)


def swapn(n: int) -> bytes:
    """``SWAP{n}`` — swap the top stack item with the (n+1)-th item
    (``1 ≤ n ≤ 16``); ``SWAP1`` swaps the top two."""
    if not 1 <= n <= 16:
        raise ValueError(f"SWAP index out of range: {n}")
    return bytes((SWAP1 + (n - 1),))


def stop() -> bytes:
    """``STOP`` — halt successfully."""
    return bytes((STOP,))


def program(*fragments: bytes) -> bytes:
    """Concatenate opcode fragments into a bytecode program."""
    return b"".join(fragments)
