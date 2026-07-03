"""Content-addressed compilation cache (FRAMEWORK.md §2 "Cache").

Keyed ``(input hash, translator version)`` (ARCHITECTURE.md §4). Because the
translator is a pure function, the cache is sound and — once pairs compose —
extends across a route for free (ROUTES.md §2). The cache existing at all is a
restatement of the determinism invariant.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .registry import Pair

_store: dict[str, bytes] = {}


def _canonical(program: Any) -> bytes:
    """A stable byte encoding of a source program for keying.

    MVP-1 uses ``repr`` for simple inputs; a pair with a structured source
    model supplies its own serializer in a later increment.
    """
    if isinstance(program, bytes):
        return program
    return repr(program).encode("utf-8")


def cache_key(pair: Pair, program: Any) -> str:
    h = hashlib.sha256()
    h.update(_canonical(program))
    h.update(b"\x00")
    h.update(pair.id.encode("utf-8"))
    h.update(b"\x00")
    h.update(pair.translator_version.encode("utf-8"))
    return h.hexdigest()


def compile(pair: Pair, program: Any) -> bytes:
    """Translate ``program`` through ``pair`` (the square's top edge ``T``),
    memoized by content address. Deterministic: identical inputs -> identical
    bytes."""
    key = cache_key(pair, program)
    if key not in _store:
        _store[key] = bytes(pair.translator(program))
    return _store[key]


def recompile_and_diff(pair: Pair, program: Any) -> bool:
    """Determinism check (PAIRING.md §5): translate twice (bypassing the
    cache) and assert byte-identical output."""
    a = bytes(pair.translator(program))
    b = bytes(pair.translator(program))
    return a == b


def _reset() -> None:
    _store.clear()
