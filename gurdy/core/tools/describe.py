"""``describe(topic, pair)`` tool: schema-on-demand."""

from __future__ import annotations

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
    """
    return _index_for(pair).describe(topic)


def topics(pair: str) -> tuple[str, ...]:
    return _index_for(pair).topics()


def _reset_cache_for_tests() -> None:
    _index_for.cache_clear()


__all__ = ["describe", "topics"]
