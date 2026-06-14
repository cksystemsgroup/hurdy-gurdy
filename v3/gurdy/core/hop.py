"""Hops (= pairs) and trust tiers.

A *hop* is one edge of the language graph: ``in_lang -> out_lang``. Three
kinds: ``compile`` (input->representation), ``reasoning``
(representation->reasoning), ``bridge`` (reasoning->reasoning).

Trust tiers form the assurance order ``transparent > checked > reproducible
> trusted``; a chain's trust is the *meet* (weakest hop).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

HOP_KINDS = ("compile", "reasoning", "bridge")


class Tier(IntEnum):
    """Assurance ranking. Higher is stronger; compose by ``min`` (the meet)."""

    trusted = 0       # taken on faith; quarantine, admit only behind a verifier
    reproducible = 1  # byte-deterministic, but not semantically validated
    checked = 2       # validated every run (a differential/cross-check establishes it)
    transparent = 3   # schema-auditable; correctness inspectable from the deterministic schema

    @property
    def label(self) -> str:
        return self.name


def weakest_tier(tiers: tuple[Tier, ...]) -> Tier:
    """The meet: a chain's trust is its weakest hop."""
    return min(tiers) if tiers else Tier.trusted


@dataclass(frozen=True)
class Hop:
    """A registered edge. ``declared_tier`` is the static (pre-runtime) tier;
    a verifier hop may lift the *effective* tier at run time."""

    id: str
    kind: str
    in_lang: str
    out_lang: str
    declared_tier: Tier

    def __post_init__(self) -> None:
        if self.kind not in HOP_KINDS:
            raise ValueError(f"kind must be one of {HOP_KINDS}, got {self.kind!r}")


# The registered-hop graph (populated by the hop modules at import time).
_HOPS: dict[str, Hop] = {}


def register(hop: Hop) -> Hop:
    if hop.id in _HOPS:
        raise ValueError(f"hop {hop.id!r} already registered")
    _HOPS[hop.id] = hop
    return hop


def all_hops() -> tuple[Hop, ...]:
    return tuple(_HOPS.values())


def get(hop_id: str) -> Hop | None:
    return _HOPS.get(hop_id)
