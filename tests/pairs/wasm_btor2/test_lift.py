"""Tests for the P8 witness lifter.

Coverage:
  - WasmWitness construction, as_signed conversion
  - parse_z3_model: decimal / #x hex / #b binary / 0x hex / multiline
  - lift_witness: param extraction via in0_n{nid} and s0_n{nid} fallback
  - lift_witness: trap_step identification
  - lift_witness: zero-param function, missing trap symbol, empty witness
  - lift_witness: integration with a synthetic BTOR2 artifact + model
"""

from __future__ import annotations

import pytest

from gurdy.pairs.wasm_btor2.lift import WasmWitness, lift_witness, parse_z3_model


# ---------------------------------------------------------------------------
# WasmWitness
# ---------------------------------------------------------------------------


def test_witness_construction_defaults():
    w = WasmWitness()
    assert w.params == {}
    assert w.trap_step is None
    assert w.n_params == 0


def test_witness_fields():
    w = WasmWitness(params={0: 10, 1: 20}, trap_step=3, n_params=2)
    assert w.params[0] == 10
    assert w.params[1] == 20
    assert w.trap_step == 3
    assert w.n_params == 2


def test_as_signed_positive():
    w = WasmWitness(params={0: 42})
    assert w.as_signed(0) == 42


def test_as_signed_negative():
    # 0xFFFFFFFF == 4294967295 unsigned == -1 signed i32
    w = WasmWitness(params={0: 0xFFFFFFFF})
    assert w.as_signed(0) == -1


def test_as_signed_boundary():
    # 2^31 == -2147483648 signed
    w = WasmWitness(params={0: 2147483648})
    assert w.as_signed(0) == -2147483648


def test_as_signed_missing_defaults_zero():
    w = WasmWitness(params={})
    assert w.as_signed(0) == 0


# ---------------------------------------------------------------------------
# parse_z3_model
# ---------------------------------------------------------------------------


def test_parse_decimal():
    text = "[x = 42, y = 0]"
    result = parse_z3_model(text)
    assert result["x"] == 42
    assert result["y"] == 0


def test_parse_hex_smtlib():
    text = "[s0_n5 = #x0000002a]"
    result = parse_z3_model(text)
    assert result["s0_n5"] == 0x2A


def test_parse_binary_smtlib():
    text = "[flag = #b1]"
    result = parse_z3_model(text)
    assert result["flag"] == 1


def test_parse_cstyle_hex():
    text = "[in0_n7 = 0xff]"
    result = parse_z3_model(text)
    assert result["in0_n7"] == 255


def test_parse_multiline():
    text = """[s0_n3 = 0,
 s0_n5 = 100,
 in0_n8 = 42,
 s1_n3 = 1]"""
    result = parse_z3_model(text)
    assert result["s0_n3"] == 0
    assert result["s0_n5"] == 100
    assert result["in0_n8"] == 42
    assert result["s1_n3"] == 1


def test_parse_empty_string():
    assert parse_z3_model("") == {}


def test_parse_z3_bang_suffix():
    # z3 uses '!' in some variable naming styles; our regex accepts it
    text = "[local_0!0 = 7]"
    result = parse_z3_model(text)
    assert result.get("local_0!0") == 7


# ---------------------------------------------------------------------------
# Synthetic BTOR2 + witness helpers
# ---------------------------------------------------------------------------


def _btor2_two_params() -> str:
    """Minimal BTOR2 with two i32 params, one extra local, and a trap state."""
    return """\
1 sort bitvec 1
2 sort bitvec 8
3 sort bitvec 16
4 sort bitvec 32
5 sort array 2 4
10 state 3 pc
11 state 2 sp
12 state 5 stack
13 state 4 local_0
14 input 4 param_0_init
15 state 4 local_1
16 input 4 param_1_init
17 state 4 local_2
18 state 1 trap
19 state 1 halted
"""


def _btor2_no_params() -> str:
    """Minimal BTOR2 with no params."""
    return """\
1 sort bitvec 1
2 sort bitvec 32
3 state 1 trap
4 state 1 halted
"""


# ---------------------------------------------------------------------------
# lift_witness
# ---------------------------------------------------------------------------


def test_lift_params_from_in0():
    btor2 = _btor2_two_params()
    # param_0_init is nid 14, param_1_init is nid 16
    witness = "[in0_n14 = 100, in0_n16 = 200, s0_n18 = 0, s1_n18 = 0]"
    w = lift_witness(btor2, witness)
    assert w.params[0] == 100
    assert w.params[1] == 200
    assert w.n_params == 2


def test_lift_params_fallback_s0():
    # in0_n{nid} absent; fallback to s0_n{local_nid}
    btor2 = _btor2_two_params()
    # local_0 is nid 13, local_1 is nid 15
    witness = "[s0_n13 = 55, s0_n15 = 77, s0_n18 = 0]"
    w = lift_witness(btor2, witness)
    assert w.params[0] == 55
    assert w.params[1] == 77


def test_lift_trap_step_found():
    btor2 = _btor2_two_params()
    # trap is nid 18; fires at cycle 2
    witness = "[in0_n14 = 1, in0_n16 = 2, s0_n18 = 0, s1_n18 = 0, s2_n18 = 1]"
    w = lift_witness(btor2, witness)
    assert w.trap_step == 2


def test_lift_trap_at_cycle_zero():
    btor2 = _btor2_two_params()
    witness = "[in0_n14 = 0, in0_n16 = 0, s0_n18 = 1]"
    w = lift_witness(btor2, witness)
    assert w.trap_step == 0


def test_lift_no_trap_in_witness():
    btor2 = _btor2_two_params()
    # trap never fires (all s{c}_n18 absent or zero)
    witness = "[in0_n14 = 10, in0_n16 = 20, s0_n18 = 0, s1_n18 = 0]"
    w = lift_witness(btor2, witness)
    assert w.trap_step is None


def test_lift_no_params():
    btor2 = _btor2_no_params()
    # trap is nid 3
    witness = "[s0_n3 = 0, s1_n3 = 1]"
    w = lift_witness(btor2, witness)
    assert w.n_params == 0
    assert w.params == {}
    assert w.trap_step == 1


def test_lift_empty_witness():
    w = lift_witness(_btor2_two_params(), "")
    assert w.params == {}
    assert w.trap_step is None
    assert w.n_params == 2  # params found from BTOR2 even if no values in witness


def test_lift_wrapping_param():
    # 0xFFFFFFFF stored unsigned, as_signed gives -1
    btor2 = _btor2_two_params()
    witness = "[in0_n14 = 4294967295, in0_n16 = 1]"
    w = lift_witness(btor2, witness)
    assert w.params[0] == 0xFFFFFFFF
    assert w.as_signed(0) == -1


def test_lift_hex_values_in_witness():
    btor2 = _btor2_two_params()
    witness = "[in0_n14 = #x0000002a, in0_n16 = #x00000064, s0_n18 = 0, s1_n18 = 1]"
    w = lift_witness(btor2, witness)
    assert w.params[0] == 0x2A  # 42
    assert w.params[1] == 0x64  # 100
    assert w.trap_step == 1


def test_lift_bytes_btor2():
    # CompiledArtifact.flattened is bytes; lift_witness accepts bytes too
    btor2_bytes = _btor2_two_params().encode("utf-8")
    witness = "[in0_n14 = 7, in0_n16 = 8]"
    w = lift_witness(btor2_bytes, witness)
    assert w.params[0] == 7
    assert w.params[1] == 8


def test_lift_n_params_count():
    btor2 = _btor2_two_params()
    w = lift_witness(btor2, "")
    # Even with empty witness, BTOR2 symbol scan finds both params
    assert w.n_params == 2


# ---------------------------------------------------------------------------
# Integration: lift against real CompiledArtifact
# ---------------------------------------------------------------------------


def test_lift_integration_with_seed_artifact():
    """Compile 0001-i32-add-wrap and confirm lift_witness handles its BTOR2."""
    from pathlib import Path
    from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
    from gurdy.pairs.wasm_btor2.source import load_wasm_source
    from gurdy.pairs.wasm_btor2.spec import WasmBtor2Spec
    from gurdy.pairs.wasm_btor2.translation import Translator

    seed = (
        Path(__file__).resolve().parents[3]
        / "bench/wasm-btor2/corpus/seed/0001-i32-add-wrap"
    )
    import json
    src = load_wasm_source(seed / "module.wasm")
    spec = WasmBtor2Spec.from_jsonable(json.loads((seed / "spec.json").read_text()))
    ann = AnnotationEmitter(AnnotationSidecar(schema_version="1.0.0", spec_hash=""))
    artifact = Translator().translate(spec, src, ann)

    # Synthesise a plausible reachable witness: params 5 and 10, trap at step 3.
    # (param_0_init and param_1_init nids are found by scanning the flattened text)
    btor2_text = artifact.flattened.decode("utf-8")
    sym_map: dict[str, int] = {}
    for line in btor2_text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] in ('state', 'input'):
            sym_map[parts[3]] = int(parts[0])

    assert 'param_0_init' in sym_map
    assert 'param_1_init' in sym_map
    assert 'trap' in sym_map

    p0_nid = sym_map['param_0_init']
    p1_nid = sym_map['param_1_init']
    trap_nid = sym_map['trap']

    witness = (
        f"[in0_n{p0_nid} = 5, in0_n{p1_nid} = 10, "
        f"s0_n{trap_nid} = 0, s1_n{trap_nid} = 0, s3_n{trap_nid} = 1]"
    )
    w = lift_witness(artifact.flattened, witness)
    assert w.params[0] == 5
    assert w.params[1] == 10
    assert w.trap_step == 3
    assert w.n_params == 2
