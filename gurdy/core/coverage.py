"""Coverage measurement (BENCHMARKS.md §2, §5).

Construct coverage against a spec-derived inventory the implementer does not
choose: the inventory is a set of named probes (minimal programs, one per
language construct); a construct is *covered* iff its probe translates without
a typed ``Unsupported`` abort, and *missing* otherwise. The missing set is the
itemized ``unsupported`` histogram — the gap made visible rather than hidden.

Only ``Unsupported`` (the honest-failure mechanism, BENCHMARKS.md §3) counts
as "out of scope"; any other exception is a real bug and propagates.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import Unsupported


@dataclass
class CoverageReport:
    total: int
    covered: set[str] = field(default_factory=set)
    missing: dict[str, str] = field(default_factory=dict)  # probe name -> construct

    @property
    def fraction(self) -> float:
        return len(self.covered) / self.total if self.total else 1.0

    @property
    def histogram(self) -> dict[str, int]:
        """Unsupported constructs and how many probes each blocked."""
        return dict(collections.Counter(self.missing.values()))

    def meets(self, floor: float = 1.0) -> bool:
        return self.fraction >= floor


def measure(translate: Callable[[Any], Any], probes: dict[str, Any]) -> CoverageReport:
    report = CoverageReport(total=len(probes))
    for name, program in probes.items():
        try:
            translate(program)
            report.covered.add(name)
        except Unsupported as exc:
            report.missing[name] = exc.construct
    return report
