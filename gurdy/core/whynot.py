"""``why_not`` — the answerability diagnosis as a first-class call
(POTENTIAL.md §1–2 lifted from prose into the interface).

A question ``(p, φ)`` is answerable iff four obstacles all pass, and when
it is not, exactly one of them fails *first* — in this order:

1. **connectivity** — a route exists from the source language to some
   reasoning language (one that declares ``question_shapes``);
2. **loss** — some such route keeps the observables φ reads (checked
   against the head projection, as in the route report; a dynamic
   per-system projection is *unknown*, which survives — never a silent
   pass, never a false indictment);
3. **shape** — some loss-surviving route ends at a reasoning language
   whose declared solver shapes include φ's;
4. **cost** — a solver actually returned a verdict other than
   ``unknown`` / ``resource-out`` within the player's budget (this one is
   dynamic: it fires only when the caller hands in such a verdict).

The diagnosis returns a machine-readable **demand record** naming the
generation target the failure calls for — a missing pair, a
wider-projection change to a named pair, a missing reasoning language, or
a *reduction* (an abstraction / property-transformation endo-pair) — and,
for pair-shaped targets, a draft **brief stub** with the AGENTS.md §1
fields pre-named. The stub is a work-queue convenience, nothing more:
**registration is a human act** (AGENTS.md §1), and this module is
read-only — it diagnoses and names; it never registers, never chooses.
"""

from __future__ import annotations

from typing import Any

from . import registry, route as _route


def reasoning_languages() -> dict[str, tuple[str, ...]]:
    """The registered reasoning languages and their declared question
    shapes (SOLVERS.md §9, via the registry's ``question_shapes``)."""
    return {lid: lang.question_shapes
            for lid, lang in sorted(registry.list_languages().items())
            if getattr(lang, "question_shapes", ())}


def _hub_connected(max_hops: int) -> list[str]:
    """Languages from which some reasoning language is reachable — the
    candidate targets for a connectivity-restoring edge."""
    hubs = set(reasoning_languages())
    out = set(hubs)
    for lid in registry.list_languages():
        if lid in out:
            continue
        if any(_route.routes(lid, hub, max_hops=max_hops) for hub in hubs):
            out.add(lid)
    return sorted(out)


def brief_stub(source: str, target: str, observables: list[str] | None,
               shape: str | None) -> str:
    """A draft registration brief for a demanded pair, fields per
    AGENTS.md §1. A stub, not a registration: the human decides."""
    obs = ", ".join(f"`{o}`" for o in (observables or [])) or "TODO"
    return "\n".join([
        f"# Pair — `{source}-{target}`  ·  {source} → {target}  (DRAFT STUB)",
        "",
        "*Demand record from `why_not` — **registration is a human act**",
        "(AGENTS.md §1); this stub only names what the diagnosis knows.*",
        "",
        "- **Source / target languages.** "
        f"`{source}` → `{target}` (both must be in `languages/` or be "
        "introduced by this pair).",
        "- **Intended translator.** TODO (spec-derived / pinned tool / "
        "rule-for-rule mapping).",
        "- **Fidelity target + evidence.** TODO (PAIRING.md §4; not "
        "inflated).",
        f"- **Projection `π`.** Must keep at least: {obs}.",
        "- **Direction.** TODO (`exact` default; `over` ships its witness "
        "embedding — ARCHITECTURE.md §3).",
        "- **Coverage target.** TODO (construct inventory + public suite, "
        "BENCHMARKS.md).",
        "- **Reuses / contributes.** TODO (shared interpreters; reuse-first)."
        + (f"\n- **Question shape driving this demand.** `{shape}`."
           if shape else ""),
    ])


def why_not(source: str, observables: list[str] | None = None,
            shape: str | None = None, *,
            verdict: Any | None = None,
            max_hops: int = 6) -> dict[str, Any]:
    """Diagnose why a question about a ``source``-language program is (or
    is not) answerable. Returns ``{"answerable": True, ...}`` or the first
    failing obstacle with its demand record. Read-only and advisory."""
    hubs = reasoning_languages()
    if not hubs:
        raise ValueError("no reasoning language is registered")

    # Obstacles 1–3, computed from the same annotated report the player
    # sees (core/route.py::route_report), per reasoning language.
    reports: dict[str, list[dict]] = {
        hub: _route.route_report(source, hub, max_hops=max_hops,
                                 observables=observables, shape=shape)
        for hub in hubs
    }
    all_routes = [(hub, e) for hub, entries in reports.items() for e in entries]

    if not all_routes:  # obstacle 1: connectivity
        into = [lid for lid in _hub_connected(max_hops) if lid != source]
        target = sorted(hubs)[0]  # canonical stub: the direct hub bridge
        return {
            "answerable": False,
            "obstacle": "connectivity",
            "detail": {"reasoning_languages": {h: list(s) for h, s in hubs.items()},
                       "hub_connected": into},
            "generation_target": {
                "kind": "pair",
                "from": source,
                "into_any_of": into or sorted(hubs),
            },
            "brief_stub": brief_stub(source, target, observables, shape),
        }

    def _feas(e: dict, key: str) -> Any:
        return e.get("feasibility", {}).get(key, True)

    # obstacle 2: loss — a route survives unless its head projection
    # *definitely* drops an asked observable ("dynamic" survives as unknown).
    loss_survivors = [(hub, e) for hub, e in all_routes
                      if _feas(e, "observables") is not False]
    if observables is not None and not loss_survivors:
        drops: dict[str, list[str]] = {}
        for _hub, e in all_routes:
            head = e["route"][0]
            missing = e.get("feasibility", {}).get("observables_missing", [])
            if missing:
                drops[head] = sorted(set(drops.get(head, [])) | set(missing))
        return {
            "answerable": False,
            "obstacle": "loss",
            "detail": {"head_pairs_dropping": drops},
            "generation_target": {
                "kind": "wider-projection",
                "pairs": sorted(drops),
                "missing_observables": sorted({o for m in drops.values() for o in m}),
            },
        }

    # obstacle 3: shape — among loss survivors, some terminal must decide
    # φ's shape (an undeclared inventory survives as unknown).
    shape_survivors = [(hub, e) for hub, e in loss_survivors
                       if _feas(e, "shape") is not False]
    if shape is not None and not shape_survivors:
        return {
            "answerable": False,
            "obstacle": "shape",
            "detail": {"shape": shape,
                       "declared_shapes": {h: list(s) for h, s in hubs.items()}},
            "generation_target": {
                "kind": "reasoning-language",
                "shape": shape,
                "note": "a reasoning language deciding this shape, plus the "
                        "bridge into it (depth growth, POTENTIAL.md §3) — or "
                        "a property transformation reducing the shape to a "
                        "declared one (e.g. liveness-to-safety on a hub)",
            },
        }

    # obstacle 4: cost — only a real verdict can fire it.
    vname = getattr(verdict, "value", verdict)
    if vname in ("unknown", "resource-out"):
        from . import costs

        terminals = sorted({hub for hub, _e in shape_survivors})
        reductions = sorted(
            pid for pid, pair in registry.list_pairs().items()
            if pair.source == pair.target and pair.source in terminals)
        return {
            "answerable": False,
            "obstacle": "cost",
            "detail": {
                "verdict": vname,
                "measured_decide": {
                    hub: costs.profiles_by("engine", "decide", language=hub)
                    for hub in terminals},
            },
            "generation_target": {
                "kind": "reduction",
                "on_any_of": terminals,
                "registered_reductions": reductions,
                "note": "an abstraction (direction: over) or property "
                        "transformation on the hub — registered reductions "
                        "are player-parameterized dials to try first; a "
                        "refinement demand names a new one (POTENTIAL.md §6)",
            },
        }

    return {
        "answerable": True,
        "routes": [e for _hub, e in shape_survivors],
    }
