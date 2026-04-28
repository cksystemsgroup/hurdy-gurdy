from gurdy.core.cache.content_addressed import (
    CacheKey,
    FilesystemCache,
    InMemoryCache,
    build_key,
    hash_source,
)


def test_cache_key_digest_stable_and_dependent_on_extras():
    k1 = CacheKey("s", "src", "1.0")
    k2 = CacheKey("s", "src", "1.0")
    assert k1.digest() == k2.digest()
    k3 = CacheKey("s", "src", "1.0", extras={"solver": "z3@4.13"})
    assert k1.digest() != k3.digest()


def test_in_memory_get_put_has():
    c = InMemoryCache()
    k = CacheKey("a", "b", "c")
    assert c.get(k) is None
    assert not c.has(k)
    c.put(k, b"hello")
    assert c.get(k) == b"hello"
    assert c.has(k)


def test_filesystem_cache_persists(tmp_path):
    c = FilesystemCache(tmp_path / "cache")
    k = CacheKey("a", "b", "c")
    c.put(k, b"payload")
    assert c.get(k) == b"payload"
    # Re-open and verify persistence.
    c2 = FilesystemCache(tmp_path / "cache")
    assert c2.get(k) == b"payload"


def test_hash_source_accepts_str_and_bytes():
    assert hash_source(b"x") == hash_source("x")


def test_build_key_invokes_extras_hook():
    def extras(arg):
        return {"v": str(arg)}

    k = build_key(
        spec_hash="s",
        source_hash="src",
        schema_version="1",
        extras_hook=extras,
        extras_arg=42,
    )
    assert dict(k.extras) == {"v": "42"}
