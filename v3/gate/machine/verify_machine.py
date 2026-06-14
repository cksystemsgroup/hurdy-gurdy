"""Gate a btor2-machine realization (whole-machine equivalence to Sail).

Wraps ``tools.sail_btor2_machine.verify``; on ``green`` flips the group's
``equivalence`` to GREEN and publishes the realization. Until then, any
pair's ``machine_tool`` path stays unavailable (merge policy refuses to rely
on an un-gated realization).
"""

from __future__ import annotations

from pathlib import Path

from gurdy.core.report import MachineFidelityReport

SEMANTICS = Path(__file__).resolve().parents[2] / "semantics"


def gate_machine(group: str) -> MachineFidelityReport:
    # TODO(gate): load semantics/<group>/GROUP.yaml, generate (or load) the
    # btor2-machine, run tools.sail_btor2_machine.verify against the pinned
    # Sail model, subtract IDF, return the report. Publish on green.
    return MachineFidelityReport(realization=f"{group}@btor2-machine")
