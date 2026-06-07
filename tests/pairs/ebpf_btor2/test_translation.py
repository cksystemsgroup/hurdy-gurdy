"""Tests for the P4 ebpf-btor2 translator.

Verifies that ``translate(spec, bytecode)`` produces a BTOR2 artifact
that is correctly evaluated by ``EbpfReasoningInterpreter`` and that
step-by-step state matches ``source_interp.run`` on the same programs.

Seed programs used as bytecode fixtures:
  _EXIT_ONLY    : [EXIT]
  _ADD_EXIT     : [r0 += 1, EXIT]
  _ADD_X_EXIT   : [r1 += r0, EXIT]
  _BRANCH_EXIT  : [JEQ K r0==5 +1, r0 = r0 XOR 0, EXIT]  (conditional branch)
"""

from __future__ import annotations

import struct

import pytest

from gurdy.core.annotation.sidecar import AnnotationSidecar, AnnotationEmitter
from gurdy.pairs.ebpf_btor2.reasoning_interp import (
    EbpfReasoningBinding,
    EbpfReasoningInterpreter,
)
from gurdy.pairs.ebpf_btor2.source_interp import EbpfInputBinding
from gurdy.pairs.ebpf_btor2.source_interp import run as src_run
from gurdy.pairs.ebpf_btor2.spec import (
    EbpfBtor2Spec,
    EbpfProgramRef,
    Property,
    RegisterBound,
)
from gurdy.pairs.ebpf_btor2.translation import (
    LAYER_NAMES,
    SCHEMA_VERSION,
    translate,
)
from gurdy.core.btor2.parser import from_text


# ---------------------------------------------------------------------------
# Bytecode fixtures
# ---------------------------------------------------------------------------

def _insn(opcode: int, dst: int, src: int, off: int, imm: int) -> bytes:
    return struct.pack("<BBhi", opcode, (src << 4) | dst, off, imm)


_EXIT_ONLY = _insn(0x95, 0, 0, 0, 0)

_ADD_EXIT = (
    _insn(0x07, 0, 0, 0, 1)    # r0 += 1  (ALU64 ADD K, dst=0, imm=1)
    + _insn(0x95, 0, 0, 0, 0)  # EXIT
)

_ADD_X_EXIT = (
    _insn(0x0F, 1, 0, 0, 0)    # r1 += r0  (ALU64 ADD X, dst=1, src=0)
    + _insn(0x95, 0, 0, 0, 0)  # EXIT
)

# JEQ K dst=0 imm=5 off=1 → if r0==5, jump over next insn
# r0 ^= 0 (no-op but verifies XOR lowering)
# EXIT
_BRANCH_EXIT = (
    _insn(0x15, 0, 0, 1, 5)    # JEQ K: if r0==5, skip 1
    + _insn(0xA7, 0, 0, 0, 0)  # r0 ^= 0 (XOR64 K, no-op)
    + _insn(0x95, 0, 0, 0, 0)  # EXIT
)

_JA_EXIT = (
    _insn(0x05, 0, 0, 1, 0)    # JA off=1 (jump over next insn)
    + _insn(0x07, 0, 0, 0, 99) # r0 += 99 (should be skipped)
    + _insn(0x95, 0, 0, 0, 0)  # EXIT
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spec(bytecode: bytes = b"", expression: str = "false",
          assumptions: tuple = ()) -> EbpfBtor2Spec:
    return EbpfBtor2Spec(
        program=EbpfProgramRef(path="test"),
        property=Property(expression=expression),
        assumptions=assumptions,
    )


def _sym_nids(artifact) -> dict[str, int]:
    """Return {symbol: nid} for all state nodes in the artifact."""
    text = artifact.flattened.decode("utf-8")
    parsed = from_text(text)
    return {
        n.symbol: n.nid
        for n in parsed.model.nodes()
        if n.op == "state" and n.symbol
    }


def _run_reasoning(artifact, initial_regs=None, max_steps=5) -> object:
    binding = EbpfReasoningBinding(
        state_init_by_symbol={f"reg_r{i}": v for i, v in enumerate(initial_regs or [])}
    )
    return EbpfReasoningInterpreter().run(artifact, binding, max_steps=max_steps)


# ---------------------------------------------------------------------------
# Artifact structure tests
# ---------------------------------------------------------------------------


def test_translate_returns_compiled_artifact():
    art = translate(_spec(), _EXIT_ONLY)
    assert art.pair == "ebpf-btor2"
    assert art.schema_version == SCHEMA_VERSION


def test_all_eight_layers_present():
    art = translate(_spec(), _ADD_EXIT)
    for name in LAYER_NAMES:
        assert name in art.layers, f"missing layer: {name}"


def test_flattened_is_bytes():
    art = translate(_spec(), _EXIT_ONLY)
    assert isinstance(art.flattened, bytes)
    assert len(art.flattened) > 0


def test_flattened_is_valid_btor2():
    art = translate(_spec(), _ADD_EXIT)
    text = art.flattened.decode("utf-8")
    parsed = from_text(text)
    assert len(parsed.model.nodes()) > 0


def test_state_symbols_declared():
    art = translate(_spec(), _ADD_EXIT)
    sym = _sym_nids(art)
    for i in range(10):
        assert f"reg_r{i}" in sym
    assert "insn_idx" in sym
    assert "halted" in sym


def test_determinism():
    spec = _spec()
    art1 = translate(spec, _ADD_EXIT)
    art2 = translate(spec, _ADD_EXIT)
    assert art1.flattened == art2.flattened


def test_different_bytecode_different_artifact():
    art1 = translate(_spec(), _EXIT_ONLY)
    art2 = translate(_spec(), _ADD_EXIT)
    assert art1.flattened != art2.flattened


# ---------------------------------------------------------------------------
# EXIT-only program
# ---------------------------------------------------------------------------


def test_exit_only_halts_at_step0():
    art = translate(_spec(), _EXIT_ONLY)
    trace = _run_reasoning(art, max_steps=3)
    sym = _sym_nids(art)
    halted_nid = sym["halted"]
    assert trace.steps[0].layer_values["machine"][halted_nid] == 1


def test_exit_only_insn_idx_frozen():
    art = translate(_spec(), _EXIT_ONLY)
    trace = _run_reasoning(art, max_steps=3)
    sym = _sym_nids(art)
    idx_nid = sym["insn_idx"]
    assert trace.steps[0].layer_values["machine"][idx_nid] == 0
    assert trace.steps[1].layer_values["machine"][idx_nid] == 0


def test_exit_only_exit_reached_fires_step0():
    art = translate(_spec(expression="exit_reached"), _EXIT_ONLY)
    trace = _run_reasoning(art, max_steps=3)
    assert trace.bad_fired_at == 0


# ---------------------------------------------------------------------------
# ADD then EXIT — step-by-step alignment
# ---------------------------------------------------------------------------


def test_add_exit_step0_reg_r0_incremented():
    initial = [7] + [0] * 9
    art = translate(_spec(), _ADD_EXIT)
    trace = _run_reasoning(art, initial_regs=initial, max_steps=3)
    sym = _sym_nids(art)
    m0 = trace.steps[0].layer_values["machine"]
    assert m0[sym["reg_r0"]] == 8
    assert m0[sym["insn_idx"]] == 1
    assert m0[sym["halted"]] == 0


def test_add_exit_step1_halted():
    initial = [7] + [0] * 9
    art = translate(_spec(), _ADD_EXIT)
    trace = _run_reasoning(art, initial_regs=initial, max_steps=3)
    sym = _sym_nids(art)
    m1 = trace.steps[1].layer_values["machine"]
    assert m1[sym["halted"]] == 1
    assert m1[sym["reg_r0"]] == 8
    assert m1[sym["insn_idx"]] == 1


def test_add_exit_halted_freeze_step2():
    initial = [7] + [0] * 9
    art = translate(_spec(), _ADD_EXIT)
    trace = _run_reasoning(art, initial_regs=initial, max_steps=4)
    sym = _sym_nids(art)
    for step_idx in range(2, 4):
        m = trace.steps[step_idx].layer_values["machine"]
        assert m[sym["halted"]] == 1
        assert m[sym["reg_r0"]] == 8
        assert m[sym["insn_idx"]] == 1


def test_add_exit_alignment_with_source_interp():
    bytecode = _ADD_EXIT
    initial = (5,) + (0,) * 9
    art = translate(_spec(), bytecode)
    sym = _sym_nids(art)

    src_trace = src_run(EbpfInputBinding(bytecode=bytecode, initial_regs=initial))
    r_trace = _run_reasoning(art, initial_regs=list(initial), max_steps=4)

    # reasoning step i corresponds to source step i+1 (both record post-execution state)
    for r_step_idx, src_step_idx in [(0, 1), (1, 2)]:
        r_m = r_trace.steps[r_step_idx].layer_values["machine"]
        src_state = src_trace.steps[src_step_idx]
        src_final = src_trace.final_state if src_step_idx >= len(src_trace.steps) else None

        r_halted = r_m[sym["halted"]]
        r_r0 = r_m[sym["reg_r0"]]
        r_insn_idx = r_m[sym["insn_idx"]]

        # Use final_state if we've run out of steps
        if src_step_idx < len(src_trace.steps):
            src_s = src_trace.steps[src_step_idx]
            assert r_halted == int(src_s.halted)


def test_add_exit_exit_reached_fires_step1():
    art = translate(_spec(expression="exit_reached"), _ADD_EXIT)
    trace = _run_reasoning(art, max_steps=4)
    assert trace.bad_fired_at == 1
    assert not trace.steps[0].bad_fired
    assert trace.steps[1].bad_fired


def test_add_exit_false_property_never_fires():
    art = translate(_spec(expression="false"), _ADD_EXIT)
    trace = _run_reasoning(art, max_steps=5)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# ADD X (register source)
# ---------------------------------------------------------------------------


def test_add_x_exit_result():
    # r1 += r0 with r0=3, r1=10 → r1=13
    initial = [3, 10] + [0] * 8
    art = translate(_spec(), _ADD_X_EXIT)
    trace = _run_reasoning(art, initial_regs=initial, max_steps=3)
    sym = _sym_nids(art)
    m0 = trace.steps[0].layer_values["machine"]
    assert m0[sym["reg_r1"]] == 13
    assert m0[sym["reg_r0"]] == 3   # unchanged


# ---------------------------------------------------------------------------
# Conditional branch
# ---------------------------------------------------------------------------


def test_branch_taken_skips_xor():
    # r0 = 5 → JEQ taken → skip XOR → EXIT
    initial = [5] + [0] * 9
    art = translate(_spec(), _BRANCH_EXIT)
    trace = _run_reasoning(art, initial_regs=initial, max_steps=5)
    sym = _sym_nids(art)

    # After step 0 (JEQ): insn_idx should jump to 2 (skip insn 1)
    m0 = trace.steps[0].layer_values["machine"]
    assert m0[sym["insn_idx"]] == 2  # jumped over insn 1
    assert m0[sym["halted"]] == 0

    # After step 1 (EXIT at insn 2): halted=1
    m1 = trace.steps[1].layer_values["machine"]
    assert m1[sym["halted"]] == 1
    assert m1[sym["reg_r0"]] == 5   # r0 unchanged (XOR was skipped)


def test_branch_not_taken_executes_xor():
    # r0 = 0 → JEQ not taken → execute XOR r0 0 (no-op) → EXIT
    initial = [0] + [0] * 9
    art = translate(_spec(), _BRANCH_EXIT)
    trace = _run_reasoning(art, initial_regs=initial, max_steps=5)
    sym = _sym_nids(art)

    # After step 0 (JEQ not taken): insn_idx advances to 1
    m0 = trace.steps[0].layer_values["machine"]
    assert m0[sym["insn_idx"]] == 1
    assert m0[sym["halted"]] == 0


# ---------------------------------------------------------------------------
# Unconditional jump
# ---------------------------------------------------------------------------


def test_ja_skips_instruction():
    # JA off=1 skips r0+=99 → EXIT; r0 should stay 0
    initial = [0] * 10
    art = translate(_spec(), _JA_EXIT)
    trace = _run_reasoning(art, initial_regs=initial, max_steps=5)
    sym = _sym_nids(art)

    # After step 0 (JA): insn_idx = 0+1+1 = 2
    m0 = trace.steps[0].layer_values["machine"]
    assert m0[sym["insn_idx"]] == 2

    # After step 1 (EXIT): halted=1, r0=0 (skipped the add)
    m1 = trace.steps[1].layer_values["machine"]
    assert m1[sym["halted"]] == 1
    assert m1[sym["reg_r0"]] == 0


# ---------------------------------------------------------------------------
# Property expression: register comparison
# ---------------------------------------------------------------------------


def test_property_r0_eq_value_fires_when_halted_and_equal():
    # r0 += 1 then EXIT; initial r0=41 → final r0=42; bad = "r0 == 42"
    initial = [41] + [0] * 9
    art = translate(_spec(expression="r0 == 42"), _ADD_EXIT)
    trace = _run_reasoning(art, initial_regs=initial, max_steps=5)
    assert trace.bad_fired_at == 1   # fires when halted=1 and r0==42


def test_property_r0_eq_value_not_fires_wrong_value():
    # initial r0=0 → final r0=1; bad = "r0 == 42" → never fires
    initial = [0] + [0] * 9
    art = translate(_spec(expression="r0 == 42"), _ADD_EXIT)
    trace = _run_reasoning(art, initial_regs=initial, max_steps=5)
    assert trace.bad_fired_at is None


def test_property_r0_lt_10_fires_when_halted_and_small():
    # initial r0=0 → final r0=1 < 10; bad = "r0 < 10"
    initial = [0] + [0] * 9
    art = translate(_spec(expression="r0 < 10"), _ADD_EXIT)
    trace = _run_reasoning(art, initial_regs=initial, max_steps=5)
    assert trace.bad_fired_at == 1


def test_property_and_expression():
    # bad = "r0 == 1 AND r1 == 0"; initial r0=0, r1=0 → after ADD r0=1, r1=0
    initial = [0] * 10
    art = translate(_spec(expression="r0 == 1 AND r1 == 0"), _ADD_EXIT)
    trace = _run_reasoning(art, initial_regs=initial, max_steps=5)
    assert trace.bad_fired_at == 1


def test_property_false_never_fires():
    art = translate(_spec(expression="false"), _ADD_EXIT)
    trace = _run_reasoning(art, max_steps=5)
    assert trace.bad_fired_at is None


# ---------------------------------------------------------------------------
# Constraint layer: RegisterBound
# ---------------------------------------------------------------------------


def test_constraint_layer_nonempty_with_register_bound():
    spec = EbpfBtor2Spec(
        program=EbpfProgramRef(path="test"),
        property=Property(expression="false"),
        assumptions=(RegisterBound(reg=0, value_lo=0, value_hi=100),),
    )
    art = translate(spec, _ADD_EXIT)
    constraint_body = art.layers["constraint"].body.decode("utf-8")
    assert "constraint" in constraint_body


def test_constraint_layer_empty_without_assumptions():
    art = translate(_spec(), _ADD_EXIT)
    constraint_body = art.layers["constraint"].body.decode("utf-8")
    assert "constraint" not in constraint_body


# ---------------------------------------------------------------------------
# Layer content sanity checks
# ---------------------------------------------------------------------------


def test_header_layer_contains_sort_declarations():
    art = translate(_spec(), _ADD_EXIT)
    header = art.layers["header"].body.decode("utf-8")
    assert "bitvec 1" in header
    assert "bitvec 32" in header
    assert "bitvec 64" in header


def test_machine_layer_contains_state_declarations():
    art = translate(_spec(), _ADD_EXIT)
    machine = art.layers["machine"].body.decode("utf-8")
    assert "state" in machine
    assert "reg_r0" in machine
    assert "insn_idx" in machine
    assert "halted" in machine


def test_dispatch_layer_contains_next_clauses():
    art = translate(_spec(), _ADD_EXIT)
    dispatch = art.layers["dispatch"].body.decode("utf-8")
    assert "next" in dispatch


def test_init_layer_contains_init_clauses():
    art = translate(_spec(), _ADD_EXIT)
    init_body = art.layers["init"].body.decode("utf-8")
    assert "init" in init_body


def test_bad_layer_contains_bad_node():
    art = translate(_spec(expression="exit_reached"), _ADD_EXIT)
    bad_body = art.layers["bad"].body.decode("utf-8")
    assert "bad" in bad_body


def test_spec_hash_in_artifact():
    spec = _spec()
    art = translate(spec, _EXIT_ONLY)
    assert art.spec_hash == spec.spec_hash()


def test_annotation_emitter_accepted():
    sidecar = AnnotationSidecar(schema_version=SCHEMA_VERSION, spec_hash="x")
    emitter = AnnotationEmitter(sidecar)
    art = translate(_spec(), _EXIT_ONLY, annotation_emitter=emitter)
    assert art.annotation is sidecar
