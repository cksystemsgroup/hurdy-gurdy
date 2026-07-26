"""The ``btor2-interval`` pair — BTOR2 -> BTOR2 interval (range) abstraction.

The platform's second **directional** endo-pair (``direction="over"``,
ARCHITECTURE.md §3, core/direction.py), registered 2026-07-13 as the
direction axis's corroborating sibling to ``btor2-havoc`` and implemented to
its brief (pairs/btor2-interval/README.md). The translator replaces the
``next`` function of each caller-named state with a free choice inside a
caller-declared range ``[lo, hi]``: where havoc deletes all information
about a state's update, interval retains the one fact the player asserts —
the state stays in its range — so universal verdicts are sharper at
slightly higher solver cost. The two pairs bracket a CEGAR ladder with
registered rungs: full range (≡ havoc) ⊒ subrange ⊒ singleton ``[c, c]``
(constant pinning) ⊒ keeping ``next`` (exact).

Unlike havoc — an over-approximation *by construction* — the interval claim
is **falsifiable by the corpus**: the witness embedding drives ``iv`` with
the affine decode inverse ``(v − lo) mod 2^w`` of the value ``v`` the
deleted ``next`` produces, and ``lo + urem(v − lo, hi − lo + 1) = v``
exactly when ``v ∈ [lo, hi]`` — the square along ``W`` *is* the interval
claim. A failing square means the declared interval is not invariant
(widen — the abstraction was unsound); a spurious counterexample at solve
time means it is too loose (tighten). Both failure modes are the player's
refinement demands, graded and negative-controlled — never absorbed: a
builder must not flip ``over`` to ``exact`` and must not silently widen a
declared interval to make a failing square pass (SCALING.md §9).

Verdict transfer per core/direction.py: ``unreachable`` transfers;
``reachable`` replays at the source (SOLVERS.md §4). The projection is
per-program (``projection_for``): all bit-vector state labels and all
``bad`` statuses of the *source* system.
"""

from __future__ import annotations

from typing import Any

from ...core import oracle, registry
from ...core.registry import Pair, Status
from ...core.types import AlignResult, Projection

# Importing the language registers the shared BTOR2 interpreter (both roles).
from ...languages import btor2 as _btor2  # noqa: F401
from ...languages.btor2.model import Bitvec, System
from .inventory import ALL_PROBES
from .lift import lift
from .translate import interval_plan, translate

__all__ = ["translate", "lift", "embed", "square", "projection_for"]

_DEFAULT_STEPS = 8


def projection_for(system: System) -> Projection:
    """The per-system ``π``: every bit-vector state label plus every ``bad``
    status of the source system — exactly the trace-row vocabulary."""
    fields = [n.symbol or f"n{n.id}" for n in system.states()
              if isinstance(system.sorts.get(n.sort), Bitvec)]
    fields += [f"bad{n.id}" for n in system.bads()]
    return Projection(tuple(sorted(fields)))


def embed(program: dict[str, Any], binding: dict[str, Any] | None) -> dict[str, Any]:
    """The witness embedding ``W``: drive each fresh ``iv_*`` input with the
    affine decode inverse ``(v − lo) mod 2^w``, where ``v`` is the value the
    deleted ``next`` actually produced. Computed from the *source* system
    alone (never from the translator's output), so a translator defect
    cannot bend the check. The decode then reproduces ``v`` exactly when
    ``v ∈ [lo, hi]`` — the embedding carries the abstraction's arithmetic,
    and its simulation claim has falsifiable semantic content."""
    binding = dict(binding or {})
    k = int(binding.get("steps", 1))
    sys, text, plan = interval_plan(program)
    src = list(_btor2.interpret(text, binding))
    inputs = {c: dict((binding.get("inputs") or {}).get(c, {})) for c in range(k)}
    for state, lo, _hi, ids in plan:
        label = state.symbol or f"n{state.id}"
        width = sys.sorts[state.sort].width
        for c in range(k):
            follow = src[c + 1] if c + 1 < len(src) else src[-1]
            inputs[c][ids[0]] = (follow[label] - lo) % (1 << width)
    binding["inputs"] = inputs
    return binding


def square(program: dict[str, Any]) -> AlignResult:
    """The lax square, checked along the witness embedding: run the source,
    translate, run the abstraction under ``embed``'s binding, carry back,
    and align under the per-system projection. A divergence localizes to a
    mapped state's label at the first step its source value leaves the
    declared range — the interval claim, falsified."""
    binding = dict(program.get("binding") or {})
    binding.setdefault("steps", _DEFAULT_STEPS)
    sys, text, _plan = interval_plan(program)
    src = list(_btor2.interpret(text, binding))
    artifact = translate(program)
    carried = lift(_btor2.interpret(artifact, embed(program, binding)))
    return oracle.align(src, list(carried), projection_for(sys))


def _compose_from_upstream(prev: Any, params: dict) -> dict:
    """Path-runner glue: wrap a predecessor's BTOR2 artifact and the player's
    interval map (the refinement parameter) into this pair's input."""
    return {"system": prev, "intervals": dict(params.get("intervals", {}) or {})}


registry.register_pair(
    Pair(
        id="btor2-interval",
        source="btor2",
        target="btor2",
        translator=translate,
        target_to_source=lift,
        # Per-system π via projection_for() (the btor2-havoc precedent);
        # the registered field stays nominal.
        projection=Projection(()),
        fidelity="checked",
        direction="over",
        translator_version="0.1",
        status=Status.PARTIAL,
        compose_input=_compose_from_upstream,
        probes=ALL_PROBES,
        square=square,
    )
)
