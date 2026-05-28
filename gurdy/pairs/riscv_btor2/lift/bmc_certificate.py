"""DRAT-validated certificate for BMC ``unreachable`` verdicts.

A BMC backend's ``unreachable`` answer says: no bad state is reachable
within ``k`` cycles from init. The certificate ships the unrolled
formula as SMT-LIB plus the bound, and the verifier runs a three-stage
pipeline:

  1. SMT-LIB  → DIMACS    via ``bitwuzla --write-cnf`` (bit-blasts the
                          BV / array theory into pure SAT)
  2. DIMACS   → DRAT      via ``cadical foo.cnf foo.drat --no-binary``
                          (CaDiCaL solves CNF, emits a DRAT proof)
  3. DIMACS + DRAT → ✓    via ``drat-trim foo.cnf foo.drat``
                          (small trusted checker re-verifies the proof
                          without re-solving)

The certificate is *not* "another SMT solver re-checked unsat" — it's
a SAT-level proof certificate plus the small Heule-style verifier that
re-checks it. The trust gap shrinks to: bitwuzla's bit-blasting and
drat-trim itself.

drat-trim is bundled inside CaDiCaL's source tree in the bench Docker
image (``/opt/pono/deps/smt-switch/deps/cadical/test/cnf/drat-trim.c``).
The verifier compiles it once on first use and caches the binary in
``/tmp``.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gurdy.pairs.riscv_btor2.btor2.parser import from_text
from gurdy.pairs.riscv_btor2.solvers._bmc import (
    Compiled,
    compile_btor2,
    evaluate_all,
    find_sort_for,
)


_DEFAULT_IMAGE = os.environ.get(
    "HURDY_PONO_DOCKER_IMAGE", "christophkirsch/hurdy-gurdy-bench:latest"
)

# Where drat-trim's source lives inside the bench image, and where the
# compiled binary lands (cached across runs in the same container).
_DRAT_TRIM_SRC = "/opt/pono/deps/smt-switch/deps/cadical/test/cnf/drat-trim.c"
_CADICAL_BIN = "/opt/pono/deps/smt-switch/deps/cadical/build/cadical"


@dataclass(frozen=True)
class BMCCertificateReport:
    accepted: bool
    bound: int
    stage: str  # 'dimacs' | 'drat' | 'verify' | 'done'
    drat_lemmas: int | None = None
    elapsed_s: float = 0.0
    reason: str | None = None

    def summary(self) -> str:
        if self.accepted:
            suffix = (
                f", {self.drat_lemmas} lemmas" if self.drat_lemmas is not None else ""
            )
            return (
                f"PASS: BMC unreachable at k={self.bound} verified via DRAT"
                f"{suffix} ({self.elapsed_s:.2f}s)"
            )
        return f"FAIL at stage={self.stage}: {self.reason or 'unknown'}"


def dump_bmc_smtlib(artifact_bytes: bytes, bound: int) -> str:
    """Build the BMC unrolling at ``bound`` cycles, dump as SMT-LIB.

    Uses the same unrolling as ``_bmc.bmc(comp, bound, Z3Backend())``
    but extracts the assertion set as text via z3's ``to_smt2`` before
    ``check_sat`` is meaningful. The returned string is a stand-alone
    QF_ABV / QF_BV problem ending in ``(check-sat)``.
    """
    import z3

    parsed = from_text(artifact_bytes.decode("utf-8", "replace"))
    comp = compile_btor2(parsed.model)
    from gurdy.pairs.riscv_btor2.solvers.btor2_to_z3 import Z3Backend
    backend = Z3Backend()
    from gurdy.pairs.riscv_btor2.solvers._bmc import bmc

    # bmc now returns the solver on unreachable too, so we can grab the
    # post-solve assertion set as SMT-LIB. The verdict we get here is
    # informational — the caller's cert generation already determined
    # the verdict via dispatch; we just need the formula text.
    _, solver = bmc(comp, int(bound), backend)
    smt = solver.to_smt2()
    # Force bitwuzla to actually bit-blast (so ``--write-cnf`` produces
    # a CNF) — without this, bitwuzla's preprocessing often discharges
    # the unrolling before SAT and writes nothing.
    smt = "(set-option :preprocess false)\n" + smt
    if "(check-sat)" not in smt:
        smt = smt.rstrip() + "\n(check-sat)\n"
    return smt


def _ensure_drat_trim_built(image: str) -> str:
    """Ensure /tmp/drat-trim exists inside the image; return the path."""
    # We compile inside a one-shot container; the binary lives in /tmp
    # only for the lifetime of THAT container, not across `docker run`
    # invocations. So the verify_* helper always compiles+verifies in
    # the same container.
    return "/tmp/drat-trim"


def verify_bmc_drat_certificate(
    smtlib_text: str,
    bound: int,
    *,
    image: str = _DEFAULT_IMAGE,
    timeout_s: float = 120.0,
) -> BMCCertificateReport:
    """Run SMT-LIB → DIMACS → DRAT → drat-trim, all in one Docker shot."""
    start = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="bmc-cert-") as td:
        tdpath = Path(td)
        (tdpath / "model.smt2").write_text(smtlib_text)

        # Single shell pipeline:
        #   1. bitwuzla --write-cnf model.cnf model.smt2
        #   2. cadical model.cnf model.drat --no-binary
        #   3. cc drat-trim.c; drat-trim model.cnf model.drat
        script = f"""
set -e
cd /work
bitwuzla --write-cnf model.cnf model.smt2 > model.bitwuzla.out 2>&1
if ! grep -q '^unsat\\b' model.bitwuzla.out; then
  echo 'STAGE=dimacs'
  echo 'REASON=bitwuzla did not report unsat:'
  cat model.bitwuzla.out
  exit 11
fi
{_CADICAL_BIN} model.cnf model.drat --no-binary > model.cadical.out 2>&1 || true
if [ ! -s model.drat ]; then
  echo 'STAGE=drat'
  echo 'REASON=cadical produced no proof'
  tail -5 model.cadical.out
  exit 12
fi
if [ ! -x /tmp/drat-trim ]; then
  cp {_DRAT_TRIM_SRC} /tmp/drat-trim.c
  cc -O2 -o /tmp/drat-trim /tmp/drat-trim.c -lm
fi
/tmp/drat-trim model.cnf model.drat > model.drattrim.out 2>&1
if ! grep -q '^s VERIFIED' model.drattrim.out; then
  echo 'STAGE=verify'
  echo 'REASON=drat-trim did not VERIFY'
  tail -10 model.drattrim.out
  exit 13
fi
echo 'STAGE=done'
grep -E '^s VERIFIED|lemmas in core' model.drattrim.out
"""
        argv = [
            "docker", "run", "--rm",
            "-v", f"{tdpath}:/work",
            image,
            "sh", "-c", script,
        ]
        try:
            proc = subprocess.run(
                argv, capture_output=True, timeout=timeout_s + 30,
            )
        except subprocess.TimeoutExpired:
            return BMCCertificateReport(
                False, bound, "docker", reason="docker timeout",
                elapsed_s=time.monotonic() - start,
            )

    elapsed = time.monotonic() - start
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")

    if proc.returncode != 0:
        # Parse STAGE=... REASON=... from stdout to pinpoint failure.
        stage_m = re.search(r"^STAGE=(\w+)", out, re.MULTILINE)
        reason_m = re.search(r"^REASON=(.+)", out, re.MULTILINE)
        stage = stage_m.group(1) if stage_m else "exec"
        reason = reason_m.group(1) if reason_m else (err.strip()[:200] or "rc != 0")
        return BMCCertificateReport(
            False, bound, stage, elapsed_s=elapsed, reason=reason,
        )

    # Extract lemma count from drat-trim's "N of M lemmas in core" line.
    lemmas_m = re.search(r"(\d+)\s+of\s+\d+\s+lemmas in core", out)
    return BMCCertificateReport(
        True,
        bound,
        "done",
        drat_lemmas=int(lemmas_m.group(1)) if lemmas_m else None,
        elapsed_s=elapsed,
    )


__all__ = [
    "BMCCertificateReport",
    "dump_bmc_smtlib",
    "verify_bmc_drat_certificate",
]
