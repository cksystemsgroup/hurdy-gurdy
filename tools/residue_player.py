#!/usr/bin/env python3
"""The residue take-up player — the two family members the host alone
could not hold, played (the last enumeration step before a saturation
judgment).

After iteration 5 the demanded family ("BMC / k-induction / IC3-class
model checking", board entry ``d4c59dafc402``) had every host-holdable
member played and spent. Two members remained, each behind a build the
host cannot carry natively:

* **pono-msat** (``gurdy/solvers/pono_msat_btor2``) — ``msat-ic3ia``,
  IC3 via implicit predicate abstraction on MathSAT interpolation (the
  sub-family's reference configuration), through the pinned amd64
  image ``pono-msat:c81aa36`` under emulation. Shares ``pono`` and
  ``smt-switch`` lineage with the host build: played for family
  coverage, not the trust axis.
* **abc** (``gurdy/solvers/abc_btor2``) — Berkeley ABC's ``pdr``, the
  bit-level IC3/PDR reference implementation, on the AIGER encoding
  produced by btor2tools' ``btor2aiger`` (which bit-blasts through
  Boolector — declared in the lineage, so ABC corroborates AVR but
  never btormc/pono).

Routing, currency, and the exploration refinement are unchanged from
``avr_player``: procedure-first for pins with standing cost demands,
exact btormc first elsewhere, probes on bounded pono BMC (one engine
per curve); unbounded ``unreachable`` books ``bounded: false``;
``reachable`` only after a replayable witness (ABC's cex is not yet
translated back to a BTOR2 witness, so its ``sat`` stays unconfirmed
— recorded, and the portfolio continues); a later ``unsat`` against a
recorded unconfirmed ``sat`` books the disagreement as ``unknown``; a
fully spent portfolio re-books the cost demand citing the dials the
books already hold (``spent_pairs``).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from typing import Any, Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from gurdy.core.benchmark import Benchmark  # noqa: E402
from gurdy.core.solver import Verdict  # noqa: E402
from gurdy.solvers.abc_btor2 import ABC_WALL_S  # noqa: E402
from gurdy.solvers.pono_btor2 import (EXPLORATION_MODES,  # noqa: E402
                                      UNBOUNDED_MODES,
                                      UNBOUNDED_WALL_S)
from gurdy.solvers.pono_msat_btor2 import PONO_MSAT_IMAGE  # noqa: E402

from havoc_player import _capped_native, blocked_hashes  # noqa: E402
from pono_player import (PonoFn, _capped_pono,  # noqa: E402
                         _replay_confirms,
                         spent_reductions_from_books)

#: The caps this player adds to the iteration record's provenance.
#: ``already_spent_modes`` names every member iterations 3–5 played;
#: their walls are on the books and are cited, not re-spent.
RESIDUE_CAPS = {"portfolio": ["msat-ic3ia", "abc-pdr"],
                "pono_msat_image": PONO_MSAT_IMAGE,
                "pono_msat_wall_s": UNBOUNDED_WALL_S,
                "abc_wall_s": ABC_WALL_S,
                "already_spent_modes": (list(UNBOUNDED_MODES)
                                        + list(EXPLORATION_MODES)
                                        + ["avr"]),
                "probe": "bounded BMC at the probe bound"}

#: ``(text) -> (verdict, witness_text | None)`` — injection seams.
ResidueFn = Callable[[str], tuple[Verdict, Any]]


def _capped_msat() -> ResidueFn:
    from gurdy.solvers.pono_msat_btor2 import PonoMsatBtor2Checker

    checker = PonoMsatBtor2Checker()

    def msat(text: str) -> tuple[Verdict, str | None]:
        try:
            return checker.decide(text)
        except subprocess.TimeoutExpired:
            return Verdict.RESOURCE_OUT, None

    return msat


def _capped_abc() -> ResidueFn:
    from gurdy.solvers.abc_btor2 import AbcBtor2Checker

    checker = AbcBtor2Checker()

    def abc(text: str) -> tuple[Verdict, str | None]:
        try:
            return checker.decide(text)
        except subprocess.TimeoutExpired:
            return Verdict.RESOURCE_OUT, None

    return abc


def make_decide(bench: Benchmark, books_path: str, *, k: int,
                native: Callable[[str, int], tuple[Verdict, Any]] | None = None,
                pono: PonoFn | None = None,
                msat: ResidueFn | None = None,
                abc: ResidueFn | None = None) -> Callable[
                    [str, int], tuple[Verdict, dict[str, Any]]]:
    """The player: exact btormc first with the residue portfolio as
    fallback; portfolio-first for the books' standing cost demands;
    probes play bounded BMC — one engine per curve."""
    native = native or _capped_native()
    pono = pono or _capped_pono()
    msat = msat or _capped_msat()
    abc = abc or _capped_abc()
    blocked = blocked_hashes(bench, books_path)
    spent_by_pin = spent_reductions_from_books(bench, books_path)

    def _legs(text: str):
        yield "pono-msat", "msat-ic3ia", msat(text)
        yield "abc", "pdr", abc(text)

    def _procedure(text: str, kk: int,
                   spent: tuple[str, ...]) -> tuple[Verdict, dict[str, Any]]:
        spent_meta = {"spent_pairs": list(spent)} if spent else {}
        if kk < k:  # a probe: bounded BMC (RESIDUE_CAPS)
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
                    return Verdict.UNKNOWN, {
                        "engine": "residue", "mode": mode, **spent_meta,
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
            "engine": "residue", "mode": "msat-ic3ia+abc-pdr",
            **spent_meta,
            "capped": f"wall {UNBOUNDED_WALL_S}s msat-ic3ia + "
                      f"{ABC_WALL_S}s abc-pdr"}
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
