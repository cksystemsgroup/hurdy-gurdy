"""The fixed, ISA-agnostic CPU skeleton the generator fills.

State and transition *shape* are independent of the ISA; the generator
supplies only the per-instruction ``execute`` logic and the decoder. The
program is data in the initial memory array.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StateVar:
    name: str
    sort: str           # BTOR2 sort, e.g. "bv64" or "array bv64 bv8"
    note: str = ""


# The skeleton state for a generic von-Neumann ISA machine. An ISA config
# (XLEN, register count, CSR set) instantiates the concrete sorts.
SKELETON_STATE: tuple[StateVar, ...] = (
    StateVar("pc", "bv<XLEN>", "program counter"),
    StateVar("regfile", "array bv<RIDX> bv<XLEN>", "general-purpose registers"),
    StateVar("mem", "array bv<XLEN> bv8", "byte-addressed memory; holds the program"),
    StateVar("csrs", "array bv12 bv<XLEN>", "control/status registers"),
    StateVar("halted", "bv1", "halt flag"),
)

# The transition shape: one fetch -> decode -> execute -> pc-update step.
TRANSITION_SHAPE = (
    "fetch:   instr = read32(mem, pc)",
    "decode:  fields = DECODE(instr)            # generator-supplied",
    "execute: next_state = mux over opcode of EXECUTE[op](state, fields)  # generator-supplied",
    "pc:      next_pc = EXECUTE[op].next_pc or pc + 4",
)


@dataclass
class ISAConfig:
    """An instantiation of the skeleton for a concrete ISA."""

    isa: str                       # "rv64"
    xlen: int = 64
    ridx_bits: int = 5             # 32 GPRs
    extensions: tuple[str, ...] = field(default_factory=lambda: ("I", "M"))
