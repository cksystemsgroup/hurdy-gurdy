"""The shared Sail language + interpreter (languages/sail brief).

Registers ``sail`` with the independent RISC-V executor built on the
Sail-derived ``Expr`` semantics (``rv64.EXEC``). Source of ``riscv-sail`` and
consumed by ``sail-btor2``.

Interpreter version: ``0.3`` — the RV64IMC RISC-V arm plus an *additive*
AArch64 arm (``aarch64.run_aarch64``, dispatched on ``isa=aarch64``) for the
``aarch64-sail`` route. The A64 arm covers the simple, no-flag/no-control-flow
ALU family ``ADD (immediate)``, ``SUB (immediate)`` (both 64-bit) and ``MOVZ``
(64-bit) — the ``0.2`` → ``0.3`` bump widens it from ``ADD``-only to also lower
``SUB``/``MOVZ`` via the same Sail-derived ``Expr`` vocabulary, mirroring the
``aarch64-btor2`` widening so the two AArch64→BTOR2 routes decide the same
constructs (branch agreement, PATHS.md §4-5). The A64 arm is strictly additive —
it leaves the RISC-V path byte-for-byte unchanged, and the prior ``ADD`` behavior
is unchanged — but bumping it is a versioned event (AGENTS.md §3), so the
dependents (``riscv-sail``, ``sail-btor2``) are re-validated against this version
(their full suites stay green).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from . import expr, rv64  # noqa: F401  (the semantic encoding)
from .interp import run

INTERPRETER_VERSION = "0.3"

__all__ = ["run", "expr", "rv64", "INTERPRETER_VERSION"]

register_language(Language("sail", source_interpreter=run))
