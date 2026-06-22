"""The shared molecular-formula language + interpreter
(languages/molecular-formula brief).

Registers the ``molecular-formula`` language with its deterministic **target**
interpreter (``I_t``): a formula reader/normalizer that parses a Hill-notation
string to its atom multiset and re-emits canonical Hill notation. Shared by
every pair targeting molecular formulas (currently ``smiles-formula``).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from .hill import hill_order, parse, to_hill
from .interp import canonical_atoms, run

__all__ = ["run", "parse", "to_hill", "hill_order", "canonical_atoms"]

register_language(Language("molecular-formula", target_interpreter=run))
