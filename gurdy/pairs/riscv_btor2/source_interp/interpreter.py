"""``SourceInterpreter`` for riscv-btor2: drives the existing RV64
simulator and packages the run as a framework ``SourceTrace``.

Per step we record:

- ``location``: ``{"pc", "mnemonic", "disasm", "file", "line"}``
- ``deltas``: post-step register snapshot, memory changes, and halted
  flag. The post-step register snapshot is what cross-check compares
  against the BTOR2 state nids.

The interpreter is deterministic: same source + binding → identical
trace. No search.
"""

from __future__ import annotations

from typing import Any

from gurdy.core.interp.types import SourceStep, SourceTrace
from gurdy.pairs.riscv_btor2.lift.simulator import (
    State,
    fetch_from_memory_map,
    step as sim_step,
)
from gurdy.pairs.riscv_btor2.source.disasm import disasm
from gurdy.pairs.riscv_btor2.source.loader import RISCVSource
from gurdy.pairs.riscv_btor2.source_interp.bindings import RiscvInputBinding


INTERPRETER_VERSION = "1.0.0"
PAIR_ID = "riscv-btor2"


class RiscvSourceInterpreter:
    """``SourceInterpreter`` Protocol implementation for riscv-btor2."""

    version: str = INTERPRETER_VERSION

    def run(
        self,
        source: RISCVSource,
        binding: RiscvInputBinding,
        max_steps: int,
        *,
        spec: Any | None = None,
    ) -> SourceTrace:
        state = self._initial_state(source, binding)
        bytemap = source.binary.loadable_byte_map()
        fetch = fetch_from_memory_map(bytemap)

        excluded = self._excluded_pc_ranges(spec)

        steps: list[SourceStep] = []
        halt_reason: str | None = None
        for i in range(max_steps):
            if state.halted:
                halt_reason = "ecall_or_ebreak"
                break
            if self._pc_excluded(state.pc, excluded):
                halt_reason = "pc_in_excluded_range"
                break
            d = fetch(state.pc)
            if d is None:
                halt_reason = "fetch_failed"
                break
            pre_pc = state.pc
            location = {
                "pc": pre_pc,
                "mnemonic": d.mnemonic,
                "disasm": disasm(d),
            }
            loc = source.line_table.lookup(pre_pc) if source.line_table is not None else None
            if loc is not None:
                location["file"] = loc.file
                location["line"] = loc.line
            new_state = sim_step(state, d)

            # Apply per-step havoc overrides if any.
            new_state = self._apply_havoc(new_state, i, binding)

            deltas = {
                "pc": new_state.pc,
                "regs": tuple(new_state.regs),
                "halted": new_state.halted,
            }
            mem_changes = self._mem_diff(state.mem, new_state.mem)
            if mem_changes:
                deltas["mem_changes"] = mem_changes
            steps.append(
                SourceStep(
                    step=i, location=location, deltas=deltas, halted=new_state.halted
                )
            )
            state = new_state

        final_state = {
            "pc": state.pc,
            "regs": tuple(state.regs),
            "halted": state.halted,
            "mem": dict(state.mem),
        }
        return SourceTrace(
            pair=PAIR_ID,
            interpreter_version=INTERPRETER_VERSION,
            inputs_hash=binding.inputs_hash(),
            steps=tuple(steps),
            final_state=final_state,
            halted=state.halted,
            halt_reason=halt_reason,
        )

    # ------------------------------------------------------------------

    def _initial_state(
        self, source: RISCVSource, binding: RiscvInputBinding
    ) -> State:
        state = State()
        if binding.pc is not None:
            state.pc = binding.pc & ((1 << 64) - 1)
        elif source.binary is not None:
            state.pc = source.binary.entry
        for r, v in binding.register_init.items():
            if 1 <= r < 32:
                state.regs[r] = v & ((1 << 64) - 1)
        # Initial memory: layered on top of the binary's loadable bytes.
        for addr, b in binding.memory_init.items():
            state.mem[addr & ((1 << 64) - 1)] = b & 0xFF
        state.halted = bool(binding.halted)
        return state

    def _excluded_pc_ranges(self, spec: Any | None) -> tuple[tuple[int, int], ...]:
        if spec is None:
            return ()
        entry = getattr(spec, "entry", None)
        if entry is None:
            return ()
        ranges = getattr(entry, "excluded_pc_ranges", ()) or ()
        return tuple((int(lo), int(hi)) for lo, hi in ranges)

    def _pc_excluded(self, pc: int, ranges) -> bool:
        for lo, hi in ranges:
            if lo <= pc <= hi:
                return True
        return False

    def _mem_diff(self, before: dict, after: dict) -> dict[int, int]:
        diff: dict[int, int] = {}
        for addr, byte in after.items():
            if before.get(addr, 0) != byte:
                diff[addr] = byte
        for addr in before:
            if addr not in after:
                diff[addr] = 0
        return diff

    def _apply_havoc(
        self, state: State, step_idx: int, binding: RiscvInputBinding
    ) -> State:
        if step_idx >= len(binding.havoc_per_step):
            return state
        overrides = binding.havoc_per_step[step_idx] or {}
        if not overrides:
            return state
        new_state = state.clone()
        for r, v in overrides.items():
            if 1 <= r < 32:
                new_state.regs[r] = v & ((1 << 64) - 1)
        return new_state


__all__ = ["RiscvSourceInterpreter", "INTERPRETER_VERSION"]
