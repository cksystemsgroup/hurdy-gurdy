#!/usr/bin/env python3
"""Re-discharge a campaign's unbounded closures — the after-the-batch
obligation the pono/avr briefs declare (languages/btor2/README.md,
amended 2026-07-25/26; issue #2 route (b)): every ``bounded: false``
closure on a campaign's books gets its inductive invariant re-derived
(``--show-invar``) and checked through **both** certificate routes —

* invariant re-discharge (``gurdy/solvers/invariant.py``): the three
  obligations as self-contained QF_ABV scripts, decided by every
  available SMT engine, independent only across declared lineages;
* certifaiger witness circuits (``gurdy/solvers/certifaiger.py``): the
  same invariant compiled into an AIGER witness circuit and validated
  by certifaiger's kissat harness.

One extraction feeds both routes — the amendment's own reading ("same
witness, two checkers on disjoint trust bases"): either alone
certifies, running both corroborates the certificate across trust
bases.

**Discovery** walks ``WORKDIR/iterations.jsonl``: an instance whose
verdict in any iteration is ``bounded: false`` with claim
``unreachable-unbounded`` is a standing closure — a later
``resource-out`` does not erase it (the books are cumulative; a later
portfolio's failure to re-prove is that portfolio's coverage, not a
retraction), but a later ``reachable`` is a contradiction and this
tool refuses to certify anything until it is resolved.

**Generators are untrusted** (the module docstrings' discipline), so
the invariant need not come from the closing mode: the pool is the
closer first (when it can print one) then the brief's declared
unbounded modes that can, each attempted at most once at the declared
wall — the walls are budgets, not free retries. pono's ``ind`` cannot
print an invariant (measured on the pinned v2.0.0 c81aa36 build,
2026-07-26: "Engine ind does not support getting the invariant"), so
an ``ind`` closure re-derives through the others; a closure by AVR
re-derives through pono (the avr brief's own wording). Once a mode
yields an invariant, the routes' verdict on it is final for this run —
shopping for a friendlier invariant after a refutation would bury the
refutation.

**Booking**: one ``kind: "certificate"`` event per closure appended to
``WORKDIR/books.jsonl`` in the ledger's field discipline
(core/ledger.py) — the typed outcome lands whether or not a
certificate was obtained (fetch-offline, no-invariant, wall-spent,
checker-unavailable, refuted are recorded, never silent). The
saturation report is a pure function of ``iterations.jsonl``
(tools/saturation_report.py), so certificate events never disturb its
byte-identical regen.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gurdy.core.benchmark import Benchmark, fetch  # noqa: E402
from gurdy.core.errors import Unsupported  # noqa: E402
from gurdy.solvers.certifaiger import (  # noqa: E402
    CertifaigerUnavailable,
    check_witness_circuit,
    emit_certificate,
    find_certifaiger,
)
from gurdy.solvers.invariant import (  # noqa: E402
    extract_invariant,
    redischarge_invariant,
)
from gurdy.solvers.pono_btor2 import UNBOUNDED_MODES, UNBOUNDED_WALL_S  # noqa: E402

#: Modes whose ``--show-invar`` prints no invariant — measured on the
#: pinned pono build (v2.0.0 c81aa36, 2026-07-26): the run still proves,
#: then prints "Engine ind does not support getting the invariant".
#: Spending a declared wall on a known-silent generator is not honesty,
#: it is waste; the closure re-derives through the remaining pool.
NO_INVAR_MODES = ("ind",)


def discover_closures(iterations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The standing unbounded closures of a campaign: per instance, the
    latest iteration whose verdict is ``bounded: false`` with claim
    ``unreachable-unbounded``. Any ``reachable`` verdict on the same
    instance — before or after — is a contradiction: raise, certify
    nothing (a disagreement is frontier_loop's event, not this tool's
    to paper over)."""
    closures: dict[str, dict[str, Any]] = {}
    contradicted: dict[str, int] = {}
    for rec in iterations:
        it = rec.get("iteration")
        for name, v in (rec.get("verdicts") or {}).items():
            if v.get("verdict") == "reachable":
                contradicted[name] = it
            if (v.get("bounded") is False
                    and v.get("claim") == "unreachable-unbounded"):
                closures[name] = {"instance": name, "iteration": it,
                                  "engine": v.get("engine"),
                                  "mode": v.get("mode"),
                                  "wall_s": v.get("wall_s")}
    both = sorted(set(closures) & set(contradicted))
    if both:
        raise ValueError(
            f"contradicted closure(s) {both}: an unbounded unreachable and "
            f"a reachable verdict share an instance — resolve the "
            f"disagreement before certifying")
    return [closures[name] for name in sorted(closures)]


def generator_pool(closure: dict[str, Any],
                   derive_modes: tuple[str, ...]) -> tuple[list[str], list[dict]]:
    """The invariant-generator modes for one closure, in order, each at
    most once: the closing mode first (only a pono mode that can print),
    then the declared derivation pool. Returns the pool and the typed
    non-attempts (a closer that cannot print is recorded, not spent)."""
    pool: list[str] = []
    skipped: list[dict] = []
    mode, engine = closure.get("mode"), closure.get("engine")
    if engine == "pono" and mode:
        if mode in NO_INVAR_MODES:
            skipped.append({"mode": mode, "outcome": "closer-cannot-print",
                            "note": "pono prints no invariant for this "
                                    "engine (--show-invar, measured); "
                                    "re-deriving through the pool"})
        else:
            pool.append(mode)
    for m in derive_modes:
        if m not in pool and m not in NO_INVAR_MODES:
            pool.append(m)
    return pool, skipped


def _derive_invariants(text: str, n_bads: int, pool: list[str],
                       wall_s: int) -> tuple[list[str] | None, str | None,
                                             list[dict]]:
    """Walk the generator pool until one mode yields an invariant for
    every bad property (pono is per-property; the claim is any-bad).
    Returns (invariants, generator mode, the spent-attempt records)."""
    spent: list[dict] = []
    for mode in pool:
        invs: list[str] = []
        outcome = "invariant"
        t0 = time.perf_counter()
        for prop in range(n_bads):
            try:
                inv = extract_invariant(text, mode=mode, prop=prop,
                                        timeout_s=wall_s)
            except subprocess.TimeoutExpired:
                outcome = "wall-spent"
                break
            if inv is None:
                outcome = "no-invariant"
                break
            invs.append(inv)
        spent.append({"mode": mode, "outcome": outcome,
                      "wall_s": round(time.perf_counter() - t0, 3)})
        if outcome == "invariant":
            return invs, mode, spent
    return None, None, spent


def _route_smt(text: str, invariants: list[str]) -> dict[str, Any]:
    results = [redischarge_invariant(text, inv, prop=p)
               for p, inv in enumerate(invariants)]
    ok = all(r.ok for r in results)
    indep = ok and all(r.independent for r in results)
    engines = sorted(set.intersection(*(set(r.engines) for r in results))
                     ) if results else []
    return {"ok": ok, "independent": indep,
            "tier": "proved" if ok and indep else
                    ("reproducible" if ok else None),
            "engines": engines,
            "refuted": sorted(f"p{p}/{name}" for p, r in enumerate(results)
                              for name in r.refuted),
            "obligations": {f"p{p}/{name}": per
                            for p, r in enumerate(results)
                            for name, per in r.obligations.items()}}


def _route_aiger(text: str, invariants: list[str],
                 check_wall_s: int) -> dict[str, Any]:
    try:
        model, witness = emit_certificate(text, invariants)
    except Unsupported as e:
        return {"ok": False, "tier": None, "gap": f"bitblast-unsupported: {e}"}
    try:
        ok, prov = check_witness_circuit(model, witness,
                                         timeout_s=check_wall_s)
    except CertifaigerUnavailable as e:
        return {"ok": False, "tier": None, "gap": f"checker-unavailable: {e}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "tier": None, "gap": "checker-wall-spent"}
    return {"ok": ok, "tier": "proved" if ok else None,
            "checker": prov.get("checker"),
            "checker_exit": prov.get("checker_exit"),
            "checker_output": prov.get("checker_output", "")[-200:]}


def _book(books_path: str, event: dict[str, Any]) -> None:
    rec = {"kind": "certificate", "host":
           f"{platform.system()}-{platform.machine()}-cpus{os.cpu_count()}",
           "ts": round(time.time(), 3), **event}
    with open(books_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def certify_closure(bench: Benchmark, closure: dict[str, Any], *,
                    derive_modes: tuple[str, ...], wall_s: int,
                    check_wall_s: int,
                    cache_dir: str | None = None) -> dict[str, Any]:
    """One closure through both routes; returns the bookable event."""
    from gurdy.languages.btor2.model import from_text

    name = closure["instance"]
    inst = next(i for i in bench.instances if i.name == name)
    event: dict[str, Any] = {
        "key": inst.sha256, "suite": bench.suite,
        "question": inst.question.asdict(),
        "claim": "unreachable-unbounded", "closure": closure,
    }
    data = fetch(bench, name, cache_dir=cache_dir)
    if data is None:
        return {**event, "ok": False, "tier": None, "gap": "fetch-offline"}
    text = data.decode("utf-8")
    pool, skipped = generator_pool(closure, derive_modes)
    invs, generator, spent = _derive_invariants(
        text, len(from_text(text).bads()), pool, wall_s)
    event["modes_spent"] = skipped + spent
    if invs is None:
        return {**event, "ok": False, "tier": None,
                "gap": "no-certificate — no generator in the declared pool "
                       "yielded an invariant within its wall"}
    event["generator"] = generator
    event["invariant"] = invs[0] if len(invs) == 1 else invs
    routes = {"invariant-redischarge": _route_smt(text, invs),
              "certifaiger": _route_aiger(text, invs, check_wall_s)}
    event["routes"] = routes
    smt, aig = routes["invariant-redischarge"], routes["certifaiger"]
    ok = bool(smt["ok"] or aig["ok"])
    tiers = [t for t in (smt.get("tier"), aig.get("tier")) if t]
    tcb: list[str] = []
    if smt["ok"]:
        tcb += [f"{e}:re-discharge" for e in smt["engines"]]
        tcb += ["btor2-smtlib:operator-mapping"]
    if aig["ok"]:
        tcb += ["hurdy-gurdy:btor2-aiger-bitblast",
                "certifaiger:witness-circuit", "kissat:sat"]
    return {**event, "ok": ok,
            "tier": ("proved" if "proved" in tiers else
                     (tiers[0] if tiers else None)),
            "corroborated": bool(smt["ok"] and aig["ok"]), "tcb": tcb}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("benchmark", help="pin file (benchmarks/<suite>.json)")
    ap.add_argument("workdir", help="campaign workdir holding "
                                    "iterations.jsonl + books.jsonl")
    ap.add_argument("--wall", type=int, default=UNBOUNDED_WALL_S,
                    help="per-mode extraction wall (the declared budget)")
    ap.add_argument("--check-wall", type=int, default=600,
                    help="certifaiger check wall")
    ap.add_argument("--modes", nargs="*", default=list(UNBOUNDED_MODES),
                    help="derivation pool after the closer (non-printing "
                         "modes are excluded automatically)")
    ap.add_argument("--instance", action="append", default=None,
                    help="restrict to named closure(s)")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="discover and print, run nothing, book nothing")
    args = ap.parse_args(argv)

    with open(args.benchmark, encoding="utf-8") as f:
        bench = Benchmark.from_json(f.read())
    with open(os.path.join(args.workdir, "iterations.jsonl")) as f:
        iterations = [json.loads(ln) for ln in f if ln.strip()]
    closures = discover_closures(iterations)
    if args.instance:
        closures = [c for c in closures if c["instance"] in args.instance]
    print(f"{len(closures)} standing unbounded closure(s):")
    for c in closures:
        print(f"  {c['instance']}: iteration {c['iteration']}, "
              f"{c['engine']}/{c['mode']}, {c['wall_s']}s")
    if args.dry_run:
        return 0
    if not find_certifaiger():
        print("note: certifaiger-check unavailable — the SMT route decides "
              "alone, the checker route books its typed gap")

    books = os.path.join(args.workdir, "books.jsonl")
    certified = 0
    for c in closures:
        event = certify_closure(
            bench, c, derive_modes=tuple(args.modes), wall_s=args.wall,
            check_wall_s=args.check_wall, cache_dir=args.cache_dir)
        _book(books, event)
        certified += bool(event["ok"])
        tag = (f"CERTIFIED tier={event['tier']}"
               f"{' corroborated' if event.get('corroborated') else ''}"
               if event["ok"] else f"uncertified — {event.get('gap', 'see routes')}")
        print(f"  {c['instance']}: {tag}")
    print(f"certified {certified}/{len(closures)}; events appended to {books}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
