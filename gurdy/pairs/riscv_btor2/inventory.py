"""Construct coverage for riscv-btor2 against the language-owned inventory.

The RV64IMC probe inventory itself lives with the *language*
(``gurdy.languages.riscv.inventory``, BENCHMARKS.md §2): Definition 4.6 fixes
the yardstick per language, so both RISC-V-headed pairs (this one and
``riscv-sail``) are measured against the same denominator. This module keeps
the pair's ``coverage()`` entry point and re-exports the inventory for
backward compatibility.
"""

from __future__ import annotations

from ...core.coverage import CoverageReport, measure
from ...languages.riscv.inventory import (  # noqa: F401  (re-exported)
    ALL_PROBES,
    RV64C_PROBES,
    RV64I_PROBES,
    RV64M_PROBES,
)
from .translate import translate


def coverage() -> CoverageReport:
    return measure(translate, ALL_PROBES)
