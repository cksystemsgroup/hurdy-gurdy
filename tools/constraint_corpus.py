#!/usr/bin/env python3
"""The constrained-corpus benchmark: BTOR2 ``constraint`` enforcement
decided three ways, in both verdict polarities (SOLVERS.md §4/§7;
BENCHMARKS.md §6; the first post-snapshot benchmark family named by the
paper's evaluation exhibits).

Nine authored constrained systems with by-construction ground truth,
each decided by

* the **native checker** — btormc, bounded, canary-controlled exhaustion
  (``solvers/native_btor2``);
* the **bridged engine** — the per-frame SMT encoding through
  ``btor2-smtlib`` and z3 (``pairs/btor2_smtlib.reach``);
* the **shared evaluator** — witness replay for reachable ground truth
  (both the bridged model's carry-back and btormc's ``.wit`` replayed
  through the strict interpreter), seeded-run corroboration
  (``corroborate_unreach``) for unreachable ground truth. The evaluator
  corroborates; it does not decide.

Three structural controls ride along:

* **masking** — the historical *global* constraint reading (constraints
  asserted over ``0..k`` instead of per frame), kept here as an
  instrument, must mask the valid-prefix reach that the per-frame
  reading and the native checker both find;
* **additive** — a vacuously-true constraint must not change the
  verdict of its constraint-free sibling;
* **blocking** — removing the constraint from the constraint-blocked
  system must flip its verdict back to reachable.

RAM discipline: every system is tiny (a 4-bit counter or a 1-bit
input; at most two constraints) and all runs are sequential.
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gurdy.core.solver import Verdict                        # noqa: E402
from gurdy.languages.btor2.build import Builder              # noqa: E402
from gurdy.languages.btor2.model import from_text            # noqa: E402
from gurdy.languages.btor2.witness import (                  # noqa: E402
    check_witness,
    corroborate_unreach,
)
from gurdy.pairs.btor2_smtlib import reach, translate        # noqa: E402
from gurdy.solvers.native_btor2 import (                     # noqa: E402
    NativeBtor2Checker,
    find_btormc,
)

# The package __init__ binds the *function* ``translate``; the module
# (whose deterministic naming the masking instrument reuses) is fetched
# explicitly.
_tmod = importlib.import_module("gurdy.pairs.btor2_smtlib.translate")


def _counter(limit: int | None, bad_at: int, neq: int | None = None,
             vacuous: bool = False) -> str:
    """A 4-bit counter from 0; ``bad`` iff it equals ``bad_at``;
    constrained below ``limit`` (and, optionally, ``!= neq``); or under a
    constant-true constraint (``vacuous``); or constraint-free."""
    b = Builder()
    c = b.state(4, "c")
    b.init(c, b.zero(4))
    b.next(c, b.op2("add", 4, c, b.one(4)))
    if limit is not None:
        b.constraint(b.op2("ult", 1, c, b.constd(4, limit)))
    if neq is not None:
        b.constraint(b.op1("not", 1, b.op2("eq", 1, c, b.constd(4, neq))))
    if vacuous:
        b.constraint(b.one(1))
    b.bad(b.op2("eq", 1, c, b.constd(4, bad_at)))
    return b.to_text()


# 1-bit input systems, literal for legibility: the constraint requires
# g = 1; the bad reads g (reachable through the constraint) or ¬g
# (unreachable only *because of* the constraint).
_INPUT_THROUGH = "1 sort bitvec 1\n2 input 1 g\n3 constraint 2\n4 bad 2\n"
_INPUT_BLOCKED = "1 sort bitvec 1\n2 input 1 g\n3 constraint 2\n4 not 1 2\n5 bad 4\n"
_INPUT_FREE = "1 sort bitvec 1\n2 input 1 g\n3 not 1 2\n4 bad 3\n"


def build_corpus() -> list[dict[str, Any]]:
    """The nine constrained systems, ground truth by construction."""
    return [
        {"name": "valid-prefix-reach", "k": 5, "truth": "reachable",
         "text": _counter(3, 2),
         "note": "bad at step 2 on a valid prefix; every run violates at 3"
                 " (the masking shape)"},
        {"name": "two-guards-reach", "k": 6, "truth": "reachable",
         "text": _counter(5, 2, neq=3),
         "note": "two constraints; bad before either is violated"},
        {"name": "late-window-reach", "k": 8, "truth": "reachable",
         "text": _counter(6, 4),
         "note": "bad at step 4 inside a longer valid window"},
        {"name": "vacuous-constraint", "k": 4, "truth": "reachable",
         "text": _counter(None, 2, vacuous=True),
         "note": "constant-true constraint (the additive control's"
                 " constrained half)"},
        {"name": "constrained-input-reach", "k": 2, "truth": "reachable",
         "text": _INPUT_THROUGH,
         "note": "bad reachable only through the constrained input value"},
        {"name": "constraint-blocked-input", "k": 3, "truth": "unreachable",
         "text": _INPUT_BLOCKED,
         "note": "bad unreachable only because of the constraint"},
        {"name": "truncated-before-bad", "k": 12, "truth": "unreachable",
         "text": _counter(3, 10),
         "note": "the constraint truncates every run before the bad"},
        {"name": "invalid-row-bad", "k": 5, "truth": "unreachable",
         "text": _counter(2, 2),
         "note": "bad fires exactly on the violating row (not a reach)"},
        {"name": "bound-scoped-unreach", "k": 1, "truth": "unreachable",
         "text": _counter(3, 2),
         "note": "the reach lies beyond the declared bound"},
    ]


def global_encoding(text: str, k: int) -> bytes:
    """The historical *global* constraint reading, as an instrument: the
    pair's own emission with its per-frame reach assertion swapped for
    constraints asserted over all of ``0..k`` plus a bare bad
    disjunction. This is the encoding the per-frame fix replaced
    (``pairs/btor2_smtlib/translate.py``); it is kept only to measure
    what it masks."""
    script = translate({"system": text, "k": k}).decode("utf-8")
    lines = script.rstrip("\n").split("\n")
    if lines[-1] != "(check-sat)" or not lines[-2].startswith("(assert"):
        raise AssertionError("unexpected emission tail: %r" % lines[-2:])
    sys_ = from_text(text)
    cons = [n for n in sys_.nodes.values() if n.op == "constraint"]
    if not cons:
        raise AssertionError("global_encoding needs a constrained system")
    glob = [f"(assert (= {_tmod._name(sys_, cn.refs[0], t)} #b1))"
            for cn in cons for t in range(k + 1)]
    disj = [f"(= {_tmod._name(sys_, bn.refs[0], t)} #b1)"
            for bn in sys_.bads() for t in range(k + 1)]
    bad = (f"(assert (or {' '.join(disj)}))" if len(disj) > 1
           else f"(assert {disj[0]})")
    return ("\n".join(lines[:-2] + glob + [bad, "(check-sat)"]) + "\n").encode("utf-8")


def _decide_global(text: str, k: int) -> Verdict:
    from gurdy.solvers.z3_smt import Z3SmtBackend

    return Z3SmtBackend().decide(global_encoding(text, k)).verdict


def _verdict_str(v: Verdict) -> str:
    return v.name.lower()


def run_experiment() -> dict[str, Any]:
    """Run the corpus through all three deciders and the three controls.
    Requires btormc and z3 (the caller gates)."""
    checker = NativeBtor2Checker()
    rows: list[dict[str, Any]] = []
    for entry in build_corpus():
        text, k, truth = entry["text"], entry["k"], entry["truth"]
        bridged = reach(text, k)
        bridged_v = bridged["verdict"]
        if truth == "reachable":
            native_v, wit = checker.decide_witness(text, k)
            native_replay = bool(wit) and check_witness(text, wit, k=k)
            evaluator_ok = bool(bridged.get("witness_ok")) and native_replay
            evaluator = "replay"
        else:
            native_v = checker.decide_bounded(text, k)
            evaluator_ok = corroborate_unreach(text, k)
            evaluator = "no bad"
        rows.append({
            "name": entry["name"], "k": k, "truth": truth,
            "note": entry["note"],
            "native": _verdict_str(native_v),
            "bridged": _verdict_str(bridged_v),
            "evaluator": evaluator,
            "evaluator_ok": evaluator_ok,
            "agree": (_verdict_str(native_v) == truth
                      and _verdict_str(bridged_v) == truth
                      and evaluator_ok),
        })

    masking_target = next(e for e in build_corpus()
                          if e["name"] == "valid-prefix-reach")
    global_v = _decide_global(masking_target["text"], masking_target["k"])
    plain = _counter(None, 2)
    controls = {
        # The defective reading must answer unreachable where per-frame
        # and native answer reachable: the reach masked, measured.
        "masking": {
            "system": "valid-prefix-reach",
            "global": _verdict_str(global_v),
            "per_frame": next(r["bridged"] for r in rows
                              if r["name"] == "valid-prefix-reach"),
            "masked": global_v is Verdict.UNREACHABLE,
        },
        # A constant-true constraint must not move the verdict.
        "additive": {
            "constrained": next(r["bridged"] for r in rows
                                if r["name"] == "vacuous-constraint"),
            "plain": _verdict_str(reach(plain, 4)["verdict"]),
        },
        # Removing the constraint must flip the blocked system.
        "blocking": {
            "constrained": next(r["bridged"] for r in rows
                                if r["name"] == "constraint-blocked-input"),
            "freed": _verdict_str(reach(_INPUT_FREE, 3)["verdict"]),
        },
    }
    controls["additive"]["ok"] = (controls["additive"]["constrained"]
                                  == controls["additive"]["plain"]
                                  == "reachable")
    controls["blocking"]["ok"] = (controls["blocking"]["constrained"]
                                  == "unreachable"
                                  and controls["blocking"]["freed"]
                                  == "reachable")
    counts = {
        "systems": len(rows),
        "reachable": sum(r["truth"] == "reachable" for r in rows),
        "unreachable": sum(r["truth"] == "unreachable" for r in rows),
        "agree": sum(r["agree"] for r in rows),
        "controls_ok": (controls["masking"]["masked"]
                        and controls["additive"]["ok"]
                        and controls["blocking"]["ok"]),
    }
    return {"rows": rows, "controls": controls, "counts": counts}


def main() -> int:
    if not find_btormc():
        print("constraint corpus: btormc unavailable — cannot run")
        return 1
    report = run_experiment()
    for row in report["rows"]:
        print(f"{row['name']:26s} k={row['k']:<3d} truth={row['truth']:11s} "
              f"native={row['native']:11s} bridged={row['bridged']:11s} "
              f"evaluator={row['evaluator']}({'ok' if row['evaluator_ok'] else 'FAIL'}) "
              f"{'agree' if row['agree'] else 'DISAGREE'}")
    print("controls:", report["controls"])
    print("counts:", report["counts"])
    ok = (report["counts"]["agree"] == report["counts"]["systems"]
          and report["counts"]["controls_ok"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
