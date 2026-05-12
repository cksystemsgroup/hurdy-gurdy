"""Shadow event types for the term-shadow source interpreter.

SCHEMA.md §14.6. The shadow records, per executed step of the
simulator, the metadata a downstream consumer needs to construct a
``BranchPin`` (§14.3) or a memory-address pin (§14.7) from the
trace. v1.1.0 records event triples; future versions may attach
BTOR2 sub-terms directly.

The shadow does *not* perform a parallel BTOR2 emission. The
volatile-layer lowering of a ``BranchPin`` recovers the branch
condition's BTOR2 term from the existing
``library.LoweringResult.branch_cond`` keyed by the pin's PC. The
shadow's job is only to identify *which* ``(step, pc, taken)``
triples to convert into pins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


BRANCH_MNEMONICS: frozenset[str] = frozenset(
    {"BEQ", "BNE", "BLT", "BGE", "BLTU", "BGEU"}
)
LOAD_MNEMONICS: frozenset[str] = frozenset(
    {"LB", "LH", "LW", "LD", "LBU", "LHU", "LWU"}
)
STORE_MNEMONICS: frozenset[str] = frozenset({"SB", "SH", "SW", "SD"})


@dataclass(frozen=True)
class BranchEvent:
    step: int
    pc: int
    mnemonic: str
    taken: bool

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "pc": self.pc,
            "mnemonic": self.mnemonic,
            "taken": self.taken,
        }


@dataclass(frozen=True)
class MemoryAccessEvent:
    step: int
    pc: int
    mnemonic: str
    addr: int
    kind: str  # "load" | "store"
    free_dependent: bool = False

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "pc": self.pc,
            "mnemonic": self.mnemonic,
            "addr": self.addr,
            "kind": self.kind,
            "free_dependent": self.free_dependent,
        }


@dataclass(frozen=True)
class ShadowRecord:
    """All shadow events from one interpreter run, plus the set of
    binding fields that were :data:`FREE`."""

    branch_events: tuple[BranchEvent, ...] = ()
    memory_events: tuple[MemoryAccessEvent, ...] = ()
    free_register_init: tuple[int, ...] = ()
    free_memory_init: tuple[int, ...] = ()
    free_havoc_steps: tuple[tuple[int, int], ...] = ()

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "branch_events": [e.to_jsonable() for e in self.branch_events],
            "memory_events": [e.to_jsonable() for e in self.memory_events],
            "free_fields": {
                "register_init": list(self.free_register_init),
                "memory_init": list(self.free_memory_init),
                "havoc_steps": [list(p) for p in self.free_havoc_steps],
            },
        }


def free_fields_of(binding) -> dict[str, Any]:
    """Inventory the FREE positions in a binding (for ShadowRecord)."""
    from gurdy.pairs.riscv_btor2.source_interp.bindings import Free

    reg = tuple(
        sorted(k for k, v in binding.register_init.items() if isinstance(v, Free))
    )
    mem = tuple(
        sorted(k for k, v in binding.memory_init.items() if isinstance(v, Free))
    )
    havoc = tuple(
        (step_idx, reg_idx)
        for step_idx, overrides in enumerate(binding.havoc_per_step)
        for reg_idx, v in sorted(overrides.items())
        if isinstance(v, Free)
    )
    return {
        "free_register_init": reg,
        "free_memory_init": mem,
        "free_havoc_steps": havoc,
    }


__all__ = [
    "BRANCH_MNEMONICS",
    "BranchEvent",
    "LOAD_MNEMONICS",
    "MemoryAccessEvent",
    "STORE_MNEMONICS",
    "ShadowRecord",
    "free_fields_of",
]
