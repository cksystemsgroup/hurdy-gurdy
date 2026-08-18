"""The two modes of operation (KERNEL.md §4, §6).

*Automatic*: ``play`` runs a pinned benchmark against everything
admitted — the loop is the LLM invoking it repeatedly, reading the
frontier, generating what would move it, and passing that through the
gate; pulling the plug is safe at any moment because every result is
appended as it happens and the board and graph are pure functions of
the log. *Manual*: a human writes a registry entry directory and
``admit`` runs the same one gate over it. Same operations, same gate,
no special case: steering the system is only ever adding checked
capability. The driver contains no conjecture code, and the LLM never
writes a result — only the kernel does, by running checked code.

Routes are enumerated breadth-first — translation hops, then a
terminal — deterministically ordered by hop count then entry id, over
the **whole** registry: a domain never fences it, so every admitted
pair and terminal is in play for every benchmark, however unrelated
the domains look (KERNEL.md §4). Universal verdicts transfer back over
``exact`` and ``over`` hops only; witnesses are carried back hop by
hop through each pair's ``lam.py`` and replayed at the source — a
witness that cannot be carried or does not replay is booked as
evidence inside a ``partial``, never as a result.

Usage::

    python3 -m kernel.driver play   <run-dir>   [--registry DIR] [--wall S]
                                                [--only id1,id2,...]
    python3 -m kernel.driver report <run-dir>   [--registry DIR]
    python3 -m kernel.driver graph  <run-dir>   [--registry DIR]
    python3 -m kernel.driver admit  <entry-dir> [--registry DIR] [--wall S]
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
    """All routes from ``language`` to a terminal: zero or more
    translation hops, then one terminal at the reached language.
    Deterministic order: fewer hops first, then entry ids. The whole
    registry participates — availability is universal."""
    pairs = [m for m in reg["pairs"].values() if "admission" in m]
    terminals = [m for m in reg["terminals"].values() if "admission" in m]
    routes: list[list[dict]] = []
    reached: list[tuple[str, list[dict]]] = [(language, [])]
    for _ in range(max_hops + 1):
        nxt: list[tuple[str, list[dict]]] = []
        for lang, hops in reached:
            for term in sorted(terminals, key=lambda m: m["name"]):
                if term["language"] == lang:
                    routes.append(hops + [term])
            for t in sorted(pairs, key=lambda m: m["id"]):
                if t["src"] == lang and t["id"] not in [h["id"] for h in hops]:
                    nxt.append((t["tgt"], hops + [t]))
        reached = nxt
    return routes


def _exe(manifest: dict, name: str) -> str:
    """The checked fast path (KERNEL.md §2): translation and solving may
    run an admitted accelerator, because their outputs are checked
    downstream — witnesses replay, universal claims grade. Replay and
    discharge never come through here: the check itself is always the
    Python reference."""
    acc = manifest.get("accelerator")
    if (acc and acc.get("replaces") == name
            and "accelerator" in manifest.get("admission", {})):
        return os.path.join(manifest["_dir"], acc["exe"])
    return os.path.join(manifest["_dir"], name)


def _translate_chain(hops: list[dict], program: str,
                     wall_s: float) -> tuple[list[str] | None, str]:
    """Run the translation hops; return (the program chain — source
    first, one entry per language crossed — or None, note)."""
    chain = [program]
    for hop in hops:
        res, same = runner.run_twice(_exe(hop, "T.py"), [chain[-1]],
                                     wall_s=wall_s)
        if not same or not res.ok:
            return None, f"{hop['id']}: translation failed or nondeterministic"
        fd, path = tempfile.mkstemp(suffix=".program")
        with os.fdopen(fd, "wb") as fh:
            fh.write(res.out)
        chain.append(path)
    return chain, ""


def run_route(reg: dict, route: list[dict], question: dict,
              wall_s: float) -> dict:
    """Run one route; always returns a result record (partial on any
    failure — a route that breaks is evidence, not an exception)."""
    hops, term = route[:-1], route[-1]
    rec = {"question": question["id"],
           "route": [p["id"] for p in hops] + [term["name"]],
           # The route's lineage union, recorded so corroboration —
           # disjoint lineages agreeing (KERNEL.md §3) — is computable
           # from the log alone; the report stays a pure function of it.
           "lineage": sorted({x for p in route
                              for x in p.get("lineage", [])}),
           "budget": {"wall_s": wall_s, "spent_s": 0.0}}
    # entries running at a revision > 1 say so, so the log's citations
    # stay exact even after a name rebinds (KERNEL.md §8)
    revs = {(p.get("id") or p.get("name")): p["revision"]
            for p in route if p.get("revision", 1) > 1}
    if revs:
        rec["revisions"] = revs

    def partial(note: str, **progress) -> dict:
        rec["value"] = {"kind": "partial",
                        "progress": {"note": note, **progress}}
        rec["grade"] = ""
        return rec

    # The observable composed through the hops' declared maps must be
    # one the terminal declares it decides; anything else is a partial,
    # never an answer.
    observable = question["observable"]
    for hop in hops:
        observable = hop.get("maps", {}).get(observable, observable)
    if observable not in term.get("decides", []):
        return partial(
            f"route cannot decide {question['observable']!r}: composed "
            f"observable is {observable!r}, terminal decides "
            f"{term.get('decides', [])}")

    chain, note = _translate_chain(hops, question["_program_path"], wall_s)
    if chain is None:
        return partial(note)
    program = chain[-1]
    res, same = runner.run_twice(
        _exe(term, "solve.py"),
        [program, question["mode"], observable,
         str(question["bound"]), str(wall_s)], wall_s=wall_s * 2 + 10)
    rec["budget"]["spent_s"] = round(res.wall_s, 3)
    if res.timed_out:
        return partial("terminal exceeded twice the declared wall")
    if not same:
        return partial("terminal nondeterministic")
    if not res.ok:
        return partial(f"terminal failed rc={res.rc}",
                       stderr=res.err[:400].decode(errors="replace"))
    try:
        value = json.loads(res.out)
    except json.JSONDecodeError:
        return partial("terminal output not JSON")

    if value.get("kind") == "witness":
        src = reg["languages"][question["language"]]
        fired, depth = checker.certify_witness(
            src, term["_dir"], question["_program_path"],
            question["observable"], value.get("payload"), hops=hops,
            programs=chain, wall_s=wall_s)
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
        # A universal claim crossing a bound-eating hop caps at the
        # hop's declared unrolling: a k=20 unsat is a bound-20 fact,
        # never an unbounded one.
        rec["value"] = {"kind": "all",
                        "bound": results.cap(
                            value["bound"],
                            [h.get("bound_cap", "inf") for h in hops]),
                        "cert": value.get("cert")}
        # Strict ladder (KERNEL.md §3): claimed until the kernel itself
        # discharges the certificate against the program. On a hop-free
        # route the program is the source, so a validated discharge is
        # route-independent: certified. Past translation hops it is
        # checked at the target — route trust rides along. Fail-safe:
        # any discharge failure leaves the verdict claimed.
        rec["grade"] = "claimed"
        obligations = checker.discharge_cert(
            term["_dir"], program, value.get("cert"), wall_s=wall_s)
        if obligations is not None:
            rec["grade"] = "certified" if not hops else "checked"
            rec["discharge"] = {
                "at": "source" if not hops else "target",
                "lineage": term.get("discharge_lineage", []),
                "obligations": obligations}
    elif value.get("kind") == "partial":
        rec["value"] = value
        rec["grade"] = ""
    else:
        return partial(f"unknown value kind {value.get('kind')!r}")
    return rec


# -- play (the automatic mode's one iteration) --------------------------------

def play(run_dir: str, reg_root: str = "registry", *,
         wall_s: float = _DEFAULT_WALL_S,
         only: set[str] | None = None) -> str:
    bench = results.load_benchmark(os.path.join(run_dir, "benchmark.json"))
    if only is not None:
        known = {q["id"] for q in bench["questions"]}
        unknown = sorted(only - known)
        if unknown:
            raise ValueError(f"--only names unknown questions: {unknown}")
    reg = registry.load(reg_root)
    log_path = os.path.join(run_dir, "log.jsonl")
    prior = results.load(log_path)
    iteration = sum(1 for r in prior if r.get("event") == "play")
    event = {"event": "play", "iteration": iteration,
             "caps": {"wall_s": wall_s}}
    if only is not None:
        # A restricted play is the deliberate form of what a plug-pull
        # produces by accident: fewer paths this iteration, the ratchet
        # untouched. The log records the restriction so no reader
        # mistakes a partial iteration for a full one.
        event["only"] = sorted(only)
    results.append(log_path, event)
    for q in bench["questions"]:
        if only is not None and q["id"] not in only:
            continue
        routes = enumerate_routes(reg, q["language"])
        if not routes:
            results.append(log_path, {
                "question": q["id"], "route": [],
                "budget": {"wall_s": 0, "spent_s": 0.0},
                "value": {"kind": "partial",
                          "progress": {"note": "no route: no admitted "
                                       f"terminal reachable from "
                                       f"{q['language']}"}},
                "grade": ""})
            continue
        # Enumerate, don't choose: every admitted route plays, so a
        # settled answer can still gain grade (a later route's
        # certificate) and corroboration (a disjoint lineage agreeing).
        # The wall cap per route is the budget; junk never wins a route
        # because the result order, not arrival, picks the best.
        for route in routes:
            rec = run_route(reg, route, q, wall_s)
            rec["iteration"] = iteration
            results.append(log_path, rec)
    for contra in results.contradictions(bench, results.load(log_path)):
        results.append(log_path, {"event": "contradiction",
                                  "question": contra["question"],
                                  "witness_route": contra["witness"]["route"],
                                  "universal_route":
                                      contra["universal"]["route"]})
    return report(run_dir, reg_root)


def report(run_dir: str, reg_root: str = "registry") -> str:
    """Regenerate the board (``frontier.md``) and the graph
    (``frontier.dot``) from the log; return the board."""
    bench = results.load_benchmark(os.path.join(run_dir, "benchmark.json"))
    log = results.load(os.path.join(run_dir, "log.jsonl"))
    text = results.report(bench, log)
    with open(os.path.join(run_dir, "frontier.md"), "w",
              encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(run_dir, "frontier.dot"), "w",
              encoding="utf-8") as fh:
        fh.write(results.dot(registry.load(reg_root), bench, log))
    return text


# -- admit (the manual mode; the loop's gate is the same call) ----------------

def admit(entry_dir: str, reg_root: str = "registry", *,
          wall_s: float = _DEFAULT_WALL_S) -> dict:
    """A human (or the LLM) writes an entry directory under the
    registry; the kernel adjudicates. Runs the one gate — the
    generation rule, determinism, the square (or result validity), and
    two-sided controls — and stamps the evidence into the manifest.
    Any failure raises and leaves the entry unstamped."""
    entry_dir = os.path.abspath(entry_dir)
    with open(os.path.join(entry_dir, "manifest.json"),
              encoding="utf-8") as fh:
        manifest = json.load(fh)
    evidence = checker.check(registry.load(reg_root), entry_dir, manifest,
                             wall_s=wall_s)
    registry.stamp_admission(entry_dir, evidence)
    return evidence


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] in ("play", "report", "graph", "admit"):
        run_dir = argv[1]
        kw = {}
        if "--registry" in argv:
            kw["reg_root"] = argv[argv.index("--registry") + 1]
        if "--wall" in argv:
            kw["wall_s"] = float(argv[argv.index("--wall") + 1])
        if argv[0] == "play" and "--only" in argv:
            kw["only"] = {qid for qid in
                          argv[argv.index("--only") + 1].split(",") if qid}
        if argv[0] == "play":
            text = play(run_dir, **kw)
        elif argv[0] == "report":
            text = report(run_dir, kw.get("reg_root", "registry"))
        elif argv[0] == "admit":
            try:
                evidence = admit(run_dir, **kw)
            except (checker.AdmissionError,
                    registry.RegistryError) as exc:
                sys.stderr.write(f"not admitted: {exc}\n")
                return 1
            text = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        else:
            text = results.dot(
                registry.load(kw.get("reg_root", "registry")),
                results.load_benchmark(
                    os.path.join(run_dir, "benchmark.json")),
                results.load(os.path.join(run_dir, "log.jsonl")))
        sys.stdout.write(text)
        return 0
    sys.stderr.write(__doc__ or "")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
