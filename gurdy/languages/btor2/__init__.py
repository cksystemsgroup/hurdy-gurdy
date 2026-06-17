"""The shared BTOR2 language + interpreter (languages/btor2 brief).

Registers ``btor2`` with one model-agnostic interpreter serving both roles:
target of the BTOR2 front-ends (``riscv-btor2``, ``sail-btor2``, …) and source
of ``btor2-smtlib``.
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from .eval import interpret, step
from .model import System, canonicalize, from_text, to_text
from .witness import Witness, check_witness, parse_witness, replay

__all__ = ["interpret", "step", "from_text", "to_text", "canonicalize", "System",
           "parse_witness", "replay", "check_witness", "Witness"]

register_language(
    Language("btor2", source_interpreter=interpret, target_interpreter=interpret)
)
