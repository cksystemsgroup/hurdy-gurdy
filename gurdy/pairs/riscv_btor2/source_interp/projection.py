"""Projection from BTOR2 reasoning steps to RV64 source steps.

The riscv-btor2 schema pins state symbol names: ``pc``, ``reg_x{N}``
for N=1..31, ``mem``, ``halted``. The reasoning interpreter records
state values keyed by nid in the trace; the source interpreter
records post-step state in ``deltas``. This projection joins the two
by symbol.

The projection requires the artifact's state-symbol-to-nid map; we
compute it once at registration and pass it as a closure argument.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from gurdy.core.interp.align import ProjectedField
from gurdy.core.interp.types import ReasoningStep, SourceStep


def make_projection(state_symbol_to_nid: Mapping[str, int]):
    """Build a ``Projection`` callable closed over the artifact's
    symbol table.

    Compares post-step ``pc``, ``reg_x1``..``reg_x31``, and ``halted``.
    Memory is not compared step-by-step (the BTOR2 mem state is an
    array; comparing whole arrays per step is expensive). A separate
    final-state check covers it; cross-check covers register/PC/halted.
    """

    sym = dict(state_symbol_to_nid)

    def projection(
        source_step: SourceStep, reasoning_step: ReasoningStep
    ) -> Sequence[ProjectedField]:
        deltas = source_step.deltas or {}
        regs = deltas.get("regs") or ()
        machine = (reasoning_step.layer_values or {}).get("machine") or {}

        fields: list[ProjectedField] = []

        # PC.
        if "pc" in sym:
            r_pc = machine.get(sym["pc"])
            s_pc = deltas.get("pc")
            if r_pc is not None and s_pc is not None:
                fields.append(
                    ProjectedField(
                        label="pc",
                        source_view=int(s_pc),
                        reasoning_view=int(r_pc),
                        agree=int(s_pc) == int(r_pc),
                    )
                )

        # Registers x1..x31.
        if regs and len(regs) >= 32:
            for r in range(1, 32):
                key = f"reg_x{r}"
                if key not in sym:
                    continue
                r_v = machine.get(sym[key])
                if r_v is None:
                    continue
                s_v = int(regs[r])
                fields.append(
                    ProjectedField(
                        label=key,
                        source_view=s_v,
                        reasoning_view=int(r_v),
                        agree=s_v == int(r_v),
                    )
                )

        # Halted.
        if "halted" in sym:
            r_h = machine.get(sym["halted"])
            s_h = deltas.get("halted")
            if r_h is not None and s_h is not None:
                fields.append(
                    ProjectedField(
                        label="halted",
                        source_view=bool(s_h),
                        reasoning_view=bool(r_h),
                        agree=bool(s_h) == bool(r_h),
                    )
                )

        return fields

    return projection


__all__ = ["make_projection"]
