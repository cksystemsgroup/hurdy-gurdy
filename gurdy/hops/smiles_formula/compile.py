"""SMILES (aliphatic organic subset) -> Hill-notation molecular formula.

This is the translation rule of the ``smiles-formula`` *transparent* compile
hop. It is pure, deterministic, and fully specified by ``SCHEMA.md``: an LLM
(or human) that has read the schema can predict the output formula for any
in-subset SMILES, byte-for-byte (the ``PAIRING.md`` §5 predictability
invariant, in chemistry).

Supported subset (everything else raises :class:`SmilesError`): the aliphatic
organic-subset atoms ``B C N O P S F Cl Br I``; bonds ``-`` ``=`` ``#`` (single
is implicit between adjacent atoms); branches ``( )``; single-digit ring
closures ``1``-``9``. No brackets ``[...]`` (so no charges, isotopes, explicit
H, or stereo), no aromatic (lowercase) atoms, no disconnected ``.``. See
``SCHEMA.md`` for the implicit-hydrogen valence rules and Hill ordering.
"""

from __future__ import annotations

from dataclasses import dataclass


class SmilesError(ValueError):
    """The input is malformed or outside the supported SMILES subset."""


# Organic-subset standard valences (OpenSMILES). Implicit hydrogens fill an
# atom's bond-order sum up to the smallest standard valence >= that sum.
_VALENCES: dict[str, tuple[int, ...]] = {
    "B": (3,),
    "C": (4,),
    "N": (3, 5),
    "O": (2,),
    "P": (3, 5),
    "S": (2, 4, 6),
    "F": (1,),
    "Cl": (1,),
    "Br": (1,),
    "I": (1,),
}
_TWO_LETTER = ("Cl", "Br")
_ONE_LETTER = ("B", "C", "N", "O", "P", "S", "F", "I")
_BOND_ORDER = {"-": 1, "=": 2, "#": 3}


@dataclass
class _Atom:
    element: str
    bond_order_sum: int = 0  # sum of bond orders to neighbours (excludes implicit H)


def _implicit_h(element: str, bond_order_sum: int) -> int:
    for valence in _VALENCES[element]:
        if bond_order_sum <= valence:
            return valence - bond_order_sum
    return 0  # hypervalent beyond the largest standard valence: no implicit H


def _parse(smiles: str) -> list[_Atom]:
    atoms: list[_Atom] = []
    branch_stack: list[int] = []  # atom indices to return to on ')'
    ring: dict[str, tuple[int, int | None]] = {}  # digit -> (atom_idx, bond_order)
    prev: int | None = None
    pending_bond: int | None = None

    i, n = 0, len(smiles)
    while i < n:
        c = smiles[i]

        if c in _BOND_ORDER:
            if pending_bond is not None:
                raise SmilesError(f"repeated bond symbol at position {i}")
            pending_bond = _BOND_ORDER[c]
            i += 1
            continue

        if c == "(":
            if prev is None:
                raise SmilesError(f"branch '(' with no preceding atom at {i}")
            branch_stack.append(prev)
            i += 1
            continue

        if c == ")":
            if not branch_stack:
                raise SmilesError(f"unmatched ')' at position {i}")
            prev = branch_stack.pop()
            i += 1
            continue

        if c.isdigit():
            if prev is None:
                raise SmilesError(f"ring-closure digit with no preceding atom at {i}")
            if c in ring:
                other_idx, other_bond = ring.pop(c)
                if (
                    pending_bond is not None
                    and other_bond is not None
                    and pending_bond != other_bond
                ):
                    raise SmilesError(f"conflicting ring-bond orders for digit {c}")
                order = (
                    pending_bond
                    if pending_bond is not None
                    else (other_bond if other_bond is not None else 1)
                )
                atoms[prev].bond_order_sum += order
                atoms[other_idx].bond_order_sum += order
            else:
                ring[c] = (prev, pending_bond)
            pending_bond = None
            i += 1
            continue

        # Atom: try a two-letter element first (Cl, Br), then one-letter.
        if smiles[i : i + 2] in _TWO_LETTER:
            element, i = smiles[i : i + 2], i + 2
        elif c in _ONE_LETTER:
            element, i = c, i + 1
        else:
            raise SmilesError(
                f"unsupported character {c!r} at position {i}: the subset is "
                "aliphatic organic SMILES (no brackets, aromatics, '.', or charges)"
            )

        idx = len(atoms)
        atoms.append(_Atom(element=element))
        if prev is not None:
            order = pending_bond if pending_bond is not None else 1
            atoms[prev].bond_order_sum += order
            atoms[idx].bond_order_sum += order
        elif pending_bond is not None:
            raise SmilesError(f"bond symbol with no preceding atom near position {i}")
        pending_bond = None
        prev = idx

    if pending_bond is not None:
        raise SmilesError("dangling bond symbol at end of input")
    if ring:
        raise SmilesError(f"unclosed ring bond(s): {sorted(ring)}")
    if branch_stack:
        raise SmilesError("unclosed '(' branch")
    if not atoms:
        raise SmilesError("empty molecule")
    return atoms


def _hill(counts: dict[str, int]) -> str:
    """Hill notation: with carbon present, C then H then the rest alphabetically;
    with no carbon, every element (including H) alphabetically. Count 1 is
    written implicitly."""

    def render(element: str) -> str:
        count = counts[element]
        return element if count == 1 else f"{element}{count}"

    if "C" in counts:
        order = ["C"] + (["H"] if "H" in counts else [])
        order += sorted(e for e in counts if e not in ("C", "H"))
    else:
        order = sorted(counts)
    return "".join(render(e) for e in order)


def smiles_to_formula(smiles: str | bytes) -> str:
    """Translate an in-subset SMILES string to its Hill-notation molecular
    formula. Raises :class:`SmilesError` on malformed or out-of-subset input."""
    if isinstance(smiles, (bytes, bytearray)):
        try:
            smiles = bytes(smiles).decode("ascii")
        except UnicodeDecodeError as exc:
            raise SmilesError("SMILES must be ASCII") from exc
    smiles = smiles.strip()

    atoms = _parse(smiles)
    counts: dict[str, int] = {}
    hydrogens = 0
    for atom in atoms:
        counts[atom.element] = counts.get(atom.element, 0) + 1
        hydrogens += _implicit_h(atom.element, atom.bond_order_sum)
    if hydrogens:
        counts["H"] = counts.get("H", 0) + hydrogens
    return _hill(counts)


__all__ = ["SmilesError", "smiles_to_formula"]
