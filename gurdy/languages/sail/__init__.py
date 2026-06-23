"""The shared Sail language + interpreter (languages/sail brief).

Registers ``sail`` with the independent RISC-V executor built on the
Sail-derived ``Expr`` semantics (``rv64.EXEC``). Source of ``riscv-sail`` and
consumed by ``sail-btor2``.

Interpreter version: ``0.6`` — the RV64IMC RISC-V arm plus an *additive*
AArch64 arm (``aarch64.run_aarch64``, dispatched on ``isa=aarch64``) for the
``aarch64-sail`` route. The A64 arm covers the simple, no-flag/no-control-flow
ALU family ``ADD (immediate)``, ``SUB (immediate)`` (both 64-bit) and ``MOVZ``
(64-bit) **plus** the NZCV writes (``SUBS``/``CMP`` **and** ``ADDS``/``CMN``
immediate), the conditional **and** unconditional control flow (``B.cond``,
``B``/``BL``), **and the first memory access** — the 64-bit unsigned-offset
``LDR``/``STR``. The ``0.2`` → ``0.3`` bump widened the A64 arm from ``ADD``-only
to also lower ``SUB``/``MOVZ``; the ``0.3`` → ``0.4`` bump added ``SUBS``/``CMP`` +
``B.cond``; the ``0.4`` → ``0.5`` bump added the unconditional branch ``B``/``BL``
and the addition flag write ``ADDS``/``CMN``; the ``0.5`` → ``0.6`` bump mirrors
the ``aarch64-btor2`` ``0.5`` widening so the two AArch64→BTOR2 routes decide the
**same** constructs again (full branch agreement restored, PATHS.md §4-5) — adding
the 64-bit unsigned-offset ``LDR``/``STR`` over a byte-addressed, little-endian
``memory`` (a Python byte map; the ``Expr`` IR is QF_BV-only, so only the LE
byte-assembly is a Sail-derived ``Expr`` tree) with the fixed
``m0``–``m{MEM_WINDOW-1}`` memory-window observable (the additive ``0.6``
projection extension, mirroring ``aarch64-btor2``'s window). The A64 arm is
strictly additive — it leaves the RISC-V path byte-for-byte unchanged, and the
prior ``ADD``/``SUB``/``MOVZ`` + ``SUBS``/``CMP`` + ``B.cond`` + ``B``/``BL`` +
``ADDS``/``CMN`` behavior is unchanged — but bumping it is a versioned event
(AGENTS.md §3), so the dependents (``riscv-sail``, ``sail-btor2``) are re-validated
against this version (their full suites stay green).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from . import expr, rv64  # noqa: F401  (the semantic encoding)
from .interp import run

INTERPRETER_VERSION = "0.6"

__all__ = ["run", "expr", "rv64", "INTERPRETER_VERSION"]

register_language(Language("sail", source_interpreter=run))
