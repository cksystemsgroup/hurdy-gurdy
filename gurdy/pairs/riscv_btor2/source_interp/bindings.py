"""Concrete-input binding for the RISC-V source interpreter.

A ``RiscvInputBinding`` fully determines a source run when combined
with a spec's ``EntryAssumptions``. The fields mirror the spec's own
``RegisterInit`` / ``MemoryInit`` vocabulary but with concrete values
(no comparisons; the binding picks one element of each spec-allowed
range).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Sequence

from gurdy.core.interp.types import InputBinding


@dataclass(frozen=True)
class RiscvInputBinding(InputBinding):
    """Concrete inputs for one RV64 simulator run.

    ``register_init``: x1..x31 -> u64 (x0 is hard-wired zero per
    SCHEMA.md and is ignored if specified).
    ``memory_init``: address -> byte. Sparse; missing addresses read
    as zero per simulator convention.
    ``pc``: starting PC. ``None`` defers to the binary's e_entry.
    ``havoc_per_step``: sequence indexed by step; each entry maps
    register index to the value forced into that register *after* the
    step's normal write. Models the spec's ``havoc_registers``
    overlay on a concrete run.
    """

    pair: ClassVar[str] = "riscv-btor2"

    register_init: Mapping[int, int] = field(default_factory=dict)
    memory_init: Mapping[int, int] = field(default_factory=dict)
    pc: int | None = None
    halted: bool = False
    havoc_per_step: Sequence[Mapping[int, int]] = ()

    @classmethod
    def from_jsonable(cls, obj: Mapping[str, Any]) -> "RiscvInputBinding":
        f = obj.get("fields", obj)
        regs = {int(k): int(v) for k, v in (f.get("register_init") or {}).items() if str(k).isdigit() or isinstance(k, int)}
        mem = {int(k): int(v) for k, v in (f.get("memory_init") or {}).items() if str(k).lstrip("-").isdigit() or isinstance(k, int)}
        havoc_raw = f.get("havoc_per_step") or ()
        havoc = tuple(
            {int(k): int(v) for k, v in (m or {}).items()} for m in havoc_raw
        )
        pc = f.get("pc")
        return cls(
            register_init=regs,
            memory_init=mem,
            pc=int(pc) if pc is not None else None,
            halted=bool(f.get("halted", False)),
            havoc_per_step=havoc,
        )


__all__ = ["RiscvInputBinding"]
