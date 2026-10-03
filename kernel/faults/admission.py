"""The first experiment: where does a fault die at the gate?"""

from __future__ import annotations

import ast
import json
import os
import shutil
import tempfile
import time

from kernel import gate, runner
from kernel.faults import harness, mutate


# -- the tiers a mutated entry faces ------------------------------------------

def _tiers(reg: dict, t: dict, staged: str) -> list[tuple[str, object]]:
    """(name, thunk) in admission order; a thunk raises when the gate
    refuses. ``staged`` is the scratch copy of the entry."""
    m, kind = t["manifest"], t["manifest"]["kind"]
    wall = harness.WALL_S
    if kind == "language":
        own = lambda: gate.check_language(staged, m, wall_s=wall)
    elif kind == "pair":
        own = lambda: gate.check_pair(reg, staged, m, wall_s=wall)
    else:
        own = lambda: gate.check_search(reg, staged, m, wall_s=wall)
    tiers = [("own", own)]
    if m.get("revision", 1) > 1:
        tiers.append(("revision", lambda: gate._check_revision(
            reg, staged, m, wall)))
    if t["role"] == "judge":
        # the registry as the dependents would see it with the mutant
        # admitted: the language's directory is the staged one
        seen = dict(reg)
        seen["languages"] = dict(reg["languages"])
        seen["languages"][t["key"]] = dict(m, _dir=staged)

        def dependents():
            for pid, pm in sorted(reg["pairs"].items()):
                if "admission" in pm and t["key"] in (pm["src"], pm["tgt"]):
                    gate.check_pair(seen, pm["_dir"], pm, wall_s=wall)
            for name, sm in sorted(reg["searches"].items()):
                if "admission" in sm and sm["language"] == t["key"]:
                    gate.check_search(seen, sm["_dir"], sm, wall_s=wall)
        tiers.append(("dependents", dependents))
    return tiers


def _face(tiers) -> tuple[str | None, str]:
    """Run the tiers in order; (the tier that refused or None, why)."""
    for name, thunk in tiers:
        try:
            thunk()
        except gate.AdmissionError as exc:
            return name, str(exc)
        except Exception as exc:          # the gate itself fell over a
            return name, f"gate raised {type(exc).__name__}: {exc}"  # mutant
    return None, ""


def _statement_lines(source: str) -> set[int]:
    return {n.lineno for n in ast.walk(ast.parse(source))
            if isinstance(n, ast.stmt)}


# -- the experiment -----------------------------------------------------------

def gate_target(reg_root: str, reg: dict, t: dict, n: int, seed: int,
                out: str, like: str = "") -> None:
    """Gate ``n`` sampled mutants of one executable; append one record
    each. Two controls come first and must pass every tier: the intact
    file (run under the line recorder, its longest run setting the
    cap) and the identity mutant (the intact tree unparsed).

    ``like`` names another entry — a predecessor — holding the same
    file byte for byte: the sample drawn is then that entry's, so a
    revision that changes only what surrounds a judge is measured on
    the very mutants its predecessor was."""
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
        tiers = _tiers(reg, t, staged)

        harness.fresh_tmp(scratch)
        probe.cover_out = os.path.join(scratch, "lines.jsonl")
        start = time.monotonic()
        tier, why = _face(tiers)
        baseline_s = time.monotonic() - start
        if tier is not None:
            raise SystemExit(f"{what}: the intact entry was refused at "
                             f"{tier!r}: {why}")
        hit: set[int] = set()
        with open(probe.cover_out, encoding="utf-8") as fh:
            for line in fh:
                hit.update(json.loads(line))
        probe.cover_out = None
        probe.learning = False
        probe.cap = max(10.0, round(4 * probe.longest, 1))
        peak_mb = probe.peak_mb

        with open(path, "w", encoding="utf-8") as fh:
            fh.write(mutate.identity(source))
        harness.fresh_tmp(scratch)
        probe.reset()
        tier, why = _face(tiers)
        if tier is not None:
            raise SystemExit(f"{what}: the identity mutant was refused at "
                             f"{tier!r}: {why}")

        if like:
            with open(os.path.join(reg_root, like, t["file"]),
                      encoding="utf-8") as fh:
                if fh.read() != source:
                    raise SystemExit(f"{what}: not the bytes of {like}")
        chosen = mutate.sample(source, f"{like}/{t['file']}" if like
                               else what, n, seed)
        done = harness.done(out, t["entry"], t["file"], seed)
        if not done:
            stmts = _statement_lines(source)
            harness.append(out, {
                "event": "target", "entry": t["entry"], "file": t["file"],
                "role": t["role"], "seed": seed, "like": like,
                "sites": len(mutate.sites(source)), "sampled": len(chosen),
                "statements": len(stmts), "executed": len(stmts & hit),
                "tiers": [name for name, _ in tiers],
                "baseline_s": round(baseline_s, 1), "cap_s": probe.cap,
                "peak_mb": round(peak_mb)})
        for i, site in enumerate(chosen):
            if (site.node, site.alt) in done:
                continue
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(mutate.mutant(source, site))
            harness.fresh_tmp(scratch)
            probe.reset()
            start = time.monotonic()
            tier, why = _face(tiers)
            how = None if tier is None else (
                "memory" if probe.bloats else
                "timeout" if probe.timeouts else
                "crash" if probe.crashes else "check")
            harness.append(out, {
                "entry": t["entry"], "file": t["file"], "role": t["role"],
                "seed": seed, "node": site.node, "alt": site.alt,
                "op": site.op, "detail": site.detail, "line": site.line,
                "cover": any(k in hit for k in range(site.line,
                                                     site.end_line + 1)),
                "runs": probe.runs,
                "outcome": "survived" if tier is None else "refused",
                "tier": tier, "how": how,
                "why": why.replace(scratch + os.sep, "")[:200],
                "seconds": round(time.monotonic() - start, 1)})
            harness.say(f"{what} {i + 1}/{len(chosen)} "
                        f"{site.op}@{site.line}: {tier or 'survived'}")
    finally:
        runner.run, tempfile.tempdir = saved_run, saved_tmp
        shutil.rmtree(scratch, ignore_errors=True)


# -- the report ---------------------------------------------------------------

def _result_files() -> list[str]:
    return sorted(os.path.join(harness.RESULTS, f)
                  for f in os.listdir(harness.RESULTS)
                  if f.startswith("gate-") and f.endswith(".jsonl"))


def report(paths: list[str]) -> str:
    """One row per executable: how many mutants each tier refused, how
    many survived, and of the survivors how many sit on lines an
    admission input executed."""
    heads, rows = {}, {}
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                key = (r["role"], r["entry"], r["file"])
                if r.get("event") == "target" and "tiers" in r:
                    heads[key] = r
                elif "outcome" in r:
                    rows.setdefault(key, []).append(r)
    if not rows:
        return ""
    out = ["| role | executable | statements run | mutants | own | "
           "revision | dependents | survived | on executed lines |",
           "|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(rows):
        rs, h = rows[key], heads.get(key, {})
        by = lambda tier: sum(1 for r in rs if r["tier"] == tier)
        tiers = h.get("tiers", [])
        cell = lambda tier: str(by(tier)) if tier in tiers else "—"
        alive = [r for r in rs if r["outcome"] == "survived"]
        ran = (f"{h['executed']} of {h['statements']}"
               if "statements" in h else "?")
        out.append(f"| {key[0]} | `{key[1]}/{key[2]}` | {ran} | {len(rs)} | "
                   f"{cell('own')} | {cell('revision')} | "
                   f"{cell('dependents')} | {len(alive)} | "
                   f"{sum(1 for r in alive if r['cover'])} |")
    return "\n".join(out) + "\n"
