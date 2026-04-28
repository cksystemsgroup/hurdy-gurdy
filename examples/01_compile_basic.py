"""Example 01: build a tiny RV64 ELF, compile it to BTOR2, print layers.

Run from the repo root:

    python examples/01_compile_basic.py

This is the simplest possible end-to-end use of the riscv-btor2 pair
and serves as the executable companion to the README's reading
order.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Make the example runnable without an editable install.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gurdy.pairs.riscv_btor2  # noqa: F401  (registers the pair)
from gurdy.core.tools.compile import compile_spec
from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    Property,
    RegisterAt,
    RiscvBtor2Spec,
)
from tests.fixtures.elf_builder import FuncDef, build_elf


# RV64 instruction stream:  addi a0, x0, 1 ; addi a0, a0, 1 ; ret
TEXT_BASE = 0x10000
ADD2 = bytes.fromhex("13050100" "13051500" "67800000")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "add2.elf"
        path.write_bytes(build_elf(ADD2, TEXT_BASE, [FuncDef("add2", TEXT_BASE, len(ADD2))]))
        spec = RiscvBtor2Spec(
            binary=BinaryRef(path=str(path)),
            scope=AnalysisScope(entry_function="add2"),
            observables=(RegisterAt(register=10, pc=TEXT_BASE),),
            property=Property(expression="eq(reg(10), 2)"),
            analysis=AnalysisDirective(engine="z3-bmc", bound=5),
        )
        artifact = compile_spec(spec, source_payload=path)
        print(f"pair={artifact.pair} schema={artifact.schema_version}")
        print(f"spec_hash={artifact.spec_hash}")
        for name, layer in artifact.layers.items():
            print(f"  layer {name}: {len(layer.body):>5} bytes  hash={layer.content_hash[:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
