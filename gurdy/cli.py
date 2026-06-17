"""The ``gurdy`` CLI — a thin player surface over the framework
(FRAMEWORK.md §2 "Player surface"; INTERFACE.md).

MVP-1 exposes registry introspection and the square edges for the demo pair:
``pairs``, ``languages``, ``compile``, ``decide``, ``align``. The MCP server
and the full per-pair generic surface are later increments.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from . import __version__
from .core import cache, oracle, registry

# Importing the demo registers a trivial pair so the CLI has something to show
# before the real per-pair agents have built anything.
from . import demo  # noqa: F401  (side-effecting registration)

# Real registered pairs, so `gurdy pairs` / `languages` reflect what's built.
from .pairs import btor2_smtlib  # noqa: F401  (side-effecting registration)
from .pairs import riscv_btor2  # noqa: F401  (side-effecting registration)


def _parse_program(pair: registry.Pair, raw: str) -> Any:
    # MVP-1: the demo source is an integer. A real pair supplies its own loader.
    try:
        return int(raw, 0)
    except ValueError:
        return raw


def cmd_pairs(_args: argparse.Namespace) -> int:
    for pid, pair in sorted(registry.list_pairs().items()):
        print(f"{pid}\t{pair.source} -> {pair.target}\t{pair.fidelity}\t{pair.status.value}")
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

    p_compile = sub.add_parser("compile", help="translate a program (square edge T)")
    p_compile.add_argument("pair")
    p_compile.add_argument("program")
    p_compile.set_defaults(func=cmd_compile)

    p_decide = sub.add_parser("decide", help="compile then decide via z3")
    p_decide.add_argument("pair")
    p_decide.add_argument("program")
    p_decide.set_defaults(func=cmd_decide)

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
