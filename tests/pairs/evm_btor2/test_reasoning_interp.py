"""Tests for the P3 evm-btor2 reasoning interpreter.

Covers the BTOR2 parser, evaluator, printer, and the multi-step
reasoning interpreter.  All tests use hand-constructed BTOR2 text so
that no translator is required at this phase.

BTOR2 primer for the examples below:
  - ``sort bitvec N`` declares an N-bit integer sort.
  - ``state S sym`` declares a state variable of sort S with name sym.
  - ``input S sym`` declares a symbolic (free) input of sort S.
  - ``init S state val`` sets the initial value of state.
  - ``next S state expr`` wires the next-cycle value of state.
  - ``bad expr`` asserts the bad-state condition (bv1 expression).
  - ``constd S N`` is the constant integer N at sort S.
  - ``add S a b`` is a + b (modular, sort S).
  - ``eq  S a b`` is a == b → bv1.
"""

import json
import pathlib

import pytest

from gurdy.pairs.evm_btor2.btor2.nodes import BitvecSort, Model, Node, Comment
from gurdy.pairs.evm_btor2.btor2.parser import from_text
from gurdy.pairs.evm_btor2.btor2.printer import to_text
from gurdy.pairs.evm_btor2.btor2.evaluator import evaluate, SortMismatch
from gurdy.pairs.evm_btor2.reasoning_interp import (
    Btor2ReasoningBinding,
    Btor2ReasoningInterpreter,
    INTERPRETER_VERSION,
)
from gurdy.core.pair import CompiledArtifact
from gurdy.core.annotation.sidecar import AnnotationSidecar
from gurdy.core.pair import Layer
from gurdy.pairs.evm_btor2.spec import EvmBtor2Spec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CORPUS = pathlib.Path(__file__).parent.parent.parent.parent / "bench" / "evm-btor2" / "corpus" / "seed"


def _make_artifact(btor2_text: str) -> CompiledArtifact:
    body = btor2_text.encode("utf-8")
    return CompiledArtifact(
        pair="evm-btor2",
        layers={"all": Layer(name="all", body=body, content_hash="x")},
        annotation=AnnotationSidecar(),
        flattened=body,
        schema_version="1.0.0",
        spec_hash="x",
    )


def _make_binding(**state_init) -> Btor2ReasoningBinding:
    return Btor2ReasoningBinding(state_init_by_symbol=state_init)


# ---------------------------------------------------------------------------
# BTOR2 parser: basic smoke tests
# ---------------------------------------------------------------------------


def test_parse_empty():
    result = from_text("")
    assert not result.has_errors()
    assert result.model.nodes() == []


def test_parse_comment_only():
    result = from_text("; this is a comment\n")
    assert not result.has_errors()
    assert result.model.nodes() == []


def test_parse_bitvec_sort():
    result = from_text("1 sort bitvec 256\n")
    assert not result.has_errors()
    nodes = result.model.nodes()
    assert len(nodes) == 1
    n = nodes[0]
    assert n.nid == 1 and n.op == "sort"
    assert isinstance(n.sort, BitvecSort) and n.sort.width == 256


def test_parse_state_with_symbol():
    text = "1 sort bitvec 8\n2 state 1 counter\n"
    result = from_text(text)
    assert not result.has_errors()
    state_node = result.model.by_nid(2)
    assert state_node is not None
    assert state_node.symbol == "counter"


def test_parse_bad_nid_error():
    result = from_text("not_an_int sort bitvec 8\n")
    assert result.has_errors()


def test_parse_round_trip():
    """to_text(from_text(text).model) reproduces the original text."""
    text = (
        "; header\n"
        "1 sort bitvec 8\n"
        "2 state 1 counter\n"
        "3 constd 1 0\n"
        "4 init 1 2 3\n"
    )
    result = from_text(text)
    assert not result.has_errors()
    assert to_text(result.model) == text


# ---------------------------------------------------------------------------
# BTOR2 evaluator: arithmetic node values
# ---------------------------------------------------------------------------

_ADD_BTOR2 = """\
1 sort bitvec 8
2 constd 1 3
3 constd 1 5
4 add 1 2 3
"""


def test_evaluate_add():
    result = from_text(_ADD_BTOR2)
    vals = evaluate(result.model)
    assert vals[4] == 8


def test_evaluate_add_wraps():
    text = "1 sort bitvec 8\n2 constd 1 200\n3 constd 1 100\n4 add 1 2 3\n"
    vals = evaluate(from_text(text).model)
    assert vals[4] == (300 & 0xFF)


def test_evaluate_eq_true():
    text = "1 sort bitvec 8\n2 sort bitvec 1\n3 constd 1 7\n4 constd 1 7\n5 eq 2 3 4\n"
    vals = evaluate(from_text(text).model)
    assert vals[5] == 1


def test_evaluate_eq_false():
    text = "1 sort bitvec 8\n2 sort bitvec 1\n3 constd 1 7\n4 constd 1 8\n5 eq 2 3 4\n"
    vals = evaluate(from_text(text).model)
    assert vals[5] == 0


def test_evaluate_ite():
    text = (
        "1 sort bitvec 1\n"
        "2 sort bitvec 8\n"
        "3 constd 1 1\n"
        "4 constd 2 10\n"
        "5 constd 2 20\n"
        "6 ite 2 3 4 5\n"
    )
    vals = evaluate(from_text(text).model)
    assert vals[6] == 10  # cond=1 → then branch


def test_evaluate_sort_mismatch_raises():
    text = (
        "1 sort bitvec 8\n"
        "2 sort bitvec 4\n"
        "3 constd 1 3\n"
        "4 constd 2 5\n"
        "5 add 1 3 4\n"
    )
    with pytest.raises(SortMismatch):
        evaluate(from_text(text).model)


# ---------------------------------------------------------------------------
# Reasoning interpreter: minimal counter model
#
# The model below counts from 0 every step (state += 1).
# After N steps the state value is N.
# We ask: does the counter reach 3 within 5 steps?
#
# BTOR2:
#   1 sort bitvec 8
#   2 state 1 cnt
#   3 constd 1 0
#   4 init 1 2 3         ; cnt_init = 0
#   5 constd 1 1
#   6 add 1 2 5          ; cnt + 1
#   7 next 1 2 6         ; cnt' = cnt + 1
#   8 constd 1 3
#   9 eq 9_sort 2 8      ; cnt == 3?  (sort bv1)
#  10 sort bitvec 1
#   9 eq 10 2 8
#  11 bad 9
# ---------------------------------------------------------------------------

_COUNTER_BTOR2 = """\
1 sort bitvec 8
10 sort bitvec 1
2 state 1 cnt
3 constd 1 0
4 init 1 2 3
5 constd 1 1
6 add 1 2 5
7 next 1 2 6
8 constd 1 3
9 eq 10 2 8
11 bad 9
"""


def test_interpreter_version():
    assert INTERPRETER_VERSION == "1.0.0"


def test_interpreter_counter_bad_fires_at_step_2():
    """Counter starts at 0, increments each step; bad (cnt==3) fires at step 2.

    Step 0: cnt goes 0→1 (POST state=1); bad? 1==3 → no.
    Step 1: cnt goes 1→2 (POST state=2); bad? 2==3 → no.
    Step 2: cnt goes 2→3 (POST state=3); bad? 3==3 → yes.
    """
    interp = Btor2ReasoningInterpreter()
    artifact = _make_artifact(_COUNTER_BTOR2)
    binding = _make_binding()
    trace = interp.run(artifact, binding, max_steps=5)
    assert trace.bad_fired_at == 2


def test_interpreter_counter_no_bad_if_too_few_steps():
    interp = Btor2ReasoningInterpreter()
    artifact = _make_artifact(_COUNTER_BTOR2)
    binding = _make_binding()
    trace = interp.run(artifact, binding, max_steps=2)
    assert trace.bad_fired_at is None


def test_interpreter_counter_state_override():
    """Starting cnt at 2 via binding makes bad fire at step 0."""
    interp = Btor2ReasoningInterpreter()
    artifact = _make_artifact(_COUNTER_BTOR2)
    binding = _make_binding(cnt=2)
    trace = interp.run(artifact, binding, max_steps=5)
    assert trace.bad_fired_at == 0


def test_interpreter_pair_and_version_in_trace():
    interp = Btor2ReasoningInterpreter()
    artifact = _make_artifact(_COUNTER_BTOR2)
    trace = interp.run(artifact, _make_binding(), max_steps=1)
    assert trace.pair == "evm-btor2"
    assert trace.interpreter_version == INTERPRETER_VERSION


def test_interpreter_step_count():
    interp = Btor2ReasoningInterpreter()
    artifact = _make_artifact(_COUNTER_BTOR2)
    trace = interp.run(artifact, _make_binding(), max_steps=4)
    assert len(trace.steps) == 4


# ---------------------------------------------------------------------------
# 2-state halted/trap model (mirrors EVM SCHEMA.md bv1 machine flags)
#
# Two bv1 states, a bv256 counter, no external inputs:
#   counter' = counter + 1                          (starts at 0)
#   halted'  = or(halted, counter == 3)             (sticky once set)
#   trap'    = halted                               (lags halted by 1 step)
#   bad      = and(halted, trap)                    (both 1 simultaneously)
#
# Trace (POST-state after each step, checked for bad):
#   step 0: counter 0→1, halted 0→0, trap 0→0  bad=0
#   step 1: counter 1→2, halted 0→0, trap 0→0  bad=0
#   step 2: counter 2→3, halted 0→0, trap 0→0  bad=0
#   step 3: counter 3→4, halted 0→1 (eq(3,3)), trap 0→0  bad=and(1,0)=0
#   step 4: counter 4→5, halted 1→1, trap 0→1            bad=and(1,1)=1 ← fires
# ---------------------------------------------------------------------------

_HALTED_TRAP_BTOR2 = """\
1 sort bitvec 1
2 sort bitvec 256
3 state 1 halted
4 state 1 trap
5 state 2 counter
6 zero 1
7 init 1 3 6
8 init 1 4 6
9 zero 2
10 init 2 5 9
11 constd 2 1
12 add 2 5 11
13 next 2 5 12
14 constd 2 3
15 eq 1 5 14
16 or 1 3 15
17 next 1 3 16
18 next 1 4 3
19 and 1 3 4
20 bad 19
"""


def test_halted_trap_model_bad_fires_at_step_4():
    """bad (halted AND trap both 1) fires at step 4 per the trace above."""
    interp = Btor2ReasoningInterpreter()
    artifact = _make_artifact(_HALTED_TRAP_BTOR2)
    trace = interp.run(artifact, _make_binding(), max_steps=8)
    assert trace.bad_fired_at == 4


def test_halted_trap_model_no_bad_within_4_steps():
    interp = Btor2ReasoningInterpreter()
    artifact = _make_artifact(_HALTED_TRAP_BTOR2)
    trace = interp.run(artifact, _make_binding(), max_steps=4)
    assert trace.bad_fired_at is None


def test_halted_trap_model_step_layers_contain_both_states():
    """layer_values for each step records state nids including halted and trap."""
    interp = Btor2ReasoningInterpreter()
    artifact = _make_artifact(_HALTED_TRAP_BTOR2)
    trace = interp.run(artifact, _make_binding(), max_steps=2)
    for step in trace.steps:
        machine_layer = step.layer_values.get("machine", {})
        # nids 3 (halted) and 4 (trap) must be present
        assert 3 in machine_layer
        assert 4 in machine_layer


# ---------------------------------------------------------------------------
# Corpus seed round-trip: task.spec.json files parse without error
# ---------------------------------------------------------------------------

_SEED_DIRS = sorted(_CORPUS.glob("0*"))


@pytest.mark.parametrize("seed_dir", _SEED_DIRS, ids=[d.name for d in _SEED_DIRS])
def test_corpus_seed_spec_roundtrip(seed_dir):
    spec_path = seed_dir / "task.spec.json"
    assert spec_path.exists(), f"missing task.spec.json in {seed_dir}"
    obj = json.loads(spec_path.read_text())
    spec = EvmBtor2Spec.from_jsonable(obj)
    # Round-trip back to JSON and parse again.
    obj2 = spec.to_jsonable()
    spec2 = EvmBtor2Spec.from_jsonable(obj2)
    assert spec == spec2


@pytest.mark.parametrize("seed_dir", _SEED_DIRS, ids=[d.name for d in _SEED_DIRS])
def test_corpus_seed_bin_matches_spec(seed_dir):
    """task.bin hex matches the bytecode in task.spec.json."""
    bin_path = seed_dir / "task.bin"
    spec_path = seed_dir / "task.spec.json"
    assert bin_path.exists()
    assert spec_path.exists()
    bin_hex = bin_path.read_text().strip()
    spec_hex = json.loads(spec_path.read_text())["fields"]["bytecode"]["hex"]
    assert bin_hex == spec_hex, (
        f"{seed_dir.name}: task.bin hex {bin_hex!r} != spec hex {spec_hex!r}"
    )
