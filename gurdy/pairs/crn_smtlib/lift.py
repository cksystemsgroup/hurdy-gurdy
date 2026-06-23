"""Target-to-source interpreter ``L`` for crn-smtlib: decode an SMT model (a
reachability witness) into a CRN behavior — the firing sequence and the per-step
species populations that reach the target marking (pairs/crn-smtlib brief).

The solver's model only *proposes* the witness (SOLVERS.md §4); the
deterministic CRN interpreter then **regrows** the full run, which is what makes
the answer trustworthy. ``decode_schedule`` reads the per-step firing flags
``f<i>_t`` from the model (matching ``translate``'s variable names) and turns
them into a firing schedule — the index of whichever reaction fired that step
(the translator's mutual-exclusion constraint makes at most one true), or a
stutter when none did. ``lift`` replays that schedule through the shared CRN
interpreter, so the populations it returns are the interpreter's, not the
solver's. Width/shape oddities in a model entry default to "did not fire".
"""

from __future__ import annotations

from typing import Any

from ...languages.crn.eval import step
from ...languages.crn.model import Network, as_network


def _truthy(val: Any) -> bool:
    """A model entry for a ``Bool``: the z3 backend stringifies it to
    ``"True"``/``"False"``; accept the obvious shapes, default to ``False``."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "#b1", "1")
    if isinstance(val, int):
        return val != 0
    return False


def decode_schedule(k: int, model: dict[str, Any], n: int = 1) -> list[int | None]:
    """The per-step choice list for an ``n``-reaction network: the index ``i`` of
    the reaction whose flag ``f<i>_t`` fired that step (the lowest such index —
    the translator's mutual-exclusion constraint makes at most one true), or
    ``None`` (a stutter) when none fired. ``n`` defaults to 1 (a single reaction
    ``R0``), preserving the prior single-reaction signature."""
    schedule: list[int | None] = []
    for t in range(k):
        fired = next((i for i in range(n) if _truthy(model.get(f"f{i}_{t}"))), None)
        schedule.append(fired)
    return schedule


def lift(witness: dict[str, Any]):
    """``witness`` bundles the CRN ``crn``, the bound ``k``, and the SMT
    ``model``; returns the replayed CRN behavior (post-step populations). The
    reaction count is taken from the network, so a multi-reaction witness decodes
    which reaction fired each step."""
    net: Network = as_network(witness["crn"])
    k = int(witness["k"])
    schedule = decode_schedule(k, witness["model"], len(net.reactions))
    return step(net, {"steps": k, "schedule": schedule})
