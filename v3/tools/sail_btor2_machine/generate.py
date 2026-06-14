"""Generate a BTOR2 machine model from a Sail ISA model (LLM-driven).

Each Sail ``execute`` clause -> one BTOR2 sub-circuit, muxed by the decoder.
The harness (state + fetch/decode/pc shape) is fixed; the generator supplies
per-instruction execute logic + the decoder, emitting per-instruction
provenance (Sail clause <-> BTOR2 fragment) for the verifier and triage.

This is the *referential* agent's tool: it MAY read Sail (its job is to
mirror it). Pair-build agents must not call it during construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from gurdy.hops.base import NotYetImplemented
from tools.sail_btor2_machine.harness import ISAConfig


@dataclass
class GeneratedMachine:
    realization: str                          # "sail-riscv@btor2-machine"
    model_path: Path | None = None            # model.btor2
    decode_map: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)   # instr -> {sail_clause, btor2_fragment}


def generate(sail_model_dir: Path, cfg: ISAConfig, *, out_dir: Path) -> GeneratedMachine:
    # TODO(machine-agent): drive the LLM to fill harness EXECUTE[op] + DECODE
    # from the Sail clauses; emit model.btor2 + decode_map + provenance.
    raise NotYetImplemented("sail_btor2_machine.generate [TODO(machine-agent)]")
