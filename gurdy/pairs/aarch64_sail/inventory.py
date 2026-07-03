"""Construct coverage for aarch64-sail against the language-owned inventory.

The A64 probe inventory itself lives with the *language*
(``gurdy.languages.aarch64.inventory``, BENCHMARKS.md §2) — **identical to
``aarch64-btor2``'s yardstick by construction** (same probe keys, same
in-scope / out-of-scope split), so the two AArch64→BTOR2 routes are measured
on the same denominator and their covered sets coincide exactly (branch
agreement, ROUTES.md §4-5). The Sail interpreter's widening history
(0.6 → 0.7 mirroring the direct pair's 0.5 → 0.6: the 32-bit W-register
ALU/flag forms, 27/33 with full branch agreement restored) is recorded in
``gurdy/languages/sail``; the coverage ratchet (BENCHMARKS.md §5) holds:
covered only grows, nothing covered ever drops.

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
