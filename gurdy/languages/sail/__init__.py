"""The shared Sail language + interpreter (languages/sail brief).

Registers ``sail`` with the independent RISC-V executor built on the
Sail-derived ``Expr`` semantics (``rv64.EXEC``). Source of ``riscv-sail`` and
consumed by ``sail-btor2``.

Interpreter version: ``0.2`` — the RV64IMC RISC-V arm plus an *additive*
AArch64 (``ADD``-immediate) arm (``aarch64.run_aarch64``, dispatched on
``isa=aarch64``) for the ``aarch64-sail`` route. The A64 arm is strictly
additive — it leaves the RISC-V path byte-for-byte unchanged — but adding it is
a versioned event (AGENTS.md §3), so the dependents (``riscv-sail``,
``sail-btor2``) are re-validated against this version (their full suites stay
green).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from . import expr, rv64  # noqa: F401  (the semantic encoding)
from .interp import run

INTERPRETER_VERSION = "0.2"

__all__ = ["run", "expr", "rv64", "INTERPRETER_VERSION"]

register_language(Language("sail", source_interpreter=run))
