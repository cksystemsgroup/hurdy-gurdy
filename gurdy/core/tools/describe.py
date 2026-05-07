"""``describe(topic, pair)`` tool: schema-on-demand."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from gurdy.core.pair import get_pair
from gurdy.core.schema.indexer import SchemaEntry, SchemaIndex, load_index


@lru_cache(maxsize=64)
def _index_for(pair: str) -> SchemaIndex:
    p = get_pair(pair)
    return load_index(pair, p.schema_path)


def describe(topic: str, pair: str) -> SchemaEntry | None:
    """Return the schema entry for ``topic`` in the named pair.

    Misses return a ``SchemaEntry`` with empty body and a hint listing
    candidate topics, exactly as the schema indexer produces.

    Every entry carries the pair's ``schema_version`` and
    ``interpreter_version`` (empty if the pair declares no interpreters),
    so an LLM can branch on capability without a separate lookup.
    """
    entry = _index_for(pair).describe(topic)
    if entry is None:
        return None
    p = get_pair(pair)
    return replace(
        entry,
        schema_version=p.schema_version,
        interpreter_version=p.interpreter_version,
    )


def topics(pair: str) -> tuple[str, ...]:
    return _index_for(pair).topics()


def _reset_cache_for_tests() -> None:
    _index_for.cache_clear()


__all__ = ["describe", "topics"]
