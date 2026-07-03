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
from ...languages.ebpf.interp import CALL_CLOBBERED
from .inventory import ALL_PROBES
from .lift import _is_call as lift_is_call
from .lift import helper_inputs_from_behavior, lift
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
        translator_version="0.5",  # 0.5: off-the-end -> halted (I21); 0.4: CALL lowering.
        status=Status.PARTIAL,
        probes=ALL_PROBES,
    )
)

__all__ = ["translate", "lift", "square", "helper_inputs_from_behavior", "PROJECTION"]


def _call_input_binding(artifact: bytes, prog: Any, src: list, helper_inputs: list) -> dict:
    """Build the BTOR2 per-cycle ``inputs`` binding that feeds the *same* helper
    returns to the BTOR2 model the interpreter consumed.

    Each dynamic ``CALL`` (the ``k``-th, at cycle ``c`` = its position in ``src``)
    reads the BTOR2 inputs ``call{pc}_r{reg}`` at cycle ``c``; map the stream's
    ``k``-th ``{reg: value}`` onto those input nodes (resolved by symbol). Cycle
    ``c`` executes the instruction at the pre-cycle pc — ``prog.entry`` for the
    first cycle, else the previous source row's pc.
    """
    from ...languages.btor2.model import from_text

    sys = from_text(artifact.decode("utf-8"))
    by_symbol = {n.symbol: n.id for n in sys.nodes.values() if n.op == "input"}
    insns = prog.insns
    inputs: dict[int, dict[int, int]] = {}
    k = 0
    for c in range(len(src)):
        pc = prog.entry if c == 0 else src[c - 1].get("pc")
        if pc is None or not (0 <= pc < len(insns)):
            continue
        if not lift_is_call(insns[pc]):
            continue
        effect = helper_inputs[k] if k < len(helper_inputs) else {}
        k += 1
        row = inputs.setdefault(c, {})
        for reg in CALL_CLOBBERED:
            nid = by_symbol.get(f"call{pc}_r{reg}")
            if nid is not None:
                row[nid] = int(effect.get(reg, 0)) & ((1 << 64) - 1)
    return inputs


def square(program: dict[str, Any], max_steps: int = 10_000) -> AlignResult:
    """Check the commuting square for ``program`` (no solver needed): run the
    eBPF interpreter and the translate->BTOR2-interpret->carry-back path and
    align them under ``π``. The BTOR2 trace's first row is the initial state,
    so the source trace aligns with the BTOR2 trace shifted by one cycle.

    ``program['helper_inputs']`` (optional) is the helper-return stream for
    ``CALL`` (a list of per-call-execution ``{reg: value}`` dicts). It is fed to
    *both* sides — the interpreter consumes it directly; the BTOR2 model reads
    the same values from its per-call input nodes — so the square is exercised
    on non-trivial helper returns, not only the all-zero default.
    """
    pair = registry.get_pair("ebpf-btor2")
    prog = program["prog"]
    init_regs = program.get("init_regs", {})
    helper_inputs = [dict(d) for d in program.get("helper_inputs", [])]

    initial_mem = dict(prog.mem)
    # The packet is a constant BTOR2 array; thread its bytes as initial state
    # so the target run reads the same packet the source interpreter does.
    initial_pkt = {int(k): int(v) & 0xFF for k, v in getattr(prog, "pkt", {}).items()}
    artifact = translate(program)
    src = list(pair.source_interpreter(
        prog, {"regs": init_regs, "helper_inputs": helper_inputs}, max_steps=max_steps))
    n = len(src)
    btor_inputs = _call_input_binding(artifact, prog, src, helper_inputs)
    btrace = pair.target_interpreter(
        artifact,
        {"steps": n + 1, "state": {"mem": initial_mem, "pkt": initial_pkt}, "inputs": btor_inputs},
    )
    carried = lift(btrace)
    return oracle.align(src, carried[1 : n + 1], pair.projection)


# Wire the square oracle onto the registered pair (Definition 4.6 conjunction).
registry.attach_square("ebpf-btor2", square)
