"""The shared AArch64 language + interpreter (languages/aarch64 brief).

Registers the ``aarch64`` language with its deterministic source interpreter
(``interp.run``), reused by every AArch64 pair (``aarch64-btor2`` and
``aarch64-sail`` — ARCHITECTURE.md §6). The interpreter is a standalone
deliverable, owned by the language, not by the first pair that touches it.

Interpreter version: ``0.2`` — a strictly **additive** widening of the ``0.1``
thin ``ADD (immediate)`` slice (coverage ratchet, BENCHMARKS.md §5) to the
simple, no-flag/no-control-flow ALU family ``ADD``/``SUB`` (immediate) and
``MOVZ``. The change is additive: the ``0.1`` ``ADD`` behavior is byte-for-byte
unchanged and the ``ADD``-only ``decode`` is retained, so the cross-checked
``aarch64-sail`` route is undisturbed until its sibling agent mirrors the new
ops. Any change to observed behavior is a versioned event that re-validates
dependents (AGENTS.md §3).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from .interp import (
    OP_ADD,
    OP_MOVZ,
    OP_SUB,
    A64Program,
    Decoded,
    decode,
    decode_insn,
    program_from_words,
    run,
)

INTERPRETER_VERSION = "0.2"

__all__ = ["run", "A64Program", "Decoded", "decode", "decode_insn",
           "program_from_words", "OP_ADD", "OP_SUB", "OP_MOVZ",
           "INTERPRETER_VERSION"]

register_language(Language("aarch64", source_interpreter=run))
