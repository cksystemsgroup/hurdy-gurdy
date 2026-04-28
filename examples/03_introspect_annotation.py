"""Example 03: introspect the annotation sidecar produced by compile.

Walks the artifact's annotation and prints state declarations and
the dispatch role population.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gurdy.pairs.riscv_btor2  # noqa: F401
from gurdy.core.annotation.lookup import IntrospectQuery
from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.introspect import introspect
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
        states = introspect(artifact, IntrospectQuery(role="state"))
        print(f"states: {len(states.matches)}")
        for a in states.matches[:5]:
            print(f"  layer={a.layer} nid={a.nid} sm={a.source_mapping}")
        dispatch_nodes = introspect(artifact, IntrospectQuery(role="dispatch"))
        print(f"dispatch nodes: {len(dispatch_nodes.matches)}")
        bad_nodes = introspect(artifact, IntrospectQuery(role="bad"))
        print(f"bad nodes: {len(bad_nodes.matches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
