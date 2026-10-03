"""The third experiment: which way does a surviving checker fault lean?

A mutant of a certificate checker that the gate does not refuse is
one of three things, and the gate experiment cannot say which: the
same judge, a stricter one — it refuses something the intact checker
discharges, which costs answers and no trust — or a laxer one, which
discharges something the intact checker refuses. Only the last is a
hole in the trusted base.

``probe`` tells them apart against the intact checker, on a pool of
(program, certificate) wider than what admission runs. The pool is
drawn from everything in the tree that holds a certificate of the
checker's form: its vectors and controls; what every bound search at
its language writes on its corpus; the certificates the bound pairs
carry, at the target and carried home; the certificates in the logs
of the pinned runs, direct or carried home over one hop. To these are
added each certificate against programs it was not written for, and
single edits of each certificate — an integer moved by one, a list
element or a dictionary entry dropped. The intact checker judges every
candidate once; what it discharges and what it refuses is the pool's
only label.

Each surviving mutant then judges the refused half until it
discharges one — ``laxer`` — and, if it never does, the discharged
half until it refuses one — ``stricter``; a mutant that agrees with
the intact checker on the whole pool is ``same``, which is a statement
about the pool and not a proof of equivalence. A mutant that keeps
running into the wall is stricter by default: it discharges nothing in
time.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
import time

from kernel import gate, results, runner
from kernel.faults import harness, mutate

#: Candidates the intact checker needs longer than this for are left
#: out: the pool is run once per surviving mutant.
_KEEP_S = 5.0
_ACCEPTED, _REFUSED = 20, 40      # the pool's two halves, at most
_CROSS, _EDITS = 2, 6             # per certificate found in the tree
#: A mutant that has run into the wall or the memory cap this many
#: times discharges nothing in time: stricter, and not asked again.
_GIVE_UP = 3


def _rank(seed: int, text: str) -> str:
    return hashlib.sha256(f"{seed}:{text}".encode()).hexdigest()


def _load(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# -- certificates the tree holds ----------------------------------------------

def _keep(scratch: str, data: bytes) -> str:
    """A program that must outlive the temporary directory."""
    path = os.path.join(scratch, "pool",
                        hashlib.sha256(data).hexdigest()[:16] + ".program")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def _carried(pair: dict, cert: dict, program: str) -> dict | None:
    """``cert`` carried home over ``pair`` for ``program``, or None."""
    fd, path = tempfile.mkstemp(suffix=".cert")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(cert, fh, sort_keys=True)
    res = runner.run_exe(os.path.join(pair["_dir"], "lam_cert.py"),
                         [path, program], wall_s=harness.WALL_S)
    try:
        out = json.loads(res.out) if res.ok else None
    except json.JSONDecodeError:
        return None
    return out if isinstance(out, dict) else None


def _found(reg: dict, runs_root: str, lang: str, schema: str, base: str,
           scratch: str) -> list[tuple[str, str, object]]:
    """(name, program, payload) for every certificate of ``schema`` at
    ``lang`` the tree holds, each (program, payload) once."""
    raw: list[tuple[str, str, object]] = []

    def take(name: str, program: str, cert) -> None:
        if isinstance(cert, dict) and cert.get("schema") == schema:
            raw.append((name, program, cert.get("payload")))

    for prog in gate._items(base, "vectors", "program"):
        stem = os.path.basename(prog)[:-len(".program")]
        raw.append((f"vector/{stem}", prog,
                    _load(prog[:-len(".program")] + ".cert")))
        control = os.path.join(base, "controls", stem + ".cert")
        if os.path.isfile(control):
            raw.append((f"control/{stem}", prog, _load(control)))
    for name, sm in sorted(reg["searches"].items()):
        if sm["language"] != lang:
            continue
        for prog in gate._items(sm["_dir"], "corpus", "program"):
            q = _load(prog[:-len(".program")] + ".q")
            try:
                value = gate._solve(os.path.join(sm["_dir"], "solve.py"),
                                    prog, q, harness.WALL_S)
            except gate.AdmissionError:
                continue
            take(f"{name}/{os.path.basename(prog)[:-len('.program')]}",
                 prog, value.get("cert"))
    for pid, pm in sorted(reg["pairs"].items()):
        if "cert" not in pm.get("channels", []):
            continue
        for prog in gate._items(pm["_dir"], "corpus", "program"):
            cert_file = prog[:-len(".program")] + ".cert"
            if not os.path.isfile(cert_file):
                continue
            stem = os.path.basename(prog)[:-len(".program")]
            cert = _load(cert_file)
            if pm["tgt"] == lang:
                res = runner.run_exe(os.path.join(pm["_dir"], "T.py"),
                                     [prog], wall_s=harness.WALL_S)
                if res.ok:
                    take(f"{pid}/{stem}", _keep(scratch, res.out), cert)
            if pm["src"] == lang:
                take(f"{pid}/{stem}/home", prog, _carried(pm, cert, prog))
    for run in sorted(os.listdir(runs_root)):
        bench_path = os.path.join(runs_root, run, "benchmark.json")
        if not os.path.isfile(bench_path):
            continue
        questions = {q["id"]: q for q in
                     results.load_benchmark(bench_path)["questions"]}
        for rec in results.load(os.path.join(runs_root, run, "log.jsonl")):
            q = questions.get(rec.get("question"))
            cert = (rec.get("value") or {}).get("cert")
            if q is None or cert is None or q["language"] != lang:
                continue
            route, name = rec["route"], f"{run}/{rec['question']}"
            if len(route) == 1:
                take(name, q["_program_path"], cert)
            elif len(route) == 2 and "cert" in reg["pairs"].get(
                    route[0], {}).get("channels", []):
                take(f"{name}/home", q["_program_path"], _carried(
                    reg["pairs"][route[0]], cert, q["_program_path"]))
    seen, once = set(), []
    for name, program, payload in raw:
        with open(program, "rb") as fh:
            key = (hashlib.sha256(fh.read()).hexdigest(),
                   json.dumps(payload, sort_keys=True))
        if key not in seen:
            seen.add(key)
            once.append((name, program, payload))
    return once


# -- single edits of a certificate --------------------------------------------

def _edits(payload) -> list[tuple[str, object]]:
    """Every single edit of a JSON value: an integer moved by one
    either way, a list element dropped, a dictionary entry dropped."""
    out: list[tuple[str, object]] = []

    def walk(node, path: tuple) -> None:
        def edited(change) -> object:
            root = copy.deepcopy(payload)
            parent, here = None, root
            for step in path:
                parent, here = here, here[step]
            new = change(here)
            if parent is None:
                return new
            parent[path[-1]] = new
            return root
        where = "/".join(str(p) for p in path)
        if isinstance(node, bool):
            return
        if isinstance(node, int):
            out.append((f"{where}+1", edited(lambda v: v + 1)))
            out.append((f"{where}-1", edited(lambda v: v - 1)))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                out.append((f"{where}/drop{i}",
                            edited(lambda v, i=i: v[:i] + v[i + 1:])))
                walk(item, path + (i,))
        elif isinstance(node, dict):
            for k in sorted(node):
                out.append((f"{where}/drop:{k}", edited(
                    lambda v, k=k: {a: b for a, b in v.items() if a != k})))
                walk(node[k], path + (k,))
    walk(payload, ())
    return out


# -- the experiment -----------------------------------------------------------

def _survivors(gate_results: str, t: dict, seed: int) -> list[dict]:
    with open(gate_results, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]
    return [r for r in records if r.get("outcome") == "survived"
            and (r["entry"], r["file"], r["seed"]) == (
                t["entry"], t["file"], seed)]


def probe_target(reg_root: str, reg: dict, t: dict, seed: int, out: str,
                 gate_results: str, runs_root: str = "runs") -> None:
    """Class every mutant of one checker the gate experiment recorded
    as surviving; append one record each."""
    what = f"{t['entry']}/{t['file']}"
    lang, schema = t["key"], t["file"].split("/")[1]
    scratch = tempfile.mkdtemp(prefix="faults-")
    saved_run, saved_tmp = runner.run, tempfile.tempdir
    try:
        staged = harness.stage(reg_root, t, scratch)
        path = os.path.join(staged, t["file"])
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        probe = harness.Probe(path)
        runner.run = probe
        judge = {"_dir": staged}

        def discharges(item) -> bool:
            return gate.discharge(
                judge, item["program"],
                {"schema": schema, "payload": item["payload"]},
                wall_s=harness.WALL_S) is not None

        harness.fresh_tmp(scratch)
        found = _found(reg, runs_root, lang, schema,
                       os.path.join(staged, "evidence", schema), scratch)
        candidates = [{"name": n, "program": p, "payload": c}
                      for n, p, c in found]
        programs = sorted({p for _, p, _ in found})
        for name, program, payload in found:
            others = sorted((p for p in programs if p != program),
                            key=lambda p: _rank(seed, name + p))[:_CROSS]
            candidates += [{"name": f"{name}@{os.path.basename(p)}",
                            "program": p, "payload": payload}
                           for p in others]
            edits = sorted(_edits(payload),
                           key=lambda e: _rank(seed, name + e[0]))[:_EDITS]
            candidates += [{"name": f"{name}~{label}", "program": program,
                            "payload": edit} for label, edit in edits]
        pool, slowest = [], 0.0
        for item in candidates:
            start = time.monotonic()
            item["ok"] = discharges(item)
            spent = time.monotonic() - start
            if spent <= _KEEP_S:
                pool.append(item)
                slowest = max(slowest, spent)

        def half(ok: bool, cap: int) -> list[dict]:
            # the shipped vectors and controls always; the rest by rank
            mine = sorted((i for i in pool if i["ok"] is ok),
                          key=lambda i: (not i["name"].startswith(
                              ("vector/", "control/")) or "~" in i["name"]
                              or "@" in i["name"],
                              _rank(seed, i["name"])))
            return mine[:cap]
        accepted, refused = half(True, _ACCEPTED), half(False, _REFUSED)
        probe.learning = False
        # the wall is the checker's own on this pool, not the searches'
        # that wrote the certificates
        probe.cap = max(20.0, round(8 * slowest, 1))

        with open(path, "w", encoding="utf-8") as fh:
            fh.write(mutate.identity(source))
        harness.fresh_tmp(scratch)
        probe.reset()
        if any(discharges(i) != i["ok"] for i in accepted + refused):
            raise SystemExit(f"{what}: the identity mutant disagrees with "
                             "the intact checker on the pool")

        by_site = {(s.node, s.alt): s for s in mutate.sites(source)}
        survivors = _survivors(gate_results, t, seed)
        done = harness.done(out, t["entry"], t["file"], seed)
        if not done:
            harness.append(out, {
                "event": "target", "entry": t["entry"], "file": t["file"],
                "role": t["role"], "seed": seed, "probe": True,
                "found": len(found), "candidates": len(candidates),
                "survivors": len(survivors), "cap_s": probe.cap,
                "accepted": [i["name"] for i in accepted],
                "refused": [i["name"] for i in refused]})
        for n, r in enumerate(survivors):
            if (r["node"], r["alt"]) in done:
                continue
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(mutate.mutant(source, by_site[(r["node"],
                                                        r["alt"])]))
            harness.fresh_tmp(scratch)
            probe.reset()
            start = time.monotonic()
            lean, on = "same", None
            for item in refused:
                if discharges(item):
                    lean, on = "laxer", item["name"]
                    break
                if probe.timeouts + probe.bloats >= _GIVE_UP:
                    lean, on = "stricter", "wall"
                    break
            if lean == "same":
                for item in accepted:
                    if not discharges(item):
                        lean, on = "stricter", item["name"]
                        break
            harness.append(out, {
                "entry": t["entry"], "file": t["file"], "role": t["role"],
                "seed": seed, "node": r["node"], "alt": r["alt"],
                "op": r["op"], "detail": r["detail"], "line": r["line"],
                "cover": r["cover"], "lean": lean, "on": on,
                "seconds": round(time.monotonic() - start, 1)})
            harness.say(f"{what} {n + 1}/{len(survivors)} "
                        f"{r['op']}@{r['line']}: {lean}")
    finally:
        runner.run, tempfile.tempdir = saved_run, saved_tmp
        shutil.rmtree(scratch, ignore_errors=True)


# -- the report ---------------------------------------------------------------

def result_files() -> list[str]:
    return sorted(os.path.join(harness.RESULTS, f)
                  for f in os.listdir(harness.RESULTS)
                  if f.startswith("probe-") and f.endswith(".jsonl"))


def report(paths: list[str]) -> str:
    """One row per checker: its surviving mutants by the way they
    lean, and the pool they were held against."""
    heads, rows = {}, {}
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                key = (r["entry"], r["file"])
                if r.get("probe"):
                    heads[key] = r
                elif "lean" in r:
                    rows.setdefault(key, []).append(r)
    if not rows:
        return ""
    out = ["| checker | pool (discharged + refused) | survivors | same | "
           "stricter | laxer | laxer on executed lines |",
           "|---|---|---|---|---|---|---|"]
    for key in sorted(rows):
        rs, h = rows[key], heads.get(key, {})
        count = lambda lean: sum(1 for r in rs if r["lean"] == lean)
        pool = (f"{len(h['accepted'])} + {len(h['refused'])}"
                if h else "?")
        out.append(
            f"| `{key[0]}/{key[1]}` | {pool} | {len(rs)} | {count('same')} "
            f"| {count('stricter')} | {count('laxer')} | "
            f"{sum(1 for r in rs if r['lean'] == 'laxer' and r['cover'])} |")
    return "\n".join(out) + "\n"
