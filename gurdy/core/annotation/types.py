"""Annotation types: per-node metadata for compiled artifacts.

The framework defines the structural shape (role, source mapping,
provenance). The vocabulary of source mappings is pair-specific —
the framework treats them as opaque dictionaries which the pair-
specific lifter reinterprets.
"""

from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass, field
from typing import Any, Mapping


class Role(str, enum.Enum):
    """Role of an emitted node in the reasoning artifact."""

    SORT = "sort"
    STATE = "state"
    INPUT = "input"
    INIT = "init"
    TRANSITION = "transition"
    CONSTRAINT = "constraint"
    BAD = "bad"
    OBSERVABLE = "observable"
    ASSUMPTION = "assumption"
    LEARNED_INVARIANT = "learned_invariant"
    DISPATCH = "dispatch"
    BINDING = "binding"
    HAVOC = "havoc"
    EXPRESSION = "expression"
    OTHER = "other"


@dataclass(frozen=True)
class SourceMapping:
    """Base for pair-specific source mappings.

    Pairs subclass with their own fields (PC + DWARF for RISC-V; AST
    node + line for Python). The framework treats this as a marker
    base and serializes via the dataclass field set.
    """


@dataclass(frozen=True)
class LearnedFactProvenance:
    """Records that a node originated as a learned-fact carry-forward."""

    source_question_hash: str
    source_engine: str
    validated: bool


@dataclass(frozen=True)
class NodeProvenance:
    """Provenance for a single emitted node."""

    schema_version: str
    spec_hash: str
    learned_fact: LearnedFactProvenance | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Annotation:
    """One annotation entry: which node, in which layer, what role,
    where it came from in source, and how it got here."""

    layer: str
    nid: int
    role: Role
    source_mapping: SourceMapping | Mapping[str, Any] | None = None
    provenance: NodeProvenance | None = None

    def to_jsonable(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "layer": self.layer,
            "nid": self.nid,
            "role": self.role.value,
        }
        if self.source_mapping is not None:
            out["source_mapping"] = _dataclass_to_jsonable(self.source_mapping)
        if self.provenance is not None:
            out["provenance"] = _dataclass_to_jsonable(self.provenance)
        return out

    @classmethod
    def from_jsonable(cls, obj: Mapping[str, Any]) -> "Annotation":
        return cls(
            layer=obj["layer"],
            nid=int(obj["nid"]),
            role=Role(obj["role"]),
            source_mapping=obj.get("source_mapping"),
            provenance=_provenance_from_jsonable(obj.get("provenance")),
        )


def _dataclass_to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _dataclass_to_jsonable(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {k: _dataclass_to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dataclass_to_jsonable(v) for v in value]
    if isinstance(value, enum.Enum):
        return value.value
    return value


def _provenance_from_jsonable(obj: Any) -> NodeProvenance | None:
    if obj is None:
        return None
    learned = obj.get("learned_fact")
    if learned is not None:
        learned = LearnedFactProvenance(**learned)
    return NodeProvenance(
        schema_version=obj["schema_version"],
        spec_hash=obj["spec_hash"],
        learned_fact=learned,
        extras=dict(obj.get("extras", {})),
    )


__all__ = [
    "Role",
    "SourceMapping",
    "LearnedFactProvenance",
    "NodeProvenance",
    "Annotation",
]
