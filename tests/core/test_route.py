"""Tests for route enumeration over the hop graph (gurdy.core.route)."""

from __future__ import annotations

import pytest

from gurdy.core.hop import (
    CompileHop,
    Tier,
    _clear_registry_for_tests,
    register_hop,
)
from gurdy.core.route import routes


@pytest.fixture(autouse=True)
def _clean():
    _clear_registry_for_tests()
    yield
    _clear_registry_for_tests()


def _hop(ident: str, a: str, b: str, tier: Tier = Tier.transparent) -> CompileHop:
    return CompileHop(
        identifier=ident, in_lang=a, out_lang=b, tier=tier, compile=lambda *x: None
    )


def test_no_route_on_empty_graph():
    assert routes("a", "b") == ()


def test_single_hop_route():
    register_hop(_hop("ab", "a", "b"))
    (r,) = routes("a", "b")
    assert r.hops == ("ab",)
    assert r.languages == ("a", "b")
    assert r.in_lang == "a"
    assert r.out_lang == "b"
    assert r.length == 1


def test_two_hop_chain_threads_languages_and_tiers():
    register_hop(_hop("ab", "a", "b", Tier.reproducible))
    register_hop(_hop("bc", "b", "c", Tier.transparent))
    (r,) = routes("a", "c")
    assert r.hops == ("ab", "bc")
    assert r.languages == ("a", "b", "c")
    assert r.tiers == (Tier.reproducible, Tier.transparent)


def test_multiple_routes_shortest_first():
    register_hop(_hop("ac", "a", "c"))  # direct (1 hop)
    register_hop(_hop("ab", "a", "b"))
    register_hop(_hop("bc", "b", "c"))  # via b (2 hops)
    assert [r.hops for r in routes("a", "c")] == [("ac",), ("ab", "bc")]


def test_parallel_edges_both_enumerated_sorted_by_id():
    register_hop(_hop("ab2", "a", "b"))
    register_hop(_hop("ab1", "a", "b"))
    assert [r.hops for r in routes("a", "b")] == [("ab1",), ("ab2",)]


def test_cycle_does_not_blow_up():
    register_hop(_hop("ab", "a", "b"))
    register_hop(_hop("ba", "b", "a"))  # a <-> b cycle
    register_hop(_hop("bc", "b", "c"))
    assert [r.hops for r in routes("a", "c")] == [("ab", "bc")]


def test_same_in_and_out_has_no_zero_hop_route():
    register_hop(_hop("ab", "a", "b"))
    register_hop(_hop("ba", "b", "a"))
    assert routes("a", "a") == ()


def test_max_hops_backstop():
    register_hop(_hop("ab", "a", "b"))
    register_hop(_hop("bc", "b", "c"))
    register_hop(_hop("cd", "c", "d"))
    assert routes("a", "d", max_hops=2) == ()  # needs 3 hops
    assert [r.hops for r in routes("a", "d", max_hops=3)] == [("ab", "bc", "cd")]


def test_real_chain_graph():
    """The registered c-riscv hop + riscv-btor2 pair form the canonical chain."""
    from gurdy.core.hop import register_hop as _rh
    from gurdy.core.pair import register_pair
    from gurdy.hops.c_riscv import C_RISCV
    from gurdy.pairs.riscv_btor2 import PAIR

    register_pair(PAIR)  # idempotent re-register after the autouse clear
    _rh(C_RISCV)

    assert [r.hops for r in routes("c", "btor2")] == [("c-riscv", "riscv-btor2")]
    assert [r.hops for r in routes("rv64-elf", "btor2")] == [("riscv-btor2",)]
    assert routes("btor2", "c") == ()

    (chain,) = routes("c", "btor2")
    assert chain.languages == ("c", "rv64-elf", "btor2")
    assert chain.tiers == (Tier.reproducible, Tier.transparent)
    assert chain.trust == Tier.reproducible  # weakest hop (c-riscv)
    assert chain.is_deterministic is True
    assert chain.predictable_prefix == 0  # the first hop (c-riscv) is opaque


def test_route_trust_is_weakest_hop():
    register_hop(_hop("ab", "a", "b", Tier.transparent))
    register_hop(_hop("bc", "b", "c", Tier.reproducible))
    (r,) = routes("a", "c")
    assert r.trust == Tier.reproducible
    assert r.is_deterministic is True
    assert r.predictable_prefix == 1  # 'ab' transparent, then opaque


def test_route_trusted_hop_breaks_determinism():
    register_hop(_hop("ab", "a", "b", Tier.transparent))
    register_hop(_hop("bc", "b", "c", Tier.trusted))
    (r,) = routes("a", "c")
    assert r.is_deterministic is False
    assert r.trust == Tier.trusted
