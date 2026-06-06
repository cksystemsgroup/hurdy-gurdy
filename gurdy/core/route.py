"""Route enumeration over the registered-hop graph.

The registered hops (:mod:`gurdy.core.hop`) form a directed multigraph: nodes
are languages, edges are hops (``in_lang -> out_lang``). :func:`routes`
enumerates the simple-path routes from one language to another — the candidate
chains a caller may run.

This module *enumerates*; it does not *choose*. Picking among routes (by trust
× latency × lossiness) is a judgement left to the caller / LLM, keeping "no
reasoning in core" intact (``DESIGN_generalized_pairs.md`` §11.2). Routes come
back in a deterministic order: shortest first, then by hop identifiers. Per-hop
``tiers`` are reported as raw data; computing a single chain-trust verdict (the
meet, with verifier-hop re-establishment) is Stage 4.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from gurdy.core.hop import Hop, Tier, all_hops

DEFAULT_MAX_HOPS = 8


@dataclass(frozen=True)
class Route:
    """One candidate chain: an ordered sequence of hops from ``in_lang`` to
    ``out_lang``.

    ``languages`` lists every language visited, in order (length
    ``len(hops) + 1``); ``tiers`` is the per-hop trust tier, aligned with
    ``hops``.
    """

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


def routes(
    in_lang: str, out_lang: str, *, max_hops: int = DEFAULT_MAX_HOPS
) -> tuple[Route, ...]:
    """Enumerate simple-path routes ``in_lang -> out_lang`` over the registered
    hops.

    Returns an empty tuple if no route exists (including the degenerate
    ``in_lang == out_lang``, for which there is no zero-hop route). Only simple
    paths are enumerated — no language is visited twice — so cycles cannot blow
    up the search; ``max_hops`` bounds the depth as a backstop.
    """
    by_in: dict[str, list[Hop]] = defaultdict(list)
    for hop in all_hops():
        by_in[hop.in_lang].append(hop)
    for edges in by_in.values():
        edges.sort(key=lambda h: h.identifier)

    found: list[Route] = []

    def walk(current: str, visited: frozenset[str], path: list[Hop]) -> None:
        if path and current == out_lang:
            found.append(
                Route(
                    hops=tuple(h.identifier for h in path),
                    languages=(in_lang,) + tuple(h.out_lang for h in path),
                    tiers=tuple(h.tier for h in path),
                )
            )
            return  # a route ends at its destination; do not extend past it
        if len(path) >= max_hops:
            return
        for hop in by_in.get(current, ()):
            if hop.out_lang in visited:
                continue
            walk(hop.out_lang, visited | {hop.out_lang}, path + [hop])

    walk(in_lang, frozenset({in_lang}), [])
    found.sort(key=lambda r: (r.length, r.hops))
    return tuple(found)


__all__ = ["Route", "routes", "DEFAULT_MAX_HOPS"]
