#!/usr/bin/env python3
"""The abstraction benchmark: the direction axis measured end to end
(ARCHITECTURE.md §3; the paper's §3.4 and POTENTIAL.md §6; the last
post-snapshot benchmark family named by the paper's evaluation
exhibits — HWMCC ingestion for the hub and its abstraction pairs).

Two blocks.

**Authored block** (controlled ground truth; z3 only):

* ``decoy-M`` — a small counter question beside M symbolic 24-bit
  states with multiplier-heavy updates, all outside the question's
  cone. Havocking the advisor's free set must preserve the verdict on
  both engines while the artifact (BTOR2 text and the bridge's SMT
  unrolling) shrinks. Decide *time* is reported as measured — engines
  already ignore satisfiable-independent transitions, so parity there
  is the honest expectation, and the finding.
* ``cegar-chain`` — a 6-deep dependency chain plus free decoys,
  abstracted too aggressively on purpose (the advisor's ladder prefix):
  every spurious counterexample is caught by source replay, each
  refinement un-havocs one ladder rung, and the loop must converge to
  exactly the advisor's free set with the universal verdict
  transferring (``direction.transfers``).
* ``true-cex`` — a genuinely reachable question through the free-set
  abstraction: believed only after the source replay confirms it.
* ``sharp-boundary`` — the negative control: havocking one state
  *inside* the cone must produce a spurious reach (the free set's
  boundary is exact), refuted by replay.

**HWMCC block** (network + btormc gated): six bit-vector instances from
the HWMCC 2019--2024 corpus, streamed-with-pin (commit + sha256,
BENCHMARKS.md §4) from the community mirror, spanning beem, mann, and
sosylab families. Per instance: ingestion through the platform's own
stack (parse, shared-evaluator run, reduction advisor), the exact
bounded verdict (btormc, canary-controlled), and the CEGAR
localization: havoc the advisor's ladder-prefix, refine on spurious
counterexamples — each checked by replaying the witness at the
*source* with the havoc inputs filtered out — and report where the
loop converges (havocked states / total) and that the converged
verdict agrees with the exact one. Skipped honestly when offline.

Sequential throughout; every solver call is on a system of ~10 states.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from typing import Any, Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gurdy.core import direction, route  # noqa: E402
from gurdy.core.benchmark import Benchmark, Instance  # noqa: E402
from gurdy.core.benchmark import fetch as _bench_fetch  # noqa: E402
from gurdy.core.question import Question  # noqa: E402
from gurdy.core.solver import Verdict  # noqa: E402
from gurdy.languages.btor2.build import Builder  # noqa: E402
from gurdy.languages.btor2.coi import suggest_reduction  # noqa: E402
from gurdy.languages.btor2.eval import interpret  # noqa: E402
from gurdy.languages.btor2.model import from_text  # noqa: E402
from gurdy.languages.btor2.witness import parse_witness  # noqa: E402
from gurdy.pairs.btor2_havoc import translate as havoc_translate  # noqa: E402
from gurdy.pairs.btor2_smtlib import reach, translate as bridge_translate  # noqa: E402

import gurdy.pairs.btor2_havoc   # noqa: F401,E402  (registration)
import gurdy.pairs.btor2_smtlib  # noqa: F401,E402


# --- the pinned HWMCC slice (streamed-with-pin; BENCHMARKS.md §4) ---------

HWMCC_COMMIT = "57174f5d6f575aedcfe83694b35ec8e7b83043fc"
HWMCC_REPO = "CyanoKobalamyne/hwmcc-benchmarks"
HWMCC_K = 20
HWMCC = {
    "bin-suffix-5": {
        "path": "bv/2024/sosylab/loop-invariants/bin-suffix-5.btor2",
        "sha256": "4a3020ad7c498472966af3b4c2d2f8e38eb73d16b2ba285a72003ffc8f94b272",
        "family": "sosylab'24", "expected": "unreachable"},
    "trex02-1": {
        "path": "bv/2024/sosylab/loops/trex02-1.btor2",
        "sha256": "51b5162c5f8236acd307f7dbcfbc6107b2fdccc8ba4ba3756194f181ac71dd1e",
        "family": "sosylab'24", "expected": "unreachable"},
    "benchmark04_conjunctive": {
        "path": "bv/2024/sosylab/loop-zilu/benchmark04_conjunctive.btor2",
        "sha256": "7a0fea741ef809c72423d7d229f45a7ffee394e71c7d0b81546c36af04046079",
        "family": "sosylab'24", "expected": "unreachable"},
    "phases_2-1": {
        "path": "bv/2024/sosylab/loop-acceleration/phases_2-1.btor2",
        "sha256": "7e8e902882ce8406b25d1c5d0acd8ce24dd30f77bffbf6e89236ffc8e0c83296",
        "family": "sosylab'24", "expected": "reachable"},
    "analog_estimation": {
        "path": "bv/2019/mann/unsafe/analog_estimation_convergence.btor2",
        "sha256": "bcc576cd35dfc231bbfc3ed7585843d2609572a1e5cbcf1b260e360f45b48247",
        "family": "mann'19", "expected": "reachable"},
    "adding.5": {
        "path": "bv/2019/beem/adding.5.prop1-func-interl.btor2",
        "sha256": "af5441359805f446c42c8898f6dae1a400eb34ee2c14990f58b2cbc40337e7db",
        "family": "beem'19", "expected": "unreachable",
        "note": "negated-refs ingestion catch"},
}


def hwmcc_benchmark() -> Benchmark:
    """The pinned slice as the platform's benchmark object
    (core/benchmark.py; FRONTIER.md §1.1) — same pins, same provenance,
    one ingestion. ``gurdy saturation`` consumes its JSON."""
    return Benchmark(
        suite="hwmcc-slice",
        source=f"github:{HWMCC_REPO}@{HWMCC_COMMIT}",
        instances=tuple(
            Instance(
                name=name, path=meta["path"], sha256=meta["sha256"],
                question=Question(source="btor2", shape="reachability",
                                  program=name),
                expected=meta["expected"],
                meta={k: meta[k] for k in ("family", "note") if k in meta})
            for name, meta in HWMCC.items()))


def _cache_dir() -> str:
    d = os.environ.get("GURDY_HWMCC_CACHE") or os.path.join(
        tempfile.gettempdir(), "hurdy-hwmcc-cache")
    os.makedirs(d, exist_ok=True)
    return d


def fetch_instance(name: str) -> str | None:
    """Fetch (or reuse the cached copy of) one pinned instance through
    the shared streamed-with-pin ingestion (core/benchmark.py — sha256
    verified; a mismatch is an error, never a silent substitution).
    Returns the BTOR2 text, or None when offline."""
    data = _bench_fetch(hwmcc_benchmark(), name, cache_dir=_cache_dir())
    return data.decode("utf-8") if data is not None else None


# --- the authored block ----------------------------------------------------

DECOY_WIDTH = 24


def decoy_system(m: int, bad_at: int = 200, update_depth: int = 10) -> str:
    """A deterministic 8-bit counter question beside ``m`` symbolic
    24-bit states whose updates are deep multiplier towers (the
    expensive logic localization exists to drop), none feeding the bad:
    the advisor's free set is exactly the decoys."""
    b = Builder()
    c = b.state(8, "c")
    b.init(c, b.zero(8))
    b.next(c, b.op2("add", 8, c, b.one(8)))
    for i in range(m):
        d = b.state(DECOY_WIDTH, f"d{i}")  # no init: symbolic start
        v = d
        for j in range(update_depth):
            v = b.op2("add", DECOY_WIDTH,
                      b.op2("mul", DECOY_WIDTH, v, d),
                      b.constd(DECOY_WIDTH, j + 1))
        b.next(d, v)
    b.bad(b.op2("eq", 1, c, b.constd(8, bad_at)))
    return b.to_text()


def chain_system(depth: int = 6, decoys: int = 4) -> str:
    """A dependency chain s0 -> ... -> s{depth-1} (bad reads the far
    end) beside free decoys: the CEGAR corpus. Unreachable within the
    bound by construction (the chain delays the counter)."""
    b = Builder()
    s = b.state(8, "s0")
    b.init(s, b.zero(8))
    b.next(s, b.op2("add", 8, s, b.one(8)))
    prev = s
    for i in range(1, depth):
        si = b.state(8, f"s{i}")
        b.init(si, b.zero(8))
        b.next(si, prev)
        prev = si
    for i in range(decoys):
        d = b.state(DECOY_WIDTH, f"d{i}")
        b.next(d, b.op2("mul", DECOY_WIDTH, d, d))
    b.bad(b.op2("eq", 1, prev, b.constd(8, 9)))
    return b.to_text()


def _authored_bad_reached(source_text: str, k: int) -> bool:
    """Source-side truth for the authored corpus: every state the bad
    reads is initialized and input-free, so the deterministic run *is*
    the source's one behavior on the question's cone."""
    trace = interpret(source_text, {"steps": k + 1})
    return any(v == 1 for row in trace
               if all(cv == 1 for ck, cv in row.items()
                      if ck.startswith("constraint"))
               for key, v in row.items() if key.startswith("bad"))


def _havoc(source_text: str, labels: tuple[str, ...]) -> str:
    out = havoc_translate({"system": source_text, "havoc": labels})
    return out.decode("utf-8") if isinstance(out, (bytes, bytearray)) else out


def run_cegar(source_text: str, k: int,
              free: list[str], prefix: list[str],
              decide: Callable[[str, int], tuple[Verdict, Any]],
              spurious: Callable[[Any], bool],
              max_rounds: int | None = None) -> dict[str, Any]:
    """The refinement loop: havoc ``free + prefix``, decide, and on a
    reachable verdict ask ``spurious`` (source replay); a spurious
    counterexample un-havocs the ladder rung nearest the question
    (the prefix's end). Returns the loop's ledger."""
    havoc = list(free) + list(prefix)
    rounds = 0
    spurious_count = 0
    limit = (len(prefix) + 2) if max_rounds is None else max_rounds
    while True:
        rounds += 1
        verdict, evidence = decide(_havoc(source_text, tuple(havoc)), k)
        if verdict is Verdict.REACHABLE:
            if spurious(evidence):
                spurious_count += 1
                if not any(p in havoc for p in prefix):
                    return {"verdict": "spurious-at-exact-cone",
                            "rounds": rounds, "spurious": spurious_count,
                            "final_havoc": havoc}
                for p in reversed(prefix):  # nearest-the-question first
                    if p in havoc:
                        havoc.remove(p)
                        break
            else:
                return {"verdict": "reachable", "rounds": rounds,
                        "spurious": spurious_count, "final_havoc": havoc,
                        "replay_confirms": True}
        elif verdict is Verdict.UNREACHABLE:
            return {"verdict": "unreachable", "rounds": rounds,
                    "spurious": spurious_count, "final_havoc": havoc,
                    "transfers": direction.transfers(
                        "unreachable", route.route_direction(["btor2-havoc"]))}
        else:
            return {"verdict": f"unknown ({verdict})", "rounds": rounds,
                    "spurious": spurious_count, "final_havoc": havoc}
        if rounds >= limit:
            return {"verdict": "round-limit", "rounds": rounds,
                    "spurious": spurious_count, "final_havoc": havoc}


def _bridged_decide(text: str, k: int) -> tuple[Verdict, Any]:
    info = reach(text, k)
    return info["verdict"], info


def run_authored() -> dict[str, Any]:
    """The controlled block (z3 only)."""
    K = 12
    decoy_rows = []
    for m in (2, 4, 8):
        text = decoy_system(m)
        adv = suggest_reduction(text, k=4, samples=1)
        assert adv["free_havoc"] == [f"d{i}" for i in range(m)]
        abst = _havoc(text, tuple(adv["free_havoc"]))
        t0 = time.perf_counter()
        v_exact = reach(text, K)["verdict"]
        t_exact = time.perf_counter() - t0
        t0 = time.perf_counter()
        v_abst = reach(abst, K)["verdict"]
        t_abst = time.perf_counter() - t0
        smt_exact = len(bridge_translate({"system": text, "k": K}))
        smt_abst = len(bridge_translate({"system": abst, "k": K}))
        decoy_rows.append({
            "m": m, "k": K,
            "states_exact": 1 + m, "states_abstract": 1 + m,
            "verdict_exact": v_exact.value, "verdict_abstract": v_abst.value,
            "verdicts_agree": v_exact == v_abst == Verdict.UNREACHABLE,
            "btor2_bytes": [len(text), len(abst)],
            "smt_bytes": [smt_exact, smt_abst],
            "decide_s": [round(t_exact, 4), round(t_abst, 4)],
            "transfers": direction.transfers("unreachable", "over"),
        })

    chain = chain_system()
    adv = suggest_reduction(chain, k=4, samples=1)
    prefix = adv["refinement_ladder"][:4]   # farthest-first, aggressive
    cegar = run_cegar(chain, 12, adv["free_havoc"], prefix,
                      _bridged_decide,
                      lambda _info: not _authored_bad_reached(chain, 12))
    cegar["converged_to_free_set"] = sorted(cegar["final_havoc"]) == sorted(
        adv["free_havoc"])

    reach_sys = decoy_system(4, bad_at=9)
    adv_r = suggest_reduction(reach_sys, k=4, samples=1)
    abst_r = _havoc(reach_sys, tuple(adv_r["free_havoc"]))
    info = reach(abst_r, 12)
    true_cex = {
        "verdict": info["verdict"].value,
        "replay_confirms": _authored_bad_reached(reach_sys, 12),
        "witness_ok_on_abstraction": bool(info.get("witness_ok")),
    }

    boundary_sys = decoy_system(4)
    adv_b = suggest_reduction(boundary_sys, k=4, samples=1)
    over = _havoc(boundary_sys, tuple(adv_b["free_havoc"] + ["c"]))
    v_over = reach(over, 12)["verdict"]
    sharp = {
        "abstract_verdict": v_over.value,
        "source_bad": _authored_bad_reached(boundary_sys, 12),
        "spurious_as_expected": (v_over is Verdict.REACHABLE
                                 and not _authored_bad_reached(boundary_sys, 12)),
    }
    return {"decoys": decoy_rows, "cegar": cegar, "true_cex": true_cex,
            "sharp_boundary": sharp}


# --- the HWMCC block --------------------------------------------------------

def _source_replay_hits_bad(source_text: str, wit_text: str, k: int) -> bool:
    """Replay an *abstraction* witness at the source: frame-0 states and
    the source's own inputs carry over (matched by symbol, else by the
    positional prefix — havoc inputs are appended after the source's,
    and their ``havoc_*`` symbols never match); a ``bad`` counts only on
    a constraint-valid row."""
    sysm = from_text(source_text)
    w = parse_witness(wit_text)
    states = sysm.states()
    src_inputs = [n for n in sysm.nodes.values() if n.op == "input"]
    ssym = {n.symbol: n for n in states if n.symbol}
    isym = {n.symbol: n for n in src_inputs if n.symbol}

    state_binding: dict[str, Any] = {}
    for idx, sym, val in w.states:
        node = ssym.get(sym) if sym else (
            states[idx] if 0 <= idx < len(states) else None)
        if node is not None and not isinstance(val, dict):
            state_binding[node.symbol or f"n{node.id}"] = val
    inputs: dict[int, dict[int, int]] = {}
    for fr, rows in w.inputs.items():
        r: dict[int, int] = {}
        for idx, sym, val in rows:
            node = (isym.get(sym) if sym is not None
                    else (src_inputs[idx] if 0 <= idx < len(src_inputs)
                          else None))
            if node is not None and not isinstance(val, dict):
                r[node.id] = val
        if r:
            inputs[fr] = r
    trace = interpret(sysm, {"steps": k + 1, "state": state_binding,
                             "inputs": inputs})
    return any(v == 1 for row in trace
               if all(cv == 1 for ck, cv in row.items()
                      if ck.startswith("constraint"))
               for key, v in row.items() if key.startswith("bad"))


def run_hwmcc() -> list[dict[str, Any]]:
    """The pinned slice, gated on btormc and the network."""
    from gurdy.solvers.native_btor2 import NativeBtor2Checker, find_btormc

    if not find_btormc():
        return [{"name": n, "status": "skipped (btormc absent)"}
                for n in HWMCC]
    checker = NativeBtor2Checker()

    def _native_decide(text: str, k: int) -> tuple[Verdict, Any]:
        v, wit = checker.decide_witness(text, k)
        if v is not Verdict.REACHABLE:
            v = checker.decide_bounded(text, k)
        return v, wit

    rows = []
    for name, meta in HWMCC.items():
        text = fetch_instance(name)
        if text is None:
            rows.append({"name": name, "status": "skipped (offline)"})
            continue
        sysm = from_text(text)
        nstates = len(list(sysm.states()))
        adv = suggest_reduction(text, k=4, samples=1)
        t0 = time.perf_counter()
        v_exact = checker.decide_bounded(text, HWMCC_K)
        t_exact = time.perf_counter() - t0
        ladder = adv["refinement_ladder"]
        prefix = ladder[:max(1, len(ladder) // 2)]
        t0 = time.perf_counter()
        cegar = run_cegar(
            text, HWMCC_K, adv["free_havoc"], prefix, _native_decide,
            lambda wit, _t=text: not _source_replay_hits_bad(_t, wit, HWMCC_K))
        t_cegar = time.perf_counter() - t0
        final_verdict = ("unreachable" if cegar["verdict"] == "unreachable"
                         else "reachable" if cegar["verdict"] == "reachable"
                         else cegar["verdict"])
        rows.append({
            "name": name, "family": meta["family"], "status": "ok",
            "states": nstates, "cone": len(adv["cone"]),
            "free": len(adv["free_havoc"]),
            "exact_verdict": v_exact.value, "exact_s": round(t_exact, 3),
            "expected": meta["expected"],
            "prefix": len(prefix),
            "cegar_verdict": final_verdict,
            "cegar_rounds": cegar["rounds"],
            "cegar_spurious": cegar["spurious"],
            "final_havocked": len(cegar["final_havoc"]),
            "cegar_s": round(t_cegar, 3),
            "agree": (final_verdict == v_exact.value == meta["expected"]),
            "note": meta.get("note", ""),
        })
    return rows


def run_experiment() -> dict[str, Any]:
    authored = run_authored()
    hwmcc = run_hwmcc()
    a_ok = (all(r["verdicts_agree"] and r["transfers"]
                and r["smt_bytes"][1] < r["smt_bytes"][0]
                for r in authored["decoys"])
            and authored["cegar"]["verdict"] == "unreachable"
            and authored["cegar"]["converged_to_free_set"]
            and authored["cegar"].get("transfers")
            and authored["true_cex"]["replay_confirms"]
            and authored["sharp_boundary"]["spurious_as_expected"])
    ran = [r for r in hwmcc if r.get("status") == "ok"]
    h_ok = all(r["agree"] for r in ran) if ran else None
    return {"authored": authored, "hwmcc": hwmcc,
            "hwmcc_ran": len(ran), "ok_authored": a_ok, "ok_hwmcc": h_ok,
            "ok": bool(a_ok and (h_ok is not False))}


def main() -> int:
    try:
        import z3  # noqa: F401
    except Exception:
        print("abstraction bench: z3 unavailable — cannot run")
        return 1
    report = run_experiment()
    a = report["authored"]
    for r in a["decoys"]:
        print(f"decoy-{r['m']}: verdicts agree={r['verdicts_agree']} "
              f"smt {r['smt_bytes'][0]}->{r['smt_bytes'][1]}B "
              f"decide {r['decide_s'][0]}s->{r['decide_s'][1]}s")
    print("cegar:", {k: a['cegar'][k] for k in
                     ('verdict', 'rounds', 'spurious', 'converged_to_free_set')})
    print("true-cex:", a["true_cex"])
    print("sharp-boundary:", a["sharp_boundary"])
    for r in report["hwmcc"]:
        if r.get("status") != "ok":
            print(f"{r['name']}: {r['status']}")
        else:
            print(f"{r['name']}: exact={r['exact_verdict']}({r['exact_s']}s) "
                  f"cegar={r['cegar_verdict']} rounds={r['cegar_rounds']} "
                  f"spurious={r['cegar_spurious']} "
                  f"havocked {r['final_havocked']}/{r['states']} "
                  f"agree={r['agree']}")
    print("ok:", report["ok"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
