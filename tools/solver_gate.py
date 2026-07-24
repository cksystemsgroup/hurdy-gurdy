#!/usr/bin/env python3
"""The solver admission gate (SYNTHESIS.md §5): what a candidate engine
must clear before an inventory believes it.

A candidate is a *decider* — ``(btor2_text, k) -> Verdict`` — and the
gate never trusts it: it falsifies. Four checks, each the solver-side
analogue of one the pairs already clear (SCALING.md §12):

* **Census replay.** Every entry of a ground-truth corpus is
  re-decided. A verdict that contradicts the recorded truth fails
  admission outright; ``unknown`` / ``resource-out`` are *abstentions*
  — recorded, counted, never failing (the gate admits sound-and-slow;
  the books price it). The shipped census is the constrained-systems
  corpus (``tools/constraint_corpus.py``: by-construction truth, both
  polarities); a saturation campaign's own solved region is the
  intended corpus at scale.
* **Two-sided canaries.** A trivially reachable system must read
  ``reachable`` and a trivially unreachable one ``unreachable`` —
  strictly, no abstaining on the trivial case. This is the
  SOLVERS.md §5 adapter rule ("an adapter without a negative control
  is itself unchecked"), generalized from the exhaustion signal of
  ``solvers/native_btor2`` to any candidate, in both polarities.
* **Verdict-flip mutants.** Census entries are mutated so the ground
  truth provably flips — ``mask_bads`` (every bad replaced by one that
  never fires: reachable → unreachable, unconditionally sound) and
  ``force_bad`` (an always-firing bad added: unreachable → reachable,
  sound whenever a constraint-valid row exists within the bound, which
  the shipped census guarantees). A candidate that repeats the old
  verdict on a flipped instance is contradicted; one that abstains
  passes weakly, and the report says so. A candidate that cannot be
  made to change its answer is not checked — it is unfalsifiable.
* **Twice-and-diff (opt-in).** With ``runs >= 2`` every decision is
  repeated and verdicts must match. External engines are admitted
  non-deterministic (SOLVERS.md §1) and gate with ``runs=1``; a
  synthesized pure-Python procedure has no such excuse and gates with
  ``runs=2`` (SYNTHESIS.md §6 — the newest authors get the strictest
  gate).

Admission is the conjunction: canaries strict, zero census
disagreements, zero flip contradictions, and — when determinism is
demanded — zero verdict diffs. Everything else (abstentions, weak
flips, per-decision seconds) is reported, not judged: that is cost
evidence for the books, not admission evidence.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gurdy.core.solver import Verdict                        # noqa: E402

Decider = Callable[[str, int], Verdict]

# The canary pair: the same one-node skeleton with the constant
# flipped — bad on constant one (reachable at step 0) vs bad on
# constant zero (unreachable at every step). The reachable half is
# solvers/native_btor2's exhaustion canary, verbatim.
CANARY_REACH = "1 sort bitvec 1\n2 one 1\n3 bad 2\n"
CANARY_UNREACH = "1 sort bitvec 1\n2 zero 1\n3 bad 2\n"

#: verdicts that count as an abstention, never a lie
_ABSTAIN = (Verdict.UNKNOWN, Verdict.RESOURCE_OUT)


def _ids(text: str) -> list[int]:
    out = []
    for line in text.splitlines():
        tok = line.split()
        if tok and tok[0].isdigit():
            out.append(int(tok[0]))
    return out


def mask_bads(text: str) -> str:
    """The reachable→unreachable mutant: every ``bad`` line is dropped
    (bads are sinks — nothing references them) and one fresh bad on a
    constant zero is appended. Sound unconditionally: the remaining bad
    can never fire, so the system is unreachable within any bound."""
    kept = [ln for ln in text.splitlines()
            if not (ln.split() and ln.split()[0].isdigit()
                    and len(ln.split()) > 1 and ln.split()[1] == "bad")]
    m = max(_ids(text), default=0)
    kept += [f"{m + 1} sort bitvec 1", f"{m + 2} zero {m + 1}",
             f"{m + 3} bad {m + 2}"]
    return "\n".join(kept) + "\n"


def force_bad(text: str) -> str:
    """The unreachable→reachable mutant: an always-firing bad is
    appended. Sound iff some constraint-valid row exists within the
    bound — true by construction for the shipped census; a caller
    supplying a corpus owns that check for its own entries."""
    m = max(_ids(text), default=0)
    return (text.rstrip("\n") + "\n"
            + f"{m + 1} sort bitvec 1\n{m + 2} one {m + 1}\n"
            + f"{m + 3} bad {m + 2}\n")


def default_census() -> list[dict[str, Any]]:
    """The constrained-systems corpus as the built-in census:
    ``{name, text, k, truth}`` with by-construction ground truth."""
    import constraint_corpus

    return [{"name": e["name"], "text": e["text"], "k": e["k"],
             "truth": e["truth"]} for e in constraint_corpus.build_corpus()]


@dataclass(frozen=True)
class GateReport:
    """The gate's verdict on one candidate. ``admitted`` is the
    conjunction of the falsification checks; the rest is evidence."""
    candidate: str
    runs: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    disagreements: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    nondeterministic: list[str] = field(default_factory=list)
    abstained: int = 0
    strong_flips: dict[str, int] = field(default_factory=dict)
    canaries_ok: bool = False
    admitted: bool = False


def _decide(decider: Decider, text: str, k: int, runs: int) -> dict[str, Any]:
    verdicts, err, t0 = [], None, time.monotonic()
    for _ in range(max(1, runs)):
        try:
            verdicts.append(decider(text, k))
        except Exception as exc:                       # a crash is an
            verdicts.append(Verdict.UNKNOWN)           # abstention with
            err = f"{type(exc).__name__}: {exc}"       # its reason kept
    row = {"verdicts": [v.value for v in verdicts],
           "verdict": verdicts[0],
           "seconds": round(time.monotonic() - t0, 4),
           "diverged": len(set(verdicts)) > 1}
    if err:
        row["error"] = err
    return row


def gate(decider: Decider, corpus: list[dict[str, Any]] | None = None, *,
         candidate: str = "candidate", runs: int = 1) -> GateReport:
    """Run the admission gate on ``decider`` against ``corpus``
    (default: the constrained-systems census). ``runs >= 2`` demands
    verdict-level determinism (twice-and-diff)."""
    corpus = default_census() if corpus is None else corpus
    rows: list[dict[str, Any]] = []
    disagreements: list[str] = []
    contradictions: list[str] = []
    nondet: list[str] = []
    abstained = 0
    strong = {"masked": 0, "forced": 0}

    def push(name: str, kind: str, truth: str, text: str, k: int) -> None:
        nonlocal abstained
        row = {"name": name, "kind": kind, "truth": truth, "k": k,
               **_decide(decider, text, k, runs)}
        v = row["verdict"]
        if row.pop("diverged"):
            nondet.append(name)
            row["outcome"] = "nondeterministic"
        elif kind in ("census", "canary"):
            if v in _ABSTAIN:
                abstained += 1
                row["outcome"] = "abstain"
            elif v.value == truth:
                row["outcome"] = "agree"
            else:
                disagreements.append(name)
                row["outcome"] = "disagree"
        else:                                   # a flipped instance
            if v in _ABSTAIN:
                row["outcome"] = "weak"
            elif v.value == truth:
                strong["masked" if kind == "flip-masked" else "forced"] += 1
                row["outcome"] = "strong"
            else:
                contradictions.append(name)
                row["outcome"] = "contradiction"
        rows.append(row)

    push("canary-reach", "canary", "reachable", CANARY_REACH, 1)
    push("canary-unreach", "canary", "unreachable", CANARY_UNREACH, 1)
    for e in corpus:
        push(e["name"], "census", e["truth"], e["text"], e["k"])
        if e["truth"] == "reachable":
            push(e["name"] + "@masked", "flip-masked", "unreachable",
                 mask_bads(e["text"]), e["k"])
        else:
            push(e["name"] + "@forced", "flip-forced", "reachable",
                 force_bad(e["text"]), e["k"])

    canaries_ok = all(r["outcome"] == "agree"
                      for r in rows if r["kind"] == "canary")
    admitted = (canaries_ok and not disagreements and not contradictions
                and (runs < 2 or not nondet))
    return GateReport(candidate=candidate, runs=runs, rows=rows,
                      disagreements=disagreements,
                      contradictions=contradictions,
                      nondeterministic=nondet, abstained=abstained,
                      strong_flips=strong, canaries_ok=canaries_ok,
                      admitted=admitted)


# -- adapters: registered engine families, normalized to a Decider ----------

def native_decider(checker: Any = None) -> Decider:
    """The native composite: BMC for the reachable half, btormc's
    canary-controlled ``-kmax`` exhaustion for the bounded-unreachable
    half (``solvers/native_btor2``)."""
    from gurdy.solvers.native_btor2 import NativeBtor2Checker

    checker = checker or NativeBtor2Checker()

    def decide(text: str, k: int) -> Verdict:
        v = checker.decide(text, k)
        if v is Verdict.REACHABLE:
            return v
        return checker.decide_bounded(text, k)

    return decide


def pono_decider(checker: Any = None) -> Decider:
    """The unbounded composite behind the ``pono`` brief
    (solvers/pono_btor2.py): BMC at the census bound for the reachable
    half, then the declared ``UNBOUNDED_MODES`` portfolio for the
    unreachable half — an unbounded proof entails every bounded claim. A ``sat`` from an
    unbounded mode after BMC cleared the bound is a counterexample
    *beyond* the census bound: about the bounded truth it says
    nothing, so the decider abstains rather than contradict."""
    import subprocess

    from gurdy.solvers.pono_btor2 import (UNBOUNDED_FRAMES,
                                          UNBOUNDED_MODES,
                                          PonoBtor2Checker)

    checker = checker or PonoBtor2Checker()

    def decide(text: str, k: int) -> Verdict:
        try:
            v, _ = checker.decide(text, mode="bmc", k=k)
        except subprocess.TimeoutExpired:
            return Verdict.RESOURCE_OUT
        if v is Verdict.REACHABLE:
            return v
        for mode in UNBOUNDED_MODES:
            try:
                u, _ = checker.decide(text, mode=mode, k=UNBOUNDED_FRAMES)
            except subprocess.TimeoutExpired:
                continue
            if u is Verdict.UNREACHABLE:
                return u
            if u is Verdict.REACHABLE:
                return Verdict.UNKNOWN   # beyond the bound: abstain
        return Verdict.UNKNOWN

    return decide


def bridged_decider(backend: Any = None) -> Decider:
    """The bridge: ``btor2-smtlib``'s per-frame encoding decided by an
    SMT backend (default z3); ``sat`` is reachable, ``unsat`` the
    bounded-unreachable claim."""
    from gurdy.pairs.btor2_smtlib import translate
    from gurdy.solvers.z3_smt import Z3SmtBackend

    backend = backend or Z3SmtBackend()

    def decide(text: str, k: int) -> Verdict:
        return backend.decide(translate({"system": text, "k": k})).verdict

    return decide


def render(report: GateReport) -> str:
    lines = [f"solver gate: {report.candidate} (runs={report.runs})"]
    for r in report.rows:
        lines.append(f"  {r['name']:34s} {r['kind']:11s} "
                     f"truth={r['truth']:11s} got={r['verdict'].value:12s} "
                     f"{r['outcome']:16s} {r['seconds']:.3f}s")
    lines.append(f"  abstained={report.abstained} "
                 f"strong_flips={report.strong_flips} "
                 f"disagreements={report.disagreements or 'none'} "
                 f"contradictions={report.contradictions or 'none'} "
                 f"nondeterministic={report.nondeterministic or 'none'}")
    lines.append(f"  {'ADMITTED' if report.admitted else 'NOT ADMITTED'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--engine", default="native",
                    help="native | pono | z3 | one of the CLI SMT "
                         "engine ids")
    ap.add_argument("--runs", type=int, default=1,
                    help=">=2 additionally demands verdict determinism")
    args = ap.parse_args(argv)

    if args.engine == "native":
        from gurdy.solvers.native_btor2 import find_btormc
        if not find_btormc():
            print("solver gate: btormc unavailable — cannot run")
            return 1
        decider = native_decider()
    elif args.engine == "pono":
        from gurdy.solvers.pono_btor2 import find_pono
        if not find_pono():
            print("solver gate: pono unavailable — cannot run")
            return 1
        decider = pono_decider()
    elif args.engine == "z3":
        decider = bridged_decider()
    else:
        from gurdy.solvers import inventory
        backend = next((b for b in inventory.available_smt_backends()
                        if b.id == args.engine), None)
        if backend is None:
            print(f"solver gate: engine {args.engine!r} unavailable")
            return 1
        decider = bridged_decider(backend)

    report = gate(decider, candidate=args.engine, runs=args.runs)
    print(render(report))
    return 0 if report.admitted else 1


if __name__ == "__main__":
    sys.exit(main())
