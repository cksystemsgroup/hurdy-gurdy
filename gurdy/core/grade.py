"""Path grading — measured composition (ROUTES.md §7; BENCHMARKS.md §6-7).

The merge-triggered route-grader (AGENTS.md §7) runs these checks over the
capped routes a merged pair participates in. Three are implementable with the
deterministic core alone:

- **composed determinism**: a route re-run on the same input yields a
  byte-identical terminal artifact (the determinism ratchet, ROUTES.md §2).
- **composed coverage**: the fraction of the head pair's source-construct
  probes that survive *end to end* through every hop of a route without an
  ``Unsupported`` abort (BENCHMARKS.md §5). This is strictly stronger than any
  single pair's coverage: a construct a front-end lowers may still die at a
  later hop, and composed coverage localizes that to the stage that rejected
  it — the gap a per-pair number hides.
- **branch agreement**: when several routes reach the same target from the
  same source, deciding the same question along each must agree (the
  fidelity-raising cross-check, ROUTES.md §4 / BENCHMARKS.md §6). With a single
  route this is trivially satisfied; it becomes load-bearing once a branch
  (e.g. the Sail route to BTOR2) exists.

The merge *trigger* and the regression *ratchet* (compare to a baseline) are
orchestration (CI), outside this module; these are the measurements they act on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from . import cache, costs, registry
from . import route as _route
from .coverage import CoverageReport
from .errors import Unsupported


def composed_determinism(route: list[str], head_program: Any,
                         params: dict[str, dict] | None = None) -> bool:
    a = _route.run_route(route, head_program, params)["artifact"]
    b = _route.run_route(route, head_program, params)["artifact"]
    return a == b


def composed_coverage(route: list[str], head_probes: dict[str, Any] | None = None,
                      *, k: int = 1, params: dict[str, dict] | None = None,
                      conjoin: bool = True) -> CoverageReport:
    """Construct coverage of a whole *route*: a probe is covered iff it
    translates through every hop without an ``Unsupported`` abort **and**, at
    every hop that has a decidable square oracle, the hop's square passes on
    the hop's input (the route-level reading of Definition 4.6's conjunction;
    hops without a square — e.g. the ``predicted``-grade bridge — contribute
    per-run faithfulness at question time instead).

    Probes default to the head pair's inventory (the source-language
    constructs, owned by the language). Missing probes record
    ``"<stage>:<construct>"`` and unfaithful probes ``"<pair>: <divergence>"``
    — the stage is the hop that rejected (or diverged on) the construct, so an
    end-to-end gap points at itself. ``k`` seeds any hop that needs a step
    bound (e.g. the SMT bridge); other hops ignore it.

    Each hop compiles before its square runs: the square executes the source
    interpreter, whose stores mutate the shared program image, and the
    artifact must be the pristine translation.
    """
    head = registry.get_pair(route[0])
    probes = head_probes if head_probes is not None else (head.probes or {})
    full_params = {pid: {"k": k} for pid in route}
    if params:
        for pid, p in params.items():
            full_params.setdefault(pid, {}).update(p)

    report = CoverageReport(
        total=len(probes),
        conjoined=conjoin and any(registry.get_pair(pid).square for pid in route),
    )
    for name, program in probes.items():
        try:
            artifact: Any = None
            diverged = None
            for i, pid in enumerate(route):
                pair = registry.get_pair(pid)
                if i == 0:
                    hop_input = program
                elif pair.compose_input is not None:
                    hop_input = pair.compose_input(artifact, full_params.get(pid, {}))
                else:
                    hop_input = artifact
                artifact = cache.compile(pair, hop_input)
                if conjoin and pair.square is not None:
                    with costs.timed("cross_check", cache.cache_key(pair, hop_input),
                                     pair=pid):
                        result = pair.square(hop_input)
                    if not getattr(result, "ok", bool(result)):
                        d = getattr(result, "divergence", None)
                        where = (f"step {d.step}, {d.field}" if d else "diverged")
                        diverged = f"{pid}: {where}"
                        break
            if diverged is not None:
                report.unfaithful[name] = diverged
            else:
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
