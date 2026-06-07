"""Framework-route tests for the registered ebpf-btor2 pair (Stage 7.E).

The existing ebpf tests call ``translate()`` / ``run()`` directly. These
exercise the pair through the framework's registered ``Pair`` instead:
``get_pair`` → ``compile_spec`` → ``dispatch`` → ``lift``, the same path
the LLM-facing tool surface uses. This is the registration the Stage 7.E
follow-up calls for.
"""

from __future__ import annotations

import importlib
import struct

import pytest

from gurdy.core.btor2.parser import from_text
from gurdy.core.pair import _clear_registry_for_tests, get_pair, list_pairs
from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.describe import _reset_cache_for_tests
from gurdy.core.tools.dispatch import dispatch
from gurdy.core.tools.lift import lift
from gurdy.pairs.ebpf_btor2.lift.lifter import lift_witness
from gurdy.pairs.ebpf_btor2.lift.witness import EbpfWitness
from gurdy.pairs.ebpf_btor2.spec import (
    AnalysisDirective,
    EbpfBtor2Spec,
    EbpfProgramRef,
    EbpfScope,
    Property,
)


def _insn(opcode: int, dst: int, src: int, off: int, imm: int) -> bytes:
    return struct.pack("<BBhi", opcode, (src << 4) | dst, off, imm)


_EXIT_ONLY = _insn(0x95, 0, 0, 0, 0)
_ADD_EXIT = _insn(0x07, 0, 0, 0, 1) + _insn(0x95, 0, 0, 0, 0)  # r0 += 1 ; EXIT


@pytest.fixture(autouse=True)
def _clean_registry():
    _clear_registry_for_tests()
    _reset_cache_for_tests()
    import gurdy.pairs.ebpf_btor2 as pkg
    importlib.reload(pkg)
    yield
    _clear_registry_for_tests()
    _reset_cache_for_tests()


def _spec(expression: str = "false", bound: int = 3) -> EbpfBtor2Spec:
    return EbpfBtor2Spec(
        program=EbpfProgramRef(path=""),
        scope=EbpfScope(max_insns=8),
        property=Property(expression=expression),
        analysis=AnalysisDirective(engine="z3-bmc", bound=bound),
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_pair_is_registered():
    assert "ebpf-btor2" in list_pairs()
    pair = get_pair("ebpf-btor2")
    assert pair.in_lang == "ebpf"
    assert pair.out_lang == "btor2"
    assert pair.spec_class is EbpfBtor2Spec
    assert "z3-bmc" in pair.solvers
    assert [layer.name for layer in pair.layer_specs] == [
        "header", "machine", "library", "dispatch",
        "init", "constraint", "bad", "binding",
    ]


def test_schema_path_exists():
    pair = get_pair("ebpf-btor2")
    assert pair.schema_path.is_file()
    assert pair.schema_version


# ---------------------------------------------------------------------------
# compile route (source_loader + translator)
# ---------------------------------------------------------------------------


def test_compile_spec_routes_through_pair():
    art = compile_spec(_spec(), source_payload=_ADD_EXIT)
    assert art.pair == "ebpf-btor2"
    assert set(art.layers) == {
        "header", "machine", "library", "dispatch",
        "init", "constraint", "bad", "binding",
    }
    # flattened artifact parses as valid BTOR2
    parsed = from_text(art.flattened.decode("utf-8"))
    assert not parsed.has_errors()


def test_compile_is_byte_deterministic():
    a = compile_spec(_spec(), source_payload=_ADD_EXIT)
    b = compile_spec(_spec(), source_payload=_ADD_EXIT)
    assert a.flattened == b.flattened


def test_source_loader_accepts_program_ref(tmp_path):
    obj = tmp_path / "prog.bin"
    obj.write_bytes(_ADD_EXIT)
    art = compile_spec(_spec(), source_payload=EbpfProgramRef(path=str(obj)))
    assert art.flattened == compile_spec(_spec(), source_payload=_ADD_EXIT).flattened


# ---------------------------------------------------------------------------
# dispatch + lift route
# ---------------------------------------------------------------------------


def test_dispatch_then_lift_reachable():
    spec = _spec(expression="exit_reached")
    art = compile_spec(spec, source_payload=_ADD_EXIT)
    raw = dispatch(art, spec.analysis)
    assert raw.verdict == "reachable"
    facts = lift(art, raw)
    assert isinstance(facts, EbpfWitness)
    assert facts.reachable
    assert facts.halted_step is not None


# ---------------------------------------------------------------------------
# lifter unit behaviour
# ---------------------------------------------------------------------------


def test_lifter_empty_on_unreachable():
    w = lift_witness("", "", reachable=False)
    assert w.reachable is False
    assert w.initial_regs == {}
    assert w.halted_step is None


def test_lifter_reads_initial_regs_and_halt():
    btor2 = "\n".join([
        "1 sort bitvec 64",
        "2 sort bitvec 1",
        "10 state 1 reg_r0",
        "11 state 1 reg_r1",
        "20 state 2 halted",
    ])
    model = "s0_n10 = 7, s0_n11 = #x000000000000000a, s2_n20 = 1, s0_n20 = 0"
    w = lift_witness(btor2, model, reachable=True)
    assert w.reachable
    assert w.initial_regs[0] == 7
    assert w.initial_regs[1] == 10
    assert w.halted_step == 2
