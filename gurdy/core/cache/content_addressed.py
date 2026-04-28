"""Content-addressed cache for compiled artifacts.

Keyed on ``(spec_hash, source_hash, schema_version)`` plus pluggable
``cache_key_extras`` per pair (e.g. solver versions or library hashes
that affect compilation).

The cache stores opaque byte payloads. The framework's ``compile`` tool
will serialize the ``CompiledArtifact`` (layers + annotation +
flattened) before storing.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional


@dataclass(frozen=True)
class CacheKey:
    spec_hash: str
    source_hash: str
    schema_version: str
    extras: Mapping[str, str] = field(default_factory=dict)

    def digest(self) -> str:
        payload = {
            "spec_hash": self.spec_hash,
            "source_hash": self.source_hash,
            "schema_version": self.schema_version,
            "extras": dict(sorted(self.extras.items())),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class CacheBackend:
    """Abstract backend. Concrete subclasses below."""

    def get(self, key: CacheKey) -> bytes | None:  # pragma: no cover - abstract
        raise NotImplementedError

    def put(self, key: CacheKey, value: bytes) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def has(self, key: CacheKey) -> bool:
        return self.get(key) is not None


class InMemoryCache(CacheBackend):
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(self, key: CacheKey) -> bytes | None:
        return self._store.get(key.digest())

    def put(self, key: CacheKey, value: bytes) -> None:
        self._store[key.digest()] = value

    def __len__(self) -> int:  # pragma: no cover - utility
        return len(self._store)


class FilesystemCache(CacheBackend):
    """Stores blobs under ``root/<digest[:2]>/<digest>``."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: CacheKey) -> Path:
        d = key.digest()
        return self.root / d[:2] / d

    def get(self, key: CacheKey) -> bytes | None:
        p = self._path(key)
        if not p.exists():
            return None
        return p.read_bytes()

    def put(self, key: CacheKey, value: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(value)
        os.replace(tmp, p)


# ---------------------------------------------------------------------------
# Convenience: source hashing
# ---------------------------------------------------------------------------


def hash_source(payload: bytes | str | Path) -> str:
    if isinstance(payload, Path):
        payload = payload.read_bytes()
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


CacheExtrasHook = Callable[[Any], Mapping[str, str]]


def build_key(
    *,
    spec_hash: str,
    source_hash: str,
    schema_version: str,
    extras_hook: Optional[CacheExtrasHook] = None,
    extras_arg: Any = None,
) -> CacheKey:
    extras: Mapping[str, str] = {}
    if extras_hook is not None:
        extras = dict(extras_hook(extras_arg))
    return CacheKey(
        spec_hash=spec_hash,
        source_hash=source_hash,
        schema_version=schema_version,
        extras=extras,
    )


__all__ = [
    "CacheKey",
    "CacheBackend",
    "InMemoryCache",
    "FilesystemCache",
    "hash_source",
    "build_key",
]
