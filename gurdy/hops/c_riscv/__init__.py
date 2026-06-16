"""c_riscv — compile hop  C -> rv64-elf.

Source semantics group: ``cerberus-c`` (not Sail). Differential-only: the
agent builds against an independent reference and the gate validates
differentially (a CBMC/gcc differential lifts the reproducible compile hop to
``checked``). No ``machine_tool`` — the Sail BTOR2 machine is rv64-specific.
"""

from __future__ import annotations

from typing import Any

from gurdy.core.hop import Hop as HopEdge, Tier, register
from gurdy.hops.base import Hop, NotYetImplemented, TranslateResult, LiftResult

register(HopEdge("c_riscv", "compile", "c", "rv64-elf", Tier.reproducible))


class CRiscv(Hop):
    id = "c_riscv"
    kind = "compile"
    in_lang = "c"
    out_lang = "rv64-elf"

    def translate(self, source: Any, question: dict, *, path: str = "own") -> TranslateResult:
        # TODO(agent): compile C -> rv64 ELF deterministically (pinned toolchain),
        # emit a CONTRACT.md (reproducibility) + provenance. Differential-only
        # vs cerberus-c; a CBMC differential re-establishes `checked`.
        raise NotYetImplemented("c_riscv.translate [TODO(agent)]")

    def lift(self, artifact: Any, raw_solver_result: Any) -> LiftResult:
        raise NotYetImplemented("c_riscv.lift [TODO(agent)]")


HOP = CRiscv()
