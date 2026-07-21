#!/usr/bin/env python3
"""The ``btor2-havoc`` take-up player — the promoted reduction, played.

Board entry ``9c26710bf77f`` (kind ``reduction``, in-set) promoted the
standing cost demand of the ``hwmcc-sosylab-beem`` campaign onto the
registered pair ``pairs/btor2-havoc``. This module is the take-up: a
``decide`` function for ``tools/frontier_loop.py``'s player seam
(``--engine havoc``) that plays the abstraction route
``btor2 → btor2-havoc → (btormc)`` exactly as the pair's brief
prescribes — advisor-named free havoc set plus the farthest half of the
refinement ladder (``gurdy suggest-reduction``), CEGAR on spurious
counterexamples, ``unreachable`` transferring on the ``over`` direction
alone, ``reachable`` believed only after source replay
(``tools/abstraction_bench.py``'s audited loop, reused verbatim).

Routing is the books' recommendation, mechanically applied: a question
whose pin carries a **standing cost demand** in the workdir's books goes
abstraction-first (re-spending the exact engine's declared wall on it is
the one measurement the books already hold); every other question plays
the exact native engine first and falls back to the abstraction only on
a spent verdict. All budgets are declared, cited in provenance, and a
spent budget is a verdict on the books — never a crash.
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
from gurdy.languages.btor2.coi import suggest_reduction  # noqa: E402
from gurdy.solvers.native_btor2 import DECIDE_TIMEOUT_S  # noqa: E402

from abstraction_bench import (_havoc, _source_replay_hits_bad,  # noqa: E402
                               run_cegar)

#: Declared refinement budget: CEGAR rounds per question (a spent
#: round limit is ``resource-out`` on the books, cited as this cap).
CEGAR_MAX_ROUNDS = 4

#: The caps this player adds to the iteration record's provenance.
HAVOC_CAPS = {"cegar_max_rounds": CEGAR_MAX_ROUNDS,
              "probe": "single abstraction round"}

NativeFn = Callable[[str, int], tuple[Verdict, Any]]


def blocked_hashes(bench: Benchmark, books_path: str) -> set[str]:
    """The pins whose questions carry a standing **cost** demand in the
    books — the exact set the promoted board entry cites."""
    names = {
        (r.get("question") or {}).get("program")
        for r in ledger._records(books_path)
        if r.get("kind") == "demand" and r.get("suite") == bench.suite
        and r.get("obstacle") == "cost"}
    return {i.sha256 for i in bench.instances if i.name in names}


def _capped_native() -> NativeFn:
    from gurdy.solvers.native_btor2 import NativeBtor2Checker

    checker = NativeBtor2Checker()

    def native(text: str, k: int) -> tuple[Verdict, Any]:
        # The wall cap is a declared budget (native_btor2.py): exceeding
        # it is a spent verdict, never a dead iteration.
        try:
            v, wit = checker.decide_witness(text, k)
            if v is not Verdict.REACHABLE:
                v = checker.decide_bounded(text, k)
            return v, wit
        except subprocess.TimeoutExpired:
            return Verdict.RESOURCE_OUT, None

    return native


def make_decide(bench: Benchmark, books_path: str, *, k: int,
                native: NativeFn | None = None) -> Callable[
                    [str, int], tuple[Verdict, dict[str, Any]]]:
    """The player: exact-first with abstraction fallback; abstraction-
    first for the books' standing cost demands; probes (a call below the
    iteration's ``k``) play a single abstraction round so the curve
    measures the route's first leg, not the refinement loop."""
    native = native or _capped_native()
    blocked = blocked_hashes(bench, books_path)

    def _abstraction(text: str, kk: int) -> tuple[Verdict, dict[str, Any]]:
        adv = suggest_reduction(text, k=2, samples=0)
        free = list(adv["free_havoc"])
        ladder = list(adv["refinement_ladder"])
        prefix = ladder[:max(1, len(ladder) // 2)] if ladder else []
        base: dict[str, Any] = {"engine": "btormc", "pair": "btor2-havoc",
                                "free": len(free), "prefix": len(prefix)}
        if kk < k:  # a probe: one round, no refinement (HAVOC_CAPS)
            v, wit = native(_havoc(text, tuple(free + prefix)), kk)
            if (v is Verdict.REACHABLE
                    and not _source_replay_hits_bad(text, wit, kk)):
                return Verdict.UNKNOWN, {**base, "probe": True, "spurious": 1}
            return v, {**base, "probe": True}
        cegar = run_cegar(
            text, kk, free, prefix, native,
            lambda wit: not _source_replay_hits_bad(text, wit, kk),
            max_rounds=CEGAR_MAX_ROUNDS)
        meta = {**base, "rounds": cegar["rounds"],
                "spurious": cegar["spurious"],
                "havocked": len(cegar["final_havoc"])}
        verdict = cegar["verdict"]
        if verdict == "unreachable":
            return Verdict.UNREACHABLE, {**meta, "transfers": "over"}
        if verdict == "reachable":
            return Verdict.REACHABLE, {**meta, "replay_confirms": True}
        if verdict == "round-limit":
            return Verdict.RESOURCE_OUT, {
                **meta, "capped": f"cegar rounds {CEGAR_MAX_ROUNDS}"}
        if "resource" in verdict.lower().replace("_", "-"):
            return Verdict.RESOURCE_OUT, {
                **meta, "capped": f"wall {DECIDE_TIMEOUT_S}s"}
        return Verdict.UNKNOWN, {**meta, "note": verdict}

    def decide(text: str, kk: int) -> tuple[Verdict, dict[str, Any]]:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if h not in blocked:
            v, _wit = native(text, kk)
            if v in (Verdict.REACHABLE, Verdict.UNREACHABLE):
                return v, {"engine": "btormc"}
        return _abstraction(text, kk)

    return decide
