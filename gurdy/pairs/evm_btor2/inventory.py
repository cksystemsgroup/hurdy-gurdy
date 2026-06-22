"""The construct-coverage inventory for evm-btor2 (BENCHMARKS.md §2).

The denominator is the *spec-derived* EVM opcode set (the agent does not choose
it): every defined opcode of the London + Shanghai (``PUSH0``) baseline. A
probe is a minimal one-opcode program; a construct is *covered* iff its probe
translates without an ``Unsupported`` abort. The thin slice covers exactly
``PUSH1``, ``ADD``, and ``STOP``; every other opcode lands in the
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
    """A minimal program exercising opcode ``op``. ``PUSH1``/``ADD`` are framed
    with the operands they consume; every other opcode is emitted bare (its
    translation aborts on decode, before any operand is consulted)."""
    if op == asm.PUSH1:
        return _p(asm.push1(1), asm.stop())
    if op == asm.ADD:
        return _p(asm.push1(2), asm.push1(3), asm.add(), asm.stop())
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
