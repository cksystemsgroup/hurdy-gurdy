"""The ``smiles-formula`` translator ``T`` (PAIRING.md §1).

A schema-determined map (PAIRING.md §2, ``predicted`` discipline): parse the
SMILES string to its molecular graph (reusing the shared SMILES interpreter's
reader — chains, branches, rings, and bracket atoms), read off the atom multiset,
and emit its **canonical Hill-notation** string (reusing the shared
molecular-formula language's renderer). No adaptive choice anywhere — given the
SMILES string and the schema (the per-element valence rule for bare atoms, over a
degree that counts branch/ring bonds; the explicit-H, no-valence-fill rule for
bracket atoms; + Hill notation), the output bytes are reproducible byte-for-byte
on any host.

The translator and the target-to-source interpreter ``L`` share one source of
truth — the molecular-formula language's ``parse``/``to_hill`` — so the square
commutes by construction (PAIRING.md §6).
"""

from __future__ import annotations

from typing import Any

from ...languages.molecular_formula.hill import to_hill
from ...languages.smiles.graph import parse


def _smiles_of(program: Any) -> str:
    """Accept either a raw SMILES string or a ``{"smiles": ...}`` dict (the
    shape the route runner / coverage probes may hand in)."""
    if isinstance(program, str):
        return program
    if isinstance(program, dict) and "smiles" in program:
        return str(program["smiles"])
    raise TypeError(f"expected SMILES string or {{'smiles': ...}}, got {program!r}")


def translate(program: Any) -> bytes:
    """``T``: SMILES string -> canonical Hill-notation formula bytes.

    Out-of-scope constructs hard-abort inside ``parse`` (BENCHMARKS.md §3)
    before any formula is emitted.
    """
    smiles = _smiles_of(program)
    atoms = parse(smiles).atom_multiset()
    return to_hill(atoms).encode("utf-8")
