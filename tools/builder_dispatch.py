#!/usr/bin/env python3
"""The builder-dispatch harness — Phase 4 of the automated-scaling rollout
(SCALING.md §12.4, §5, §8).

Turns a *partial* pair's uncovered constructs into work for unattended builder
agents. It provides the reusable pieces an orchestrator (or a coordinator using
the Claude Agent SDK) drives:

- ``work_list(pair_id)`` — the pair's uncovered constructs, the builder queue;
- ``build_brief(pair_id, constructs)`` — a precise, self-contained brief a
  builder agent implements against (PAIRING.md as a work item);
- ``self_verify(pair_id)`` — the per-construct gate a builder runs before it
  commits: conjoined coverage, determinism, and the two-sided negative control
  (SCALING.md §3.2), for this one pair. Fast (interpreters only).

The *loop* (SCALING.md §5): pick a partial pair below target → generate a brief
→ run a builder on an isolated branch → the builder implements one construct,
runs ``self_verify``, and **commits on green**, construct by construct (the
ratchet keeps every prior verdict standing) → the coordinator runs the full
gate and **opens a PR when the milestone is reached**. This module supplies the
work-list / brief / self-verify; spawning the builder agent and opening the PR
are the coordinator's actions.

CLI: ``python tools/builder_dispatch.py {worklist|brief|verify} <pair-id> [constructs...]``.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gurdy.core import negative_control, registry     # noqa: E402
from gurdy.core.coverage import measure               # noqa: E402


def _import_all_pairs() -> None:
    import gurdy.pairs as pairs_pkg
    for mod in pkgutil.iter_modules(pairs_pkg.__path__):
        importlib.import_module(f"gurdy.pairs.{mod.name}")


def _conjoined(pair: Any):
    return measure(pair.translator, pair.probes, faithful=pair.square)


def partial_pairs() -> list[dict[str, Any]]:
    """Every checked-grade pair with uncovered constructs — the platform's
    build queue (AGENTS.md §1: the registered briefs are the work queue; this
    surfaces the *widening* work within them)."""
    _import_all_pairs()
    out = []
    for pid, pair in sorted(registry.list_pairs().items()):
        if pair.square is None or not pair.probes:
            continue
        rep = _conjoined(pair)
        if len(rep.covered) < rep.total:
            out.append({"pair": pid, "covered": len(rep.covered),
                        "total": rep.total,
                        "uncovered": sorted(set(rep.missing.values()))})
    return out


def work_list(pair_id: str) -> list[str]:
    """The uncovered constructs for a pair — the builder's queue."""
    _import_all_pairs()
    pair = registry.get_pair(pair_id)
    rep = _conjoined(pair)
    return sorted(set(rep.missing.values()))


def self_verify(pair_id: str) -> dict[str, Any]:
    """The per-construct gate a builder runs before committing: conjoined
    coverage, determinism (twice-and-diff over probes), and the two-sided
    negative control. Returns a structured verdict."""
    _import_all_pairs()
    pair = registry.get_pair(pair_id)
    rep = _conjoined(pair)
    # determinism: translate every accepted probe twice, bytes must match.
    from gurdy.core.errors import Unsupported
    det = True
    for program in pair.probes.values():
        try:
            a = pair.translator(program)
        except Unsupported:
            continue
        if a != pair.translator(program):
            det = False
            break
    ctrl = negative_control.two_sided_control(pair)
    return {
        "pair": pair_id,
        "conjoined": [len(rep.covered), rep.total],
        "uncovered": len(set(rep.missing.values())),
        "determinism_ok": det,
        "negative_control_ok": (ctrl.ok if ctrl else None),
        "gate_ok": det and (ctrl.ok if ctrl else True),
    }


def build_brief(pair_id: str, constructs: list[str]) -> str:
    """A self-contained brief a builder agent implements against."""
    _import_all_pairs()
    pair = registry.get_pair(pair_id)
    rep = _conjoined(pair)
    src, tgt = pair.source, pair.target
    modname = pair_id.replace("-", "_")
    todo = constructs or sorted(set(rep.missing.values()))
    todo_str = ", ".join(todo)
    return f"""\
# Builder brief — widen `{pair_id}` ({src} -> {tgt})

You are an independent builder agent (AGENTS.md, PAIRING.md). Widen the
`{pair_id}` pair to cover these currently-`unsupported` constructs, **one at a
time**:

    {todo_str}

Current conjoined coverage: {len(rep.covered)}/{rep.total}. Raise it; never
lower it (the coverage ratchet, BENCHMARKS.md §5).

## Files you own (edit only these)
- `gurdy/pairs/{modname}/translate.py` — the translator `T`. Extend the decoder
  to accept each opcode and add its lowering. Follow the existing template (the
  binary-arithmetic block is the model for binary ops; unary and comparison ops
  are small variants).
- `gurdy/pairs/{modname}/inventory.py` — the probe corpus. For each opcode you
  cover, replace its **bare** probe (`_probe_for`'s fallthrough) with an
  **operand-framed** probe that actually exercises the opcode's computation
  (mirror `ADD`'s probe: push two distinguishing operands, apply the op, stop).
  A bare probe only exercises stack-underflow and does NOT test your lowering.
- `gurdy/pairs/{modname}/SPEC.md` — record each construct's lowering rule.

## Files you must NOT change
- Any other pair, any `gurdy/languages/*`, any `gurdy/core/*`, the framework,
  or another pair's tests. If you need shared logic, stop and report (a shared
  change is the coordinator's to arbitrate, SCALING.md §6).

## The contract (PAIRING.md)
- `T` stays **pure/deterministic**: same input -> byte-identical output.
- The commuting **square must pass** on each covered opcode's operand-framed
  probe: `I_s(p)` == `L(I_t(T(p)))` under the projection. A divergence means
  your lowering is wrong — fix it; the square localizes the step/observable.
- Everything you do not cover stays a typed `unsupported: evm:<OPCODE>` abort —
  never a silent drop.

## Self-verify and commit protocol
After covering **each** opcode, run the per-construct gate:

    python tools/builder_dispatch.py verify {pair_id}

It must show `conjoined` increased by one, `determinism_ok: true`, and
`negative_control_ok: true`. Only then **commit that one opcode**:

    git add -A && git commit -m "{pair_id}: cover <OPCODE>"

Commit regularly — one opcode per commit. Do **not** open a PR; when you have
covered all you can, stop and report which opcodes you covered and the final
`verify` output. The coordinator runs the full suite and opens the PR.

If an opcode is genuinely hard (needs environment/context state, external
calls, or shared-layer changes — e.g. CALL, CREATE, KECCAK256, the LOG family,
gas), skip it, note why, and move on. Land the tractable ones cleanly.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("queue", help="list partial pairs with uncovered constructs")
    w = sub.add_parser("worklist", help="uncovered constructs for a pair")
    w.add_argument("pair")
    b = sub.add_parser("brief", help="emit a builder brief for a pair")
    b.add_argument("pair")
    b.add_argument("constructs", nargs="*")
    v = sub.add_parser("verify", help="the per-construct gate for a pair")
    v.add_argument("pair")
    args = ap.parse_args()

    if args.cmd == "queue":
        for row in partial_pairs():
            print(f"{row['pair']:16s} {row['covered']}/{row['total']} "
                  f"({len(row['uncovered'])} uncovered)")
    elif args.cmd == "worklist":
        print("\n".join(work_list(args.pair)))
    elif args.cmd == "brief":
        print(build_brief(args.pair, args.constructs))
    elif args.cmd == "verify":
        import json
        print(json.dumps(self_verify(args.pair), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
