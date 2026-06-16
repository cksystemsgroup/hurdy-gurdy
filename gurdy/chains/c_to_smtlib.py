"""The worked route  C -> rv64-elf -> btor2 -> smt-lib.

Demonstrates: all three hop kinds, the meet-composition of trust, and the
two reasoning paths at the ``riscv_btor2`` node. Core enumerates the route;
*choosing* the path is the caller's (LLM's) job — here we just show both.
"""

from __future__ import annotations

import gurdy.hops  # noqa: F401  (registers the hops)
from gurdy.core.route import Route, routes


def the_route() -> Route:
    cands = routes("c", "smt-lib")
    if not cands:
        raise RuntimeError("no route c -> smt-lib; are the hops registered?")
    return cands[0]


def describe() -> str:
    r = the_route()
    lines = [
        f"route: {r}",
        "",
        "at riscv_btor2 the caller picks a reasoning path:",
        "  - own     : independent specializing lowering (validates Sail)",
        "  - machine : instantiate the verified BTOR2 machine (trusted; needed",
        "              for symbolic control flow / self-modifying code)",
        "  - cross_check: run both, assert agreement on the projection",
        "",
        f"chain trust (meet of hops): {r.trust.label}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
