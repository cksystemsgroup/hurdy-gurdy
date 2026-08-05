"""btormc as a solver pair — carried over from v3 (KERNEL.md §7).

Bounded model checking on BTOR2: ``sat`` yields a witness payload (the
raw ``.wit``, replayed by the kernel through the shared interpreter),
exhaustion yields ``all(k)``. The exhaustion signal is *silence*, so it
is trusted only from a binary that first answers ``sat`` on a trivially
reachable canary — the negative-control discipline of v3's
``gurdy/solvers/native_btor2.py``, carried over with the code. An
unbounded ask is answered to the declared cap ``k = 20`` and lands as a
level-1 result: this engine cannot close an ``inf`` ask, and says so.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

INF_CAP_K = 20
CANARY = "1 sort bitvec 1\n2 one 1\n3 bad 2\n"


def emit(obj) -> None:
    print(json.dumps(obj, sort_keys=True))
    sys.exit(0)


def partial(note: str, **progress) -> None:
    emit({"kind": "partial", "progress": {"note": note, **progress}})


def main() -> None:
    program_path, _mode, _observable, bound, wall_s = sys.argv[1:6]
    k = INF_CAP_K if bound == "inf" else min(int(bound), 10**6)
    wall = float(wall_s)
    btormc = os.environ.get("BTORMC") or shutil.which("btormc")
    if not btormc:
        partial("btormc not found on PATH")

    def run(path: str, kk: int, wl: float):
        return subprocess.run(
            [btormc, "-kmax", str(kk), "--trace-gen-full", path],
            capture_output=True, text=True, timeout=wl)

    fd, canary = tempfile.mkstemp(suffix=".btor2")
    with os.fdopen(fd, "w") as fh:
        fh.write(CANARY)
    try:
        try:
            c = run(canary, 0, min(wall, 30.0))
        except subprocess.TimeoutExpired:
            partial("canary timed out")
        if "sat" not in c.stdout.split():
            partial("btormc failed the reachable canary; "
                    "its silence cannot be trusted")
        try:
            p = run(program_path, k, wall)
        except subprocess.TimeoutExpired:
            partial("resource-out at the declared wall",
                    bound_reached=-1, wall_s=wall, k=k)
    finally:
        os.unlink(canary)
    tokens = [line.strip() for line in
              (p.stdout + "\n" + p.stderr).splitlines()]
    if any(t == "sat" or t.startswith("sat ") for t in tokens):
        emit({"kind": "witness", "payload": {"wit": p.stdout}})
    if any(t == "unsat" or t.startswith("unsat ") for t in tokens):
        emit({"kind": "all", "bound": k})
    if p.returncode == 0 and not p.stdout.strip() and not p.stderr.strip():
        emit({"kind": "all", "bound": k})    # clean exhaustion, canary-trusted
    partial("unparseable btormc output", rc=p.returncode,
            head=p.stdout[:200])


if __name__ == "__main__":
    main()
