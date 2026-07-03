"""The ``c-riscv`` pair — C → RISC-V via a pinned compiler.

The platform's highest-altitude pair and the head of the long route to a
solver. Fidelity is ``reproducible`` (byte-identical ELF from the pinned
toolchain + flags), re-established to ``checked`` downstream by the
RISC-V→BTOR2 route(s) and a C-level differential. ``reproduce()`` is the
twice-and-diff evidence.
"""

from __future__ import annotations

from typing import Any

from ...core import registry
from ...core.registry import Pair, Status
from ...core.types import Projection

# Importing the languages registers what the pair reuses.
from ...languages import c as _c  # noqa: F401
from ...languages import riscv as _riscv  # noqa: F401
from .differential import cbmc_reg_eq
from .differential import differential as cbmc_differential
from .lift import c_function_at, c_line_at, find_addr2line, lift
from .translate import compile_c, find_gcc, translate

_REGS = tuple(f"x{r}" for r in range(1, 32))
PROJECTION = Projection(("pc", *_REGS, "halted"))

registry.register_pair(
    Pair(
        id="c-riscv",
        source="c",
        target="riscv",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="reproducible",
        translator_version="gcc-rv64im-O2.0",
        status=Status.PARTIAL,
    )
)

__all__ = ["translate", "lift", "compile_c", "c_function_at", "c_line_at",
           "find_addr2line", "find_gcc", "reproduce",
           "cbmc_differential", "cbmc_reg_eq"]


def reproduce(source: str) -> bool:
    """The reproducibility evidence: the same source compiles byte-identically."""
    return translate({"source": source}) == translate({"source": source})
