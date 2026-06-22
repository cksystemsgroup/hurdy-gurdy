"""The shared molecular-formula interpreter (``I_t`` for the ``smiles-formula``
pair; languages/molecular-formula brief).

A molecular formula's *behavior* is not a temporal trace but its meaning as an
**atom multiset** plus the canonical Hill string that denotes it. To plug into
the framework's trace/observable contract (ARCHITECTURE.md §5), the interpreter
yields a one-state ``Trace`` whose observables are:

  - ``atoms``   : the atom multiset, as a sorted tuple of ``(symbol, count)``
                  pairs (a hashable, order-canonical representation — never a
                  dict, so the bytes never depend on iteration order);
  - ``formula`` : the canonical Hill-notation string.

Both observables are projectable; the ``smiles-formula`` pair's projection ``π``
selects them. Pure and deterministic.
"""

from __future__ import annotations

from typing import Any

from ...core.types import Trace
from .hill import parse, to_hill


def canonical_atoms(atoms: dict[str, int]) -> tuple[tuple[str, int], ...]:
    """A canonical, hashable form of an atom multiset: Hill-ordered
    ``(symbol, count)`` pairs. Order is fixed by Hill notation, so two equal
    multisets always produce byte-identical tuples regardless of how the dict
    was built."""
    from .hill import hill_order

    return tuple((s, atoms[s]) for s in hill_order(list(atoms.keys())))


def run(formula: str, *_args: Any, **_kw: Any) -> Trace:
    """Interpret a molecular-formula string: parse it to its atom multiset and
    re-emit canonical Hill notation. Returns a one-state ``Trace``.

    ``run`` is the shared target interpreter ``I_t``: the carried-back source
    behavior is compared against it under the pair's projection.
    """
    atoms = parse(formula)
    return [{"atoms": canonical_atoms(atoms), "formula": to_hill(atoms)}]
