"""The ``sail-btor2`` pair (ALU slice) — SAIL → BTOR2.

The *indirect* arm of the RISC-V→BTOR2 branch: it derives the BTOR2 model from
the Sail-derived ``Expr`` semantics, independently of the direct ``riscv-btor2``
translator. Composed after ``riscv-sail`` it gives a second ``riscv → smtlib``
route, which the path-grader's ``branch_agreement`` cross-checks against the
direct one (PATHS.md §4-5).
"""

from __future__ import annotations

from typing import Any

from ...core import oracle, registry
from ...core.registry import Pair, Status
from ...core.types import AlignResult, Projection

# Importing the languages registers the shared interpreters this pair reuses.
from ...languages import btor2 as _btor2  # noqa: F401
from ...languages import sail as _sail  # noqa: F401
from .inventory import ALU_PROBES
from .lift import lift
from .translate import translate

_REGS = tuple(f"x{r}" for r in range(1, 32))
PROJECTION = Projection(("pc", *_REGS, "halted"))

registry.register_pair(
    Pair(
        id="sail-btor2",
        source="sail",
        target="btor2",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="checked",
        translator_version="0.1",
        status=Status.PARTIAL,
        probes=ALU_PROBES,
    )
)

__all__ = ["translate", "lift", "square", "PROJECTION"]


def square(program: dict[str, Any], max_steps: int = 10_000) -> AlignResult:
    """Commuting square for a Sail program: the Sail interpreter vs
    translate→BTOR2-interpret→carry-back, aligned under ``π``."""
    pair = registry.get_pair("sail-btor2")
    init_regs = program.get("init_regs", {})
    artifact = translate(program)
    src = list(pair.source_interpreter(program, {"regs": init_regs}, max_steps=max_steps))
    n = len(src)
    btrace = pair.target_interpreter(artifact, {"steps": n + 1})
    carried = lift(btrace)
    return oracle.align(src, carried[1 : n + 1], pair.projection)
