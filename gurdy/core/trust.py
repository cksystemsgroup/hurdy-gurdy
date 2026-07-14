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
  the anchor census, and — when the floor is unmet — the demand record:
  run an existing independent branch, or generate a route derived from a
  *new* artifact, or, honestly, **saturation**: every further route
  would share the registered anchors, and more spending buys no trust.

Read-only and advisory throughout: grades are declared and protected;
corroboration is evidence the player runs, not a grade this module
awards; nothing here chooses.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from . import registry
from . import route as _route


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


def trust_options(source: str, dst: str, *, floor: str | None = None,
                  max_hops: int = 6) -> dict[str, Any]:
    """The trust ledger for a question routed ``source -> dst``: per-route
    assurance, branch independence, the anchor census, and — when the
    ``floor`` (a grade or assurance class) is unmet — what would raise
    trust, stated honestly (an existing independent branch to run; a new
    route from a *new* artifact; or saturation)."""
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
                    "certificates at the terminal are the other currency "
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
        result["generation_target"] = {
            "kind": "declare-provenance",
            "pairs": undeclared,
            "note": "independence is unknown until these pairs declare their "
                    "semantic_artifact (SCALING.md §9; coordinator-attested, "
                    "not self-reported)",
        }
        return result
    result["generation_target"] = {
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
        result["generation_target"]["undeclared_pairs"] = undeclared
    return result
