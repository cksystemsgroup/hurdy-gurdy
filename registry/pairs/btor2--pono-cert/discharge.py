"""Discharge checker for the pono pair's invariant certificates
(KERNEL.md §2) — carried over from v3's ``gurdy/solvers/invariant.py``.

A certificate is one inductive invariant per ``bad`` property, in
pono's ``state<id>``/``input<id>`` naming. For each, three QF_ABV
obligations are built through the v3 bridge's operator mapping (the
one the native-vs-bridged cross-check exercised all campaign) and
decided by z3 — a lineage disjoint from pono's declared four:

  base:  Init ∧ C₀ ∧ ¬Inv₀             must be unsat
  step:  Inv₀ ∧ C₀ ∧ T ∧ C₁ ∧ ¬Inv₁    must be unsat
  safe:  Inv₀ ∧ C₀ ∧ bad₀              must be unsat

``ok`` only when every obligation of every property answers ``unsat``.
Fail-safe as everywhere: an invariant outside the compiler's grammar,
a width mismatch, a ``sat``/``unknown``/timeout — each can only fail
to certify, never fake a certification. What a validated discharge
still rests on, recorded: the bridge's BTOR2→SMT operator mapping and
z3 itself (the manifest's ``discharge_lineage``).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
sys.path.insert(0, _ROOT)

from gurdy.solvers.invariant import obligation_scripts  # noqa: E402

_Z3_WALL_S = 60.0


def emit(ok: bool, obligations: dict) -> None:
    print(json.dumps({"ok": ok, "obligations": obligations},
                     sort_keys=True))
    sys.exit(0)


def main() -> None:
    program_path, cert_path = sys.argv[1:3]
    with open(program_path, encoding="utf-8") as fh:
        text = fh.read()
    with open(cert_path, encoding="utf-8") as fh:
        cert = json.load(fh)
    z3 = os.environ.get("Z3") or shutil.which("z3")
    if not z3:
        emit(False, {"error": "z3 not found on PATH"})
    if cert.get("schema") != "btor2-invariant-smtlib":
        emit(False, {"error": "unknown certificate schema "
                              f"{cert.get('schema')!r}"})
    invariants = cert.get("invariants")
    n_bads = sum(1 for line in text.splitlines()
                 if len(line.split()) > 1 and line.split()[0].isdigit()
                 and line.split()[1] == "bad")
    if not isinstance(invariants, list) or len(invariants) != n_bads:
        emit(False, {"error": "one invariant per bad property required"})
    obligations, ok = {}, True
    for prop, inv in enumerate(invariants):
        try:
            scripts = obligation_scripts(text, inv, prop=prop)
        except Exception as exc:                     # fail-safe, recorded
            emit(False, {f"p{prop}": f"invariant rejected: {exc}"})
        for name in sorted(scripts):
            path = None
            try:
                fd, path = tempfile.mkstemp(suffix=".smt2")
                with os.fdopen(fd, "wb") as fh:
                    fh.write(scripts[name])
                proc = subprocess.run([z3, "-smt2", path],
                                      capture_output=True, text=True,
                                      timeout=_Z3_WALL_S)
                verdict = (proc.stdout.split() or ["error"])[0]
            except subprocess.TimeoutExpired:
                verdict = "timeout"
            finally:
                if path:
                    os.unlink(path)
            obligations[f"p{prop}/{name}"] = verdict
            ok = ok and verdict == "unsat"
    emit(ok, obligations)


if __name__ == "__main__":
    main()
