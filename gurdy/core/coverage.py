"""Coverage measurement (BENCHMARKS.md §2, §5).

Construct coverage against a spec-derived inventory the implementer does not
choose: the inventory is a set of named probes (minimal programs, one per
language construct). A construct is *covered* iff its probe translates without
a typed ``Unsupported`` abort **and** — when the pair has a decidable square
oracle — the commuting square passes on the probe (the conjunction of
Definition 4.6: accepted *and* faithful). The missing set is the itemized
``unsupported`` histogram — the gap made visible rather than hidden; the
``unfaithful`` set is the sharper failure: accepted but wrong, each entry
localized to its first divergence.

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
    # probe name -> first-divergence summary ("step k, field f: l != r").
    # Populated only when measuring the conjunction (a ``faithful`` oracle was
    # supplied); an accepted-but-diverging probe is NOT covered.
    unfaithful: dict[str, str] = field(default_factory=dict)
    # True iff the faithfulness conjunct was actually measured (vs. acceptance
    # only, when the pair has no decidable square).
    conjoined: bool = False

    @property
    def fraction(self) -> float:
        return len(self.covered) / self.total if self.total else 1.0

    @property
    def histogram(self) -> dict[str, int]:
        """Unsupported constructs and how many probes each blocked."""
        return dict(collections.Counter(self.missing.values()))

    def meets(self, floor: float = 1.0) -> bool:
        return self.fraction >= floor


def _divergence_summary(result: Any) -> str:
    d = getattr(result, "divergence", None)
    if d is None:
        return "diverged"
    return f"step {d.step}, {d.field}: {d.left!r} != {d.right!r}"


def measure(translate: Callable[[Any], Any], probes: dict[str, Any],
            faithful: Callable[[Any], Any] | None = None) -> CoverageReport:
    """Measure construct coverage over ``probes``.

    Without ``faithful`` this measures translator *acceptance* only. With
    ``faithful`` (the pair's square oracle, ``program -> AlignResult``) it
    measures Definition 4.6's conjunction: a probe counts iff it is accepted
    *and* its commuting square passes.
    """
    report = CoverageReport(total=len(probes), conjoined=faithful is not None)
    for name, program in probes.items():
        try:
            translate(program)
        except Unsupported as exc:
            report.missing[name] = exc.construct
            continue
        if faithful is not None:
            result = faithful(program)
            if not getattr(result, "ok", bool(result)):
                report.unfaithful[name] = _divergence_summary(result)
                continue
        report.covered.add(name)
    return report
