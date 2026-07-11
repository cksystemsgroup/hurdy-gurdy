"""The two-sided negative-control harness — Phase 3 of the automated-scaling
rollout (SCALING.md §12.3, §3.2).

Before a green square is trusted on a PR, prove the square *can fail* on this
pair's probes — the I19 lesson generalized. The control grades the pair twice:

- a **seeded defect** must be caught (``mutant_pass < intact_pass``): if it
  survives, either the square is no-op'd or the probes are too weak (the
  I23/I24 class) — either way the pair is not gate-worthy;
- the **intact** pair must pass on every accepted probe (``intact_pass ==
  accepted``): proof the square is not merely always-fail.

Grading injects the (grader-authored) mutant by rebinding the pair module's
``translate`` for the duration and restoring it — a pair's ``square()`` looks up
``translate`` as a module global, so the mutant flows into the exact grading
path. This runs in-process because the mutant mutates the pair's own already
merged, trusted output; isolating *untrusted contributed* code is the
``PureOracle`` seam's job (SCALING.md §3.1). A caller may pass a stronger,
semantic mutant (e.g. one of ``tools/fault_injection.py``'s op-swaps) to test
probe *adequacy* rather than mere grader liveness.

Only ``checked``-grade pairs carry a decidable square; ``predicted``-grade hops
discharge faithfulness per run and have no build-time square to control.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable

from .errors import Unsupported
from .registry import Pair


def _pair_module(pair: Pair) -> Any:
    return importlib.import_module(f"gurdy.pairs.{pair.id.replace('-', '_')}")


def _accepts(translate: Callable[[Any], Any], program: Any) -> bool:
    try:
        translate(program)
        return True
    except Unsupported:
        return False


def truncate_mutant(pair: Pair) -> Callable[[Any], bytes]:
    """A gross-defect mutant guaranteed to break a checked pair's square:
    keep only the first half of the emitted artifact. Tests grader *liveness*
    (the square is running), not probe adequacy."""
    real = _pair_module(pair).translate

    def mutant(program: Any) -> bytes:
        art = bytes(real(program))
        return art[: max(1, len(art) // 2)]

    return mutant


def grade(pair: Pair, translate_override: Callable[[Any], Any] | None = None) -> int:
    """Count accepted probes whose square passes, optionally with the pair's
    ``translate`` rebound to ``translate_override`` (restored afterward). Scope
    (which probes are 'accepted') is fixed by the *real* translator, so a
    mutation cannot silently shrink it."""
    mod = _pair_module(pair)
    real = mod.translate
    if translate_override is not None:
        mod.translate = translate_override
    passed = 0
    try:
        for program in pair.probes.values():
            if not _accepts(real, program):
                continue
            try:
                result = pair.square(program)
            except Exception:                 # a crash in the square = caught
                continue
            if getattr(result, "ok", False):
                passed += 1
    finally:
        mod.translate = real
    return passed


@dataclass
class ControlResult:
    pair: str
    accepted: int
    intact_pass: int
    mutant_pass: int
    caught: bool                              # the seeded defect was caught
    intact_ok: bool                           # every accepted probe passes intact
    ok: bool                                  # the two-sided control holds


def two_sided_control(pair: Pair,
                      mutant: Callable[[Any], Any] | None = None) -> ControlResult | None:
    """Run the two-sided control on a checked-grade pair. Returns ``None`` for a
    pair with no decidable square (nothing to control at build time)."""
    if pair.square is None or not pair.probes:
        return None
    real = _pair_module(pair).translate
    accepted = sum(1 for p in pair.probes.values() if _accepts(real, p))
    intact = grade(pair)
    mut = mutant if mutant is not None else truncate_mutant(pair)
    mutant_pass = grade(pair, translate_override=mut)
    caught = mutant_pass < intact
    intact_ok = intact == accepted
    return ControlResult(pair.id, accepted, intact, mutant_pass,
                         caught, intact_ok, caught and intact_ok)
