"""The ``riscv-btor2`` pair (thin slice) — RV64I -> BTOR2.

Registers the pair (reusing the shared RISC-V and BTOR2 interpreters) and
provides ``square()``, which runs the commuting-square check
``I_s(p) ≡_π L(I_t(T(p)))`` through the framework oracle.
"""

from __future__ import annotations

from typing import Any

from ...core import oracle, registry
from ...core.registry import Pair, Status
from ...core.types import AlignResult, Projection

# Importing the languages registers the shared interpreters this pair reuses.
from ...languages import btor2 as _btor2  # noqa: F401
from ...languages import riscv as _riscv  # noqa: F401
from .inventory import RV64I_PROBES
from .lift import lift
from .translate import translate

_REGS = tuple(f"x{r}" for r in range(1, 32))
PROJECTION = Projection(("pc", *_REGS, "halted"))

register_pair_result = registry.register_pair(
    Pair(
        id="riscv-btor2",
        source="riscv",
        target="btor2",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="checked",
        translator_version="0.1",
        status=Status.PARTIAL,
        probes=RV64I_PROBES,
    )
)

__all__ = ["translate", "lift", "square", "PROJECTION"]


def square(program: dict[str, Any], max_steps: int = 10_000) -> AlignResult:
    """Check the commuting square for ``program`` (no solver needed): run the
    RISC-V interpreter and the translate->BTOR2-interpret->carry-back path and
    align them under ``π``.

    Both interpreters record post-step state, but a BTOR2 run's first row is
    the *initial* state, so the source trace (which starts after the first
    instruction) aligns with the BTOR2 trace shifted by one cycle.
    """
    pair = registry.get_pair("riscv-btor2")
    image = program["image"]
    init_regs = program.get("init_regs", {})

    initial_mem = dict(image.mem)  # snapshot before the source run mutates it (stores)
    artifact = translate(program)
    src = list(pair.source_interpreter(image, {"regs": init_regs}, max_steps=max_steps))
    n = len(src)
    btrace = pair.target_interpreter(
        artifact, {"steps": n + 1, "state": {"mem": initial_mem}}
    )
    carried = lift(btrace)
    return oracle.align(src, carried[1 : n + 1], pair.projection)
