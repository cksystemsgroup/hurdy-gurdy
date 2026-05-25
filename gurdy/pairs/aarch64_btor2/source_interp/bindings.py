"""Concrete-input binding for the AArch64 source interpreter.

Adapted from gurdy/pairs/riscv_btor2/source_interp/bindings.py (v2-bootstrap).
AArch64-specific fields vs riscv-btor2:
- register_init keys are 0–30 (x0–x30; XZR/SP are not state variables).
- sp_init: initial value of the SP state (register 31 in stack context).
- nzcv_init: initial 4-bit condition flags (SCHEMA.md §3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Sequence, Union

from gurdy.core.interp.types import InputBinding


class Free:
    """Sentinel for symbolic binding fields (SCHEMA.md §14.2)."""

    _instance: "Free | None" = None

    def __new__(cls) -> "Free":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "Free"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Free)

    def __hash__(self) -> int:
        return hash("Free")


FREE: Free = Free()

Cell = Union[int, Free]


class FreeFieldNotAllowed(ValueError):
    """Raised by the plain interpreter when FREE fields are supplied."""


def _decode_cell(v: Any) -> Cell:
    if isinstance(v, Free) or v == "Free":
        return FREE
    return int(v)


@dataclass(frozen=True)
class AArch64InputBinding(InputBinding):
    """Concrete inputs for one AArch64 simulator run.

    ``register_init``: x0–x30 (keys 0–30) -> Cell. x31 (XZR/SP) is
    not a GPR state variable; use ``sp_init`` for SP.
    ``sp_init``: initial SP value. None leaves SP at 0.
    ``nzcv_init``: initial 4-bit NZCV flags. None leaves NZCV at 0.
    ``memory_init``: address -> Cell (sparse; missing → 0).
    ``pc``: starting PC. None defers to binary e_entry.
    ``halted``: bool only; no FREE.
    ``havoc_per_step``: per-step register overrides; may be FREE.
    ``havoc_sp``: per-step SP overrides (SCHEMA.md §9).
    """

    pair: ClassVar[str] = "aarch64-btor2"

    register_init: Mapping[int, Cell] = field(default_factory=dict)
    sp_init: int | None = None
    nzcv_init: int | None = None
    memory_init: Mapping[int, Cell] = field(default_factory=dict)
    pc: int | None = None
    halted: bool = False
    havoc_per_step: Sequence[Mapping[int, Cell]] = ()
    havoc_sp: Sequence[int | None] = ()

    @classmethod
    def from_jsonable(cls, obj: Mapping[str, Any]) -> "AArch64InputBinding":
        f = obj.get("fields", obj)
        regs = {
            int(k): _decode_cell(v)
            for k, v in (f.get("register_init") or {}).items()
            if str(k).isdigit() or isinstance(k, int)
        }
        mem = {
            int(k): _decode_cell(v)
            for k, v in (f.get("memory_init") or {}).items()
            if str(k).lstrip("-").isdigit() or isinstance(k, int)
        }
        havoc_raw = f.get("havoc_per_step") or ()
        havoc = tuple(
            {int(k): _decode_cell(v) for k, v in (m or {}).items()}
            for m in havoc_raw
        )
        havoc_sp_raw = f.get("havoc_sp") or ()
        havoc_sp = tuple(int(v) if v is not None else None for v in havoc_sp_raw)
        pc = f.get("pc")
        sp = f.get("sp_init")
        nzcv = f.get("nzcv_init")
        return cls(
            register_init=regs,
            sp_init=int(sp) if sp is not None else None,
            nzcv_init=int(nzcv) if nzcv is not None else None,
            memory_init=mem,
            pc=int(pc) if pc is not None else None,
            halted=bool(f.get("halted", False)),
            havoc_per_step=havoc,
            havoc_sp=havoc_sp,
        )

    def has_free_fields(self) -> bool:
        if any(isinstance(v, Free) for v in self.register_init.values()):
            return True
        if any(isinstance(v, Free) for v in self.memory_init.values()):
            return True
        for overrides in self.havoc_per_step:
            if any(isinstance(v, Free) for v in overrides.values()):
                return True
        return False


__all__ = [
    "AArch64InputBinding",
    "Cell",
    "FREE",
    "Free",
    "FreeFieldNotAllowed",
]
