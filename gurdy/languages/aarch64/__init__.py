"""The shared AArch64 language + interpreter (languages/aarch64 brief).

Registers the ``aarch64`` language with its deterministic source interpreter
(``interp.run``), reused by every AArch64 pair (``aarch64-btor2`` today, and
``aarch64-sail`` later — ARCHITECTURE.md §6). The interpreter is a standalone
deliverable, owned by the language, not by the first pair that touches it.

Interpreter version: ``0.1`` — the thin ``ADD (immediate)`` slice. Any change
to its observed behavior is a versioned event that re-validates dependents
(AGENTS.md §3).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from .interp import A64Program, Decoded, decode, program_from_words, run

INTERPRETER_VERSION = "0.1"

__all__ = ["run", "A64Program", "Decoded", "decode", "program_from_words",
           "INTERPRETER_VERSION"]

register_language(Language("aarch64", source_interpreter=run))
