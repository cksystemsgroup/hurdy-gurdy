"""The ``riscv-sail`` pair (ALU slice) — RISC-V → SAIL.

The front of the *indirect* RISC-V→BTOR2 branch: it lifts a RISC-V program
into the Sail model's representation, which ``sail-btor2`` then lowers. Its
whole reason to exist is the corroboration of the direct ``riscv-btor2``
translator via the path-grader's branch-agreement cross-check.
"""

from __future__ import annotations

from ...core import registry
from ...core.registry import Pair, Status
from ...core.types import Projection, Trace

# Importing the languages registers the shared interpreters this pair reuses.
from ...languages import riscv as _riscv  # noqa: F401
from ...languages import sail as _sail  # noqa: F401
from ...languages.riscv.interp import image_from_words
from ..sail_btor2.inventory import CORE_PROBES as _SAIL_CORE
from .translate import translate

_REGS = tuple(f"x{r}" for r in range(1, 32))
PROJECTION = Projection(("pc", *_REGS, "halted"))

# Reuse the Sail core word-lists as RISC-V image probes, so composed coverage
# can measure the Sail route's head.
PROBES = {
    name: {"image": image_from_words(p["words"]), "init_regs": {}}
    for name, p in _SAIL_CORE.items()
}


def lift(target_trace: Trace) -> Trace:
    return list(target_trace)   # routing front; squared end-to-end via the branch check


registry.register_pair(
    Pair(
        id="riscv-sail",
        source="riscv",
        target="sail",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="checked",
        translator_version="0.1",
        status=Status.PARTIAL,
        probes=PROBES,
    )
)

__all__ = ["translate", "lift", "PROJECTION"]
