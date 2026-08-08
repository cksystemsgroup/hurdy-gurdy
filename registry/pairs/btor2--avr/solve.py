"""AVR as a solver pair — carried over from v3 (KERNEL.md §7):
Averroes v2, IC3-style equality abstraction over the word-level
netlist, the platform's second unbounded native engine. Its lineage
is the point: the host build compiles only the Yices 2 backend, so
the ancestry is exactly (avr, yices) — disjoint from every
boolector-family engine — and its unbounded agreement is what
corroborates a certified all(inf). AVR checks all bad properties
natively (any-bad, no per-property loop); an unbounded proof books
all(inf); a counterexample dumps a BTOR2-format witness the shared
interpreter replays — btormc's evidence path; its own timeout and
memout self-reports book as partials that say so. The memout cap is
v3's admitted 8192 MB (a smaller cap trips AVR's accounting even on
trivial systems).
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.languages.btor2.witness import (  # noqa: E402
    _row_valid, replay)

MEMOUT_MB = 8192
RESULTS = {"avr-h": "all", "avr-h_triv": "all", "avr-v": "witness",
           "avr-f_to": "resource", "avr-f_to_q": "resource",
           "avr-f_mo": "resource"}


def emit(obj) -> None:
    print(json.dumps(obj, sort_keys=True))
    sys.exit(0)


def partial(note: str, **progress) -> None:
    emit({"kind": "partial", "progress": {"note": note, **progress}})


def find_avr():
    for cand in (os.environ.get("AVR"), os.path.expanduser("~/avr")):
        if cand and os.path.isfile(os.path.join(cand, "avr.py")):
            return cand
    return None


def main() -> None:
    program_path, _mode, _observable, _bound, wall_s = sys.argv[1:6]
    wall = float(wall_s)
    avr_dir = find_avr()
    if not avr_dir:
        partial("avr not found (set $AVR or build ~/avr)")
    with open(program_path, encoding="utf-8") as fh:
        text = fh.read()
    work = tempfile.mkdtemp(prefix="avr-")
    path = os.path.join(work, "q.btor2")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        proc = subprocess.Popen(
            [sys.executable, os.path.join(avr_dir, "avr.py"),
             "-o", work, "-n", "q", "--backend", "y2", "--witness",
             "--timeout", str(int(wall)), "--memout", str(MEMOUT_MB),
             path],
            cwd=avr_dir, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            proc.wait(timeout=wall + 30)
        except subprocess.TimeoutExpired:
            # avr.py's own CPU timer should have fired; the grace
            # catches a hung frontend. Kill the whole session (avr.py
            # spawns vwn/dpa/reach_y2).
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            partial("resource-out at the wall grace", wall_s=wall)
        outdir = os.path.join(work, "work_q")
        try:
            with open(os.path.join(outdir, "result.pr"),
                      encoding="utf-8") as fh:
                result = fh.read().strip()
        except FileNotFoundError:
            partial("avr produced no result.pr")
        kind = RESULTS.get(result)
        if kind == "all":
            emit({"kind": "all", "bound": "inf"})
        if kind == "witness":
            witpath = os.path.join(outdir, "cex.witness")
            if os.path.exists(witpath):
                with open(witpath, encoding="utf-8") as fh:
                    wit = fh.read()
                # v3's caller discipline, carried into the shim: a
                # witness AVR's equality abstraction leaves degenerate
                # does not fire on replay — the verdict then stands
                # unconfirmed, evidence rather than a result.
                try:
                    trace = replay(text, wit)
                    fired = any(_row_valid(row) and any(
                        v == 1 for k, v in row.items()
                        if k.startswith("bad")) for row in trace)
                except Exception:
                    fired = False
                if fired:
                    emit({"kind": "witness", "payload": {"wit": wit}})
                partial("reachable, but the dumped witness is "
                        "degenerate under replay — unconfirmed",
                        result=result)
            partial("reachable without a dumped witness — unconfirmed",
                    result=result)
        if kind == "resource":
            partial("avr self-reported spent budget", result=result,
                    wall_s=wall, memout_mb=MEMOUT_MB)
        partial("avr abstained", result=result)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
