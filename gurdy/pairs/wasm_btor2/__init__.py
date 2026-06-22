"""The ``wasm-btor2`` pair (thin slice) — WebAssembly -> BTOR2.

A front-end into the BTOR2 hub: it reuses the shared BTOR2 interpreter, the
commuting-square oracle, the coverage harness, and (via the BTOR2 ``bad`` signal
it emits) the ``btor2-smtlib`` decide path — contributing only the Wasm
interpreter and the per-opcode lowering. ``square()`` runs the commuting check
``I_s(p) ≡_π L(I_t(T(p)))`` through the framework oracle.

Scope: the i32-stack core (``i32.const``, ``local.get``, ``i32.add``); every
other Wasm opcode hard-aborts with a typed ``Unsupported``. Fidelity: ``checked``
(the square is validated against the shared Wasm interpreter every run).
"""

from __future__ import annotations

from typing import Any

from ...core import oracle, registry
from ...core.registry import Pair, Status
from ...core.types import AlignResult, Projection

# Importing the languages registers the shared interpreters this pair reuses.
from ...languages import btor2 as _btor2  # noqa: F401
from ...languages import wasm as _wasm  # noqa: F401
from .inventory import ALL_PROBES
from .lift import lift
from .translate import translate

PROJECTION = Projection(("pc", "halted", "sp", "stack", "locals"))

registry.register_pair(
    Pair(
        id="wasm-btor2",
        source="wasm",
        target="btor2",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="checked",
        translator_version="0.1",
        status=Status.PARTIAL,
        probes=ALL_PROBES,
    )
)

__all__ = ["translate", "lift", "square", "PROJECTION"]


def square(program: dict[str, Any], max_steps: int = 10_000) -> AlignResult:
    """Check the commuting square for ``program`` (no solver needed): run the
    Wasm interpreter and the translate->BTOR2-interpret->carry-back path and
    align them under ``π``. The BTOR2 trace's first row is the initial state,
    so the source trace aligns with the BTOR2 trace shifted by one cycle.
    """
    pair = registry.get_pair("wasm-btor2")
    mod = program["mod"]
    init_locals = program.get("init_locals", {})

    artifact = translate(program)
    src = list(pair.source_interpreter(mod, {"locals": init_locals}, max_steps=max_steps))
    n = len(src)
    btrace = pair.target_interpreter(artifact, {"steps": n + 1})
    carried = lift(btrace)
    return oracle.align(src, carried[1 : n + 1], pair.projection)
