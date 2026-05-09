"""Reference hand-encoder for condition C — smoke and demonstration.

Condition C (BENCHMARKING.md §3.C) requires the LLM to hand-write its
own encoding into a solver's input language with no help from the
pair. The harness exposes `tool_solve(engine, input_language,
input_text, options)` (in `harness.py`); the question is *whether*
the path is end-to-end functional.

This script answers that without an LLM in the loop. For each task in
a small reference set, it ships a hand-written SMT-LIB encoding of
the question, dispatches through `tool_solve` against `z3`, parses
the verdict back to the corpus vocabulary (sat → reachable, unsat →
unreachable), and compares to `expected_verdict`. It exits non-zero
if any reference encoding produces the wrong verdict — which would
mean either the C path is broken or the encoding is wrong.

The reference set is deliberately small (the simplest tasks where a
straight-line SMT-LIB model is faithful). It is *not* a corpus-wide
condition-C grader; that requires an actual LLM under condition C
(`run_matrix.py --conditions C`). It is a §3.C plumbing check: when
the bench infrastructure is asked to run condition C, does it
produce a verdict the matcher can grade?

Usage::

    python bench/riscv-btor2/condition_c_reference.py
    python bench/riscv-btor2/condition_c_reference.py --json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# Make ``harness.tool_solve`` importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import tool_solve  # type: ignore


# ---------------------------------------------------------------------------
# Reference encodings
# ---------------------------------------------------------------------------
#
# Each entry is one corpus task with a hand-written SMT-LIB encoding
# the LLM under condition C *could* produce. The encoding is "the
# minimum faithful model" — only the registers and operations the
# property mentions. Adding a task here is a vote that this task is
# encodable in pure SMT-LIB without ever consulting `SCHEMA.md`.

REFERENCE: dict[str, dict[str, str]] = {
    "0007-simple-add-baseline": {
        "expected": "reachable",
        "smt2": r"""
            (set-logic QF_BV)
            (declare-const x5  (_ BitVec 64))
            (declare-const x6  (_ BitVec 64))
            (declare-const x10 (_ BitVec 64))
            (assert (= x5  (_ bv5 64)))
            (assert (= x6  (_ bv7 64)))
            (assert (= x10 (bvadd x5 x6)))
            (assert (= x10 (_ bv12 64)))
            (check-sat)
        """,
    },
    "0017-and-baseline": {
        "expected": "reachable",
        "smt2": r"""
            ; addi x5, zero, 0xF0; addi x6, zero, 0x0F; and x10, x5, x6.
            (set-logic QF_BV)
            (declare-const x5  (_ BitVec 64))
            (declare-const x6  (_ BitVec 64))
            (declare-const x10 (_ BitVec 64))
            (assert (= x5  (_ bv240 64)))   ; 0xF0
            (assert (= x6  (_ bv15 64)))    ; 0x0F
            (assert (= x10 (bvand x5 x6)))
            ; Property: can x10 = 0? (sat = reachable.)
            (assert (= x10 (_ bv0 64)))
            (check-sat)
        """,
    },
    "0050-deep-mul-chain": {
        "expected": "reachable",
        "smt2": r"""
            ; nine sequential muls of x10 by x11 = 3 starting at x10 = 2.
            ; final value: 2 * 3^9 = 39366.
            (set-logic QF_BV)
            (declare-const x10_0 (_ BitVec 64))
            (declare-const x11   (_ BitVec 64))
            (declare-const x10_1 (_ BitVec 64))
            (declare-const x10_2 (_ BitVec 64))
            (declare-const x10_3 (_ BitVec 64))
            (declare-const x10_4 (_ BitVec 64))
            (declare-const x10_5 (_ BitVec 64))
            (declare-const x10_6 (_ BitVec 64))
            (declare-const x10_7 (_ BitVec 64))
            (declare-const x10_8 (_ BitVec 64))
            (declare-const x10_9 (_ BitVec 64))
            (assert (= x10_0 (_ bv2 64)))
            (assert (= x11   (_ bv3 64)))
            (assert (= x10_1 (bvmul x10_0 x11)))
            (assert (= x10_2 (bvmul x10_1 x11)))
            (assert (= x10_3 (bvmul x10_2 x11)))
            (assert (= x10_4 (bvmul x10_3 x11)))
            (assert (= x10_5 (bvmul x10_4 x11)))
            (assert (= x10_6 (bvmul x10_5 x11)))
            (assert (= x10_7 (bvmul x10_6 x11)))
            (assert (= x10_8 (bvmul x10_7 x11)))
            (assert (= x10_9 (bvmul x10_8 x11)))
            (assert (= x10_9 (_ bv39366 64)))
            (check-sat)
        """,
    },
}


# ---------------------------------------------------------------------------
# Verdict mapping
# ---------------------------------------------------------------------------


def smt_to_corpus_verdict(smt: str) -> str:
    """Canonical sat/unsat → corpus-verdict mapping for the C path.

    `proved` (an unbounded inductive claim) is not expressible by a
    single satisfiability query without inductive reasoning, so we
    accept `unsat` as confirmation of an `unreachable` *or* `proved`
    expected verdict — same as `framework_oracle.compare`."""
    if smt == "sat":
        return "reachable"
    if smt == "unsat":
        return "unreachable"
    return "unknown"


def verdict_satisfies(expected: str, observed: str) -> bool:
    if observed == "unknown":
        return False
    if expected == "reachable":
        return observed == "reachable"
    if expected in ("unreachable", "proved"):
        return observed in ("unreachable", "proved")
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


# SMT-LIB engines exposed under condition C (in priority order).
# Each engine that's actually present on PATH gets dispatched against
# every reference encoding; engines that are missing are skipped.
SMT2_ENGINES = ("z3", "bitwuzla", "cvc5")


def run_one(task: str, entry: dict[str, str], engine: str) -> dict[str, object]:
    raw = tool_solve(
        engine=engine,
        input_language="smt2",
        input_text=entry["smt2"],
    )
    smt_verdict = raw["verdict"]
    corpus_verdict = smt_to_corpus_verdict(smt_verdict)
    expected = entry["expected"]
    return {
        "task":            task,
        "engine":          engine,
        "expected":        expected,
        "smt_verdict":     smt_verdict,
        "corpus_verdict":  corpus_verdict,
        "elapsed":         raw["elapsed"],
        "passes":          verdict_satisfies(expected, corpus_verdict),
        "stderr":          raw.get("stderr", "")[:200],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Reference hand-encoder smoke test for bench condition C"
    )
    p.add_argument("--json", action="store_true")
    p.add_argument("--task", help="run only one task by id")
    p.add_argument(
        "--engines",
        help=(
            "comma-separated subset of SMT-LIB engines (default: every "
            "engine in {z3, bitwuzla, cvc5} present on PATH)"
        ),
    )
    args = p.parse_args(argv)

    selected: list[str]
    if args.engines:
        selected = [e.strip() for e in args.engines.split(",") if e.strip()]
    else:
        selected = [e for e in SMT2_ENGINES if shutil.which(e) is not None]

    if not selected:
        print(
            "no SMT-LIB CLI present (looked for z3/bitwuzla/cvc5)",
            file=sys.stderr,
        )
        return 2

    items = REFERENCE.items()
    if args.task:
        items = [(k, v) for k, v in items if args.task in k]
        if not items:
            print(f"no reference task matching {args.task!r}", file=sys.stderr)
            return 2

    rows = []
    fail_count = 0
    skip_count = 0
    for task, entry in items:
        for engine in selected:
            if shutil.which(engine) is None:
                rows.append({
                    "task": task, "engine": engine, "passes": True,
                    "smt_verdict": "skip", "corpus_verdict": "skip",
                    "expected": entry["expected"], "elapsed": 0.0,
                    "stderr": f"{engine} not on PATH",
                })
                skip_count += 1
                if not args.json:
                    print(f"SKIP  {task:42s} engine={engine:10s} ({engine} not on PATH)")
                continue
            row = run_one(task, entry, engine)
            rows.append(row)
            if not row["passes"]:
                fail_count += 1
            if not args.json:
                tag = "PASS" if row["passes"] else "FAIL"
                print(
                    f"{tag:5s} {task:42s} engine={engine:10s} "
                    f"expected={row['expected']:11s} "
                    f"smt={row['smt_verdict']:7s} → {row['corpus_verdict']:11s} "
                    f"{row['elapsed']:.2f}s"
                )

    if args.json:
        json.dump(
            {"rows": rows, "failures": fail_count, "skipped": skip_count},
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    elif fail_count:
        print(f"\n{fail_count} reference encoding(s) failed", file=sys.stderr)

    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
