"""Property-language coverage tracker for the riscv-btor2 corpus.

Walks the corpus and reports the utilisation rate of every
schema-declared capability: observable types, assumption types,
property DSL features, witness fingerprint shapes, verdict
distribution, difficulty / lowering-sensitive distribution, and
free-input usage.

The tracker exists to keep the corpus honest as it grows. It is
trivial to add ten more "register x10 = 12 at halt" tasks; it is
not visible in any single PR review that doing so concentrates
mass on a single property shape and leaves declared capabilities
unused. Run this before/after corpus changes; the diff is the
coverage delta.

The v0.1.2 baseline (32 tasks) used roughly 15-20% of declared
capabilities; v0.2's acceptance criterion is >50%.

Usage:

    python bench/riscv-btor2/coverage_tracker.py
    python bench/riscv-btor2/coverage_tracker.py --json
    python bench/riscv-btor2/coverage_tracker.py --diff baseline.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Schema-declared capabilities -- update if SCHEMA.md adds new types.
OBSERVABLE_TYPES = {"RegisterAt", "MemoryAt", "PCAtStep", "Executed"}
ASSUMPTION_TYPES = {"RegisterInit", "MemoryInit", "CycleInvariant"}
ENGINES = {"z3-bmc", "z3-spacer", "bitwuzla", "cvc5", "pono"}
PROPERTY_OPS = {
    "atoms": {"pc", "true", "false"},
    "memory": {"reg", "mem", "const"},
    "compare": {"eq", "neq", "lt", "le", "gt", "ge",
                "ltu", "leu", "gtu", "geu"},
    "logic":   {"and", "or", "xor", "not"},
    "arith":   {"add", "sub"},
}
DIFFICULTIES = {"T1", "T2", "T3", "T4"}
VERDICTS = {"reachable", "unreachable", "proved", "unknown"}


@dataclass
class CoverageReport:
    n_tasks: int = 0
    by_difficulty: Counter = field(default_factory=Counter)
    by_verdict: Counter = field(default_factory=Counter)
    by_task_class: Counter = field(default_factory=Counter)
    by_engine: Counter = field(default_factory=Counter)
    lowering_sensitive: int = 0

    observable_use: Counter = field(default_factory=Counter)
    assumption_use: Counter = field(default_factory=Counter)
    property_op_use: Counter = field(default_factory=Counter)

    witness_uses_final_regs: int = 0
    witness_uses_executed_pcs: int = 0
    witness_uses_memory: int = 0
    witness_required_count: int = 0  # tasks where verdict=reachable

    learned_populated: int = 0  # tasks where spec.fields.learned is non-empty
    free_input: int = 0  # tasks with no RegisterInit (so reg values are free)

    def utilization(self) -> dict[str, dict[str, float]]:
        """Per-capability utilization: fraction of tasks using each."""
        n = max(1, self.n_tasks)
        return {
            "observables": {
                kind: self.observable_use.get(kind, 0) / n
                for kind in OBSERVABLE_TYPES
            },
            "assumptions": {
                kind: self.assumption_use.get(kind, 0) / n
                for kind in ASSUMPTION_TYPES
            },
            "property_ops": {
                op: self.property_op_use.get(op, 0) / n
                for group in PROPERTY_OPS.values()
                for op in group
            },
            "witness_features": {
                "final_regs":   self.witness_uses_final_regs / n,
                "executed_pcs": self.witness_uses_executed_pcs / n,
                "memory":       self.witness_uses_memory / n,
            },
            "engines": {
                eng: self.by_engine.get(eng, 0) / n for eng in ENGINES
            },
        }

    def overall_utilization(self) -> float:
        """Single number: what fraction of declared capabilities does
        the corpus exercise at all? Capability counts: 4 observable
        types, 3 assumption types, 5 engines, 24 property ops, 3
        witness fingerprint kinds = 39. A capability is "used" if at
        least one task exercises it."""
        used = 0
        total = 0
        u = self.utilization()
        for group in u.values():
            for v in group.values():
                total += 1
                if v > 0:
                    used += 1
        return used / max(1, total)


def _walk_property(expr: str, op_counter: Counter) -> None:
    """Tokenize a DSL expression and record which operators appear.
    Lightweight regex-only walk; does not validate."""
    if not isinstance(expr, str):
        return
    for token in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", expr):
        # We only count tokens that match a known op/atom.
        for group in PROPERTY_OPS.values():
            if token in group:
                op_counter[token] += 1


def analyze_task(task_dir: Path) -> dict[str, Any] | None:
    """Read one task's metadata and return a per-task analysis dict,
    or None if the directory isn't a real task."""
    try:
        import tomllib  # py311+
    except Exception:  # pragma: no cover
        import tomli as tomllib  # type: ignore

    if not (task_dir / "task.toml").exists():
        return None
    if not (task_dir / "spec.json").exists():
        return None

    raw_task = tomllib.loads((task_dir / "task.toml").read_text())
    spec = json.loads((task_dir / "spec.json").read_text())

    fields = spec.get("fields", {})
    obs = fields.get("observables", []) or []
    asn = fields.get("assumptions", []) or []
    learned = fields.get("learned", []) or []
    prop_expr = (fields.get("property") or {}).get("expression", "")
    engine = (fields.get("analysis") or {}).get("engine")

    # Free-input heuristic: if no RegisterInit assumption pins a0/a1
    # (registers 10/11 by RV ABI), the spec has free arg inputs.
    register_inits = {a.get("register") for a in asn
                      if a.get("__type__") == "RegisterInit"}
    free_input = (10 not in register_inits) and (11 not in register_inits) and (5 not in register_inits)

    witness = raw_task.get("witness") or {}
    return {
        "id": task_dir.name,
        "difficulty": (raw_task.get("task") or {}).get("difficulty"),
        "task_class": (raw_task.get("task") or {}).get("task_class"),
        "lowering_sensitive": bool((raw_task.get("task") or {}).get("lowering_sensitive")),
        "verdict": (raw_task.get("expected") or {}).get("verdict"),
        "engine": engine,
        "observable_types": [o.get("__type__") for o in obs],
        "assumption_types": [a.get("__type__") for a in asn],
        "property_expr": prop_expr,
        "learned_count": len(learned),
        "free_input": free_input,
        "witness_present": bool(witness),
        "witness_has_final_regs": bool(witness.get("final_regs")),
        "witness_has_executed_pcs": bool(witness.get("executed_pcs")),
        "witness_has_memory": bool(witness.get("memory")),
    }


def build_report(corpus: Path) -> CoverageReport:
    rep = CoverageReport()
    for d in sorted(corpus.iterdir()):
        if not d.is_dir():
            continue
        ana = analyze_task(d)
        if ana is None:
            continue

        rep.n_tasks += 1
        if ana["difficulty"]:
            rep.by_difficulty[ana["difficulty"]] += 1
        if ana["verdict"]:
            rep.by_verdict[ana["verdict"]] += 1
        if ana["task_class"]:
            rep.by_task_class[ana["task_class"]] += 1
        if ana["engine"]:
            rep.by_engine[ana["engine"]] += 1
        if ana["lowering_sensitive"]:
            rep.lowering_sensitive += 1

        for kind in set(ana["observable_types"]):
            rep.observable_use[kind] += 1
        for kind in set(ana["assumption_types"]):
            rep.assumption_use[kind] += 1

        _walk_property(ana["property_expr"], rep.property_op_use)

        if ana["witness_has_final_regs"]:
            rep.witness_uses_final_regs += 1
        if ana["witness_has_executed_pcs"]:
            rep.witness_uses_executed_pcs += 1
        if ana["witness_has_memory"]:
            rep.witness_uses_memory += 1
        if ana["verdict"] == "reachable":
            rep.witness_required_count += 1

        if ana["learned_count"] > 0:
            rep.learned_populated += 1
        if ana["free_input"]:
            rep.free_input += 1
    return rep


def render_text(rep: CoverageReport) -> str:
    n = rep.n_tasks
    out = []
    out.append(f"=== riscv-btor2 corpus coverage ({n} tasks) ===")
    out.append("")
    out.append("Difficulty distribution:")
    for d in sorted(DIFFICULTIES):
        c = rep.by_difficulty.get(d, 0)
        out.append(f"  {d}: {c:>3} ({c/max(1,n):.0%})")
    out.append(f"  lowering_sensitive: {rep.lowering_sensitive} ({rep.lowering_sensitive/max(1,n):.0%})")
    out.append("")
    out.append("Verdict distribution:")
    for v in sorted(VERDICTS):
        c = rep.by_verdict.get(v, 0)
        out.append(f"  {v:<11} {c:>3}")
    out.append("")
    out.append("Task class distribution:")
    for cls, c in rep.by_task_class.most_common():
        out.append(f"  {cls:<22} {c:>3}")
    out.append("")
    out.append("Engine distribution (analysis.engine):")
    for eng in sorted(ENGINES):
        c = rep.by_engine.get(eng, 0)
        out.append(f"  {eng:<12} {c:>3} ({c/max(1,n):.0%})")
    out.append("")
    out.append("Observable type usage (any task using each):")
    for kind in sorted(OBSERVABLE_TYPES):
        c = rep.observable_use.get(kind, 0)
        out.append(f"  {kind:<14} {c:>3} ({c/max(1,n):.0%})")
    out.append("")
    out.append("Assumption type usage:")
    for kind in sorted(ASSUMPTION_TYPES):
        c = rep.assumption_use.get(kind, 0)
        out.append(f"  {kind:<18} {c:>3} ({c/max(1,n):.0%})")
    out.append("")
    out.append("Property DSL operator usage (count of expressions referencing each):")
    for group_name, ops in PROPERTY_OPS.items():
        out.append(f"  [{group_name}]")
        for op in sorted(ops):
            c = rep.property_op_use.get(op, 0)
            mark = "" if c > 0 else "  -- UNUSED"
            out.append(f"    {op:<10} {c:>3}{mark}")
    out.append("")
    out.append("Witness fingerprint shape:")
    out.append(f"  final_regs:   {rep.witness_uses_final_regs:>3} / {rep.witness_required_count} reachable tasks")
    out.append(f"  executed_pcs: {rep.witness_uses_executed_pcs:>3} / {rep.witness_required_count}")
    out.append(f"  memory:       {rep.witness_uses_memory:>3} / {rep.witness_required_count}")
    out.append("")
    out.append("Spec features:")
    out.append(f"  learned (T3 LearnedFact populated): {rep.learned_populated:>3} ({rep.learned_populated/max(1,n):.0%})")
    out.append(f"  free input (no RegisterInit on a0/a1/x5): {rep.free_input:>3} ({rep.free_input/max(1,n):.0%})")
    out.append("")
    out.append(f"Overall utilisation (capabilities used / declared): {rep.overall_utilization():.1%}")
    return "\n".join(out)


def to_json(rep: CoverageReport) -> dict[str, Any]:
    return {
        "n_tasks": rep.n_tasks,
        "by_difficulty": dict(rep.by_difficulty),
        "by_verdict": dict(rep.by_verdict),
        "by_task_class": dict(rep.by_task_class),
        "by_engine": dict(rep.by_engine),
        "lowering_sensitive": rep.lowering_sensitive,
        "observable_use": dict(rep.observable_use),
        "assumption_use": dict(rep.assumption_use),
        "property_op_use": dict(rep.property_op_use),
        "witness_uses_final_regs":   rep.witness_uses_final_regs,
        "witness_uses_executed_pcs": rep.witness_uses_executed_pcs,
        "witness_uses_memory":       rep.witness_uses_memory,
        "witness_required_count":    rep.witness_required_count,
        "learned_populated": rep.learned_populated,
        "free_input": rep.free_input,
        "utilization": rep.utilization(),
        "overall_utilization": rep.overall_utilization(),
    }


def render_diff(prev: dict, curr: dict) -> str:
    """Diff-format renderer: only show metrics that changed."""
    out = ["=== coverage diff (baseline -> current) ==="]
    out.append(f"  n_tasks: {prev.get('n_tasks')} -> {curr.get('n_tasks')}")
    overall_prev = prev.get("overall_utilization", 0.0)
    overall_curr = curr.get("overall_utilization", 0.0)
    out.append(f"  overall_utilization: {overall_prev:.1%} -> {overall_curr:.1%}")

    for top_key, group in curr.get("utilization", {}).items():
        prev_group = prev.get("utilization", {}).get(top_key, {})
        for k, v in group.items():
            pv = prev_group.get(k, 0.0)
            if abs(pv - v) > 1e-9:
                out.append(f"  utilization.{top_key}.{k}: {pv:.0%} -> {v:.0%}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--corpus",
        default=str(Path(__file__).resolve().parent / "corpus"),
    )
    p.add_argument("--json", action="store_true",
                   help="emit JSON to stdout instead of a text report")
    p.add_argument("--diff",
                   help="path to a baseline JSON; print only the delta")
    args = p.parse_args(argv)

    rep = build_report(Path(args.corpus))
    payload = to_json(rep)

    if args.diff:
        baseline = json.loads(Path(args.diff).read_text())
        print(render_diff(baseline, payload))
        return 0

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(render_text(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
