"""riscv-btor2 reasoning-side interpreter.

Wraps the BTOR2 single-cycle evaluator into a multi-step,
deterministic transition-system evaluator. Returns a framework
``ReasoningTrace`` whose ``layer_values`` carries the state nids per
step.
"""

from gurdy.pairs.riscv_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
from gurdy.pairs.riscv_btor2.reasoning_interp.interpreter import (
    Btor2ReasoningInterpreter,
)

__all__ = ["Btor2ReasoningBinding", "Btor2ReasoningInterpreter"]
