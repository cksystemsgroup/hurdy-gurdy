"""The ``btor2-havoc`` pair — BTOR2 -> BTOR2 localization abstraction.

The platform's first **directional** pair (``direction="over"``,
ARCHITECTURE.md §3, core/direction.py) and its first **endo-pair** (source
language == target language, POTENTIAL.md §4): the translator rewrites the
``next`` functions of caller-named states into fresh inputs, producing a
smaller-constraint system whose behaviors are a superset of the source's.

Its square is the lax square ``I_s(p) ⊑_π Λ(I_t(T(p)))``, checked as an exact
square **along the witness embedding**: ``embed`` maps a source binding to
the target binding that drives each fresh ``havoc_*`` input with exactly the
value the deleted next function produces, so ``align`` under the per-system
projection is decidable, deterministic, and defect-localizing exactly as for
an exact pair. What the direction changes is *verdict transfer*: an
``unreachable`` decided on the abstraction holds for the source; a
``reachable`` is only ever believed after source replay (SOLVERS.md §4), and
a replay failure is a **spurious counterexample** — a refinement demand
(havoc fewer states).

Like ``crn-smtlib`` and the ``sail-btor2`` AArch64 arm, the projection is
per-program (``projection_for``): the kept observables are all bit-vector
state labels and all ``bad`` statuses of the *source* system.
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
from .translate import havoc_plan, translate

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
    """The witness embedding ``W``: the target binding under which the
    abstraction simulates the source run of ``binding`` — each fresh havoc
    input is driven with the state value the source's next function actually
    produced. Computed from the *source* system alone (never from the
    translator's output), so a translator defect cannot bend the check."""
    binding = dict(binding or {})
    k = int(binding.get("steps", 1))
    _sys, text, plan = havoc_plan(program)
    src = list(_btor2.interpret(text, binding))
    inputs = {c: dict((binding.get("inputs") or {}).get(c, {})) for c in range(k)}
    for state, input_id, _next_id in plan:
        label = state.symbol or f"n{state.id}"
        for c in range(k):
            follow = src[c + 1] if c + 1 < len(src) else src[-1]
            inputs[c][input_id] = follow[label]
    binding["inputs"] = inputs
    return binding


def square(program: dict[str, Any]) -> AlignResult:
    """The lax square, checked along the witness embedding: run the source,
    translate, run the abstraction under ``embed``'s binding, carry back, and
    align under the per-system projection."""
    binding = dict(program.get("binding") or {})
    binding.setdefault("steps", _DEFAULT_STEPS)
    sys, text, _plan = havoc_plan(program)
    src = list(_btor2.interpret(text, binding))
    artifact = translate(program)
    carried = lift(_btor2.interpret(artifact, embed(program, binding)))
    return oracle.align(src, list(carried), projection_for(sys))


def _compose_from_upstream(prev: Any, params: dict) -> dict:
    """Path-runner glue: wrap a predecessor's BTOR2 artifact and the player's
    havoc set (the refinement parameter) into this pair's input."""
    return {"system": prev, "havoc": tuple(params.get("havoc", ()))}


registry.register_pair(
    Pair(
        id="btor2-havoc",
        source="btor2",
        target="btor2",
        translator=translate,
        target_to_source=lift,
        # Per-system π via projection_for() (the crn-smtlib / sail-btor2
        # dynamic-projection precedent); the registered field stays nominal.
        projection=Projection(()),
        fidelity="checked",
        direction="over",
        # 0.2: dead value nodes swept from the emission (a non-extension
        # rewrite — the version bump per prop:ratchet; squares, traces,
        # and the witness embedding are unchanged).
        translator_version="0.2",
        status=Status.PARTIAL,
        compose_input=_compose_from_upstream,
        probes=ALL_PROBES,
        square=square,
    )
)
