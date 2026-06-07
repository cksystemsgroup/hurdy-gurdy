"""Test-suite fixtures for the aarch64-btor2 pair.

Landing a second pair onto the shared framework exposes two cross-suite
hazards, both neutralised here (autouse) for every aarch64 test:

1. **Registry.** Tests under ``tests/core/`` use an autouse
   ``_clear_registry_for_tests()`` that empties the global pair registry and
   does not restore it. The pair package is import-cached, so its import-time
   ``register_pair`` does not re-run. Re-register the pair before each test so
   registry lookups (``get_pair`` and the bench harness / engine_bench /
   oracle_cross paths) succeed regardless of suite ordering.

2. **Bench module names.** ``bench/riscv-btor2/`` and ``bench/aarch64-btor2/``
   both expose top-level modules named ``harness`` / ``engine_bench`` /
   ``oracle_cross`` / ``oracle_align``. Python caches modules by bare name, and
   a riscv test imports its ``harness`` at *module level* — which runs during
   pytest's collection phase, before any test executes — poisoning the cache.
   A later aarch64 test doing an in-function ``from harness import run_task``
   then gets riscv's harness (which has no ``run_task``). Before each test, drop
   the cached names and pin aarch64's bench dir at ``sys.path[0]`` so bare bench
   imports resolve to this pair; restore the prior state afterwards so this does
   not leak into sibling-pair tests.

Every landed pair whose tests reach the registry or its bench modules needs the
equivalent conftest (see ``gurdy/pairs/PAIR_TEMPLATE.md``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BENCH = Path(__file__).resolve().parents[3] / "bench" / "aarch64-btor2"
_COLLIDING_BENCH_MODULES = ("harness", "engine_bench", "oracle_cross", "oracle_align")


@pytest.fixture(autouse=True)
def _aarch64_test_env():
    # (1) keep the pair registered despite tests/core clearing the registry
    from gurdy.core.pair import get_pair, register_pair
    from gurdy.pairs.aarch64_btor2 import PAIR

    try:
        get_pair(PAIR.identifier)
    except KeyError:
        register_pair(PAIR)

    # (2) make bare bench imports resolve to aarch64's bench, then restore so
    #     sibling-pair tests are unaffected.
    saved_path = list(sys.path)
    saved_mods = {n: sys.modules.get(n) for n in _COLLIDING_BENCH_MODULES}
    for name in _COLLIDING_BENCH_MODULES:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(_BENCH))
    try:
        yield
    finally:
        sys.path[:] = saved_path
        for name, mod in saved_mods.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod
