"""wasm-btor2 reasoning-side interpreter.

Wraps the BTOR2 single-cycle evaluator into a multi-step,
deterministic transition-system evaluator. Returns a framework
``ReasoningTrace`` whose ``layer_values`` carries the state nids per
step.

Copied from ``gurdy.pairs.riscv_btor2.reasoning_interp`` at
INTERPRETER_VERSION 1.1.0 per V2_BOOTSTRAP.md §3.2. The btor2
subpackage (parser, evaluator, nodes, printer) is also copied under
this pair so the wasm-btor2 simulator is fully self-contained and
can diverge from riscv-btor2 as WASM-specific BTOR2 patterns emerge.
"""

from gurdy.pairs.wasm_btor2.reasoning_interp.bindings import Btor2ReasoningBinding
from gurdy.pairs.wasm_btor2.reasoning_interp.interpreter import (
    Btor2ReasoningInterpreter,
    INTERPRETER_VERSION,
)

__all__ = ["Btor2ReasoningBinding", "Btor2ReasoningInterpreter", "INTERPRETER_VERSION"]
