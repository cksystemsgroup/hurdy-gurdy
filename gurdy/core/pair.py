"""The Pair protocol object and registry.

A pair is a fixed combination of a source language and a reasoning
language. The framework knows nothing about either; it just holds
``Pair`` records in a registry and dispatches calls to the callables
they expose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from gurdy.core.annotation.sidecar import AnnotationSidecar
from gurdy.core.diagnostics import Diagnostic
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.core.spec.base import BaseSpec

if False:  # for type checkers only — avoids circular import at runtime
    from gurdy.core.interp.align import Projection
    from gurdy.core.interp.types import (
        InputBinding,
        ReasoningBinding,
        ReasoningTrace,
        SourceTrace,
    )


# ---------------------------------------------------------------------------
# Protocols (callables that pairs supply)
# ---------------------------------------------------------------------------


@runtime_checkable
class SourceLoader(Protocol):
    """Reads the pair's source format from bytes (or a path) into a
    pair-specific ``Source`` object. The framework treats Source as
    opaque — the translator is the consumer."""

    def __call__(self, payload: bytes | Path) -> Any: ...


@runtime_checkable
class SpecValidator(Protocol):
    """Returns diagnostics for a (spec, source) pair. An empty iterable
    means the spec validates."""

    def __call__(self, spec: BaseSpec, source: Any) -> Iterable[Diagnostic]: ...


@runtime_checkable
class AnnotationEmitter(Protocol):
    """Threaded into the translator. The translator records provenance,
    role, and source-mapping per emitted node through this object.

    The concrete implementation lives in ``gurdy.core.annotation``;
    the protocol here is what the translator sees."""

    def emit(
        self,
        layer: str,
        nid: int,
        role: str,
        source_mapping: Any | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> None: ...


@runtime_checkable
class Translator(Protocol):
    """Compiles ``(spec, source)`` into a layered artifact.

    Returns a ``CompiledArtifact``. The framework's annotation emitter
    is passed in so that provenance/source-mapping is recorded as
    nodes are produced."""

    def translate(
        self,
        spec: BaseSpec,
        source: Any,
        annotation_emitter: AnnotationEmitter,
    ) -> "CompiledArtifact": ...


@runtime_checkable
class Lifter(Protocol):
    """Maps a raw solver result through the artifact's annotation back
    to source-level facts. Each pair's lifter handles its own raw
    payload format."""

    def lift(self, artifact: "CompiledArtifact", raw: Any) -> Any: ...


@runtime_checkable
class SourceInterpreter(Protocol):
    """Runs source code on a concrete ``InputBinding`` and returns a
    ``SourceTrace``. Deterministic; no search, no symbolic state.

    The pair's interpreter is responsible for honouring the spec's
    entry assumptions (e.g. excluded PC ranges) when the caller threads
    them in through the binding. The framework treats the binding and
    trace contents as opaque.
    """

    def run(
        self,
        source: Any,
        binding: "InputBinding",
        max_steps: int,
        *,
        spec: Any | None = None,
    ) -> "SourceTrace": ...


@runtime_checkable
class ReasoningInterpreter(Protocol):
    """Evaluates a compiled artifact on a concrete ``ReasoningBinding``
    and returns a ``ReasoningTrace``. Deterministic; no search.

    Per-step evaluation supplies values for every state and input nid;
    the interpreter applies the artifact's transition relation
    mechanically and reports whether the ``bad`` clause has fired.
    """

    def run(
        self,
        artifact: "CompiledArtifact",
        binding: "ReasoningBinding",
        max_steps: int,
    ) -> "ReasoningTrace": ...


@runtime_checkable
class SolverBackend(Protocol):
    """Runs a single solver against the flattened reasoning artifact.

    Concrete subclasses live under each pair's ``solvers/`` directory.
    The framework is responsible for timeouts and structured result
    shaping; the backend's job is to invoke the solver and pull its
    raw verdict and payload."""

    name: str

    def dispatch(
        self,
        artifact_bytes: bytes,
        directive: Any,
    ) -> "RawSolverResult": ...


# ---------------------------------------------------------------------------
# Layer + artifact data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Layer:
    """A named, content-addressable piece of a compiled artifact."""

    name: str
    body: bytes
    content_hash: str


@dataclass(frozen=True)
class CompiledArtifact:
    """Result of ``compile(spec)``."""

    pair: str
    layers: Mapping[str, Layer]
    annotation: AnnotationSidecar
    flattened: bytes
    schema_version: str
    spec_hash: str


# ---------------------------------------------------------------------------
# LayerSpec (declared by pairs)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerSpec:
    """Declares a layer the pair emits.

    ``stability`` documents the layer's invalidation profile (universal,
    per-ISA, per-question, etc.); the cache uses this informationally
    only. ``depends_on`` lists layers whose names this layer may
    reference via the linker."""

    name: str
    stability: str
    depends_on: tuple[str, ...] = ()
    description: str = ""


# ---------------------------------------------------------------------------
# Pair record + registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pair:
    """The unit of registration: one source/reasoning translation.

    Beyond translation, every pair must also expose concrete
    interpreters for both languages plus a *projection* that maps
    reasoning-side state to source-side state for cross-checking. The
    interpreters are the contract for the ``simulate``, ``evaluate``,
    ``cross_check``, ``replay``, and ``check`` tools.

    During the v0.1.0 → v0.2.0 transition the interpreter fields are
    optional (default ``None``) so that pairs can be migrated one at a
    time. Once a pair sets ``interpreter_version`` to a non-empty
    string it is expected to provide a working ``SourceInterpreter``
    and ``ReasoningInterpreter``; ``register_pair`` enforces this.
    """

    identifier: str
    schema_version: str
    source_loader: SourceLoader
    spec_class: type[BaseSpec]
    spec_validator: SpecValidator
    layer_specs: tuple[LayerSpec, ...]
    translator: Translator
    lifter: Lifter
    solvers: Mapping[str, type[SolverBackend]]
    schema_path: Path
    extras: Mapping[str, Any] = field(default_factory=dict)
    source_interpreter: SourceInterpreter | None = None
    reasoning_interpreter: ReasoningInterpreter | None = None
    projection: Any | None = None  # Callable[[CompiledArtifact], Projection]
    witness_replayer: Any | None = None  # Callable[[CompiledArtifact, RawSolverResult], JoinedTrace]
    predicate_evaluator: Any | None = None  # backs the ``check`` tool
    interpreter_version: str = ""


_REGISTRY: dict[str, Pair] = {}


def register_pair(pair: Pair) -> None:
    """Add a pair to the singleton registry. Re-registering the same
    identifier with the same schema version is a no-op (idempotent for
    test-suite imports); a different schema version is an error.

    A pair declaring an ``interpreter_version`` must also supply both
    a ``source_interpreter`` and a ``reasoning_interpreter``. Pairs
    leaving ``interpreter_version`` empty register without interpreters
    (deprecated path; warned by the tool surface, not here)."""

    if pair.interpreter_version:
        if pair.source_interpreter is None:
            raise ValueError(
                f"pair {pair.identifier!r} declares interpreter_version "
                f"{pair.interpreter_version!r} but has no source_interpreter"
            )
        if pair.reasoning_interpreter is None:
            raise ValueError(
                f"pair {pair.identifier!r} declares interpreter_version "
                f"{pair.interpreter_version!r} but has no reasoning_interpreter"
            )

    existing = _REGISTRY.get(pair.identifier)
    if existing is None:
        _REGISTRY[pair.identifier] = pair
        return
    if existing is pair:
        return
    if existing.schema_version != pair.schema_version:
        raise ValueError(
            f"pair {pair.identifier!r} already registered with schema "
            f"version {existing.schema_version!r}; cannot re-register "
            f"with {pair.schema_version!r}"
        )
    # Identifier+version match: replace silently. Useful for hot-reload.
    _REGISTRY[pair.identifier] = pair


def get_pair(identifier: str) -> Pair:
    try:
        return _REGISTRY[identifier]
    except KeyError as exc:  # pragma: no cover - exercised via tests
        raise KeyError(f"no pair registered with identifier {identifier!r}") from exc


def list_pairs() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def unregister_pair(identifier: str) -> None:
    """Test/utility helper. Not part of the user-facing surface."""
    _REGISTRY.pop(identifier, None)


def _clear_registry_for_tests() -> None:
    _REGISTRY.clear()


__all__ = [
    "Pair",
    "LayerSpec",
    "Layer",
    "AnnotationSidecar",
    "CompiledArtifact",
    "RawSolverResult",
    "SourceLoader",
    "SpecValidator",
    "AnnotationEmitter",
    "Translator",
    "Lifter",
    "SolverBackend",
    "SourceInterpreter",
    "ReasoningInterpreter",
    "register_pair",
    "get_pair",
    "list_pairs",
    "unregister_pair",
]
