"""Keep the aarch64-btor2 pair registered for the whole aarch64 test suite.

Tests under ``tests/core/`` use an autouse fixture that calls
``_clear_registry_for_tests()`` in teardown and does not restore the prior
state, so by the time these tests run the global pair registry can be empty.
The pair package is import-cached, so its import-time ``register_pair`` side
effect does not re-run on a later ``import``. Re-register the pair before each
test here so registry lookups (``get_pair`` and the bench harness /
engine_bench / oracle_cross paths) succeed regardless of suite ordering.

This is the registration-robustness step the PAIR_TEMPLATE.md landing checklist
calls for; every landed pair whose tests reach the registry needs the
equivalent conftest.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _ensure_aarch64_pair_registered():
    from gurdy.core.pair import get_pair, register_pair
    from gurdy.pairs.aarch64_btor2 import PAIR

    try:
        get_pair(PAIR.identifier)
    except KeyError:
        register_pair(PAIR)
    yield
