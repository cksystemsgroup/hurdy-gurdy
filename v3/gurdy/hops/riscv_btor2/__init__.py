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
            # Runtime-only: delegate to the group's verified machine model via
            # tools.sail_btor2_machine.instantiate(machine, source, question).
            # Kept a stub here — the own (independent) path is this hop's job.
            raise NotYetImplemented("riscv_btor2.translate[machine] [TODO(agent)]")

        # path == "own": the agent's independent specializing lowering. Static
        # decode of the concrete program (no Sail, no machine-model crib) into a
        # program-specific BTOR2 transition system with a per-PC dispatch.
        from pathlib import Path

        from gurdy.hops.riscv_btor2 import btor2, decode, elf

        data = source if isinstance(source, (bytes, bytearray)) else Path(source).read_bytes()
        prog = elf.load(bytes(data))
        ops = decode.decode_program(prog)
        checks = (question or {}).get("checks")          # optional [(reg, expected)]
        model = btor2.lower(ops, prog.entry, checks=checks)
        return TranslateResult(
            artifact=model.text.encode(),
            annotation={
                "ops": ops,
                "entry": prog.entry,
                "n_insns": len(ops),
                "reg_state": model.reg_state,
                "pc_state": model.pc_state,
                "halted_state": model.halted_state,
                "end_pc": model.end_pc,
            },
            path="own",
        )

    def lift(self, artifact: Any, raw_solver_result: Any) -> LiftResult:
        """Map a solved/run final state to rv64 facts on the pinned projection
        (pc, x1..x31, halted). ``raw_solver_result`` is the register assignment
        the reasoning engine produced (a ``{reg_index: value}`` mapping, or a
        dict carrying ``regs``/``pc``/``halted``)."""
        res = raw_solver_result or {}
        regs = res.get("regs", res) if isinstance(res, dict) else {}
        facts: dict = {
            "pc": res.get("pc") if isinstance(res, dict) else None,
            "halted": res.get("halted", True) if isinstance(res, dict) else True,
        }
        for k in range(1, 32):
            facts[f"x{k}"] = int(regs.get(k, 0)) & ((1 << 64) - 1)
        return LiftResult(facts=facts, witness=raw_solver_result)


HOP = RiscvBtor2()
