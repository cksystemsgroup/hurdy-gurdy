"""evm-btor2 reasoning-side interpreter (P3).

Ports the riscv-btor2 Btor2ReasoningInterpreter verbatim (with
PAIR_ID and INTERPRETER_VERSION adapted for evm-btor2) per
V2_BOOTSTRAP.md §3.2.  The underlying BTOR2 parser/evaluator lives
in ``gurdy.pairs.evm_btor2.btor2`` and is domain-free.
"""

from gurdy.pairs.evm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
from gurdy.pairs.evm_btor2.reasoning_interp.interpreter import (
    Btor2ReasoningInterpreter,
    INTERPRETER_VERSION,
)

__all__ = ["Btor2ReasoningBinding", "Btor2ReasoningInterpreter", "INTERPRETER_VERSION"]
