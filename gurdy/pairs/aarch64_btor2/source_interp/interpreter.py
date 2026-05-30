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
    _apply_extend,
    fetch_from_memory_map,
    step as sim_step,
)
from gurdy.pairs.aarch64_btor2.source.loader import AArch64Source
from gurdy.pairs.aarch64_btor2.source_interp.bindings import (
    AArch64InputBinding,
    Free,
    FreeFieldNotAllowed,
)
from gurdy.pairs.aarch64_btor2.source_interp.shadow import (
    BRANCH_MNEMONICS,
    LOAD_MNEMONICS,
    STORE_MNEMONICS,
    BranchEvent,
    MemoryAccessEvent,
    ShadowRecord,
    free_fields_of,
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
        record_shadow: bool = False,
    ) -> SourceTrace:
        """Run the simulator and return a SourceTrace.

        record_shadow=False (default): raises FreeFieldNotAllowed if any
        FREE binding fields are present.

        record_shadow=True: FREE cells concretize to 0 for execution;
        per-instruction branch and memory events are recorded and exposed
        on trace.final_state["shadow"] (SCHEMA.md §14.6).
        """
        if binding.has_free_fields() and not record_shadow:
            raise FreeFieldNotAllowed(
                "AArch64SourceInterpreter does not accept FREE binding fields "
                "with record_shadow=False; pass record_shadow=True or "
                "concretize the binding (SCHEMA.md §14.6)."
            )
        state = self._initial_state(source, binding)
        bytemap = source.binary.loadable_byte_map()
        for addr, b in binding.memory_init.items():
            if not isinstance(b, Free):
                bytemap[addr & 0xFFFFFFFFFFFFFFFF] = int(b) & 0xFF
        fetch = fetch_from_memory_map(bytemap)

        excluded = self._excluded_pc_ranges(spec)

        steps: list[SourceStep] = []
        halt_reason: str | None = None
        branch_events: list[BranchEvent] = []
        memory_events: list[MemoryAccessEvent] = []

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

            pre_pc = state.pc
            location = {"pc": pre_pc, "mnemonic": d.mnemonic}
            new_state = sim_step(state, d)
            new_state = self._apply_havoc(new_state, i, binding)

            if record_shadow:
                if d.mnemonic in BRANCH_MNEMONICS:
                    not_taken_pc = (pre_pc + 4) & 0xFFFFFFFFFFFFFFFF
                    branch_events.append(
                        BranchEvent(
                            step=i,
                            pc=pre_pc,
                            mnemonic=d.mnemonic,
                            taken=(new_state.pc != not_taken_pc),
                        )
                    )
                elif d.mnemonic in LOAD_MNEMONICS or d.mnemonic in STORE_MNEMONICS:
                    addr = self._effective_addr(state, d, pre_pc)
                    kind = "load" if d.mnemonic in LOAD_MNEMONICS else "store"
                    memory_events.append(
                        MemoryAccessEvent(
                            step=i,
                            pc=pre_pc,
                            mnemonic=d.mnemonic,
                            addr=addr,
                            kind=kind,
                            free_dependent=False,
                        )
                    )

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
        if record_shadow:
            shadow_record = ShadowRecord(
                branch_events=tuple(branch_events),
                memory_events=tuple(memory_events),
                **free_fields_of(binding),
            )
            final_state["shadow"] = shadow_record.to_jsonable()
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

    def _effective_addr(self, state: "State", d: Any, pre_pc: int) -> int:
        """Compute the effective memory address from the pre-step state.

        Mirrors the address-computation logic in simulator.step() so the
        shadow records the same address that the simulator acts on.
        """
        def spr(n: int) -> int:
            return state.sp if n == 31 else state.regs[n]

        if d.addr_mode == "literal":
            return (pre_pc + d.imm) & 0xFFFFFFFFFFFFFFFF
        if d.addr_mode in ("base_imm", "base", "pre"):
            return (spr(d.rn) + d.imm) & 0xFFFFFFFFFFFFFFFF
        if d.addr_mode == "post":
            return spr(d.rn) & 0xFFFFFFFFFFFFFFFF
        if d.addr_mode in ("base_reg", "ext_reg"):
            ext = _apply_extend(state.read_reg(d.rm, sp_context=False),
                                d.extend_type, d.shift_amount)
            return (spr(d.rn) + ext) & 0xFFFFFFFFFFFFFFFF
        return spr(d.rn) & 0xFFFFFFFFFFFFFFFF

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
