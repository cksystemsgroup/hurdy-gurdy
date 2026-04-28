"""``compile(spec)`` tool: ``(spec, source) -> CompiledArtifact``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gurdy.core.annotation.sidecar import AnnotationEmitter, AnnotationSidecar
from gurdy.core.pair import CompiledArtifact, get_pair
from gurdy.core.spec.base import BaseSpec


def compile_spec(
    spec: BaseSpec, source_payload: bytes | Path | Any | None = None
) -> CompiledArtifact:
    """Route ``spec`` to its pair's translator and return the artifact.

    If ``source_payload`` is ``None``, the framework first tries to
    infer a source path from the spec (``source`` / ``source_path`` /
    ``binary`` fields). If no payload can be inferred, the loader is
    invoked with ``None`` so pairs that don't need an external payload
    can handle it themselves.
    """

    pair = get_pair(spec.pair)
    if source_payload is None:
        source_payload = _infer_source_payload(spec)
    source = pair.source_loader(source_payload)
    sidecar = AnnotationSidecar(
        schema_version=pair.schema_version, spec_hash=spec.spec_hash()
    )
    emitter = AnnotationEmitter(sidecar)
    artifact = pair.translator.translate(spec, source, emitter)
    return artifact


def _infer_source_payload(spec: BaseSpec) -> Any:
    """Best-effort: pull a path-shaped attribute off the spec.
    Returns ``None`` if nothing matches; the loader handles that case."""
    for attr in ("source", "source_path", "binary"):
        v = getattr(spec, attr, None)
        if v is None:
            continue
        path = getattr(v, "path", v)
        if isinstance(path, (str, Path)):
            return Path(path)
        return v
    return None


__all__ = ["compile_spec"]
