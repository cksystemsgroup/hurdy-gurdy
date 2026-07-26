#!/usr/bin/env python3
"""The ``btor2-interval`` rung on the CEGAR ladder — the second dial,
played.

Registering the interval pair (the second directional endo-pair) made
``why_not``'s cost demands honest about the unspent dial: a blocked
question that spent only ``btor2-havoc`` now demands ``btor2-interval``
before its target advances. This module is the mechanism that spends
it: a ``decide`` function for ``tools/frontier_loop.py``'s player seam
(``--engine interval``) that walks the brief's rung ladder
(pairs/btor2-interval/README.md: full range ≡ havoc ⊒ subrange ⊒
exact) — start at havoc, and on a spurious counterexample tighten the
rung nearest the question one notch to its observed ``[min, max]`` seed
(``gurdy suggest-reduction``) before falling all the way to exact.

Unlike havoc, an interval confinement is **falsifiable**: the player
asserts the state stays in range, and the source may leave it. So a
confinement decides nothing until it is validated — escape monitors on
the source (``state < lo ∨ state > hi`` as the only ``bad``s), decided
by the same engine at the same bound. An escape refutes the seed and
that rung falls to exact; a spent validation demotes the confinement
(exact is always sound); only a validated interval's ``unreachable``
transfers. Routing, replay discipline, and budget currency are the
havoc player's, reused: ``reachable`` only after source replay, spent
rounds and walls are verdicts on the books, and ``spent_pairs`` reports
exactly the dials the route actually played.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from gurdy.core import route  # noqa: E402
from gurdy.core.benchmark import Benchmark  # noqa: E402
from gurdy.core.solver import Verdict  # noqa: E402
from gurdy.languages.btor2.coi import suggest_reduction  # noqa: E402
from gurdy.languages.btor2.model import Bitvec, from_text  # noqa: E402
from gurdy.languages.btor2.witness import parse_witness  # noqa: E402
from gurdy.pairs.btor2_interval import translate as interval_translate  # noqa: E402
from gurdy.pairs.btor2_interval.translate import (_max_id,  # noqa: E402
                                                 interval_plan)
from gurdy.solvers.native_btor2 import DECIDE_TIMEOUT_S  # noqa: E402

from abstraction_bench import (_havoc, _source_replay_hits_bad)  # noqa: E402
from havoc_player import _capped_native, blocked_hashes  # noqa: E402

#: Declared refinement budget: rounds per question (a validation call
#: and its decide share a round; a spent limit is ``resource-out`` on
#: the books, cited as this cap). Two notches per rung state — havoc →
#: interval → exact — need more headroom than havoc's single notch.
CEGAR_MAX_ROUNDS = 6

#: The caps this player adds to the iteration record's provenance.
INTERVAL_CAPS = {"cegar_max_rounds": CEGAR_MAX_ROUNDS,
                 "probe": "single abstraction round",
                 "rungs": "havoc,observed-interval,exact"}

NativeFn = Callable[[str, int], tuple[Verdict, Any]]


def usable_seeds(text: str, adv: dict[str, Any]) -> dict[str, tuple[int, int]]:
    """The advisor's observed ``[min, max]`` seeds that actually
    confine: a full-range seed is the havoc rung already and is
    dropped (the translator would emit havoc's exact rewrite)."""
    sysm = from_text(text)
    width = {n.symbol or f"n{n.id}": sysm.sorts[n.sort].width
             for n in sysm.states()
             if isinstance(sysm.sorts.get(n.sort), Bitvec)}
    out: dict[str, tuple[int, int]] = {}
    for lbl, bounds in adv.get("interval_seeds", {}).items():
        w = width.get(lbl)
        if w is None:
            continue
        lo, hi = int(bounds[0]), int(bounds[1])
        if (lo, hi) == (0, (1 << w) - 1):
            continue
        out[lbl] = (lo, hi)
    return out


def range_monitors(source_text: str,
                   intervals: dict[str, tuple[int, int]]) -> tuple[
                       str, list[str]]:
    """The validation system: the source with its own ``bad``s removed
    and one escape monitor (``s < lo ∨ s > hi``) per confined state as
    the only properties, in ascending state-id order — a ``reachable``
    verdict's witness header (``b<i>``) then names the refuted seed.
    Constraints are kept: the claim is range-invariance of the
    constraint-valid runs, exactly what the abstraction must cover."""
    _sysm, text, plan = interval_plan(
        {"system": source_text, "intervals": intervals})
    lines = [ln for ln in text.split("\n")
             if not (len(ln.split()) >= 2 and ln.split()[1] == "bad")]
    while lines and not lines[-1].strip():
        lines.pop()
    bit1 = None
    for ln in lines:
        toks = ln.split()
        if (len(toks) >= 4 and toks[1] == "sort" and toks[2] == "bitvec"
                and toks[3] == "1"):
            bit1 = int(toks[0])
            break
    nid = _max_id(text) + 1
    if bit1 is None:
        lines.append(f"{nid} sort bitvec 1")
        bit1, nid = nid, nid + 1
    monitored: list[str] = []
    for state, lo, hi, _ids in plan:
        c_lo, c_hi, lt, gt, orr, bad = range(nid, nid + 6)
        lines.append(f"{c_lo} constd {state.sort} {lo}")
        lines.append(f"{c_hi} constd {state.sort} {hi}")
        lines.append(f"{lt} ult {bit1} {state.id} {c_lo}")
        lines.append(f"{gt} ugt {bit1} {state.id} {c_hi}")
        lines.append(f"{orr} or {bit1} {lt} {gt}")
        lines.append(f"{bad} bad {orr}")
        nid += 6
        monitored.append(state.symbol or f"n{state.id}")
    return "\n".join(lines) + "\n", monitored


def _escaped(wit: Any, monitored: list[str]) -> list[str]:
    """The refuted seeds a validation witness names — all of them when
    the witness cannot localize (the conservative reading: a tested
    claim the engine falsified must not keep confining)."""
    try:
        bads = parse_witness(wit).bads
    except Exception:
        return list(monitored)
    hit = [monitored[i] for i in bads if 0 <= i < len(monitored)]
    return hit or list(monitored)


def _compose(source_text: str, havoc_pot: list[str],
             interval_pot: dict[str, tuple[int, int]]) -> str:
    out = _havoc(source_text, tuple(havoc_pot))
    if interval_pot:
        out = interval_translate(
            {"system": out, "intervals": dict(interval_pot)}).decode("utf-8")
    return out


def run_interval_cegar(source_text: str, k: int,
                       free: list[str], prefix: list[str],
                       seeds: dict[str, tuple[int, int]],
                       decide: NativeFn,
                       spurious: Callable[[Any], bool],
                       max_rounds: int | None = None) -> dict[str, Any]:
    """The rung walk: havoc ``free + prefix``, decide, and on a
    spurious counterexample tighten the ladder rung nearest the
    question one notch — havoc → its observed interval → exact. Every
    unvalidated confinement is checked before it may confine (escape
    monitors, same engine, same bound). Returns the loop's ledger."""
    havoc_pot = list(free) + list(prefix)
    interval_pot: dict[str, tuple[int, int]] = {}
    validated = True  # vacuously: the pot starts empty
    interval_played = False
    seed_refuted: list[str] = []
    demoted: list[str] = []
    rounds = 0
    spurious_count = 0
    limit = CEGAR_MAX_ROUNDS if max_rounds is None else max_rounds

    def ledger(verdict: str, **extra: Any) -> dict[str, Any]:
        return {"verdict": verdict, "rounds": rounds,
                "spurious": spurious_count, "final_havoc": havoc_pot,
                "final_intervals": dict(interval_pot),
                "seed_refuted": seed_refuted,
                "demoted_unvalidated": demoted,
                "interval_played": interval_played, **extra}

    while True:
        rounds += 1
        if interval_pot and not validated:
            interval_played = True
            mon, monitored = range_monitors(source_text, interval_pot)
            v, wit = decide(mon, k)
            if v is Verdict.REACHABLE:
                for lbl in _escaped(wit, monitored):
                    interval_pot.pop(lbl, None)
                    seed_refuted.append(lbl)
                if rounds >= limit:
                    return ledger("round-limit")
                continue  # the refuted rungs fell to exact; revalidate
            if v is Verdict.UNREACHABLE:
                validated = True
            else:  # a spent validation: the confinement must not confine
                demoted += sorted(interval_pot)
                interval_pot.clear()
                validated = True
        verdict, evidence = decide(
            _compose(source_text, havoc_pot, interval_pot), k)
        if verdict is Verdict.REACHABLE:
            if spurious(evidence):
                spurious_count += 1
                for p in reversed(prefix):  # nearest-the-question first
                    if p in havoc_pot:
                        havoc_pot.remove(p)
                        if p in seeds and p not in seed_refuted:
                            interval_pot[p] = seeds[p]
                            validated = False
                        break
                    if p in interval_pot:
                        interval_pot.pop(p)
                        break
                else:
                    return ledger("spurious-at-exact-cone")
            else:
                return ledger("reachable", replay_confirms=True)
        elif verdict is Verdict.UNREACHABLE:
            return ledger("unreachable", direction=route.route_direction(
                ["btor2-havoc"]
                + (["btor2-interval"] if interval_played else [])))
        else:
            return ledger(f"unknown ({verdict})")
        if rounds >= limit:
            return ledger("round-limit")


def make_decide(bench: Benchmark, books_path: str, *, k: int,
                native: NativeFn | None = None) -> Callable[
                    [str, int], tuple[Verdict, dict[str, Any]]]:
    """The player: the havoc player's routing (exact-first with the
    abstraction as fallback; abstraction-first for the books' standing
    cost demands; probes play a single havoc round — the route's first
    leg) with the interval rung walked on refinement."""
    native = native or _capped_native()
    blocked = blocked_hashes(bench, books_path)

    def _abstraction(text: str, kk: int) -> tuple[Verdict, dict[str, Any]]:
        adv = suggest_reduction(text, k=2, samples=0)
        free = list(adv["free_havoc"])
        ladder = list(adv["refinement_ladder"])
        prefix = ladder[:max(1, len(ladder) // 2)] if ladder else []
        seeds = {lbl: rng for lbl, rng in usable_seeds(text, adv).items()
                 if lbl in prefix}
        base: dict[str, Any] = {"engine": "btormc", "pair": "btor2-interval",
                                "free": len(free), "prefix": len(prefix),
                                "seeded_rungs": len(seeds)}
        if kk < k:  # a probe: one havoc round, no refinement (the caps)
            v, wit = native(_havoc(text, tuple(free + prefix)), kk)
            probe = {**base, "probe": True, "spent_pairs": ["btor2-havoc"]}
            if (v is Verdict.REACHABLE
                    and not _source_replay_hits_bad(text, wit, kk)):
                return Verdict.UNKNOWN, {**probe, "spurious": 1}
            return v, probe
        cegar = run_interval_cegar(
            text, kk, free, prefix, seeds, native,
            lambda wit: not _source_replay_hits_bad(text, wit, kk),
            max_rounds=CEGAR_MAX_ROUNDS)
        meta = {**base, "rounds": cegar["rounds"],
                "spurious": cegar["spurious"],
                "havocked": len(cegar["final_havoc"]),
                "confined": sorted(cegar["final_intervals"]),
                "spent_pairs": ["btor2-havoc"] + (
                    ["btor2-interval"] if cegar["interval_played"] else [])}
        if cegar["seed_refuted"]:
            meta["seed_refuted"] = sorted(set(cegar["seed_refuted"]))
        if cegar["demoted_unvalidated"]:
            meta["unvalidated_demoted"] = sorted(cegar["demoted_unvalidated"])
        verdict = cegar["verdict"]
        if verdict == "unreachable":
            return Verdict.UNREACHABLE, {**meta,
                                         "transfers": cegar["direction"]}
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
