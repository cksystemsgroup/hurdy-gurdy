"""CLI of the second lineage (kernel-second-g1): the pure half only.

    python3 -m kernel.second.driver base   [--registry DIR]
    python3 -m kernel.second.driver report <run-dir> [--registry DIR]
    python3 -m kernel.second.driver graph  <run-dir> [--registry DIR]

``base`` prints the trusted base; ``report`` prints the board
(frontier.md) and ``graph`` the graph (frontier.dot) of a run to stdout.
Nothing is written to disk, nothing is executed.  A registry entry whose
pin does not verify, or a benchmark program that violates its pin, is a
hard error: a message on stderr and exit status 1.
"""

import argparse
import sys

from . import registry as REG
from . import render
from . import runs


def _emit(text):
    out = getattr(sys.stdout, "buffer", None)
    if out is not None:
        out.write(text.encode("utf-8"))
        out.flush()
    else:
        sys.stdout.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m kernel.second.driver")
    sub = parser.add_subparsers(dest="command", required=True)
    p_base = sub.add_parser("base", help="print the trusted base (admitted judges)")
    p_base.add_argument("--registry", default="registry")
    p_report = sub.add_parser("report", help="print the board (frontier.md) of a run")
    p_report.add_argument("run_dir")
    p_report.add_argument("--registry", default="registry")
    p_graph = sub.add_parser("graph", help="print the graph (frontier.dot) of a run")
    p_graph.add_argument("run_dir")
    p_graph.add_argument("--registry", default="registry")
    args = parser.parse_args(argv)
    try:
        registry = REG.load_registry(args.registry)
        if args.command == "base":
            _emit(render.base(registry))
            return 0
        benchmark = runs.load_benchmark(args.run_dir)
        log = runs.load_log(args.run_dir)
        if args.command == "report":
            _emit(render.board(registry, benchmark, log))
        else:
            _emit(render.graph(registry, benchmark, log))
        return 0
    except (REG.RegistryError, runs.BenchmarkError) as e:
        sys.stderr.write(f"kernel.second: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
