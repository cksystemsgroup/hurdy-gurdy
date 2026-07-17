"""The ``aarch64-btor2`` pair (thin slice) — AArch64 (A64) -> BTOR2.

A second front-end into the BTOR2 hub, demonstrating the translator
architecture is ISA-portable (riscv-btor2 shape re-aimed at A64). It reuses the
shared BTOR2 interpreter, the commuting-square oracle, the coverage harness, and
the ``btor2-smtlib`` decide path (via the BTOR2 ``bad`` it emits) — contributing
only the AArch64 interpreter (a standalone shared deliverable, reused later by
``aarch64-sail``) and the per-instruction lowering. ``square()`` runs the
commuting check ``I_s(p) ≡_π L(I_t(T(p)))`` through the framework oracle.

Scope (interp ``0.5``): the ALU family ``ADD``/``SUB`` (immediate) + ``MOVZ``
(all 64-bit), the NZCV writes (``SUBS``/``CMP`` and ``ADDS``/``CMN`` immediate),
the conditional and unconditional control flow (``B.cond``, full condition table;
``B``/``BL``), **plus the first memory access** — the 64-bit unsigned-offset
``LDR``/``STR`` over a byte-addressed, little-endian memory with a fixed
``m0``–``m{MEM_WINDOW-1}`` memory-window observable. Status: ``partial``
(PAIRING.md §1 "Start thin, then widen").
"""

from __future__ import annotations

from typing import Any

from ...core import oracle, registry
from ...core.registry import Pair, Status
from ...core.types import AlignResult, Projection

# Importing the languages registers the shared interpreters this pair reuses.
from ...languages import aarch64 as _aarch64  # noqa: F401
from ...languages import btor2 as _btor2  # noqa: F401
from ...languages.aarch64.interp import MEM_WINDOW, SP_DEFAULT
from .inventory import ALL_PROBES
from .lift import lift
from .translate import translate

_REGS = tuple(f"x{r}" for r in range(31))
_MEM = tuple(f"m{i}" for i in range(MEM_WINDOW))   # the byte-memory window observable
# π: post-step pc, x0..x30, sp, the NZCV flags, the memory-window bytes, and the
# halt/trap flag — the AArch64 interpreter's observables mapped onto the BTOR2
# state variables (pairs/aarch64-btor2 brief). Kept compatible with aarch64-sail.
PROJECTION = Projection(("pc", *_REGS, "sp", "nzcv", *_MEM, "halted"))

registry.register_pair(
    Pair(
        id="aarch64-btor2",
        source="aarch64",
        target="btor2",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="checked",
        translator_version="0.5",
        # Branch-corroboration provenance (SCALING.md §9; protected):
        # the prose Arm ARM (vs the Sail branch).
        semantic_artifact="arm-prose-manual",
        status=Status.PARTIAL,
        probes=ALL_PROBES,
    )
)

__all__ = ["translate", "lift", "square", "PROJECTION"]


def square(program: dict[str, Any], max_steps: int = 10_000) -> AlignResult:
    """Check the commuting square for ``program`` (no solver needed): run the
    shared AArch64 interpreter and the translate->BTOR2-interpret->carry-back
    path and align them under ``π``.

    Both interpreters record post-step state, but a BTOR2 run's first row is the
    *initial* state, so the source trace (which starts after the first
    instruction) aligns with the BTOR2 trace shifted by one cycle.
    """
    pair = registry.get_pair("aarch64-btor2")
    image = program["image"]
    init_regs = program.get("init_regs", {})
    init_sp = int(program.get("init_sp", SP_DEFAULT))
    init_nzcv = int(program.get("init_nzcv", 0))
    init_mem = program.get("init_mem", {})

    artifact = translate({**program, "init_sp": init_sp})
    src = list(
        pair.source_interpreter(
            image,
            {"regs": init_regs, "sp": init_sp, "nzcv": init_nzcv, "mem": init_mem},
            max_steps=max_steps,
        )
    )
    n = len(src)
    # Seed the BTOR2 ``mem`` array's initial bytes to match the source's
    # ``init_mem`` (the window states are init-seeded in T; the array itself is
    # seeded here via the btor2 interpreter's per-state override, keyed by symbol).
    tbind: dict[str, Any] = {"steps": n + 1}
    if init_mem:
        tbind["state"] = {"mem": {int(a): int(v) & 0xFF for a, v in init_mem.items()}}
    btrace = pair.target_interpreter(artifact, tbind)
    carried = lift(btrace)
    return oracle.align(src, carried[1 : n + 1], pair.projection)


# The square oracle is defined above; wire it onto the registered pair so
# the coverage harness can measure Definition 4.6's conjunction (accepted
# AND square-passing) instead of acceptance alone.
registry.attach_square("aarch64-btor2", square)
