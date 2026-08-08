"""Bitwuzla as the second SMT-LIB solver pair — carried over from v3
(KERNEL.md §7): a different codebase than z3 deciding the same
scripts, which is what independence means — except the lineage says
exactly how far it goes: Boolector's successor, one family with
btormc and pono's stacks, so it corroborates z3 but never them.
Verdict-only, as the v3 adapter was: unsat is a complete fact about
the script and books all(inf) (routes cap it crossing bound-eating
hops); a sat without a model is unreplayable and books as evidence
inside a partial, never a witness result.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile


def emit(obj) -> None:
    print(json.dumps(obj, sort_keys=True))
    sys.exit(0)


def partial(note: str, **progress) -> None:
    emit({"kind": "partial", "progress": {"note": note, **progress}})


def main() -> None:
    program_path, _mode, _observable, _bound, wall_s = sys.argv[1:6]
    wall = float(wall_s)
    bitwuzla = os.environ.get("BITWUZLA") or shutil.which("bitwuzla")
    if not bitwuzla:
        partial("bitwuzla not found (set $BITWUZLA or PATH)")
    with open(program_path, encoding="utf-8") as fh:
        text = fh.read()
    fd, path = tempfile.mkstemp(suffix=".smt2")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    try:
        try:
            proc = subprocess.run([bitwuzla, path], capture_output=True,
                                  text=True, timeout=wall)
        except subprocess.TimeoutExpired:
            partial("resource-out at the declared wall", wall_s=wall)
    finally:
        os.unlink(path)
    tokens = [ln.strip().lower()
              for ln in (proc.stdout + "\n" + proc.stderr).splitlines()]
    if "unsat" in tokens:
        emit({"kind": "all", "bound": "inf"})
    if "sat" in tokens:
        partial("sat, verdict-only — bitwuzla produces no model here; "
                "unreplayable, so evidence rather than a witness")
    partial("bitwuzla answered unknown or refused the logic",
            head=(proc.stdout + proc.stderr)[:200])


if __name__ == "__main__":
    main()
