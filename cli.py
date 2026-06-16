#!/usr/bin/env python3
"""hurdy-gurdy v3 CLI — make the skeleton runnable end-to-end.

Subcommands:
  routes <in> <out>   enumerate routes over the hop graph
  plan                what the orchestrator would spawn (machine + pair agents)
  gate <hop-id>       run the pair gate (F0 real; F1-F3/machine stubbed)
  model <model-id>    certify a registered formal model (which capabilities it backs)
  chain               walk the worked C -> ... -> smt-lib route
  hops                list registered hops
"""

from __future__ import annotations

import sys
from pathlib import Path

# make the repo root importable as the package root (gurdy, gate, agents, tools);
# harmless when installed (pip install -e .), needed for `python cli.py ...`
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gurdy.hops  # noqa: E402,F401  (registers the hops)
from gurdy.core.hop import all_hops  # noqa: E402
from gurdy.core.route import routes  # noqa: E402


def cmd_routes(args: list[str]) -> int:
    if len(args) != 2:
        print("usage: cli.py routes <in_lang> <out_lang>")
        return 2
    rs = routes(args[0], args[1])
    if not rs:
        print(f"no route {args[0]} -> {args[1]}")
        return 1
    for r in rs:
        print(r)
    return 0


def cmd_hops(_: list[str]) -> int:
    for h in all_hops():
        print(f"{h.id:14s} {h.kind:9s} {h.in_lang} -> {h.out_lang}  ({h.declared_tier.label})")
    return 0


def cmd_plan(_: list[str]) -> int:
    from agents.orchestrator import plan

    for s in plan():
        sail = "sail+" if s.sail_access else "sandboxed"
        print(f"[{s.agent_type:13s}] {s.target:14s} branch={s.branch:22s} {sail:9s}")
        print(f"                {s.note}")
    return 0


def cmd_gate(args: list[str]) -> int:
    if len(args) != 1:
        print("usage: cli.py gate <hop-id>")
        return 2
    from gate.run_gate import run_by_id

    report, decision = run_by_id(args[0])
    print(f"hop: {report.hop_id}   level: {report.level.label}")
    for c in report.checks:
        print(f"  {c.level.label:12s} {c.status.name:16s} {c.detail}")
    print(f"  reasoning_trust_ok = {report.reasoning_trust_ok}")
    print(f"  projection_pinned_ok = {report.projection_pinned_ok}")
    print(f"  independence_audit_ok = {report.independence_audit_ok}")
    for f in report.independence_findings:
        print(f"      ! {f}")
    print(f"merge: {'ALLOW' if decision.allow else 'BLOCK'} — {'; '.join(decision.reasons)}")
    return 0 if decision.allow else 1


def cmd_model(args: list[str]) -> int:
    if len(args) != 1:
        print("usage: cli.py model <model-id>")
        return 2
    from gate.model.run_model import run_by_id

    r = run_by_id(args[0])
    print(f"model: {r.model_id}   language: {r.language}")
    print(f"  declared: {', '.join(r.declared_capabilities) or '(none)'}")
    for c in r.capability_status:
        print(f"  {c.capability:13s} {c.status.name:16s} {c.detail}")
    print(f"  pins_ok = {r.pins_ok}")
    for n in r.notes:
        print(f"      - {n}")
    print(f"  certified: {', '.join(sorted(r.certified)) or '(none in this environment)'}")
    return 0 if r.ok else 1


def cmd_chain(_: list[str]) -> int:
    from gurdy.chains.c_to_smtlib import describe

    print(describe())
    return 0


COMMANDS = {
    "routes": cmd_routes,
    "hops": cmd_hops,
    "plan": cmd_plan,
    "gate": cmd_gate,
    "model": cmd_model,
    "chain": cmd_chain,
}


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]            # entry point: gurdy = "cli:main"
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
