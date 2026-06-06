"""End-to-end: register the pair, run the full LLM tool surface."""

import json

import pytest

from gurdy.core.annotation.lookup import IntrospectQuery
from gurdy.core.pair import _clear_registry_for_tests, get_pair, list_pairs
from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.describe import _reset_cache_for_tests, describe
from gurdy.core.tools.dispatch import dispatch
from gurdy.core.tools.introspect import introspect
from gurdy.core.tools.lift import lift
from gurdy.pairs.riscv_btor2.translation.translate import SCHEMA_VERSION

from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000
ADD2_BYTES = bytes.fromhex("13050100" "13051500" "67800000")


@pytest.fixture(autouse=True)
def _clean_registry():
    _clear_registry_for_tests()
    _reset_cache_for_tests()
    # Force re-import so the package's register_pair runs.
    import importlib
    import gurdy.pairs.riscv_btor2 as pkg
    importlib.reload(pkg)
    yield
    _clear_registry_for_tests()
    _reset_cache_for_tests()


def _make_binary(tmp_path):
    funcs = [FuncDef(name="add2", addr=TEXT_BASE, size=len(ADD2_BYTES))]
    p = tmp_path / "add2.elf"
    p.write_bytes(build_elf(ADD2_BYTES, TEXT_BASE, funcs))
    return p


def test_pair_registers_on_import():
    assert "riscv-btor2" in list_pairs()
    pair = get_pair("riscv-btor2")
    assert pair.schema_version == SCHEMA_VERSION
    assert "z3-bmc" in pair.solvers


def test_describe_serves_schema_topics():
    e = describe("Sorts", "riscv-btor2")
    assert e is not None
    assert e.heading.lower().endswith("sorts") or "Sorts" in e.heading or e.hint


def test_full_tool_surface_compile_dispatch_introspect_lift(tmp_path):
    from gurdy.pairs.riscv_btor2.spec import (
        AnalysisDirective,
        AnalysisScope,
        BinaryRef,
        Property,
        RegisterAt,
        RiscvBtor2Spec,
    )

    p = _make_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(p)),
        scope=AnalysisScope(entry_function="add2"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE),),
        property=Property(expression="eq(reg(10), 2)"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=5),
    )
    artifact = compile_spec(spec, source_payload=p)
    assert artifact.pair == "riscv-btor2"
    assert b"state" in artifact.flattened or len(artifact.flattened) > 0

    # Introspect: the annotation should contain state entries.
    res = introspect(artifact, IntrospectQuery(role="state"))
    assert len(res.matches) >= 31

    # Dispatch: returns one of the standard verdicts.
    raw = dispatch(artifact, spec.analysis)
    assert raw.verdict in {"reachable", "unreachable", "unknown", "error", "proved"}

    # Lift: produces a lifted result echoing the verdict.
    lifted = lift(artifact, raw)
    assert lifted.verdict == raw.verdict
    assert lifted.pair == "riscv-btor2"
