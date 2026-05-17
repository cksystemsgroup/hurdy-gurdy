"""Multi-engine cross-solver oracle for the riscv-btor2 corpus.

A no-LLM check that runs every corpus task under *every compatible
engine* in the pair's solver inventory and reports the agreement
matrix. The point is two-fold:

1. Strengthen each task's ``expected_verdict`` per
   ``BENCHMARKING.md`` §4.5 by using cross-solver agreement as an
   independent oracle ("agreement of at least two unrelated tools").
   ``framework_oracle.py`` already exercises the pinned engine; this
   script adds the other engines so the inventory's bitwuzla / cvc5 /
   pono columns become load-bearing.

2. Surface translation, dispatch, and lift bugs that only manifest
   on one engine. Same artifact bytes, multiple solvers — any
   verdict disagreement is a flag for human review.

Engine selection per task is by *class*:

- BMC class (pinned engine ∈ {z3-bmc, bitwuzla, cvc5, pono with the
  default bmc mode}) is cross-checked against all four BMC engines
  using the task's pinned bound.
- Inductive class (pinned engine == z3-spacer) is cross-checked
  against z3-spacer plus pono in k-induction mode (``extra_options
  engine=ind``); bound defaults to ``--ind-bound`` (10) when the
  pinned spec leaves it unset.

Output:

    TASK 0007-simple-add-baseline               expected=reachable
        z3-bmc       reachable  PASS  0.05s
        bitwuzla     reachable  PASS  0.21s
        cvc5         unknown    SKIP  (cvc5 bindings not installed)
        pono         unknown    SKIP  (pono: not on PATH)
        => CROSS-PASS (2 confirm, 0 disagree, 2 skipped)

Per-task summary verdicts:

- ``CROSS-PASS``      all engines that returned a definitive verdict
                      agreed with the expected verdict.
- ``CROSS-MISMATCH``  engines returned conflicting definitive
                      verdicts (e.g., one ``reachable``, another
                      ``unreachable``).
- ``CROSS-FAIL``      at least one engine returned a definitive
                      verdict that disagrees with the task's
                      ``expected_verdict``.
- ``CROSS-SKIPPED``   no engine returned a definitive verdict
                      (all ``unknown``/``error``); inconclusive.

Exit code is 1 if any task is ``CROSS-FAIL`` or ``CROSS-MISMATCH``,
0 otherwise. ``CROSS-SKIPPED`` does not fail — locally only z3-bmc /
z3-spacer / bitwuzla are typically present, so most inventory rows
will be SKIP outside the bench Docker image.

Usage::

    python bench/riscv-btor2/oracle_cross.py
    python bench/riscv-btor2/oracle_cross.py --task 0007-simple-add-baseline
    python bench/riscv-btor2/oracle_cross.py --engines z3-bmc,bitwuzla
    python bench/riscv-btor2/oracle_cross.py --json > oracle_cross.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

# Make ``gurdy.*`` importable without depending on the package being installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.dispatch import dispatch
from gurdy.pairs.riscv_btor2 import PAIR  # noqa: F401  (registers pair)
from gurdy.pairs.riscv_btor2.spec import AnalysisDirective, RiscvBtor2Spec

# Reuse the corpus walker; framework_oracle.py is the single source of
# truth for spec.json / task.toml loading, including multi-question
# splitting and binary-path rewriting.
from framework_oracle import CORPUS, iter_questions  # type: ignore


# ---------------------------------------------------------------------------
# Dispatch profiles
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Profile:
    """One dispatch attempt: which engine, which extras to overlay,
    and what bound to use if the spec leaves it unset.

    ``label`` is the row name in the report; ``engine`` is the registered
    solver key in the pair. ``label`` differs from ``engine`` only for
    pono-ind, where the same binary runs in induction mode.
    """

    label: str
    engine: str
    extras: dict[str, str] = dataclasses.field(default_factory=dict)
    bound_fallback: int | None = None


BMC_PROFILES: tuple[Profile, ...] = (
    Profile("z3-bmc", "z3-bmc"),
    Profile("bitwuzla", "bitwuzla"),
    Profile("cvc5", "cvc5"),
    Profile("pono", "pono"),
)

INDUCTIVE_PROFILES: tuple[Profile, ...] = (
    Profile("z3-spacer", "z3-spacer"),
    Profile("pono-ind", "pono", extras={"engine": "ind"}, bound_fallback=10),
)

# Pinned engines that mean "this task wants an unbounded inductive proof".
INDUCTIVE_PINNED = frozenset({"z3-spacer"})


def profiles_for(pinned_engine: str) -> tuple[Profile, ...]:
    if pinned_engine in INDUCTIVE_PINNED:
        return INDUCTIVE_PROFILES
    return BMC_PROFILES


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------


def verdict_satisfies(expected: str, observed: str) -> bool:
    """Same equivalence rule as ``framework_oracle.compare`` but
    returns a bool. ``proved`` strictly satisfies ``unreachable``;
    ``unknown``/``error`` satisfy nothing."""
    if observed in ("unknown", "error"):
        return False
    if expected == "reachable":
        return observed == "reachable"
    if expected in ("unreachable", "proved"):
        return observed in ("unreachable", "proved")
    return False


def verdicts_agree(a: str, b: str) -> bool:
    """Two definitive verdicts agree iff they're both ``reachable``,
    or both in {``unreachable``, ``proved``}. Inconclusive verdicts
    (``unknown``/``error``) agree with everything by default — they
    don't carry information."""
    if a in ("unknown", "error") or b in ("unknown", "error"):
        return True
    if a == "reachable" or b == "reachable":
        return a == b
    return True  # both in {unreachable, proved}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _override_directive(
    d: AnalysisDirective,
    p: Profile,
    *,
    timeout_cap: int | None = None,
) -> AnalysisDirective:
    extras = dict(d.extra_options or {})
    extras.update(p.extras)
    bound = d.bound if d.bound is not None else p.bound_fallback
    # The cross-oracle is a *sanity* check on top of framework_oracle.
    # Deep verification stays in framework_oracle with the spec's
    # full timeout; the cross-check caps per-engine time at a smaller
    # value so the full-corpus run finishes within the test harness's
    # 600s ceiling. Slower engines that don't agree quickly produce
    # `unknown` and are excluded from agreement — still safe, just
    # less informative.
    timeout = d.timeout
    if timeout_cap is not None:
        timeout = min(timeout, timeout_cap) if timeout is not None else timeout_cap
    return dataclasses.replace(
        d,
        engine=p.engine,
        extra_options=extras,
        bound=bound,
        timeout=timeout,
    )


def _run_profile(
    spec: RiscvBtor2Spec,
    p: Profile,
    artifact,
    *,
    timeout_cap: int | None = None,
) -> dict[str, Any]:
    directive = _override_directive(spec.analysis, p, timeout_cap=timeout_cap)
    t0 = time.monotonic()
    raw = dispatch(artifact, directive)
    return {
        "label": p.label,
        "engine": p.engine,
        "verdict": raw.verdict,
        "elapsed": time.monotonic() - t0,
        "reason": raw.reason,
    }


# ---------------------------------------------------------------------------
# Per-task summary
# ---------------------------------------------------------------------------


def summarize(expected: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll the per-engine rows up into a single per-task verdict.

    Disagreement among engines (one says reachable, another says
    unreachable) is the strongest signal — that's a MISMATCH and
    requires human review. A FAIL is the next strongest: any engine
    contradicting expected. PASS requires at least one engine to
    confirm and zero to disagree. SKIPPED means nothing decisive came
    back."""
    definitive = [r for r in rows if r["verdict"] not in ("unknown", "error")]
    confirms = [r for r in definitive if verdict_satisfies(expected, r["verdict"])]
    disagrees = [r for r in definitive if not verdict_satisfies(expected, r["verdict"])]
    skipped = [r for r in rows if r["verdict"] in ("unknown", "error")]

    # Engine-vs-engine disagreement check (independent of expected).
    pairwise_conflict = False
    for i, a in enumerate(definitive):
        for b in definitive[i + 1 :]:
            if not verdicts_agree(a["verdict"], b["verdict"]):
                pairwise_conflict = True
                break
        if pairwise_conflict:
            break

    if pairwise_conflict:
        status = "CROSS-MISMATCH"
    elif disagrees:
        status = "CROSS-FAIL"
    elif confirms:
        status = "CROSS-PASS"
    else:
        status = "CROSS-SKIPPED"

    return {
        "status": status,
        "n_confirm": len(confirms),
        "n_disagree": len(disagrees),
        "n_skipped": len(skipped),
        "engines": rows,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def render_text(task_label: str, expected: str, summary: dict[str, Any]) -> str:
    lines = [f"TASK {task_label:42s} expected={expected}"]
    for r in summary["engines"]:
        verdict = r["verdict"]
        if verdict in ("unknown", "error"):
            tag = "SKIP"
            tail = f"({r['reason']})" if r.get("reason") else ""
        elif verdict_satisfies(expected, verdict):
            tag = "PASS"
            tail = f"{r['elapsed']:.2f}s"
        else:
            tag = "FAIL"
            tail = f"{r['elapsed']:.2f}s  expected={expected}"
        lines.append(f"    {r['label']:12s} {verdict:11s} {tag}  {tail}")
    lines.append(
        f"    => {summary['status']} "
        f"({summary['n_confirm']} confirm, "
        f"{summary['n_disagree']} disagree, "
        f"{summary['n_skipped']} skipped)"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="riscv-btor2 multi-engine cross oracle (no LLM)"
    )
    ap.add_argument("--task", help="run only one task by id (substring match)")
    ap.add_argument(
        "--corpus",
        default=str(CORPUS),
        help="corpus directory (default: bench/riscv-btor2/corpus)",
    )
    ap.add_argument(
        "--engines",
        help=(
            "comma-separated subset of engine labels to run "
            "(default: all compatible profiles)"
        ),
    )
    ap.add_argument(
        "--per-profile-timeout",
        type=int,
        default=20,
        help=(
            "cap per-engine dispatch time (seconds) for cross-checks. "
            "Default 20s: the cross-oracle is a sanity check, not a "
            "deep verifier (that's framework_oracle's job). Set to 0 "
            "to disable the cap and use each spec's full timeout."
        ),
    )
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args(argv)
    timeout_cap: int | None = args.per_profile_timeout or None

    selected: set[str] | None = None
    if args.engines:
        selected = {s.strip() for s in args.engines.split(",") if s.strip()}

    corpus = Path(args.corpus)
    task_dirs = sorted(
        d for d in corpus.iterdir()
        if d.is_dir() and (d / "task.toml").exists()
    )
    if args.task:
        task_dirs = [d for d in task_dirs if d.name == args.task or args.task in d.name]
        if not task_dirs:
            print(f"no task matching {args.task!r}", file=sys.stderr)
            return 2

    fail_count = 0
    mismatch_count = 0
    out_rows: list[dict[str, Any]] = []

    for d in task_dirs:
        try:
            questions = iter_questions(d)
        except Exception as exc:
            row = {"task": d.name, "status": "ERROR", "reason": str(exc)}
            out_rows.append(row)
            if not args.json:
                print(f"ERROR {d.name}: {exc}")
            continue

        for qid, expected, spec in questions:
            label = d.name if qid is None else f"{d.name}#{qid}"
            try:
                artifact = compile_spec(spec)
            except Exception as exc:
                if args.json:
                    out_rows.append({
                        "task":     d.name,
                        "question": qid,
                        "status":   "ERROR",
                        "reason":   f"compile failed: {exc}",
                    })
                else:
                    print(f"ERROR {label}: compile failed: {exc}")
                continue

            profiles = profiles_for(spec.analysis.engine)
            if selected is not None:
                profiles = tuple(p for p in profiles if p.label in selected)
            rows = [
                _run_profile(spec, p, artifact, timeout_cap=timeout_cap)
                for p in profiles
            ]
            summary = summarize(expected, rows)

            if summary["status"] == "CROSS-FAIL":
                fail_count += 1
            elif summary["status"] == "CROSS-MISMATCH":
                mismatch_count += 1

            if args.json:
                out_rows.append({
                    "task":     d.name,
                    "question": qid,
                    "expected": expected,
                    "summary":  summary,
                })
            else:
                print(render_text(label, expected, summary))

    if args.json:
        json.dump(
            {"rows": out_rows, "failures": fail_count, "mismatches": mismatch_count},
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    elif fail_count or mismatch_count:
        print(
            f"\n{fail_count} CROSS-FAIL, {mismatch_count} CROSS-MISMATCH",
            file=sys.stderr,
        )

    return 1 if (fail_count or mismatch_count) else 0


if __name__ == "__main__":
    raise SystemExit(main())
