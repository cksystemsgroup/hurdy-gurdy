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
    0x50 POP
    0x60 PUSH1
    0x61 PUSH2
    0x63 PUSH4
    0x80 DUP1
"""

from __future__ import annotations

# In-scope opcode bytes.
STOP = 0x00
ADD = 0x01
MUL = 0x02
SUB = 0x03
POP = 0x50
PUSH1 = 0x60
PUSH2 = 0x61
PUSH4 = 0x63
DUP1 = 0x80

# The in-scope push immediates and their inline-immediate byte width. A PUSH{n}
# occupies ``n + 1`` bytes (the opcode plus an ``n``-byte big-endian operand);
# this map is the single source of truth both the interpreter and the
# translator key on.
PUSH_WIDTH: dict[int, int] = {PUSH1: 1, PUSH2: 2, PUSH4: 4}

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


def push1(value: int) -> bytes:
    """``PUSH1 value`` — push a single byte (0..255) as a 256-bit word."""
    if not 0 <= value <= 0xFF:
        raise ValueError(f"PUSH1 immediate out of range: {value}")
    return bytes((PUSH1, value & 0xFF))


def push2(value: int) -> bytes:
    """``PUSH2 value`` — push a 2-byte big-endian immediate as a 256-bit word."""
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"PUSH2 immediate out of range: {value}")
    return bytes((PUSH2,)) + value.to_bytes(2, "big")


def push4(value: int) -> bytes:
    """``PUSH4 value`` — push a 4-byte big-endian immediate as a 256-bit word."""
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"PUSH4 immediate out of range: {value}")
    return bytes((PUSH4,)) + value.to_bytes(4, "big")


def add() -> bytes:
    """``ADD`` — pop ``a``, pop ``b``, push ``(a + b) mod 2**256``."""
    return bytes((ADD,))


def mul() -> bytes:
    """``MUL`` — pop ``a``, pop ``b``, push ``(a * b) mod 2**256``."""
    return bytes((MUL,))


def sub() -> bytes:
    """``SUB`` — pop ``a``, pop ``b``, push ``(a - b) mod 2**256`` (top minus next)."""
    return bytes((SUB,))


def pop() -> bytes:
    """``POP`` — discard the top stack item."""
    return bytes((POP,))


def dup1() -> bytes:
    """``DUP1`` — duplicate the top stack item."""
    return bytes((DUP1,))


def stop() -> bytes:
    """``STOP`` — halt successfully."""
    return bytes((STOP,))


def program(*fragments: bytes) -> bytes:
    """Concatenate opcode fragments into a bytecode program."""
    return b"".join(fragments)
