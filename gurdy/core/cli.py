"""gurdy CLI entry point.

Phase 0 stub: just prints a help message. Subcommands are wired up in
phase 4.
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gurdy",
        description=(
            "hurdy-gurdy: deterministic translations from source languages "
            "to reasoning languages, for use by external solvers and LLMs."
        ),
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print package version and exit",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("describe", help="show a schema entry for a topic in a pair")
    sub.add_parser("compile", help="compile a (spec, source) into a layered artifact")
    sub.add_parser("dispatch", help="run a single solver against a compiled artifact")
    sub.add_parser("lift", help="lift a raw solver result through the annotation")
    sub.add_parser("introspect", help="query the annotation of a compiled artifact")
    sub.add_parser("pairs", help="list registered pairs")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from gurdy import __version__

        print(__version__)
        return 0
    if args.command is None:
        parser.print_help()
        return 0
    # Phase 0 stub: subcommands not yet wired.
    print(
        f"gurdy: subcommand '{args.command}' is not yet implemented in this build.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
