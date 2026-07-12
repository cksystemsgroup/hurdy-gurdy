"""tools/common_mode_gate.py — common-mode / escape gate, per PR (SCALING.md §9,
Phase 7). Reframes the fault-injection experiments (tools/fault_injection.py,
BENCHMARKS.md §6.7) as a per-construct gate.

**The single-leg family (fast lane).** A single-leg defect makes the two legs of
the square disagree, so the square *should* catch it. Seeding the single-leg
mutation family against a touched pair's probes measures exactly that. But — as
the escape experiment found — some single-leg mutations still slip past the
square when the probes do not discriminate them (e.g. `slt->ult` on inputs where
both agree); those are **anchor-required** — only the external differential
catches them, and it runs at the heavier BENCHMARKS cadence, not in the fast
per-PR gate. So the fast lane *reports* the layered outcome (square-caught vs
anchor-required); it does not hard-fail on an anchor-required mutation, which is
not a translator defect.

**The both-leg round (posture).** A both-leg misreading — the same wrong reading
in the reference and the translation (the MUL/ADD common-mode class) — makes the
legs *agree*, so the square is **blind to it by construction**. Only an external
differential, derived from a *different* semantic artifact, catches it. A pair
therefore has one of two common-mode postures:

* **external-differential** — an independent artifact (a Sail model) exists, so
  the both-leg round is catchable; it runs at BENCHMARKS cadence, and a pair's
  anchor-required set must clear it before the merge queue graduates that pair to
  autonomous merge.
* **single-artifact** — only one semantic artifact exists, so a shared misreading
  is uncatchable: the honest residue of SCALING.md §11, made explicit and
  machine-readable here rather than left implicit.

The posture is cheap (a registry lookup) and rides in the PR manifest; the
single-leg family is the richer, pair-specific gate exposed via the CLI.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Languages with an independent external semantic artifact (a Sail model). A pair
# touching one of these has an external differential available for the both-leg
# round; every other pair's common-mode corner is a §11 residue.
_SAIL_MODELED = {"riscv", "aarch64", "sail"}

EXTERNAL = "external-differential"
SINGLE = "single-artifact"


def _load(mod_path: str, name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, ROOT / mod_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _pairs() -> dict:
    """``pair_id -> {source, target}`` from the live registry."""
    pm = _load("tools/pr_manifest.py", "pr_manifest")
    pm._import_all_pairs()
    from gurdy.core import registry
    return {pid: {"source": p.source, "target": p.target}
            for pid, p in registry.list_pairs().items()}


def posture(pair_id: str, pairs: dict | None = None) -> str:
    """A pair's common-mode posture. ``external-differential`` if it touches a
    Sail-modeled language (an independent artifact exists), else ``single-artifact``
    (the common-mode corner is a §11 residue)."""
    pairs = pairs if pairs is not None else _pairs()
    meta = pairs.get(pair_id, {})
    if meta.get("source") in _SAIL_MODELED or meta.get("target") in _SAIL_MODELED:
        return EXTERNAL
    return SINGLE


def single_leg_report(pair_id: str, sites: tuple[int, ...] | None = None,
                      probes: dict | None = None) -> dict:
    """The single-leg mutation family through the pure-python square. Pairs with
    a dedicated fault-injection module (riscv-btor2 today) get the rich family;
    every other pair's single-leg control is the Phase-3 negative control (op-swap
    + truncate), already run by the fast gate. ``sites`` narrows the mutation
    sites and ``probes`` overrides the probe set (both default to the full sets;
    narrowing them trades resolution for speed)."""
    if pair_id != "riscv-btor2":
        return {"family": "negative_control",
                "note": "single-leg control is the Phase-3 negative control "
                        "(op-swap + truncate), already in the fast gate"}
    fi = _load("tools/fault_injection.py", "fault_injection")
    import gurdy.pairs.riscv_btor2  # noqa: F401
    from gurdy.core import registry
    if probes is None:
        probes = registry.get_pair("riscv-btor2").probes
    mutations = fi.mutation_set(sites) if sites is not None else fi.mutation_set()
    caught, anchor_required = [], []
    for m in mutations:
        if not fi._applicable(m, probes):
            continue
        if fi._gate_square(m, probes) is None:      # square blind -> external anchor
            anchor_required.append(m.name)
        else:
            caught.append(m.name)
    return {"family": "fault_injection", "square_caught": len(caught),
            "anchor_required": sorted(anchor_required)}


def assess(pair_id: str, pairs: dict | None = None) -> dict:
    """A pair's full common-mode assessment: posture, the single-leg family
    report, and the both-leg round classification."""
    pairs = pairs if pairs is not None else _pairs()
    p = posture(pair_id, pairs)
    sl = single_leg_report(pair_id)
    both = {
        "square_blind": True,   # a shared misreading makes the legs agree, by construction
        "anchor": ("sail-differential (external; runs at BENCHMARKS cadence)"
                   if p == EXTERNAL
                   else "none — single-artifact common-mode is a declared residue (§11)"),
    }
    return {"pair": pair_id, "posture": p, "single_leg": sl, "both_leg": both}


def requires_anchor_round(pair_id: str, pairs: dict | None = None,
                          report: dict | None = None) -> bool:
    """True iff a touched pair has an external differential *and* single-leg
    mutations that escape the square — so the anchor round must confirm them
    before the merge queue graduates that pair to autonomous merge. ``report``
    reuses an already-computed single-leg report (the family is expensive)."""
    pairs = pairs if pairs is not None else _pairs()
    if posture(pair_id, pairs) != EXTERNAL:
        return False
    report = report if report is not None else single_leg_report(pair_id)
    return bool(report.get("anchor_required"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("assess", help="assess one pair's common-mode posture + single-leg family")
    a.add_argument("pair")
    p = sub.add_parser("posture", help="posture for all pairs (cheap registry lookup)")
    args = ap.parse_args()
    pairs = _pairs()
    if args.cmd == "assess":
        print(json.dumps(assess(args.pair, pairs), indent=2))
        return 0
    if args.cmd == "posture":
        print(json.dumps({pid: posture(pid, pairs) for pid in sorted(pairs)}, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
