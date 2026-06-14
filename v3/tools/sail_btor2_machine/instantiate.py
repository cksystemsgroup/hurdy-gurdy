"""Instantiate a verified machine model for one program — the alt path.

``(machine, binary, question) -> btor2 instance``: load the binary into the
memory array, set PC to the entry, and weave in the question (constraints +
bad properties). Trivially correct given the machine is verified; this is
what ``riscv_btor2.translate(path="machine")`` delegates to.
"""

from __future__ import annotations

from typing import Any

from gurdy.hops.base import NotYetImplemented
from tools.sail_btor2_machine.generate import GeneratedMachine


def instantiate(machine: GeneratedMachine, binary: bytes, question: dict) -> Any:
    # TODO(agent): memory-init + pc-set + question instrumentation over the
    # fixed machine model. No per-instruction lowering happens here.
    raise NotYetImplemented("sail_btor2_machine.instantiate [TODO(agent)]")
