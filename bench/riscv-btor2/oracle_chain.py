"""Chain-aware oracle for the C-derived corpus (``C -> RV64 ELF -> BTOR2``).

The verdict/align oracles (``framework_oracle.py``, ``oracle_align.py``)
start from the on-disk ``source.elf`` build product. Since the corpus
migration, that ELF is built reproducibly by ``_compile_c.py`` (which now
drives the ``c-riscv`` hop), but it is still a *build product*: this oracle
instead starts from the tracked ``task.c`` and runs the whole chain
in-process, so it validates the source→verdict path end to end rather than
trusting any pre-built bytes:

    task.c  --(c-riscv hop, gcc 14.2.0 @digest)-->  RV64 ELF
            --(riscv-btor2 pair)----------------->  BTOR2
            --(dispatch)------------------------->  verdict
            --(lift + walk projection)----------->  alignment

so it validates the *as-built chain* at corpus scale, from source. Two
things are checked per task:

- **verdict_ok** — does the chain's solver verdict match the task's
  manual-proof ``[expected] verdict``?
- **align_ok** — for a ``reachable`` witness, does the BTOR2 trace agree
  step-for-step with the RV64 source interpreter (soundness through the
  chain)? A divergence is a real C->ELF->BTOR2 translation bug, localized
  to a step.

Per-task chain parameters are read from the ``[c]`` table of
``task.toml`` (``opt_level``, ``bound``, ``engine``, ``included_callees``,
``timeout``) so the chain reproduces each task's pinned question.

Status / exit code, mirroring ``oracle_align.py``:

    PASS  verdict matches (and align ok when a witness exists)
    FAIL  verdict mismatch, or witness alignment diverges
    SKIP  solver returned ``unknown`` (no decision to score)
    ERROR compile / dispatch / replay raised

Exit code 1 if any FAIL, else 0. Requires the pinned bench Docker image
(hop 1); if absent the oracle prints a notice and exits 0.

RAM safety: tasks run strictly one at a time (one docker build + one
solver subprocess in flight), with a ``--max-tasks`` cap — the C chain is
heavier than the assembly path (a container compile + an objdump run per
task), so the default cap is deliberately small.

Usage:

    python bench/riscv-btor2/oracle_chain.py
    python bench/riscv-btor2/oracle_chain.py --task 0101
    python bench/riscv-btor2/oracle_chain.py --max-tasks 26 --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

# Allow `import gurdy.*` without depending on an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.chains.c_to_btor2 import compile_c_to_btor2
from gurdy.core.tools.dispatch import dispatch
from gurdy.hops.c_riscv import (
    cbmc_verify,
    classify_differential,
    toolchain_available,
)
from gurdy.core.btor2.parser import from_text as _btor2_from_text
from gurdy.pairs.riscv_btor2.lift.replayer import replay_witness
from gurdy.pairs.riscv_btor2.source_interp.projection import make_projection

CORPUS = Path(__file__).resolve().parent / "corpus"


# ---------------------------------------------------------------------------
# Per-task chain parameters (from task.toml [c] + [expected])
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainTask:
    task: str
    source_name: str
    c_source: bytes
    expected: str
    opt_level: str
    bound: int
    timeout: int
    engine: str
    included_callees: list[str] | None
    trap_function: str
    entry_function: str
    lowering_sensitive: bool


def _load_chain_task(task_dir: Path) -> ChainTask:
    try:
        import tomllib  # py311+
    except Exception:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    raw = tomllib.loads((task_dir / "task.toml").read_text())
    c = raw.get("c", {})
    expected = raw.get("expected", {}).get("verdict", "?")
    callees = c.get("included_callees")
    return ChainTask(
        task=task_dir.name,
        source_name="task.c",
        c_source=(task_dir / "task.c").read_bytes(),
        expected=expected,
        opt_level=str(c.get("opt_level", "0")),
        bound=int(c.get("bound", 20)),
        timeout=int(c.get("timeout", 60)),
        engine=str(c.get("engine", "z3-bmc")),
        included_callees=list(callees) if callees is not None else None,
        trap_function=str(c.get("trap_function", "trap")),
        entry_function=str(c.get("entry_function", "_start")),
        lowering_sensitive=bool(raw.get("task", {}).get("lowering_sensitive", False)),
    )


# ---------------------------------------------------------------------------
# Per-task result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainCheck:
    task: str
    expected: str
    status: str  # PASS | FAIL | SKIP | ERROR
    got_verdict: str = ""
    verdict_ok: bool = False
    align_kind: str = "N/A"  # ok | diverge | N/A
    divergence_step: int | None = None
    divergence_label: str | None = None
    steps_checked: int = 0
    fields_checked: int = 0
    c_lines: int = 0  # distinct C source lines recovered in the witness
    engine: str = ""
    opt_level: str = ""
    trap_pc: int = 0
    cbmc_verdict: str = ""  # populated only with --cbmc
    differential: str = ""  # agree | expected-divergence | fault | inconclusive
    elapsed: float = 0.0
    note: str = ""

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "expected": self.expected,
            "status": self.status,
            "got_verdict": self.got_verdict,
            "verdict_ok": self.verdict_ok,
            "align_kind": self.align_kind,
            "divergence_step": self.divergence_step,
            "divergence_label": self.divergence_label,
            "steps_checked": self.steps_checked,
            "fields_checked": self.fields_checked,
            "c_lines": self.c_lines,
            "engine": self.engine,
            "opt_level": self.opt_level,
            "trap_pc": self.trap_pc,
            "cbmc_verdict": self.cbmc_verdict,
            "differential": self.differential,
            "elapsed": round(self.elapsed, 3),
            "note": self.note,
        }


def render_row(r: ChainCheck) -> str:
    if r.align_kind == "ok":
        align_str = f"ok      (steps={r.steps_checked}, C-lines={r.c_lines})"
    elif r.align_kind == "diverge":
        align_str = (
            f"diverge@step={r.divergence_step} label={r.divergence_label or '?'}"
        )
    else:
        align_str = f"N/A     ({r.note})" if r.note else "N/A"
    got = r.got_verdict or "?"
    row = (
        f"{r.status:5s} {r.task:32s} "
        f"O{r.opt_level} expected={r.expected:11s} got={got:11s} "
        f"align={align_str}"
    )
    if r.differential:
        row += f"  cbmc={r.cbmc_verdict or '?':11s} [{r.differential}]"
    return row


# ---------------------------------------------------------------------------
# Alignment walk (self-contained, mirrors oracle_align.py)
# ---------------------------------------------------------------------------


def _projection_for_artifact(artifact):
    text = artifact.flattened.decode("utf-8", errors="replace")
    parsed = _btor2_from_text(text)
    sym_to_nid: dict[str, int] = {
        n.symbol: n.nid
        for n in parsed.model.nodes()
        if n.op == "state" and n.symbol
    }
    return make_projection(sym_to_nid)


def _walk_alignment(joined, projection):
    """Return ``(outcome, steps, fields, dstep, dlabel)`` — 'ok' on full
    agreement, 'diverge' at the first projected field that disagrees."""
    steps_checked = 0
    fields_checked = 0
    for i, jstep in enumerate(joined.steps):
        steps_checked = i + 1
        for pf in projection(jstep.source, jstep.reasoning):
            fields_checked += 1
            if not pf.agree:
                return ("diverge", steps_checked, fields_checked, i, pf.label)
    return ("ok", steps_checked, fields_checked, None, None)


# ---------------------------------------------------------------------------
# Per-task runner
# ---------------------------------------------------------------------------


def run_one(ct: ChainTask) -> ChainCheck:
    t0 = time.monotonic()
    try:
        chain = compile_c_to_btor2(
            ct.c_source,
            trap_function=ct.trap_function,
            entry_function=ct.entry_function,
            included_callees=ct.included_callees,
            engine=ct.engine,
            bound=ct.bound,
            timeout=ct.timeout,
            opt_level=ct.opt_level,
            source_name=ct.source_name,
        )
        raw = dispatch(chain.artifact, chain.spec.analysis)
    except Exception as exc:
        return ChainCheck(
            task=ct.task,
            expected=ct.expected,
            status="ERROR",
            opt_level=ct.opt_level,
            elapsed=time.monotonic() - t0,
            note=f"chain/dispatch: {type(exc).__name__}: {exc}",
        )

    verdict = raw.verdict
    engine = raw.engine or ct.engine
    verdict_ok = verdict == ct.expected
    base = dict(
        task=ct.task,
        expected=ct.expected,
        got_verdict=verdict,
        verdict_ok=verdict_ok,
        engine=engine,
        opt_level=ct.opt_level,
        trap_pc=chain.trap_pc,
    )

    if verdict == "unknown":
        return ChainCheck(
            **base,
            status="SKIP",
            elapsed=time.monotonic() - t0,
            note="verdict=unknown",
        )

    if verdict == "reachable":
        # Score the witness: it must (a) match the expected verdict and
        # (b) align with the source interpreter step-for-step.
        try:
            joined = replay_witness(chain.artifact, raw, source=chain.source)
            projection = _projection_for_artifact(chain.artifact)
            outcome, steps, fields, dstep, dlabel = _walk_alignment(
                joined, projection
            )
            lifted = chain.lift(raw)
            c_lines = len(
                {
                    (s.file, s.line)
                    for s in (lifted.trace.steps if lifted.trace else [])
                    if s.file and s.file.endswith(".c") and s.line is not None
                }
            )
        except Exception as exc:
            return ChainCheck(
                **base,
                status="ERROR",
                elapsed=time.monotonic() - t0,
                note=f"replay/align: {type(exc).__name__}: {exc}",
            )
        if outcome == "diverge":
            return ChainCheck(
                **base,
                status="FAIL",
                align_kind="diverge",
                divergence_step=dstep,
                divergence_label=dlabel,
                steps_checked=steps,
                fields_checked=fields,
                c_lines=c_lines,
                elapsed=time.monotonic() - t0,
                note=f"chain divergence at step {dstep} label={dlabel}",
            )
        # align ok — PASS iff verdict also matches
        return ChainCheck(
            **base,
            status="PASS" if verdict_ok else "FAIL",
            align_kind="ok",
            steps_checked=steps,
            fields_checked=fields,
            c_lines=c_lines,
            elapsed=time.monotonic() - t0,
            note="" if verdict_ok else f"verdict {verdict} != expected {ct.expected}",
        )

    # unreachable / proved — definite, no witness to align
    if verdict in ("unreachable", "proved"):
        return ChainCheck(
            **base,
            status="PASS" if verdict_ok else "FAIL",
            elapsed=time.monotonic() - t0,
            note="no witness" if verdict_ok else f"expected {ct.expected}",
        )

    return ChainCheck(
        **base,
        status="ERROR",
        elapsed=time.monotonic() - t0,
        note=f"unexpected verdict: {verdict!r} ({raw.reason or ''})",
    )


def apply_cbmc(check: ChainCheck, ct: ChainTask) -> ChainCheck:
    """Cross-check the chain's verdict against an independent CBMC run on the
    same C source (the ``checked``-tier differential). Only a **fault** —
    a disagreement on a task that is *not* lowering-sensitive — downgrades
    the status to FAIL; ``agree`` and the documented ``expected-divergence``
    (C-UB vs RV64-defined, on lowering-sensitive tasks) are not failures.
    """
    if check.got_verdict not in ("reachable", "unreachable"):
        return replace(check, differential="inconclusive")
    try:
        r = cbmc_verify(ct.c_source, bound=ct.bound)
    except Exception as exc:
        return replace(
            check,
            cbmc_verdict="error",
            differential="inconclusive",
            note=(f"{check.note}; cbmc: {type(exc).__name__}: {exc}").strip("; "),
        )
    cls = classify_differential(
        check.got_verdict, r.verdict, lowering_sensitive=ct.lowering_sensitive
    )
    if cls == "fault":
        return replace(
            check,
            status="FAIL",
            cbmc_verdict=r.verdict,
            differential=cls,
            note=(
                f"{check.note}; CBMC differential FAULT: chain="
                f"{check.got_verdict} vs cbmc={r.verdict} on a "
                f"non-lowering-sensitive task (localizes to hop 1)"
            ).strip("; "),
        )
    return replace(check, cbmc_verdict=r.verdict, differential=cls)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _discover(corpus: Path) -> list[Path]:
    return sorted(
        d
        for d in corpus.iterdir()
        if d.is_dir() and (d / "task.toml").exists() and (d / "task.c").exists()
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="chain-aware oracle for the C-derived corpus (C->ELF->BTOR2)"
    )
    p.add_argument("--task", help="run only tasks whose id contains this substring")
    p.add_argument(
        "--corpus",
        default=str(CORPUS),
        help="corpus directory (default: bench/riscv-btor2/corpus)",
    )
    p.add_argument(
        "--max-tasks",
        type=int,
        default=4,
        help=(
            "RAM-safety cap on tasks per invocation (the C chain runs a "
            "container compile + objdump + solver per task). Default 4."
        ),
    )
    p.add_argument(
        "--cbmc",
        action="store_true",
        help=(
            "also run the CBMC differential (checked tier): cross-check each "
            "chain verdict against an independent CBMC run in the pinned "
            "image. Adds a container run per task."
        ),
    )
    p.add_argument("--json", action="store_true", help="emit JSON")
    args = p.parse_args(argv)

    if not toolchain_available():
        print(
            "pinned bench Docker image unavailable; chain hop 1 cannot run. "
            "Skipping (not a failure).",
            file=sys.stderr,
        )
        return 0

    corpus = Path(args.corpus)
    if not corpus.is_dir():
        print(f"corpus not found: {corpus}", file=sys.stderr)
        return 2

    task_dirs = _discover(corpus)
    if args.task:
        task_dirs = [d for d in task_dirs if args.task in d.name]
        if not task_dirs:
            print(f"no C task matching {args.task!r}", file=sys.stderr)
            return 2
    if len(task_dirs) > args.max_tasks:
        print(
            f"{len(task_dirs)} C tasks matched; --max-tasks={args.max_tasks} "
            f"caps this run (RAM safety); pass --max-tasks N to raise.",
            file=sys.stderr,
        )
        task_dirs = task_dirs[: args.max_tasks]

    results: list[ChainCheck] = []
    fail_count = 0
    for d in task_dirs:
        try:
            ct = _load_chain_task(d)
        except Exception as exc:
            r = ChainCheck(
                task=d.name,
                expected="?",
                status="ERROR",
                note=f"load_task: {type(exc).__name__}: {exc}",
            )
        else:
            r = run_one(ct)
            if args.cbmc:
                r = apply_cbmc(r, ct)
        results.append(r)
        if r.status == "FAIL":
            fail_count += 1
        if not args.json:
            print(render_row(r))

    if args.json:
        json.dump(
            {"rows": [r.to_jsonable() for r in results], "failures": fail_count},
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        passed = sum(1 for r in results if r.status == "PASS")
        summary = (
            f"\n{passed}/{len(results)} PASS, {fail_count} FAIL "
            f"(C-chain verdict + alignment)"
        )
        if args.cbmc:
            agree = sum(1 for r in results if r.differential == "agree")
            exp = sum(1 for r in results if r.differential == "expected-divergence")
            print(
                summary + f"; CBMC differential: {agree} agree, "
                f"{exp} expected-divergence (C-UB vs RV64)",
                file=sys.stderr,
            )
        else:
            print(summary, file=sys.stderr)

    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
