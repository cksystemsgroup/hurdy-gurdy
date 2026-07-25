#!/usr/bin/env python3
"""The ``avr`` take-up player — the exploration iteration: every
family member available before any saturation judgment.

Iterations 3–4 played three members of the demanded family
("BMC / k-induction / IC3-class model checking", board entry
``d4c59dafc402``): pono's ``ind``, ``ic3bits``, ``mbic3`` — spent at
the amended 600 s wall on every blocked pin. This player composes the
members the platform holds that those iterations never played
(SOLVERS.md §3, the player's enumeration duty):

* **AVR** (the registered ``avr`` brief, ``gurdy/solvers/avr_btor2``)
  — IC3-style equality abstraction on the disjoint ``(avr, yices)``
  lineage, played **first**: any agreement with a pono-proved
  ``bounded: false`` claim is the platform's first cross-lineage
  corroboration of an unbounded answer.
* pono's ``EXPLORATION_MODES`` (interpolation ``dar``/``interp``/
  ``ismc``, abstraction-refinement ``ic3ia``/``ic3sa``, synthesis
  ``sygus-pdr``), each under the declared ``UNBOUNDED_WALL_S``.

Routing is unchanged from the pono take-up: a pin with a standing cost
demand goes procedure-first, everything else exact btormc first;
probes play bounded pono BMC so the curve stays one engine, one
meaning. Verdict currency is unchanged too — ``unreachable`` from an
unbounded member books ``bounded: false``, ``reachable`` only after
the witness replays through the shared interpreter — with one
deliberate refinement over ``pono_player``: a ``sat`` **without** a
replayable witness no longer ends the portfolio (AVR's abstraction
can emit degenerate witnesses); it is recorded and the exploration
continues. If a later member then proves ``unreachable``, the members
disagree on the unbounded question and the player books ``unknown``
with the disagreement cited — never silently taking a side. A fully
spent portfolio re-books the cost demand citing the dials the books
already hold (``spent_pairs`` → ``why_not``'s ``spent_reductions``).
"""

from __future__ import annotations

import hashlib
import subprocess
import os
import sys
from typing import Any, Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from gurdy.core.benchmark import Benchmark  # noqa: E402
from gurdy.core.solver import Verdict  # noqa: E402
from gurdy.solvers.avr_btor2 import (AVR_MEMOUT_MB,  # noqa: E402
                                     AVR_WALL_S)
from gurdy.solvers.pono_btor2 import (EXPLORATION_MODES,  # noqa: E402
                                      UNBOUNDED_FRAMES,
                                      UNBOUNDED_MODES,
                                      UNBOUNDED_WALL_S)

from havoc_player import _capped_native, blocked_hashes  # noqa: E402
from pono_player import (PonoFn, _capped_pono,  # noqa: E402
                         _replay_confirms,
                         spent_reductions_from_books)

#: The caps this player adds to the iteration record's provenance.
#: ``already_spent_modes`` names the members it deliberately does not
#: re-play: their 600 s walls are on the books from iteration 4.
AVR_CAPS = {"portfolio": ["avr"] + list(EXPLORATION_MODES),
            "avr_wall_s": AVR_WALL_S,
            "avr_memout_mb": AVR_MEMOUT_MB,
            "pono_wall_s": UNBOUNDED_WALL_S,
            "pono_frames": UNBOUNDED_FRAMES,
            "already_spent_modes": list(UNBOUNDED_MODES),
            "probe": "bounded BMC at the probe bound"}

#: ``(text) -> (verdict, witness_text | None)`` — the AVR seam the
#: tests inject; the wired leg is the brief's adapter, wall-capped.
AvrFn = Callable[[str], tuple[Verdict, Any]]


def _capped_avr() -> AvrFn:
    from gurdy.solvers.avr_btor2 import AvrBtor2Checker

    checker = AvrBtor2Checker()

    def avr(text: str) -> tuple[Verdict, str | None]:
        # AVR self-reports its spent budgets (f_to/f_mo → resource-out
        # in the adapter); the wall-grace kill maps the same way.
        try:
            return checker.decide(text)
        except subprocess.TimeoutExpired:
            return Verdict.RESOURCE_OUT, None

    return avr


def make_decide(bench: Benchmark, books_path: str, *, k: int,
                native: Callable[[str, int], tuple[Verdict, Any]] | None = None,
                pono: PonoFn | None = None,
                avr: AvrFn | None = None) -> Callable[
                    [str, int], tuple[Verdict, dict[str, Any]]]:
    """The player: exact btormc first with the exploration portfolio
    as fallback; portfolio-first for the books' standing cost demands;
    probes play bounded BMC — one engine per curve."""
    native = native or _capped_native()
    pono = pono or _capped_pono()
    avr = avr or _capped_avr()
    blocked = blocked_hashes(bench, books_path)
    spent_by_pin = spent_reductions_from_books(bench, books_path)

    def _legs(text: str):
        yield "avr", "avr", avr(text)
        for mode in EXPLORATION_MODES:
            yield "pono", mode, pono(text, mode, UNBOUNDED_FRAMES)

    def _procedure(text: str, kk: int,
                   spent: tuple[str, ...]) -> tuple[Verdict, dict[str, Any]]:
        spent_meta = {"spent_pairs": list(spent)} if spent else {}
        if kk < k:  # a probe: bounded BMC, no unbounded run (AVR_CAPS)
            v, wit = pono(text, "bmc", kk)
            if v is Verdict.REACHABLE and not _replay_confirms(text, wit):
                return Verdict.UNKNOWN, {"engine": "pono", "mode": "bmc",
                                         "probe": True, "unconfirmed": 1}
            meta = {"engine": "pono", "mode": "bmc", "probe": True}
            if v is Verdict.REACHABLE:
                meta["replay_confirms"] = True
            return v, meta
        unconfirmed: list[str] = []
        for engine, mode, (v, wit) in _legs(text):
            if v is Verdict.UNREACHABLE:
                if unconfirmed:
                    # an earlier member claimed sat it could not
                    # evidence — the members disagree on the unbounded
                    # question, and neither side carries checkable
                    # evidence: the question stays open, the
                    # disagreement goes on the books.
                    return Verdict.UNKNOWN, {
                        "engine": "avr+pono", "mode": mode, **spent_meta,
                        "note": "unbounded disagreement: "
                                f"{'+'.join(unconfirmed)} sat without a "
                                f"replayable witness vs {mode} unsat"}
                return v, {"engine": engine, "mode": mode,
                           "bounded": False,
                           "claim": "unreachable-unbounded"}
            if v is Verdict.REACHABLE:
                if _replay_confirms(text, wit):
                    return v, {"engine": engine, "mode": mode,
                               "replay_confirms": True}
                unconfirmed.append(mode)     # keep exploring
        meta: dict[str, Any] = {
            "engine": "avr+pono",
            "mode": "+".join(["avr", *EXPLORATION_MODES]),
            **spent_meta,
            "capped": f"wall {AVR_WALL_S}s avr + {UNBOUNDED_WALL_S}s "
                      "per pono mode"}
        if unconfirmed:
            meta["note"] = ("sat without a replayable witness: "
                            + "+".join(unconfirmed))
        return Verdict.RESOURCE_OUT, meta

    def decide(text: str, kk: int) -> tuple[Verdict, dict[str, Any]]:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if h not in blocked:
            v, _wit = native(text, kk)
            if v in (Verdict.REACHABLE, Verdict.UNREACHABLE):
                return v, {"engine": "btormc"}
        return _procedure(text, kk, spent_by_pin.get(h, ()))

    return decide
