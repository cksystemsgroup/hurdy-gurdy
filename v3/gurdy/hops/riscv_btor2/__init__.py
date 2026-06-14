"""riscv_btor2 — reasoning hop  rv64-elf -> btor2.

The showcase. Differential-only vs Sail-RISCV. Exposes **two reasoning
paths**:

  - ``own``     : the agent's independent specializing lowering (fast on
                  concrete programs; *validates* Sail);
  - ``machine`` : instantiate the sail-riscv group's verified BTOR2 machine
                  model (necessary for symbolic control flow / self-modifying
                  code; *trusted* via the one-time whole-machine proof).

The two may be cross-checked at runtime (a free Sail-vs-pair differential).
The agent may NOT use the ``machine`` path during construction — that would
break independence (enforced by the gate's independence audit).
"""

from __future__ import annotations

from typing import Any

from gurdy.core.hop import Hop as HopEdge, Tier, register
from gurdy.hops.base import Hop, NotYetImplemented, TranslateResult, LiftResult

register(HopEdge("riscv_btor2", "reasoning", "rv64-elf", "btor2", Tier.transparent))


class RiscvBtor2(Hop):
    id = "riscv_btor2"
    kind = "reasoning"
    in_lang = "rv64-elf"
    out_lang = "btor2"

    def paths(self) -> tuple[str, ...]:
        return ("own", "machine")

    def translate(self, source: Any, question: dict, *, path: str = "own") -> TranslateResult:
        if path == "machine":
            # TODO(agent): delegate to the group's verified machine model via
            # tools.sail_btor2_machine.instantiate(machine, source, question).
            raise NotYetImplemented("riscv_btor2.translate[machine] [TODO(agent)]")
        # path == "own"
        # TODO(agent): specializing lowering rv64 -> BTOR2 (static decode +
        # per-PC dispatch), built differential-only against dev_oracle=spike.
        raise NotYetImplemented("riscv_btor2.translate[own] [TODO(agent)]")

    def lift(self, artifact: Any, raw_solver_result: Any) -> LiftResult:
        # TODO(agent): lift a BTOR2 witness to rv64 facts on the pinned
        # projection (pc, x1..x31, halted).
        raise NotYetImplemented("riscv_btor2.lift [TODO(agent)]")


HOP = RiscvBtor2()
