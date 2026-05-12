"""Example 07: partial binding + shadow events.

Build a tiny RV64 ELF with a conditional branch, run it through the
source interpreter in ``record_shadow=True`` mode with a partial
binding (one register marked ``FREE``), and print the recorded
branch events and free-field inventory.

Then build a v1.1.0 spec patch from the recorded trace via
``trace_to_branch_pins`` and compile a follow-up spec that pins
that prefix exactly. The flip flag lets you ask "same prefix, the
other direction at step k" in one line — the building block for a
propose-and-check loop (see example 08).

Run from the repo root:

    python examples/07_partial_binding.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gurdy.pairs.riscv_btor2  # noqa: F401  (registers the pair)
from gurdy.core.tools.compile import compile_spec
from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
from gurdy.pairs.riscv_btor2.source_interp.bindings import (
    FREE,
    RiscvInputBinding,
)
from gurdy.pairs.riscv_btor2.source_interp.interpreter import (
    RiscvSourceInterpreter,
)
from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    Property,
    RiscvBtor2Spec,
)
from gurdy.pairs.riscv_btor2.spec_helpers import trace_to_branch_pins
from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000
# addi a0, x0, 1 ; beq a0, x0, +8 ; ret
PROGRAM = bytes.fromhex("13051000" "63040500" "67800000")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "branch.elf"
        path.write_bytes(
            build_elf(PROGRAM, TEXT_BASE, [FuncDef("f", TEXT_BASE, len(PROGRAM))])
        )
        source = load_riscv_binary(path)

        # Partial binding: x1 left FREE (concretized to 0 by the
        # shadow interpreter, recorded in free_fields).
        binding = RiscvInputBinding(register_init={1: FREE})

        # Shadow run: records BranchEvent / MemoryAccessEvent per step.
        trace = RiscvSourceInterpreter().run(
            source, binding, max_steps=10, record_shadow=True
        )
        shadow = trace.final_state["shadow"]

        print("=== shadow events ===")
        for ev in shadow["branch_events"]:
            print(
                f"  step {ev['step']:>2} pc={ev['pc']:#x} "
                f"{ev['mnemonic']} taken={ev['taken']}"
            )
        for ev in shadow["memory_events"]:
            print(
                f"  step {ev['step']:>2} pc={ev['pc']:#x} "
                f"{ev['mnemonic']} addr={ev['addr']:#x} kind={ev['kind']}"
            )
        print(f"=== free fields ===\n  {shadow['free_fields']}")

        # Convert events into BranchPins; build a spec that pins
        # the recorded prefix and asks the BMC engine "is bad
        # reachable along *this* path?"
        pins = trace_to_branch_pins(trace)
        spec = RiscvBtor2Spec(
            binary=BinaryRef(path=str(path)),
            scope=AnalysisScope(entry_function="f"),
            assumptions=pins,
            property=Property(expression="false"),
            analysis=AnalysisDirective(engine="z3-bmc", bound=10),
        )
        artifact = compile_spec(spec, source_payload=path)
        print(
            f"=== compiled v{artifact.schema_version} artifact with "
            f"{len(pins)} BranchPin(s) ==="
        )
        print(
            "  volatile layer body length:",
            len(artifact.layers["volatile"].body),
            "bytes",
        )

        # Same prefix, opposite at the first branch.
        flipped_pins = trace_to_branch_pins(trace, flip_branch_at=pins[0].step)
        print(f"=== flipped pin at step {pins[0].step} ===")
        print(f"  before: {pins[0]}")
        print(f"  after:  {flipped_pins[0]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
