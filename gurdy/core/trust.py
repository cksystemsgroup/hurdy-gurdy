"""Trust advisor — independence and anchor accounting for branches
(ROUTES.md §4; SCALING.md §9/§11; the trust loop's guide).

Branch corroboration is only as strong as the **independence of the
semantic artifacts behind the diverse legs**: two routes that share the
artifact their translators derive from corroborate less than their count
suggests, and pairs can be generated without bound while independent
formalizations of a real semantics exist in small finite supply — trust
saturates at the anchors (POTENTIAL.md §5). This module makes that
arithmetic explicit and advisory:

* ``independence(route_a, route_b)`` — the shared suffix/prefix is
  removed (agreement corroborates the *diverse* segments only), then the
  diverse segments' declared ``semantic_artifact``s are compared: a
  shared artifact means **not independent** regardless of anything else;
  an undeclared pair means **unknown** (``None``) — never silently
  independent.
* ``trust_options(source, dst, floor=...)`` — which routes meet the
  player's assurance floor, which branch pairs genuinely corroborate,
  the anchor census, and — when the floor is unmet — the honest option
  set: run an existing independent branch, generate a route derived from
  a *new* artifact, or **saturation**: every further route would share
  the registered anchors, and more spending buys no trust. A pure view;
  ``why_not`` owns the demand recording (the fifth obstacle).

**Two instruments, one failure** (PROVING.md §3). When the floor is
unmet and no independent branch corroborates past it, the advisor names
*both* honest instruments and chooses neither: ``independent-pair`` —
a second route from an artifact outside the registered anchors — and
``certify-pair`` — upgrade the route's sub-floor hops to ``proved`` by
one of the two admissible certificate species (§5). They are returned
together in ``generation_targets`` (``generation_target`` remains the
first, unchanged), and ``why_not`` books one demand record per named
target, so the two stand on the books against each other. They are
priced side by side in ``pricing``, which is a *view* field and never
part of a target's signature: the anchor census says whether a
genuinely independent second route even exists to build, the
host-local ledger says what the existing front-end measured. Both
prices may be honestly unknown; neither is a ranking. The
``declare-provenance`` case is untouched — there independence is
*unknown*, not absent, and the cheap instrument is to declare it.

Read-only and advisory throughout: grades are declared and protected;
corroboration is evidence the player runs, not a grade this module
awards; nothing here chooses.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from . import registry
from . import route as _route

#: The two admissible certificate species (PROVING.md §5), each with its
#: own gate: **translation-validation** — per-run, the translator stays
#: untrusted, a pinned *independent* checker validates each translation,
#: negative controls mandatory (SCALING.md §9's I19 discipline); and
#: **refinement-proof** — once-and-for-all, gated like
#: ``paper/mechanization/`` (pinned toolchain, zero ``sorry``s, axiom
#: audit) and feasible only where a mechanized semantics already exists.
#: Which species a *given* pair admits is the brief's to state — the
#: registry declares no mechanization flag, and registration is a human
#: act (AGENTS.md §1). The advisor names both and chooses neither.
CERTIFY_SPECIES = ("translation-validation", "refinement-proof")


def _key(route: list[str]) -> str:
    return " -> ".join(route)


def route_anchors(route: list[str]) -> dict[str, str | None]:
    """Per hop, the declared semantic artifact (None = undeclared)."""
    return {pid: getattr(registry.get_pair(pid), "semantic_artifact", None)
            for pid in route}


def _independence(anchors_a: dict[str, str | None],
                  anchors_b: dict[str, str | None]) -> dict[str, Any]:
    """Pure core of the independence judgment, over the *diverse* segments'
    per-pair artifact declarations (shared hops already removed)."""
    decl_a = {v for v in anchors_a.values() if v is not None}
    decl_b = {v for v in anchors_b.values() if v is not None}
    undeclared = sorted([p for p, v in anchors_a.items() if v is None]
                        + [p for p, v in anchors_b.items() if v is None])
    shared = sorted(decl_a & decl_b)
    if shared:
        independent: bool | None = False
    elif undeclared:
        independent = None  # unknown is unknown — never silently independent
    else:
        independent = bool(decl_a and decl_b)
    return {"independent": independent,
            "shared_anchors": shared,
            "undeclared_pairs": undeclared,
            "anchors_a": sorted(decl_a),
            "anchors_b": sorted(decl_b)}


def independence(route_a: list[str], route_b: list[str]) -> dict[str, Any]:
    """The independence record for one branch pair: shared hops removed
    (they are the common suffix/prefix agreement cannot vouch for —
    ROUTES.md §4), diverse segments compared by declared artifact."""
    shared = sorted(set(route_a) & set(route_b))
    diverse_a = [p for p in route_a if p not in shared]
    diverse_b = [p for p in route_b if p not in shared]
    rec = _independence(route_anchors(diverse_a), route_anchors(diverse_b))
    rec.update({"a": _key(route_a), "b": _key(route_b),
                "shared_pairs": shared,
                "diverse_a": diverse_a, "diverse_b": diverse_b})
    return rec


def _floor_rank(floor: str) -> int:
    """Accept a grade name or an assurance-class name."""
    if floor in _route._CLASS_RANK:
        return _route._CLASS_RANK[floor]
    if floor in _route.GRADE_CLASS:
        return _route._CLASS_RANK[_route.GRADE_CLASS[floor]]
    raise ValueError(f"unknown floor: {floor!r} (grade or assurance class)")


def _pair_rank(pid: str) -> int:
    grade = registry.get_pair(pid).fidelity
    return _route._CLASS_RANK.get(_route.GRADE_CLASS.get(grade, "none"), 0)


def sub_floor_hops(route: list[str], floor: str) -> list[str]:
    """The hops of ``route`` whose declared assurance class falls below
    ``floor``. Composition is weakest-link (route.py), so *every* one of
    them binds: a certificate on one hop lifts the route only when it is
    the last hop below. Order follows the route."""
    rank = _floor_rank(floor)
    return [pid for pid in route if _pair_rank(pid) < rank]


def _certify_target(entries: list[dict[str, Any]],
                    floor: str | None) -> dict[str, Any] | None:
    """The ``certify-pair`` target (PROVING.md §3): upgrade a named
    pair's grade to ``proved`` by a named species.

    The route named is the **cheapest to lift** — fewest sub-floor hops,
    ties broken by the higher composed assurance and then by route key,
    so the target is deterministic and its signature stable. ``proved``
    is the tier the fidelity floor names (§4); when the caller's floor is
    below ``universal`` the certificate therefore over-delivers, which is
    stated in the note rather than silently rounded down.

    The *fragment* PROVING.md §3 asks for is each named pair's
    registered coverage (PAIRING.md §1): naming the pair names the
    fragment. A narrower fragment is the brief's to state — this advisor
    does not invent one, and in particular does not fold the asking
    question's observables in, which would split one instrument's
    evidence across every question shape that demands it.

    **The limit, stated.** This reads *declared* grades, so a hop that
    declares a universal-class grade is never demanded — including
    ``btor2-smtlib`` at ``predicted``, whose translation-level residual
    SCALING.md §11 names outright and which PROVING.md §7 picks as the
    first certificate to build. Seeing that is §4's job (the fidelity
    floor as a protected field, distinguishing an answer-level grade
    from a translation-level one), and §4 is not landed. Until it is,
    this target names the hops the *currency* says are short, not every
    hop a certificate would help.
    """
    ranked = []
    for e in entries:
        hops = sub_floor_hops(e["route"], floor or "universal")
        if not hops:
            continue  # a route with no sub-floor hop already meets it
        ranked.append((len(hops),
                       -_route._CLASS_RANK.get(e["assurance"], 0),
                       _key(e["route"]), e["route"], hops))
    if not ranked:
        return None
    ranked.sort(key=lambda c: c[:3])
    _n, _a, key, _route_ids, hops = ranked[0]
    return {
        "kind": "certify-pair",
        "route": key,
        "pairs": hops,
        "to_grade": "proved",
        "species": list(CERTIFY_SPECIES),
        "note": ("a translation-level certificate on the route's "
                 "sub-floor hops, re-verified by an independent pinned "
                 "checker (PROVING.md §3/§5) — the fragment is each named "
                 "pair's registered coverage unless the brief narrows it; "
                 "`proved` is the tier the fidelity floor names, so a "
                 "sub-universal floor is over-delivered, not rounded down"),
    }


def _pricing(certify: dict[str, Any],
             census: dict[str, list[str]]) -> dict[str, Any]:
    """The two instruments side by side (PROVING.md §3). A **view**
    field, never part of a target signature: the measured half is
    host-local and moves with the books, and folding it into identity
    would give the frontier board a new address every time a timing
    lands."""
    from . import ledger as _ledger

    measured = {}
    for pid in certify["pairs"]:
        prof = _ledger.profile("translate", pair=pid)
        measured[pid] = prof["wall_median_s"] if prof else None
    return {
        "independent-pair": {
            "registered_anchors": len(census),
            "needs_new_artifact": True,
            "note": "whether an artifact outside the registered anchors "
                    "exists at all is a fact about the world, not about "
                    "the platform (POTENTIAL.md §5)",
        },
        "certify-pair": {
            "hops_to_lift": len(certify["pairs"]),
            "translate_median_s": measured,
            "note": "the host-local ledger's cost side for the pairs a "
                    "certificate would cover — `None` is honestly "
                    "unmeasured, never a guessed zero; it prices the "
                    "certificate against the *existing* front-end",
        },
    }


def trust_options(source: str, dst: str, *, floor: str | None = None,
                  max_hops: int = 6) -> dict[str, Any]:
    """The trust view for a question routed ``source -> dst``: per-route
    assurance, branch independence, the anchor census, and — when the
    ``floor`` (a grade or assurance class) is unmet — what would raise
    trust, stated honestly (an existing independent branch to run; a new
    route from a *new* artifact; or saturation). A pure, read-only view:
    demand recording is owned by ``why_not`` (the fifth obstacle,
    ``trust``), which delegates here for the analysis."""
    found = _route.routes(source, dst, max_hops=max_hops)
    entries = []
    for r in found:
        fid = _route.route_fidelity(r)
        anchors = route_anchors(r)
        entries.append({
            "route": r,
            "fidelity": fid["fidelity"],
            "assurance": fid["assurance"],
            "direction": _route.route_direction(r),
            "anchors": sorted({v for v in anchors.values() if v}),
            "undeclared_pairs": sorted(p for p, v in anchors.items() if not v),
        })

    branches = [independence(a["route"], b["route"])
                for a, b in combinations(entries, 2)]
    census: dict[str, list[str]] = {}
    for e in entries:
        for pid, art in route_anchors(e["route"]).items():
            if art:
                census.setdefault(art, [])
                if pid not in census[art]:
                    census[art].append(pid)

    result: dict[str, Any] = {
        "routes": entries,
        "branches": branches,
        "anchors": {a: sorted(ps) for a, ps in sorted(census.items())},
        "floor": floor,
    }
    if floor is not None:
        rank = _floor_rank(floor)
        result["met_by"] = [_key(e["route"]) for e in entries
                            if _route._CLASS_RANK[e["assurance"]] >= rank]
        if result["met_by"]:
            return result

    independent_branches = [b for b in branches if b["independent"] is True]
    if independent_branches:
        result["corroboration"] = {
            "available": True,
            "branches": [(b["a"], b["b"]) for b in independent_branches],
            "note": "agreement on an independent branch corroborates beyond "
                    "either route's declared grade (ROUTES.md §4); "
                    "certificates at the terminal are the other instrument "
                    "(SOLVERS.md §5-6)",
        }
        return result

    # No independent branch: name the demand, honestly.
    if not entries:
        result["generation_target"] = None  # answerability first: why_not
        return result
    undeclared = sorted({p for b in branches for p in b["undeclared_pairs"]}
                        | {p for e in entries for p in e["undeclared_pairs"]})
    if branches and all(b["independent"] is None for b in branches):
        # Independence is *unknown*, not absent: the cheap instrument is
        # to declare it. No certificate is demanded against a question a
        # provenance declaration might answer for free (PROVING.md §6 —
        # the demand stays selective).
        result["generation_target"] = {
            "kind": "declare-provenance",
            "pairs": undeclared,
            "note": "independence is unknown until these pairs declare their "
                    "semantic_artifact (SCALING.md §9; coordinator-attested, "
                    "not self-reported)",
        }
        result["generation_targets"] = [result["generation_target"]]
        return result
    independent = {
        "kind": "independent-pair",
        "from": source,
        "avoiding_anchors": sorted(census),
        "note": ("a route derived from a semantic artifact outside the "
                 "registered set" +
                 (" — every existing branch shares an anchor, so further "
                  "same-anchor routes add count, not trust (saturation, "
                  "POTENTIAL.md §5)" if branches else
                  " — no second route exists yet (redundancy grows trust, "
                  "not answerability, POTENTIAL.md §3)")),
    }
    if undeclared:
        independent["undeclared_pairs"] = undeclared

    # The second honest instrument for the same failure (PROVING.md §3):
    # a certificate on the existing route, not a new front-end. Named
    # beside the first, priced against it, ranked against neither.
    certify = _certify_target(entries, floor)
    targets = [independent] + ([certify] if certify else [])
    result["generation_targets"] = targets
    result["generation_target"] = targets[0]
    if certify:
        result["pricing"] = _pricing(certify, census)
    return result
