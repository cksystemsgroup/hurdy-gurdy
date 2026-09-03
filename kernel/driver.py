"""The two modes of operation (KERNEL.md §7), and the check-time moves.

*Automatic*: ``play`` runs a pinned benchmark against everything
admitted — the loop is the LLM invoking it repeatedly, reading the
frontier, generating what would move it, and passing that through the
gate; pulling the plug is safe at any moment because every result is
appended as it happens and the board and graph are pure functions of
the log. *Manual*: a human writes a registry entry directory and
``admit`` runs the same one gate over it. Same operations, same gate,
no special case: steering the system is only ever adding checked
capability. The driver contains no conjecture code, and the LLM never
writes a result — only the kernel does, by running judges over
transported evidence.

Routes are enumerated breadth-first — ``prog`` hops, then one search —
deterministically ordered by hop count then entry id, over the
**whole** registry: a domain never fences it (KERNEL.md §7). Backward
reach is per channel (KERNEL.md §2): a universal claim crosses home
only over hops that offer ``claim`` (bounds capped by the meet); a
witness comes home only over hops that offer ``wit``, chained
carry-backs then replay where the question lives — a witness that
cannot come home is booked as evidence inside a ``partial``, never as
a result. A certificate is carried as far back as ``cert`` channels
reach, re-discharged at each arrival by that language's own judge;
the gap — hops between the question and the last check that passed —
is the grade (KERNEL.md §4), and the residual trust is the lineage
meet over the gap segment plus the judge that ran.

``regrade`` is the grade-raising replay (KERNEL.md §5): stored
certificates re-discharged under the current registry — check time,
not search time — so a newly admitted carry-back re-grades the map
without re-solving it. ``base`` prints the trusted base: a list, not
a story (KERNEL.md §1).

Usage::

    python3 -m kernel.driver play    <run-dir>   [--registry DIR] [--wall S]
                                                 [--only id1,id2,...]
    python3 -m kernel.driver report  <run-dir>   [--registry DIR]
    python3 -m kernel.driver graph   <run-dir>   [--registry DIR]
    python3 -m kernel.driver regrade <run-dir>   [--registry DIR] [--wall S]
    python3 -m kernel.driver admit   <entry-dir> [--registry DIR] [--wall S]
    python3 -m kernel.driver base                [--registry DIR]
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

from . import checker, registry, results, runner

_DEFAULT_WALL_S = 60.0


# -- routes -------------------------------------------------------------------

def enumerate_routes(reg: dict, language: str,
                     max_hops: int = 2) -> list[list[dict]]:
    """All routes from ``language`` to a search: zero or more ``prog``
    hops, then one search at the reached language. Deterministic
    order: fewer hops first, then entry ids. The whole registry
    participates — availability is universal."""
    pairs = [m for m in reg["pairs"].values() if "admission" in m]
    searches = [m for m in reg["searches"].values() if "admission" in m]
    routes: list[list[dict]] = []
    reached: list[tuple[str, list[dict]]] = [(language, [])]
    for _ in range(max_hops + 1):
        nxt: list[tuple[str, list[dict]]] = []
        for lang, hops in reached:
            for search in sorted(searches, key=lambda m: m["name"]):
                if search["language"] == lang:
                    routes.append(hops + [search])
            for t in sorted(pairs, key=lambda m: m["id"]):
                if t["src"] == lang and t["id"] not in [h["id"] for h in hops]:
                    nxt.append((t["tgt"], hops + [t]))
        reached = nxt
    return routes


def _exe(manifest: dict, name: str) -> str:
    """The checked fast path (KERNEL.md §6): translation and solving may
    run an admitted accelerator, because their outputs face judges
    downstream — witnesses replay, universal objects grade. Judging and
    carry-back never come through here: the checks are always the
    Python reference."""
    acc = manifest.get("accelerator")
    if (acc and acc.get("replaces") == name
            and "accelerator" in manifest.get("admission", {})):
        return os.path.join(manifest["_dir"], acc["exe"])
    return os.path.join(manifest["_dir"], name)


def _tmp(data: bytes, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return path


def _translate_chain(hops: list[dict], program: str,
                     wall_s: float) -> tuple[list[str] | None, str]:
    """Run the ``prog`` hops; return (the program chain — source first,
    one entry per language crossed — or None, note)."""
    chain = [program]
    for hop in hops:
        res, same = runner.run_twice(_exe(hop, "T.py"), [chain[-1]],
                                     wall_s=wall_s)
        if not same or not res.ok:
            return None, f"{hop['id']}: translation failed or nondeterministic"
        chain.append(_tmp(res.out, ".program"))
    return chain, ""


def _lineage(route: list[dict]) -> list[str]:
    """The route's full generated descent, recorded so corroboration —
    disjoint lineages agreeing (KERNEL.md §4) — is computable from the
    log alone."""
    return sorted({x for p in route for x in p.get("lineage", [])})


def _hints(hops: list[dict], chain: list[str],
           wall_s: float) -> str | None:
    """The forward trust-inert channel: collect each hint-bearing
    hop's seeds (run on its own source-side program) into one file for
    the search. A hint that fails is dropped — it can move cost, never
    a grade, so nothing here is a result."""
    seeds = []
    for i, hop in enumerate(hops):
        if "hint" not in hop.get("channels", []):
            continue
        res, same = runner.run_twice(
            os.path.join(hop["_dir"], "hint.py"), [chain[i]], wall_s=wall_s)
        if same and res.ok:
            try:
                seeds.append({"pair": hop["id"],
                              "hint": json.loads(res.out)})
            except json.JSONDecodeError:
                pass
    if not seeds:
        return None
    return _tmp(json.dumps(seeds, sort_keys=True).encode(), ".hints")


def _ledger(search: dict, program: str, value: dict,
            wall_s: float) -> dict | None:
    """The ledger beside the path (KERNEL.md §5): a search's optional
    ``ledger.py`` reads the program and the value the search wrote and
    reports what the play bought in bits — surprisal bounds, cleared
    bits. Profiling only: it is recorded, never ranked, and can never
    touch a grade, so a ledger that fails is simply absent."""
    ledger = os.path.join(search["_dir"], "ledger.py")
    if not os.path.isfile(ledger):
        return None
    value_path = _tmp(json.dumps(value, sort_keys=True).encode(), ".value")
    res, same = runner.run_twice(ledger, [program, value_path],
                                 wall_s=wall_s)
    if not same or not res.ok:
        return None
    try:
        out = json.loads(res.out)
    except json.JSONDecodeError:
        return None
    return out if isinstance(out, dict) else None


# -- the backward channels -----------------------------------------------

def _witness_home(reg: dict, question: dict, hops: list[dict],
                  chain: list[str], payload,
                  wall_s: float) -> tuple[dict | None, int, str]:
    """Chain ``wit`` carry-backs across the route, then replay where
    the question lives. Returns (home payload, depth, note); a None
    payload means the witness did not come home — evidence, not a
    result. Fail-safe: transport is untrusted, so a wrong carry-back
    can only lose a grade, never forge one."""
    for hop in hops:
        if "wit" not in hop.get("channels", []):
            return None, 0, f"{hop['id']}: no wit channel"
    data = json.dumps(payload, sort_keys=True).encode()
    for i, hop in reversed(list(enumerate(hops))):
        res, same = runner.run_twice(
            os.path.join(hop["_dir"], "lam_wit.py"),
            [_tmp(data, ".input"), chain[i]], wall_s=wall_s)
        if not same or not res.ok:
            return None, 0, f"{hop['id']}: carry-back failed"
        data = res.out
    try:
        home = json.loads(data)
    except json.JSONDecodeError:
        return None, 0, "carried payload not JSON"
    lang = reg["languages"][question["language"]]
    fired, depth = checker.replay(lang, question["_program_path"],
                                  question["observable"], home,
                                  wall_s=wall_s)
    if not fired:
        return None, 0, "witness did not replay at the question"
    return home, depth, ""


def _discharge_chain(reg: dict, question: dict, hops: list[dict],
                     chain: list[str], cert,
                     wall_s: float) -> tuple[int | None, dict | None]:
    """Carry a certificate as far home as ``cert`` channels reach,
    re-discharging at each arrival by that language's own judge
    (KERNEL.md §4: each arrival check removes everything upstream of
    it from the meet). Returns (gap, discharge record) — gap None when
    no check ever passed."""
    langs = [reg["languages"][question["language"]]] + \
            [reg["languages"][h["tgt"]] for h in hops]
    n = len(hops)
    obligations = checker.discharge(langs[n], chain[n], cert,
                                    wall_s=wall_s)
    if obligations is None:
        return None, None
    gap, landed = n, cert
    while gap > 0:
        hop = hops[gap - 1]
        if "cert" not in hop.get("channels", []):
            break
        cert_file = _tmp(json.dumps(landed, sort_keys=True).encode(),
                         ".cert")
        res, same = runner.run_twice(
            os.path.join(hop["_dir"], "lam_cert.py"),
            [cert_file, chain[gap - 1]], wall_s=wall_s)
        if not same or not res.ok:
            break
        try:
            carried = json.loads(res.out)
        except json.JSONDecodeError:
            break
        obl = checker.discharge(langs[gap - 1], chain[gap - 1], carried,
                                wall_s=wall_s)
        if obl is None:
            break
        gap, landed, obligations = gap - 1, carried, obl
    at = question["language"] if gap == 0 else hops[gap - 1]["tgt"]
    return gap, {"at": at, "gap": gap,
                 "schema": landed.get("schema"),
                 "judge": sorted(langs[gap].get("lineage", [])),
                 "obligations": obligations}


def _residual_trust(hops: list[dict], gap: int, judge: dict) -> list[str]:
    """The meet over the gap segment plus the judge that ran: the
    check unburdened the result of everything upstream — the search
    first of all."""
    residual = {x for h in hops[:gap] for x in h.get("lineage", [])}
    residual |= set(judge.get("lineage", []))
    return sorted(residual)


# -- one play of one route -------------------------------------------------

def run_route(reg: dict, route: list[dict], question: dict,
              wall_s: float) -> dict:
    """Run one route; always returns a result record (partial on any
    failure — a route that breaks is evidence, not an exception)."""
    hops, search = route[:-1], route[-1]
    rec = {"question": question["id"],
           "route": [p["id"] for p in hops] + [search["name"]],
           "lineage": _lineage(route),
           "budget": {"wall_s": wall_s, "spent_s": 0.0}}
    # entries running at a revision > 1 say so, so the log's citations
    # stay exact even after a name rebinds (KERNEL.md §10)
    revs = {(p.get("id") or p.get("name")): p["revision"]
            for p in route if p.get("revision", 1) > 1}
    if revs:
        rec["revisions"] = revs

    def partial(note: str, **progress) -> dict:
        rec["value"] = {"kind": "partial",
                        "progress": {"note": note, **progress}}
        rec["grade"], rec["gap"], rec["trust"] = "", None, []
        return rec

    # The obs channel forward: the question's observable must be kept
    # by every hop and composes through the declared maps; the search
    # must target what arrives. Anything else is a partial, never an
    # answer.
    observable = question["observable"]
    for hop in hops:
        if observable not in hop.get("keeps", []):
            return partial(f"{hop['id']} does not keep {observable!r}")
        observable = hop.get("maps", {}).get(observable, observable)
    if observable not in search.get("targets", []):
        return partial(
            f"route cannot target {question['observable']!r}: composed "
            f"observable is {observable!r}, search targets "
            f"{search.get('targets', [])}")

    chain, note = _translate_chain(hops, question["_program_path"], wall_s)
    if chain is None:
        return partial(note)
    program = chain[-1]
    args = [program, question["mode"], observable,
            str(question["bound"]), str(wall_s)]
    hints = _hints(hops, chain, wall_s)
    if hints is not None:
        args.append(hints)
    res, same = runner.run_twice(_exe(search, "solve.py"), args,
                                 wall_s=wall_s * 2 + 10)
    rec["budget"]["spent_s"] = round(res.wall_s, 3)
    if res.timed_out:
        return partial("search exceeded twice the declared wall")
    if not same:
        return partial("search nondeterministic")
    if not res.ok:
        return partial(f"search failed rc={res.rc}",
                       stderr=res.err[:400].decode(errors="replace"))
    try:
        value = json.loads(res.out)
    except json.JSONDecodeError:
        return partial("search output not JSON")
    ledger = _ledger(search, program, value, wall_s)
    if ledger is not None:
        rec["ledger"] = ledger

    if value.get("kind") == "witness":
        # wit: chained home and replayed where the question lives — a
        # witness is certified (gap 0) or it is not a result at all.
        home, depth, note = _witness_home(reg, question, hops, chain,
                                          value.get("payload"), wall_s)
        if home is None:
            return partial(f"witness did not come home: {note}",
                           witness=value.get("payload"))
        rec["value"] = {"kind": "witness", "payload": home, "depth": depth}
        rec["grade"], rec["gap"] = "certified", 0
        rec["trust"] = sorted(
            reg["languages"][question["language"]].get("lineage", []))
    elif value.get("kind") == "all":
        # claim: the checkless channel — every hop must offer it, the
        # bound caps at the meet, and the grade floors at claimed
        # until a certificate checks somewhere (KERNEL.md §4).
        for hop in hops:
            if "claim" not in hop.get("channels", []):
                return partial(f"{hop['id']}: no claim channel",
                               claimed=value)
        rec["value"] = {"kind": "all",
                        "bound": results.cap(
                            value["bound"],
                            [h.get("bound_cap", "inf") for h in hops]),
                        "cert": value.get("cert")}
        gap, disch = (None, None) if value.get("cert") is None else \
            _discharge_chain(reg, question, hops, chain,
                             value["cert"], wall_s)
        if gap is None:
            rec["grade"], rec["gap"] = "claimed", None
            rec["trust"] = rec["lineage"]      # nothing checked: the
            # residual is the whole generated chain, search included
        else:
            rec["grade"] = "certified" if gap == 0 else "checked"
            rec["gap"] = gap
            lang = reg["languages"][question["language"] if gap == 0
                                    else hops[gap - 1]["tgt"]]
            rec["trust"] = _residual_trust(hops, gap, lang)
            rec["discharge"] = disch
    elif value.get("kind") == "partial":
        rec["value"] = value
        rec["grade"], rec["gap"], rec["trust"] = "", None, []
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
                                       f"search reachable from "
                                       f"{q['language']}"}},
                "grade": "", "gap": None, "trust": []})
            continue
        # Enumerate, don't choose: every admitted route plays, so a
        # settled answer can still gain grade (a later route's
        # certificate), gap (a check closer to home), and corroboration
        # (a disjoint lineage agreeing). The wall cap per route is the
        # budget; junk never wins a route because the result order, not
        # arrival, picks the best.
        for route in routes:
            rec = run_route(reg, route, q, wall_s)
            rec["iteration"] = iteration
            results.append(log_path, rec)
    for contra in results.contradictions(bench, results.load(log_path)):
        results.append(log_path, {
            "event": "contradiction", "question": contra["question"],
            "witness_route": contra["witness"]["route"],
            "universal_route": contra["universal"]["route"],
            # the witness stands; the universal's whole chain is marked
            "falsified": contra["universal"].get("lineage", [])})
    return report(run_dir, reg_root)


# -- regrade (the grade-raising replay: check time, not search time) ----------

def regrade(run_dir: str, reg_root: str = "registry", *,
            wall_s: float = _DEFAULT_WALL_S) -> str:
    """Re-discharge stored certificates under the current registry and
    append every strictly improved path (KERNEL.md §5): a `cert`
    carry-back admitted after the fact re-grades the map without
    re-solving it. Values are never touched — only grade, gap, and
    trust can move: grade and gap only up the ladder, because appending
    is the only write and the order ratchets; trust to whatever the
    current registry's judges derive, because a revised judge is a new
    fact about an old certificate."""
    bench = results.load_benchmark(os.path.join(run_dir, "benchmark.json"))
    reg = registry.load(reg_root)
    log_path = os.path.join(run_dir, "log.jsonl")
    questions = {q["id"]: q for q in bench["questions"]}
    bests = results.best(bench, results.load(log_path))
    results.append(log_path, {"event": "regrade"})
    for qid in sorted(bests):
        rec, q = bests[qid], questions[qid]
        value = rec["value"]
        # every stored certificate is re-judged — a certified one too,
        # because a revised judge may now derive a different trust
        if (value.get("kind") != "all" or not value.get("cert")
                or not rec.get("route")):
            continue
        hop_ids, search_id = rec["route"][:-1], rec["route"][-1]
        hops = [reg["pairs"].get(h) for h in hop_ids]
        search = reg["searches"].get(search_id)
        if search is None or any(h is None or "admission" not in h
                                 for h in hops):
            continue
        start = time.monotonic()
        chain, note = _translate_chain(hops, q["_program_path"], wall_s)
        if chain is None:
            continue
        gap, disch = _discharge_chain(reg, q, hops, chain, value["cert"],
                                      wall_s)
        if gap is None:
            continue
        new = {"question": qid, "route": rec["route"],
               "lineage": _lineage(hops + [search]),
               "budget": {"wall_s": wall_s,
                          "spent_s": round(time.monotonic() - start, 3)},
               "value": value, "regrade": True,
               "grade": "certified" if gap == 0 else "checked",
               "gap": gap, "discharge": disch}
        revs = {(p.get("id") or p.get("name")): p["revision"]
                for p in hops + [search] if p.get("revision", 1) > 1}
        if revs:
            new["revisions"] = revs
        lang = reg["languages"][q["language"] if gap == 0
                                else hops[gap - 1]["tgt"]]
        new["trust"] = _residual_trust(hops, gap, lang)
        # a strictly better path, or the same path re-judged with a
        # different residual trust (a revised judge, a revised
        # carry-back): both are new facts about the map, and the
        # board keeps the latest among equals
        if (results.better(q, new, rec)
                or (not results.better(q, rec, new)
                    and sorted(new["trust"]) != sorted(rec.get("trust",
                                                                 [])))):
            results.append(log_path, new)
    return report(run_dir, reg_root)


# -- report, graph, and the printable trusted base ----------------------------

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


def base(reg_root: str = "registry") -> str:
    """The trusted base, printed: every judge — interpreters and
    evidence checkers — with the anchors and controls that corroborate
    it. A list, not a story (KERNEL.md §1): everything not on it is
    untrusted syntax and named so."""
    reg = registry.load(reg_root)
    lines = ["# The trusted base — judges only", ""]
    admitted = [m for m in reg["languages"].values() if "admission" in m]
    if not admitted:
        lines.append("(empty: zero admitted judges — the kernel ships "
                     "this way)")
    for m in sorted(admitted, key=lambda m: m["name"]):
        stamp = m["admission"]
        anchors = sorted(
            f"{d['name']} ({len(d['anchors'])} anchors)"
            for d in reg["domains"].values()
            if "admission" in d and d["root"] == m["name"])
        rev = f"@{m['revision']}" if m.get("revision", 1) > 1 else ""
        anchored = (", ".join(anchors) if anchors else
                    "no domain — corroborated only by its pairs' squares")
        lines.append(
            f"- interpreter `{m['name']}{rev}` — vectors "
            f"{stamp.get('vectors', 0)}, controls "
            f"{stamp.get('controls', 0)}; lineage "
            f"{m.get('lineage', [])}; anchored by {anchored}")
        for schema, ev in sorted(stamp.get("evidence", {}).items()):
            lines.append(f"  - judge `{m['name']}:{schema}` — vectors "
                         f"{ev['vectors']}, controls {ev['controls']}")
    lines += ["", "Everything else in the registry is untrusted syntax: "
              "every transport's output is only ever as good as the "
              "judgment it survives."]
    lines.append("")
    return "\n".join(lines)


# -- admit (the manual mode; the loop's gate is the same call) ---------------

def admit(entry_dir: str, reg_root: str = "registry", *,
          wall_s: float = _DEFAULT_WALL_S) -> dict:
    """A human (or the LLM) writes an entry directory under the
    registry; the kernel adjudicates. Runs the one gate — the
    generation rule, determinism, every declared channel's round-trip
    (or vectors, or corpus discipline), and two-sided controls — and
    stamps the evidence into the manifest. Any failure raises and
    leaves the entry unstamped."""
    entry_dir = os.path.abspath(entry_dir)
    with open(os.path.join(entry_dir, "manifest.json"),
              encoding="utf-8") as fh:
        manifest = json.load(fh)
    evidence = checker.check(registry.load(reg_root), entry_dir, manifest,
                             wall_s=wall_s)
    registry.stamp_admission(entry_dir, evidence)
    return evidence


def main(argv: list[str]) -> int:
    commands = ("play", "report", "graph", "admit", "regrade", "base")
    if argv and argv[0] in commands and (argv[0] == "base"
                                         or len(argv) >= 2):
        kw = {}
        if "--registry" in argv:
            kw["reg_root"] = argv[argv.index("--registry") + 1]
        if "--wall" in argv:
            kw["wall_s"] = float(argv[argv.index("--wall") + 1])
        if argv[0] == "base":
            sys.stdout.write(base(kw.get("reg_root", "registry")))
            return 0
        run_dir = argv[1]
        if argv[0] == "play" and "--only" in argv:
            kw["only"] = {qid for qid in
                          argv[argv.index("--only") + 1].split(",") if qid}
        if argv[0] == "play":
            text = play(run_dir, **kw)
        elif argv[0] == "regrade":
            text = regrade(run_dir, **kw)
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
