from textwrap import dedent

from gurdy.pairs.riscv_btor2.btor2.nodes import (
    ArraySort,
    BitvecSort,
    Comment,
    Model,
    Node,
)
from gurdy.pairs.riscv_btor2.btor2.parser import from_text
from gurdy.pairs.riscv_btor2.btor2.printer import to_text


def test_round_trip_basic_counter():
    text = dedent(
        """\
        ; tiny counter
        1 sort bitvec 1
        2 sort bitvec 64
        3 zero 2
        4 state 2 pc
        5 init 2 4 3
        6 one 2
        7 add 2 4 6
        8 next 2 4 7
        9 ones 2
        10 eq 1 4 9
        11 bad 10
        """
    )
    result = from_text(text)
    assert not result.has_errors(), result.diagnostics
    rebuilt = to_text(result.model)
    assert rebuilt == text


def test_round_trip_array_sort_and_states():
    text = dedent(
        """\
        1 sort bitvec 64
        2 sort bitvec 8
        3 sort array 1 2
        4 state 3 mem
        5 input 1 addr
        6 zero 2
        7 write 3 4 5 6
        8 next 3 4 7
        """
    )
    result = from_text(text)
    assert not result.has_errors()
    assert to_text(result.model) == text


def test_inline_and_standalone_comments_preserved():
    text = dedent(
        """\
        1 sort bitvec 32
        2 zero 1  ; baseline zero
        ; section break
        3 state 1 x
        4 init 1 3 2
        """
    )
    result = from_text(text)
    assert not result.has_errors()
    assert to_text(result.model) == text


def test_blank_lines_preserved():
    text = "1 sort bitvec 8\n\n2 zero 1\n"
    result = from_text(text)
    assert to_text(result.model) == text


def test_unknown_op_passes_through_with_args():
    # Some HWMCC files use ops the framework doesn't model semantically.
    text = "1 sort bitvec 4\n2 magic_op 1 0 1\n"
    result = from_text(text)
    assert not result.has_errors()
    n = result.model.by_nid(2)
    assert n is not None
    assert n.op == "magic_op"
    assert n.args == ["1", "0", "1"]


def test_constructed_model_round_trips():
    m = Model()
    s_bv1 = Node(nid=1, op="sort", sort=BitvecSort(width=1))
    s_bv64 = Node(nid=2, op="sort", sort=BitvecSort(width=64))
    z = Node(nid=3, op="zero", args=["2"])
    s = Node(nid=4, op="state", args=["2"], symbol="pc")
    init = Node(nid=5, op="init", args=["2", "4", "3"])
    for n in (s_bv1, s_bv64, z, s, init):
        m.append(n)
    text = to_text(m)
    rebuilt = from_text(text)
    assert not rebuilt.has_errors()
    assert to_text(rebuilt.model) == text


def test_malformed_lines_emit_diagnostics():
    text = "abc not an nid\n2\n3 sort\n"
    result = from_text(text)
    assert result.has_errors()
    codes = [d.code for d in result.diagnostics]
    assert "btor2/parse/0001" in codes
    assert "btor2/parse/0002" in codes
    assert "btor2/parse/0010" in codes


def test_sort_with_symbol_round_trips():
    text = "1 sort bitvec 32 word\n"
    result = from_text(text)
    assert not result.has_errors()
    n = result.model.by_nid(1)
    assert isinstance(n.sort, BitvecSort)
    assert n.symbol == "word"
    assert to_text(result.model) == text


def test_state_with_symbol_recognized():
    text = "1 sort bitvec 64\n2 state 1 sp\n"
    result = from_text(text)
    n = result.model.by_nid(2)
    assert n.symbol == "sp"
    assert n.args == ["1"]


def test_array_sort_element_lookup():
    text = "1 sort bitvec 64\n2 sort bitvec 8\n3 sort array 1 2 mem_sort\n"
    result = from_text(text)
    n = result.model.by_nid(3)
    assert isinstance(n.sort, ArraySort)
    assert n.sort.index_sort_nid == 1
    assert n.sort.element_sort_nid == 2
    assert n.symbol == "mem_sort"
