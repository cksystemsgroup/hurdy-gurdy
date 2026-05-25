"""SourceInterpreter for aarch64-btor2.

Adapted from gurdy/pairs/riscv_btor2/source_interp/interpreter.py (v2-bootstrap).
Drives the AArch64 concrete simulator and packages the run as a
framework SourceTrace.
"""

from __future__ import annotations

from typing import Any

from gurdy.core.interp.types import SourceStep, SourceTrace
from gurdy.pairs.aarch64_btor2.lift.simulator import (
    State,
    fetch_from_memory_map,
    step as sim_step,
)
from gurdy.pairs.aarch64_btor2.source.loader import AArch64Source
from gurdy.pairs.aarch64_btor2.source_interp.bindings import (
    AArch64InputBinding,
    Free,
    FreeFieldNotAllowed,
)


INTERPRETER_VERSION = "0.1.0"
PAIR_ID = "aarch64-btor2"


class AArch64SourceInterpreter:
    """SourceInterpreter Protocol implementation for aarch64-btor2."""

    version: str = INTERPRETER_VERSION

    def run(
        self,
        source: AArch64Source,
        binding: AArch64InputBinding,
        max_steps: int,
        *,
        spec: Any | None = None,
    ) -> SourceTrace:
        if binding.has_free_fields():
            raise FreeFieldNotAllowed(
                "AArch64SourceInterpreter does not accept FREE binding fields"
            )
        state = self._initial_state(source, binding)
        bytemap = source.binary.loadable_byte_map()
        # Overlay memory_init on top of ELF bytes
        for addr, b in binding.memory_init.items():
            if not isinstance(b, Free):
                bytemap[addr & 0xFFFFFFFFFFFFFFFF] = int(b) & 0xFF
        fetch = fetch_from_memory_map(bytemap)

        excluded = self._excluded_pc_ranges(spec)

        steps: list[SourceStep] = []
        halt_reason: str | None = None

        for i in range(max_steps):
            if state.halted:
                halt_reason = "svc_or_brk"
                break
            if self._pc_excluded(state.pc, excluded):
                halt_reason = "pc_in_excluded_range"
                break
            d = fetch(state.pc)
            if d is None:
                halt_reason = "fetch_failed"
                break

            location = {"pc": state.pc, "mnemonic": d.mnemonic}
            new_state = sim_step(state, d)
            new_state = self._apply_havoc(new_state, i, binding)

            deltas: dict[str, Any] = {
                "pc": new_state.pc,
                "regs": tuple(new_state.regs),
                "sp": new_state.sp,
                "nzcv": new_state.nzcv,
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

        final_state: dict[str, Any] = {
            "pc": state.pc,
            "regs": tuple(state.regs),
            "sp": state.sp,
            "nzcv": state.nzcv,
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

    def _initial_state(
        self, source: AArch64Source, binding: AArch64InputBinding
    ) -> State:
        state = State()
        if binding.pc is not None:
            state.pc = binding.pc & 0xFFFFFFFFFFFFFFFF
        elif source.binary is not None:
            state.pc = source.binary.entry
        for r, v in binding.register_init.items():
            if 0 <= r <= 30:
                cv = 0 if isinstance(v, Free) else int(v)
                state.regs[r] = cv & 0xFFFFFFFFFFFFFFFF
        if binding.sp_init is not None:
            state.sp = binding.sp_init & 0xFFFFFFFFFFFFFFFF
        if binding.nzcv_init is not None:
            state.nzcv = binding.nzcv_init & 0xF
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
        self, state: State, step_idx: int, binding: AArch64InputBinding
    ) -> State:
        has_reg_havoc = step_idx < len(binding.havoc_per_step)
        has_sp_havoc = step_idx < len(binding.havoc_sp)
        if not has_reg_havoc and not has_sp_havoc:
            return state
        new_state = state.clone()
        if has_reg_havoc:
            overrides = binding.havoc_per_step[step_idx] or {}
            for r, v in overrides.items():
                if 0 <= r <= 30:
                    cv = 0 if isinstance(v, Free) else int(v)
                    new_state.regs[r] = cv & 0xFFFFFFFFFFFFFFFF
        if has_sp_havoc:
            sp_override = binding.havoc_sp[step_idx]
            if sp_override is not None:
                new_state.sp = sp_override & 0xFFFFFFFFFFFFFFFF
        return new_state


__all__ = ["INTERPRETER_VERSION", "AArch64SourceInterpreter"]
