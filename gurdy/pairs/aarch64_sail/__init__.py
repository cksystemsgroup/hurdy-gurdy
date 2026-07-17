"""The ``aarch64-sail`` pair (thin slice) — AArch64 (A64) -> Sail.

The *indirect* arm of the AArch64→BTOR2 branch: it lifts an A64 program into the
Sail ARM model's representation (the Sail-derived ``Expr`` semantics), which
``sail-btor2`` then lowers. Its whole reason to exist is the corroboration of
the direct ``aarch64-btor2`` translator via the route-grader's branch-agreement
cross-check at BTOR2 — the same fidelity-raising structure RISC-V has via
``riscv-sail`` (ROUTES.md §4-5).

It reuses both shared interpreters — the AArch64 source interpreter
(``languages/aarch64``) and the Sail target interpreter (``languages/sail``,
whose *additive* A64 arm runs the Sail object) — contributing only the
AArch64→Sail-object translator ``T``, the carry-back ``L``, and the projection
``π``. ``square()`` runs the commuting check ``I_s(p) ≡_π L(I_t(T(p)))`` through
the framework oracle.

Scope: the ALU family ``ADD``/``SUB`` (immediate) and ``MOVZ``, the NZCV writes
(``SUBS``/``CMP`` **and** ``ADDS``/``CMN`` immediate), the conditional **and**
unconditional control flow (``B.cond``, ``B``/``BL``), the first memory access —
the 64-bit unsigned-offset ``LDR``/``STR`` over a byte-addressed, little-endian
memory with a fixed ``m0``–``m{MEM_WINDOW-1}`` memory-window observable — **and the
32-bit (``W``-register) forms** of the ALU/flag-setting immediate instructions
(``ADD``/``SUB``/``MOVZ`` W and ``SUBS``/``CMP``/``ADDS``/``CMN`` W; the 32-bit
result zero-extends into ``Xd``, the flags are 32-bit) — the *same* in-scope set
``aarch64-btor2`` covers, with the *same* ``π`` (including the ``m{i}`` window), so
the two AArch64→BTOR2 routes decide the same constructs and can be
branch-cross-checked (their covered sets coincide exactly). Status: ``partial``
(PAIRING.md §1 "Start thin, then widen").

Translator ``0.1`` → ``0.2``: an optional ``property`` on the input program is
forwarded into the Sail object (as ``riscv-sail`` does), so the composed route
``aarch64-sail → sail-btor2 → btor2-smtlib`` decides reachability questions —
the second AArch64 route now composes end-to-end.
"""

from __future__ import annotations

import json
from typing import Any

from ...core import oracle, registry
from ...core.registry import Pair, Status
from ...core.types import AlignResult, Projection

# Importing the languages registers the shared interpreters this pair reuses.
from ...languages import aarch64 as _aarch64  # noqa: F401
from ...languages import sail as _sail  # noqa: F401
from ...languages.aarch64.interp import MEM_WINDOW, SP_DEFAULT
from ...languages.sail import run as sail_run  # the shared Sail interpreter (I_t)
from .inventory import ALL_PROBES
from .lift import lift
from .translate import translate

_REGS = tuple(f"x{r}" for r in range(31))
_MEM = tuple(f"m{i}" for i in range(MEM_WINDOW))   # the byte-memory window observable
# π: post-step pc, x0..x30, sp, the NZCV flags, the memory-window bytes, and the
# halt/trap flag — read out of the Sail ARM model's state. MUST match
# aarch64-btor2's projection so the branch cross-check at BTOR2 compares like with
# like (pairs/aarch64-sail brief). The m{i} window is the additive 0.6 extension.
PROJECTION = Projection(("pc", *_REGS, "sp", "nzcv", *_MEM, "halted"))


def _sail_object(artifact: bytes) -> dict[str, Any]:
    """Decode the Sail object the translator emits (its bytes are JSON)."""
    return json.loads(artifact.decode("utf-8"))


registry.register_pair(
    Pair(
        id="aarch64-sail",
        source="aarch64",
        target="sail",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="checked",
        translator_version="0.2",   # 0.1 -> 0.2: forwards an optional property
        # Branch-corroboration provenance (SCALING.md §9; protected):
        # the official Arm Sail model (ASL-derived).
        semantic_artifact="arm-sail-model",
        status=Status.PARTIAL,
        probes=ALL_PROBES,
    )
)

__all__ = ["translate", "lift", "square", "PROJECTION"]


def square(program: dict[str, Any], max_steps: int = 10_000) -> AlignResult:
    """Check the commuting square for ``program`` (no solver needed): run the
    shared AArch64 interpreter and the translate->Sail-interpret->carry-back
    path and align them under ``π``.

    Both interpreters record post-step state and halt by running off the end of
    code, so the two traces align step-for-step (unlike the BTOR2 route, whose
    first row is the initial state and needs a one-cycle shift).
    """
    pair = registry.get_pair("aarch64-sail")
    image = program["image"]
    init_regs = program.get("init_regs", {})
    init_sp = int(program.get("init_sp", SP_DEFAULT))
    init_nzcv = int(program.get("init_nzcv", 0))
    init_mem = program.get("init_mem", {})

    artifact = translate({**program, "init_sp": init_sp, "init_nzcv": init_nzcv,
                          "init_mem": init_mem})
    src = list(
        pair.source_interpreter(
            image,
            {"regs": init_regs, "sp": init_sp, "nzcv": init_nzcv, "mem": init_mem},
            max_steps=max_steps,
        )
    )
    # Sail is the *target* here; the shared Sail interpreter (`run`) is the I_t.
    # It serves both source and target roles (one model-agnostic executor — the
    # languages/sail brief), and the registry only wires a language's
    # target_interpreter field, so we call the shared `run` directly.
    sail_trace = sail_run(_sail_object(artifact), {}, max_steps=max_steps)
    carried = lift(sail_trace)
    return oracle.align(src, carried, pair.projection)


# Wire the square oracle onto the registered pair (Definition 4.6 conjunction).
registry.attach_square("aarch64-sail", square)
