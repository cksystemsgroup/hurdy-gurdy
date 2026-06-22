"""The construct-coverage inventory for evm-btor2 (BENCHMARKS.md §2).

The denominator is the *spec-derived* EVM opcode set (the agent does not choose
it): every defined opcode of the London + Shanghai (``PUSH0``) baseline. A
probe is a minimal program exercising the opcode; a construct is *covered* iff
its probe translates without an ``Unsupported`` abort. The slice covers exactly
``PUSH1`` / ``PUSH2`` / ``PUSH4``, ``ADD`` / ``MUL`` / ``SUB`` / ``DIV`` /
``MOD``, ``POP`` / ``DUP1``, and ``STOP``; every other opcode lands in the
``unsupported`` histogram (BENCHMARKS.md §3) — the honest, visible gap that
keeps this pair ``partial``.

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
    if op == asm.PUSH1:
        return _p(asm.push1(1), asm.stop())
    if op == asm.PUSH2:
        return _p(asm.push2(0x0102), asm.stop())
    if op == asm.PUSH4:
        return _p(asm.push4(0x01020304), asm.stop())
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
    if op == asm.POP:
        return _p(asm.push1(7), asm.pop(), asm.stop())
    if op == asm.DUP1:
        return _p(asm.push1(7), asm.dup1(), asm.stop())
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
