"""The ``riscv-sail`` pair (ALU slice) — RISC-V → SAIL.

The front of the *indirect* RISC-V→BTOR2 branch: it lifts a RISC-V program
into the Sail model's representation, which ``sail-btor2`` then lowers. Its
whole reason to exist is the corroboration of the direct ``riscv-btor2``
translator via the path-grader's branch-agreement cross-check.
"""

from __future__ import annotations

from ...core import registry
from ...core.registry import Pair, Status
from ...core.types import Projection, Trace

# Importing the languages registers the shared interpreters this pair reuses.
from ...languages import riscv as _riscv  # noqa: F401
from ...languages import sail as _sail  # noqa: F401
import struct

from ...languages.riscv import asm, load_elf
from ...languages.riscv.interp import image_from_bytes, image_from_words
from ..sail_btor2.inventory import ALL_PROBES as _SAIL_ALL
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

# Reuse the Sail inventory as RISC-V image probes, so composed coverage measures
# the Sail route's head. A compressed probe carries its original 16-bit
# encoding (``halfs``) -> a real RV64C image (so the route exercises
# decompression); a base probe is laid out as 32-bit words.
def _image(p: dict):
    if "halfs" in p:
        code = b"".join(struct.pack("<H", h & 0xFFFF) for h in p["halfs"])
        return image_from_bytes(code + struct.pack("<I", asm.ecall()))
    return image_from_words(p["words"])


PROBES = {name: {"image": _image(p), "init_regs": {}} for name, p in _SAIL_ALL.items()}


def lift(target_trace: Trace) -> Trace:
    return list(target_trace)   # routing front; squared end-to-end via the branch check


registry.register_pair(
    Pair(
        id="riscv-sail",
        source="riscv",
        target="sail",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="checked",
        translator_version="0.1",
        status=Status.PARTIAL,
        compose_input=_compose_from_upstream,
        probes=PROBES,
    )
)

__all__ = ["translate", "lift", "PROJECTION"]
