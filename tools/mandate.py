#!/usr/bin/env python3
"""tools/mandate.py — the scoped registration mandate, in shadow mode
(FRONTIER.md §4.2; FRONTIER-PLAN.md C9; the L4 rung of
tools/autonomy.py).

A **mandate** is a human-written, revocable JSON document naming a
*region* of registration authority: the benchmark being saturated, the
obstacle classes in scope, the admissible languages, and the protected
floors (coverage target, direction policy, fidelity target) every
mandate-registered brief carries verbatim. Within it, the mechanical
instantiation of registration is delegated — one evidence-cited brief
at a time — and everything else escalates. Two lines the delegation
never crosses:

* **The design line.** The mandate instantiates only briefs whose
  design is *mechanical*: a widening of a named pair's projection, or
  taking up an already-registered brief. An in-scope target whose
  design needs a creative act (which translator? from which spec?)
  escalates even inside the region — delegated instantiation is not
  delegated judgment.
* **The write line.** This module registers nothing and writes
  nothing under ``pairs/``: it judges scope, emits brief text, and
  keeps the shadow score. In shadow mode (the only mode implemented)
  its output is compared against what the human actually did; the L4
  rung is earned by a window of zero would-be false-gos and **burned
  by any mandate-registered brief the human later rejects on scope**.

The mandate file (JSON, like every other frontier artifact — the plan
said ``mandate.yaml``; pruned to JSON, no new dependency)::

    {"name": "hwmcc-cost", "benchmark": "hwmcc-slice",
     "obstacles": ["cost", "loss"],
     "languages": ["btor2", "smtlib"],
     "floors": {"coverage_target": "the pair's existing inventory",
                "direction": "over pairs ship witness embeddings",
                "fidelity_target": "checked"}}
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Mandate:
    name: str
    benchmark: str
    obstacles: tuple[str, ...]
    languages: tuple[str, ...]
    floors: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def from_json(text: str) -> "Mandate":
        d = json.loads(text)
        return Mandate(name=d["name"], benchmark=d["benchmark"],
                       obstacles=tuple(d.get("obstacles", ())),
                       languages=tuple(d.get("languages", ())),
                       floors=dict(d.get("floors", {})))


def _target_languages(target: dict[str, Any]) -> list[str]:
    """The language names a target mentions (pair-name fields are
    scoped by obstacle and suite instead)."""
    out = []
    for key in ("from",):
        if target.get(key):
            out.append(target[key])
    for key in ("into_any_of", "on_any_of", "attach_to_any_of"):
        out.extend(target.get(key, ()))
    return out


def in_scope(mandate: Mandate, obj: dict[str, Any]) -> tuple[bool, str]:
    """The pure scope judgment for one board entry (a frontier-object
    dict, `gurdy/core/frontier.py`). False always carries the reason —
    an escalation is an explained event, never a silent drop."""
    if obj.get("in_known_set") is not True:
        return False, "outside the known set — a mandate cannot reach it"
    if mandate.benchmark not in obj.get("evidence", {}).get("suites", ()):
        return False, (f"no evidence from benchmark {mandate.benchmark!r} "
                       "— the mandate's region is the benchmark")
    obstacles = obj.get("evidence", {}).get("obstacles", ())
    outside = sorted(set(obstacles) - set(mandate.obstacles))
    if outside:
        return False, f"obstacle(s) {outside} outside the mandate"
    langs = _target_languages(obj.get("target") or {})
    bad = sorted(set(langs) - set(mandate.languages))
    if bad and mandate.languages:
        return False, f"language(s) {bad} outside the mandate"
    return True, "in scope"


def mechanical_design(obj: dict[str, Any]) -> str | None:
    """The design line: the brief's 'intended translator' filled only
    where no creative act is needed. None = in-scope-but-escalate.
    Deliberately knows no ``native-procedure`` design (SYNTHESIS.md
    §7): choosing an algorithm family is maximally creative, so the
    synthesis lane escalates under every mandate until a dedicated
    rung exists — and none does."""
    kind = obj.get("kind")
    if kind == "wider-projection":
        keep = obj.get("required", {}).get("keep", [])
        return (f"widen the named pair(s)' projection to keep "
                f"{keep} — the ratchet-protected widening lane "
                "(SCALING.md §12.4)")
    if kind == "reduction" and obj.get("registered_matches"):
        return ("take up the registered brief(s): "
                + ", ".join(obj["registered_matches"]))
    return None


def would_register(mandate: Mandate,
                   board: list[dict[str, Any]]) -> dict[str, Any]:
    """The shadow output for one board: per entry, register (with the
    stamped brief) / escalate (with the reason). Emits text; writes
    nothing."""
    from gurdy.core.frontier import promote_brief

    register, escalate = [], []
    for obj in board:
        ok, reason = in_scope(mandate, obj)
        if not ok:
            escalate.append({"id": obj["id"], "reason": reason})
            continue
        design = mechanical_design(obj)
        if design is None:
            escalate.append({"id": obj["id"],
                             "reason": "in scope, design not mechanical "
                                       "— a creative act stays human"})
            continue
        brief = promote_brief(obj) + "\n\n" + "\n".join([
            "## Mandate-fixed floors (protected; not the builder's to "
            "change)",
            "",
            f"- **Mandate.** `{mandate.name}` — revocable by the human "
            "who wrote it (FRONTIER.md §4.2).",
            f"- **Intended translator (mechanical).** {design}",
            *(f"- **{k}.** {v}" for k, v in sorted(mandate.floors.items())),
        ])
        register.append({"id": obj["id"], "signature": obj["signature"],
                         "brief": brief})
    return {"mandate": mandate.name, "register": register,
            "escalate": escalate}


def shadow_trials(shadow: dict[str, Any],
                  human: dict[str, str]) -> list[dict[str, Any]]:
    """Score one shadow round against what the human actually did
    (``human``: board id → "registered" | "declined"). A would-be
    false-go — the mandate would register, the human declined — is
    the disagreement that must stay zero to earn L4; a missed-go is
    informative, never disqualifying (the mandate is allowed to be
    conservative)."""
    trials = []
    would = {e["id"] for e in shadow["register"]}
    for oid, action in sorted(human.items()):
        w = oid in would
        trials.append({
            "id": oid, "would_register": w, "human": action,
            "disagreement": ("false-go" if w and action != "registered"
                             else "missed-go"
                             if not w and action == "registered"
                             else None),
        })
    return trials


def fold(ledger: dict[str, Any],
         trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold a shadow round into an autonomy-ledger dict
    (tools/autonomy.py::Ledger fields). Only trials the mandate would
    have gone on count toward the window; false-gos count against it."""
    out = dict(ledger)
    for t in trials:
        if t["would_register"]:
            out["mandate_shadow_seen"] = out.get("mandate_shadow_seen", 0) + 1
            if t["disagreement"] == "false-go":
                out["mandate_shadow_disagreements"] = (
                    out.get("mandate_shadow_disagreements", 0) + 1)
    return out


def scope_rejection(ledger: dict[str, Any]) -> dict[str, Any]:
    """A mandate-registered brief the human later rejected on scope:
    the burn (FRONTIER.md §4.2). L4 drops until a human re-graduates."""
    out = dict(ledger)
    out["mandate_scope_rejections"] = (
        out.get("mandate_scope_rejections", 0) + 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="shadow-mode mandate check: what the mandate WOULD "
                    "register from the current board — printing only")
    ap.add_argument("mandate", help="mandate JSON")
    ap.add_argument("--ledger", required=True, help="the books")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    import gurdy.cli  # noqa: F401  (registers the graph)
    from gurdy.core import ledger as _ledger, registry
    from gurdy.core.frontier import derive

    mandate = Mandate.from_json(pathlib.Path(args.mandate).read_text())
    records = [r for r in _ledger._records(args.ledger)
               if r.get("kind") == "demand"]
    board = [o.asdict() for o in derive(records, registry.list_pairs())]
    shadow = would_register(mandate, board)
    if args.json:
        print(json.dumps(shadow, indent=2, default=str))
        return 0
    print(f"mandate {mandate.name!r} over benchmark "
          f"{mandate.benchmark!r} — shadow mode (nothing registers):")
    for e in shadow["register"]:
        print(f"  would register {e['id']}")
    for e in shadow["escalate"]:
        print(f"  escalate {e['id']}: {e['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
