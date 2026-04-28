"""Annotation lookup engine — backs the ``introspect`` tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gurdy.core.annotation.sidecar import AnnotationSidecar
from gurdy.core.annotation.types import Annotation, Role


@dataclass(frozen=True)
class IntrospectQuery:
    """A read-only query over an annotation sidecar."""

    layer: str | None = None
    nid: int | None = None
    role: Role | str | None = None
    # Free-form predicates against source_mapping fields. The dict's
    # entries are treated as exact-match constraints.
    source_mapping: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IntrospectResult:
    matches: tuple[Annotation, ...]


def query(sidecar: AnnotationSidecar, q: IntrospectQuery) -> IntrospectResult:
    out: list[Annotation] = []
    role = q.role
    if isinstance(role, str):
        role = Role(role)
    for a in sidecar.entries:
        if q.layer is not None and a.layer != q.layer:
            continue
        if q.nid is not None and a.nid != q.nid:
            continue
        if role is not None and a.role is not role:
            continue
        if q.source_mapping:
            sm = a.source_mapping
            if sm is None:
                continue
            if not _matches(sm, q.source_mapping):
                continue
        out.append(a)
    return IntrospectResult(matches=tuple(out))


def _matches(source_mapping: Any, expected: dict[str, Any]) -> bool:
    if isinstance(source_mapping, dict):
        for k, v in expected.items():
            if source_mapping.get(k) != v:
                return False
        return True
    # dataclass-like
    for k, v in expected.items():
        if not hasattr(source_mapping, k):
            return False
        if getattr(source_mapping, k) != v:
            return False
    return True


__all__ = ["IntrospectQuery", "IntrospectResult", "query"]
