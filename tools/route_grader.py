#!/usr/bin/env python3
"""The capped route-grader run, wired to the ledger (ROUTES.md §7;
BENCHMARKS.md §6-7; core/ledger.py).

Runs the host-runnable slice of the merge-triggered route-grader —
composed coverage over every probe-carrying source that reaches a
reasoning language, plus a small bridged-decide corpus when z3 is
present — with ``GURDY_LEDGER`` set, so the instrumented call sites
(translate on cache miss, the square oracle, the decide backends) seed
the ledger through exactly the paths they already exercise. Ends by
printing the ledger's profile summary: the measured cost axis the route
report consumes (``gurdy routes --report``).

Caps are explicit and printed (a capped result says so — BENCHMARKS.md
§7): probes per head pair, hops per route, the step bound ``k``. The
corpus is deterministic (sorted, fixed caps); the *timings* are the
point and are host-tagged by the ledger. Coverage regressions are the
merge queue's business, not this runner's: it measures and reports,
exit code 0 unless measurement itself breaks.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Register the full board (the import is the registration).
import gurdy.cli  # noqa: F401,E402  (side-effecting pair imports)

from gurdy.core import grade, ledger, registry  # noqa: E402
from gurdy.core import route as _route  # noqa: E402
from gurdy.core.whynot import reasoning_languages  # noqa: E402


def _z3() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except Exception:
        return False


def _decide_corpus() -> None:
    """A tiny bridged-decide corpus (both verdict polarities) so the
    ledger carries decide profiles, not only translate/cross_check."""
    from gurdy.languages.btor2.build import Builder
    from gurdy.pairs.btor2_smtlib import reach

    def counter(bad_at: int) -> str:
        b = Builder()
        c = b.state(4, "c")
        b.init(c, b.zero(4))
        b.next(c, b.op2("add", 4, c, b.one(4)))
        b.bad(b.op2("eq", 1, c, b.constd(4, bad_at)))
        return b.to_text()

    for bad_at, k in ((2, 5), (9, 5)):  # reachable at 2; unreachable within 5
        verdict = reach(counter(bad_at), k)["verdict"]
        print(f"decide corpus: counter bad@{bad_at} k={k} -> {verdict.value}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sources", help="comma-separated source languages "
                                      "(default: every probe-carrying source)")
    ap.add_argument("--max-probes", type=int, default=24,
                    help="probes per head pair (cap, printed; default 24)")
    ap.add_argument("--max-hops", type=int, default=4,
                    help="route length cap (default 4)")
    ap.add_argument("--k", type=int, default=2,
                    help="step bound seeded into bounded hops (default 2)")
    ap.add_argument("--no-decide", action="store_true",
                    help="skip the bridged-decide corpus even if z3 is present")
    args = ap.parse_args()

    path = ledger.ledger_path()
    if path is None:
        print("route_grader: GURDY_LEDGER is not set — measurements "
              "would be discarded; set it (or ledger.configure) and re-run",
              file=sys.stderr)
        return 2
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    print(f"ledger: {path} (host {ledger.host_id()})")

    hubs = sorted(reasoning_languages())
    wanted = set(args.sources.split(",")) if args.sources else None
    sources = sorted({
        pair.source for pair in registry.list_pairs().values()
        if pair.probes and (wanted is None or pair.source in wanted)
    })

    for src in sources:
        for hub in hubs:
            if src == hub:
                continue
            for r in _route.routes(src, hub, max_hops=args.max_hops):
                head = registry.get_pair(r[0])
                probes = dict(sorted((head.probes or {}).items())[:args.max_probes])
                if not probes:
                    continue
                report = grade.composed_coverage(r, probes, k=args.k)
                capped = (f" (capped {len(probes)}/{len(head.probes)})"
                          if len(probes) < len(head.probes or {}) else "")
                print(f"{' -> '.join(r)}: {len(report.covered)}/{report.total}"
                      f"{capped}")

    if not args.no_decide and _z3():
        _decide_corpus()
    elif not args.no_decide:
        print("decide corpus: skipped (z3 not installed)")

    print("\n--- ledger profiles (this host) ---")
    for kind, field in (("translate", "pair"), ("cross_check", "pair"),
                        ("decide", "engine")):
        for value, prof in ledger.profiles_by(field, kind).items():
            print(f"{kind}[{value}]\tn={prof['n']}"
                  f"\tmedian={prof['wall_median_s']}s"
                  f"\tp90={prof['wall_p90_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
