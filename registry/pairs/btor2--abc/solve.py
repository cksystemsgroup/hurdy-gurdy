"""Berkeley ABC's pdr as a solver pair — carried over from v3
(KERNEL.md §7): the bit-level IC3/PDR reference implementation. The
BTOR2 question reaches it through btor2tools' btor2aiger (bit-blast
via Boolector's AIG manager — declared in the lineage, so ABC can
corroborate AVR but never btormc or pono). The two empirically-forced
v3 rules ride along: ``fold`` before ``pdr`` (plain pdr ignores AIGER
invariant constraints), and one property per run (btor2aiger's B
entries are anonymous — bads are masked down at the BTOR2 level and
any-bad aggregated). "Property proved" on every property books
all(inf); an asserted output is a counterexample ABC cannot yet
translate back — evidence inside a partial, never a witness result.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

_ASSERTED = re.compile(r"was asserted in frame (\d+)")


def emit(obj) -> None:
    print(json.dumps(obj, sort_keys=True))
    sys.exit(0)


def partial(note: str, **progress) -> None:
    emit({"kind": "partial", "progress": {"note": note, **progress}})


def find_tool(env: str, fallback: str, name: str):
    for cand in (os.environ.get(env), os.path.expanduser(fallback)):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return shutil.which(name)


def count_bads(text: str) -> int:
    return sum(1 for ln in text.splitlines()
               if len(ln.split()) > 1 and ln.split()[0].isdigit()
               and ln.split()[1] == "bad")


def keep_bad(text: str, keep: int) -> str:
    out, idx = [], 0
    for ln in text.splitlines():
        t = ln.split()
        if len(t) > 1 and t[0].isdigit() and t[1] == "bad":
            if idx != keep:
                idx += 1
                continue
            idx += 1
        out.append(ln)
    return "\n".join(out) + "\n"


def main() -> None:
    program_path, _mode, _observable, _bound, wall_s = sys.argv[1:6]
    wall = float(wall_s)
    abc = find_tool("ABC", "~/abc-route/abc/abc", "abc")
    btor2aiger = find_tool("BTOR2AIGER",
                           "~/abc-route/btor2tools/build/bin/btor2aiger",
                           "btor2aiger")
    if not abc or not btor2aiger:
        partial("abc/btor2aiger not found (set $ABC / $BTOR2AIGER)")
    with open(program_path, encoding="utf-8") as fh:
        text = fh.read()
    n_bads = max(1, count_bads(text))
    all_proved, notes = True, []
    for prop in range(n_bads):
        single = keep_bad(text, prop) if n_bads > 1 else text
        work = tempfile.mkdtemp(prefix="abc-")
        btor = os.path.join(work, "q.btor2")
        aig = os.path.join(work, "q.aig")
        try:
            with open(btor, "w", encoding="utf-8") as fh:
                fh.write(single)
            try:
                conv = subprocess.run([btor2aiger, btor],
                                      capture_output=True, timeout=60)
            except subprocess.TimeoutExpired:
                partial("btor2aiger timed out", prop=prop)
            if conv.returncode != 0:
                partial("btor2aiger refused the encoding", prop=prop)
            with open(aig, "wb") as fh:
                fh.write(conv.stdout)
            try:
                proc = subprocess.run(
                    [abc, "-c", f"read {aig}; fold; pdr"],
                    capture_output=True, text=True, timeout=wall)
            except subprocess.TimeoutExpired:
                partial("resource-out at the declared wall",
                        prop=prop, wall_s=wall)
            out = proc.stdout + "\n" + proc.stderr
            m = _ASSERTED.search(out)
            if m:
                partial("counterexample asserted — abc's cex is not "
                        "yet translated back to a replayable witness",
                        prop=prop, frame=int(m.group(1)))
            if "Property proved" not in out:
                all_proved = False
                notes.append(f"prop {prop}: no verdict")
        finally:
            shutil.rmtree(work, ignore_errors=True)
    if all_proved:
        emit({"kind": "all", "bound": "inf"})
    partial("abc abstained", props=notes)


if __name__ == "__main__":
    main()
