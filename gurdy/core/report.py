"""Fidelity levels and gate reports.

``FidelityReport`` is what the pair gate emits; ``MachineFidelityReport`` is
what the machine-model gate emits. Both are pure data — the merge policy
reads them, they make no decisions themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Fidelity(IntEnum):
    """The correctness lattice. Compare with ``>=`` against a target."""

    F0_typed = 0
    F1_tested = 1
    F2_bounded = 2
    F3_lowering = 3
    F4_extracted = 4

    @classmethod
    def parse(cls, s: str) -> "Fidelity":
        key = s.strip().upper()
        for f in cls:
            if f.name.upper().startswith(key) or f.name.upper() == key:
                return f
        raise ValueError(f"unknown fidelity level {s!r}")

    @property
    def label(self) -> str:
        return self.name


class CheckStatus(IntEnum):
    PASS = 0
    FAIL = 1
    SKIP = 2          # not required by the target, or not yet implemented
    NOT_IMPLEMENTED = 3


@dataclass(frozen=True)
class CheckResult:
    level: Fidelity
    status: CheckStatus
    detail: str = ""


@dataclass
class FidelityReport:
    """Result of running the pair fidelity battery for one hop/branch."""

    hop_id: str
    branch: str
    checks: list[CheckResult] = field(default_factory=list)
    independence_audit_ok: bool | None = None
    independence_findings: list[str] = field(default_factory=list)
    projection_pinned_ok: bool | None = None
    reasoning_trust_ok: bool | None = None
    # the referenced model's certified capabilities and the fidelity ceiling
    # they imply (A6): a pair cannot be certified above its model.
    model_id: str | None = None
    model_certified: list[str] = field(default_factory=list)
    model_ceiling: "Fidelity | None" = None

    @property
    def level(self) -> Fidelity:
        """Highest level whose check PASSed with no FAIL at or below it."""
        achieved = Fidelity.F0_typed
        for c in sorted(self.checks, key=lambda c: c.level):
            if c.status == CheckStatus.FAIL:
                break
            if c.status == CheckStatus.PASS:
                achieved = c.level
        return achieved

    def meets(self, target: Fidelity) -> bool:
        return self.level >= target


@dataclass
class MachineFidelityReport:
    """Result of the whole-machine equivalence proof (machine model vs Sail)."""

    realization: str            # e.g. "sail-riscv@btor2-machine"
    instructions_total: int = 0
    instructions_proven: int = 0
    harness_lemma_ok: bool | None = None
    # The symbolic reference (reference_rv64.py) cross-validated against the
    # real Sail emulator on concrete inputs. None = not run; True/False = audited.
    reference_vs_sail_ok: bool | None = None
    idf_subtracted: int = 0
    divergences: list[str] = field(default_factory=list)

    @property
    def green(self) -> bool:
        return (
            self.harness_lemma_ok is True
            and self.reference_vs_sail_ok is True
            and self.instructions_total > 0
            and self.instructions_proven == self.instructions_total
            and not self.divergences
        )


@dataclass(frozen=True)
class CapabilityResult:
    """One model capability and whether the model gate certified it here.

    PASS = certified; SKIP = declared and backable but unconfirmed in this
    environment (e.g. no emulator binary); FAIL = overclaim / broken."""

    capability: str
    status: CheckStatus
    detail: str = ""


@dataclass
class ModelReport:
    """Result of the model gate: which declared capabilities are certified.

    The ``certified`` set is what bounds the fidelity of any pair that
    references this model (ROADMAP A6)."""

    model_id: str
    language: str
    declared_capabilities: tuple[str, ...] = ()
    capability_status: list[CapabilityResult] = field(default_factory=list)
    pins_ok: bool | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def certified(self) -> frozenset[str]:
        return frozenset(c.capability for c in self.capability_status
                         if c.status == CheckStatus.PASS)

    @property
    def ok(self) -> bool:
        """Clean iff pins are consistent and no declared capability FAILED.
        SKIP (unconfirmed here) does not fail the model — it just isn't
        certified in this environment."""
        return self.pins_ok is not False and not any(
            c.status == CheckStatus.FAIL for c in self.capability_status)
