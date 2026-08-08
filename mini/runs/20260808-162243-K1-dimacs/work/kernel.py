#!/usr/bin/env python3
"""K1 — the current kernel's concepts at minimal implementation size.

One file. The concepts are the contract's (CONTRACT.md); the mechanism
probes here: one registry namespace (registry/<id>/entry.json), and
admission evidence as an append-only gate-log event, never a manifest
stamp. The agent never writes a result; this kernel does, by running
checked code.
"""

import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

WALL_S = 60.0
_INF = 10 ** 18
GRADES = {"": 0, "claimed": 1, "checked": 2, "certified": 3, "replayed": 3}


# ---------------------------------------------------------------- running

def _run(script, args, wall):
    env = {k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ}
    with tempfile.TemporaryDirectory() as scratch:
        t0 = time.monotonic()
        try:
            p = subprocess.run([sys.executable, script, *args],
                               capture_output=True, timeout=wall,
                               cwd=scratch, env=env)
            return p.stdout, p.returncode, time.monotonic() - t0, False
        except subprocess.TimeoutExpired:
            return b"", None, time.monotonic() - t0, True


def run_twice(script, args, wall=WALL_S):
    """Determinism is measured, not declared: same invocation twice,
    stdout byte-compared."""
    out1, rc1, spent, to1 = _run(script, args, wall)
    if to1:
        return None, spent
    out2, rc2, _, to2 = _run(script, args, wall)
    if to2 or out1 != out2 or rc1 != rc2 or rc1 != 0:
        return None, spent
    return out1, spent


def _jrun(script, args, wall=WALL_S):
    out, spent = run_twice(script, args, wall)
    if out is None:
        return None, spent
    try:
        return json.loads(out), spent
    except json.JSONDecodeError:
        return None, spent


def _tmp(data, suffix):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode())
    return path


# --------------------------------------------------------------- registry

def load_registry(root):
    reg = {}
    for d in sorted(glob.glob(os.path.join(os.path.abspath(root), "*"))):
        mpath = os.path.join(d, "entry.json")
        if os.path.isfile(mpath):
            with open(mpath, encoding="utf-8") as fh:
                e = json.load(fh)
            e["_dir"], e["id"] = d, os.path.basename(d)
            reg[e["id"]] = e
    return reg


def gate_log(root):
    return os.path.join(root, "gate.jsonl")


def admitted(root):
    ok = set()
    if os.path.exists(gate_log(root)):
        with open(gate_log(root), encoding="utf-8") as fh:
            for line in fh:
                ev = json.loads(line)
                (ok.add if ev["event"] == "admitted" else ok.discard)(
                    ev["id"])
    return ok


def append(path, record):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


# ------------------------------------------------------------------- gate

class GateError(Exception):
    pass


def _mutants(d, pat="mutants/*.py"):
    return sorted(glob.glob(os.path.join(d, pat)))


def interpret(lang, program, input_path, wall=WALL_S):
    obs, _ = _jrun(os.path.join(lang["_dir"], "interp.py"),
                   [program, input_path], wall)
    if obs is None:
        raise GateError(f"{lang['id']}: interp failed or nondeterministic")
    return obs


def _vectors_ok(d, interp, wall):
    vecs = sorted(glob.glob(os.path.join(d, "vectors", "*.program")))
    for prog in vecs:
        stem = prog[:-len(".program")]
        with open(stem + ".expect", encoding="utf-8") as fh:
            expect = json.load(fh)
        obs, _ = _jrun(interp, [prog, stem + ".input"], wall)
        if obs is None:
            raise GateError(f"{interp}: failed on {os.path.basename(prog)}")
        for k, v in expect.items():
            if obs.get(k) != v:
                raise GateError(f"{os.path.basename(prog)}: {k}="
                                f"{obs.get(k)!r}, expected {v!r}")
    return len(vecs)


def _two_sided(d, n, check_one):
    """The falsifiability rule: >=1 item passed, and every mutant must
    fail the same check."""
    if n == 0:
        raise GateError(f"{d}: nothing checked")
    muts = _mutants(d)
    if not muts:
        raise GateError(f"{d}: no mutants — unfalsifiable")
    for m in muts:
        try:
            check_one(m)
        except GateError:
            continue
        raise GateError(f"{m} passed — the corpus cannot catch a defect")
    return len(muts)


def _carry_obs(entry, tgt_obs, wall):
    """Lambda on observables: the executable carry-back when shipped,
    the declared renaming otherwise; when both, they must agree."""
    maps = entry.get("maps") or {}
    lam_obs = os.path.join(entry["_dir"], "lam_obs.py")
    if os.path.exists(lam_obs):
        carried, _ = _jrun(lam_obs, [_tmp(json.dumps(tgt_obs, sort_keys=True),
                                          ".obs")], wall)
        if carried is None:
            raise GateError(f"{lam_obs}: failed or nondeterministic")
        for s, t in maps.items():
            if carried.get(s) != tgt_obs.get(t):
                raise GateError(f"map {s!r}->{t!r} disagrees with lam_obs")
        return carried
    if maps:
        carried = dict(tgt_obs)
        carried.update({s: tgt_obs.get(t) for s, t in maps.items()})
        return carried
    return tgt_obs


def _square(entry, translate, reg, prog, input_path, wall):
    src, tgt = reg[entry["src"]], reg[entry["tgt"]]
    out, _ = run_twice(translate, [prog], wall)
    if out is None:
        raise GateError(f"{translate}: failed or nondeterministic")
    src_obs = interpret(src, prog, input_path, wall)
    carried = _carry_obs(entry, interpret(tgt, _tmp(out, ".program"),
                                          input_path, wall), wall)
    for k in entry["keeps"]:
        s, t = src_obs.get(k), carried.get(k)
        ok = {"exact": s == t,
              "over": s == t if not isinstance(s, bool) else (t or not s),
              "under": s == t if not isinstance(s, bool) else (s or not t),
              }[entry["direction"]]
        if not ok:
            raise GateError(f"square broken on {k!r}: {s!r} vs {t!r}")


def certify_witness(lang, solver, program, observable, payload, hops=(),
                    programs=None, wall=WALL_S):
    """Existential certification: Lambda then replay at the source.
    Fail-safe — any error refutes the witness, never the answer."""
    programs = programs or [program]
    try:
        inp = _tmp(json.dumps(payload, sort_keys=True), ".payload")
        lam = os.path.join(solver["_dir"], "lam.py")
        if os.path.exists(lam):
            out, _ = run_twice(lam, [inp, programs[-1]], wall)
            if out is None:
                return False, 0
            inp = _tmp(out, ".input")
        for i, hop in reversed(list(enumerate(hops))):
            hop_lam = os.path.join(hop["_dir"], "lam.py")
            if not os.path.exists(hop_lam):
                return False, 0
            out, _ = run_twice(hop_lam, [inp, programs[i]], wall)
            if out is None:
                return False, 0
            inp = _tmp(out, ".input")
        obs = interpret(lang, program, inp, wall)
        return bool(obs.get(observable)), int(obs.get("depth", 0))
    except GateError:
        return False, 0


def discharge(solver, program, cert, wall=WALL_S):
    """Universal certification: the pair's checker run by the kernel.
    Fail-safe — a wrong certificate can only fail to upgrade."""
    script = os.path.join(solver["_dir"], "discharge.py")
    if cert is None or not os.path.exists(script):
        return None
    out, _ = _jrun(script, [program,
                            _tmp(json.dumps(cert, sort_keys=True), ".cert")],
                   wall)
    if out is None or out.get("ok") is not True:
        return None
    return out.get("obligations", {})


def _solver_corpus(reg, entry, solve, wall):
    src = reg[entry["src"]]
    corpus = sorted(glob.glob(os.path.join(entry["_dir"], "corpus",
                                           "*.program")))
    if not corpus:
        raise GateError(f"{entry['id']}: empty corpus")
    decided = discharged = 0
    cert_prog = None
    for prog in corpus:
        with open(prog[:-len(".program")] + ".q", encoding="utf-8") as fh:
            q = json.load(fh)
        value, _ = _jrun(solve, [prog, q["mode"], q["observable"],
                                 str(q["bound"]), str(wall)], wall * 2 + 10)
        if value is None:
            raise GateError(f"{prog}: solve failed or nondeterministic")
        name = os.path.basename(prog)
        if value["kind"] == "witness":
            fired, _ = certify_witness(src, entry, prog, q["observable"],
                                       value.get("payload"), wall=wall)
            if not fired:
                raise GateError(f"{name}: witness did not replay")
            if q.get("label") is False:
                raise GateError(f"{name}: witness against label=false")
            decided += 1
        elif value["kind"] == "all":
            if q.get("label") is True and covers(value["bound"], q["bound"]):
                raise GateError(f"{name}: all({value['bound']}) against "
                                "label=true")
            if value.get("cert") is not None:
                if discharge(entry, prog, value["cert"], wall) is None:
                    raise GateError(f"{name}: certificate did not discharge")
                discharged += 1
                cert_prog = cert_prog or prog
            decided += 1
        elif value["kind"] != "partial":
            raise GateError(f"{name}: unknown kind {value['kind']!r}")
    if decided == 0:
        raise GateError(f"{entry['id']}: abstained on the whole corpus")
    return len(corpus), discharged, cert_prog


def gate(root, entry_id, wall=WALL_S):
    reg = load_registry(root)
    entry = reg[entry_id]
    d = entry["_dir"]
    if entry["kind"] == "language":
        n = _vectors_ok(d, os.path.join(d, "interp.py"), wall)
        controls = _two_sided(d, n, lambda m: _vectors_ok(d, m, wall))
        evidence = {"vectors": n, "mutants": controls}
    elif entry["kind"] == "translation":
        corpus = sorted(glob.glob(os.path.join(d, "corpus", "*.program")))
        if not corpus:
            raise GateError(f"{entry_id}: empty corpus")
        empty = _tmp(b"{}", ".input")

        def square_all(translate):
            broken = None
            for prog in corpus:
                ipath = prog[:-len(".program")] + ".input"
                try:
                    _square(entry, translate, reg, prog,
                            ipath if os.path.exists(ipath) else empty, wall)
                except GateError as exc:
                    broken = exc
            if broken:
                raise broken
        square_all(os.path.join(d, "T.py"))
        controls = _two_sided(d, len(corpus), square_all)
        evidence = {"corpus": len(corpus), "mutants": controls}
    elif entry["kind"] == "solver":
        n, discharged, cert_prog = _solver_corpus(
            reg, entry, os.path.join(d, "solve.py"), wall)
        controls = _two_sided(
            d, n, lambda m: _solver_corpus(reg, entry, m, wall))
        evidence = {"corpus": n, "mutants": controls}
        if os.path.exists(os.path.join(d, "discharge.py")):
            if discharged == 0:
                raise GateError(f"{entry_id}: discharge never exercised")
            cms = sorted(glob.glob(os.path.join(d, "cert_mutants",
                                                "*.json")))
            if not cms:
                raise GateError(f"{entry_id}: no certificate mutants")
            for cm in cms:
                with open(cm, encoding="utf-8") as fh:
                    if discharge(entry, cert_prog, json.load(fh),
                                 wall) is not None:
                        raise GateError(f"{cm} discharged — the checker "
                                        "cannot catch a wrong certificate")
            evidence.update(discharged=discharged, cert_mutants=len(cms))
    else:
        raise GateError(f"{entry_id}: unknown kind {entry['kind']!r}")
    append(gate_log(root), {"event": "admitted", "id": entry_id,
                            "evidence": evidence})
    return evidence


# ---------------------------------------------------------------- results

def _bkey(bound):
    return _INF if bound == "inf" else int(bound)


def covers(bound, ask):
    return _bkey(bound) >= _bkey(ask)


def cap(bound, caps):
    b = min([_bkey(bound)] + [_bkey(c) for c in caps])
    return "inf" if b >= _INF else b


def terminal(q, value):
    if value["kind"] == "witness":
        return True
    return value["kind"] == "all" and covers(value["bound"], q["bound"])


def key(q, rec):
    v = rec["value"]
    if terminal(q, v):
        level = 2
        bound = _INF if v["kind"] == "witness" else _bkey(v["bound"])
    elif v["kind"] == "all":
        level, bound = 1, _bkey(v["bound"])
    else:
        level, bound = 0, int(v.get("progress", {}).get("bound_reached", -1))
    return (level, bound, GRADES[rec.get("grade", "")])


def load_benchmark(path):
    with open(path, encoding="utf-8") as fh:
        bench = json.load(fh)
    base = os.path.dirname(os.path.abspath(path))
    for q in bench["questions"]:
        p = os.path.join(base, q["program"])
        with open(p, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        if digest != q["sha256"]:
            raise SystemExit(f"pin violated: {q['id']}")
        q["_program"] = p
    return bench


def load_log(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def best(bench, records):
    qs = {q["id"]: q for q in bench["questions"]}
    out = {}
    for rec in records:
        qid = rec.get("question")
        if qid in qs and "value" in rec and (
                qid not in out or key(qs[qid], rec) > key(qs[qid], out[qid])):
            out[qid] = rec
    return out


def corroborated(bench, records):
    qs = {q["id"]: q for q in bench["questions"]}
    bests, out = best(bench, records), set()
    for qid, rec in bests.items():
        q = qs[qid]
        if not terminal(q, rec["value"]):
            continue
        pool = [set(r["lineage"]) for r in records
                if r.get("question") == qid and "value" in r
                and r.get("lineage") and r["value"]["kind"] ==
                rec["value"]["kind"] and terminal(q, r["value"])]
        if any(not (a & b) for i, a in enumerate(pool) for b in pool[i + 1:]):
            out.add(qid)
    return out


def contradictions(bench, records):
    qs = {q["id"]: q for q in bench["questions"]}
    found = []
    for qid in qs:
        recs = [r for r in records if r.get("question") == qid
                and "value" in r]
        for w in (r for r in recs if r["value"]["kind"] == "witness"):
            for u in (r for r in recs if r["value"]["kind"] == "all"):
                if covers(u["value"]["bound"], int(w["value"].get("depth",
                                                                  0))):
                    found.append({"question": qid, "witness": w["route"],
                                  "universal": u["route"]})
    return found


def report(bench, records):
    bests = best(bench, records)
    qs = bench["questions"]
    open_qs = [q["id"] for q in qs if q["id"] not in bests
               or not terminal(q, bests[q["id"]]["value"])]
    corrob = corroborated(bench, records)
    lines = [f"# Frontier — `{bench['name']}`", "",
             f"{len(qs) - len(open_qs)} of {len(qs)} terminal; "
             f"frontier holds {len(open_qs)}.", "",
             "| question | best | grade | route |", "|---|---|---|---|"]
    for q in sorted(qs, key=lambda q: q["id"]):
        rec = bests.get(q["id"])
        if rec is None:
            lines.append(f"| {q['id']} | — unplayed | | |")
            continue
        v = rec["value"]
        show = (f"witness (depth {v.get('depth', '?')})"
                if v["kind"] == "witness"
                else f"all (bound {v['bound']})" if v["kind"] == "all"
                else f"partial ({v.get('progress', {}).get('note', '')})")
        grade = rec.get("grade", "") + (
            " +corroborated" if q["id"] in corrob else "")
        lines.append(f"| {q['id']} | {show} | {grade} "
                     f"| {'>'.join(rec.get('route', []))} |")
    if open_qs:
        lines += ["", "## The frontier", ""]
        for qid in sorted(open_qs):
            rec = bests.get(qid)
            ev = (json.dumps(rec["value"].get("progress",
                                              rec["value"]), sort_keys=True)
                  if rec else "unplayed")
            lines.append(f"- `{qid}` — {ev}")
    for c in contradictions(bench, records):
        lines.append(f"- CONTRADICTION on `{c['question']}`: "
                     f"{'>'.join(c['witness'])} vs "
                     f"{'>'.join(c['universal'])}")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------- play

def routes(reg, ok, language, max_hops=2):
    hops_t = [e for e in reg.values() if e["kind"] == "translation"
              and e["id"] in ok]
    solvers = [e for e in reg.values() if e["kind"] == "solver"
               and e["id"] in ok]
    out, frontier = [], [(language, [])]
    for _ in range(max_hops + 1):
        nxt = []
        for lang, hops in frontier:
            out += [hops + [s] for s in sorted(solvers,
                                               key=lambda e: e["id"])
                    if s["src"] == lang]
            nxt += [(t["tgt"], hops + [t])
                    for t in sorted(hops_t, key=lambda e: e["id"])
                    if t["src"] == lang
                    and t["id"] not in [h["id"] for h in hops]]
        frontier = nxt
    return out


def run_route(reg, route, q, wall):
    hops, solver = route[:-1], route[-1]
    rec = {"question": q["id"], "route": [e["id"] for e in route],
           "lineage": sorted({x for e in route
                              for x in e.get("lineage", [])})}

    def partial(note, **kw):
        rec.update(value={"kind": "partial",
                          "progress": {"note": note, **kw}}, grade="")
        return rec

    obs = q["observable"]
    for hop in hops:
        obs = hop.get("maps", {}).get(obs, obs)
    if obs not in solver.get("decides", []):
        return partial(f"route cannot decide {q['observable']!r}")
    chain, t0 = [q["_program"]], time.monotonic()
    for hop in hops:
        out, _ = run_twice(os.path.join(hop["_dir"], "T.py"), [chain[-1]],
                           wall)
        if out is None:
            return partial(f"{hop['id']}: translation failed")
        chain.append(_tmp(out, ".program"))
    value, spent = _jrun(os.path.join(solver["_dir"], "solve.py"),
                         [chain[-1], q["mode"], obs, str(q["bound"]),
                          str(wall)], wall * 2 + 10)
    rec["spent_s"] = round(time.monotonic() - t0, 3)
    if value is None:
        return partial("solver failed or nondeterministic")
    if value.get("kind") == "witness":
        fired, depth = certify_witness(
            reg[q["language"]], solver, q["_program"], q["observable"],
            value.get("payload"), hops, chain, wall)
        if not fired:
            return partial("witness did not replay",
                           witness=value.get("payload"))
        rec.update(value={"kind": "witness", "payload": value["payload"],
                          "depth": depth}, grade="replayed")
    elif value.get("kind") == "all":
        if any(h.get("direction") not in ("exact", "over") for h in hops):
            return partial("universal cannot cross an under-hop")
        rec.update(value={"kind": "all",
                          "bound": cap(value["bound"],
                                       [h.get("bound_cap", "inf")
                                        for h in hops]),
                          "cert": value.get("cert")}, grade="claimed")
        obligations = discharge(solver, chain[-1], value.get("cert"), wall)
        if obligations is not None:
            rec["grade"] = "certified" if not hops else "checked"
            rec["discharge"] = obligations
    elif value.get("kind") == "partial":
        rec.update(value=value, grade="")
    else:
        return partial(f"unknown kind {value.get('kind')!r}")
    return rec


def play(run_dir, root, wall=WALL_S):
    bench = load_benchmark(os.path.join(run_dir, "benchmark.json"))
    reg, ok = load_registry(root), admitted(root)
    log = os.path.join(run_dir, "log.jsonl")
    append(log, {"event": "play", "wall_s": wall})
    for q in bench["questions"]:
        rs = routes(reg, ok, q["language"])
        if not rs:
            append(log, {"question": q["id"], "route": [], "grade": "",
                         "value": {"kind": "partial",
                                   "progress": {"note": "no route"}}})
        for route in rs:
            append(log, run_route(reg, route, q, wall))
    text = report(bench, load_log(log))
    with open(os.path.join(run_dir, "frontier.md"), "w",
              encoding="utf-8") as fh:
        fh.write(text)
    return text


def main(argv):
    cmd = argv[0] if argv else ""
    root = argv[argv.index("--registry") + 1] if "--registry" in argv \
        else "registry"
    wall = float(argv[argv.index("--wall") + 1]) if "--wall" in argv \
        else WALL_S
    if cmd == "gate":
        try:
            print(json.dumps(gate(root, argv[1], wall), sort_keys=True))
        except GateError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
    elif cmd == "play":
        sys.stdout.write(play(argv[1], root, wall))
    elif cmd == "report":
        bench = load_benchmark(os.path.join(argv[1], "benchmark.json"))
        sys.stdout.write(report(bench, load_log(
            os.path.join(argv[1], "log.jsonl"))))
    else:
        print("usage: kernel.py gate <entry-id> | play <run-dir> | "
              "report <run-dir>  [--registry DIR] [--wall S]",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
