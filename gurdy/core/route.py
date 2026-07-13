"""Route enumeration + the generic route runner (FRAMEWORK.md §2; ROUTES.md).

Treats the registry as a graph (nodes = languages, edges = pairs) and
enumerates the simple-path routes between two languages — it *enumerates*; the
player *chooses* (ROUTES.md §6). ``run_route`` composes a route's translators,
wrapping each hop's input via the next pair's ``compose_input`` and threading
per-hop provenance. Deterministic: a route is deterministic iff every pair is
(ROUTES.md §2).
"""

from __future__ import annotations

from typing import Any

from . import cache, direction as _direction, registry


def _graph() -> dict[str, list[tuple[str, str]]]:
    g: dict[str, list[tuple[str, str]]] = {}
    for pid, pair in registry.list_pairs().items():
        g.setdefault(pair.source, []).append((pid, pair.target))
    for lang in g:
        g[lang].sort()  # deterministic enumeration order
    return g


def routes(src: str, dst: str, max_hops: int = 6, *,
           endo: bool = False) -> list[list[str]]:
    """Every simple-path route (list of pair ids) from language ``src`` to
    ``dst`` through the registered pairs.

    With ``endo=True`` the walk may also take **endo-pairs** (source language
    == target language, e.g. an abstraction hop like ``btor2-havoc``), each
    pair at most once per route; languages are still never revisited through a
    non-endo edge. Off by default: an endo-hop is a player-directed reduction
    (its parameters — which states to havoc — are the player's call), so plain
    enumeration stays the simple-path reading of ROUTES.md §6.
    """
    g = _graph()
    found: list[list[str]] = []

    def dfs(lang: str, path: list[str], seen: frozenset[str]) -> None:
        if path and lang == dst:
            found.append(list(path))
            return
        if len(path) >= max_hops:
            return
        for pid, tgt in g.get(lang, []):
            if pid in path:
                continue
            if tgt in seen and not (endo and tgt == lang):
                continue
            dfs(tgt, path + [pid], seen | {tgt})

    dfs(src, [], frozenset({src}))
    found.sort()
    return found


def run_route(route: list[str], head_program: Any,
              params: dict[str, dict] | None = None) -> dict[str, Any]:
    """Run a route end to end, composing translators.

    ``head_program`` is the first pair's input; ``params[pair_id]`` carries
    per-hop parameters (e.g. the bridge's bound ``k``) consumed by that pair's
    ``compose_input``. Returns the terminal artifact, the route, and per-hop
    provenance.
    """
    params = params or {}
    artifact: Any = None
    provenance: list[dict[str, Any]] = []
    for i, pid in enumerate(route):
        pair = registry.get_pair(pid)
        if i == 0:
            program = head_program
        elif pair.compose_input is not None:
            program = pair.compose_input(artifact, params.get(pid, {}))
        else:
            program = artifact
        artifact = cache.compile(pair, program)
        provenance.append({
            "pair": pid,
            "translator_version": pair.translator_version,
            "fidelity": pair.fidelity,
            "direction": pair.direction,
        })
    return {
        "artifact": artifact,
        "route": list(route),
        "provenance": provenance,
        "direction": route_direction(route),
    }


def route_direction(route: list[str]) -> str:
    """The composed square direction of a route: ``exact`` iff every hop's
    square is exact, else ``over`` (ROUTES.md §3; core/direction.py). Governs
    which verdicts transfer from the destination back to the source."""
    return _direction.compose(*(registry.get_pair(pid).direction for pid in route))
