"""The shared AArch64 language + interpreter (languages/aarch64 brief).

Registers the ``aarch64`` language with its deterministic source interpreter
(``interp.run``), reused by every AArch64 pair (``aarch64-btor2`` and
``aarch64-sail`` — ARCHITECTURE.md §6). The interpreter is a standalone
deliverable, owned by the language, not by the first pair that touches it.

Interpreter version: ``0.5`` — a strictly **additive** widening of the ``0.4``
family (``ADD``/``SUB`` immediate + ``MOVZ`` + ``SUBS``/``CMP`` + ``ADDS``/``CMN``
+ ``B.cond`` + ``B``/``BL``) (coverage ratchet, BENCHMARKS.md §5) that introduces
the **first memory access**: the 64-bit unsigned-offset ``LDR``/``STR``
(``Xt, [Xn|SP, #imm]``) over a byte-addressed, little-endian memory, with a fixed
``m0``–``m{MEM_WINDOW-1}`` memory-window observable. The change is additive: the
``0.1``–``0.4`` behavior is byte-for-byte unchanged and the narrower ``decode``
(``ADD``-only), ``decode_insn`` (``ADD``/``SUB``/``MOVZ``), ``decode_insn_v3``
(+``SUBS``/``CMP``+``B.cond``) and ``decode_insn_v4`` (+``B``/``BL``+``ADDS``/
``CMN``) decoders are retained as the ``aarch64-sail`` rejection gate, so that
route is undisturbed until its sibling agent mirrors the new ops; the ``0.5``
family is decoded by ``decode_insn_v5``. Any change to observed behavior is a
versioned event that re-validates dependents (AGENTS.md §3).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from .interp import (
    MEM_WINDOW,
    OP_ADD,
    OP_ADDS,
    OP_B,
    OP_BCOND,
    OP_LDR,
    OP_MOVZ,
    OP_STR,
    OP_SUB,
    OP_SUBS,
    A64Program,
    Decoded,
    cond_holds,
    decode,
    decode_insn,
    decode_insn_v3,
    decode_insn_v4,
    decode_insn_v5,
    program_from_words,
    run,
)

INTERPRETER_VERSION = "0.5"

__all__ = ["run", "A64Program", "Decoded", "decode", "decode_insn",
           "decode_insn_v3", "decode_insn_v4", "decode_insn_v5", "cond_holds",
           "program_from_words", "MEM_WINDOW",
           "OP_ADD", "OP_SUB", "OP_MOVZ", "OP_SUBS", "OP_ADDS", "OP_BCOND",
           "OP_B", "OP_LDR", "OP_STR", "INTERPRETER_VERSION"]

register_language(Language("aarch64", source_interpreter=run))
