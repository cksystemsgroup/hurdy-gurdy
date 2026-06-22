"""The shared SMILES language + interpreter (languages/smiles brief).

Registers the ``smiles`` language with its deterministic **source** interpreter
(``I_s``): an OpenSMILES-subset reader that parses the in-scope organic carbon
chain to a molecular graph and exposes its atom multiset. Shared by every SMILES
pair (currently ``smiles-formula``). Out-of-scope constructs hard-abort with a
typed ``Unsupported`` (BENCHMARKS.md §3).
"""

from __future__ import annotations

from ...core.registry import Language, register_language
from .graph import Atom, MolGraph, parse
from .interp import run

__all__ = ["run", "parse", "Atom", "MolGraph"]

register_language(Language("smiles", source_interpreter=run))
