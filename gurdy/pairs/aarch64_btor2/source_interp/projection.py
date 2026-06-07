"""Projection from BTOR2 reasoning steps to AArch64 source steps (Stage 7.E
aarch64 Tier-2: step-level alignment).

The aarch64-btor2 schema pins state symbol names: ``pc``, ``reg_x{N}`` for
N=0..30, ``sp``, ``nzcv``, ``mem``, ``halted`` (see
``translation/layers.emit_machine``). The reasoning interpreter records state
values keyed by nid in the trace; the source interpreter records post-step
state in ``deltas`` (``pc``, ``regs`` (x0..x30), ``sp``, ``nzcv``, ``halted``).
This projection joins the two by symbol so the alignment oracle can compare
them step-for-step; a divergence localizes a translation bug to a step and a
named field.

The projection requires the artifact's state-symbol-to-nid map, computed once
at registration and passed as a closure argument (mirrors riscv-btor2).
"""

from __future__ import annotations

from typing import Mapping, Sequence

from gurdy.core.interp.align import ProjectedField
from gurdy.core.interp.types import ReasoningStep, SourceStep


def make_projection(state_symbol_to_nid: Mapping[str, int]):
    """Build a ``Projection`` callable closed over the artifact's symbol table.

    Compares post-step ``pc``, ``reg_x0``..``reg_x30``, ``sp``, ``nzcv``, and
    ``halted``. Memory is not compared step-by-step (the BTOR2 ``mem`` state is
    an array; whole-array per-step comparison is expensive) — a final-state
    check covers it, and the cross-check covers register/PC/flags/halted.
    """

    sym = dict(state_symbol_to_nid)

    def _bv(name: str, source_val, reasoning_val) -> ProjectedField | None:
        nid = sym.get(name)
        if nid is None or reasoning_val is None or source_val is None:
            return None
        s, r = int(source_val), int(reasoning_val)
        return ProjectedField(label=name, source_view=s, reasoning_view=r, agree=s == r)

    def projection(
        source_step: SourceStep, reasoning_step: ReasoningStep
    ) -> Sequence[ProjectedField]:
        deltas = source_step.deltas or {}
        regs = deltas.get("regs") or ()
        machine = (reasoning_step.layer_values or {}).get("machine") or {}

        fields: list[ProjectedField] = []

        # PC.
        f = _bv("pc", deltas.get("pc"), machine.get(sym.get("pc")))
        if f is not None:
            fields.append(f)

        # General registers x0..x30.
        if regs and len(regs) >= 31:
            for r in range(31):
                f = _bv(f"reg_x{r}", regs[r], machine.get(sym.get(f"reg_x{r}")))
                if f is not None:
                    fields.append(f)

        # Stack pointer and condition flags.
        for name in ("sp", "nzcv"):
            f = _bv(name, deltas.get(name), machine.get(sym.get(name)))
            if f is not None:
                fields.append(f)

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
