"""Tests for the P4 evm-btor2 Btor2Builder.

Covers sort declaration, machine-state declaration, constant emission,
arithmetic helpers, and round-trip through the BTOR2 printer/parser.
"""

import pytest

from gurdy.pairs.evm_btor2.translation.builder import (
    Btor2Builder,
    EVM_ARRAY_SORTS,
    EVM_BITVEC_SORTS,
    MACHINE_STATE_VARS,
)
from gurdy.pairs.evm_btor2.btor2.nodes import BitvecSort, ArraySort
from gurdy.pairs.evm_btor2.btor2.parser import from_text
from gurdy.pairs.evm_btor2.btor2.printer import to_text
from gurdy.pairs.evm_btor2.btor2.evaluator import evaluate


# ---------------------------------------------------------------------------
# Sort declaration
# ---------------------------------------------------------------------------


def test_emit_header_declares_all_bitvec_sorts():
    b = Btor2Builder()
    b.emit_header()
    for name, width in EVM_BITVEC_SORTS:
        assert name in b.sort_nids, f"missing bitvec sort {name}"
        node = b.model.by_nid(b.sort_nids[name])
        assert node is not None
        assert isinstance(node.sort, BitvecSort)
        assert node.sort.width == width


def test_emit_header_declares_all_array_sorts():
    b = Btor2Builder()
    b.emit_header()
    for name, idx, elt in EVM_ARRAY_SORTS:
        assert name in b.sort_nids, f"missing array sort {name}"
        node = b.model.by_nid(b.sort_nids[name])
        assert node is not None
        assert isinstance(node.sort, ArraySort)
        assert node.sort.index_sort_nid == b.sort_nids[idx]
        assert node.sort.element_sort_nid == b.sort_nids[elt]


def test_emit_header_idempotent():
    b = Btor2Builder()
    nids1 = b.emit_header()
    nids2 = b.emit_header()
    assert nids1 == nids2
    # No duplicate nodes emitted.
    sort_nodes = [n for n in b.model.nodes() if n.op == "sort"]
    assert len(sort_nodes) == len(EVM_BITVEC_SORTS) + len(EVM_ARRAY_SORTS)


def test_declare_sort_on_demand():
    b = Btor2Builder()
    nid = b.declare_sort("bv32")
    assert nid == b.sort_nids["bv32"]
    node = b.model.by_nid(nid)
    assert isinstance(node.sort, BitvecSort) and node.sort.width == 32


def test_declare_unknown_sort_raises():
    b = Btor2Builder()
    with pytest.raises(KeyError):
        b.declare_sort("notasort")


# ---------------------------------------------------------------------------
# Machine-state declarations
# ---------------------------------------------------------------------------


def test_emit_machine_states_after_header():
    b = Btor2Builder()
    b.emit_header()
    state_nids = b.emit_machine_states()
    for sym, sort_name in MACHINE_STATE_VARS:
        assert sym in state_nids, f"missing state {sym}"
        node = b.model.by_nid(state_nids[sym])
        assert node is not None and node.op == "state"
        assert node.symbol == sym
        assert node.args[0] == str(b.sort_nids[sort_name])


def test_emit_machine_states_count():
    b = Btor2Builder()
    b.emit_header()
    state_nids = b.emit_machine_states()
    assert len(state_nids) == len(MACHINE_STATE_VARS)


def test_machine_state_symbols_match_schema():
    """State symbols must exactly match SCHEMA.md §3 canonical names."""
    expected = {sym for sym, _ in MACHINE_STATE_VARS}
    assert expected == {
        "sp", "stack", "mem", "mem_words", "sto", "pc", "gas",
        "trap", "halted", "returndata", "returndatasize", "sto_warm",
    }


def test_bv1_states_trap_and_halted_declared():
    b = Btor2Builder()
    b.emit_header()
    b.emit_machine_states()
    for sym in ("trap", "halted"):
        nid = b.state_nids[sym]
        node = b.model.by_nid(nid)
        sort_nid = int(node.args[0])
        sort_node = b.model.by_nid(sort_nid)
        assert isinstance(sort_node.sort, BitvecSort) and sort_node.sort.width == 1


# ---------------------------------------------------------------------------
# Constant emission
# ---------------------------------------------------------------------------


def test_const_zero_emits_zero_op():
    b = Btor2Builder()
    b.emit_header()
    nid = b.const("bv256", 0)
    node = b.model.by_nid(nid)
    assert node.op == "zero"


def test_const_one_emits_one_op():
    b = Btor2Builder()
    b.emit_header()
    nid = b.const("bv256", 1)
    node = b.model.by_nid(nid)
    assert node.op == "one"


def test_const_large_emits_constd():
    b = Btor2Builder()
    b.emit_header()
    nid = b.const("bv256", 0x42)
    node = b.model.by_nid(nid)
    assert node.op == "constd" and node.args[1] == "66"


def test_const_cached():
    b = Btor2Builder()
    b.emit_header()
    nid1 = b.const("bv256", 42)
    nid2 = b.const("bv256", 42)
    assert nid1 == nid2


# ---------------------------------------------------------------------------
# Arithmetic helpers
# ---------------------------------------------------------------------------


def test_add_emits_correct_node():
    b = Btor2Builder()
    b.emit_header()
    a = b.const("bv256", 3)
    c = b.const("bv256", 5)
    r = b.add("bv256", a, c)
    node = b.model.by_nid(r)
    assert node.op == "add"
    assert node.args[1] == str(a) and node.args[2] == str(c)


def test_eq_result_is_bv1():
    b = Btor2Builder()
    b.emit_header()
    a = b.const("bv256", 7)
    c = b.const("bv256", 7)
    r = b.eq(a, c)
    node = b.model.by_nid(r)
    assert node.op == "eq"
    assert node.args[0] == str(b.sort_nids["bv1"])


def test_ite_helper():
    b = Btor2Builder()
    b.emit_header()
    cond = b.const("bv1", 1)
    a = b.const("bv256", 10)
    c = b.const("bv256", 20)
    r = b.ite("bv256", cond, a, c)
    node = b.model.by_nid(r)
    assert node.op == "ite"


# ---------------------------------------------------------------------------
# Round-trip: built model parses back without errors
# ---------------------------------------------------------------------------


def test_header_round_trips():
    b = Btor2Builder()
    b.emit_header()
    text = to_text(b.model)
    result = from_text(text)
    assert not result.has_errors()
    assert len(result.model.nodes()) == len(b.model.nodes())


def test_machine_states_round_trip():
    b = Btor2Builder()
    b.emit_header()
    b.emit_machine_states()
    text = to_text(b.model)
    result = from_text(text)
    assert not result.has_errors()
    state_nodes = [n for n in result.model.nodes() if n.op == "state"]
    assert len(state_nodes) == len(MACHINE_STATE_VARS)


def test_full_tiny_model_evaluates():
    """Build a tiny halted/trap model with the builder and evaluate it."""
    b = Btor2Builder()
    b.emit_header()
    # two bv1 states
    h_nid = b.state("bv1", "halted")
    t_nid = b.state("bv1", "trap")
    z1 = b.const("bv1", 0)
    b.emit_no_sort("init", b.sort_nids["bv1"], h_nid, z1)
    b.emit_no_sort("init", b.sort_nids["bv1"], t_nid, z1)
    # halted' = 1 (always)
    one1 = b.const("bv1", 1)
    b.emit_no_sort("next", b.sort_nids["bv1"], h_nid, one1)
    # trap' = halted
    b.emit_no_sort("next", b.sort_nids["bv1"], t_nid, h_nid)
    # bad = halted AND trap
    bad_expr = b.and_("bv1", h_nid, t_nid)
    b.bad(bad_expr)

    # Evaluate step-0 with both states=0: bad should be 0
    vals = evaluate(b.model, bindings={h_nid: 0, t_nid: 0})
    assert vals.get(bad_expr, 0) == 0

    # With halted=1, trap=1: bad fires
    vals2 = evaluate(b.model, bindings={h_nid: 1, t_nid: 1})
    assert vals2.get(bad_expr, 0) == 1
