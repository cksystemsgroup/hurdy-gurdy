"""Whole-machine equivalence: the generated BTOR2 machine model vs Sail.

Two obligations, composed:

  1. per-instruction lemmas  ``encode(instr) == sail_relation(instr)``  for
     all inputs (QF_BV; the F3 lemmas) — discharged by an SMT solver;
  2. a harness lemma: fetch/decode/pc/control == Sail's ``step``.

Implementation-defined points (``idf_allowlist``) are subtracted. The result
is a ``MachineFidelityReport``; the machine gate publishes the realization
only when it is ``green``.
"""

from __future__ import annotations

from pathlib import Path

from gurdy.core.report import MachineFidelityReport
from gurdy.hops.base import NotYetImplemented
from tools.sail_btor2_machine.generate import GeneratedMachine


def verify(machine: GeneratedMachine, sail_model_dir: Path, idf_allowlist: list[str]) -> MachineFidelityReport:
    # TODO(machine-agent): discharge per-instruction QF_BV lemmas + harness
    # lemma against Sail's per-instruction relation / step. Subtract IDF.
    raise NotYetImplemented("sail_btor2_machine.verify [TODO(machine-agent)]")
