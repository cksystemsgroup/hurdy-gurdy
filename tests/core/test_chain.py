"""Tests for the generic chain runner (gurdy.core.chain)."""

from __future__ import annotations

import pytest

from gurdy.core.chain import (
    Chain,
    ChainConnectivityError,
    ChainStep,
    StepOutcome,
)
from gurdy.core.hop import (
    CompileHop,
    Tier,
    _clear_registry_for_tests,
    register_hop,
)


@pytest.fixture(autouse=True)
def _clean():
    _clear_registry_for_tests()
    yield
    _clear_registry_for_tests()


def _step(hop, a, b, fn):
    return ChainStep(hop=hop, in_lang=a, out_lang=b, run=fn)


def test_single_step_run():
    ex = Chain(
        [_step("ab", "a", "b", lambda x: StepOutcome(output=x + 1, provenance={"hop": "ab"}))]
    ).run(10)
    assert ex.outputs == (11,)
    assert ex.final == 11
    assert ex.hops == ("ab",)
    assert ex.languages == ("a", "b")
    assert ex.provenance == ({"hop": "ab"},)


def test_two_steps_thread_output_and_provenance():
    s1 = _step("ab", "a", "b", lambda x: StepOutcome(output=x * 2, provenance={"hop": "ab", "n": x}))
    s2 = _step("bc", "b", "c", lambda x: StepOutcome(output=x + 1, provenance={"hop": "bc", "n": x}))
    ex = Chain([s1, s2]).run(5)
    assert ex.outputs == (10, 11)  # 5*2=10, then 10+1=11
    assert ex.final == 11
    assert ex.hops == ("ab", "bc")
    assert ex.languages == ("a", "b", "c")
    assert ex.provenance == ({"hop": "ab", "n": 5}, {"hop": "bc", "n": 10})


def test_connectivity_validation_rejects_gap():
    s1 = _step("ab", "a", "b", lambda x: StepOutcome(output=x))
    s2 = _step("cd", "c", "d", lambda x: StepOutcome(output=x))  # b != c
    with pytest.raises(ChainConnectivityError):
        Chain([s1, s2])


def test_empty_chain_rejected():
    with pytest.raises(ValueError):
        Chain([])


def test_chain_metadata_properties():
    c = Chain(
        [
            _step("ab", "a", "b", lambda x: StepOutcome(output=x)),
            _step("bc", "b", "c", lambda x: StepOutcome(output=x)),
        ]
    )
    assert c.hops == ("ab", "bc")
    assert c.in_lang == "a"
    assert c.out_lang == "c"
    assert c.languages == ("a", "b", "c")


def test_default_provenance_is_empty_dict():
    ex = Chain([_step("ab", "a", "b", lambda x: StepOutcome(output=x))]).run(1)
    assert ex.provenance == ({},)


def test_for_route_binds_from_graph():
    register_hop(
        CompileHop(identifier="ab", in_lang="a", out_lang="b", tier=Tier.transparent, compile=lambda *x: None)
    )
    register_hop(
        CompileHop(identifier="bc", in_lang="b", out_lang="c", tier=Tier.transparent, compile=lambda *x: None)
    )
    from gurdy.core.route import routes

    (route,) = routes("a", "c")
    runners = {
        "ab": lambda x: StepOutcome(output=x + "-ab"),
        "bc": lambda x: StepOutcome(output=x + "-bc"),
    }
    ex = Chain.for_route(route, runners).run("start")
    assert ex.hops == ("ab", "bc")
    assert ex.languages == ("a", "b", "c")
    assert ex.final == "start-ab-bc"
