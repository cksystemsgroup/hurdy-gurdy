"""The shared AArch64 language + interpreter (languages/aarch64 brief).

Registers the ``aarch64`` language with its deterministic source interpreter
(``interp.run``), reused by every AArch64 pair (``aarch64-btor2`` and
``aarch64-sail`` — ARCHITECTURE.md §6). The interpreter is a standalone
deliverable, owned by the language, not by the first pair that touches it.

Interpreter version: ``0.3`` — a strictly **additive** widening of the ``0.2``
simple, no-flag/no-control-flow ALU family (``ADD``/``SUB`` immediate + ``MOVZ``)
(coverage ratchet, BENCHMARKS.md §5) that introduces the **first NZCV write** and
the **first conditional control flow**: ``SUBS (immediate)`` / ``CMP`` (sets the
NZCV flags) and ``B.cond`` (a conditional pc update reading NZCV). The change is
additive: the ``0.1``/``0.2`` behavior is byte-for-byte unchanged and the
narrower ``decode`` (``ADD``-only) and ``decode_insn`` (``ADD``/``SUB``/``MOVZ``)
decoders are retained as the ``aarch64-sail`` rejection gate, so that route is
undisturbed until its sibling agent mirrors the new ops; the ``0.3`` family is
decoded by ``decode_insn_v3``. Any change to observed behavior is a versioned
event that re-validates dependents (AGENTS.md §3).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from .interp import (
    OP_ADD,
    OP_BCOND,
    OP_MOVZ,
    OP_SUB,
    OP_SUBS,
    A64Program,
    Decoded,
    cond_holds,
    decode,
    decode_insn,
    decode_insn_v3,
    program_from_words,
    run,
)

INTERPRETER_VERSION = "0.3"

__all__ = ["run", "A64Program", "Decoded", "decode", "decode_insn",
           "decode_insn_v3", "cond_holds", "program_from_words",
           "OP_ADD", "OP_SUB", "OP_MOVZ", "OP_SUBS", "OP_BCOND",
           "INTERPRETER_VERSION"]

register_language(Language("aarch64", source_interpreter=run))
