"""Pono with its certificate printer — carried over from v3
(KERNEL.md §7; supersedes the cert-less ``btor2--pono`` entry, pruned
between runs).

The unbounded leg as before — IC3 and k-induction answer
``unreachable`` for every bound — but certificate-yielding modes come
first: ``ic3bits`` and ``mbic3`` print the inductive invariant
(``--show-invar``) that proves the claim, and it rides the result as a
certificate the kernel re-discharges through ``discharge.py`` (base /
step / safe, decided by z3 — a lineage disjoint from pono's). ``ind``
stays as the deciding fallback; it does not support invariant
extraction, so its ``all(inf)`` travels certificate-less and stays
*claimed*. Modes are canary-checked two-sided before trust; the
multi-bad discipline (one property per pono run, ``unsat`` claimed
only when all agree, one invariant per property) is carried over from
``gurdy/solvers/pono_btor2.py`` and ``gurdy/solvers/invariant.py``.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

MODES = ("ic3bits", "mbic3", "ind")
FRAMES = 10_000            # -k ceiling; the wall is the real budget
CANARY_SAT = "1 sort bitvec 1\n2 one 1\n3 bad 2\n"
CANARY_UNSAT = "1 sort bitvec 1\n2 zero 1\n3 bad 2\n"


def emit(obj) -> None:
    print(json.dumps(obj, sort_keys=True))
    sys.exit(0)


def partial(note: str, **progress) -> None:
    emit({"kind": "partial", "progress": {"note": note, **progress}})


def count_bads(text: str) -> int:
    count = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[0].isdigit() and parts[1] == "bad":
            count += 1
    return count


def parse_invariant(output: str):
    """The ``INVAR: <term>`` line of a ``--show-invar`` run, balanced
    across following lines when the printer wraps (the parse
    ``gurdy/solvers/invariant.py`` used all campaign)."""
    lines = output.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("INVAR:"):
            continue
        term = stripped[len("INVAR:"):].strip()
        depth = term.count("(") - term.count(")")
        j = i
        while depth > 0 and j + 1 < len(lines):
            j += 1
            term += " " + lines[j].strip()
            depth += lines[j].count("(") - lines[j].count(")")
        return term or None
    return None


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
        cmd = [pono, "-e", mode, "-k", str(FRAMES), "-p", str(prop),
               "--show-invar"]
        if witpath:
            cmd += ["--witness", "--dump-btor2-witness", witpath]
        proc = subprocess.run(cmd + [path], capture_output=True,
                              text=True, timeout=wl)
        out = proc.stdout + "\n" + proc.stderr
        for verdict in ("sat", "unsat", "unknown"):
            if verdict in out.split():
                return verdict, out
        return "unparseable", out

    sat_canary = tmpfile(CANARY_SAT, ".btor2")
    unsat_canary = tmpfile(CANARY_UNSAT, ".btor2")
    notes = []
    try:
        for mode in MODES:
            try:
                if (run(sat_canary, mode, 0, min(wall, 30.0))[0] != "sat"
                        or run(unsat_canary, mode, 0,
                               min(wall, 30.0))[0] != "unsat"):
                    notes.append(f"{mode}: failed a canary, not trusted")
                    continue
            except subprocess.TimeoutExpired:
                notes.append(f"{mode}: canary timed out")
                continue
            all_unsat, invariants = True, []
            for prop in range(n_bads):
                witpath = tmpfile("", ".wit")
                os.unlink(witpath)
                try:
                    verdict, out = run(program, mode, prop, wall,
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
                invariants.append(parse_invariant(out))
            if all_unsat:
                value = {"kind": "all", "bound": "inf"}
                if all(inv is not None for inv in invariants):
                    value["cert"] = {"schema": "btor2-invariant-smtlib",
                                     "invariants": invariants}
                emit(value)
    finally:
        os.unlink(sat_canary)
        os.unlink(unsat_canary)
        os.unlink(program)
    partial("no mode decided", modes=notes)


if __name__ == "__main__":
    main()
