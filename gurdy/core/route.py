"""Route enumeration over the registered-hop graph.

This module *enumerates*; it does not *choose*. Picking among routes (by
trust x latency x lossiness) is the LLM's job, keeping "no reasoning in
core" intact. Routes come back deterministically: shortest first, then by
hop ids.
"""

from __future__ import annotations

from dataclasses import dataclass

from gurdy.core.hop import Hop, Tier, all_hops, weakest_tier

DEFAULT_MAX_HOPS = 8


@dataclass(frozen=True)
class Route:
    """One candidate chain: an ordered sequence of hops."""

    hops: tuple[str, ...]
    languages: tuple[str, ...]
    tiers: tuple[Tier, ...]

    @property
    def in_lang(self) -> str:
        return self.languages[0]

    @property
    def out_lang(self) -> str:
        return self.languages[-1]

    @property
    def length(self) -> int:
        return len(self.hops)

    @property
    def trust(self) -> Tier:
        """The chain's declared trust: its weakest hop (the static meet)."""
        return weakest_tier(self.tiers)

    def __str__(self) -> str:
        body = " -> ".join(self.languages)
        return f"{body}  [{', '.join(self.hops)}]  trust={self.trust.label}"


def _edges() -> dict[str, list[Hop]]:
    out: dict[str, list[Hop]] = {}
    for h in all_hops():
        out.setdefault(h.in_lang, []).append(h)
    return out


def routes(in_lang: str, out_lang: str, *, max_hops: int = DEFAULT_MAX_HOPS) -> list[Route]:
    """All simple-path routes from ``in_lang`` to ``out_lang``."""
    edges = _edges()
    found: list[Route] = []

    def walk(node: str, hops: list[Hop], visited: set[str]) -> None:
        if node == out_lang and hops:
            found.append(
                Route(
                    hops=tuple(h.id for h in hops),
                    languages=(in_lang, *(h.out_lang for h in hops)),
                    tiers=tuple(h.declared_tier for h in hops),
                )
            )
            return
        if len(hops) >= max_hops:
            return
        for h in sorted(edges.get(node, []), key=lambda e: e.id):
            if h.out_lang in visited:
                continue
            walk(h.out_lang, [*hops, h], visited | {h.out_lang})

    walk(in_lang, [], {in_lang})
    found.sort(key=lambda r: (r.length, r.hops))
    return found
