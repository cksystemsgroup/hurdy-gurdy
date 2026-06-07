"""Witness lift: replay a Z3 model through the AArch64 simulator.

Adapted from gurdy/pairs/riscv_btor2/lift/witness.py (v2-bootstrap).
AArch64 differences vs riscv-btor2:
- 31 GPRs (x0–x30); x31 is XZR/SP, not a state variable.
- sp and nzcv are separate state variables.
- No DWARF line-table on AArch64Source (deferred); file/line are always None.
- State symbols: pc, reg_x0..reg_x30, sp, nzcv, halted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from gurdy.core.btor2.parser import from_text
from gurdy.pairs.aarch64_btor2.lift.simulator import State, fetch_from_memory_map, simulate
from gurdy.pairs.aarch64_btor2.source.loader import AArch64Source


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


def _state_symbol_to_nid(btor2_text: str) -> dict[str, int]:
    """Walk BTOR2 and return {symbol: nid} for every state node.

    aarch64-btor2 schema (SCHEMA.md §3) uses: pc, reg_x0..reg_x30,
    sp, nzcv, mem, halted.
    """
    out: dict[str, int] = {}
    try:
        parsed = from_text(btor2_text).model
    except Exception:
        return out
    for node in parsed.nodes():
        if node.op == "state" and node.symbol:
            out[node.symbol] = node.nid
    return out


def _initial_state_from_witness(
    source: AArch64Source,
    initial: dict[int, int],
    sym_to_nid: dict[str, int],
) -> State:
    """Build the simulator's starting state from witness values.

    Missing fields fall back to safe defaults (entry pc from ELF,
    zero registers, zero sp/nzcv, not halted).
    """
    state = State()
    pc_nid = sym_to_nid.get("pc")
    if pc_nid is not None and pc_nid in initial:
        state.pc = initial[pc_nid] & ((1 << 64) - 1)
    elif source.binary is not None:
        state.pc = source.binary.entry
    # Registers x0..x30 (31 GPRs; x31 is XZR/SP, not a state var).
    for r in range(31):
        nid = sym_to_nid.get(f"reg_x{r}")
        if nid is not None and nid in initial:
            state.regs[r] = initial[nid] & ((1 << 64) - 1)
    sp_nid = sym_to_nid.get("sp")
    if sp_nid is not None and sp_nid in initial:
        state.sp = initial[sp_nid] & ((1 << 64) - 1)
    nzcv_nid = sym_to_nid.get("nzcv")
    if nzcv_nid is not None and nzcv_nid in initial:
        state.nzcv = initial[nzcv_nid] & 0xF
    halted_nid = sym_to_nid.get("halted")
    if halted_nid is not None and halted_nid in initial:
        state.halted = bool(initial[halted_nid])
    return state


def lift_witness(
    source: AArch64Source,
    payload: dict[str, Any] | None,
    *,
    btor2_text: str | None = None,
) -> WitnessTrace:
    """Replay a witness against the AArch64 simulator.

    ``payload`` carries ``witness_text`` from the solver result.
    ``btor2_text`` is required to map state nids to symbols; without
    it the trace is empty (graceful degradation).
    """
    if not isinstance(payload, dict):
        return WitnessTrace()

    text = payload.get("witness_text", "")
    initial = _extract_initial_register_values(text)
    sym_to_nid = _state_symbol_to_nid(btor2_text) if btor2_text else {}

    state = _initial_state_from_witness(source, initial, sym_to_nid)
    bytemap = source.binary.loadable_byte_map()
    fetch = fetch_from_memory_map(bytemap)
    final, decoded_trace = simulate(state, fetch, max_steps=256)
    steps: list[LiftedStep] = []
    for cycle, d in enumerate(decoded_trace):
        steps.append(
            LiftedStep(
                cycle=cycle,
                pc=d.pc,
                mnemonic=d.mnemonic,
                disasm=d.mnemonic,  # full disasm deferred to P5+
                file=None,
                line=None,
            )
        )
    return WitnessTrace(steps=steps, halted=final.halted, final_regs=tuple(final.regs))


__all__ = ["LiftedStep", "WitnessTrace", "lift_witness",
           "_extract_initial_register_values", "_state_symbol_to_nid"]
