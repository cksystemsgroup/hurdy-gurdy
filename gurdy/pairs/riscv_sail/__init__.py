"""The ``riscv-sail`` pair (ALU slice) — RISC-V → SAIL.

The front of the *indirect* RISC-V→BTOR2 branch: it lifts a RISC-V program
into the Sail model's representation, which ``sail-btor2`` then lowers. Its
whole reason to exist is the corroboration of the direct ``riscv-btor2``
translator via the route-grader's branch-agreement cross-check — and, since
``0.2``, its own decidable square: the RISC-V reference interpreter against
translate→Sail-interpret→carry-back, aligned under ``π`` (so the pair's
faithfulness is measured per construct, not only end-to-end via the branch).
"""

from __future__ import annotations

import json
from typing import Any

from ...core import oracle, registry
from ...core.registry import Pair, Status
from ...core.types import AlignResult, Projection, Trace

# Importing the languages registers the shared interpreters this pair reuses.
from ...languages import riscv as _riscv  # noqa: F401
from ...languages import sail as _sail  # noqa: F401

from ...languages.riscv import load_elf
from ...languages.riscv.inventory import ALL_PROBES
from ...languages.sail import run as sail_run
from .translate import translate

_REGS = tuple(f"x{r}" for r in range(1, 32))
PROJECTION = Projection(("pc", *_REGS, "halted"))
_DEFAULT_SP = 1 << 20


def _compose_from_upstream(prev, params: dict) -> dict:
    """Wrap a predecessor's ELF bytes (e.g. from ``c-riscv``) into this pair's
    input, so the indirect Sail route also heads a C program."""
    image = load_elf(prev) if isinstance(prev, (bytes, bytearray)) else prev
    program = {"image": image, "init_regs": params.get("init_regs", {2: _DEFAULT_SP})}
    if "property" in params:
        program["property"] = params["property"]
    return program


def lift(target_trace: Trace) -> Trace:
    return list(target_trace)   # states are already RISC-V-shaped (pc, x*, halted)


def square(program: dict[str, Any], max_steps: int = 10_000) -> AlignResult:
    """Check the commuting square for ``program``: the shared RISC-V reference
    interpreter vs translate→Sail-interpret→carry-back, aligned under ``π``.

    Both interpreters record post-step states, so the traces align
    step-for-step (the Sail object rebases ``entry`` to 0, matching the
    word-image probes; the initial memory travels inside the artifact).
    Note the pc field is compared relative to each side's entry, so a
    rebased Sail object aligns with a nonzero-based image.
    """
    pair = registry.get_pair("riscv-sail")
    image = program["image"]
    init_regs = program.get("init_regs", {})

    # Translate first: the source run mutates the shared image's memory
    # (stores), and the artifact must carry the *initial* memory.
    artifact = translate(program)
    src = list(pair.source_interpreter(image, {"regs": init_regs}, max_steps=max_steps))
    sail_obj = json.loads(artifact.decode())
    carried = lift(sail_run(sail_obj, {}, max_steps=max_steps))
    # The Sail object is entry-rebased to 0; align pc relative to the entries.
    base = image.entry
    if base:
        carried = [{**row, "pc": (row["pc"] + base) & ((1 << 64) - 1)}
                   for row in carried]
    return oracle.align(src, carried, pair.projection)


# Registered last so the square oracle can be wired in (the coverage harness
# measures Definition 4.6's conjunction through it). Probes are the
# language-owned RV64IMC inventory — the same 96-construct yardstick the
# direct ``riscv-btor2`` route is measured against (Definition 4.6 fixes the
# inventory per language, so the two routes cannot quote different totals).
registry.register_pair(
    Pair(
        id="riscv-sail",
        source="riscv",
        target="sail",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="checked",
        translator_version="0.2",   # 0.1 -> 0.2: initial memory carried (I20)
        status=Status.PARTIAL,
        compose_input=_compose_from_upstream,
        probes=ALL_PROBES,
        square=square,
    )
)

__all__ = ["translate", "lift", "square", "PROJECTION"]
