"""The grader-authoritative square — the second half of SCALING.md §12.2's
"still to harden", the consequence §3.1 spells out:

    The grader **ignores the pair's own ``square()`` / ``attach_square``** and
    rebuilds the square from ``T``, ``Λ``, ``π``, and the trusted oracle. A
    rigged ``square()`` is never called.

Today a pair ships its own ``square()`` and the coverage harness calls it. That
function is *pair code*: it can return ``AlignResult(ok=True)`` unconditionally,
shrink ``π``, run zero steps, or align a trace against itself, and every
downstream number — construct coverage, the PR gate's conjunction, the negative
control — inherits the lie. The seam of ``pure_oracle.py`` moved ``T``/``Λ`` out
of the grader's process; it did **not** stop the grader from asking the pair
what the answer is.

This module closes that. It holds a **grader-owned recipe** per pair — a
:class:`SquarePlan` written in the trusted tree (``gurdy/core``) out of trusted
parts only: the language-owned interpreters read off the registry, ``π`` from
the pair's protected projection or rebuilt from language constants, and the
binding the target interpreter runs under. :func:`grade` drives the five steps
itself, shelling exactly the two untrusted ones to a ``PureOracle``::

    pre      = plan.prepare(program)                 # trusted (state snapshot)
    artifact = oracle.translate(...)                 # UNTRUSTED -> PureOracle
    src      = plan.run_source(...)                  # trusted   (I_s)
    binding  = plan.target_binding(...)              # trusted
    ttrace   = plan.run_target(...)                  # trusted   (I_t)
    carried  = oracle.lift(ttrace)                   # UNTRUSTED -> PureOracle
    verdict  = align(src, carried[window], π)        # trusted

``pair.square`` is never read. The step order is the pairs' own — translate
before the source run, because several source interpreters mutate the image's
memory in place and the artifact must carry the *initial* memory.

**No silent fallback.** A pair without a grader-side plan raises :class:`NoPlan`
rather than quietly deferring to ``pair.square`` — a fallback would make the
whole guarantee unobservable at the call site. :func:`planned_pairs` is the
honest list of what the grader can currently grade on its own authority.

**Stated limits (not fixed here).**

- The two directional ``over`` endo-pairs, ``btor2-havoc`` and
  ``btor2-interval``, have no plan: each one's square runs along the pair's own
  witness embedding (``havoc_plan``/``embed``/``projection_for``, and the
  interval pair's affine decode), so a grader-owned recipe would have to
  re-derive the abstraction plan. The lax "over" direction needs its own §3.1
  split; until then those pairs are graded the old way. This is one gap with
  two members, not two gaps — closing the split closes both.
- The plans are transcriptions, kept honest by ``tests/test_grader_square.py``
  asserting verdict-for-verdict agreement with each pair's own ``square()`` on
  every probe. Transcription is what §3.1 asks for (the recipe must live on the
  trusted side), but a pair that changes its square's binding without updating
  the plan turns that test red — which is the point.
- The child is still a bare ``subprocess`` (``pure_oracle``'s seam). OS-level
  isolation — filesystem/network/seccomp, §3.3 closer 2 — remains open.
- Two pairs cannot yet be graded *out of process* at all: see
  :data:`CHANNEL_TUPLE_GAP`.

**The channel-fidelity gap this work surfaced.** ``pure_oracle``'s safe result
channel returns ``Λ``'s output as JSON, and JSON has no tuple — a tuple-valued
observable arrives in the parent as a list. On the BTOR2 spine every projected
observable is an int or a string, so the widening is invisible; on
``wasm-btor2`` (``stack``) and ``smiles-formula`` (``atoms``) it is not, and the
trusted ``align`` correctly reports ``(7,) != [7]`` as a divergence. The square
therefore *flips verdict with the backend*, which no grader may do silently, so
:func:`grade` refuses those pairs out-of-process with :class:`ChannelGap` rather
than answering wrongly.

This is a defect in the seam, not in the plans, and it was invisible until now
because ``tests/test_pure_oracle.py``'s ``TestLiftEquivalence`` compares the two
backends through ``_canon`` = ``json.dumps(..., default=str)`` — which maps
tuples to lists on *both* sides and so normalizes away precisely the asymmetry
it exists to catch (``wasm-btor2`` is in that test's ``SPINE`` and passes). The
fix belongs to ``pure_oracle`` (a tuple-preserving wire format, or a declared
canonical trace type) and is left as its own unit of work.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from . import oracle as _oracle
from . import pure_oracle, registry
from .registry import Pair
from .types import AlignResult, Projection, Trace


class NoPlan(Exception):
    """No grader-owned recipe exists for this pair, so the grader cannot grade
    it without trusting the pair's own ``square()``. Typed so a caller decides
    explicitly rather than inheriting a silent fallback."""

    def __init__(self, pair_id: str) -> None:
        super().__init__(
            f"no grader-side square plan for {pair_id!r}; grading it would mean "
            "calling the pair's own square() (SCALING.md §3.1)"
        )
        self.pair_id = pair_id


#: Pairs whose ``Λ`` carries a **tuple-valued** projected observable, which the
#: ``pure_oracle`` JSON result channel widens to a list. Their square is exact
#: in-process and spuriously diverges out-of-process, so the grader refuses the
#: subprocess backend for them (see the module docstring). Shrinking this tuple
#: is the seam fix's acceptance test.
CHANNEL_TUPLE_GAP: tuple[str, ...] = ("smiles-formula", "wasm-btor2")


class ChannelGap(Exception):
    """The requested backend cannot carry this pair's trace faithfully, so the
    verdict would be an artefact of the channel. Refusing beats answering."""

    def __init__(self, pair_id: str, backend: str) -> None:
        super().__init__(
            f"{pair_id!r} has a tuple-valued observable that the {backend!r} "
            "result channel widens to a list; the square would diverge on the "
            "wire format, not on the semantics (SCALING.md §3.3)"
        )
        self.pair_id = pair_id
        self.backend = backend


# --- the recipe -------------------------------------------------------------

def _identity(program: Any) -> Any:
    return program


def _no_pre(program: Any) -> dict:
    return {}


def _pair_projection(pair: Pair, program: Any) -> Projection:
    return pair.projection


def _run_target_default(pair: Pair, artifact: bytes, binding: dict) -> Trace:
    return pair.target_interpreter(artifact, binding)


@dataclass(frozen=True)
class SquarePlan:
    """How the grader drives one pair's square using only trusted parts.

    Every callable here is framework-owned and may import ``gurdy/core`` and
    ``gurdy/languages`` — never ``gurdy/pairs``. ``T`` and ``Λ`` are absent by
    construction: they arrive through the ``PureOracle``.
    """

    pair_id: str
    #: Source behaviour ``I_s(program)`` under the pair's own binding.
    run_source: Callable[[Pair, Any, dict, int], Any]
    #: The binding ``I_t`` runs under, given the source trace and the artifact.
    target_binding: Callable[[Any, list, bytes, dict, int], dict] = \
        field(default=lambda program, src, artifact, pre, max_steps: {})
    #: Trusted state to snapshot *before* the source run mutates it.
    prepare: Callable[[Any], dict] = field(default=_no_pre)
    #: What ``T`` is actually called on (some pairs thread defaults into it).
    translator_input: Callable[[Any], Any] = field(default=_identity)
    #: How ``I_t`` is invoked (the BTOR2 spine's default, or a language arm).
    run_target: Callable[[Pair, bytes, dict], Trace] = field(default=_run_target_default)
    #: ``k`` => compare ``carried[k : k+n]``; ``None`` => compare ``carried``
    #: whole, so a length mismatch is still a divergence.
    shift: int | None = 1
    #: ``π`` — the pair's protected projection, or one rebuilt per program.
    projection: Callable[[Pair, Any], Projection] = field(default=_pair_projection)


# --- the driver -------------------------------------------------------------

def grade(pair_id: str, program: Any, *, backend: str = "inproc",
          max_steps: int = 10_000,
          oracle: pure_oracle.PureOracle | None = None) -> AlignResult:
    """Run ``pair_id``'s commuting square on ``program`` under the grader's own
    authority: trusted steps in-process, ``T``/``Λ`` through a ``PureOracle``.

    ``oracle`` injects a specific backend (a mutated one, for negative
    controls); otherwise one is built for ``backend`` and closed afterwards. An
    injected oracle bypasses the :class:`ChannelGap` guard — the caller owns the
    channel it supplied.

    Raises :class:`NoPlan` if the grader has no recipe, :class:`ChannelGap` if
    the backend cannot carry this pair's trace. ``Unsupported`` from a trusted
    interpreter propagates, exactly as it does through ``pair.square``.
    """
    plan = plan_for(pair_id)
    pair = registry.get_pair(pair_id)
    if oracle is None and backend != "inproc" and pair_id in CHANNEL_TUPLE_GAP:
        raise ChannelGap(pair_id, backend)
    po = oracle if oracle is not None else pure_oracle.for_pair(pair, backend)
    owned = oracle is None
    try:
        pre = plan.prepare(program)                                   # trusted
        artifact = po.translate(plan.translator_input(program))       # UNTRUSTED
        src = list(plan.run_source(pair, program, pre, max_steps))    # trusted
        binding = plan.target_binding(program, src, artifact, pre, max_steps)
        ttrace = plan.run_target(pair, artifact, binding)             # trusted
        carried = list(po.lift(ttrace))                               # UNTRUSTED
    finally:
        if owned:
            po.close()
    n = len(src)
    right = carried if plan.shift is None else carried[plan.shift: plan.shift + n]
    return _oracle.align(src, right, plan.projection(pair, program))  # trusted


def faithful_for(pair_id: str, *, backend: str = "inproc",
                 max_steps: int = 10_000) -> Callable[[Any], AlignResult]:
    """A ``program -> AlignResult`` callable for ``coverage.measure(faithful=)``
    that grades on the grader's authority instead of the pair's ``square()``.
    Raises :class:`NoPlan` now, not per probe, if there is no recipe."""
    plan_for(pair_id)
    return lambda program: grade(pair_id, program, backend=backend,
                                 max_steps=max_steps)


def plan_for(pair_id: str) -> SquarePlan:
    plan = PLANS.get(pair_id)
    if plan is None:
        raise NoPlan(pair_id)
    return plan


def has_plan(pair_id: str) -> bool:
    return pair_id in PLANS


def planned_pairs() -> tuple[str, ...]:
    """The pairs the grader can grade without trusting their own square."""
    return tuple(sorted(PLANS))


# --- per-pair recipes (trusted tree only; never imports gurdy.pairs) --------

def _btor2_steps(program: Any, src: list, artifact: bytes, pre: dict,
                 max_steps: int) -> dict:
    """The BTOR2 spine's default binding: a run's first row is the initial
    state, so ``n`` source steps need ``n + 1`` cycles."""
    return {"steps": len(src) + 1}


def _btor2_steps_mem(program: Any, src: list, artifact: bytes, pre: dict,
                     max_steps: int) -> dict:
    binding = {"steps": len(src) + 1}
    if pre.get("mem") is not None:
        binding["state"] = {"mem": pre["mem"]}
    return binding


# riscv-btor2 ----------------------------------------------------------------

def _riscv_pre(program: Any) -> dict:
    # Snapshot before the source run's stores mutate the shared image.
    return {"mem": dict(program["image"].mem)}


def _riscv_source(pair: Pair, program: Any, pre: dict, max_steps: int) -> Any:
    return pair.source_interpreter(program["image"],
                                   {"regs": program.get("init_regs", {})},
                                   max_steps=max_steps)


# sail-btor2 -----------------------------------------------------------------

def _sail_btor2_source(pair: Pair, program: Any, pre: dict, max_steps: int) -> Any:
    if program.get("isa") == "aarch64":
        return pair.source_interpreter(program, {}, max_steps=max_steps)
    return pair.source_interpreter(program, {"regs": program.get("init_regs", {})},
                                   max_steps=max_steps)


def _sail_btor2_pre(program: Any) -> dict:
    if program.get("isa") == "aarch64":
        mem = {int(a): int(v) & 0xFF for a, v in program.get("init_mem", {}).items()}
    else:
        mem = {int(k): int(v) for k, v in program.get("mem", {}).items()}
    return {"mem": mem or None}


def _sail_btor2_projection(pair: Pair, program: Any) -> Projection:
    """The A64 arm's ``π``, rebuilt from the *language*'s constants — π is
    trusted/brief-owned (§3.1), so the grader constructs it rather than reading
    it off the pair."""
    if program.get("isa") != "aarch64":
        return pair.projection
    from ..languages.aarch64.interp import MEM_WINDOW, NREG
    regs = tuple(f"x{r}" for r in range(NREG))
    mems = tuple(f"m{i}" for i in range(MEM_WINDOW))
    return Projection(("pc", *regs, "sp", "nzcv", *mems, "halted"))


# aarch64-btor2 / aarch64-sail -----------------------------------------------

def _a64_defaults(program: Any) -> dict:
    from ..languages.aarch64.interp import SP_DEFAULT
    return {
        "regs": program.get("init_regs", {}),
        "sp": int(program.get("init_sp", SP_DEFAULT)),
        "nzcv": int(program.get("init_nzcv", 0)),
        "mem": program.get("init_mem", {}),
    }


def _a64_source(pair: Pair, program: Any, pre: dict, max_steps: int) -> Any:
    d = _a64_defaults(program)
    return pair.source_interpreter(program["image"], d, max_steps=max_steps)


def _a64_btor2_translator_input(program: Any) -> Any:
    return {**program, "init_sp": _a64_defaults(program)["sp"]}


def _a64_sail_translator_input(program: Any) -> Any:
    d = _a64_defaults(program)
    return {**program, "init_sp": d["sp"], "init_nzcv": d["nzcv"],
            "init_mem": d["mem"]}


def _a64_btor2_pre(program: Any) -> dict:
    init_mem = program.get("init_mem", {})
    return {"mem": {int(a): int(v) & 0xFF for a, v in init_mem.items()} or None}


# evm-btor2 ------------------------------------------------------------------

def _evm_source(pair: Pair, program: Any, pre: dict, max_steps: int) -> Any:
    from ..languages.evm import program_from_bytes
    prog = program_from_bytes(program["code"], int(program.get("entry", 0)))
    binding = {
        "pc": int(program.get("entry", 0)),
        "sp": int(program.get("init_sp", 0)),
        "stack": program.get("init_stack", {}),
    }
    return pair.source_interpreter(prog, binding, max_steps=max_steps)


# wasm-btor2 -----------------------------------------------------------------

def _wasm_source(pair: Pair, program: Any, pre: dict, max_steps: int) -> Any:
    return pair.source_interpreter(program["mod"],
                                   {"locals": program.get("init_locals", {})},
                                   max_steps=max_steps)


# ebpf-btor2 -----------------------------------------------------------------

def _ebpf_pre(program: Any) -> dict:
    prog = program["prog"]
    return {
        "mem": dict(prog.mem),
        "pkt": {int(k): int(v) & 0xFF for k, v in getattr(prog, "pkt", {}).items()},
        "helper_inputs": [dict(d) for d in program.get("helper_inputs", [])],
    }


def _ebpf_source(pair: Pair, program: Any, pre: dict, max_steps: int) -> Any:
    return pair.source_interpreter(
        program["prog"],
        {"regs": program.get("init_regs", {}), "helper_inputs": pre["helper_inputs"]},
        max_steps=max_steps)


def _ebpf_is_call(insn: int) -> bool:
    from ..languages.ebpf.interp import _decode
    code, _dst, _src, _off, _imm = _decode(insn)
    return (code & 0x07) == 0x05 and ((code >> 4) & 0x0F) == 0x8   # JMP class, CALL


def _ebpf_binding(program: Any, src: list, artifact: bytes, pre: dict,
                  max_steps: int) -> dict:
    """Feed the BTOR2 model the *same* helper returns the interpreter consumed:
    the ``k``-th dynamic ``CALL`` (at cycle ``c``) reads ``call{pc}_r{reg}`` at
    cycle ``c``. Built from the artifact's own input symbols — the grader reads
    the emitted model, it does not ask the pair what the binding should be."""
    from ..languages.btor2.model import from_text
    from ..languages.ebpf.interp import CALL_CLOBBERED

    sys = from_text(artifact.decode("utf-8"))
    by_symbol = {n.symbol: n.id for n in sys.nodes.values() if n.op == "input"}
    insns = program["prog"].insns
    entry = program["prog"].entry
    stream = pre["helper_inputs"]
    inputs: dict[int, dict[int, int]] = {}
    k = 0
    for c in range(len(src)):
        pc = entry if c == 0 else src[c - 1].get("pc")
        if pc is None or not (0 <= pc < len(insns)) or not _ebpf_is_call(insns[pc]):
            continue
        effect = stream[k] if k < len(stream) else {}
        k += 1
        row = inputs.setdefault(c, {})
        for reg in CALL_CLOBBERED:
            nid = by_symbol.get(f"call{pc}_r{reg}")
            if nid is not None:
                row[nid] = int(effect.get(reg, 0)) & ((1 << 64) - 1)
    return {"steps": len(src) + 1,
            "state": {"mem": pre["mem"], "pkt": pre["pkt"]},
            "inputs": inputs}


# sail-target arms (riscv-sail, aarch64-sail) --------------------------------

def _sail_binding(program: Any, src: list, artifact: bytes, pre: dict,
                  max_steps: int) -> dict:
    return {"max_steps": max_steps}


def _sail_run_target(pair: Pair, artifact: bytes, binding: dict) -> Trace:
    """The Sail language serves both roles with one model-agnostic executor, so
    the registry wires it as ``source_interpreter`` only; call the shared ``run``
    directly on the JSON object the translator emits."""
    from ..languages.sail import run as sail_run
    return sail_run(json.loads(artifact.decode("utf-8")), {},
                    max_steps=binding["max_steps"])


def _riscv_sail_source(pair: Pair, program: Any, pre: dict, max_steps: int) -> Any:
    return pair.source_interpreter(program["image"],
                                   {"regs": program.get("init_regs", {})},
                                   max_steps=max_steps)


# smiles-formula -------------------------------------------------------------

def _smiles_source(pair: Pair, program: Any, pre: dict, max_steps: int) -> Any:
    return pair.source_interpreter(program)          # I_s takes the string


def _smiles_run_target(pair: Pair, artifact: bytes, binding: dict) -> Trace:
    return pair.target_interpreter(artifact.decode("utf-8"))


PLANS: dict[str, SquarePlan] = {
    "riscv-btor2": SquarePlan(
        pair_id="riscv-btor2",
        prepare=_riscv_pre,
        run_source=_riscv_source,
        target_binding=_btor2_steps_mem,
    ),
    "sail-btor2": SquarePlan(
        pair_id="sail-btor2",
        prepare=_sail_btor2_pre,
        run_source=_sail_btor2_source,
        target_binding=_btor2_steps_mem,
        projection=_sail_btor2_projection,
    ),
    "aarch64-btor2": SquarePlan(
        pair_id="aarch64-btor2",
        prepare=_a64_btor2_pre,
        translator_input=_a64_btor2_translator_input,
        run_source=_a64_source,
        target_binding=_btor2_steps_mem,
    ),
    "evm-btor2": SquarePlan(
        pair_id="evm-btor2",
        run_source=_evm_source,
        target_binding=_btor2_steps,
    ),
    "wasm-btor2": SquarePlan(
        pair_id="wasm-btor2",
        run_source=_wasm_source,
        target_binding=_btor2_steps,
    ),
    "ebpf-btor2": SquarePlan(
        pair_id="ebpf-btor2",
        prepare=_ebpf_pre,
        run_source=_ebpf_source,
        target_binding=_ebpf_binding,
    ),
    "riscv-sail": SquarePlan(
        pair_id="riscv-sail",
        run_source=_riscv_sail_source,
        target_binding=_sail_binding,
        run_target=_sail_run_target,
        shift=None,
    ),
    "aarch64-sail": SquarePlan(
        pair_id="aarch64-sail",
        translator_input=_a64_sail_translator_input,
        run_source=_a64_source,
        target_binding=_sail_binding,
        run_target=_sail_run_target,
        shift=None,
    ),
    "smiles-formula": SquarePlan(
        pair_id="smiles-formula",
        run_source=_smiles_source,
        run_target=_smiles_run_target,
        shift=None,
    ),
}
