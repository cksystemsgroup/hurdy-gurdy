"""Base spec types shared across pairs.

Each pair provides its own ``QuestionSpec`` subclass and per-pair
vocabulary. The framework supplies the structural skeleton: the spec
must have a ``pair`` identifier and must serialize to a stable JSON
form so that ``spec_hash`` is well-defined.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from typing import Any, ClassVar


def _to_jsonable(value: Any) -> Any:
    """Recursively convert dataclasses, frozensets, tuples, and bytes
    into deterministic JSON-friendly structures."""

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "__type__": type(value).__name__,
            **{
                f.name: _to_jsonable(getattr(value, f.name))
                for f in dataclasses.fields(value)
            },
        }
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return ["__set__", *sorted((_to_jsonable(v) for v in value), key=repr)]
    if isinstance(value, bytes):
        return {"__bytes_hex__": value.hex()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # Fallback: stringify exotic objects (e.g. enum) by their repr/value.
    if hasattr(value, "value"):
        return _to_jsonable(value.value)
    return repr(value)


@dataclass(frozen=True)
class BaseObservable:
    """Marker base for pair-specific observables."""


@dataclass(frozen=True)
class BaseAssumption:
    """Marker base for pair-specific assumptions/constraints."""


@dataclass(frozen=True)
class BaseProperty:
    """Marker base for pair-specific properties (bad/goal expressions)."""


@dataclass(frozen=True)
class BaseAnalysisDirective:
    """Marker base for pair-specific solver-selection directives."""

    engine: str
    bound: int | None = None
    timeout: float | None = None


@dataclass(frozen=True)
class BaseSpec:
    """Base class for ``QuestionSpec`` types.

    Pairs subclass this and add their own fields (binary, scope,
    observables, assumptions, learned, property, analysis). The framework
    only needs structural access to ``pair`` and to a serializable
    representation for hashing/caching.
    """

    pair: ClassVar[str] = ""

    def to_jsonable(self) -> dict[str, Any]:
        """Stable JSON-friendly representation. Subclasses generally
        do not need to override this; ``_to_jsonable`` already handles
        nested dataclasses."""
        return {
            "__type__": type(self).__name__,
            "pair": self.pair,
            "fields": _to_jsonable(self),
        }

    def canonical_bytes(self) -> bytes:
        """Deterministic byte-encoding used for hashing."""
        payload = self.to_jsonable()
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )

    def spec_hash(self) -> str:
        """SHA-256 hex digest of the canonical encoding."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


__all__ = [
    "BaseSpec",
    "BaseObservable",
    "BaseAssumption",
    "BaseProperty",
    "BaseAnalysisDirective",
    "_to_jsonable",
]
