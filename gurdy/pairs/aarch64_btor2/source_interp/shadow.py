"""Shadow event types for the AArch64 term-shadow source interpreter.

Adapted from gurdy/pairs/riscv_btor2/source_interp/shadow.py.
SCHEMA.md §14.6. Per-step metadata recorded when record_shadow=True; lets
a downstream consumer construct BranchPin / memory-address pins.

AArch64-specific changes vs riscv_btor2:
- BRANCH_MNEMONICS: B.cond / CBZ / CBNZ / TBZ / TBNZ (conditional only).
  Unconditional B/BL/BR/BLR/RET are not recorded (no shadow needed).
- LOAD_MNEMONICS / STORE_MNEMONICS: A64 load/store vocabulary.
- free_fields_of: sp_init, nzcv_init, and havoc_sp cannot carry FREE
  (their types are int|None); only register_init, memory_init, and
  havoc_per_step are Free-capable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


BRANCH_MNEMONICS: frozenset[str] = frozenset(
    {"B.cond", "CBZ", "CBNZ", "TBZ", "TBNZ"}
)
LOAD_MNEMONICS: frozenset[str] = frozenset(
    {"LDR", "LDRB", "LDRH", "LDRSB", "LDRSH", "LDRSW", "LDP"}
)
STORE_MNEMONICS: frozenset[str] = frozenset({"STR", "STRB", "STRH", "STP"})


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
    """All shadow events from one interpreter run, plus the FREE field inventory."""

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
    """Inventory the FREE positions in an AArch64InputBinding."""
    from gurdy.pairs.aarch64_btor2.source_interp.bindings import Free

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
