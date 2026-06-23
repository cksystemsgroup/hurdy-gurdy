"""The ``evm-btor2`` pair (stack/arithmetic slice) — EVM -> BTOR2.

A front-end into the BTOR2 hub: it reuses the shared BTOR2 interpreter, the
commuting-square oracle, the coverage harness, and (via the BTOR2 ``bad``
signal it emits) the ``btor2-smtlib`` decide path — contributing only the EVM
interpreter and the per-opcode lowering. ``square()`` runs the commuting check
``I_s(p) ≡_π L(I_t(T(p)))`` through the framework oracle.

Scope (stack/arithmetic + byte-memory + storage + control-flow slice,
PAIRING.md §1): the full push family ``PUSH1`` .. ``PUSH32``, the binary
arithmetic ``ADD`` / ``MUL`` / ``SUB``, the unsigned ``DIV`` / ``MOD`` and the
signed ``SDIV`` / ``SMOD`` (each with the EVM by-zero = 0 case; ``SDIV`` with the
``INT_MIN / -1`` wrap), the stack shuffles ``POP``, the duplications ``DUP1`` ..
``DUP16`` and the swaps ``SWAP1`` .. ``SWAP16``, ``STOP``, the byte-addressed
memory ops ``MLOAD`` / ``MSTORE`` / ``MSTORE8`` (an ``Array bv256 bv8``), the
**persistent storage ops** ``SLOAD`` / ``SSTORE`` (an ``Array bv256 bv256``), and
the **control-flow ops** ``JUMP`` / ``JUMPI`` / ``JUMPDEST`` / ``PC`` (a dynamic
pc resolved against the static ``JUMPDEST`` set — the first non-linear control
flow) over 256-bit words. Every other opcode hard-aborts
``unsupported: evm:<opcode>``. Status ``partial``; fidelity ``checked`` (the
square is validated under ``π`` on a corpus every run).
"""

from __future__ import annotations

from typing import Any

from ...core import oracle, registry
from ...core.registry import Pair, Status
from ...core.types import AlignResult, Projection

# Importing the languages registers the shared interpreters this pair reuses.
from ...languages import btor2 as _btor2  # noqa: F401
from ...languages import evm as _evm  # noqa: F401
from ...languages.evm.interp import (
    MEM_WINDOW,
    STACK_SIZE,
    STORE_WINDOW,
    program_from_bytes,
)
from .inventory import ALL_PROBES
from .lift import lift
from .translate import translate

_CELLS = tuple(f"s{i}" for i in range(STACK_SIZE))
_MEM = tuple(f"m{i}" for i in range(MEM_WINDOW))   # the byte-memory window observable
_STORE = tuple(f"s_at_{i}" for i in range(STORE_WINDOW))  # the storage window observable
PROJECTION = Projection(("pc", "sp", *_CELLS, *_MEM, *_STORE, "halted"))

registry.register_pair(
    Pair(
        id="evm-btor2",
        source="evm",
        target="btor2",
        translator=translate,
        target_to_source=lift,
        projection=PROJECTION,
        fidelity="checked",
        translator_version="0.8",
        status=Status.PARTIAL,
        probes=ALL_PROBES,
    )
)

__all__ = ["translate", "lift", "square", "PROJECTION"]


def square(program: dict[str, Any], max_steps: int = 10_000) -> AlignResult:
    """Check the commuting square for ``program`` (no solver needed): run the
    EVM interpreter and the translate->BTOR2-interpret->carry-back path and
    align them under ``π``.

    Both interpreters record post-step state, but a BTOR2 run's first row is the
    *initial* state, so the source trace (which starts after the first opcode)
    aligns with the BTOR2 trace shifted by one cycle.
    """
    pair = registry.get_pair("evm-btor2")
    code = program["code"]
    prog = program_from_bytes(code, int(program.get("entry", 0)))
    binding = {
        "pc": int(program.get("entry", 0)),
        "sp": int(program.get("init_sp", 0)),
        "stack": program.get("init_stack", {}),
    }

    artifact = translate(program)
    src = list(pair.source_interpreter(prog, binding, max_steps=max_steps))
    n = len(src)
    btrace = pair.target_interpreter(artifact, {"steps": n + 1})
    carried = lift(btrace)
    return oracle.align(src, carried[1 : n + 1], pair.projection)
