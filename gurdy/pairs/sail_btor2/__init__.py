"""The ``sail-btor2`` pair — SAIL → BTOR2.

The *indirect* arm of the ISA→BTOR2 branches: it derives the BTOR2 model from
the Sail-derived ``Expr`` semantics, independently of the direct hand-written
translators. Composed after ``riscv-sail`` it gives a second ``riscv → smtlib``
route, which the route-grader's ``branch_agreement`` cross-checks against the
direct one (ROUTES.md §4-5).

Translator ``0.1`` → ``0.2`` (a versioned event, AGENTS.md §3): the additive
**AArch64 arm** — a Sail object tagged ``isa=aarch64`` (as ``aarch64-sail``
emits) now lowers to a BTOR2 system over ``aarch64-btor2``'s state space
(``pc``, ``x0``–``x30``, ``sp``, ``nzcv``, the ``m0``–``m{MEM_WINDOW-1}``
memory window, ``halted``), its datapaths ``expr.lower``-ed from the *same*
Sail-derived ``Expr`` trees the shared Sail interpreter's A64 arm evaluates
(``languages/sail/aarch64``). Composed after ``aarch64-sail`` this completes
the second ``aarch64 → smtlib`` route, branch-cross-checked against the direct
``aarch64-btor2`` at BTOR2 — the same structure RISC-V has. The RISC-V arm is
byte-for-byte unchanged (no RISC-V Sail object carries an ``isa`` key).
"""

from __future__ import annotations

from typing import Any

from ...core import oracle, registry
from ...core.registry import Pair, Status
from ...core.types import AlignResult, Projection

# Importing the languages registers the shared interpreters this pair reuses.
from ...languages import btor2 as _btor2  # noqa: F401
from ...languages import sail as _sail  # noqa: F401
from .inventory import ALL_PROBES
from .lift import lift
from .translate import translate

_REGS = tuple(f"x{r}" for r in range(1, 32))
PROJECTION = Projection(("pc", *_REGS, "halted"))

registry.register_pair(
    Pair(
        id="sail-btor2",
        source="sail",
        target="btor2",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="checked",
        translator_version="0.2",   # 0.1 -> 0.2: the additive AArch64 arm
        status=Status.PARTIAL,
        probes=ALL_PROBES,
    )
)

__all__ = ["translate", "lift", "square", "square_aarch64", "aarch64_projection",
           "PROJECTION"]


def square(program: dict[str, Any], max_steps: int = 10_000) -> AlignResult:
    """Commuting square for a Sail program: the Sail interpreter vs
    translate→BTOR2-interpret→carry-back, aligned under ``π``."""
    pair = registry.get_pair("sail-btor2")
    init_regs = program.get("init_regs", {})
    initial_mem = {int(k): int(v) for k, v in program.get("mem", {}).items()}
    artifact = translate(program)
    src = list(pair.source_interpreter(program, {"regs": init_regs}, max_steps=max_steps))
    n = len(src)
    btrace = pair.target_interpreter(artifact, {"steps": n + 1, "state": {"mem": initial_mem}})
    carried = lift(btrace)
    return oracle.align(src, carried[1 : n + 1], pair.projection)


def aarch64_projection() -> Projection:
    """The A64 arm's ``π``: post-step ``pc``, ``x0..x30``, ``sp``, ``nzcv``, the
    memory window ``m0..m{MEM_WINDOW-1}``, ``halted`` — identical to the AArch64
    pairs' projection, so the branch cross-check at BTOR2 compares like with
    like. Constructed lazily (the aarch64 language loads only when the A64 arm
    is exercised, mirroring the translator's deferred dispatch)."""
    from ...languages.aarch64.interp import MEM_WINDOW, NREG

    regs = tuple(f"x{r}" for r in range(NREG))
    mems = tuple(f"m{i}" for i in range(MEM_WINDOW))
    return Projection(("pc", *regs, "sp", "nzcv", *mems, "halted"))


def square_aarch64(program: dict[str, Any], max_steps: int = 10_000) -> AlignResult:
    """Commuting square for an A64 Sail object (``isa=aarch64``): the shared
    Sail interpreter's A64 arm vs translate→BTOR2-interpret→carry-back, aligned
    under the A64 ``π``.

    A BTOR2 run's first row is the *initial* state, so the carried trace aligns
    with the source shifted by one cycle (exactly the RISC-V ``square`` above).
    The BTOR2 ``mem`` array is seeded from the object's ``init_mem`` via the
    interpreter's per-state override (the window states are init-seeded in
    ``T``), mirroring ``aarch64-btor2``'s square."""
    pair = registry.get_pair("sail-btor2")
    artifact = translate(program)
    src = list(pair.source_interpreter(program, {}, max_steps=max_steps))
    n = len(src)
    tbind: dict[str, Any] = {"steps": n + 1}
    init_mem = {int(a): int(v) & 0xFF for a, v in program.get("init_mem", {}).items()}
    if init_mem:
        tbind["state"] = {"mem": init_mem}
    carried = lift(pair.target_interpreter(artifact, tbind))
    return oracle.align(src, carried[1 : n + 1], aarch64_projection())
