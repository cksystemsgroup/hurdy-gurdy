"""Tests for EbpfReasoningInterpreter and EbpfReasoningBinding (P3).

Uses hand-constructed BTOR2 fragments rather than the full translator
(P4) to exercise the interpreter in isolation.

Fragment ``_ADD_THEN_EXIT_BTOR2`` models a 2-instruction program:
  insn 0: r0 += 1   (ALU64 ADD K, dst=r0, imm=1)
  insn 1: EXIT

States: reg_r0 (bv64), insn_idx (bv32), halted (bv1).
Dispatch:
  halted==1  → freeze all state.
  insn_idx==0 → reg_r0 += 1, insn_idx += 1.
  insn_idx==1 → halted := 1, reg_r0/insn_idx frozen.
bad: halted (fires when EXIT has been executed).
"""

from __future__ import annotations

import hashlib

import pytest

from gurdy.core.annotation.sidecar import AnnotationSidecar
from gurdy.core.pair import CompiledArtifact, Layer
from gurdy.pairs.ebpf_btor2.reasoning_interp import (
    INTERPRETER_VERSION,
    PAIR_ID,
    EbpfReasoningBinding,
    EbpfReasoningInterpreter,
)

# ---------------------------------------------------------------------------
# Hand-crafted BTOR2 model: insn0=ADD r0 r0 1, insn1=EXIT
#
# Sorts:
#   1 = bv1   (halted, condition results)
#   2 = bv32  (insn_idx, bv32 arithmetic)
#   3 = bv64  (reg_r0, bv64 arithmetic)
#
# States:
#   10 reg_r0 : bv64  (free at entry — no init clause)
#   20 insn_idx : bv32  (init = 0)
#   21 halted : bv1   (init = 0)
#
# Dispatch logic (ite chains):
#   reg_r0_next  = if halted then r0 else (if insn_idx==0 then r0+1 else r0)
#   insn_idx_next = if halted then insn_idx else (if insn_idx==0 then insn_idx+1 else insn_idx)
#   halted_next  = if halted then halted else (if insn_idx==1 then 1 else halted)
# ---------------------------------------------------------------------------

_ADD_THEN_EXIT_BTOR2 = "\n".join([
    "1 sort bitvec 1",
    "2 sort bitvec 32",
    "3 sort bitvec 64",
    "10 state 3 reg_r0",
    "20 state 2 insn_idx",
    "21 state 1 halted",
    "; insn_idx init = 0, halted init = 0; reg_r0 is free",
    "100 constd 2 0",
    "101 init 2 20 100",
    "102 constd 1 0",
    "103 init 1 21 102",
    "; library: r0 + 1",
    "200 constd 3 1",
    "201 add 3 10 200",
    "; dispatch constants",
    "202 constd 2 0",
    "203 constd 2 1",
    "204 constd 1 1",
    "; dispatch conditions",
    "300 eq 1 20 202",
    "301 eq 1 20 203",
    "; reg_r0_next",
    "302 ite 3 300 201 10",
    "303 ite 3 21 10 302",
    "; insn_idx_next",
    "304 add 2 20 203",
    "305 ite 2 300 304 20",
    "306 ite 2 21 20 305",
    "; halted_next",
    "307 ite 1 301 204 21",
    "308 ite 1 21 21 307",
    "; next clauses",
    "400 next 3 10 303",
    "401 next 2 20 306",
    "402 next 1 21 308",
    "; bad: halted (fires when EXIT executed)",
    "500 bad 21",
]) + "\n"

# Simple model: halted never changes, bad never fires.
_STATIC_BTOR2 = "\n".join([
    "1 sort bitvec 1",
    "10 state 1 halted",
    "100 constd 1 0",
    "101 init 1 10 100",
    "200 next 1 10 100",
    "300 bad 100",
]) + "\n"


def _make_artifact(text: str, pair: str = PAIR_ID) -> CompiledArtifact:
    body = text.encode("utf-8")
    return CompiledArtifact(
        pair=pair,
        layers={"all": Layer(name="all", body=body, content_hash="x")},
        annotation=AnnotationSidecar(),
        flattened=body,
        schema_version="1.0.0",
        spec_hash="x",
    )


# ---------------------------------------------------------------------------
# EbpfReasoningBinding tests
# ---------------------------------------------------------------------------


def test_binding_defaults():
    b = EbpfReasoningBinding()
    assert b.pair == PAIR_ID
    assert b.state_init_by_symbol == {}
    assert b.input_per_step_by_symbol == ()


def test_binding_with_state_init():
    b = EbpfReasoningBinding(state_init_by_symbol={"reg_r0": 42})
    assert b.state_init_by_symbol["reg_r0"] == 42


def test_binding_from_jsonable_roundtrip():
    b = EbpfReasoningBinding(
        state_init_by_symbol={"reg_r0": 7, "insn_idx": 0},
        input_per_step_by_symbol=({"x": 1}, {"x": 2}),
    )
    j = b.to_jsonable()
    b2 = EbpfReasoningBinding.from_jsonable(j)
    assert dict(b2.state_init_by_symbol) == {"reg_r0": 7, "insn_idx": 0}
    assert len(b2.input_per_step_by_symbol) == 2


def test_binding_hash_is_hex_string():
    b = EbpfReasoningBinding()
    h = b.bindings_hash()
    assert isinstance(h, str)
    assert len(h) == 64  # sha256 hex
    int(h, 16)  # must be valid hex


def test_binding_hash_changes_with_state():
    b1 = EbpfReasoningBinding()
    b2 = EbpfReasoningBinding(state_init_by_symbol={"reg_r0": 1})
    assert b1.bindings_hash() != b2.bindings_hash()


# ---------------------------------------------------------------------------
# EbpfReasoningInterpreter — basic properties
# ---------------------------------------------------------------------------


def test_interpreter_version():
    interp = EbpfReasoningInterpreter()
    assert interp.version == INTERPRETER_VERSION


def test_pair_id_constant():
    assert PAIR_ID == "ebpf-btor2"


def test_max_steps_zero_gives_empty_trace():
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=0)
    assert len(trace.steps) == 0
    assert trace.bad_fired_at is None
    assert trace.pair == PAIR_ID
    assert trace.interpreter_version == INTERPRETER_VERSION


def test_trace_artifact_hash():
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=1)
    expected = hashlib.sha256(art.flattened).hexdigest()
    assert trace.artifact_hash == expected


def test_trace_bindings_hash_present():
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    b = EbpfReasoningBinding()
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, b, max_steps=1)
    assert trace.bindings_hash == b.bindings_hash()


# ---------------------------------------------------------------------------
# ADD then EXIT — step-by-step trace verification
# ---------------------------------------------------------------------------


def test_add_then_exit_step_count():
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=3)
    assert len(trace.steps) == 3


def test_add_then_exit_step0_register_incremented():
    # Step 0 executes insn 0 (ADD r0 1). Post-step state: reg_r0=1, insn_idx=1, halted=0.
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=2)
    machine0 = trace.steps[0].layer_values["machine"]
    # nid 10 = reg_r0, 20 = insn_idx, 21 = halted
    assert machine0[10] == 1   # r0 went from 0 → 1
    assert machine0[20] == 1   # insn_idx advanced to 1
    assert machine0[21] == 0   # not halted yet


def test_add_then_exit_step0_bad_not_fired():
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=2)
    assert not trace.steps[0].bad_fired


def test_add_then_exit_step1_halted():
    # Step 1 executes insn 1 (EXIT). Post-step: halted=1.
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=2)
    machine1 = trace.steps[1].layer_values["machine"]
    assert machine1[21] == 1   # halted
    assert machine1[10] == 1   # reg_r0 frozen
    assert machine1[20] == 1   # insn_idx frozen


def test_add_then_exit_bad_fires_at_step1():
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=3)
    assert trace.bad_fired_at == 1
    assert trace.steps[1].bad_fired
    assert not trace.steps[0].bad_fired


def test_add_then_exit_bad_not_fired_if_only_one_step():
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=1)
    assert trace.bad_fired_at is None
    assert not trace.steps[0].bad_fired


def test_add_then_exit_halted_freezes_at_step2():
    # After halted=1, all state stays frozen.
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=4)
    for step_idx in range(2, 4):
        m = trace.steps[step_idx].layer_values["machine"]
        assert m[21] == 1   # halted stays 1
        assert m[10] == 1   # reg_r0 frozen
        assert m[20] == 1   # insn_idx frozen


def test_add_then_exit_bad_only_fires_once():
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=5)
    fired_count = sum(1 for s in trace.steps if s.bad_fired)
    assert fired_count == 1
    assert trace.bad_fired_at == 1


# ---------------------------------------------------------------------------
# Binding override
# ---------------------------------------------------------------------------


def test_binding_override_reg_r0():
    # Start with reg_r0=5; after ADD (insn 0) expect reg_r0=6.
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    b = EbpfReasoningBinding(state_init_by_symbol={"reg_r0": 5})
    trace = interp.run(art, b, max_steps=1)
    m0 = trace.steps[0].layer_values["machine"]
    assert m0[10] == 6   # 5 + 1


def test_binding_override_large_value():
    # Start with reg_r0 = 2^63; after ADD expect 2^63 + 1.
    val = (1 << 63)
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    b = EbpfReasoningBinding(state_init_by_symbol={"reg_r0": val})
    trace = interp.run(art, b, max_steps=1)
    m0 = trace.steps[0].layer_values["machine"]
    assert m0[10] == val + 1


def test_binding_override_wraparound():
    # Start with reg_r0 = 2^64 - 1; after ADD expect 0 (wraparound).
    val = (1 << 64) - 1
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    b = EbpfReasoningBinding(state_init_by_symbol={"reg_r0": val})
    trace = interp.run(art, b, max_steps=1)
    m0 = trace.steps[0].layer_values["machine"]
    assert m0[10] == 0   # 2^64 - 1 + 1 = 2^64 ≡ 0 mod 2^64


# ---------------------------------------------------------------------------
# Static model (bad never fires)
# ---------------------------------------------------------------------------


def test_static_bad_never_fires():
    art = _make_artifact(_STATIC_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=10)
    assert trace.bad_fired_at is None
    assert all(not s.bad_fired for s in trace.steps)


def test_static_halted_stays_zero():
    art = _make_artifact(_STATIC_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=5)
    # nid 10 = halted
    for s in trace.steps:
        assert s.layer_values["machine"][10] == 0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_determinism_same_binding():
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    b = EbpfReasoningBinding(state_init_by_symbol={"reg_r0": 3})
    t1 = interp.run(art, b, max_steps=4)
    t2 = interp.run(art, b, max_steps=4)
    assert t1.to_jsonable() == t2.to_jsonable()


def test_determinism_different_bindings_differ():
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    t1 = interp.run(art, EbpfReasoningBinding(state_init_by_symbol={"reg_r0": 0}), max_steps=2)
    t2 = interp.run(art, EbpfReasoningBinding(state_init_by_symbol={"reg_r0": 99}), max_steps=2)
    m0_t1 = t1.steps[0].layer_values["machine"][10]
    m0_t2 = t2.steps[0].layer_values["machine"][10]
    assert m0_t1 != m0_t2


# ---------------------------------------------------------------------------
# Trace serialisation
# ---------------------------------------------------------------------------


def test_trace_to_jsonable_structure():
    art = _make_artifact(_ADD_THEN_EXIT_BTOR2)
    interp = EbpfReasoningInterpreter()
    trace = interp.run(art, EbpfReasoningBinding(), max_steps=2)
    j = trace.to_jsonable()
    assert j["pair"] == PAIR_ID
    assert j["interpreter_version"] == INTERPRETER_VERSION
    assert len(j["steps"]) == 2
    assert j["bad_fired_at"] == 1
