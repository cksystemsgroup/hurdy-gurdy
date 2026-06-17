"""Path grading — measured composition (PATHS.md §7; BENCHMARKS.md §6-7).

The merge-triggered path-grader (AGENTS.md §7) runs these checks over the
capped routes a merged pair participates in. Three are implementable with the
deterministic core alone:

- **composed determinism**: a route re-run on the same input yields a
  byte-identical terminal artifact (the determinism ratchet, PATHS.md §2).
- **composed coverage**: the fraction of the head pair's source-construct
  probes that survive *end to end* through every hop of a route without an
  ``Unsupported`` abort (BENCHMARKS.md §5). This is strictly stronger than any
  single pair's coverage: a construct a front-end lowers may still die at a
  later hop, and composed coverage localizes that to the stage that rejected
  it — the gap a per-pair number hides.
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

from . import registry
from . import route as _route
from .coverage import CoverageReport
from .errors import Unsupported


def composed_determinism(route: list[str], head_program: Any,
                         params: dict[str, dict] | None = None) -> bool:
    a = _route.run_route(route, head_program, params)["artifact"]
    b = _route.run_route(route, head_program, params)["artifact"]
    return a == b


def composed_coverage(route: list[str], head_probes: dict[str, Any] | None = None,
                      *, k: int = 1, params: dict[str, dict] | None = None) -> CoverageReport:
    """Construct coverage of a whole *route*: a probe is covered iff it
    translates through every hop without an ``Unsupported`` abort.

    Probes default to the head pair's inventory (the source-language
    constructs). Missing probes record ``"<stage>:<construct>"`` — the stage is
    the hop that rejected the construct, so an end-to-end gap points at itself.
    ``k`` seeds any hop that needs a step bound (e.g. the SMT bridge); other
    hops ignore it.
    """
    head = registry.get_pair(route[0])
    probes = head_probes if head_probes is not None else (head.probes or {})
    full_params = {pid: {"k": k} for pid in route}
    if params:
        for pid, p in params.items():
            full_params.setdefault(pid, {}).update(p)

    report = CoverageReport(total=len(probes))
    for name, program in probes.items():
        try:
            _route.run_route(route, program, full_params)
            report.covered.add(name)
        except Unsupported as exc:
            report.missing[name] = f"{exc.language}:{exc.construct}"
    return report


def composed_coverage_by_route(src: str, dst: str, *, k: int = 1,
                               max_hops: int = 6) -> dict[tuple[str, ...], CoverageReport]:
    """Composed coverage for every route from language ``src`` to ``dst``."""
    return {
        tuple(r): composed_coverage(r, k=k)
        for r in _route.routes(src, dst, max_hops=max_hops)
    }


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
