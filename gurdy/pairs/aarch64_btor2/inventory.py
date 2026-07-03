"""Construct coverage for aarch64-btor2 against the language-owned inventory.

The A64 probe inventory itself lives with the *language*
(``gurdy.languages.aarch64.inventory``, BENCHMARKS.md §2): Definition 4.6
fixes the yardstick per language, so both AArch64 pairs (this one and
``aarch64-sail``) are measured against the same declared slice — same probe
keys, same in-scope / out-of-scope split — and the two AArch64→BTOR2 routes'
covered sets can be compared construct-for-construct (branch agreement,
ROUTES.md §4-5). The slice's widening history (0.5 → 0.6: the 32-bit
W-register ALU/flag forms, growing 19/23 → 27/33) is recorded in the language
module and in this pair's translator version notes; the coverage ratchet
(BENCHMARKS.md §5) holds: covered only grows, nothing covered ever drops.

This module keeps the pair's ``coverage()`` entry point and re-exports the
inventory for backward compatibility.
"""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from ...languages.aarch64.inventory import (  # noqa: F401  (re-exported)
    ALL_PROBES,
    IN_SCOPE,
    OUT_OF_SCOPE,
)
from .translate import translate


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
