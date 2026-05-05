"""Content-addressed cache key for interpreter traces.

Source traces key on ``(pair, interpreter_version, inputs_hash,
max_steps)``; reasoning traces add ``artifact_hash`` and
``bindings_hash``. The framework reuses ``cache.content_addressed``
backends (``InMemoryCache`` / ``FilesystemCache``) for storage.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class InterpreterCacheKey:
    pair: str
    interpreter_version: str
    role: str  # "source" | "reasoning" | "joined" | "spec_eval"
    inputs_hash: str = ""
    bindings_hash: str = ""
    artifact_hash: str = ""
    max_steps: int = 0
    extras: Mapping[str, str] = field(default_factory=dict)

    def digest(self) -> str:
        payload = {
            "pair": self.pair,
            "interpreter_version": self.interpreter_version,
            "role": self.role,
            "inputs_hash": self.inputs_hash,
            "bindings_hash": self.bindings_hash,
            "artifact_hash": self.artifact_hash,
            "max_steps": self.max_steps,
            "extras": dict(sorted(self.extras.items())),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_interpreter_key(
    *,
    pair: str,
    interpreter_version: str,
    role: str,
    inputs_hash: str = "",
    bindings_hash: str = "",
    artifact_hash: str = "",
    max_steps: int = 0,
    extras: Mapping[str, str] | None = None,
) -> InterpreterCacheKey:
    return InterpreterCacheKey(
        pair=pair,
        interpreter_version=interpreter_version,
        role=role,
        inputs_hash=inputs_hash,
        bindings_hash=bindings_hash,
        artifact_hash=artifact_hash,
        max_steps=max_steps,
        extras=dict(extras or {}),
    )


__all__ = ["InterpreterCacheKey", "build_interpreter_key"]
