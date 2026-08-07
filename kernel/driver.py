"""One loop iteration (KERNEL.md §4): play a benchmark, record, report.

The driver is deliberately one iteration per invocation; autonomy is
the outer agent invoking it repeatedly, and pulling the plug is safe at
any moment because every result is appended as it happens and the
report is a pure function of the log. The driver contains no conjecture
code: the LLM reads ``frontier.md`` and writes registry entries; the
kernel adjudicates. The LLM never writes a result.

Routes are enumerated breadth-first (translation hops, then a solver
pair), deterministically ordered by hop count then pair id. Universal
verdicts transfer back over ``exact`` and ``over`` hops only; witnesses
are carried back hop by hop through each pair's ``lam.py`` and replayed
at the source — a witness that cannot be carried or does not replay is
booked as evidence inside a ``partial``, never as a result.

Usage::

    python3 -m kernel.driver play  <run-dir> [--registry DIR] [--wall S]
    python3 -m kernel.driver report <run-dir>
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

from . import checker, registry, results, runner

_DEFAULT_WALL_S = 60.0


# -- routes -------------------------------------------------------------------

def enumerate_routes(reg: dict, language: str,
                     max_hops: int = 2) -> list[list[dict]]:
    """All routes from ``language`` to a solver pair: zero or more
    translation hops, then one solver pair. Deterministic order: fewer
    hops first, then pair ids."""
    translations = [m for m in reg["pairs"].values()
                    if m.get("pair_kind") != "solver" and "admission" in m]
    solvers = [m for m in reg["pairs"].values()
               if m.get("pair_kind") == "solver" and "admission" in m]
    routes: list[list[dict]] = []
    frontier_paths: list[tuple[str, list[dict]]] = [(language, [])]
    for _ in range(max_hops + 1):
        next_paths: list[tuple[str, list[dict]]] = []
        for lang, hops in frontier_paths:
            for solver in sorted(solvers, key=lambda m: m["id"]):
                if solver["src"] == lang:
                    routes.append(hops + [solver])
            for t in sorted(translations, key=lambda m: m["id"]):
                if t["src"] == lang and t["id"] not in [h["id"] for h in hops]:
                    next_paths.append((t["tgt"], hops + [t]))
        frontier_paths = next_paths
    return routes


def _translate_chain(hops: list[dict], program: str,
                     wall_s: float) -> tuple[str | None, str]:
    """Run the translation hops; return (program-path or None, note)."""
    current = program
    for hop in hops:
        res, same = runner.run_twice(os.path.join(hop["_dir"], "T.py"),
                                     [current], wall_s=wall_s)
        if not same or not res.ok:
            return None, f"{hop['id']}: translation failed or nondeterministic"
        fd, path = tempfile.mkstemp(suffix=".program")
        with os.fdopen(fd, "wb") as fh:
            fh.write(res.out)
        current = path
    return current, ""


def run_route(reg: dict, route: list[dict], question: dict,
              wall_s: float) -> dict:
    """Run one route; always returns a result record (partial on any
    failure — a route that breaks is evidence, not an exception)."""
    hops, solver = route[:-1], route[-1]
    rec = {"question": question["id"],
           "route": [p["id"] for p in route],
           "budget": {"wall_s": wall_s, "spent_s": 0.0}}

    def partial(note: str, **progress) -> dict:
        rec["value"] = {"kind": "partial",
                        "progress": {"note": note, **progress}}
        rec["grade"] = ""
        return rec

    program, note = _translate_chain(hops, question["_program_path"], wall_s)
    if program is None:
        return partial(note)
    res, same = runner.run_twice(
        os.path.join(solver["_dir"], "solve.py"),
        [program, question["mode"], question["observable"],
         str(question["bound"]), str(wall_s)], wall_s=wall_s * 2 + 10)
    rec["budget"]["spent_s"] = round(res.wall_s, 3)
    if res.timed_out:
        return partial("solver exceeded twice the declared wall")
    if not same:
        return partial("solver nondeterministic")
    if not res.ok:
        return partial(f"solver failed rc={res.rc}",
                       stderr=res.err[:400].decode(errors="replace"))
    try:
        value = json.loads(res.out)
    except json.JSONDecodeError:
        return partial("solver output not JSON")

    if value.get("kind") == "witness":
        src = reg["languages"][question["language"]]
        fired, depth = checker.certify_witness(
            src, solver["_dir"], question["_program_path"],
            question["observable"], value.get("payload"), hops=hops,
            wall_s=wall_s)
        if not fired:
            return partial("witness did not replay at the source",
                           witness=value.get("payload"))
        rec["value"] = {"kind": "witness", "payload": value.get("payload"),
                        "depth": depth or value.get("depth", 0)}
        rec["grade"] = "replayed"
    elif value.get("kind") == "all":
        if any(h.get("direction") not in ("exact", "over") for h in hops):
            return partial("universal cannot transfer over an under-"
                           "approximating hop", claimed=value)
        rec["value"] = {"kind": "all", "bound": value["bound"],
                        "cert": value.get("cert")}
        # Strict ladder (KERNEL.md §2): claimed until the kernel itself
        # discharges the certificate against the program. On a hop-free
        # route the program is the source, so a validated discharge is
        # route-independent: certified. Past translation hops it is
        # checked at the target — route trust rides along. Fail-safe:
        # any discharge failure leaves the verdict claimed.
        rec["grade"] = "claimed"
        obligations = checker.discharge_cert(
            solver["_dir"], program, value.get("cert"), wall_s=wall_s)
        if obligations is not None:
            rec["grade"] = "certified" if not hops else "checked"
            rec["discharge"] = {
                "at": "source" if not hops else "target",
                "lineage": solver.get("discharge_lineage", []),
                "obligations": obligations}
    elif value.get("kind") == "partial":
        rec["value"] = value
        rec["grade"] = ""
    else:
        return partial(f"unknown value kind {value.get('kind')!r}")
    return rec


# -- play ---------------------------------------------------------------------

def play(run_dir: str, reg_root: str = "registry", *,
         wall_s: float = _DEFAULT_WALL_S) -> str:
    bench = results.load_benchmark(os.path.join(run_dir, "benchmark.json"))
    reg = registry.load(reg_root)
    log_path = os.path.join(run_dir, "log.jsonl")
    prior = results.load(log_path)
    iteration = sum(1 for r in prior if r.get("event") == "play")
    results.append(log_path, {"event": "play", "iteration": iteration,
                              "caps": {"wall_s": wall_s}})
    for q in bench["questions"]:
        routes = enumerate_routes(reg, q["language"])
        if not routes:
            results.append(log_path, {
                "question": q["id"], "route": [],
                "budget": {"wall_s": 0, "spent_s": 0.0},
                "value": {"kind": "partial",
                          "progress": {"note": "no route: no admitted "
                                       f"solver reachable from "
                                       f"{q['language']}"}},
                "grade": ""})
            continue
        for route in routes:
            rec = run_route(reg, route, q, wall_s)
            rec["iteration"] = iteration
            results.append(log_path, rec)
            if results.terminal(q, rec["value"]):
                break
    for contra in results.contradictions(bench, results.load(log_path)):
        results.append(log_path, {"event": "contradiction",
                                  "question": contra["question"],
                                  "witness_route": contra["witness"]["route"],
                                  "universal_route":
                                      contra["universal"]["route"]})
    return report(run_dir)


def report(run_dir: str) -> str:
    bench = results.load_benchmark(os.path.join(run_dir, "benchmark.json"))
    text = results.report(bench, results.load(
        os.path.join(run_dir, "log.jsonl")))
    with open(os.path.join(run_dir, "frontier.md"), "w",
              encoding="utf-8") as fh:
        fh.write(text)
    return text


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] in ("play", "report"):
        run_dir = argv[1]
        kw = {}
        if "--registry" in argv:
            kw["reg_root"] = argv[argv.index("--registry") + 1]
        if "--wall" in argv:
            kw["wall_s"] = float(argv[argv.index("--wall") + 1])
        text = play(run_dir, **kw) if argv[0] == "play" else report(run_dir)
        sys.stdout.write(text)
        return 0
    sys.stderr.write(__doc__ or "")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
