"""The ``ebpf-btor2`` pair (thin slice) — eBPF -> BTOR2.

A second front-end into the BTOR2 hub: it reuses the shared BTOR2 interpreter,
the commuting-square oracle, the coverage harness, and (via the BTOR2 ``bad``
signal it emits) the ``btor2-smtlib`` decide path — contributing only the
eBPF interpreter and the per-opcode lowering. ``square()`` runs the commuting
check ``I_s(p) ≡_π L(I_t(T(p)))`` through the framework oracle.
"""

from __future__ import annotations

from typing import Any

from ...core import oracle, registry
from ...core.registry import Pair, Status
from ...core.types import AlignResult, Projection

# Importing the languages registers the shared interpreters this pair reuses.
from ...languages import btor2 as _btor2  # noqa: F401
from ...languages import ebpf as _ebpf  # noqa: F401
from .inventory import ALL_PROBES
from .lift import lift
from .translate import translate

_REGS = tuple(f"r{r}" for r in range(11))
PROJECTION = Projection(("pc", *_REGS, "halted"))

registry.register_pair(
    Pair(
        id="ebpf-btor2",
        source="ebpf",
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
    eBPF interpreter and the translate->BTOR2-interpret->carry-back path and
    align them under ``π``. The BTOR2 trace's first row is the initial state,
    so the source trace aligns with the BTOR2 trace shifted by one cycle.
    """
    pair = registry.get_pair("ebpf-btor2")
    prog = program["prog"]
    init_regs = program.get("init_regs", {})

    initial_mem = dict(prog.mem)
    artifact = translate(program)
    src = list(pair.source_interpreter(prog, {"regs": init_regs}, max_steps=max_steps))
    n = len(src)
    btrace = pair.target_interpreter(
        artifact, {"steps": n + 1, "state": {"mem": initial_mem}}
    )
    carried = lift(btrace)
    return oracle.align(src, carried[1 : n + 1], pair.projection)
