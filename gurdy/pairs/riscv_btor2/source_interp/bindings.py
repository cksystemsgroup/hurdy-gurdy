"""Concrete-input binding for the RISC-V source interpreter.

A ``RiscvInputBinding`` describes a (possibly partial) run when
combined with a spec's ``EntryAssumptions``. Fully-pinned bindings —
every map value an ``int`` — drive the plain simulator; partial
bindings whose values may be the ``FREE`` sentinel drive the
term-shadow simulator (SCHEMA.md §14.2 / §14.6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Sequence, Union

from gurdy.core.interp.types import InputBinding


class Free:
    """Sentinel type marking a binding field as symbolic.

    SCHEMA.md §14.2. The single ``FREE`` instance is what callers
    use; the class exists so :func:`isinstance` works.
    """

    _instance: "Free | None" = None

    def __new__(cls) -> "Free":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # serialization-friendly
        return "Free"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Free)

    def __hash__(self) -> int:
        return hash("Free")


FREE: Free = Free()


# Type alias: a binding cell is either pinned (int) or free.
Cell = Union[int, Free]


class FreeFieldNotAllowed(ValueError):
    """Raised by the plain interpreter on encountering a ``FREE``
    binding field. The term-shadow interpreter accepts ``FREE``
    instead (SCHEMA.md §14.6)."""


def _decode_cell(v: Any) -> Cell:
    """Decode a JSON value into ``Cell``. The string ``"Free"``
    deserializes to :data:`FREE`; everything else is interpreted as
    an integer."""
    if isinstance(v, Free) or v == "Free":
        return FREE
    return int(v)


@dataclass(frozen=True)
class RiscvInputBinding(InputBinding):
    """Concrete inputs for one RV64 simulator run.

    ``register_init``: x1..x31 -> ``Cell`` (x0 is hard-wired zero
    per SCHEMA.md and is ignored if specified). A value of
    :data:`FREE` marks the register's entry value as symbolic.
    ``memory_init``: address -> ``Cell``. Sparse; missing addresses
    read as zero per simulator convention.
    ``pc``: starting PC. ``None`` defers to the binary's e_entry.
    ``FREE`` is *not* a legal value for ``pc`` (SCHEMA.md §14.2).
    ``halted``: bool only; no ``FREE``.
    ``havoc_per_step``: per-step havoc value; may be :data:`FREE`.
    """

    pair: ClassVar[str] = "riscv-btor2"

    register_init: Mapping[int, Cell] = field(default_factory=dict)
    memory_init: Mapping[int, Cell] = field(default_factory=dict)
    pc: int | None = None
    halted: bool = False
    havoc_per_step: Sequence[Mapping[int, Cell]] = ()

    @classmethod
    def from_jsonable(cls, obj: Mapping[str, Any]) -> "RiscvInputBinding":
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
        pc = f.get("pc")
        return cls(
            register_init=regs,
            memory_init=mem,
            pc=int(pc) if pc is not None else None,
            halted=bool(f.get("halted", False)),
            havoc_per_step=havoc,
        )

    def has_free_fields(self) -> bool:
        """True iff any field is marked symbolic via :data:`FREE`."""
        if any(isinstance(v, Free) for v in self.register_init.values()):
            return True
        if any(isinstance(v, Free) for v in self.memory_init.values()):
            return True
        for overrides in self.havoc_per_step:
            if any(isinstance(v, Free) for v in overrides.values()):
                return True
        return False


__all__ = [
    "Cell",
    "FREE",
    "Free",
    "FreeFieldNotAllowed",
    "RiscvInputBinding",
]
