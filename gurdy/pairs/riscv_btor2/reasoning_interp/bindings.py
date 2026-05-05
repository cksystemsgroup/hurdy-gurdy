"""Concrete-binding type for the BTOR2 reasoning interpreter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Sequence

from gurdy.core.interp.types import ReasoningBinding


@dataclass(frozen=True)
class Btor2ReasoningBinding(ReasoningBinding):
    """All concrete values the BTOR2 multi-step evaluator needs.

    Bindings are keyed by *symbol* — ``pc``, ``reg_x1``..``reg_x31``,
    ``mem``, ``halted`` per the riscv-btor2 schema — rather than by
    nid, because nids are renumbered during linking and the symbol is
    the stable cross-version handle.

    ``state_init_by_symbol`` overrides the initial value for the named
    state. ``input_per_step_by_symbol`` supplies, per step, a mapping
    from input symbol to value (used when the artifact has havoc
    inputs or fresh-input nids).

    Memory state values may be a flat dict ``{addr: byte}``.
    """

    pair: ClassVar[str] = "riscv-btor2"

    state_init_by_symbol: Mapping[str, Any] = field(default_factory=dict)
    input_per_step_by_symbol: Sequence[Mapping[str, Any]] = ()

    @classmethod
    def from_jsonable(cls, obj: Mapping[str, Any]) -> "Btor2ReasoningBinding":
        f = obj.get("fields", obj)
        states = dict(f.get("state_init_by_symbol") or {})
        inputs_raw = f.get("input_per_step_by_symbol") or ()
        inputs = tuple(dict(m or {}) for m in inputs_raw)
        return cls(
            state_init_by_symbol=states,
            input_per_step_by_symbol=inputs,
        )


__all__ = ["Btor2ReasoningBinding"]
