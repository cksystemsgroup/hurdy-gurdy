"""Tests for the crn-smtlib reasoning pair (chemistry -> SMT-LIB).

Dependency-free: the SMT solver is z3's Python package (no Docker). Exercises
the parser, the transparent SMT-LIB encoding (structure + determinism), the full
tool surface (compile -> dispatch -> lift) on reachable/unreachable questions,
spec validation, and graph integration."""

from __future__ import annotations

import pytest

from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.dispatch import dispatch
from gurdy.core.tools.lift import lift
from gurdy.pairs.crn_smtlib import CRN_LANG, PAIR, SMTLIB_LANG
from gurdy.pairs.crn_smtlib.model import CrnParseError, parse_crn
from gurdy.pairs.crn_smtlib.spec import CrnAnalysis, CrnSpec, CrnTarget, validate_crn_spec
from gurdy.pairs.crn_smtlib.translate import emit_smtlib

try:
    import z3 as _z3  # noqa: F401

    _HAS_Z3 = True
except ImportError:  # pragma: no cover
    _HAS_Z3 = False

_needs_z3 = pytest.mark.skipif(not _HAS_Z3, reason="z3 not installed")

INTERCONV = "A -> B\nB -> A"  # A+B conserved
INFLOW = "-> A"  # unbounded production of A


@pytest.fixture(autouse=True)
def _register():
    # idempotent re-registration so graph tests survive a registry clear
    from gurdy.core.language import register_language
    from gurdy.core.pair import register_pair

    register_pair(PAIR)
    register_language(CRN_LANG)
    register_language(SMTLIB_LANG)
    yield


# --- parser ---------------------------------------------------------------


def test_parse_basic():
    crn = parse_crn("r_fwd: A -> B\nB -> A")
    assert crn.species == ("A", "B")  # sorted
    assert [r.name for r in crn.reactions] == ["r_fwd", "r1"]
    assert crn.reactions[0].reactants == (("A", 1),)
    assert crn.reactions[0].products == (("B", 1),)


def test_parse_coefficients_and_flows():
    crn = parse_crn("2 A -> C\n-> A\nA ->")
    assert crn.species == ("A", "C")
    assert crn.reactions[0].reactants == (("A", 2),)
    assert crn.reactions[1].reactants == ()  # inflow
    assert crn.reactions[2].products == ()  # outflow


@pytest.mark.parametrize("bad", ["", "A B", "A -", "1 -> A", "0 A -> B", "A -> -> B"])
def test_parse_rejects_malformed(bad):
    with pytest.raises(CrnParseError):
        parse_crn(bad)


# --- encoding -------------------------------------------------------------


def test_emit_structure_and_determinism():
    crn = parse_crn(INTERCONV)
    spec = CrnSpec(initial={"A": 2}, target=CrnTarget("B", ">=", 1), bound=2)
    smt = emit_smtlib(spec, crn)
    assert emit_smtlib(spec, crn) == smt  # deterministic
    assert "(set-logic QF_LIA)" in smt
    assert "; @crn-meta " in smt
    assert "(check-sat)" in smt
    assert "(declare-const x_A_0 Int)" in smt
    assert "(assert (= x_A_0 2))" in smt  # initial


def test_emit_rejects_unknown_species():
    crn = parse_crn(INTERCONV)
    with pytest.raises(ValueError):
        emit_smtlib(CrnSpec(target=CrnTarget("Z"), bound=1), crn)


# --- validation -----------------------------------------------------------


def test_validate_rejects_unknown_target():
    crn = parse_crn(INTERCONV)
    diags = validate_crn_spec(CrnSpec(target=CrnTarget("Z"), bound=1), crn)
    assert any("unknown-target-species" in d.code for d in diags)


def test_validate_accepts_good_spec():
    crn = parse_crn(INTERCONV)
    spec = CrnSpec(initial={"A": 2}, target=CrnTarget("B", ">=", 1), bound=1)
    assert validate_crn_spec(spec, crn) == []


# --- end to end (z3) ------------------------------------------------------


@_needs_z3
def test_reachable_target_with_trajectory():
    spec = CrnSpec(
        initial={"A": 2}, target=CrnTarget("B", ">=", 1), bound=1,
        analysis=CrnAnalysis(engine="z3-smt"),
    )
    artifact = compile_spec(spec, INTERCONV)
    raw = dispatch(artifact, spec.analysis)
    assert raw.verdict == "reachable", raw.reason

    result = lift(artifact, raw)
    assert result["verdict"] == "reachable"
    assert result["trajectory"] is not None
    # the target species actually reaches the threshold somewhere in the witness
    assert any(step["counts"]["B"] >= 1 for step in result["trajectory"])
    # exactly `bound` reactions fired
    assert len(result["fired"]) == 1


@_needs_z3
def test_unreachable_within_bound():
    # A + B is conserved at 2, so B >= 5 is impossible at any bound.
    spec = CrnSpec(
        initial={"A": 2}, target=CrnTarget("B", ">=", 5), bound=5,
        analysis=CrnAnalysis(engine="z3-smt"),
    )
    artifact = compile_spec(spec, INTERCONV)
    raw = dispatch(artifact, spec.analysis)
    assert raw.verdict == "unreachable", raw.reason
    assert lift(artifact, raw)["trajectory"] is None


@_needs_z3
def test_inflow_reaches_threshold():
    spec = CrnSpec(
        initial={}, target=CrnTarget("A", ">=", 3), bound=3,
        analysis=CrnAnalysis(engine="z3-smt"),
    )
    artifact = compile_spec(spec, INFLOW)
    raw = dispatch(artifact, spec.analysis)
    assert raw.verdict == "reachable", raw.reason
    assert lift(artifact, raw)["trajectory"][-1]["counts"]["A"] >= 3


@_needs_z3
def test_artifact_is_deterministic():
    spec = CrnSpec(initial={"A": 2}, target=CrnTarget("B", ">=", 1), bound=2)
    a = compile_spec(spec, INTERCONV)
    b = compile_spec(spec, INTERCONV)
    assert a.flattened == b.flattened


# --- graph integration ----------------------------------------------------


def test_registered_in_graph():
    from gurdy.core.language import get_language, list_languages
    from gurdy.core.pair import list_pairs
    from gurdy.core.route import routes

    assert "crn-smtlib" in list_pairs()  # a reasoning pair
    (r,) = routes("crn", "smtlib")
    assert r.hops == ("crn-smtlib",)
    assert r.trust.value == "transparent"
    assert "crn" in list_languages(kind="input")
    assert "smtlib" in list_languages(kind="reasoning")
    assert "z3-smt" in get_language("smtlib").reasons_via
