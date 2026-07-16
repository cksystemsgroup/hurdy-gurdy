"""The far side, derived — frontier objects and the saturation check
(FRONTIER.md §1.1; the currency of FRONTIER-PLAN.md §1.6).

Two functions, one story:

* ``derive`` is a **pure** function of (demand records, registered
  pairs): records group by generation-target signature and each group
  becomes a **frontier object** — the target's kind and detail, the
  **required contract** joined over the citing questions (the union of
  observables they need kept, the highest floor they state, the
  histogram of spent verdicts), the evidence (distinct questions,
  origins, suites, first/last seen), and its classification against
  the known set. Derived, never stored; there is no write path.

* ``saturate`` runs the fixpoint check over a pinned benchmark
  (core/benchmark.py): re-diagnose every question statically, keep the
  iteration's standing **cost** demands (a spent verdict a static
  re-ask cannot reproduce), derive the board from the open questions'
  records, and report **saturated** iff no derived object lies inside
  the known set — the tier-2 emptiness of the plan's F5. The books
  decide; no judgment call.

Classification against the known set: ``pair``, ``wider-projection``,
``reduction``, and ``declare-provenance`` targets lie **inside** (a
brief over registered languages and solvers could be written today —
registered-but-unbuilt matches are named beside them), while
``reasoning-language`` and ``independent-pair`` targets lie
**outside** (a hypothetical language; a semantic artifact the world
has not supplied), and a record may honestly carry **no** target at
all (POTENTIAL.md §5) — the outermost wall names nothing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .atlas import locate as atlas_locate
from .ledger import target_signature
from .question import Question, question_key
from .registry import Pair, Status

#: Target kinds a registration brief could be written for today.
IN_SET_KINDS = ("pair", "wider-projection", "reduction",
                "declare-provenance")
#: Target kinds naming something outside the known set.
OUT_SET_KINDS = ("reasoning-language", "independent-pair")


@dataclass(frozen=True)
class FrontierObject:
    """One entry of the terminal board: a generation target with its
    required contract and evidence — a frontier pair when the target
    is edge-shaped, a capability demand when it names a language-side
    instrument. Never executable; promotion is registration."""

    signature: str
    id: str  # sha256(signature) prefix — the board's stable address
    kind: str | None  # None — no honest target (the outermost wall)
    target: dict[str, Any] | None
    required: dict[str, Any]   # {"keep": [...], "floor": ..., "budgets": {}}
    evidence: dict[str, Any]
    citing: tuple[dict[str, Any], ...]  # the questions verbatim, deduped
    in_known_set: bool | None  # None when there is no target to classify
    registered_matches: tuple[str, ...]  # unbuilt registry pairs that match
    atlas: dict[str, Any] | None = None  # shape targets: the landscape

    def asdict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "id": self.id,
            "kind": self.kind,
            "target": self.target,
            "required": self.required,
            "evidence": self.evidence,
            "citing": list(self.citing),
            "in_known_set": self.in_known_set,
            "registered_matches": list(self.registered_matches),
            "atlas": self.atlas,
        }


def _floor_max(floors: list[str]) -> str | None:
    from .trust import _floor_rank

    return max(floors, key=_floor_rank) if floors else None


def _registered_matches(target: dict[str, Any],
                        pairs: dict[str, Pair]) -> tuple[str, ...]:
    """Registry pairs that address the target but are not built yet —
    tier 2 in flight. (A built match means the demand is stale; the
    fresh diagnosis would no longer fire.)"""
    kind = target.get("kind")
    if kind == "pair":
        into = set(target.get("into_any_of", ()))
        return tuple(sorted(
            pid for pid, p in pairs.items()
            if p.source == target.get("from") and p.target in into
            and p.status is not Status.BUILT))
    if kind in ("wider-projection", "declare-provenance"):
        return tuple(sorted(p for p in target.get("pairs", ()) if p in pairs))
    if kind == "reduction":
        return tuple(sorted(
            p for p in target.get("registered_reductions", ())
            if p in pairs and pairs[p].status is not Status.BUILT))
    return ()


def derive(records: list[dict[str, Any]],
           pairs: dict[str, Pair]) -> tuple[FrontierObject, ...]:
    """The board, from the books: pure in its inputs, deterministic in
    its output (sorted by evidence volume, then signature — the
    demand_summary order)."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if r.get("kind", "demand") != "demand":
            continue
        groups.setdefault(target_signature(r.get("target")), []).append(r)

    out = []
    for sig, recs in groups.items():
        # The canonical target is the signature's own data (prose
        # ``note``s are per-record and would make the representative
        # depend on record order).
        target = None if sig == "(none)" else json.loads(sig)
        kind = target.get("kind") if target else None
        questions = [r.get("question", {}) for r in recs]
        budgets: dict[str, int] = {}
        for q in questions:
            v = q.get("verdict")
            if v is not None:
                budgets[v] = budgets.get(v, 0) + 1
        required = {
            "keep": sorted({o for q in questions
                            for o in q.get("observables", ())}),
            "floor": _floor_max([q["floor"] for q in questions
                                 if q.get("floor") is not None]),
            "budgets": dict(sorted(budgets.items())),
        }
        origins: dict[str, int] = {}
        for r in recs:
            o = r.get("origin", "organic")
            origins[o] = origins.get(o, 0) + 1
        stamps = [r["ts"] for r in recs if r.get("ts") is not None]
        evidence = {
            "distinct_questions": len({question_key(q) for q in questions}),
            "origins": dict(sorted(origins.items())),
            "suites": sorted({r["suite"] for r in recs
                              if r.get("suite") is not None}),
            "first_ts": min(stamps) if stamps else None,
            "last_ts": max(stamps) if stamps else None,
        }
        deduped: dict[str, dict[str, Any]] = {}
        for q in questions:
            deduped.setdefault(question_key(q), q)
        citing = tuple(sorted(
            deduped.values(),
            key=lambda q: json.dumps(q, sort_keys=True, default=str)))
        out.append(FrontierObject(
            signature=sig,
            id=hashlib.sha256(sig.encode("utf-8")).hexdigest()[:12],
            kind=kind,
            target=target,
            required=required,
            evidence=evidence,
            citing=citing,
            in_known_set=(None if target is None
                          else kind in IN_SET_KINDS),
            registered_matches=(_registered_matches(target, pairs)
                                if target else ()),
            # The shape operator (O1): a demand for a new reasoning
            # language arrives locating itself in the known landscape
            # — including the classical crossing that might discharge
            # it with an endo-pair instead.
            atlas=(atlas_locate(target.get("shape"))
                   if kind == "reasoning-language" and target else None),
        ))
    out.sort(key=lambda o: (-o.evidence["distinct_questions"], o.signature))
    return tuple(out)


def conditional_plans(target: dict[str, Any] | None,
                      max_hops: int = 6) -> list[dict[str, Any]] | None:
    """The conditional reading of an edge-shaped frontier object
    (FRONTIER-PLAN.md §1.6): discharge ``source → T``, and an existing
    suffix completes the route. ``why_not`` computed ``into_any_of``
    as exactly the hub-connected languages, so the suffix exists by
    construction; this advisor names it, with its composed assurance
    — the conditional contract's achieved half. Advisory strings in a
    report, never registry edges: no conditional route is executable,
    by construction rather than by flag."""
    if not target or target.get("kind") != "pair":
        return None
    from . import route as _route
    from .whynot import reasoning_languages

    hubs = reasoning_languages()
    plans = []
    for t in target.get("into_any_of", ()):
        if t in hubs:
            plans.append({"discharge": f"{target.get('from')} -> {t}",
                          "suffix": "(native — T is a reasoning language)"})
            continue
        suffix: dict[str, Any] = {}
        for hub in hubs:
            entries = _route.route_report(t, hub, max_hops=max_hops)
            if entries:
                best = max(entries, key=lambda e: _route._CLASS_RANK.get(
                    e.get("assurance"), 0))
                suffix[hub] = {"routes": len(entries),
                               "best_assurance": best.get("assurance")}
        if suffix:
            plans.append({"discharge": f"{target.get('from')} -> {t}",
                          "suffix": suffix})
    return plans or None


def promote_brief(obj: FrontierObject | dict[str, Any]) -> str:
    """A draft registration brief for one board entry, its evidence
    cited verbatim (plan C8 — generalizes ``why-not --brief-stub``).
    A stub, not a registration: writing it under ``pairs/`` and
    admitting it stay the human act of AGENTS.md §1; this function
    only prints."""
    o = obj.asdict() if isinstance(obj, FrontierObject) else obj
    target = o.get("target") or {}
    kind = o.get("kind") or "(no honest target)"
    req = o.get("required", {})
    ev = o.get("evidence", {})
    lines = [
        f"# Frontier promotion — {kind}  (id {o.get('id')})  (DRAFT BRIEF)",
        "",
        "*Derived from the books (`gurdy saturation` /"
        " `gurdy frontier-promote`) — **registration is a human act**",
        "(AGENTS.md §1): this becomes a brief only when a human writes it",
        "under `pairs/` and stands behind its scope.*",
        "",
        "## Generation target",
        "",
    ]
    for k, v in sorted(target.items()):
        if k != "note":
            lines.append(f"- **{k}.** {v}")
    if target.get("note"):
        lines.append(f"- *{target['note']}*")
    lines += [
        "",
        "## Required contract (joined over the citing questions)",
        "",
        f"- **Projection `π` must keep at least:** "
        f"{', '.join(f'`{k}`' for k in req.get('keep', [])) or '(none named)'}",
        f"- **Assurance floor:** {req.get('floor') or '(none stated)'}",
        f"- **Spent budgets (verdict histogram):** "
        f"{req.get('budgets') or '(none — statically blocked)'}",
        "",
        "## Evidence",
        "",
        f"- distinct questions: {ev.get('distinct_questions')}",
        f"- origins: {ev.get('origins')}",
        f"- suites: {ev.get('suites') or '(unscoped)'}",
        f"- first/last seen: {ev.get('first_ts')} / {ev.get('last_ts')}",
        "",
        "### Citing questions, verbatim",
        "",
    ]
    for q in o.get("citing", ()):
        lines.append(f"- `{json.dumps(q, sort_keys=True, default=str)}`")
    if o.get("atlas"):
        a = o["atlas"]
        lines += ["", "## Atlas location (the known landscape)", ""]
        for k in ("shape", "setting", "status", "native", "crossing",
                  "note"):
            if a.get(k):
                lines.append(f"- **{k}.** {a[k]}")
    plans = conditional_plans(o.get("target"))
    if plans:
        lines += ["", "## Conditional plans (existing suffix per discharge)",
                  ""]
        for p in plans:
            lines.append(f"- discharge `{p['discharge']}` → "
                         f"suffix: {p['suffix']}")
    lines += [
        "",
        "## To complete (AGENTS.md §1 — the human's fields)",
        "",
        "- **Intended translator.** TODO (spec-derived / pinned tool / "
        "rule-for-rule mapping).",
        "- **Fidelity target + evidence.** TODO (PAIRING.md §4; not "
        "inflated).",
        "- **Direction.** TODO (`exact` default; `over` ships its witness "
        "embedding).",
        "- **Coverage target.** TODO (construct inventory + public suite, "
        "BENCHMARKS.md).",
        "- **Reuses / contributes.** TODO (shared interpreters; "
        "reuse-first).",
    ]
    return "\n".join(lines)


def _static_key(question: dict[str, Any]) -> str:
    """Question identity with the spent verdict stripped: what matches
    a cost record to the static question it was about."""
    return question_key({k: v for k, v in question.items()
                         if k != "verdict"})


def saturate(bench: Any, *, ledger_path: str | None = None,
             max_hops: int = 6) -> dict[str, Any]:
    """The fixpoint check (FRONTIER.md §1.1). Re-diagnoses every
    question of ``bench`` statically (recording suite-tagged demands
    when ``ledger_path`` is given — the iteration's books), merges the
    suite's standing cost demands, derives the board from the open
    questions' records, and reports ``saturated`` iff no derived
    object lies inside the known set."""
    from . import ledger as _ledger, registry as _registry
    from .whynot import why_not

    prior = _ledger._path_override
    if ledger_path is not None:
        _ledger.configure(ledger_path)
    try:
        fresh = []
        for inst in bench.instances:
            q = inst.question
            program = q.program or inst.name
            rec = why_not(
                q.source,
                list(q.observables) if q.observables is not None else None,
                q.shape, floor=q.floor, program=program,
                origin="campaign", suite=bench.suite, max_hops=max_hops)
            entry: dict[str, Any] = {
                "name": inst.name,
                "answerable": rec["answerable"],
                "question": Question(
                    source=q.source, observables=q.observables,
                    shape=q.shape, floor=q.floor, program=program).asdict(),
            }
            if rec["answerable"]:
                # The way-census (FRONTIER.md §1 "solved, all ways"):
                # the diagnosis already computed the full option set —
                # every feasible route with its composed assurance,
                # direction, feasibility, and measured cost profile —
                # so the census is kept, not recomputed.
                entry["census"] = rec["routes"]
                for extra in ("met_by", "corroboration"):
                    if extra in rec:
                        entry[extra] = rec[extra]
            else:
                entry["obstacle"] = rec["obstacle"]
                entry["target"] = rec.get("generation_target")
            fresh.append(entry)
    finally:
        _ledger.configure(prior)

    if ledger_path is not None:
        records = [r for r in _ledger._records(ledger_path)
                   if r.get("kind") == "demand"
                   and r.get("suite") == bench.suite]
    else:
        records = [{"kind": "demand", "question": e["question"],
                    "obstacle": e["obstacle"], "target": e.get("target"),
                    "origin": "campaign", "suite": bench.suite}
                   for e in fresh if not e["answerable"]]

    # Standing dynamic demand: a cost record's spent verdict is evidence
    # a static re-ask cannot reproduce, so it keeps its question open
    # for this iteration (the loop owns freshness — hand this function
    # the iteration's ledger, not all history).
    name_by_key = {_static_key(e["question"]): e["name"] for e in fresh}
    dynamic: set[str] = set()
    for r in records:
        if r.get("obstacle") == "cost":
            name = name_by_key.get(_static_key(r.get("question", {})))
            if name is not None:
                dynamic.add(name)

    open_names = {e["name"] for e in fresh if not e["answerable"]} | dynamic
    open_keys = {_static_key(e["question"]) for e in fresh
                 if e["name"] in open_names}
    open_records = [r for r in records
                    if _static_key(r.get("question", {})) in open_keys]

    board = derive(open_records, _registry.list_pairs())
    actionable = [o for o in board if o.in_known_set]
    board_dicts = []
    for o in board:
        d = o.asdict()
        plans = conditional_plans(o.target, max_hops=max_hops)
        if plans:
            d["conditional"] = plans
        board_dicts.append(d)
    return {
        "suite": bench.suite,
        "provenance": bench.provenance(),
        "solved": sorted(e["name"] for e in fresh
                         if e["name"] not in open_names),
        "open": sorted(open_names),
        "questions": fresh,
        "board": board_dicts,
        "actionable": [o.signature for o in actionable],
        "saturated": not actionable,
    }
