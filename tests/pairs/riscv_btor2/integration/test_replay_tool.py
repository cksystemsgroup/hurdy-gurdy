"""End-to-end test of the ``replay`` tool on a synthetic Z3 witness.

Doesn't require Z3: builds a witness payload by hand the same way Z3
would (``s0_n<NID> = <value>`` lines), feeds it through the framework
``replay`` tool, and checks the joined trace runs both interpreters
on the recovered initial state.
"""

from __future__ import annotations

import importlib

import pytest

from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.pair import _clear_registry_for_tests, get_pair
from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.describe import _reset_cache_for_tests
from gurdy.core.tools.replay import replay
from gurdy.pairs.riscv_btor2.btor2.parser import from_text
from gurdy.pairs.riscv_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BinaryRef,
    Property,
    RegisterAt,
    RiscvBtor2Spec,
)

from tests.fixtures.elf_builder import FuncDef, build_elf


TEXT_BASE = 0x10000


@pytest.fixture(autouse=True)
def _clean_registry():
    _clear_registry_for_tests()
    _reset_cache_for_tests()
    import gurdy.pairs.riscv_btor2 as pkg
    importlib.reload(pkg)
    yield
    _clear_registry_for_tests()
    _reset_cache_for_tests()


def _make_binary(tmp_path):
    code = bytes.fromhex("13055000" "73000000")  # ADDI x10,x0,5; ECALL
    p = tmp_path / "m.elf"
    p.write_bytes(
        build_elf(
            code,
            TEXT_BASE,
            [FuncDef(name="main", addr=TEXT_BASE, size=len(code))],
        )
    )
    return p


def test_replay_yields_joined_trace(tmp_path):
    binary = _make_binary(tmp_path)
    spec = RiscvBtor2Spec(
        binary=BinaryRef(path=str(binary)),
        scope=AnalysisScope(entry_function="main"),
        observables=(RegisterAt(register=10, pc=TEXT_BASE),),
        property=Property(expression="false"),
        analysis=AnalysisDirective(engine="z3-bmc", bound=4),
    )
    artifact = compile_spec(spec, source_payload=binary)

    # Find the pc state nid from the artifact and build a synthetic
    # witness pinning it to TEXT_BASE.
    parsed = from_text(artifact.flattened.decode("utf-8", errors="replace"))
    pc_nid = None
    for n in parsed.model.nodes():
        if n.op == "state" and n.symbol == "pc":
            pc_nid = n.nid
            break
    assert pc_nid is not None, "schema requires a state node named 'pc'"

    witness_text = f"s0_n{pc_nid} = {TEXT_BASE}\n"
    raw = RawSolverResult(
        verdict="reachable",
        elapsed=0.0,
        engine="z3-bmc",
        payload={"witness_text": witness_text, "binary_path": str(binary)},
    )

    joined = replay(artifact, raw)
    assert joined.pair == "riscv-btor2"
    # We expect at least the ADDI step in the joined trace.
    assert len(joined.steps) >= 1
    s0 = joined.steps[0]
    assert s0.source.location["mnemonic"] == "ADDI"
