"""Pono as a solver pair — carried over from v3 (KERNEL.md §7).

The unbounded leg: k-induction (``ind``) and IC3 (``ic3bits``,
``mbic3``) answer ``unreachable`` *for every bound*, so an ``inf`` ask
this engine closes lands as ``all(inf)`` — what bounded BMC provably
cannot do (the campaign's exponential-in-k curves). Modes are tried in
v3's admitted order (``gurdy/solvers/pono_btor2.py``), each first
proved two-sided on a pair of canaries — a reachable one that must
answer ``sat`` and an unreachable one that must answer ``unsat`` —
before its verdict on the program is trusted. Pono checks one ``bad``
property per run where the question is any-bad, so every property is
checked and ``unsat`` is claimed only when all agree — the multi-bad
discipline carried over with the code. On ``sat`` the dumped
BTOR2-format witness rides the same evidence path as btormc's
``.wit``: the kernel replays it through the shared interpreter.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

MODES = ("ind", "ic3bits", "mbic3")
FRAMES = 10_000            # -k ceiling; the wall is the real budget
CANARY_SAT = "1 sort bitvec 1\n2 one 1\n3 bad 2\n"
CANARY_UNSAT = "1 sort bitvec 1\n2 zero 1\n3 bad 2\n"


def emit(obj) -> None:
    print(json.dumps(obj, sort_keys=True))
    sys.exit(0)


def partial(note: str, **progress) -> None:
    emit({"kind": "partial", "progress": {"note": note, **progress}})


def count_bads(text: str) -> int:
    """Pono checks exactly one property per run (``--prop``); reading a
    single-property ``unsat`` as "the system is unreachable" would lie
    on multi-bad systems."""
    count = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[0].isdigit() and parts[1] == "bad":
            count += 1
    return count


def tmpfile(text: str, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    return path


def main() -> None:
    program_path, _mode, _observable, _bound, wall_s = sys.argv[1:6]
    wall = float(wall_s)
    pono = os.environ.get("PONO") or shutil.which("pono")
    if not pono:
        partial("pono not found on PATH")
    with open(program_path, encoding="utf-8") as fh:
        text = fh.read()
    n_bads = max(1, count_bads(text))
    # pono dispatches its parser on the file extension; the kernel hands
    # programs around as ``.program``, so stage a ``.btor2`` copy.
    program = tmpfile(text, ".btor2")

    def run(path: str, mode: str, prop: int, wl: float, witpath=None):
        cmd = [pono, "-e", mode, "-k", str(FRAMES), "-p", str(prop)]
        if witpath:
            cmd += ["--witness", "--dump-btor2-witness", witpath]
        proc = subprocess.run(cmd + [path], capture_output=True,
                              text=True, timeout=wl)
        tokens = (proc.stdout + "\n" + proc.stderr).split()
        for verdict in ("sat", "unsat", "unknown"):
            if verdict in tokens:
                return verdict
        return "unparseable"

    sat_canary = tmpfile(CANARY_SAT, ".btor2")
    unsat_canary = tmpfile(CANARY_UNSAT, ".btor2")
    notes = []
    try:
        for mode in MODES:
            try:
                if (run(sat_canary, mode, 0, min(wall, 30.0)) != "sat"
                        or run(unsat_canary, mode, 0,
                               min(wall, 30.0)) != "unsat"):
                    notes.append(f"{mode}: failed a canary, not trusted")
                    continue
            except subprocess.TimeoutExpired:
                notes.append(f"{mode}: canary timed out")
                continue
            all_unsat = True
            for prop in range(n_bads):
                witpath = tmpfile("", ".wit")
                os.unlink(witpath)
                try:
                    verdict = run(program, mode, prop, wall,
                                  witpath=witpath)
                except subprocess.TimeoutExpired:
                    notes.append(f"{mode}: resource-out on prop {prop} "
                                 f"at wall {wall}")
                    all_unsat = False
                    break
                if verdict == "sat" and os.path.exists(witpath):
                    with open(witpath, encoding="utf-8") as fh:
                        wit = fh.read()
                    os.unlink(witpath)
                    emit({"kind": "witness", "payload": {"wit": wit}})
                if verdict != "unsat":
                    notes.append(f"{mode}: {verdict} on prop {prop}")
                    all_unsat = False
                    break
            if all_unsat:
                emit({"kind": "all", "bound": "inf"})
    finally:
        os.unlink(sat_canary)
        os.unlink(unsat_canary)
        os.unlink(program)
    partial("no mode decided", modes=notes)


if __name__ == "__main__":
    main()
