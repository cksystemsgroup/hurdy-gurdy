#!/usr/bin/env python3
"""tools/procedure_dispatch.py — the solver-synthesis lane, shadow-first
(SYNTHESIS.md §7; the procedure sibling of tools/builder_dispatch.py).

The pair lane turns a partial pair's uncovered constructs into work
items; this lane turns the board's `native-procedure` entries into
**procedure-synthesis briefs** — the fourth extraction operator beside
the three of the design-oracle table (FRONTIER-PLAN.md §"far side"):

* ``work_list`` — the derived board's `native-procedure` entries,
  split honestly: **workable** (atlas-charted, inside the known set —
  instantiation) and **frontier** (uncharted — discovery, listed
  apart and never worked by this lane);
* ``fragment_hull`` — the data-defined fragment: the shapes, sources,
  and observables of the citing questions, verbatim — what the
  procedure must actually decide, defined by demand rather than
  taste;
* ``draft_solver_brief`` — the SolverBrief skeleton with the human's
  fields left TODO. The draft deliberately **fails validation** until
  a human completes it: an unregisterable draft is the write line, in
  type form;
* ``build_brief`` — the self-contained markdown work item: hull,
  atlas location and family, required contract, the certificate
  obligation to declare (SOLVERS.md §2.1), the deliverables (a
  backend class under ``gurdy/solvers/``, its brief entry), and the
  admission command;
* ``self_verify`` — the lane's gate: brief validation
  (solvers/brief.py) plus the solver admission gate
  (tools/solver_gate.py) at ``runs=2`` — a synthesized pure-Python
  procedure gets the strict gate (SYNTHESIS.md §6), no exceptions.

Discipline, same as every valve: **registration is a human act.** No
autonomy rung exists for this lane — ``mandate.mechanical_design``
knows no procedure design, so under any mandate the kind escalates by
construction — and this module writes nothing under ``gurdy/solvers/``:
it derives, drafts, prints, and verifies. The reference inhabitant it
was exercised on is ``gurdy/solvers/enum_btor2.py``.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from gurdy.core.solver import Verdict  # noqa: E402  (re-export for briefs)
from gurdy.solvers.brief import (  # noqa: E402
    SHAPE_CLAIMS,
    SolverBrief,
    validate,
)

Decider = Callable[[str, int], Verdict]


def work_list(records: list[dict[str, Any]],
              pairs: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The lane's queue, derived from the books (pure, like the board
    it reads): `native-procedure` entries only, split by atlas
    chartedness. Everything else on the board belongs to the pair
    lane."""
    from gurdy.core.frontier import derive

    workable, frontier = [], []
    for obj in derive(records, pairs):
        if obj.kind != "native-procedure":
            continue
        (workable if obj.in_known_set else frontier).append(obj.asdict())
    return {"workable": workable, "frontier": frontier}


def fragment_hull(obj: dict[str, Any]) -> dict[str, Any]:
    """The data-defined fragment: what the citing questions actually
    ask, joined — the hull the procedure must cover, and the corpus
    its overfit would be audited against."""
    citing = obj.get("citing", ())
    return {
        "shapes": sorted({q.get("shape") for q in citing
                          if q.get("shape")}),
        "sources": sorted({q.get("source") for q in citing
                           if q.get("source")}),
        "observables": sorted({o for q in citing
                               for o in q.get("observables", ())}),
        "questions": len(citing),
    }


def draft_solver_brief(obj: dict[str, Any]) -> SolverBrief:
    """The SolverBrief skeleton for one board entry. The human's
    fields are TODO — and the draft therefore fails
    ``brief.validate`` until a human completes it: the write line,
    enforced by the contract itself."""
    target = obj.get("target") or {}
    shape = target.get("shape")
    hubs = target.get("attach_to_any_of", ())
    required = obj.get("required", {})
    return SolverBrief(
        engine=f"TODO-{shape}",
        language=(hubs[0] if hubs else "TODO"),
        shapes=(shape,) if shape else (),
        budgets=dict(required.get("budgets") or {}) or {"wall_s": "TODO"},
        certificates={f"{shape}/{claim}": "TODO"
                      for claim in SHAPE_CLAIMS.get(shape, ("TODO",))},
        lineage=(),   # the reference semantics — the human names them
        intended="TODO — the algorithm family is the human's choice "
                 "(the design line, FRONTIER.md §4.2)",
    )


def build_brief(obj: dict[str, Any]) -> str:
    """The self-contained work item for one workable entry — the
    fourth extraction operator's output, printable and pastable."""
    target = obj.get("target") or {}
    atlas = obj.get("atlas") or {}
    hull = fragment_hull(obj)
    req = obj.get("required", {})
    ev = obj.get("evidence", {})
    shape = target.get("shape")
    lines = [
        f"# Procedure synthesis — `{shape}`  (id {obj.get('id')})  "
        "(WORK ITEM)",
        "",
        "*Derived from the books (tools/procedure_dispatch.py) — "
        "**registration is a human act** (AGENTS.md §1; SOLVERS.md "
        "§2.1): this becomes a brief only when a human completes the "
        "TODO fields of the draft and stands behind the design.*",
        "",
        "## The demand",
        "",
        f"- **Shape.** `{shape}` — "
        f"{ev.get('distinct_questions')} distinct citing question(s), "
        f"origins {ev.get('origins')}.",
        f"- **Attach to.** one of {list(target.get('attach_to_any_of', ()))}",
        f"- **Procedure family (atlas).** {target.get('family')}",
        f"- **Known crossing (try first).** "
        f"{atlas.get('crossing') or '(none — no cheaper discharge known)'}",
        "",
        "## The fragment hull (what it must decide, defined by demand)",
        "",
        f"- shapes: {hull['shapes']}",
        f"- source languages: {hull['sources']}",
        f"- observables: {hull['observables'] or '(none named)'}",
        "",
        "## Required contract (joined over the citing questions)",
        "",
        f"- **Assurance floor:** {req.get('floor') or '(none stated)'}",
        f"- **Spent budgets:** {req.get('budgets') or '(statically blocked)'}",
        "",
        "## Deliverables (the lane's shape — see "
        "gurdy/solvers/enum_btor2.py for the reference)",
        "",
        "- a backend class under `gurdy/solvers/` — pure, "
        "deterministic, budget-declared;",
        "- its `SolverBrief` entry (solvers/brief.py): shapes, "
        "budgets, certificate obligation per claim, **lineage naming "
        "the reference semantics it was built from**;",
        "- admission: `self_verify` — brief validation + the solver "
        "gate at runs=2 (tools/solver_gate.py; SYNTHESIS.md §5–6).",
    ]
    return "\n".join(lines)


def self_verify(decider: Decider, brief: SolverBrief,
                corpus: list[dict[str, Any]] | None = None,
                runs: int = 2) -> dict[str, Any]:
    """The lane's gate: the brief must validate and the engine must be
    admitted by the solver gate — at ``runs=2`` by default, because a
    lane-built procedure is pure Python and gets the strict gate
    (SYNTHESIS.md §6). Returns both verdicts; ``admitted`` is their
    conjunction."""
    import solver_gate

    problems = validate(brief)
    report = solver_gate.gate(decider, corpus, candidate=brief.engine,
                              runs=runs)
    return {"brief_problems": problems, "gate": report,
            "admitted": not problems and report.admitted}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="the solver-synthesis lane's work list and briefs "
                    "— printing only; registration stays human")
    ap.add_argument("--ledger", required=True, help="the books")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    import gurdy.cli  # noqa: F401  (registers the graph)
    from gurdy.core import ledger as _ledger, registry

    records = [r for r in _ledger._records(args.ledger)
               if r.get("kind") == "demand"]
    queue = work_list(records, registry.list_pairs())
    if args.json:
        print(json.dumps(queue, indent=2, default=str))
        return 0
    print(f"workable (charted — instantiation): "
          f"{len(queue['workable'])}")
    for obj in queue["workable"]:
        print()
        print(build_brief(obj))
    print()
    print(f"frontier (uncharted — discovery, not worked by this lane): "
          f"{[o['id'] for o in queue['frontier']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
