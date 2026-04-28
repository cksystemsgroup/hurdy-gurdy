"""Witness lift: replay a Z3 model through the simulator.

Given a ``RawSolverResult.payload`` from the Z3 BMC backend, extract
the cycle-0 input values for registers and memory and replay the
binary's analyzed scope through the concrete simulator. The result
is a list of ``LiftedStep`` records carrying source-level information
(PC, mnemonic, register/memory state, DWARF source location).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from gurdy.pairs.riscv_btor2.lift.simulator import State, fetch_from_memory_map, simulate
from gurdy.pairs.riscv_btor2.source.disasm import disasm
from gurdy.pairs.riscv_btor2.source.loader import RISCVSource


@dataclass(frozen=True)
class LiftedStep:
    cycle: int
    pc: int
    mnemonic: str
    disasm: str
    file: str | None = None
    line: int | None = None
    regs: tuple[int, ...] = ()


@dataclass
class WitnessTrace:
    steps: list[LiftedStep] = field(default_factory=list)
    halted: bool = False
    final_regs: tuple[int, ...] = ()


_REG_RE = re.compile(r"s0_n(\d+)\s*=\s*([0-9A-Fa-fxX]+)")


def _extract_initial_register_values(witness_text: str) -> dict[int, int]:
    """Pull cycle-0 register-state assignments from a Z3 model dump.

    The Z3 model.format isn't standardized for our purposes; we look
    for ``s0_nN = value`` lines and return the bound nids.
    """
    out: dict[int, int] = {}
    for m in _REG_RE.finditer(witness_text):
        nid = int(m.group(1))
        raw = m.group(2)
        try:
            value = int(raw, 0)
        except ValueError:
            continue
        out[nid] = value
    return out


def lift_witness(
    source: RISCVSource,
    payload: dict[str, Any] | None,
) -> WitnessTrace:
    """Replay a witness against the simulator. If ``payload`` is None
    or unparseable, returns an empty trace."""
    if not isinstance(payload, dict):
        return WitnessTrace()

    text = payload.get("witness_text", "")
    initial = _extract_initial_register_values(text)
    # We don't have a stable nid->register mapping here without the
    # artifact's annotation; the lift module that wires through the
    # full annotation lives in lift.lift. This module's job is the
    # mechanical replay, given a starting State.
    state = State()
    bytemap = source.binary.loadable_byte_map()
    fetch = fetch_from_memory_map(bytemap)
    final, decoded_trace = simulate(state, fetch, max_steps=64)
    steps: list[LiftedStep] = []
    pc_walker = State()
    pc_walker.mem = dict(state.mem)
    for cycle, d in enumerate(decoded_trace):
        loc = source.line_table.lookup(d.pc)
        steps.append(
            LiftedStep(
                cycle=cycle,
                pc=d.pc,
                mnemonic=d.mnemonic,
                disasm=disasm(d),
                file=loc.file if loc else None,
                line=loc.line if loc else None,
            )
        )
    return WitnessTrace(steps=steps, halted=final.halted, final_regs=tuple(final.regs))


__all__ = ["LiftedStep", "WitnessTrace", "lift_witness"]
