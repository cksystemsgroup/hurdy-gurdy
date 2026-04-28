"""Example 05: demonstrate layer reuse across related questions.

Compile the same source under two specs that differ only in the
property expression; show that the stable layers (header, machine,
library, dispatch, binding) are byte-identical between them — this
is the substrate that makes incremental analysis cheap when an LLM
re-asks variations of the same question.
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
    Property,
    RiscvBtor2Spec,
)
from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000
ADD2 = bytes.fromhex("13050100" "13051500" "67800000")


def _build_spec(path: Path, prop_expr: str) -> RiscvBtor2Spec:
    return RiscvBtor2Spec(
        binary=BinaryRef(path=str(path)),
        scope=AnalysisScope(entry_function="add2"),
        property=Property(expression=prop_expr),
        analysis=AnalysisDirective(engine="z3-bmc", bound=5),
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "add2.elf"
        path.write_bytes(build_elf(ADD2, TEXT_BASE, [FuncDef("add2", TEXT_BASE, len(ADD2))]))
        a = compile_spec(_build_spec(path, "eq(reg(10), 2)"), source_payload=path)
        b = compile_spec(_build_spec(path, "eq(reg(10), 99)"), source_payload=path)
        for name in a.layers:
            same = a.layers[name].body == b.layers[name].body
            print(f"  layer {name:<11} {'unchanged' if same else 'CHANGED  '}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
