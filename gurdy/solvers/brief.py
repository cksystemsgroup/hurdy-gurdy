"""Solver briefs — the per-engine contract (SYNTHESIS.md §4;
SOLVERS.md §2.1).

A pair enters the platform through a one-page brief a human registers
(AGENTS.md §1). A solver enters through the same discipline: a
**solver brief** declares, per engine,

* the **language** it attaches to and the **shapes** it decides —
  tokens of the SOLVERS.md §9 taxonomy, honest against the atlas;
* the **budget schema** — the declared limits its runs are bounded by
  (never an undeclared hardcoded timeout);
* the **certificate obligation**, per shape × verdict: the witness
  kind it emits and the deterministic-side checker that re-validates
  it (SOLVERS.md §5) — or the explicit ``UNCHECKABLE``, which caps
  what an answer through this engine can contribute: corroboration
  (``checked``) remains reachable, certification (``proved``) does
  not. The silent ``unsupported`` escape hatch is closed: every
  declared shape carries a stated obligation.
* the **lineage** — the codebase ancestry the engine descends from,
  the unit of independence accounting: corroboration counts only
  agreement across *disjoint declared lineages*
  (``solvers/proved.py``), so a teacher and its student can never
  corroborate each other. For a synthesized engine, lineage includes
  the reference semantics and any solver corpus it was synthesized
  from.
* the **intended** design, in a sentence — the human's field, exactly
  as a pair brief's "intended translator" is.

Registration stays a human act; a brief is recommended by the
``native-procedure`` demand that cites it (SYNTHESIS.md §3) and its
admission gate is ``tools/solver_gate.py`` (SYNTHESIS.md §5). The
``BRIEFS`` table below is the registered set — the existing engines,
retroactively under the contract they always implicitly had.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: The explicit no-certificate declaration: the claim can be
#: corroborated, never certified. Declaring it is honest; omitting the
#: entry is a validation failure.
UNCHECKABLE = "uncheckable"

#: The verdicts each declared shape obliges an entry for — the claims
#: an engine can make in that shape (SOLVERS.md §9's table rows).
SHAPE_CLAIMS: dict[str, tuple[str, ...]] = {
    "reachability": ("reachable",),
    "bounded-unreachability": ("unreachable",),
}


@dataclass(frozen=True)
class SolverBrief:
    engine: str                      # backend id (solvers/inventory.py)
    language: str                    # reasoning language it attaches to
    shapes: tuple[str, ...]          # SOLVERS.md §9 tokens
    budgets: dict[str, Any]          # declared limits schema
    certificates: dict[str, Any]     # "shape/verdict" -> obligation
    lineage: tuple[str, ...]         # codebase ancestry (independence)
    intended: str                    # the design, in a sentence

    def obligation(self, shape: str, verdict: str) -> Any | None:
        return self.certificates.get(f"{shape}/{verdict}")


def validate(brief: SolverBrief) -> list[str]:
    """The brief's static contract check. Returns the list of problems
    — empty means valid. Validation is honest, not clever: it checks
    that every declaration is *present and well-formed*; whether the
    engine lives up to it is the admission gate's job."""
    from ..core.atlas import locate

    problems: list[str] = []
    if not brief.shapes:
        problems.append("no shapes declared")
    for shape in brief.shapes:
        if locate(shape).get("status") == "uncharted":
            problems.append(
                f"shape {shape!r} is uncharted in the atlas — chart it "
                "by review before a brief declares it (SOLVERS.md §9)")
        claims = SHAPE_CLAIMS.get(shape, ())
        if not claims and not any(k.startswith(f"{shape}/")
                                  for k in brief.certificates):
            problems.append(
                f"shape {shape!r}: no certificate obligation entry")
        for verdict in claims:
            ob = brief.obligation(shape, verdict)
            if ob is None:
                problems.append(
                    f"{shape}/{verdict}: obligation missing — declare "
                    f"a witness+checker or {UNCHECKABLE!r} explicitly")
            elif ob != UNCHECKABLE and not (
                    isinstance(ob, dict) and ob.get("witness")
                    and ob.get("checker")):
                problems.append(
                    f"{shape}/{verdict}: obligation must be "
                    f"{UNCHECKABLE!r} or a witness+checker dict")
    if not brief.lineage:
        problems.append("no lineage declared — independence accounting "
                        "needs ancestry (an unknown ancestry is a "
                        "declaration too: name the reference semantics)")
    if not brief.budgets:
        problems.append("no budget schema declared")
    if not brief.intended.strip():
        problems.append("the intended design is the human's field — "
                        "it cannot be empty")
    return problems


def assurance_ceiling(brief: SolverBrief) -> dict[str, str]:
    """What an answer through this engine can at most contribute, per
    declared claim: ``proved`` when the obligation names a
    deterministic-side re-validation (witness replay or a proof
    checker, SOLVERS.md §5), ``checked`` when the claim is declared
    uncheckable — corroboration across disjoint lineages remains
    available (§6), certification does not."""
    out: dict[str, str] = {}
    for key, ob in brief.certificates.items():
        out[key] = "checked" if ob == UNCHECKABLE else "proved"
    return out


def independent(a: Any, b: Any) -> bool:
    """Lineage disjointness — the independence predicate corroboration
    uses. Conservative: an *undeclared* lineage is never independent
    (you cannot corroborate with an engine of unknown ancestry)."""
    la = tuple(getattr(a, "lineage", ()) or ())
    lb = tuple(getattr(b, "lineage", ()) or ())
    return bool(la) and bool(lb) and not (set(la) & set(lb))


#: The registered briefs — every engine the inventories ship, under
#: the contract. Amending this table is a versioned admission event
#: (SOLVERS.md §2), human-reviewed like every protected instrument.
BRIEFS: dict[str, SolverBrief] = {
    "z3": SolverBrief(
        engine="z3", language="smtlib",
        shapes=("reachability", "bounded-unreachability"),
        budgets={"wall_s": 300},
        certificates={
            "reachability/reachable": {
                "witness": "model (input binding)",
                "checker": "smtlib evaluator + source replay "
                           "(SOLVERS.md §4)"},
            # z3 emits no proof artifact the platform checks: the
            # unsat claim is corroboration-only, declared as such.
            "bounded-unreachability/unreachable": UNCHECKABLE,
        },
        lineage=("z3",),
        intended="Z3 through its Python bindings — the wired MVP "
                 "engine; models parsed, proofs not"),
    "bitwuzla": SolverBrief(
        engine="bitwuzla", language="smtlib",
        shapes=("reachability", "bounded-unreachability"),
        budgets={"wall_s": 300},
        certificates={
            # verdict-only adapter on the reachable side (models are
            # z3's job) — declared, not hidden.
            "reachability/reachable": UNCHECKABLE,
            "bounded-unreachability/unreachable": {
                "witness": "DRAT via bit-blast (--write-cnf + cadical)",
                "checker": "drat-trim / cake_lpr (solvers/proved.py, "
                           "SOLVERS.md §5–6)"},
        },
        lineage=("boolector", "bitwuzla"),
        intended="Bitwuzla CLI — Boolector's successor; the "
                 "bit-blaster of the proved chain"),
    "boolector": SolverBrief(
        engine="boolector", language="smtlib",
        shapes=("reachability", "bounded-unreachability"),
        budgets={"wall_s": 300},
        certificates={
            "reachability/reachable": UNCHECKABLE,
            "bounded-unreachability/unreachable": UNCHECKABLE,
        },
        lineage=("boolector",),
        intended="Boolector CLI — verdict-only corroboration; shares "
                 "the boolector lineage with bitwuzla, so the two "
                 "never corroborate each other"),
    "cvc5": SolverBrief(
        engine="cvc5", language="smtlib",
        shapes=("reachability", "bounded-unreachability"),
        budgets={"wall_s": 300},
        certificates={
            "reachability/reachable": UNCHECKABLE,
            "bounded-unreachability/unreachable": UNCHECKABLE,
        },
        lineage=("cvc",),
        intended="cvc5 CLI — verdict-only corroboration; Alethe/LFSC "
                 "proofs are the named future obligation upgrade "
                 "(SOLVERS.md §10)"),
    "yices2": SolverBrief(
        engine="yices2", language="smtlib",
        shapes=("reachability", "bounded-unreachability"),
        budgets={"wall_s": 300},
        certificates={
            "reachability/reachable": UNCHECKABLE,
            "bounded-unreachability/unreachable": UNCHECKABLE,
        },
        lineage=("yices",),
        intended="Yices2 CLI — verdict-only corroboration"),
    "native-btor2": SolverBrief(
        engine="native-btor2", language="btor2",
        shapes=("reachability", "bounded-unreachability"),
        budgets={"wall_s": 300, "bound": "k"},
        certificates={
            "reachability/reachable": {
                "witness": "BTOR2 .wit trace",
                "checker": "shared-interpreter replay "
                           "(languages/btor2.check_witness, "
                           "SOLVERS.md §4)"},
            # kmax exhaustion is a canary-controlled *signal*, not a
            # re-checkable artifact: corroboration territory
            # (corroborate_unreach corroborates — it cannot entail).
            "bounded-unreachability/unreachable": UNCHECKABLE,
        },
        lineage=("boolector", "pono"),
        intended="btormc / pono behind one adapter — BMC for reach, "
                 "canary-controlled -kmax exhaustion for bounded "
                 "unreach; per-binary lineage resolves at run time"),
}
