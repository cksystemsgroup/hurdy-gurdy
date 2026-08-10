#!/usr/bin/env python3
"""pono solver: a second, independent external BTOR2 model checker
(disjoint from btormc and from the hand-built btor2-explicit /
btor2-congruence engines — a different codebase entirely).

<program> <mode> <observable> <bound> <wall_s> -> one result JSON.

Two phases, both empirically checked against this domain's benchmarks
before being trusted here:

  1. BMC (`pono -e bmc -k kmax --witness`) hunts for a violation. A
     'sat' verdict gives a concrete trace, parsed into the same
     input-list payload the btor2 interpreter replays (the kernel
     never trusts pono's own reading of it). Empirically, pono's plain
     BMC reports 'unknown' — never a clean bounded-unsat — when it
     finds nothing, at any k, so a miss here is never turned into a
     bounded 'all' claim (unlike btormc, whose '-kmax' convention *is*
     a genuine bounded sweep; see registry/btormc/solve.py).

  2. Only for an unbounded ('inf') ask with no BMC violation: bit-level
     IC3 (`pono -e ic3bits`, falling back to `ic3ia`) is a real
     decision procedure for these finite-state bitvector systems.  A
     clean 'unsat' is a genuine, tool-verified unbounded safety proof
     — reported as 'all(bound="inf")', ungraded (no certificate;
     pono's inductive invariant isn't parsed and re-checked here, so
     this can only ever reach the 'claimed' grade, same as any
     external tool without a discharge script). It exists to
     *corroborate* registry/btor2-congruence's certified proofs from
     an entirely different lineage, and to independently close cases
     the congruence search's power-of-two search doesn't cover.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

FALLBACK_KMAX = 250


def as_btor2(program_path):
    """pono picks its parser from the filename extension and rejects
    anything but .btor/.btor2 — but the gate corpus convention names
    programs 'NNN.program'. Normalise with a same-content temp copy."""
    if program_path.endswith((".btor", ".btor2")):
        return program_path
    with open(program_path, "rb") as fh:
        data = fh.read()
    fd, path = tempfile.mkstemp(suffix=".btor2")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return path


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


def run_pono(args, timeout):
    try:
        return subprocess.run(["pono", *args], capture_output=True,
                              timeout=max(timeout, 0.1), text=True)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def main():
    program_path, mode, observable, bound_s, wall_s = sys.argv[1:6]
    wall = float(wall_s)
    if observable != "bad":
        print(json.dumps({"kind": "partial", "progress": {
            "note": f"cannot decide {observable!r}"}}))
        return
    bound_i = None if bound_s == "inf" else int(bound_s)
    kmax = bound_i if bound_i is not None else FALLBACK_KMAX
    t0 = time.monotonic()
    btor_path = as_btor2(program_path)

    p = run_pono(["-e", "bmc", "-k", str(kmax), "--witness", btor_path],
                max(wall * 0.5, 1.0))
    if p is not None:
        payload = parse_trace(p.stdout)
        if payload is not None:
            print(json.dumps({"kind": "witness", "payload": payload}))
            return

    if bound_i is not None:
        print(json.dumps({"kind": "partial", "progress": {
            "note": f"pono bmc found no violation up to k={kmax}, but plain "
                    "bmc never reports a bounded-unsat verdict for this "
                    "tool (empirically always 'unknown' on a miss) — not "
                    "turned into an 'all' claim", "bound_reached": kmax}}))
        return

    for engine in ("ic3bits", "ic3ia"):
        remaining = wall * 0.9 - (time.monotonic() - t0)
        if remaining <= 0.2:
            break
        p = run_pono(["-e", engine, "--witness", btor_path], remaining)
        if p is None:
            continue
        out = p.stdout.strip()
        if out.startswith("unsat"):
            print(json.dumps({"kind": "all", "bound": "inf", "cert": None}))
            return
        payload = parse_trace(p.stdout)
        if payload is not None:
            print(json.dumps({"kind": "witness", "payload": payload}))
            return

    print(json.dumps({"kind": "partial", "progress": {
        "note": "bmc found no violation and ic3bits/ic3ia reached no "
                "conclusive verdict within budget", "bound_reached": kmax}}))


if __name__ == "__main__":
    main()
