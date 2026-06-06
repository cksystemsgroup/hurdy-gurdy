"""Tests for the BTOR2 -> SMT-LIB bridge.

Dependency-free (z3 Python; no Docker). The headline test is the cross-check:
the bridge's verdict must match riscv-btor2's *native* z3-bmc solver on the same
BTOR2 — the "many chains, one question" translator-bug detector."""

from __future__ import annotations

import types

import pytest

from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.dispatch import dispatch
from gurdy.core.tools.lift import lift
from gurdy.pairs.btor2_smtlib import PAIR
from gurdy.pairs.btor2_smtlib.spec import Btor2SmtSpec
from gurdy.pairs.btor2_smtlib.translate import BridgeError, encode_bmc, parse_btor2

try:
    import z3 as _z3  # noqa: F401

    _HAS_Z3 = True
except ImportError:  # pragma: no cover
    _HAS_Z3 = False

_needs_z3 = pytest.mark.skipif(not _HAS_Z3, reason="z3 not installed")

# bad holds at the initial state (reachable at any bound).
REACH0 = """
1 sort bitvec 2
2 sort bitvec 1
3 zero 1
4 state 1 c
5 init 1 4 3
6 eq 2 4 3
7 bad 6
"""

# 2-bit counter; bad when c == 3 (reachable in 3 steps).
COUNTER2 = """
1 sort bitvec 2
2 sort bitvec 1
3 zero 1
4 state 1 c
5 init 1 4 3
6 one 1
7 add 1 4 6
8 next 1 4 7
9 ones 1
10 eq 2 4 9
11 bad 10
"""

# 3-bit counter; bad when c == 7 (unreachable within bound 3: c only reaches 3).
COUNTER3_UNREACH = """
1 sort bitvec 3
2 sort bitvec 1
3 zero 1
4 state 1 c
5 init 1 4 3
6 one 1
7 add 1 4 6
8 next 1 4 7
9 constd 1 7
10 eq 2 4 9
11 bad 10
"""


@pytest.fixture(autouse=True)
def _register():
    from gurdy.core.hop import register_hop
    from gurdy.core.pair import register_pair
    from gurdy.hops.c_riscv import C_RISCV
    from gurdy.pairs.riscv_btor2 import PAIR as RISCV_PAIR

    register_pair(RISCV_PAIR)  # for the rv64-elf -> btor2 edge + btor2 language
    register_hop(C_RISCV)  # for the c -> rv64-elf edge (3-hop routes)
    register_pair(PAIR)
    yield


def _bridge_verdict(btor2_text, bound):
    spec = Btor2SmtSpec(bound=bound)
    artifact = compile_spec(spec, btor2_text)
    return dispatch(artifact, spec.analysis).verdict


def _native_verdict(btor2_text, bound):
    from gurdy.pairs.riscv_btor2.solvers.z3bmc import Z3BMCSolver

    directive = types.SimpleNamespace(bound=bound, engine="z3-bmc", timeout=None)
    return Z3BMCSolver().dispatch(btor2_text.encode(), directive).verdict


# --- encoding -------------------------------------------------------------


def test_encode_structure_and_determinism():
    model = parse_btor2(COUNTER2)
    smt = encode_bmc(model, 2)
    assert encode_bmc(model, 2) == smt  # deterministic
    assert "(set-logic QF_BV)" in smt
    assert "; @btor2-bmc " in smt
    assert "(check-sat)" in smt


def test_unsupported_op_raises():
    bt = "1 sort bitvec 2\n2 state 1 c\n3 redand 1 2\n4 bad 3\n"
    with pytest.raises(BridgeError):
        encode_bmc(parse_btor2(bt), 1)


# --- end to end (z3) ------------------------------------------------------


@_needs_z3
def test_reachable_and_witness():
    spec = Btor2SmtSpec(bound=3)
    artifact = compile_spec(spec, COUNTER2)
    raw = dispatch(artifact, spec.analysis)
    assert raw.verdict == "reachable", raw.reason
    result = lift(artifact, raw)
    assert result["witness"] is not None
    # the counter actually reaches 3 somewhere in the witness
    assert any(step["state"].get("c") == 3 for step in result["witness"])


@_needs_z3
def test_unreachable_within_bound():
    spec = Btor2SmtSpec(bound=2)  # c reaches at most 2
    raw = dispatch(compile_spec(spec, COUNTER2), spec.analysis)
    assert raw.verdict == "unreachable", raw.reason


# --- cross-check against the native BTOR2 solver --------------------------


@_needs_z3
@pytest.mark.parametrize(
    "btor2,bound",
    [
        (REACH0, 3),  # reachable at init
        (COUNTER2, 5),  # reachable (deeper)
        (COUNTER3_UNREACH, 3),  # unreachable within bound
    ],
)
def test_cross_check_matches_native_solver(btor2, bound):
    bridged = _bridge_verdict(btor2, bound)
    native = _native_verdict(btor2, bound)
    assert bridged == native, f"bridge={bridged} native={native}"


# --- graph integration ----------------------------------------------------


def test_bridge_connects_the_hubs():
    from gurdy.core.route import routes

    assert [r.hops for r in routes("btor2", "smtlib")] == [("btor2-smtlib",)]

    # The bridge now gives rv64-elf (and c) a multi-hop path to the SMT hub.
    (two_hop,) = routes("rv64-elf", "smtlib")
    assert two_hop.hops == ("riscv-btor2", "btor2-smtlib")
    assert two_hop.trust.value == "transparent"

    (three_hop,) = routes("c", "smtlib")
    assert three_hop.hops == ("c-riscv", "riscv-btor2", "btor2-smtlib")
    assert three_hop.trust.value == "reproducible"  # weakest hop (c-riscv)
