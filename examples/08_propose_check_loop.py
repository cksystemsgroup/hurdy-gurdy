"""Example 08: propose-and-check loop with a dual-role invariant.

Propose a candidate invariant on a tiny RV64 program by marking a
``CycleInvariant`` as ``dual_role=True``. The translator emits the
predicate as both:

- an ``assumption`` in the ``constraint`` layer (downstream use), and
- a negated ``bad`` clause in the new ``volatile`` layer (this
  question's falsification target).

The two are linked in the annotation via ``paired_with_nid``.

The propose-and-check pattern, sketched:

1. LLM proposes an invariant ``P``.
2. ``check(spec, binding)`` falsifies ``P`` on cheap concrete inputs.
3. If P survives, compile the spec and dispatch to a BMC engine; the
   volatile bad clause is the falsification target.
4. If BMC also can't falsify within the bound, the invariant survives
   *this question* — the LLM either declares it learned or escalates
   to an inductive solver.

This example shows step 1 (proposal) and 3 (compile + inspect); the
LLM-side iteration is the consumer's job.

Run from the repo root:

    python examples/08_propose_check_loop.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gurdy.pairs.riscv_btor2  # noqa: F401
from gurdy.core.tools.compile import compile_spec
from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    CycleInvariant,
    Property,
    RiscvBtor2Spec,
)
from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000
# ADDI a0, x0, 5 ; ADDI a0, a0, 3 ; ECALL → a0 = 8, halted.
PROGRAM = bytes.fromhex("13055000" "13053500" "73000000")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "addchain.elf"
        path.write_bytes(
            build_elf(PROGRAM, TEXT_BASE, [FuncDef("f", TEXT_BASE, len(PROGRAM))])
        )

        # Propose: "a0 is always < 100." The translator turns
        # dual_role=True into a paired (constraint, volatile-bad)
        # emission — assume the predicate downstream AND check it
        # this question.
        proposal = CycleInvariant(
            expression="ltu(reg(10), 100)",
            provenance="proposal_v0",
            dual_role=True,
        )

        spec = RiscvBtor2Spec(
            binary=BinaryRef(path=str(path)),
            scope=AnalysisScope(entry_function="f"),
            assumptions=(proposal,),
            property=Property(expression="false"),
            analysis=AnalysisDirective(engine="z3-bmc", bound=8),
        )
        artifact = compile_spec(spec, source_payload=path)

        print(f"=== compiled v{artifact.schema_version} artifact ===")
        print(
            f"  constraint layer: {len(artifact.layers['constraint'].body)} bytes"
        )
        print(
            f"  volatile layer:   {len(artifact.layers['volatile'].body)} bytes"
        )

        # Inspect the paired annotations: constraint side (assumption)
        # and volatile side (bad) carry paired_with_nid pointing at
        # each other.
        c_entries = [
            a
            for a in artifact.annotation.entries
            if a.layer == "constraint" and a.source_mapping
            and a.source_mapping.get("dual_role") is True
        ]
        v_entries = [
            a
            for a in artifact.annotation.entries
            if a.layer == "volatile" and a.source_mapping
            and a.source_mapping.get("role") == "dual_role_check"
        ]
        print(f"=== dual-role pair ===")
        for c in c_entries:
            print(f"  constraint nid {c.nid}: {c.source_mapping}")
        for v in v_entries:
            print(
                f"  volatile bad nid {v.nid}: paired_with_nid="
                f"{v.source_mapping['paired_with_nid']} "
                f"expression={v.source_mapping['expression']!r}"
            )

        # The LLM's loop would now dispatch the artifact. Each
        # surviving proposal narrows the spec for follow-up questions.
        # We stop here — the framework supplies primitives; the loop
        # itself lives in the LLM (or in the user's script).
        print(
            "\nnext step: dispatch(artifact, spec.analysis) and lift the verdict;\n"
            "if the volatile-bad clause is reachable, the proposal is refuted."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
