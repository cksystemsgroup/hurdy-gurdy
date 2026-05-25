"""EVM concrete executor with shadow mode (P2)."""

from .disasm import Instruction, compute_jumpdest_table, disassemble
from .executor import EvmContext, MachineState, StepRecord, run, step

__all__ = [
    "Instruction",
    "disassemble",
    "compute_jumpdest_table",
    "MachineState",
    "EvmContext",
    "StepRecord",
    "step",
    "run",
]
