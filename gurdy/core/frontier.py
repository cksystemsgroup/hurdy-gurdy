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

import json
from dataclasses import dataclass
from typing import Any

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
    kind: str | None  # None — no honest target (the outermost wall)
    target: dict[str, Any] | None
    required: dict[str, Any]   # {"keep": [...], "floor": ..., "budgets": {}}
    evidence: dict[str, Any]
    in_known_set: bool | None  # None when there is no target to classify
    registered_matches: tuple[str, ...]  # unbuilt registry pairs that match

    def asdict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "kind": self.kind,
            "target": self.target,
            "required": self.required,
            "evidence": self.evidence,
            "in_known_set": self.in_known_set,
            "registered_matches": list(self.registered_matches),
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
        out.append(FrontierObject(
            signature=sig,
            kind=kind,
            target=target,
            required=required,
            evidence=evidence,
            in_known_set=(None if target is None
                          else kind in IN_SET_KINDS),
            registered_matches=(_registered_matches(target, pairs)
                                if target else ()),
        ))
    out.sort(key=lambda o: (-o.evidence["distinct_questions"], o.signature))
    return tuple(out)


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
            if not rec["answerable"]:
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
    return {
        "suite": bench.suite,
        "provenance": bench.provenance(),
        "solved": sorted(e["name"] for e in fresh
                         if e["name"] not in open_names),
        "open": sorted(open_names),
        "questions": fresh,
        "board": [o.asdict() for o in board],
        "actionable": [o.signature for o in actionable],
        "saturated": not actionable,
    }
