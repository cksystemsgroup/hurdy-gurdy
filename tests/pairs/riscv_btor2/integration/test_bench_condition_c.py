"""End-to-end smoke tests for condition C (solver-only) in the bench.

Condition C is the BENCHMARKING.md §3.C condition: the LLM hand-writes
its own encoding into a solver's input language with no help from the
pair (no schema, no `compile`, no `lift`). The harness exposes a
single `tool_solve(engine, input_language, input_text, options)` tool
implemented at `bench/riscv-btor2/harness.py:tool_solve`.

These tests prove:

1. `tool_solve` correctly dispatches z3 on hand-written SMT-LIB and
   parses the sat/unsat/unknown verdict.
2. The disallowed-pair (e.g., z3 + btor2, bitwuzla anything) and
   missing-binary paths return structured `error` results without
   raising.
3. A tiny reference encoder can hand-encode a corpus task and reach
   the same verdict that the pair-equipped condition B reaches —
   demonstrating the C path is end-to-end functional and that an
   LLM under C *could* succeed on a corpus task if it produced a
   faithful encoding.

The pono path is exercised lazily: locally pono isn't on PATH, so
the pono cells return `error` and we just assert that the error path
is structured correctly.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
BENCH = REPO / "bench" / "riscv-btor2"

sys.path.insert(0, str(BENCH))

# bench/*/harness.py are distinct top-level modules sharing the name "harness";
# another pair's bench (e.g. aarch64) may have cached it first. Drop any cached
# "harness" so this resolves to riscv's from the freshly-inserted path[0].
sys.modules.pop("harness", None)
from harness import tool_solve  # type: ignore  # noqa: E402


# ---------------------------------------------------------------------------
# Smoke tests for tool_solve directly
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("z3") is None, reason="z3 binary not on PATH")
def test_tool_solve_z3_smt2_sat():
    res = tool_solve(
        engine="z3",
        input_language="smt2",
        input_text="(declare-const x Int)\n(assert (= x 5))\n(check-sat)\n",
    )
    assert res["verdict"] == "sat", res


@pytest.mark.skipif(shutil.which("z3") is None, reason="z3 binary not on PATH")
def test_tool_solve_z3_smt2_unsat():
    res = tool_solve(
        engine="z3",
        input_language="smt2",
        input_text="(declare-const x Int)\n(assert (and (= x 5) (= x 6)))\n(check-sat)\n",
    )
    assert res["verdict"] == "unsat", res


@pytest.mark.skipif(shutil.which("z3") is None, reason="z3 binary not on PATH")
def test_tool_solve_z3_appends_check_sat_when_missing():
    """Cooperative behaviour: if the LLM forgets `(check-sat)`,
    the harness appends one rather than returning unknown for
    syntactic reasons."""
    res = tool_solve(
        engine="z3",
        input_language="smt2",
        input_text="(declare-const x Int)\n(assert (= x 5))\n",
    )
    assert res["verdict"] == "sat", res


def test_tool_solve_rejects_disallowed_pair():
    """z3 + btor2 isn't a supported combination."""
    res = tool_solve(
        engine="z3",
        input_language="btor2",
        input_text="",
    )
    assert res["verdict"] == "error"
    assert "not allowed" in res["stderr"]


def test_tool_solve_rejects_unsupported_engine():
    """An engine name that isn't in _SOLVE_ALLOWED returns a
    structured error rather than raising. ``cvc5 + btor2`` is the
    closest live miss — cvc5 only consumes SMT-LIB."""
    res = tool_solve(
        engine="cvc5",
        input_language="btor2",
        input_text="",
    )
    assert res["verdict"] == "error"


# ---------------------------------------------------------------------------
# bitwuzla CLI (pinned in the bench Docker image; locally optional)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("bitwuzla") is None, reason="bitwuzla binary not on PATH")
def test_tool_solve_bitwuzla_smt2_sat():
    res = tool_solve(
        engine="bitwuzla",
        input_language="smt2",
        input_text="(set-logic QF_BV)\n(declare-const x (_ BitVec 8))\n(assert (= x (_ bv5 8)))\n(check-sat)\n",
    )
    assert res["verdict"] == "sat", res


@pytest.mark.skipif(shutil.which("bitwuzla") is None, reason="bitwuzla binary not on PATH")
def test_tool_solve_bitwuzla_smt2_unsat():
    res = tool_solve(
        engine="bitwuzla",
        input_language="smt2",
        input_text="(set-logic QF_BV)\n(declare-const x (_ BitVec 8))\n(assert (and (= x (_ bv5 8)) (= x (_ bv6 8))))\n(check-sat)\n",
    )
    assert res["verdict"] == "unsat", res


def test_tool_solve_bitwuzla_btor2_rejected():
    """bitwuzla's CLI does not handle the BTOR2 model-checking
    extensions (state/init/next/bad), so the (bitwuzla, btor2)
    combination is excluded from _SOLVE_ALLOWED. Verify the
    rejection is structured (error verdict, no exception)."""
    res = tool_solve(
        engine="bitwuzla",
        input_language="btor2",
        input_text="1 sort bitvec 1\n",
    )
    assert res["verdict"] == "error"
    assert "not allowed" in res["stderr"]


# ---------------------------------------------------------------------------
# cvc5 CLI (pinned in the bench Docker image; locally optional)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 binary not on PATH")
def test_tool_solve_cvc5_smt2_sat():
    res = tool_solve(
        engine="cvc5",
        input_language="smt2",
        input_text="(set-logic QF_BV)\n(declare-const x (_ BitVec 8))\n(assert (= x (_ bv5 8)))\n(check-sat)\n",
    )
    assert res["verdict"] == "sat", res


@pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 binary not on PATH")
def test_tool_solve_cvc5_smt2_unsat():
    res = tool_solve(
        engine="cvc5",
        input_language="smt2",
        input_text="(set-logic QF_BV)\n(declare-const x (_ BitVec 8))\n(assert (and (= x (_ bv5 8)) (= x (_ bv6 8))))\n(check-sat)\n",
    )
    assert res["verdict"] == "unsat", res


# When cvc5 isn't installed locally, the missing-binary path must
# return a structured error rather than raising.
def test_tool_solve_cvc5_missing_binary_returns_error():
    if shutil.which("cvc5") is not None:
        pytest.skip("cvc5 is installed; this test only meaningful when missing")
    res = tool_solve(
        engine="cvc5",
        input_language="smt2",
        input_text="(check-sat)\n",
    )
    assert res["verdict"] == "error"
    assert "not found" in res["stderr"]


@pytest.mark.skipif(shutil.which("z3") is None, reason="z3 binary not on PATH")
def test_tool_solve_z3_smt2_bitvector_sat():
    """Closer to a real condition-C encoding: 64-bit bvadd of two
    bitvector constants. This is the kind of fragment an LLM under
    C would emit when trying to encode `addi x10, x10, 7` style
    instructions."""
    res = tool_solve(
        engine="z3",
        input_language="smt2",
        input_text="""
            (set-logic QF_BV)
            (declare-const x10_initial (_ BitVec 64))
            (declare-const x10_final   (_ BitVec 64))
            (assert (= x10_initial (_ bv5 64)))
            (assert (= x10_final (bvadd x10_initial (_ bv7 64))))
            (assert (= x10_final (_ bv12 64)))
            (check-sat)
        """,
    )
    assert res["verdict"] == "sat", res


# ---------------------------------------------------------------------------
# Reference encoder: hand-encode a corpus task and dispatch.
#
# This proves the condition-C path is end-to-end functional: an LLM
# that produced a faithful SMT-LIB encoding of corpus task
# 0007-simple-add-baseline ("can x10 = 12 after addi-and-add halts?")
# would get the same verdict the pair-equipped condition B reaches.
# ---------------------------------------------------------------------------


CORPUS_0007_REFERENCE_SMT2 = r"""
; Reference SMT-LIB encoding of corpus task 0007-simple-add-baseline.
;
; Source program (RV64IMC, 4 instructions, halts at PC 0x10008):
;   _start:
;     addi x5, zero, 5
;     addi x6, zero, 7
;     add  x10, x5, x6     ; x10 = 12
;     ebreak
;
; Question: at halt PC 0x10008, can register x10 hold the value 12?
;
; Encoding strategy: only model the values of x5, x6, x10 after each
; relevant instruction. PC tracking is omitted because the program
; is straight-line; we directly assert the post-halt register state.
(set-logic QF_BV)
(declare-const x5  (_ BitVec 64))
(declare-const x6  (_ BitVec 64))
(declare-const x10 (_ BitVec 64))
(assert (= x5  (_ bv5 64)))
(assert (= x6  (_ bv7 64)))
(assert (= x10 (bvadd x5 x6)))
; Property: can x10 = 12 at halt? (sat = reachable, unsat = unreachable.)
(assert (= x10 (_ bv12 64)))
(check-sat)
"""


@pytest.mark.skipif(shutil.which("z3") is None, reason="z3 binary not on PATH")
def test_condition_c_reference_encoder_matches_corpus_oracle():
    """The reference SMT-LIB encoding for 0007-simple-add-baseline
    should return `sat` from z3 — which under condition C's
    sat→reachable mapping matches the corpus's
    `expected_verdict = reachable`. This demonstrates a hand-
    encoded condition-C answer reaches the same conclusion as the
    pair-mediated condition B."""
    res = tool_solve(
        engine="z3",
        input_language="smt2",
        input_text=CORPUS_0007_REFERENCE_SMT2,
    )
    assert res["verdict"] == "sat", res
    # And the inverse: asking for an unreachable value (e.g., x10 = 99)
    # under the same encoding should be unsat.
    res = tool_solve(
        engine="z3",
        input_language="smt2",
        input_text=CORPUS_0007_REFERENCE_SMT2.replace(
            "(assert (= x10 (_ bv12 64)))",
            "(assert (= x10 (_ bv99 64)))",
        ),
    )
    assert res["verdict"] == "unsat", res
