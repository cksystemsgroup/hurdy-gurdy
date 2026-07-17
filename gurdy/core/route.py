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


# Grade -> assurance class (ROUTES.md §3; the paper's Prop. 4.2): weakest
# link composes on the class chain universal > per-run > replay > none.
GRADE_CLASS = {
    "proved": "universal",
    "predicted": "universal",
    "checked": "per-run",
    "reproducible": "replay",
    "trusted": "none",
}
_CLASS_RANK = {"universal": 3, "per-run": 2, "replay": 1, "none": 0}
_DIRECTION_RANK = {"exact": 1, "over": 0}


def route_fidelity(route: list[str]) -> dict[str, str]:
    """Weakest-link composition of a route's declared grades: the hop whose
    assurance class ranks lowest names the route's grade and class."""
    weakest_pid = min(
        route,
        key=lambda pid: _CLASS_RANK.get(
            GRADE_CLASS.get(registry.get_pair(pid).fidelity, "none"), 0),
    )
    grade = registry.get_pair(weakest_pid).fidelity
    return {"fidelity": grade,
            "assurance": GRADE_CLASS.get(grade, "none"),
            "weakest_hop": weakest_pid}


def _feasibility(route: list[str], dst: str, observables, shape) -> dict:
    checks: dict[str, object] = {}
    if observables is not None:
        head = registry.get_pair(route[0])
        fields = tuple(head.projection.fields)
        if not fields:
            # e.g. a dynamic per-system projection (projection_for): the
            # static report cannot decide it — unknown, never a silent pass.
            checks["observables"] = "dynamic"
        else:
            missing = sorted(set(observables) - set(fields))
            checks["observables"] = True if not missing else False
            if missing:
                checks["observables_missing"] = missing
    if shape is not None:
        shapes = getattr(registry.get_language(dst), "question_shapes", ())
        checks["shape"] = (shape in shapes) if shapes else "undeclared"
    verdicts = [v for k, v in checks.items()
                if k in ("observables", "shape")]
    if any(v is False for v in verdicts):
        checks["feasible"] = False
    elif verdicts and all(v is True for v in verdicts):
        checks["feasible"] = True
    else:
        checks["feasible"] = None  # unknown — dynamic/undeclared parts
    return checks


def _route_cost(route: list[str], dst: str) -> dict:
    from . import ledger

    translate = {pid: ledger.profile("translate", pair=pid) for pid in route}
    medians = [p["wall_median_s"] for p in translate.values() if p]
    total = round(sum(medians), 6) if len(medians) == len(route) else None
    return {
        "translate": translate,
        "translate_total_median_s": total,
        "decide": ledger.profiles_by("engine", "decide", language=dst),
        "measured": total is not None,
    }


def route_report(src: str, dst: str, *, max_hops: int = 6, endo: bool = False,
                 observables: list[str] | None = None,
                 shape: str | None = None) -> list[dict]:
    """The enumerated routes from ``src`` to ``dst``, each annotated with the
    four tradeoff axes: composed fidelity/assurance (weakest link), composed
    direction, question feasibility (when ``observables`` and/or ``shape``
    are given), and the measured cost profile from the host-local ledger
    (core/ledger.py; ``"measured": False`` and ``None`` totals are the honest
    unmeasured default).

    Routes that are Pareto-dominated — another route at least as good on
    assurance class and direction, no more expensive on the measured
    translate total, and strictly better somewhere — are **marked**
    (``dominated_by``), never hidden; dominance is only ever computed
    between fully measured routes, so partial cost data never dis-ranks a
    route. No scalar ranking is produced: the platform enumerates and
    annotates; the player chooses (ROUTES.md §6)."""
    report: list[dict] = []
    for r in routes(src, dst, max_hops=max_hops, endo=endo):
        entry: dict = {
            "route": r,
            "hops": len(r),
            "direction": route_direction(r),
            **route_fidelity(r),
            "cost": _route_cost(r, dst),
            "dominated_by": [],
        }
        if observables is not None or shape is not None:
            entry["feasibility"] = _feasibility(r, dst, observables, shape)
        report.append(entry)

    def _axes(e: dict) -> tuple[int, int, float | None]:
        return (_CLASS_RANK.get(e["assurance"], 0),
                _DIRECTION_RANK.get(e["direction"], 0),
                e["cost"]["translate_total_median_s"])

    for e in report:
        ec, ed, ecost = _axes(e)
        for other in report:
            if other is e:
                continue
            oc, od, ocost = _axes(other)
            if ecost is None or ocost is None:
                continue  # dominance needs complete measurement
            if (oc >= ec and od >= ed and ocost <= ecost
                    and (oc > ec or od > ed or ocost < ecost)):
                e["dominated_by"].append(" -> ".join(other["route"]))
    return report
