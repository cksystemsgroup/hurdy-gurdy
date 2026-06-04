"""Audit corpus halted_step values against the BMC engine's actual anchor.

For every reachable task in the corpus, compile the pre-registered
spec.json, dispatch with its pinned AnalysisDirective, lift the
witness, and walk the lifted trace looking for the first step whose
PC equals task.toml's [witness] bad_pc. That cycle is the BMC
engine's "true" halted_step. Compare against the corpus's pinned
``halted_step`` ± ``halted_step_tolerance`` and flag any task where
the engine and the corpus disagree.

This script catches the same class of issue that the 2026-05-07
sweep surfaced for 0023-stride-3-loop (commit 7f4f04d): an author's
eyeball-counted halted_step that drifts from the BMC engine's
actual anchor by more than the recorded tolerance. Tasks that lack
[witness] (proved/unreachable/unknown) are skipped.

Output format mirrors the §9.10 oracle:

    PASS  0007-simple-add-baseline      bmc_step=3   halted_step=3   tol=0
    PASS  0023-stride-3-loop            bmc_step=22  halted_step=22  tol=3
    FAIL  0099-something-broken         bmc_step=42  halted_step=17  tol=3  (off by 25)

Exit code is 1 if any FAIL is reported; 0 otherwise. SKIP rows
indicate no [witness] table or a non-reachable verdict.

Usage:

    python bench/riscv-btor2/audit_anchors.py
    python bench/riscv-btor2/audit_anchors.py --task 0023-stride-3-loop
    python bench/riscv-btor2/audit_anchors.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gurdy.core.tools.compile import compile_spec
from gurdy.core.tools.dispatch import dispatch
from gurdy.pairs.riscv_btor2 import PAIR  # noqa: F401  (registers pair)
from gurdy.pairs.riscv_btor2.lift.lift import Lifter
from gurdy.pairs.riscv_btor2.source.loader import load_riscv_binary
from gurdy.pairs.riscv_btor2.spec import RiscvBtor2Spec


CORPUS = Path(__file__).resolve().parent / "corpus"


def load_task(task_dir: Path) -> tuple[dict[str, Any], RiscvBtor2Spec]:
    try:
        import tomllib  # py311+
    except Exception:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    raw = tomllib.loads((task_dir / "task.toml").read_text())
    spec_obj = json.loads((task_dir / "spec.json").read_text())
    fields = spec_obj.setdefault("fields", {})
    bin_field = fields.setdefault("binary", {})
    rel = bin_field.get("path", "source.elf")
    bin_field["path"] = str((task_dir / rel).resolve())
    return raw, RiscvBtor2Spec.from_jsonable(spec_obj)


def bmc_anchor_step(
    spec: RiscvBtor2Spec,
    bad_pc: int,
    final_regs: dict[int, int] | None = None,
) -> int | None:
    """Return the cycle of the first lifted step whose PC equals
    ``bad_pc`` **and** (when ``final_regs`` is supplied) whose
    register state at that step matches every ``(reg, value)``
    constraint, or None if the verdict isn't reachable / no trace
    is produced / no matching step is found.

    The ``final_regs`` filter resolves the non-unique-bad_pc case:
    when ``bad_pc`` is a loop body PC (e.g., 0201's mul at the loop
    entry), PC alone matches every iteration. Comparing register
    state against the witness fingerprint ``[witness.final_regs]``
    in task.toml picks the step where the property actually fires
    — which is what the corpus's ``halted_step`` pin records.

    Tasks without a ``[witness.final_regs]`` block (pass
    ``final_regs=None`` or ``{}``) fall back to the historical
    PC-only walk so they continue to behave as before.

    Only the z3-bmc backend currently emits a structured witness
    payload that the lifter walks into a per-cycle trace. Tasks
    pinned to bitwuzla / cvc5 / pono get an automatic z3-bmc
    re-dispatch here — the anchor concept is engine-independent
    (it's "which cycle hits bad_pc with the witness fingerprint"),
    and BMC engines that agree on the verdict will agree on the
    anchor.
    """
    import dataclasses

    artifact = compile_spec(spec)
    directive = spec.analysis
    if directive.engine != "z3-bmc":
        directive = dataclasses.replace(directive, engine="z3-bmc")
    raw = dispatch(artifact, directive)
    if raw.verdict != "reachable":
        return None
    source = load_riscv_binary(Path(spec.binary.path))
    lifted = Lifter().lift(artifact, raw, source=source)
    if lifted.trace is None:
        return None
    for step in lifted.trace.steps:
        if step.pc != bad_pc:
            continue
        if final_regs:
            # step.regs is indexed by ABI register number (x0..x31).
            # All listed (reg, value) constraints must match.
            ok = all(
                idx < len(step.regs) and step.regs[idx] == val
                for idx, val in final_regs.items()
            )
            if not ok:
                continue
        return step.cycle
    return None


def render_row(status: str, task_id: str, row: dict[str, Any]) -> str:
    if status == "SKIP":
        return f"{status:5s} {task_id:38s} {row.get('reason', '')}"
    bmc = row.get("bmc_step")
    halted = row.get("halted_step")
    tol = row.get("tolerance", 0)
    bmc_s = "?" if bmc is None else str(bmc)
    halted_s = "?" if halted is None else str(halted)
    base = f"{status:5s} {task_id:38s} bmc_step={bmc_s:>3}  halted_step={halted_s:>3}  tol={tol}"
    if status == "FAIL":
        gap = abs((bmc or 0) - (halted or 0))
        return f"{base}  (off by {gap})"
    return base


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="riscv-btor2 corpus anchor audit")
    p.add_argument("--task", help="run only one task by id (substring match)")
    p.add_argument(
        "--corpus",
        default=str(CORPUS),
        help="corpus directory (default: bench/riscv-btor2/corpus)",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    corpus = Path(args.corpus)
    task_dirs = sorted(d for d in corpus.iterdir() if d.is_dir() and (d / "task.toml").exists())
    if args.task:
        task_dirs = [d for d in task_dirs if d.name == args.task or args.task in d.name]
        if not task_dirs:
            print(f"no task matching {args.task!r}", file=sys.stderr)
            return 2

    rows: list[dict[str, Any]] = []
    fail_count = 0
    for d in task_dirs:
        try:
            raw_task, spec = load_task(d)
        except Exception as exc:
            row = {"task": d.name, "status": "ERROR", "reason": str(exc)}
            rows.append(row)
            if not args.json:
                print(f"ERROR {d.name:38s} {exc}")
            continue

        # Multi-question tasks (B2) carry their verdict per
        # [questions.qN] block; the legacy top-level [expected] is
        # absent. This auditor only checks anchors for single-question
        # 'reachable' tasks (the only ones with witness fingerprints
        # whose anchor_step needs corroborating against BMC), so just
        # SKIP multi-q tasks with a clear reason.
        if "questions" in raw_task:
            row = {"task": d.name, "status": "SKIP",
                   "reason": "multi-question task (B2) — anchor audit "
                             "skipped; framework_oracle covers per-question "
                             "verdicts"}
            rows.append(row)
            if not args.json:
                print(render_row("SKIP", d.name, row))
            continue
        verdict = raw_task.get("expected", {}).get("verdict")
        witness = raw_task.get("witness")
        if verdict != "reachable" or not witness or "halted_step" not in witness:
            row = {"task": d.name, "status": "SKIP",
                   "reason": "no [witness].halted_step (verdict is "
                             f"{verdict!r})"}
            rows.append(row)
            if not args.json:
                print(render_row("SKIP", d.name, row))
            continue

        bad_pc = int(witness["bad_pc"])
        halted = int(witness["halted_step"])
        tol = int(witness.get("halted_step_tolerance", 0))
        # Optional witness fingerprint: register values that must
        # hold at the property-violation step. Lets audit_anchors
        # disambiguate when bad_pc is revisited (see option-A
        # discussion in V2_PROGRESS.md, iter 37–38).
        raw_final = witness.get("final_regs") or {}
        try:
            final_regs = {int(k): int(v) for k, v in raw_final.items()}
        except (TypeError, ValueError):
            final_regs = {}
        try:
            bmc = bmc_anchor_step(spec, bad_pc, final_regs=final_regs)
        except Exception as exc:
            row = {"task": d.name, "status": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            if not args.json:
                print(f"ERROR {d.name:38s} {exc}")
            continue

        if bmc is None:
            row = {"task": d.name, "status": "SKIP",
                   "reason": f"reachable but no trace step at bad_pc={bad_pc}",
                   "bmc_step": None, "halted_step": halted, "tolerance": tol}
            rows.append(row)
            if not args.json:
                print(render_row("SKIP", d.name, row))
            continue

        gap = abs(bmc - halted)
        status = "PASS" if gap <= tol else "FAIL"
        row = {"task": d.name, "status": status, "bmc_step": bmc,
               "halted_step": halted, "tolerance": tol, "gap": gap}
        rows.append(row)
        if status == "FAIL":
            fail_count += 1
        if not args.json:
            print(render_row(status, d.name, row))

    if args.json:
        json.dump({"rows": rows, "failures": fail_count}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif fail_count:
        print(
            f"\n{fail_count} task(s) flagged: BMC anchor outside halted_step ± tolerance",
            file=sys.stderr,
        )

    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
