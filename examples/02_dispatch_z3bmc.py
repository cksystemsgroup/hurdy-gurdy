"""Example 02: compile a spec, dispatch through Z3 BMC, print the verdict.

The full pipeline: source -> compile -> dispatch -> verdict, with no
LLM in the loop. The LLM would normally orchestrate this and decide
what to ask next based on the verdict.
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
from gurdy.core.tools.dispatch import dispatch
from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    Property,
    RiscvBtor2Spec,
)
from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000
ADD2 = bytes.fromhex("13050100" "13051500" "67800000")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "add2.elf"
        path.write_bytes(build_elf(ADD2, TEXT_BASE, [FuncDef("add2", TEXT_BASE, len(ADD2))]))
        spec = RiscvBtor2Spec(
            binary=BinaryRef(path=str(path)),
            scope=AnalysisScope(entry_function="add2"),
            property=Property(expression="eq(reg(10), 2)"),
            analysis=AnalysisDirective(engine="z3-bmc", bound=5),
        )
        artifact = compile_spec(spec, source_payload=path)
        raw = dispatch(artifact, spec.analysis)
        print(f"engine={raw.engine}  verdict={raw.verdict}  elapsed={raw.elapsed:.3f}s")
        if raw.reason:
            print(f"reason: {raw.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
