"""Tests for the Hop genus / Tier ranking (gurdy.core.hop)."""

from __future__ import annotations

from gurdy.core.hop import Tier


def test_tier_trust_rank_ordering():
    # transparent (auditable) > checked (validated) > reproducible
    # (deterministic only) > trusted (faith). See DESIGN_pair_taxonomy.md §8.
    assert (
        Tier.transparent.trust_rank
        > Tier.checked.trust_rank
        > Tier.reproducible.trust_rank
        > Tier.trusted.trust_rank
    )


def test_tier_determinism():
    assert Tier.transparent.is_deterministic
    assert Tier.reproducible.is_deterministic
    assert Tier.checked.is_deterministic
    assert not Tier.trusted.is_deterministic
