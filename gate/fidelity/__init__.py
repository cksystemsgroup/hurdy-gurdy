"""The fidelity battery: F0 (real) .. F4 (stub). Each check returns a
``CheckResult``; ``run_gate`` runs everything up to the manifest target."""

from gate.fidelity.f0_typed import check as f0
from gate.fidelity.f1_tested import check as f1
from gate.fidelity.f2_bounded import check as f2
from gate.fidelity.f3_lowering import check as f3

__all__ = ["f0", "f1", "f2", "f3"]
