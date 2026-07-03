"""The ``wasm-btor2`` pair (thin slice) — WebAssembly -> BTOR2.

A front-end into the BTOR2 hub: it reuses the shared BTOR2 interpreter, the
commuting-square oracle, the coverage harness, and (via the BTOR2 ``bad`` signal
it emits) the ``btor2-smtlib`` decide path — contributing only the Wasm
interpreter and the per-opcode lowering. ``square()`` runs the commuting check
``I_s(p) ≡_π L(I_t(T(p)))`` through the framework oracle.

Scope: the integer value-stack core at **two widths** — the producers
``i32.const`` / ``i64.const`` / ``local.get``, the local store ``local.set``, the
conditional ``select``, the unary comparisons ``i32.eqz`` / ``i64.eqz``, the full
binary-operator family at each width (arithmetic / bitwise / shifts /
signed&unsigned comparisons), the **division / remainder family**
``{i32,i64}.div_s`` / ``div_u`` / ``rem_s`` / ``rem_u`` with the Wasm **trap**
edge (a zero divisor — and ``div_s`` signed overflow ``INT_MIN / -1`` — sets a
``trapped`` observable, a defined halt distinct from the typed ``unsupported``
abort), and the **structured conditional** ``if <blocktype> <then> [else <else>]
end`` (lowered by the value-stack branch-merge — both arms over a copy of the
incoming static stack, joined per slot/local with ``ite``; the Wasm validation
discipline enforced or a typed ``unsupported``; a nested ``if`` allowed, while
``block`` / ``loop`` / ``br`` / ``br_if`` / ``br_table`` stay out of scope). The
value stack carries both bv32 and bv64 slots, each slot's value type tracked
statically, and locals are mutable. Every other Wasm opcode hard-aborts with a
typed ``Unsupported``. Fidelity: ``checked`` (the square is validated against the
shared Wasm interpreter every run).
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

PROJECTION = Projection(("pc", "halted", "trapped", "sp", "stack", "locals"))

registry.register_pair(
    Pair(
        id="wasm-btor2",
        source="wasm",
        target="btor2",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="checked",
        translator_version="0.3",
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


# Wire the square oracle onto the registered pair (Definition 4.6 conjunction).
registry.attach_square("wasm-btor2", square)
