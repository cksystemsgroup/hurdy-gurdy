"""The second experiment: what can a fault the gate never saw do to
an answer?

Here the gate is taken away. Every sampled mutant of a transport — a
translator, a carry-back, a map, a search — is put where the intact
file stood and *played*: ``driver.run_route`` runs the routes through
the mutated entry on questions whose answer is known, exactly as a
play would, and nothing is admitted first. Each record the kernel
writes is then held against the truth:

- ``same``    the order key of the intact route's record
- ``lost``    a weaker record, nothing wrong in it: a partial where
              the intact route answered, a smaller bound, a lower
              grade
- ``gained``  a stronger record, nothing wrong in it
- ``wrong``   the record settles the question the other way — a
              universal claim covering the ask on a question with a
              known witness, or a witness within the bound a question
              is known safe to — filed under the grade it carries

The design predicts the last line (KERNEL.md §4): a transport is
untrusted, so a wrong record can be ``claimed``, and it can be
``checked`` at a positive gap with the faulty entry inside the gap —
but it is never ``certified``, and its residual always names the
entry that was wrong. ``blamed`` records the second half per wrong
record: whether the residual holds the mutated entry's whole lineage.

The truth of a question is not the mutant's to state. A search's
corpus question carries its label; a question of a pinned run is used
only where the board holds a replayed witness (unsafe) or a universal
answer certified at gap 0 that covers the ask (safe). The mutated
entry's accelerator, if it has one, is set aside so that the mutated
reference is what runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time

from kernel import driver, results, runner
from kernel.faults import harness, mutate

#: The wall a played route gets. Questions are chosen for being cheap
#: on the intact route, so this is slack, not budget.
_PLAY_WALL_S = 5.0
#: A (question, route) is kept only if the intact route's search spends
#: no more than this many seconds on it.
_KEEP_S = 2.0
#: The cheapest unsafe and the cheapest safe questions taken per run.
_PER_RUN = 6


# -- questions whose answer is known ------------------------------------------

def _corpus_questions(reg: dict) -> list[dict]:
    """The labelled questions every bound search ships as its corpus."""
    found = []
    for name, sm in sorted(reg["searches"].items()):
        base = os.path.join(sm["_dir"], "corpus")
        for fn in sorted(os.listdir(base)):
            if not fn.endswith(".q"):
                continue
            with open(os.path.join(base, fn), encoding="utf-8") as fh:
                q = json.load(fh)
            if not isinstance(q.get("label"), bool):
                continue
            found.append({
                "id": f"{name}/{fn[:-2]}", "language": sm["language"],
                "mode": q["mode"], "observable": q["observable"],
                "bound": q["bound"],
                "truth": "unsafe" if q["label"] else "safe",
                "_program_path": os.path.join(base, fn[:-2] + ".program")})
    return found


def _run_questions(runs_root: str) -> list[dict]:
    """Per pinned run, the cheapest questions the board has judged:
    a replayed witness says unsafe, a covering universal answer
    certified at gap 0 says safe."""
    found = []
    for run in sorted(os.listdir(runs_root)):
        bench_path = os.path.join(runs_root, run, "benchmark.json")
        if not os.path.isfile(bench_path):
            continue
        bench = results.load_benchmark(bench_path)
        log = results.load(os.path.join(runs_root, run, "log.jsonl"))
        best = results.best(bench, log)
        cheapest: dict[str, float] = {}
        for rec in log:
            if "value" in rec and rec.get("grade") == "certified":
                spent = rec["budget"]["spent_s"]
                qid = rec["question"]
                cheapest[qid] = min(cheapest.get(qid, spent), spent)
        by_truth: dict[str, list] = {"unsafe": [], "safe": []}
        for q in bench["questions"]:
            rec = best.get(q["id"])
            if rec is None or rec.get("grade") != "certified":
                continue
            if not results.settled(q, rec["value"]):
                continue
            truth = "unsafe" if rec["value"]["kind"] == "witness" else "safe"
            by_truth[truth].append((cheapest[q["id"]], q["id"], dict(
                q, id=f"{run}/{q['id']}", truth=truth)))
        for truth in ("unsafe", "safe"):
            found += [q for _, _, q in sorted(
                by_truth[truth], key=lambda x: x[:2])[:_PER_RUN]]
    return found


# -- one record against the truth ---------------------------------------------

def _show(rec: dict) -> str:
    v = rec["value"]
    if v["kind"] == "witness":
        return f"witness@{v.get('depth')}"
    if v["kind"] == "all":
        return f"all({v['bound']})"
    return "partial"


def verdict(q: dict, intact: dict, rec: dict) -> str:
    v = rec["value"]
    if q["truth"] == "unsafe" and v["kind"] == "all" \
            and results.covers(v["bound"], q["bound"]):
        return f"wrong-{rec.get('grade') or 'ungraded'}"
    if q["truth"] == "safe" and v["kind"] == "witness" \
            and results.covers(q["bound"], int(v.get("depth", 0))):
        # the kernel's own rule for a contradiction: a witness beside
        # a universal covering its depth. A witness deeper than the
        # bound a question is known safe to contradicts nothing.
        return f"wrong-{rec.get('grade') or 'ungraded'}"
    mine, theirs = results.key(q, rec), results.key(q, intact)
    return "same" if mine == theirs else "lost" if mine < theirs \
        else "gained"


# -- the experiment -----------------------------------------------------------

def _pick(kept: list[tuple], k: int, seed: int) -> list[tuple]:
    """``k`` of the kept (question, route, intact record), in turn
    from four kinds so that a wrong answer has somewhere to show:
    unsafe and answered by a witness, safe and answered by a judged
    universal, unsafe and unanswered, safe and unanswered — within a
    kind in the order of a hash of (seed, question, route)."""
    def kind(item) -> int:
        q, _, rec = item
        judged = rec["value"]["kind"] == "witness" or (
            rec["value"]["kind"] == "all" and rec.get("gap") is not None)
        return (0 if judged else 2) + (0 if q["truth"] == "unsafe" else 1)

    def rank(item) -> str:
        q, _, rec = item
        return hashlib.sha256(
            f"{seed}:{q['id']}:{'>'.join(rec['route'])}".encode()).hexdigest()
    piles = [sorted((x for x in kept if kind(x) == i), key=rank)
             for i in range(4)]
    chosen = []
    while len(chosen) < k and any(piles):
        for pile in piles:
            if pile and len(chosen) < k:
                chosen.append(pile.pop(0))
    return chosen


def play_target(reg_root: str, reg: dict, t: dict, n: int, seed: int,
                out: str, runs_root: str = "runs", k: int = 10) -> None:
    """Play ``n`` sampled mutants of one transport — the sample the
    gate experiment draws, so the two join on (entry, file, node, alt)
    — over ``k`` (question, route) the intact entry plays cheaply."""
    what = f"{t['entry']}/{t['file']}"
    scratch = tempfile.mkdtemp(prefix="faults-")
    saved_run, saved_tmp = runner.run, tempfile.tempdir
    try:
        staged = harness.stage(reg_root, t, scratch)
        path = os.path.join(staged, t["file"])
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        probe = harness.Probe(path)
        runner.run = probe

        # the registry with the staged entry bound, its accelerator
        # set aside: the mutated reference is what must run
        forced = dict(t["manifest"], _dir=staged)
        forced.pop("accelerator", None)
        seen = dict(reg)
        seen[t["sub"]] = dict(reg[t["sub"]])
        seen[t["sub"]][t["key"]] = forced

        harness.fresh_tmp(scratch)
        kept = []
        for q in _corpus_questions(reg) + _run_questions(runs_root):
            for route in driver.enumerate_routes(seen, q["language"]):
                if not any(e is forced for e in route):
                    continue
                rec = driver.run_route(seen, route, q, _PLAY_WALL_S)
                if rec["budget"]["spent_s"] <= _KEEP_S:
                    kept.append((q, route, rec))
        chosen = _pick(kept, k, seed)
        if not chosen:
            raise SystemExit(f"{what}: no question the intact entry plays "
                             f"within {_KEEP_S} s")
        probe.learning = False
        probe.cap = max(10.0, round(4 * probe.longest, 1))

        with open(path, "w", encoding="utf-8") as fh:
            fh.write(mutate.identity(source))
        harness.fresh_tmp(scratch)
        probe.reset()
        for q, route, intact in chosen:
            rec = driver.run_route(seen, route, q, _PLAY_WALL_S)
            if verdict(q, intact, rec) != "same":
                raise SystemExit(f"{what}: the identity mutant changed "
                                 f"{q['id']}")

        lineage = set(t["manifest"].get("lineage", []))
        sampled = mutate.sample(source, what, n, seed)
        done = harness.done(out, t["entry"], t["file"], seed)
        if not done:
            harness.append(out, {
                "event": "target", "entry": t["entry"], "file": t["file"],
                "role": t["role"], "seed": seed, "sampled": len(sampled),
                "lineage": sorted(lineage), "cap_s": probe.cap,
                "questions": [{
                    "question": q["id"], "truth": q["truth"],
                    "route": rec["route"], "intact": _show(rec),
                    "grade": rec.get("grade", ""), "gap": rec.get("gap"),
                    "wrong": verdict(q, rec, rec).startswith("wrong")}
                    for q, _, rec in chosen]})
        for i, site in enumerate(sampled):
            if (site.node, site.alt) in done:
                continue
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(mutate.mutant(source, site))
            probe.reset()
            start, plays = time.monotonic(), []
            for q, route, intact in chosen:
                harness.fresh_tmp(scratch)
                rec = driver.run_route(seen, route, q, _PLAY_WALL_S)
                v = verdict(q, intact, rec)
                play = {"question": q["id"], "verdict": v}
                if v != "same":
                    play.update(value=_show(rec), grade=rec.get("grade", ""),
                                gap=rec.get("gap"))
                if v.startswith("wrong"):
                    play["blamed"] = lineage <= set(rec.get("trust", []))
                    play["trust"] = rec.get("trust", [])
                plays.append(play)
            harness.append(out, {
                "entry": t["entry"], "file": t["file"], "role": t["role"],
                "seed": seed, "node": site.node, "alt": site.alt,
                "op": site.op, "detail": site.detail, "line": site.line,
                "plays": plays,
                "seconds": round(time.monotonic() - start, 1)})
            tally = sorted({p["verdict"] for p in plays})
            harness.say(f"{what} {i + 1}/{len(sampled)} "
                        f"{site.op}@{site.line}: {' '.join(tally)}")
    finally:
        runner.run, tempfile.tempdir = saved_run, saved_tmp
        shutil.rmtree(scratch, ignore_errors=True)


# -- the report ---------------------------------------------------------------

def result_files() -> list[str]:
    return sorted(os.path.join(harness.RESULTS, f)
                  for f in os.listdir(harness.RESULTS)
                  if f.startswith("play-") and f.endswith(".jsonl"))


def report(paths: list[str]) -> str:
    """One row per transport: plays by verdict, the wrong ones by the
    grade they carry, and how many of those the residual blames."""
    rows: dict[tuple, list] = {}
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if "plays" in r:
                    rows.setdefault((r["entry"], r["file"]), []).append(r)
    if not rows:
        return ""
    out = ["| transport | mutants | plays | same | lost | gained | "
           "wrong claimed | wrong checked | wrong certified | blamed |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(rows):
        plays = [p for r in rows[key] for p in r["plays"]]
        count = lambda v: sum(1 for p in plays if p["verdict"] == v)
        wrong = [p for p in plays if p["verdict"].startswith("wrong")]
        out.append(
            f"| `{key[0]}/{key[1]}` | {len(rows[key])} | {len(plays)} | "
            f"{count('same')} | {count('lost')} | {count('gained')} | "
            f"{count('wrong-claimed')} | {count('wrong-checked')} | "
            f"{count('wrong-certified')} | "
            f"{sum(1 for p in wrong if p['blamed'])} of {len(wrong)} |")
    return "\n".join(out) + "\n"
