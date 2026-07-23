#!/usr/bin/env python3
"""The ``pono`` take-up player — the promoted native-procedure, played.

Board entry ``d4c59dafc402`` (kind ``native-procedure``, in-set)
advanced the ``hwmcc-sosylab-beem`` campaign's standing cost demand
past the played-and-spent ``btor2-havoc`` dial to the charted family
"BMC / k-induction / IC3-class model checking" (``core/atlas.py``).
This module is the take-up: a ``decide`` function for
``tools/frontier_loop.py``'s player seam (``--engine pono``) that plays
the registered ``pono`` solver brief (``gurdy/solvers/brief.py``,
SOLVERS.md §2.1) — the **unbounded** leg the demand asks for.

Routing is the books' recommendation, mechanically applied, exactly as
the havoc take-up before it: a question whose pin carries a standing
**cost** demand goes unbounded-first (the exact bounded engine's wall
is the measurement the books already hold, twice over); every other
question plays exact btormc first and falls to the procedure only on a
spent verdict. The portfolio is player-composed (SOLVERS.md §3):
``ic3bits`` then ``ind``, each under the shared declared wall.
``unreachable`` from an unbounded mode books ``bounded: false`` — the
claim that closes the question at every depth. ``reachable`` is
believed only after pono's dumped BTOR2 witness replays through the
shared interpreter (``languages/btor2.check_witness``, SOLVERS.md §4);
an unreplayable ``sat`` stays ``unknown``. A spent verdict re-books the
cost demand citing the dials the books already hold as
played-and-spent (``spent_pairs`` in the meta → ``why_not``'s
``spent_reductions``), so the board's memory survives the engine
change instead of regressing to the spent reduction.
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

from gurdy.core import ledger  # noqa: E402
from gurdy.core.benchmark import Benchmark  # noqa: E402
from gurdy.core.solver import Verdict  # noqa: E402
from gurdy.languages.btor2.witness import check_witness  # noqa: E402
from gurdy.solvers.native_btor2 import DECIDE_TIMEOUT_S  # noqa: E402
from gurdy.solvers.pono_btor2 import (UNBOUNDED_FRAMES,  # noqa: E402
                                      UNBOUNDED_MODES)

from havoc_player import _capped_native, blocked_hashes  # noqa: E402

#: The caps this player adds to the iteration record's provenance.
PONO_CAPS = {"pono_portfolio": list(UNBOUNDED_MODES),
             "pono_frames": UNBOUNDED_FRAMES,
             "pono_wall_s": DECIDE_TIMEOUT_S,
             "probe": "bounded BMC at the probe bound"}

#: ``(text, mode, k) -> (verdict, witness_text | None)`` — the seam the
#: tests inject; the wired leg is the brief's adapter, wall-capped.
PonoFn = Callable[[str, str, int], tuple[Verdict, str | None]]


def spent_reductions_from_books(bench: Benchmark,
                                books_path: str) -> dict[str, tuple[str, ...]]:
    """Per pin: the reductions the pin's **latest** standing cost
    demand already cites as played-and-spent — the board's memory,
    read back so this player's own spent verdicts re-book it."""
    latest: dict[str, tuple[str, ...]] = {}
    for r in ledger._records(books_path):
        if (r.get("kind") == "demand" and r.get("suite") == bench.suite
                and r.get("obstacle") == "cost"):
            prog = (r.get("question") or {}).get("program")
            if prog:
                latest[prog] = tuple(
                    (r.get("target") or {}).get("spent_reductions") or ())
    return {i.sha256: latest.get(i.name, ()) for i in bench.instances}


def _capped_pono() -> PonoFn:
    from gurdy.solvers.pono_btor2 import PonoBtor2Checker

    checker = PonoBtor2Checker()

    def pono(text: str, mode: str, k: int) -> tuple[Verdict, str | None]:
        # The wall cap is a declared budget (native_btor2.py, shared):
        # exceeding it is a spent verdict, never a dead iteration.
        try:
            return checker.decide(text, mode=mode, k=k)
        except subprocess.TimeoutExpired:
            return Verdict.RESOURCE_OUT, None

    return pono


def _replay_confirms(text: str, wit: str | None) -> bool:
    if not wit:
        return False
    try:
        return check_witness(text, wit)
    except Exception:
        return False


def make_decide(bench: Benchmark, books_path: str, *, k: int,
                native: Callable[[str, int], tuple[Verdict, Any]] | None = None,
                pono: PonoFn | None = None) -> Callable[
                    [str, int], tuple[Verdict, dict[str, Any]]]:
    """The player: exact btormc first with the procedure as fallback;
    unbounded-first for the books' standing cost demands; probes (a
    call below the iteration's ``k``) play bounded BMC so the curve
    measures this engine's bounded leg, one engine per curve."""
    native = native or _capped_native()
    pono = pono or _capped_pono()
    blocked = blocked_hashes(bench, books_path)
    spent_by_pin = spent_reductions_from_books(bench, books_path)

    def _procedure(text: str, kk: int,
                   spent: tuple[str, ...]) -> tuple[Verdict, dict[str, Any]]:
        base: dict[str, Any] = {"engine": "pono"}
        spent_meta = {"spent_pairs": list(spent)} if spent else {}
        if kk < k:  # a probe: bounded BMC, no unbounded run (PONO_CAPS)
            v, wit = pono(text, "bmc", kk)
            if v is Verdict.REACHABLE and not _replay_confirms(text, wit):
                return Verdict.UNKNOWN, {**base, "mode": "bmc",
                                         "probe": True, "unconfirmed": 1}
            meta = {**base, "mode": "bmc", "probe": True}
            if v is Verdict.REACHABLE:
                meta["replay_confirms"] = True
            return v, meta
        for mode in UNBOUNDED_MODES:
            v, wit = pono(text, mode, UNBOUNDED_FRAMES)
            if v is Verdict.UNREACHABLE:
                return v, {**base, "mode": mode, "bounded": False,
                           "claim": "unreachable-unbounded"}
            if v is Verdict.REACHABLE:
                if _replay_confirms(text, wit):
                    return v, {**base, "mode": mode,
                               "replay_confirms": True}
                return Verdict.UNKNOWN, {
                    **base, "mode": mode, **spent_meta,
                    "note": "sat without a replayable witness"}
        return Verdict.RESOURCE_OUT, {
            **base, "mode": "+".join(UNBOUNDED_MODES), **spent_meta,
            "capped": f"wall {DECIDE_TIMEOUT_S}s per mode"}

    def decide(text: str, kk: int) -> tuple[Verdict, dict[str, Any]]:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if h not in blocked:
            v, _wit = native(text, kk)
            if v in (Verdict.REACHABLE, Verdict.UNREACHABLE):
                return v, {"engine": "btormc"}
        return _procedure(text, kk, spent_by_pin.get(h, ()))

    return decide
