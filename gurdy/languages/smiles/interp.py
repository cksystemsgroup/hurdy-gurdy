"""The shared SMILES interpreter (``I_s`` for the ``smiles-formula`` pair;
languages/smiles brief).

A SMILES string's *behavior* is its parsed molecular graph; the observable a
pair selects is which graph feature it preserves (ARCHITECTURE.md §5). For the
``smiles-formula`` pair the projection is the **atom multiset**, so this
interpreter exposes a one-state ``Trace`` whose observables are:

  - ``atoms``   : the atom multiset (heavy atoms + implicit hydrogens), as a
                  Hill-ordered, hashable tuple of ``(symbol, count)`` pairs —
                  never a dict, so the bytes never depend on iteration order;
  - ``formula`` : the canonical Hill-notation string the multiset denotes.

Both are projectable. The ``formula`` observable is computed *here* (in the
source interpreter) only as a convenience for the cross-check; the canonical
form lives in the molecular-formula language and is reused, not forked.

Pure and deterministic. Out-of-scope SMILES constructs hard-abort in
``graph.parse`` (BENCHMARKS.md §3) before any behavior is produced.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from ..molecular_formula.hill import to_hill
from ..molecular_formula.interp import canonical_atoms
from .graph import parse


def run(smiles: str, *_args: Any, **_kw: Any) -> Trace:
    """Interpret an in-scope SMILES string: parse the molecular graph, fill
    implicit hydrogens by valence, and expose the atom multiset + its canonical
    Hill formula as a one-state ``Trace``. Aborts on any out-of-scope construct.
    """
    graph = parse(smiles)
    atoms = graph.atom_multiset()
    return [{"atoms": canonical_atoms(atoms), "formula": to_hill(atoms)}]
