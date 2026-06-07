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

from gurdy.core.btor2.parser import from_text
from gurdy.pairs.riscv_btor2.lift.simulator import (
    State,
    fetch_from_memory_map,
    simulate,
    simulate_with_regs,
)
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


def _state_symbol_to_nid(btor2_text: str) -> dict[str, int]:
    """Walk a BTOR2 model and return ``{symbol: nid}`` for every
    ``state`` declaration. The riscv-btor2 schema (§3) pins symbol
    names: ``pc``, ``reg_x{N}`` for N=1..31, ``mem``, ``halted``."""
    out: dict[str, int] = {}
    try:
        parsed = from_text(btor2_text).model
    except Exception:
        return out
    for node in parsed.nodes():
        if node.op == "state" and node.symbol:
            out[node.symbol] = node.nid
    return out


def _init_values_from_btor2(btor2_text: str) -> dict[int, int]:
    """Walk a BTOR2 model for ``init`` clauses and return
    ``{state_nid: initial_value}`` for every initial-state pin
    whose value resolves to a concrete constant.

    Z3's BMC witness text may *omit* state values that are pinned
    by an ``init`` clause — they're determined, so Z3 doesn't
    bother emitting them. Without this fallback, the lifter
    treats those state slots as zero, which silently misreads
    any RegisterInit / MemoryInit-pinned task. This helper fixes
    that by parsing the model's own ``init`` declarations.

    Only handles bitvector constants (``zero``, ``one``, ``ones``,
    ``constd``, ``const``, ``consth``). Array-valued inits (memory
    pins) are skipped — they're handled by the existing per-byte
    constraint path.
    """
    out: dict[int, int] = {}
    try:
        parsed = from_text(btor2_text).model
    except Exception:
        return out
    # First pass: resolve constants to their bitvector values.
    sort_widths: dict[int, int] = {}
    for n in parsed.nodes():
        if n.op == "sort" and n.sort is not None:
            w = getattr(n.sort, "width", None)
            if w is not None:
                sort_widths[n.nid] = int(w)
    const_value_by_nid: dict[int, int] = {}
    for n in parsed.nodes():
        if not n.args:
            continue
        try:
            sort_nid = int(n.args[0])
        except (TypeError, ValueError):
            continue
        w = sort_widths.get(sort_nid)
        if n.op == "zero":
            const_value_by_nid[n.nid] = 0
        elif n.op == "one":
            const_value_by_nid[n.nid] = 1
        elif n.op == "ones" and w is not None:
            const_value_by_nid[n.nid] = (1 << w) - 1
        elif n.op == "constd" and len(n.args) >= 2:
            try:
                const_value_by_nid[n.nid] = int(n.args[1])
            except (TypeError, ValueError):
                pass
        elif n.op == "const" and len(n.args) >= 2:
            try:
                const_value_by_nid[n.nid] = int(n.args[1], 2)
            except (TypeError, ValueError):
                pass
        elif n.op == "consth" and len(n.args) >= 2:
            try:
                const_value_by_nid[n.nid] = int(n.args[1], 16)
            except (TypeError, ValueError):
                pass
    # Second pass: for each ``init`` node, look up the value.
    for n in parsed.nodes():
        if n.op != "init" or len(n.args) < 3:
            continue
        try:
            state_nid = int(n.args[1])
            value_nid = int(n.args[2])
        except (TypeError, ValueError):
            continue
        if value_nid in const_value_by_nid:
            out[state_nid] = const_value_by_nid[value_nid]
    return out


def _initial_state_from_witness(
    source: RISCVSource,
    initial: dict[int, int],
    sym_to_nid: dict[str, int],
) -> State:
    """Build the simulator's starting state from witness values + the
    BTOR2 state-symbol table. Missing fields fall back to safe
    defaults (entry pc from the ELF, zero registers, not halted)."""
    state = State()
    # PC: prefer the witness's value if present, else the binary's e_entry.
    pc_nid = sym_to_nid.get("pc")
    if pc_nid is not None and pc_nid in initial:
        state.pc = initial[pc_nid] & ((1 << 64) - 1)
    elif source.binary is not None:
        state.pc = source.binary.entry
    # Registers x1..x31 (x0 is hard-wired zero per SCHEMA.md §3).
    for r in range(1, 32):
        nid = sym_to_nid.get(f"reg_x{r}")
        if nid is not None and nid in initial:
            state.regs[r] = initial[nid] & ((1 << 64) - 1)
    halted_nid = sym_to_nid.get("halted")
    if halted_nid is not None and halted_nid in initial:
        state.halted = bool(initial[halted_nid])
    return state


def lift_witness(
    source: RISCVSource,
    payload: dict[str, Any] | None,
    *,
    btor2_text: str | None = None,
) -> WitnessTrace:
    """Replay a witness against the simulator.

    ``payload`` is a ``RawSolverResult.payload`` dict carrying
    ``witness_text`` (a stringified Z3 model). ``btor2_text`` is the
    flattened BTOR2 artifact text and is required for the simulator
    to find the initial PC and register values; without it the trace
    is empty (the BMC engines and the harness's tool_lift always
    have it on hand).

    Returns an empty trace when ``payload`` is None or
    unparseable — preserves the legacy contract for callers that
    haven't plumbed the artifact through yet.
    """
    if not isinstance(payload, dict):
        return WitnessTrace()

    text = payload.get("witness_text", "")
    initial = _extract_initial_register_values(text)
    sym_to_nid = _state_symbol_to_nid(btor2_text) if btor2_text else {}
    # Z3 may omit state values that are pinned by `init` clauses.
    # Merge those in as fallback so the lifter doesn't silently
    # treat init-pinned slots as zero (which would misread any
    # RegisterInit/MemoryInit-pinned task — see V2_PROGRESS.md
    # iter 40 retrospective).
    init_values = (
        _init_values_from_btor2(btor2_text) if btor2_text else {}
    )
    for nid, val in init_values.items():
        initial.setdefault(nid, val)

    state = _initial_state_from_witness(source, initial, sym_to_nid)
    bytemap = source.binary.loadable_byte_map()
    fetch = fetch_from_memory_map(bytemap)
    # 256 covers the v0.3 large-bound corpus tasks (e.g.,
    # 0051-large-bound-loop-bitwuzla halts at cycle 164). Bump if a
    # future task pins a larger bound.
    final, decoded_trace, per_step_regs = simulate_with_regs(
        state, fetch, max_steps=256
    )
    steps: list[LiftedStep] = []
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
                regs=per_step_regs[cycle],
            )
        )
    return WitnessTrace(steps=steps, halted=final.halted, final_regs=tuple(final.regs))


__all__ = ["LiftedStep", "WitnessTrace", "lift_witness"]
