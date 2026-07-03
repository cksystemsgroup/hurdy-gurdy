"""The shared Sail language + interpreter (languages/sail brief).

Registers ``sail`` with the independent RISC-V executor built on the
Sail-derived ``Expr`` semantics (``rv64.EXEC``). Source of ``riscv-sail`` and
consumed by ``sail-btor2``.

Interpreter version: ``0.7`` — the RV64IMC RISC-V arm plus an *additive*
AArch64 arm (``aarch64.run_aarch64``, dispatched on ``isa=aarch64``) for the
``aarch64-sail`` route. The A64 arm covers the simple, no-flag/no-control-flow
ALU family ``ADD (immediate)``, ``SUB (immediate)`` and ``MOVZ`` **plus** the NZCV
writes (``SUBS``/``CMP`` **and** ``ADDS``/``CMN`` immediate), the conditional
**and** unconditional control flow (``B.cond``, ``B``/``BL``), the first memory
access — the 64-bit unsigned-offset ``LDR``/``STR`` — **and** the **32-bit
(``W``-register) forms** of the ALU/flag-setting immediate instructions
(``ADD``/``SUB``/``MOVZ`` W and ``SUBS``/``CMP``/``ADDS``/``CMN`` W). The ``0.2`` →
``0.3`` bump widened the A64 arm from ``ADD``-only to also lower ``SUB``/``MOVZ``;
the ``0.3`` → ``0.4`` bump added ``SUBS``/``CMP`` + ``B.cond``; the ``0.4`` →
``0.5`` bump added the unconditional branch ``B``/``BL`` and the addition flag write
``ADDS``/``CMN``; the ``0.5`` → ``0.6`` bump added the 64-bit unsigned-offset
``LDR``/``STR`` over a byte-addressed, little-endian ``memory`` (a Python byte map;
the ``Expr`` IR is QF_BV-only, so only the LE byte-assembly is a Sail-derived
``Expr`` tree) with the fixed ``m0``–``m{MEM_WINDOW-1}`` memory-window observable;
the ``0.6`` → ``0.7`` bump mirrors the ``aarch64-btor2`` ``0.5`` → ``0.6`` widening
so the two AArch64→BTOR2 routes decide the **same** constructs again (full branch
agreement restored, ROUTES.md §4-5) — adding the **32-bit (``W``-register) ALU/flag
forms**: the op computes on the low 32 bits of the source (``slice(a, 31, 0)``), the
bv32 result **zero-extends** into the 64-bit destination (upper 32 bits of ``Xd``
become 0), and the ``SUBS``/``ADDS`` W flags are packed at **32-bit** width — all as
``Expr`` trees over the shared QF_BV vocabulary, matching ``aarch64-btor2``'s
``width``-parameterized datapath bit-for-bit, and switching the A64 decoder gate
from ``decode_insn_v5`` to ``decode_insn_v6``. The A64 arm is strictly additive — it
leaves the RISC-V path byte-for-byte unchanged, and the prior 64-bit
``ADD``/``SUB``/``MOVZ`` + ``SUBS``/``CMP`` + ``B.cond`` + ``B``/``BL`` +
``ADDS``/``CMN`` + ``LDR``/``STR`` behavior is unchanged — but bumping it is a
versioned event (AGENTS.md §3), so the dependents (``riscv-sail``, ``sail-btor2``)
are re-validated against this version (their full suites stay green).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from . import expr, rv64  # noqa: F401  (the semantic encoding)
from .interp import run

INTERPRETER_VERSION = "0.7"

__all__ = ["run", "expr", "rv64", "INTERPRETER_VERSION"]

register_language(Language("sail", source_interpreter=run))
