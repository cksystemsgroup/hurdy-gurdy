"""Reasoning-side trust: independent engines (and decide-both-ways) must
agree; for a pair carrying a ``machine_tool`` path, the own-vs-machine
cross-check is an extra differential. STUB with real structure.

Earns ``checked`` if >=2 unrelated engines agree on every instance;
``transparent`` if additionally the encoding is schema-auditable. Any
disagreement quarantines the instance and FAILs the edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gurdy.core.manifest import Manifest


@dataclass
class TrustResult:
    ok: bool
    earned: str = "unverified"          # unverified | checked | transparent
    quarantined: list[str] = field(default_factory=list)
    note: str = ""


def check(manifest: Manifest) -> TrustResult:
    engines = list(manifest.solvers)
    if len(engines) < 2 and manifest.dev_oracle != "decide-both-ways":
        return TrustResult(False, note=f"need >=2 unrelated engines, got {engines}")
    # TODO(gate): run each engine (+ decide-both-ways for bridges; + own-vs-
    # machine cross-check when machine_tool is declared); require agreement.
    return TrustResult(
        True,
        earned="checked",
        note=f"structure ok; engines={engines}; "
        f"cross_check={'machine' in (manifest.machine_tool.use if manifest.machine_tool else ())} "
        "[execution TODO(gate)]",
    )
