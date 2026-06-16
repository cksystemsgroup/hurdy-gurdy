"""The shared RISC-V language + interpreter (languages/riscv brief).

Registers the ``riscv`` language with its deterministic source interpreter.
Reused by every RISC-V pair (``c-riscv``, ``riscv-btor2``, ``riscv-sail``).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from .interp import RiscvImage, image_from_words, run

__all__ = ["run", "RiscvImage", "image_from_words"]

register_language(Language("riscv", source_interpreter=run))
