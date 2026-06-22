"""The shared EVM language + interpreter (languages/evm brief).

Registers the ``evm`` language with its deterministic source interpreter,
reused by every EVM pair (currently ``evm-btor2``). The interpreter is a
256-bit (bv256) stack machine; its scope is the thin ``PUSH1``/``ADD``/``STOP``
slice (the rest hard-aborts ``unsupported: evm:<opcode>``). KEVM is the
recommended external oracle (BENCHMARKS.md §4).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from . import asm
from .interp import STACK_SIZE, WORD, EvmProgram, program_from_bytes, run

__all__ = ["run", "EvmProgram", "program_from_bytes", "asm", "STACK_SIZE", "WORD"]

register_language(Language("evm", source_interpreter=run))
