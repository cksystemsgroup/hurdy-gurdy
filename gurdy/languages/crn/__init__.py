"""The shared CRN language + interpreter (languages/crn brief).

Registers ``crn`` with its deterministic discrete (Petri-net) interpreter as the
**source** interpreter ``I_s`` shared by every CRN pair (today only
``crn-smtlib``). The interpreter steps an initial marking under a per-step
firing schedule and reports post-step species populations
(ARCHITECTURE.md §§5-6). CRN is the platform's non-CS source language — the
source is chemistry, not code (ARCHITECTURE.md §1).
"""

from __future__ import annotations

from ...core.registry import Language, Status, register_language
from .eval import FiringError, interpret, step
from .model import CrnSyntaxError, Network, Reaction, as_network, from_text

__all__ = [
    "interpret",
    "step",
    "from_text",
    "as_network",
    "Network",
    "Reaction",
    "CrnSyntaxError",
    "FiringError",
]

register_language(
    Language("crn", source_interpreter=interpret, status=Status.PARTIAL)
)
