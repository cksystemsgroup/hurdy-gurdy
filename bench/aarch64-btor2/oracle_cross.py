"""Multi-engine cross-solver oracle for the aarch64-btor2 corpus.

P10 implementation — port of bench/riscv-btor2/oracle_cross.py (main).
Key AArch64 adaptations vs the riscv version:

- No framework_oracle.py: task loading is inline (task.toml + spec.json).
- Tasks without source.elf are SKIP rows (cross-toolchain unavailable);
  they do not count as failures — only seed 0001 has an ELF right now.
- No pono-docker / pono-ind-docker profiles (not registered for this pair).
- No certificate re-verification (bmc_certificate / kind_certificate not
  yet ported for aarch64).
- Compilation (ELF → BTOR2) is done once per task; dispatch runs per profile.

Engine selection per task is by class:

- BMC class (pinned engine ∈ {z3-bmc, bitwuzla, cvc5, pono}) is
  cross-checked against all four BMC profiles using the task's bound.
- Inductive class (pinned engine == z3-spacer) is cross-checked against
  z3-spacer plus pono in k-induction mode.

Output::

    TASK 0001-c-loopsum-o0                     expected=unreachable
        z3-bmc           unreachable PASS  2.30s
        bitwuzla         unknown     SKIP  (bitwuzla: not on PATH)
        cvc5             unknown     SKIP  (cvc5 bindings not installed)
        pono             unknown     SKIP  (pono: not on PATH)
        => CROSS-PASS (1 confirm, 0 disagree, 3 skipped)

    SKIP 0002-c-loopsum-o1: no source.elf (cross-toolchain unavailable)

Per-task summary verdicts:

- CROSS-PASS      all engines that returned a definitive verdict agreed.
- CROSS-MISMATCH  engines returned conflicting definitive verdicts.
- CROSS-FAIL      at least one engine disagrees with expected_verdict.
- CROSS-SKIPPED   no engine returned a definitive verdict (all unknown/error).

SKIP rows (no source.elf or no spec.json) never affect the exit code.
Exit code 1 if any task is CROSS-FAIL or CROSS-MISMATCH, 0 otherwise.

Usage::

    python bench/aarch64-btor2/oracle_cross.py
    python bench/aarch64-btor2/oracle_cross.py --task 0001-c-loopsum-o0
    python bench/aarch64-btor2/oracle_cross.py --engines z3-bmc,bitwuzla
    python bench/aarch64-btor2/oracle_cross.py --json > oracle_cross.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

# Make ``gurdy.*`` importable without the package being installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.dispatch import dispatch
from gurdy.pairs.aarch64_btor2 import PAIR  # noqa: F401  (registers pair)
from gurdy.pairs.aarch64_btor2.spec import Aarch64Btor2Spec, AnalysisDirective

_BENCH = Path(__file__).parent
_CORPUS = _BENCH / "corpus" / "seed"

INDUCTIVE_PINNED = frozenset({"z3-spacer"})


# ---------------------------------------------------------------------------
# Dispatch profiles
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Profile:
    """One cross-check attempt: engine label, extras overlay, bound fallback."""

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


def profiles_for(pinned_engine: str) -> tuple[Profile, ...]:
    if pinned_engine in INDUCTIVE_PINNED:
        return INDUCTIVE_PROFILES
    return BMC_PROFILES


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------


def verdict_satisfies(expected: str, observed: str) -> bool:
    """Return True iff ``observed`` is a definitive confirmation of ``expected``."""
    if observed in ("unknown", "error"):
        return False
    if expected == "reachable":
        return observed == "reachable"
    if expected in ("unreachable", "proved"):
        return observed in ("unreachable", "proved")
    return False


def verdicts_agree(a: str, b: str) -> bool:
    """Return True iff two verdicts do not conflict (inconclusive == agree)."""
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
    spec: Aarch64Btor2Spec,
    p: Profile,
    artifact: Any,
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
# Task loading
# ---------------------------------------------------------------------------


def _load_task(
    task_dir: Path,
) -> tuple[str, Path | None, Aarch64Btor2Spec | None]:
    """Return ``(expected_verdict, elf_path_or_None, spec_or_None)``.

    ``elf_path`` is None when source.elf is absent — those tasks get a
    SKIP row.  ``spec`` is None when spec.json is absent.
    """
    toml_path = task_dir / "task.toml"
    spec_path = task_dir / "spec.json"
    elf_path = task_dir / "source.elf"

    expected_verdict = "unknown"
    if toml_path.exists():
        t = tomllib.loads(toml_path.read_text())
        expected_verdict = t.get("expected", {}).get("verdict", "unknown")

    if not spec_path.exists():
        return expected_verdict, None, None

    spec = Aarch64Btor2Spec.from_jsonable(json.loads(spec_path.read_text()))
    return expected_verdict, (elf_path if elf_path.exists() else None), spec


# ---------------------------------------------------------------------------
# Per-task summary
# ---------------------------------------------------------------------------


def summarize(expected: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll per-engine rows into a single per-task cross-check verdict."""
    definitive = [r for r in rows if r["verdict"] not in ("unknown", "error")]
    confirms = [r for r in definitive if verdict_satisfies(expected, r["verdict"])]
    disagrees = [r for r in definitive if not verdict_satisfies(expected, r["verdict"])]
    skipped = [r for r in rows if r["verdict"] in ("unknown", "error")]

    pairwise_conflict = False
    for i, a in enumerate(definitive):
        for b in definitive[i + 1:]:
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
# Rendering
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
        lines.append(f"    {r['label']:16s} {verdict:11s} {tag}  {tail}")
    lines.append(
        f"    => {summary['status']} "
        f"({summary['n_confirm']} confirm, "
        f"{summary['n_disagree']} disagree, "
        f"{summary['n_skipped']} skipped)"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="aarch64-btor2 multi-engine cross oracle (no LLM)"
    )
    ap.add_argument("--task", help="run only one task by id (substring match)")
    ap.add_argument(
        "--corpus",
        default=str(_CORPUS),
        help="seed corpus directory (default: bench/aarch64-btor2/corpus/seed)",
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
        default=10,
        help=(
            "cap per-engine dispatch time (seconds). "
            "Default 10s: cross-check is a sanity layer on top of "
            "harness.py. Set to 0 to use each spec's full timeout."
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
        task_dirs = [
            d for d in task_dirs
            if d.name == args.task or args.task in d.name
        ]
        if not task_dirs:
            print(f"no task matching {args.task!r}", file=sys.stderr)
            return 2

    fail_count = 0
    mismatch_count = 0
    out_rows: list[dict[str, Any]] = []

    for task_dir in task_dirs:
        label = task_dir.name
        expected_verdict, elf_path, spec = _load_task(task_dir)

        if elf_path is None or spec is None:
            reason = (
                "no source.elf (cross-toolchain unavailable)"
                if spec is not None or elf_path is None
                else "no spec.json"
            )
            if args.json:
                out_rows.append({"task": label, "status": "SKIP", "reason": reason})
            else:
                print(f"SKIP {label}: {reason}")
            continue

        try:
            artifact = compile_spec(spec, source_payload=elf_path)
        except Exception as exc:
            if args.json:
                out_rows.append({
                    "task": label,
                    "status": "ERROR",
                    "reason": f"compile failed: {exc}",
                })
            else:
                print(f"ERROR {label}: compile failed: {exc}")
            continue

        profiles = profiles_for(spec.analysis.engine)
        if selected is not None:
            profiles = tuple(p for p in profiles if p.label in selected)

        rows: list[dict[str, Any]] = []
        for p in profiles:
            try:
                row = _run_profile(spec, p, artifact, timeout_cap=timeout_cap)
            except Exception as exc:
                row = {
                    "label": p.label,
                    "engine": p.engine,
                    "verdict": "error",
                    "elapsed": 0.0,
                    "reason": str(exc),
                }
            rows.append(row)

        summary = summarize(expected_verdict, rows)
        if summary["status"] == "CROSS-FAIL":
            fail_count += 1
        elif summary["status"] == "CROSS-MISMATCH":
            mismatch_count += 1

        if args.json:
            out_rows.append({
                "task": label,
                "expected": expected_verdict,
                "summary": summary,
            })
        else:
            print(render_text(label, expected_verdict, summary))

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


__all__ = [
    "Profile",
    "BMC_PROFILES",
    "INDUCTIVE_PROFILES",
    "INDUCTIVE_PINNED",
    "profiles_for",
    "verdict_satisfies",
    "verdicts_agree",
    "summarize",
    "render_text",
]
