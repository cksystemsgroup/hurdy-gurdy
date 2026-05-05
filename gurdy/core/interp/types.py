"""Interpreter types: concrete-input bindings, traces, joined traces,
spec evaluations, cross-check reports.

The framework owns the *envelope* of each type (pair identifier,
hashes, step indices, halt flag); the *contents* — locations, deltas,
state values — are pair-specific opaque payloads. Mirrors how
``BaseSpec`` already works.

All types are frozen dataclasses with stable ``to_jsonable`` so traces
are content-addressable and CLI-serializable.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Sequence


# ---------------------------------------------------------------------------
# Bindings
# ---------------------------------------------------------------------------


def _to_jsonable(value: Any) -> Any:
    """Generic JSON-friendly recursive encoder. Mirrors spec.base."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "__type__": type(value).__name__,
            **{
                f.name: _to_jsonable(getattr(value, f.name))
                for f in dataclasses.fields(value)
            },
        }
    if isinstance(value, dict):
        return {
            str(k): _to_jsonable(v)
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return ["__set__", *sorted((_to_jsonable(v) for v in value), key=repr)]
    if isinstance(value, bytes):
        return {"__bytes_hex__": value.hex()}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _hash_canonical(value: Any) -> str:
    payload = _to_jsonable(value)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class InputBinding:
    """Marker base for pair-specific concrete-source-input bindings.

    A binding fully determines a source-interpreter run alongside the
    spec's entry assumptions. Pairs subclass with their own fields
    (e.g. register/memory init values, per-step havoc values).
    """

    pair: ClassVar[str] = ""

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "__type__": type(self).__name__,
            "pair": self.pair,
            "fields": _to_jsonable(self),
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.to_jsonable(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def inputs_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class ReasoningBinding:
    """Marker base for pair-specific concrete reasoning-side bindings.

    Supplies all ``input`` and initial ``state`` values plus per-step
    input values where the reasoning language has them. Pairs subclass.
    """

    pair: ClassVar[str] = ""

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "__type__": type(self).__name__,
            "pair": self.pair,
            "fields": _to_jsonable(self),
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.to_jsonable(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def bindings_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Source-side trace
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceStep:
    """One step of source execution.

    ``location`` is opaque and pair-defined: for RV64 it carries
    ``{"pc": ..., "mnemonic": ..., "disasm": ..., "file": ..., "line": ...}``.
    ``deltas`` lists what changed at this step, also pair-defined.
    """

    step: int
    location: Mapping[str, Any] | None = None
    deltas: Mapping[str, Any] | None = None
    halted: bool = False

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "location": _to_jsonable(self.location) if self.location is not None else None,
            "deltas": _to_jsonable(self.deltas) if self.deltas is not None else None,
            "halted": self.halted,
        }


@dataclass(frozen=True)
class SourceTrace:
    """Per-step result of a concrete source-interpreter run."""

    pair: str
    interpreter_version: str
    inputs_hash: str
    steps: tuple[SourceStep, ...]
    final_state: Mapping[str, Any] | None = None
    halted: bool = False
    halt_reason: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "interpreter_version": self.interpreter_version,
            "inputs_hash": self.inputs_hash,
            "steps": [s.to_jsonable() for s in self.steps],
            "final_state": (
                _to_jsonable(self.final_state) if self.final_state is not None else None
            ),
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }


# ---------------------------------------------------------------------------
# Reasoning-side trace
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReasoningStep:
    """One step of reasoning-artifact evaluation.

    ``layer_values`` is keyed by layer name, then by nid. Values are
    bitvector ints or array-as-dict, pair-encoded. ``bad_fired`` is
    true at the first step the artifact's ``bad`` clause evaluates to
    true.
    """

    step: int
    layer_values: Mapping[str, Mapping[int, Any]] = field(default_factory=dict)
    bad_fired: bool = False

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "layer_values": {
                layer: {str(nid): _to_jsonable(v) for nid, v in vals.items()}
                for layer, vals in self.layer_values.items()
            },
            "bad_fired": self.bad_fired,
        }


@dataclass(frozen=True)
class ReasoningTrace:
    """Per-step result of a concrete reasoning-interpreter run."""

    pair: str
    interpreter_version: str
    artifact_hash: str
    bindings_hash: str
    steps: tuple[ReasoningStep, ...]
    bad_fired_at: int | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "interpreter_version": self.interpreter_version,
            "artifact_hash": self.artifact_hash,
            "bindings_hash": self.bindings_hash,
            "steps": [s.to_jsonable() for s in self.steps],
            "bad_fired_at": self.bad_fired_at,
        }


# ---------------------------------------------------------------------------
# Joined trace (source + reasoning at each step)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JoinedStep:
    step: int
    source: SourceStep
    reasoning: ReasoningStep

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "source": self.source.to_jsonable(),
            "reasoning": self.reasoning.to_jsonable(),
        }


@dataclass(frozen=True)
class JoinedTrace:
    """Source + reasoning trace walked in lock-step.

    Returned by ``replay`` (post-solver) and used internally by
    ``cross_check``. The two traces share an inputs binding mapped
    through the pair-specific projection.
    """

    pair: str
    inputs_hash: str
    artifact_hash: str
    steps: tuple[JoinedStep, ...]
    halted: bool = False
    bad_fired_at: int | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "inputs_hash": self.inputs_hash,
            "artifact_hash": self.artifact_hash,
            "steps": [s.to_jsonable() for s in self.steps],
            "halted": self.halted,
            "bad_fired_at": self.bad_fired_at,
        }


# ---------------------------------------------------------------------------
# Spec evaluation
# ---------------------------------------------------------------------------


class PredicateKind(str, enum.Enum):
    OBSERVABLE = "observable"
    ASSUMPTION = "assumption"
    PROPERTY = "property"


@dataclass(frozen=True)
class SpecPredicateResult:
    """Concrete evaluation result for one observable / assumption / property.

    Semantics:

    - For OBSERVABLE: ``values`` carries ``(step, value)`` pairs at every
      step the observable fires. ``fired`` is False when no step matched.
      ``holds`` is unused.
    - For ASSUMPTION: ``holds`` is True iff the assumption was satisfied
      at every observed step. ``violations`` lists the step indices where
      it was violated.
    - For PROPERTY: ``holds`` is True iff the property was *not* triggered
      within the observed bound (i.e. property is a bad expression that
      did not fire). ``violations`` lists the step indices at which it
      did fire.
    """

    name: str
    kind: PredicateKind
    fired: bool = True
    holds: bool | None = None
    violations: tuple[int, ...] = ()
    values: tuple[tuple[int, Any], ...] = ()
    note: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "fired": self.fired,
            "holds": self.holds,
            "violations": list(self.violations),
            "values": [[s, _to_jsonable(v)] for s, v in self.values],
            "note": self.note,
        }


@dataclass(frozen=True)
class SpecEvaluation:
    """Result of evaluating a spec's predicates against a concrete trace."""

    pair: str
    inputs_hash: str
    steps_executed: int
    halted: bool
    observables: tuple[SpecPredicateResult, ...] = ()
    assumptions: tuple[SpecPredicateResult, ...] = ()
    property_result: SpecPredicateResult | None = None
    diagnostics: tuple[Mapping[str, Any], ...] = ()

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "inputs_hash": self.inputs_hash,
            "steps_executed": self.steps_executed,
            "halted": self.halted,
            "observables": [o.to_jsonable() for o in self.observables],
            "assumptions": [a.to_jsonable() for a in self.assumptions],
            "property": (
                self.property_result.to_jsonable()
                if self.property_result is not None
                else None
            ),
            "diagnostics": [dict(d) for d in self.diagnostics],
        }


# ---------------------------------------------------------------------------
# Cross-check report
# ---------------------------------------------------------------------------


class CrossCheckOutcome(str, enum.Enum):
    AGREEMENT = "agreement"
    DIVERGENCE = "divergence"


@dataclass(frozen=True)
class CrossCheckReport:
    """Result of walking source and reasoning traces in lock-step."""

    pair: str
    outcome: CrossCheckOutcome
    steps_checked: int
    fields_checked: int = 0
    divergence_step: int | None = None
    divergence_label: str | None = None
    source_view: Any | None = None
    reasoning_view: Any | None = None
    note: str | None = None

    @property
    def agrees(self) -> bool:
        return self.outcome is CrossCheckOutcome.AGREEMENT

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "outcome": self.outcome.value,
            "steps_checked": self.steps_checked,
            "fields_checked": self.fields_checked,
            "divergence_step": self.divergence_step,
            "divergence_label": self.divergence_label,
            "source_view": _to_jsonable(self.source_view),
            "reasoning_view": _to_jsonable(self.reasoning_view),
            "note": self.note,
        }


__all__ = [
    "CrossCheckOutcome",
    "CrossCheckReport",
    "InputBinding",
    "JoinedStep",
    "JoinedTrace",
    "PredicateKind",
    "ReasoningBinding",
    "ReasoningStep",
    "ReasoningTrace",
    "SourceStep",
    "SourceTrace",
    "SpecEvaluation",
    "SpecPredicateResult",
    "_hash_canonical",
    "_to_jsonable",
]
