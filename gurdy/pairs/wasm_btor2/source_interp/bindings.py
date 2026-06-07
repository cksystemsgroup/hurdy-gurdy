"""Concrete-input binding for the WASM source interpreter.

A ``WasmInputBinding`` describes a fully-pinned run when combined with
the spec's entry assumptions.  Parallel to ``RiscvInputBinding`` in the
riscv-btor2 pair.

FREE fields are supported for shadow mode (record_shadow=True):
the interpreter concretizes them to zero and records which cells were
accessed as symbolic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Union

from gurdy.core.interp.types import InputBinding


# ---------------------------------------------------------------------------
# Free sentinel
# ---------------------------------------------------------------------------


class Free:
    """Singleton sentinel marking a binding cell as symbolic."""

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
    """Raised when a FREE binding field is passed without record_shadow=True."""


def _decode_cell(v: Any) -> Cell:
    if isinstance(v, Free) or v == "Free":
        return FREE
    return int(v)


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WasmInputBinding(InputBinding):
    """Concrete inputs for one WASM source-interpreter run.

    ``param_init``: entry-function local index → value for the parameters
    (0-indexed; only parameters accepted here, declared locals start zeroed).

    ``global_init``: module-global index → value (overrides the module's
    constant initializer for that global; index 0 is the first global,
    imports included).

    ``memory_init``: byte address → value (sparse byte map; missing bytes
    read as the module's data-segment values, or zero if not in any segment).

    ``import_returns``: ``"module.name"`` → integer return value for host
    imports that are called.  Only single-value (i32/i64) results are
    supported in P2; multi-value deferred.
    """

    pair: ClassVar[str] = "wasm-btor2"

    param_init: Mapping[int, Cell] = field(default_factory=dict)
    global_init: Mapping[int, Cell] = field(default_factory=dict)
    memory_init: Mapping[int, Cell] = field(default_factory=dict)
    import_returns: Mapping[str, Cell] = field(default_factory=dict)

    def has_free_fields(self) -> bool:
        for v in self.param_init.values():
            if isinstance(v, Free):
                return True
        for v in self.global_init.values():
            if isinstance(v, Free):
                return True
        for v in self.memory_init.values():
            if isinstance(v, Free):
                return True
        for v in self.import_returns.values():
            if isinstance(v, Free):
                return True
        return False

    @classmethod
    def from_jsonable(cls, obj: Mapping[str, Any]) -> "WasmInputBinding":
        f = obj.get("fields", obj)
        param_init = {int(k): _decode_cell(v) for k, v in (f.get("param_init") or {}).items()}
        global_init = {int(k): _decode_cell(v) for k, v in (f.get("global_init") or {}).items()}
        memory_init = {int(k): _decode_cell(v) for k, v in (f.get("memory_init") or {}).items()}
        import_returns = {str(k): _decode_cell(v) for k, v in (f.get("import_returns") or {}).items()}
        return cls(
            param_init=param_init,
            global_init=global_init,
            memory_init=memory_init,
            import_returns=import_returns,
        )


__all__ = [
    "Cell",
    "FREE",
    "Free",
    "FreeFieldNotAllowed",
    "WasmInputBinding",
]
