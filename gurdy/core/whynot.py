"""``why_not`` — the answerability diagnosis as a first-class call
(POTENTIAL.md §1–2 lifted from prose into the interface).

A question ``(p, φ)`` is answerable iff five obstacles all pass, and when
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
   dynamic: it fires only when the caller hands in such a verdict);
5. **trust** — when the caller states an assurance ``floor`` (a grade or
   class), some feasible route meets it by declared grade, or an
   independent branch corroborates past it; otherwise the fifth obstacle
   fires with the trust advisor's generation target (an independent
   pair from a new artifact, or the demand to declare provenance).

The five obstacles are the platform's single demand taxonomy
(``ledger.OBSTACLES``): the obstacle that fails a question names what
the next pair pays for.

The diagnosis returns a machine-readable **demand record** naming the
generation target the failure calls for — a missing pair, a
wider-projection change to a named pair, a *native procedure* (a
charted shape's named family on a reachable hub, SYNTHESIS.md §3), a
missing reasoning language (the shape uncharted), or a *reduction*
(an abstraction / property-transformation endo-pair) — and,
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
            verdict: Any | None = None, floor: str | None = None,
            program: str | None = None,
            origin: str = "organic", suite: str | None = None,
            spent_reductions: list[str] | None = None,
            max_hops: int = 6) -> dict[str, Any]:
    """Diagnose why a question about a ``source``-language program is (or
    is not) answerable. Returns ``{"answerable": True, ...}`` or the first
    failing obstacle with its demand record — which, when the ledger is
    configured, is also **recorded** (the books' demand side,
    core/ledger.py): the question verbatim, the obstacle, the named
    target, the ``origin`` (an ``organic`` player session vs a synthetic
    ``campaign`` or ``scout``), and — when asked from a pinned benchmark
    — the ``suite`` tag (FRONTIER.md §1.1). ``program`` names the
    concrete instance the question is about, when there is one: the
    question is ``(p, φ)``, and a benchmark's questions carry their
    ``p``. ``spent_reductions`` is the player's report of registered
    reductions already **played and spent** on this very question (the
    take-up's books): the cost target excludes them from its dials,
    and once every registered dial is spent it **advances** — to the
    charted native procedure family when the atlas knows the shape (an
    unbounded engine behind a solver brief, SYNTHESIS.md §3 /
    SOLVERS.md §2.1), else to the demand for a *new* reduction
    (POTENTIAL.md §6). Otherwise read-only; always advisory."""
    from . import ledger as _ledger
    from .question import Question

    hubs = reasoning_languages()
    if not hubs:
        raise ValueError("no reasoning language is registered")

    question = Question(
        source=source,
        observables=tuple(observables) if observables is not None else None,
        shape=shape, floor=floor, program=program,
    ).asdict()

    def _demand(rec: dict[str, Any]) -> dict[str, Any]:
        _ledger.demand(question, rec["obstacle"], rec.get("generation_target"),
                       origin=origin, suite=suite)
        return rec

    # Obstacles 1–3, computed from the same annotated report the player
    # sees (core/route.py::route_report), per reasoning language.
    reports: dict[str, list[dict]] = {
        hub: _route.route_report(source, hub, max_hops=max_hops,
                                 observables=observables, shape=shape)
        for hub in hubs
    }
    all_routes = [(hub, e) for hub, entries in reports.items() for e in entries]

    # The zero-hop route: a question about a program already in a
    # reasoning language is decided there natively — no translation
    # debt (FRONTIER.md §5; HWMCC is the motivating case). Its contract
    # is the meet over zero hops, i.e. the unit: nothing translated,
    # nothing lost, nothing to distrust on the route axis (solver trust
    # is the separate certificate/checker story, SOLVERS.md §5–6).
    if source in hubs:
        all_routes.append((source, {
            "route": [],
            "native": True,
            "fidelity": "predicted",
            "assurance": "universal",
            "direction": "exact",
            "feasibility": {
                "observables": True,
                "shape": (True if shape is None else shape in hubs[source]),
            },
        }))

    if not all_routes:  # obstacle 1: connectivity
        into = [lid for lid in _hub_connected(max_hops) if lid != source]
        target = sorted(hubs)[0]  # canonical stub: the direct hub bridge
        return _demand({
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
        })

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
        return _demand({
            "answerable": False,
            "obstacle": "loss",
            "detail": {"head_pairs_dropping": drops},
            "generation_target": {
                "kind": "wider-projection",
                "pairs": sorted(drops),
                "missing_observables": sorted({o for m in drops.values() for o in m}),
            },
        })

    # obstacle 3: shape — among loss survivors, some terminal must decide
    # φ's shape (an undeclared inventory survives as unknown). The atlas
    # draws the target line (SYNTHESIS.md §3): a *charted* shape demands
    # the named procedure family on a hub the program already reaches —
    # the instantiation case — while an *uncharted* one honestly demands
    # a reasoning language nobody has designed.
    shape_survivors = [(hub, e) for hub, e in loss_survivors
                       if _feas(e, "shape") is not False]
    if shape is not None and not shape_survivors:
        from .atlas import locate as atlas_locate

        loc = atlas_locate(shape)
        reachable = sorted({hub for hub, _e in loss_survivors})
        if loc.get("status") != "uncharted":
            note = ("a charted shape: instantiate the named procedure "
                    "family behind a solver brief and the admission gate "
                    "(SYNTHESIS.md §4–5)")
            if loc.get("crossing"):
                note += (" — or discharge it first by the known "
                         "crossing: " + loc["crossing"])
            target = {
                "kind": "native-procedure",
                "shape": shape,
                "family": loc.get("native"),
                "attach_to_any_of": reachable or sorted(hubs),
                "note": note,
            }
        else:
            target = {
                "kind": "reasoning-language",
                "shape": shape,
                "note": "an uncharted shape: a reasoning language deciding "
                        "it, plus the bridge into it (depth growth, "
                        "POTENTIAL.md §3) — locate it in the atlas by "
                        "review before designing anything",
            }
        return _demand({
            "answerable": False,
            "obstacle": "shape",
            "detail": {"shape": shape,
                       "declared_shapes": {h: list(s) for h, s in hubs.items()},
                       "atlas": loc},
            "generation_target": target,
        })

    # obstacle 4: cost — only a real verdict can fire it.
    vname = getattr(verdict, "value", verdict)
    if vname in ("unknown", "resource-out"):
        question["verdict"] = vname
        from . import ledger

        terminals = sorted({hub for hub, _e in shape_survivors})
        reductions = sorted(
            pid for pid, pair in registry.list_pairs().items()
            if pair.source == pair.target and pair.source in terminals)
        spent = sorted(set(spent_reductions or ()) & set(reductions))
        remaining = [p for p in reductions if p not in spent]
        detail = {
            "verdict": vname,
            "measured_decide": {
                hub: ledger.profiles_by("engine", "decide", language=hub)
                for hub in terminals},
            **({"spent_reductions": spent} if spent else {}),
        }
        if remaining or not spent:
            return _demand({
                "answerable": False,
                "obstacle": "cost",
                "detail": detail,
                "generation_target": {
                    "kind": "reduction",
                    "on_any_of": terminals,
                    "registered_reductions": remaining,
                    **({"spent_reductions": spent} if spent else {}),
                    "note": "an abstraction (direction: over) or property "
                            "transformation on the hub — registered "
                            "reductions are player-parameterized dials to "
                            "try first; a refinement demand names a new one "
                            "(POTENTIAL.md §6)",
                },
            })
        # Every registered dial has been played and spent on this very
        # question: the target advances past the reductions. A charted
        # shape names its native procedure family — an unbounded engine
        # is instantiation behind a solver brief (SYNTHESIS.md §3,
        # SOLVERS.md §2.1) — while an uncharted (or unstated) shape can
        # only demand a reduction nobody has designed yet.
        from .atlas import locate as atlas_locate

        loc = atlas_locate(shape) if shape is not None else None
        if loc is not None and loc.get("status") != "uncharted":
            target = {
                "kind": "native-procedure",
                "shape": shape,
                "family": loc.get("native"),
                "attach_to_any_of": terminals,
                "spent_reductions": spent,
                "note": "every registered reduction on the reachable hubs "
                        "was played and spent on this question — the cost "
                        "demand advances to the charted procedure family: "
                        "an unbounded engine behind a solver brief "
                        "(SOLVERS.md §2.1), admission-gated "
                        "(SYNTHESIS.md §4-5)",
            }
        else:
            target = {
                "kind": "reduction",
                "on_any_of": terminals,
                "registered_reductions": [],
                "spent_reductions": spent,
                "note": "every registered reduction was played and spent, "
                        "and the shape names no charted procedure family — "
                        "the demand is a NEW reduction (a property "
                        "transformation, POTENTIAL.md §6)",
            }
        return _demand({
            "answerable": False,
            "obstacle": "cost",
            "detail": detail,
            "generation_target": target,
        })

    # obstacle 5: trust — only a stated assurance floor can fire it.
    if floor is not None:
        from . import trust as _trust

        rank = _trust._floor_rank(floor)
        met = [e for _hub, e in shape_survivors
               if _route._CLASS_RANK.get(e["assurance"], 0) >= rank]
        if met:
            return {"answerable": True,
                    "routes": [e for _hub, e in shape_survivors],
                    "met_by": [" -> ".join(e["route"]) for e in met]}
        hubs_with = sorted({hub for hub, _e in shape_survivors})
        options = {h: _trust.trust_options(source, h, floor=floor,
                                           max_hops=max_hops)
                   for h in hubs_with}
        corroborated = {h: r["corroboration"] for h, r in options.items()
                        if "corroboration" in r}
        if corroborated:
            return {"answerable": True,
                    "routes": [e for _hub, e in shape_survivors],
                    "met_by": [],
                    "corroboration": corroborated}
        first = next((h for h in hubs_with
                      if options[h].get("generation_target")), None)
        return _demand({
            "answerable": False,
            "obstacle": "trust",
            "detail": {h: {"anchors": r["anchors"],
                           "branches": len(r["branches"])}
                       for h, r in options.items()},
            "generation_target": (options[first]["generation_target"]
                                  if first else None),
        })

    return {
        "answerable": True,
        "routes": [e for _hub, e in shape_survivors],
    }
