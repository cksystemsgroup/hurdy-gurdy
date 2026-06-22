"""The molecular-formula model: an atom multiset and its canonical Hill-notation
written form (languages/molecular-formula brief).

The *meaning* of a molecular formula is an **atom multiset** (element symbol ->
count). **Hill notation** fixes the canonical written form: carbon first (if
present), then hydrogen (if present), then every other element alphabetically
by symbol; a count of 1 is written without a digit. Equality of formulas is
equality of multisets, so the canonical string is a total normal form of the
multiset and round-trips byte-for-byte.

Everything here is pure and deterministic. The element order in the emitted
string comes from Hill notation (a fixed canonical order), never from dict /
hash iteration order, so the bytes are reproducible on any host
(ARCHITECTURE.md §4).
"""

from __future__ import annotations

import re

from ...core.errors import Unsupported

# A formula token: an element symbol (one uppercase + optional lowercase letters)
# followed by an optional positive integer count. Anchored matching below
# rejects anything else with a typed abort (no silent drop, BENCHMARKS.md §3).
_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")


def hill_order(symbols: list[str]) -> list[str]:
    """The canonical Hill element order over a set of symbols: ``C`` first (if
    present), then ``H`` (if present), then the remaining symbols sorted
    alphabetically. Deterministic and total."""
    rest = sorted(s for s in symbols if s not in ("C", "H"))
    head = [s for s in ("C", "H") if s in symbols]
    return head + rest


def to_hill(atoms: dict[str, int]) -> str:
    """Render an atom multiset as a canonical Hill-notation string.

    ``atoms`` maps element symbol -> positive count. Zero / negative counts are
    a caller bug and rejected. The output is byte-deterministic: the element
    order is the fixed Hill order, not dict iteration order.
    """
    for sym, n in atoms.items():
        if not isinstance(n, int) or n <= 0:
            raise ValueError(f"non-positive count for {sym!r}: {n!r}")
    parts = []
    for sym in hill_order(list(atoms.keys())):
        n = atoms[sym]
        parts.append(sym if n == 1 else f"{sym}{n}")
    return "".join(parts)


def parse(formula: str) -> dict[str, int]:
    """Parse a Hill-notation formula string into its atom multiset.

    This is a *flat* formula reader (no parentheses / nesting / charges): a run
    of ``<element><count?>`` tokens. Anything outside that grammar hard-aborts
    with ``Unsupported`` naming the offending construct (BENCHMARKS.md §3),
    rather than being silently skipped.
    """
    atoms: dict[str, int] = {}
    pos = 0
    n = len(formula)
    while pos < n:
        ch = formula[pos]
        if ch in "()[].+-":
            raise Unsupported(
                "molecular-formula", "nested-or-charged-formula",
                f"token {ch!r} at {pos}",
            )
        m = _TOKEN.match(formula, pos)
        if m is None or m.start() != pos or m.end() == pos:
            raise Unsupported(
                "molecular-formula", "bad-token", f"at offset {pos}: {formula[pos:]!r}",
            )
        sym, count = m.group(1), m.group(2)
        atoms[sym] = atoms.get(sym, 0) + (int(count) if count else 1)
        pos = m.end()
    return atoms
