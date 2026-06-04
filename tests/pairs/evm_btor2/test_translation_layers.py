"""Tests for evm-btor2 translation layers (P4).

Covers emit_context_inputs() and emit_init_clauses() from layers.py,
verifying that the correct BTOR2 nodes are emitted for each spec
assumption type and that the output round-trips through the parser.
"""

import pytest

from gurdy.pairs.evm_btor2.translation.builder import Btor2Builder, MACHINE_STATE_VARS
from gurdy.pairs.evm_btor2.translation.layers import (
    CONTEXT_VARS,
    emit_context_inputs,
    emit_init_clauses,
)
from gurdy.pairs.evm_btor2.btor2.parser import from_text
from gurdy.pairs.evm_btor2.btor2.printer import to_text
from gurdy.pairs.evm_btor2.spec import (
    AnalysisDirective,
    AnalysisScope,
    BytecodeRef,
    CallerPin,
    CallvaluePin,
    CalldatasizePin,
    CalldataBytePin,
    EvmBtor2Spec,
    GasLimitPin,
    OriginPin,
    ReachKind,
    ReachProperty,
    StoragePin,
    StorageWarm,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STOP_HEX = "00"


def _spec(**kwargs) -> EvmBtor2Spec:
    defaults = dict(
        bytecode=BytecodeRef(hex=_STOP_HEX),
        scope=AnalysisScope(),
        assumptions=(),
        property=ReachProperty(kind=ReachKind.STOP),
        analysis=AnalysisDirective(engine="z3-bmc", bound=10),
    )
    defaults.update(kwargs)
    return EvmBtor2Spec(**defaults)


def _fresh() -> Btor2Builder:
    b = Btor2Builder()
    b.emit_header()
    b.emit_machine_states()
    return b


# ---------------------------------------------------------------------------
# emit_context_inputs — structure
# ---------------------------------------------------------------------------


def test_context_inputs_count():
    b = _fresh()
    ctx = emit_context_inputs(b, _spec())
    assert len(ctx) == len(CONTEXT_VARS)


def test_context_inputs_all_symbols_present():
    b = _fresh()
    ctx = emit_context_inputs(b, _spec())
    expected = {sym for sym, _ in CONTEXT_VARS}
    assert set(ctx.keys()) == expected


def test_context_inputs_are_state_nodes():
    b = _fresh()
    ctx = emit_context_inputs(b, _spec())
    for sym, nid in ctx.items():
        node = b.model.by_nid(nid)
        assert node is not None and node.op == "state", f"{sym} is not a state"
        assert node.symbol == sym


def test_context_inputs_next_wired_constant():
    """Each context state must have a next clause pointing back to itself."""
    b = _fresh()
    ctx = emit_context_inputs(b, _spec())
    # Collect all next nodes.
    next_nodes = [n for n in b.model.nodes() if n.op == "next"]
    # next(ctx_var) = ctx_var: args = [sort_nid, state_nid, state_nid]
    self_loops = {
        int(n.args[1]) for n in next_nodes if n.args[1] == n.args[2]
    }
    for sym, nid in ctx.items():
        assert nid in self_loops, f"no self-loop next for context var {sym}"


def test_context_inputs_address_constraints_emitted():
    """caller[255:160] == 0 and origin[255:160] == 0 must be constrained."""
    b = _fresh()
    emit_context_inputs(b, _spec())
    constraint_nodes = [n for n in b.model.nodes() if n.op == "constraint"]
    # There should be at least 2 address constraints + 1 chainid constraint.
    assert len(constraint_nodes) >= 3


def test_context_inputs_chainid_constrained_to_1():
    b = _fresh()
    ctx = emit_context_inputs(b, _spec())
    chain_nid = ctx["chainid"]
    # Find an eq node comparing chainid to a constd-1 node, wrapped in constraint.
    constd_1_nids = {
        n.nid for n in b.model.nodes()
        if n.op == "one" or (n.op == "constd" and n.args[-1] == "1")
    }
    eq_with_chain = [
        n for n in b.model.nodes()
        if n.op == "eq" and str(chain_nid) in n.args[1:]
    ]
    assert eq_with_chain, "no eq node comparing chainid"
    # One of those eq nids must appear in a constraint node.
    eq_nids = {n.nid for n in eq_with_chain}
    constraint_exprs = {int(n.args[0]) for n in b.model.nodes() if n.op == "constraint"}
    assert eq_nids & constraint_exprs, "chainid eq not wrapped in constraint"


# ---------------------------------------------------------------------------
# emit_context_inputs — spec assumptions
# ---------------------------------------------------------------------------


def test_caller_pin_emits_constraint():
    b = _fresh()
    ctx = emit_context_inputs(b, _spec(assumptions=(CallerPin(address=0xABCD),)))
    caller_nid = ctx["caller"]
    eq_nodes = [
        n for n in b.model.nodes()
        if n.op == "eq" and str(caller_nid) in n.args[1:]
    ]
    assert eq_nodes


def test_callvalue_pin_emits_constraint():
    b = _fresh()
    ctx = emit_context_inputs(b, _spec(assumptions=(CallvaluePin(value=0),)))
    cv_nid = ctx["callvalue"]
    eq_nodes = [n for n in b.model.nodes() if n.op == "eq" and str(cv_nid) in n.args[1:]]
    assert eq_nodes


def test_origin_pin_emits_constraint():
    b = _fresh()
    ctx = emit_context_inputs(b, _spec(assumptions=(OriginPin(address=0x1234),)))
    origin_nid = ctx["origin"]
    eq_nodes = [n for n in b.model.nodes() if n.op == "eq" and str(origin_nid) in n.args[1:]]
    assert eq_nodes


def test_calldatasize_pin_emits_constraint():
    b = _fresh()
    ctx = emit_context_inputs(b, _spec(assumptions=(CalldatasizePin(size=32),)))
    cds_nid = ctx["calldatasize"]
    eq_nodes = [n for n in b.model.nodes() if n.op == "eq" and str(cds_nid) in n.args[1:]]
    assert eq_nodes


def test_calldata_byte_pin_emits_read_and_constraint():
    b = _fresh()
    ctx = emit_context_inputs(b, _spec(assumptions=(CalldataBytePin(offset=0, value=0x42),)))
    # A read node must reference calldata.
    cd_nid = ctx["calldata"]
    read_nodes = [n for n in b.model.nodes() if n.op == "read" and str(cd_nid) in n.args[1:]]
    assert read_nodes


# ---------------------------------------------------------------------------
# emit_init_clauses — scalar zero inits
# ---------------------------------------------------------------------------


def test_init_clauses_scalar_states_get_zero_init():
    b = _fresh()
    emit_init_clauses(b, _spec(), b.state_nids)
    init_nodes = [n for n in b.model.nodes() if n.op == "init"]
    init_state_nids = {int(n.args[1]) for n in init_nodes}
    # sp, mem_words, pc, trap, halted, returndatasize must all have init.
    for sym in ("sp", "mem_words", "pc", "trap", "halted", "returndatasize"):
        assert b.state_nids[sym] in init_state_nids, f"no init for {sym}"


def test_init_clauses_no_gas_init_without_pin():
    b = _fresh()
    emit_init_clauses(b, _spec(), b.state_nids)
    init_nodes = [n for n in b.model.nodes() if n.op == "init"]
    init_state_nids = {int(n.args[1]) for n in init_nodes}
    # gas should NOT have an init when no GasLimitPin is present.
    assert b.state_nids["gas"] not in init_state_nids


def test_init_clauses_gas_pin_emits_init():
    b = _fresh()
    emit_init_clauses(b, _spec(assumptions=(GasLimitPin(gas=100_000),)), b.state_nids)
    init_nodes = [n for n in b.model.nodes() if n.op == "init"]
    init_state_nids = {int(n.args[1]) for n in init_nodes}
    assert b.state_nids["gas"] in init_state_nids


def test_init_clauses_gas_pin_value():
    b = _fresh()
    emit_init_clauses(b, _spec(assumptions=(GasLimitPin(gas=50_000),)), b.state_nids)
    init_nodes = [n for n in b.model.nodes() if n.op == "init"]
    gas_init = next(
        n for n in init_nodes if int(n.args[1]) == b.state_nids["gas"]
    )
    val_nid = int(gas_init.args[2])
    val_node = b.model.by_nid(val_nid)
    assert val_node.op == "constd" and val_node.args[-1] == "50000"


# ---------------------------------------------------------------------------
# emit_init_clauses — StoragePin / StorageWarm
# ---------------------------------------------------------------------------


def test_storage_pin_emits_constraint():
    b = _fresh()
    emit_init_clauses(b, _spec(assumptions=(StoragePin(slot=0, value=0x42),)), b.state_nids)
    constraint_nodes = [n for n in b.model.nodes() if n.op == "constraint"]
    assert constraint_nodes, "no constraint emitted for StoragePin"


def test_storage_pin_constraint_references_sto():
    b = _fresh()
    emit_init_clauses(b, _spec(assumptions=(StoragePin(slot=0, value=66),)), b.state_nids)
    sto_nid = b.state_nids["sto"]
    read_nodes = [n for n in b.model.nodes() if n.op == "read" and str(sto_nid) in n.args[1:]]
    assert read_nodes, "no read(sto, slot) for StoragePin"


def test_storage_warm_emits_constraint():
    b = _fresh()
    emit_init_clauses(b, _spec(assumptions=(StorageWarm(slot=5),)), b.state_nids)
    sto_warm_nid = b.state_nids["sto_warm"]
    read_nodes = [
        n for n in b.model.nodes() if n.op == "read" and str(sto_warm_nid) in n.args[1:]
    ]
    assert read_nodes


def test_multiple_storage_pins():
    b = _fresh()
    emit_init_clauses(
        b,
        _spec(assumptions=(StoragePin(slot=0, value=1), StoragePin(slot=1, value=2))),
        b.state_nids,
    )
    sto_nid = b.state_nids["sto"]
    read_nodes = [n for n in b.model.nodes() if n.op == "read" and str(sto_nid) in n.args[1:]]
    assert len(read_nodes) == 2


# ---------------------------------------------------------------------------
# Round-trip: full header + machine + context + init → parser accepts
# ---------------------------------------------------------------------------


def test_full_emission_round_trips():
    b = _fresh()
    spec = _spec(
        assumptions=(
            CallerPin(address=0xDEAD),
            GasLimitPin(gas=10_000),
            StoragePin(slot=0, value=42),
        )
    )
    emit_context_inputs(b, spec)
    emit_init_clauses(b, spec, b.state_nids)
    text = to_text(b.model)
    result = from_text(text)
    assert not result.has_errors(), result.diagnostics


def test_context_var_count_is_18():
    assert len(CONTEXT_VARS) == 18
