"""The ``gurdy`` CLI — a thin player surface over the framework
(FRAMEWORK.md §2 "Player surface"; INTERFACE.md).

Registry introspection and the square edges (``pairs``, ``languages``,
``compile``, ``decide``, ``align``, coverage and route coverage), plus the
advisory reads over the registry and the ledger: ``routes --report``,
``why-not``, ``trust-options``, ``suggest-reduction``, and
``recommendations`` (INTERFACE.md §2A) — all enumerate, annotate, and
account; none chooses. The MCP server mirror is a later increment.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from . import __version__
from .core import cache, oracle, registry, route

# Importing the demo registers a trivial pair so the CLI has something to show
# before the real per-pair agents have built anything.
from . import demo  # noqa: F401  (side-effecting registration)

# Real registered pairs, so `gurdy pairs` / `languages` / `routes` /
# `why-not` reflect the whole registry (the import is the registration).
from .pairs import aarch64_btor2  # noqa: F401  (side-effecting registration)
from .pairs import aarch64_sail  # noqa: F401  (side-effecting registration)
from .pairs import btor2_havoc  # noqa: F401  (side-effecting registration)
from .pairs import btor2_smtlib  # noqa: F401  (side-effecting registration)
from .pairs import c_riscv  # noqa: F401  (side-effecting registration)
from .pairs import crn_smtlib  # noqa: F401  (side-effecting registration)
from .pairs import ebpf_btor2  # noqa: F401  (side-effecting registration)
from .pairs import evm_btor2  # noqa: F401  (side-effecting registration)
from .pairs import python_smtlib  # noqa: F401  (side-effecting registration)
from .pairs import riscv_btor2  # noqa: F401  (side-effecting registration)
from .pairs import riscv_sail  # noqa: F401  (side-effecting registration)
from .pairs import sail_btor2  # noqa: F401  (side-effecting registration)
from .pairs import smiles_formula  # noqa: F401  (side-effecting registration)
from .pairs import wasm_btor2  # noqa: F401  (side-effecting registration)


def _parse_program(pair: registry.Pair, raw: str) -> Any:
    # MVP-1: the demo source is an integer. A real pair supplies its own loader.
    try:
        return int(raw, 0)
    except ValueError:
        return raw


def cmd_pairs(_args: argparse.Namespace) -> int:
    for pid, pair in sorted(registry.list_pairs().items()):
        print(f"{pid}\t{pair.source} -> {pair.target}\t{pair.fidelity}\t{pair.direction}\t{pair.status.value}")
    return 0


def cmd_languages(_args: argparse.Namespace) -> int:
    for lid, lang in sorted(registry.list_languages().items()):
        roles = []
        if lang.source_interpreter:
            roles.append("source")
        if lang.target_interpreter:
            roles.append("target")
        print(f"{lid}\t{','.join(roles) or '-'}\t{lang.status.value}")
    return 0


def cmd_routes(args: argparse.Namespace) -> int:
    if not (args.report or args.observables or args.shape):
        found = route.routes(args.source, args.target)
        if not found:
            print(f"(no route from {args.source} to {args.target})")
            return 0
        for r in found:
            print(" -> ".join(r))
        return 0
    observables = args.observables.split(",") if args.observables else None
    report = route.route_report(args.source, args.target,
                                observables=observables, shape=args.shape)
    if not report:
        print(f"(no route from {args.source} to {args.target})")
        return 0
    for e in report:
        line = (f"{' -> '.join(e['route'])}\t{e['fidelity']}/{e['assurance']}"
                f"\t{e['direction']}")
        cost = e["cost"]
        line += (f"\ttranslate~{cost['translate_total_median_s']}s"
                 if cost["measured"] else "\tcost:unmeasured")
        if "feasibility" in e:
            line += f"\tfeasible={e['feasibility']['feasible']}"
            if e["feasibility"].get("observables_missing"):
                line += f" (drops {','.join(e['feasibility']['observables_missing'])})"
        if e["dominated_by"]:
            line += f"\tdominated-by: {'; '.join(e['dominated_by'])}"
        print(line)
        for engine, prof in cost["decide"].items():
            print(f"  decide[{engine}]\tn={prof['n']}\tmedian={prof['wall_median_s']}s"
                  f"\tp90={prof['wall_p90_s']}s")
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    from .core.coverage import measure

    pair = registry.get_pair(args.pair)
    if not pair.probes:
        print(f"{args.pair}: no coverage inventory")
        return 0
    report = measure(pair.translator, pair.probes)
    print(f"coverage {len(report.covered)}/{report.total} = {report.fraction:.0%}")
    if report.missing:
        print("missing:")
        for name, construct in sorted(report.missing.items()):
            print(f"  {name}\t{construct}")
    return 0


def cmd_route_coverage(args: argparse.Namespace) -> int:
    from .core import grade

    reports = grade.composed_coverage_by_route(args.source, args.target, k=args.k)
    if not reports:
        print(f"(no route from {args.source} to {args.target})")
        return 0
    for route_ids, report in reports.items():
        print(f"{' -> '.join(route_ids)}\t{len(report.covered)}/{report.total} = "
              f"{report.fraction:.0%}")
        for name, where in sorted(report.missing.items()):
            print(f"  miss\t{name}\t{where}")
    return 0


def cmd_why_not(args: argparse.Namespace) -> int:
    import json as _json

    from .core.whynot import why_not

    observables = args.observables.split(",") if args.observables else None
    record = why_not(args.source, observables, args.shape,
                     verdict=args.verdict, origin=args.origin)
    if args.json:
        print(_json.dumps(record, indent=2, default=str))
        return 0
    if record["answerable"]:
        print(f"answerable: {len(record['routes'])} feasible route(s)")
        for e in record["routes"]:
            print(f"  {' -> '.join(e['route'])}\t{e['fidelity']}/{e['assurance']}"
                  f"\t{e['direction']}")
        return 0
    print(f"unanswerable: obstacle={record['obstacle']}")
    target = record["generation_target"]
    print(f"generation target: {target['kind']}")
    for k, v in target.items():
        if k != "kind":
            print(f"  {k}: {v}")
    if args.brief_stub and "brief_stub" in record:
        print()
        print(record["brief_stub"])
    return 0


def cmd_recommendations(args: argparse.Namespace) -> int:
    import json as _json

    from .core import ledger

    board = ledger.demand_summary()
    if args.json:
        print(_json.dumps(board, indent=2))
        return 0
    if not board:
        print("(no demand recorded — set GURDY_LEDGER and run questions "
              "through why-not / trust-options)")
        return 0
    for e in board:
        target = e["target"] or {}
        name = target.get("kind", "(none)")
        detail = {k: v for k, v in target.items() if k not in ("kind", "note")}
        origins = ", ".join(f"{o}:{n}" for o, n in e["origins"].items())
        print(f"{name}\t{'/'.join(e['currencies']) or '?'}"
              f"\tquestions={e['distinct_questions']}\torigins: {origins}")
        for k, v in sorted(detail.items()):
            print(f"  {k}: {v}")
    print("\nevidence volume only — choosing what to build stays the human "
          "act of AGENTS.md §1; a brief cites the records behind its row")
    return 0


def cmd_trust_options(args: argparse.Namespace) -> int:
    import json as _json

    from .core.trust import trust_options

    record = trust_options(args.source, args.target, floor=args.floor,
                           origin=args.origin)
    if args.json:
        print(_json.dumps(record, indent=2))
        return 0
    for e in record["routes"]:
        line = (f"{' -> '.join(e['route'])}\t{e['fidelity']}/{e['assurance']}"
                f"\tanchors: {', '.join(e['anchors']) or '(undeclared)'}")
        if e["undeclared_pairs"]:
            line += f"\tundeclared: {','.join(e['undeclared_pairs'])}"
        print(line)
    for b in record["branches"]:
        verdict = {True: "independent", False: "NOT independent",
                   None: "unknown"}[b["independent"]]
        print(f"branch: [{b['a']}] x [{b['b']}] -> {verdict}"
              + (f" (shared anchors: {', '.join(b['shared_anchors'])})"
                 if b["shared_anchors"] else "")
              + (f" (undeclared: {', '.join(b['undeclared_pairs'])})"
                 if b["undeclared_pairs"] else ""))
    if record.get("met_by"):
        print(f"floor {record['floor']}: met by {len(record['met_by'])} route(s)")
    elif record["floor"]:
        print(f"floor {record['floor']}: NOT met by any route's declared grade")
    if "corroboration" in record:
        print(f"corroboration available: {record['corroboration']['note']}")
    target = record.get("generation_target")
    if target:
        print(f"generation target: {target['kind']}")
        for k, v in target.items():
            if k != "kind":
                print(f"  {k}: {v}")
    return 0


def cmd_suggest_reduction(args: argparse.Namespace) -> int:
    import json as _json

    from .languages.btor2.coi import suggest_reduction

    with open(args.system, encoding="utf-8") as f:
        text = f.read()
    report = suggest_reduction(text, k=args.k, samples=args.samples)
    if args.json:
        print(_json.dumps(report, indent=2))
        return 0
    print(f"cone (state: distance): {report['cone'] or '(empty)'}")
    print(f"free havoc set: {report['free_havoc'] or '(none)'}")
    if report["free_array_states"]:
        print(f"free array states (not havocable): {report['free_array_states']}")
    print(f"refinement ladder (farthest first): {report['refinement_ladder'] or '(none)'}")
    for lbl, (lo, hi) in report["interval_seeds"].items():
        print(f"interval seed: {lbl} in [{lo}, {hi}]")
    print(f"note: {report['note']}")
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    pair = registry.get_pair(args.pair)
    artifact = cache.compile(pair, _parse_program(pair, args.program))
    sys.stdout.write(artifact.decode("utf-8", errors="replace"))
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    from .solvers.z3_smt import Z3SmtBackend

    pair = registry.get_pair(args.pair)
    artifact = cache.compile(pair, _parse_program(pair, args.program))
    result = Z3SmtBackend().decide(artifact)
    print(f"verdict={result.verdict.value}")
    if result.model is not None:
        print(f"model={result.model}")
    print(f"provenance={result.provenance}")
    return 0


def cmd_riscv_diff(args: argparse.Namespace) -> int:
    from .languages.riscv.differential import OracleUnavailable, differential

    subject = None
    if args.subject == "sail":
        from .languages.sail.differential import sail_subject
        subject = sail_subject
    with open(args.elf, "rb") as f:
        data = f.read()
    try:
        result = differential(elf_bytes=data, subject=subject, entry_symbol=args.entry)
    except OracleUnavailable as e:
        print(f"oracle unavailable: {e}")
        return 2
    if result.ok:
        print("differential=ok")
        return 0
    print(f"differential=FAIL {result.divergence}")
    return 1


def cmd_c_diff(args: argparse.Namespace) -> int:
    from .pairs.c_riscv.differential import differential
    from .solvers.cbmc_c import CbmcUnavailable

    try:
        result = differential(args.expr, args.value, k=args.k)
    except CbmcUnavailable as e:
        print(f"cbmc unavailable: {e}")
        return 2
    print(f"status={result['status']}  cbmc={result['cbmc'].value}  "
          f"long-route={result['reference'].value}  agree={result['agree']}")
    if result["ub_classes"]:
        print(f"c-undefined-but-riscv-defined: {', '.join(result['ub_classes'])}")
    return 1 if result["fault"] else 0


def cmd_riscv_suite(args: argparse.Namespace) -> int:
    from .languages.riscv.suite import discover, run_suite

    if not discover(args.dir):
        print(f"no test ELFs found under {args.dir}")
        return 2
    report = run_suite(args.dir, max_steps=args.max_steps)
    print(report.summary())
    for r in report.results:
        if r.status != "pass":
            print(f"  {r.status}\t{r.name}\t{r.detail}")
    return 0 if report.ok else 1


def cmd_align(args: argparse.Namespace) -> int:
    from .solvers.z3_smt import Z3SmtBackend

    pair = registry.get_pair(args.pair)
    program = _parse_program(pair, args.program)
    artifact = cache.compile(pair, program)
    result = Z3SmtBackend().decide(artifact)
    if result.verdict is not result.verdict.REACHABLE:
        print(f"verdict={result.verdict.value} (no model to align)")
        return 0
    target_trace = pair.target_interpreter(result.model)
    carried = pair.target_to_source(target_trace)
    source_trace = pair.source_interpreter(program)
    report = oracle.align(source_trace, carried, pair.projection)
    if report.ok:
        print("align=ok")
        return 0
    print(f"align=FAIL {report.divergence}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gurdy", description="hurdy-gurdy framework CLI (MVP-1)")
    parser.add_argument("--version", action="version", version=f"gurdy {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("pairs", help="list registered pairs").set_defaults(func=cmd_pairs)
    sub.add_parser("languages", help="list registered languages").set_defaults(func=cmd_languages)

    p_routes = sub.add_parser("routes", help="enumerate routes between two languages")
    p_routes.add_argument("source")
    p_routes.add_argument("target")
    p_routes.add_argument("--report", action="store_true",
                          help="annotate each route with fidelity/assurance, "
                               "direction, measured cost (GURDY_LEDGER), "
                               "and Pareto-dominance marks")
    p_routes.add_argument("--observables",
                          help="comma-separated observables the question reads "
                               "(feasibility check against the head projection)")
    p_routes.add_argument("--shape",
                          help="question shape (feasibility check against the "
                               "target language's declared solver shapes)")
    p_routes.set_defaults(func=cmd_routes)

    p_wn = sub.add_parser(
        "why-not",
        help="diagnose why a question is unanswerable; the failure names "
             "the missing edge (POTENTIAL.md §1-2)")
    p_wn.add_argument("source", help="the question's source language")
    p_wn.add_argument("--observables",
                      help="comma-separated observables the question reads")
    p_wn.add_argument("--shape", help="question shape (e.g. reachability)")
    p_wn.add_argument("--verdict",
                      choices=["unknown", "resource-out"],
                      help="a decide outcome the player got (fires the cost "
                           "obstacle)")
    p_wn.add_argument("--brief-stub", action="store_true",
                      help="print the draft registration brief for a "
                           "pair-shaped generation target")
    p_wn.add_argument("--json", action="store_true",
                      help="emit the full machine-readable demand record")
    p_wn.add_argument("--origin", choices=["organic", "campaign"],
                      default="organic",
                      help="how this question arose (recorded with the "
                           "demand; campaigns are displayed apart)")
    p_wn.set_defaults(func=cmd_why_not)

    p_rec = sub.add_parser(
        "recommendations",
        help="the books' demand side, aggregated per generation target — "
             "the evidence a pair recommendation rests on (AGENTS.md §1)")
    p_rec.add_argument("--json", action="store_true",
                       help="emit the full machine-readable board")
    p_rec.set_defaults(func=cmd_recommendations)

    p_sr = sub.add_parser(
        "suggest-reduction",
        help="advisory abstraction parameters for a BTOR2 system: cone of "
             "influence, free havoc set, refinement ladder, interval seeds")
    p_sr.add_argument("system", help="path to a .btor2 file")
    p_sr.add_argument("--k", type=int, default=8,
                      help="steps for the observed-bounds runs (default 8)")
    p_sr.add_argument("--samples", type=int, default=4,
                      help="seeded random-input runs for the bounds (default 4)")
    p_sr.add_argument("--json", action="store_true",
                      help="emit the full machine-readable report")
    p_sr.set_defaults(func=cmd_suggest_reduction)

    p_to = sub.add_parser(
        "trust-options",
        help="the trust ledger for a source->target question: branch "
             "independence, anchor census, and what would raise trust")
    p_to.add_argument("source")
    p_to.add_argument("target")
    p_to.add_argument("--floor",
                      help="the assurance the player wants (a grade like "
                           "'proved' or a class like 'universal')")
    p_to.add_argument("--json", action="store_true",
                      help="emit the full machine-readable record")
    p_to.add_argument("--origin", choices=["organic", "campaign"],
                      default="organic",
                      help="how this question arose (recorded with an "
                           "unmet-floor demand)")
    p_to.set_defaults(func=cmd_trust_options)

    p_coverage = sub.add_parser("coverage", help="construct-coverage of a pair")
    p_coverage.add_argument("pair")
    p_coverage.set_defaults(func=cmd_coverage)

    # "path-coverage" is the deprecated pre-rename alias (ROUTES.md).
    p_pcov = sub.add_parser("route-coverage", aliases=["path-coverage"],
                            help="composed construct coverage per route")
    p_pcov.add_argument("source")
    p_pcov.add_argument("target")
    p_pcov.add_argument("--k", type=int, default=1, help="step bound for reasoning hops")
    p_pcov.set_defaults(func=cmd_route_coverage)

    p_compile = sub.add_parser("compile", help="translate a program (square edge T)")
    p_compile.add_argument("pair")
    p_compile.add_argument("program")
    p_compile.set_defaults(func=cmd_compile)

    p_decide = sub.add_parser("decide", help="compile then decide via z3")
    p_decide.add_argument("pair")
    p_decide.add_argument("program")
    p_decide.set_defaults(func=cmd_decide)

    p_diff = sub.add_parser("riscv-diff", help="differential: an interp vs sail_riscv_sim")
    p_diff.add_argument("elf", help="path to a RISC-V ELF image")
    p_diff.add_argument("--subject", choices=["riscv", "sail"], default="riscv",
                        help="which interpreter to validate against the oracle")
    p_diff.add_argument("--entry", default=None, help="start at this symbol")
    p_diff.set_defaults(func=cmd_riscv_diff)

    p_cdiff = sub.add_parser(
        "c-diff", help="c-riscv differential: long route vs cbmc on the same C")
    p_cdiff.add_argument("expr", help="a C expression computed into a0 (e.g. '5*8+7')")
    p_cdiff.add_argument("value", type=lambda s: int(s, 0), help="the a0 value to decide")
    p_cdiff.add_argument("--k", type=int, default=6, help="unrolling bound for the long route")
    p_cdiff.set_defaults(func=cmd_c_diff)

    p_suite = sub.add_parser("riscv-suite", help="run a riscv-tests/-arch-test ELF dir")
    p_suite.add_argument("dir", help="directory of compliance-test ELFs")
    p_suite.add_argument("--max-steps", type=int, default=1_000_000, dest="max_steps")
    p_suite.set_defaults(func=cmd_riscv_suite)

    p_align = sub.add_parser("align", help="run the commuting-square check")
    p_align.add_argument("pair")
    p_align.add_argument("program")
    p_align.set_defaults(func=cmd_align)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
