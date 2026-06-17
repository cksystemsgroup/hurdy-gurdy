"""Path grading — measured composition (PATHS.md §7; BENCHMARKS.md §6-7).

The merge-triggered path-grader (AGENTS.md §7) runs these checks over the
capped routes a merged pair participates in. Two are implementable with the
deterministic core alone:

- **composed determinism**: a route re-run on the same input yields a
  byte-identical terminal artifact (the determinism ratchet, PATHS.md §2).
- **branch agreement**: when several routes reach the same target from the
  same source, deciding the same question along each must agree (the
  fidelity-raising cross-check, PATHS.md §4 / BENCHMARKS.md §6). With a single
  route this is trivially satisfied; it becomes load-bearing once a branch
  (e.g. the Sail route to BTOR2) exists.

The merge *trigger* and the regression *ratchet* (compare to a baseline) are
orchestration (CI), outside this module; these are the measurements they act on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from . import route as _route


def composed_determinism(route: list[str], head_program: Any,
                         params: dict[str, dict] | None = None) -> bool:
    a = _route.run_route(route, head_program, params)["artifact"]
    b = _route.run_route(route, head_program, params)["artifact"]
    return a == b


@dataclass
class BranchAgreement:
    verdicts: dict[tuple[str, ...], Any]
    agree: bool


def branch_agreement(routes: list[list[str]], head_program: Any,
                     decide: Callable[[bytes], Any],
                     params: dict[str, dict] | None = None) -> BranchAgreement:
    """Decide the same question along each route and check the verdicts agree.

    ``decide`` maps a terminal artifact to a verdict (e.g. the z3 backend's
    verdict for an SMT-LIB artifact). A disagreement means at least one route
    has a defect (localizable per the commuting squares).
    """
    verdicts: dict[tuple[str, ...], Any] = {}
    for r in routes:
        artifact = _route.run_route(r, head_program, params)["artifact"]
        verdicts[tuple(r)] = decide(artifact)
    return BranchAgreement(verdicts, len(set(verdicts.values())) <= 1)
