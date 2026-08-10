#!/usr/bin/env python3
"""btormc solver: an independent, external BTOR2 model checker.

<program> <mode> <observable> <bound> <wall_s> -> one result JSON.

Runs btormc's plain bounded model checking (no k-induction — its
success/failure isn't reliably distinguishable from stdout alone, and
an unearned 'inf' claim would be dishonest) up to kmax = the asked
bound (or a generous fallback when the ask is unbounded). A 'sat'
verdict yields a witness trace, parsed and handed back verbatim as an
input-list payload for replay through the (separately built) btor2
language interpreter — the kernel never trusts this solver's own
reading of the trace. An 'unsat'-within-kmax verdict is only ever
reported for a *finite* ask, as a bounded 'all' claim exactly at that
bound: sound (plain BMC found nothing up to kmax), but never stretched
into an unbounded one.
"""
import json
import subprocess
import sys

FALLBACK_KMAX = 250


def parse_trace(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "sat":
        return None
    frames = {}
    section = None
    cur = None
    for line in lines[1:]:
        line = line.strip()
        if line == ".":
            break
        if line.startswith("#"):
            section = "state"
            continue
        if line.startswith("@"):
            try:
                cur = int(line[1:])
            except ValueError:
                cur = None
            section = "input"
            if cur is not None:
                frames.setdefault(cur, {})
            continue
        if section == "input" and cur is not None:
            parts = line.split()
            if len(parts) >= 3:
                bits, name_at = parts[1], parts[2]
                name = name_at.split("@")[0]
                try:
                    frames[cur][name] = int(bits, 2)
                except ValueError:
                    pass
    if not frames:
        return None
    depth = max(frames)
    return [frames.get(i, {}) for i in range(depth + 1)]


def main():
    program_path, mode, observable, bound_s, wall_s = sys.argv[1:6]
    wall = float(wall_s)
    if observable != "bad":
        print(json.dumps({"kind": "partial", "progress": {
            "note": f"cannot decide {observable!r}"}}))
        return
    bound_i = None if bound_s == "inf" else int(bound_s)
    kmax = bound_i if bound_i is not None else FALLBACK_KMAX

    try:
        p = subprocess.run(
            ["btormc", "-kmax", str(kmax), "--trace-gen-full", program_path],
            capture_output=True, timeout=max(wall * 0.8, 1.0), text=True)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(json.dumps({"kind": "partial", "progress": {
            "note": f"btormc unavailable or timed out: {exc}",
            "bound_reached": -1}}))
        return

    payload = parse_trace(p.stdout)
    if payload is not None:
        print(json.dumps({"kind": "witness", "payload": payload}))
        return

    if p.returncode != 0:
        print(json.dumps({"kind": "partial", "progress": {
            "note": f"btormc exited {p.returncode}", "bound_reached": -1}}))
        return

    if bound_i is None:
        print(json.dumps({"kind": "partial", "progress": {
            "note": f"no violation found by plain BMC up to kmax={kmax}; "
                    "unbounded safety not attempted (k-induction success "
                    "is not reliably readable from btormc's plain output)",
            "bound_reached": kmax}}))
        return

    print(json.dumps({"kind": "all", "bound": bound_i, "cert": None}))


if __name__ == "__main__":
    main()
