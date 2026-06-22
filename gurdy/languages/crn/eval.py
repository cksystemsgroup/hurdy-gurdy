"""A deterministic CRN interpreter — the shared discrete (Petri-net) stepper
(languages/crn brief; ARCHITECTURE.md §5).

Given a :class:`~gurdy.languages.crn.model.Network` and a binding (an initial
marking override + a per-step **firing schedule**), produce a ``Trace`` of
post-step species populations. The schedule resolves the Petri net's
non-determinism into a deterministic run: each step either fires one named
reaction or stutters (a no-op step), exactly as the BTOR2 interpreter's
per-step ``inputs`` resolve its inputs.

A reaction fires only when **enabled** — every reactant is present in at least
its stoichiometric coefficient (the Petri-net firing rule). A scheduled firing
of a non-enabled reaction is rejected with a typed :class:`FiringError`, so an
SMT witness that proposes an impossible firing is caught on replay rather than
silently producing a bogus marking.

Observables (one per species, after each step) are the species names; the
projection ``π`` of a pair over CRN selects a subset of them
(ARCHITECTURE.md §3, §5).
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from .model import Network, as_network


class FiringError(ValueError):
    """A scheduled reaction is not enabled in the current marking (a reactant
    is below its stoichiometric coefficient)."""


def _enabled(reaction, marking: dict[str, int]) -> bool:
    return all(marking.get(s, 0) >= c for s, c in reaction.reactants)


def _fire(reaction, marking: dict[str, int]) -> dict[str, int]:
    nxt = dict(marking)
    for s, c in reaction.reactants:
        nxt[s] -= c
    for s, c in reaction.products:
        nxt[s] = nxt.get(s, 0) + c
    return nxt


def step(net: Network, binding: dict[str, Any] | None = None) -> Trace:
    """Step ``net`` under ``binding``.

    ``binding`` keys (all optional):
      * ``marking`` — initial-population overrides ``{species: count}`` (else
        the network's declared ``init``);
      * ``steps`` — number of discrete steps ``k`` (else the schedule length,
        else 1);
      * ``schedule`` — a list of per-step choices; each entry is a reaction
        index (0-based, into ``net.reactions``) to fire, or ``None`` / ``-1``
        for a stutter (no reaction fires this step).

    Returns the post-step marking after each of the ``k`` steps. Each state maps
    every species name to its (non-negative) integer population.
    """
    binding = binding or {}
    net = as_network(net)

    marking: dict[str, int] = net.init_map
    override = binding.get("marking") or {}
    for s, c in override.items():
        if s not in marking:
            raise FiringError(f"override of undeclared species {s!r}")
        marking[s] = int(c)

    schedule = list(binding.get("schedule", []))
    k = int(binding["steps"]) if "steps" in binding else (len(schedule) or 1)

    trace: list[dict[str, Any]] = []
    for i in range(k):
        choice = schedule[i] if i < len(schedule) else None
        if choice is not None and choice != -1:
            idx = int(choice)
            if not 0 <= idx < len(net.reactions):
                raise FiringError(f"reaction index {idx} out of range")
            reaction = net.reactions[idx]
            if not _enabled(reaction, marking):
                raise FiringError(f"reaction {idx} not enabled at step {i}")
            marking = _fire(reaction, marking)
        # else: stutter — marking unchanged
        trace.append({s: marking[s] for s in net.species})
    return trace


def interpret(crn: Any, binding: dict[str, Any] | None = None, **_kw: Any) -> Trace:
    """Parse a CRN artifact (bytes/str/Network) and step it. This is the
    callable registered as the language's source interpreter ``I_s``."""
    return step(as_network(crn), binding)
