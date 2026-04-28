"""Annotation sidecar persistence and the framework's emitter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Mapping

from gurdy.core.annotation.types import (
    Annotation,
    LearnedFactProvenance,
    NodeProvenance,
    Role,
)


@dataclass
class AnnotationSidecar:
    """A collection of ``Annotation`` records for one compiled artifact."""

    schema_version: str = ""
    spec_hash: str = ""
    entries: list[Annotation] = field(default_factory=list)

    # ----- mutation -----

    def add(self, annotation: Annotation) -> None:
        self.entries.append(annotation)

    def extend(self, items: Iterable[Annotation]) -> None:
        self.entries.extend(items)

    # ----- access -----

    def __iter__(self) -> Iterator[Annotation]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def by_layer(self, layer: str) -> list[Annotation]:
        return [a for a in self.entries if a.layer == layer]

    def find(self, layer: str, nid: int) -> Annotation | None:
        for a in self.entries:
            if a.layer == layer and a.nid == nid:
                return a
        return None

    def by_role(self, role: Role | str) -> list[Annotation]:
        target = role if isinstance(role, Role) else Role(role)
        return [a for a in self.entries if a.role is target]

    # ----- (de)serialization -----

    def to_json(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "spec_hash": self.spec_hash,
            "entries": [a.to_jsonable() for a in self.entries],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, data: str | bytes) -> "AnnotationSidecar":
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        obj = json.loads(data)
        return cls(
            schema_version=obj.get("schema_version", ""),
            spec_hash=obj.get("spec_hash", ""),
            entries=[Annotation.from_jsonable(e) for e in obj.get("entries", [])],
        )

    def content_hash(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


class AnnotationEmitter:
    """The concrete emitter passed into translators.

    Wraps an ``AnnotationSidecar`` and stamps every record with the
    schema version and spec hash unless an explicit override is given.
    Mutating operations are intentionally simple — this is a sink, not
    a query interface.
    """

    def __init__(self, sidecar: AnnotationSidecar):
        self._sidecar = sidecar

    @property
    def sidecar(self) -> AnnotationSidecar:
        return self._sidecar

    def emit(
        self,
        layer: str,
        nid: int,
        role: Role | str,
        source_mapping: Any | None = None,
        provenance: NodeProvenance | Mapping[str, Any] | None = None,
    ) -> None:
        if isinstance(role, str):
            role_enum = Role(role)
        else:
            role_enum = role
        if provenance is None:
            prov = NodeProvenance(
                schema_version=self._sidecar.schema_version,
                spec_hash=self._sidecar.spec_hash,
            )
        elif isinstance(provenance, NodeProvenance):
            prov = provenance
        else:
            learned = provenance.get("learned_fact")
            if isinstance(learned, dict):
                learned = LearnedFactProvenance(**learned)
            prov = NodeProvenance(
                schema_version=provenance.get(
                    "schema_version", self._sidecar.schema_version
                ),
                spec_hash=provenance.get("spec_hash", self._sidecar.spec_hash),
                learned_fact=learned,
                extras=dict(provenance.get("extras", {})),
            )
        self._sidecar.add(
            Annotation(
                layer=layer,
                nid=int(nid),
                role=role_enum,
                source_mapping=source_mapping,
                provenance=prov,
            )
        )


__all__ = ["AnnotationSidecar", "AnnotationEmitter"]
