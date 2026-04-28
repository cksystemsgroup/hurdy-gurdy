"""``introspect(artifact, query)`` tool — annotation lookup."""

from __future__ import annotations

from gurdy.core.annotation.lookup import IntrospectQuery, IntrospectResult, query
from gurdy.core.annotation.sidecar import AnnotationSidecar
from gurdy.core.pair import CompiledArtifact


def introspect(
    artifact: CompiledArtifact, q: IntrospectQuery
) -> IntrospectResult:
    sidecar = artifact.annotation
    if not isinstance(sidecar, AnnotationSidecar):
        # Pair returned the framework's frozen-record placeholder rather
        # than a real sidecar. Treat as empty.
        return IntrospectResult(matches=())
    return query(sidecar, q)


__all__ = ["introspect", "IntrospectQuery", "IntrospectResult"]
