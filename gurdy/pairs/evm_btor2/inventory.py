"""The construct-coverage inventory for evm-btor2 (BENCHMARKS.md §2).

The denominator is the *spec-derived* EVM opcode set (the agent does not choose
it): every defined opcode of the London + Shanghai (``PUSH0``) baseline. A
probe is a minimal program exercising the opcode; a construct is *covered* iff
its probe translates without an ``Unsupported`` abort. The slice covers the full
push family ``PUSH1`` .. ``PUSH32`` and ``PUSH0``, ``ADD`` / ``MUL`` / ``SUB`` /
``DIV`` / ``MOD`` and the signed ``SDIV`` / ``SMOD``, ``POP``, the duplications
``DUP1`` .. ``DUP16``, the swaps ``SWAP1`` .. ``SWAP16``, ``STOP``, the
byte-addressed memory ops ``MLOAD`` / ``MSTORE`` / ``MSTORE8``, the persistent
storage ops ``SLOAD`` / ``SSTORE``, the control-flow ops ``JUMP`` / ``JUMPI`` /
``JUMPDEST`` / ``PC``, and the terminal/halt ops ``RETURN`` / ``REVERT`` /
``INVALID``; every other opcode (``MSIZE``, the environment/block opcodes,
``CALL``/``CREATE``/``LOG0..4``, …) lands in the ``unsupported`` histogram
(BENCHMARKS.md §3) — the honest, visible gap that keeps this pair ``partial``.

``coverage()`` measures how many translate without aborting.
"""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from ...languages.evm import asm
from .translate import translate


def _p(*fragments: bytes) -> dict:
    """A probe program of opcode fragments."""
    return {"code": asm.program(*fragments)}


def _probe_for(op: int) -> dict:
    """A minimal program exercising opcode ``op``. In-scope opcodes are framed
    with the operands they consume; every other opcode is emitted bare (its
    translation aborts on decode, before any operand is consulted)."""
    if op in asm.PUSH_WIDTH:                        # PUSH1 .. PUSH32
        n = asm.PUSH_WIDTH[op]
        return _p(asm.pushn(n, 1), asm.stop())
    if op == asm.PUSH0:                             # PUSH0: push the constant 0
        return _p(asm.push0(), asm.stop())
    if op == asm.ADD:
        return _p(asm.push1(2), asm.push1(3), asm.add(), asm.stop())
    if op == asm.MUL:
        return _p(asm.push1(2), asm.push1(3), asm.mul(), asm.stop())
    if op == asm.SUB:
        return _p(asm.push1(2), asm.push1(3), asm.sub(), asm.stop())
    if op == asm.DIV:
        return _p(asm.push1(2), asm.push1(6), asm.div(), asm.stop())
    if op == asm.MOD:
        return _p(asm.push1(2), asm.push1(7), asm.mod(), asm.stop())
    if op == asm.SDIV:
        return _p(asm.push1(2), asm.push1(6), asm.sdiv(), asm.stop())
    if op == asm.SMOD:
        return _p(asm.push1(3), asm.push1(7), asm.smod(), asm.stop())
    if op == asm.AND:                               # AND: 0xFC & 0x3F = 0x3C
        return _p(asm.push1(0xFC), asm.push1(0x3F), asm.and_(), asm.stop())
    if op == asm.OR:                                # OR: 0xF0 | 0x0F = 0xFF
        return _p(asm.push1(0xF0), asm.push1(0x0F), asm.or_(), asm.stop())
    if op == asm.XOR:                               # XOR: 0xFF ^ 0x0F = 0xF0
        return _p(asm.push1(0xFF), asm.push1(0x0F), asm.xor_(), asm.stop())
    if op == asm.NOT:                               # NOT: ~0x00 = 2**256 - 1
        return _p(asm.push1(0x00), asm.not_(), asm.stop())
    if op == asm.ISZERO:                            # ISZERO: 0 -> 1 and 0x05 -> 0
        # Exercise both outputs so a wrong lowering (always-0, always-1, or
        # identity) diverges: iszero(0) = 1, then iszero(5) = 0.
        return _p(asm.push1(0x00), asm.iszero(),
                  asm.push1(0x05), asm.iszero(), asm.stop())
    if op == asm.POP:
        return _p(asm.push1(7), asm.pop(), asm.stop())
    if op == asm.MLOAD:                             # MLOAD: offset on top
        return _p(asm.push1(0), asm.mload(), asm.stop())
    if op == asm.MSTORE:                            # MSTORE: push value, then offset
        return _p(asm.push1(0xAB), asm.push1(0), asm.mstore(), asm.stop())
    if op == asm.MSTORE8:                           # MSTORE8: push value, then offset
        return _p(asm.push1(0xCD), asm.push1(1), asm.mstore8(), asm.stop())
    if op == asm.SLOAD:                             # SLOAD: key on top
        return _p(asm.push1(0), asm.sload(), asm.stop())
    if op == asm.SSTORE:                            # SSTORE: push value, then key
        return _p(asm.push1(0xAB), asm.push1(0), asm.sstore(), asm.stop())
    if op in asm.DUP_N:                             # DUP1 .. DUP16
        # Push n items so DUP{n} has an n-th item to duplicate (the bounded
        # STACK_SIZE means DUP16 still exceptional-halts, but it translates).
        n = asm.DUP_N[op]
        return _p(*[asm.push1(i + 1) for i in range(n)], asm.dupn(n), asm.stop())
    if op in asm.SWAP_N:                            # SWAP1 .. SWAP16
        # Push n+1 items so SWAP{n} has a top and an (n+1)-th item.
        n = asm.SWAP_N[op]
        return _p(*[asm.push1(i + 1) for i in range(n + 1)], asm.swapn(n), asm.stop())
    if op == asm.JUMP:                              # JUMP: PUSH dest, JUMP to a JUMPDEST
        # PUSH1 4 (->2), JUMP (->3), JUMPDEST@4? No: 0:PUSH1 4 (2), 2:JUMP (1),
        # 3:STOP (1), 4:JUMPDEST. dest must be the JUMPDEST offset (4).
        return _p(asm.push1(4), asm.jump(), asm.stop(), asm.jumpdest(), asm.stop())
    if op == asm.JUMPI:                             # JUMPI: PUSH cond, dest, JUMPI
        # 0:PUSH1 1 (cond,2), 2:PUSH1 6 (dest,2), 4:JUMPI (1), 5:STOP, 6:JUMPDEST.
        return _p(asm.push1(1), asm.push1(6), asm.jumpi(), asm.stop(), asm.jumpdest(), asm.stop())
    if op == asm.PC:                               # PC: push the current offset
        return _p(asm.pc(), asm.stop())
    if op == asm.JUMPDEST:                          # JUMPDEST: a bare no-op marker
        return _p(asm.jumpdest(), asm.stop())
    if op == asm.RETURN:                            # RETURN: push length, offset; RETURN
        return _p(asm.push1(1), asm.push1(0), asm.ret())
    if op == asm.REVERT:                            # REVERT: push length, offset; REVERT
        return _p(asm.push1(1), asm.push1(0), asm.revert())
    if op == asm.INVALID:                           # INVALID: a bare exceptional halt
        return _p(asm.invalid())
    if op == asm.STOP:
        return _p(asm.stop())
    return {"code": bytes((op,))}


# The denominator is the spec-derived EVM opcode inventory (``asm.OPCODE_NAMES``,
# London baseline + Shanghai ``PUSH0``), keyed by mnemonic so the ``unsupported``
# histogram is human-readable. The agent does not get to shrink it.
ALL_PROBES: dict[str, dict] = {
    name: _probe_for(op) for op, name in sorted(asm.OPCODE_NAMES.items())
}


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
