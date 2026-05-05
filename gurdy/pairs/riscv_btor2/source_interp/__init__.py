"""riscv-btor2 source-side interpreter.

Wraps the existing concrete RV64 simulator (``..lift.simulator``) into
the framework's ``SourceInterpreter`` protocol with a structured input
binding and a structured per-step trace. The simulator code itself
remains the soundness ground truth and is shared with witness replay.
"""

from gurdy.pairs.riscv_btor2.source_interp.bindings import RiscvInputBinding
from gurdy.pairs.riscv_btor2.source_interp.interpreter import RiscvSourceInterpreter

__all__ = ["RiscvInputBinding", "RiscvSourceInterpreter"]
