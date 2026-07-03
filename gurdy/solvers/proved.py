"""The `proved`-tier pipeline for certified **unreachability** (SOLVERS.md §5-6;
issue #2) — the unreachable counterpart to the reachable witness replays
(`btor2-smtlib.reach`, `languages/btor2.check_witness`).

A `bad`-unreachability claim (`unsat` of the bounded bridge query) is certified
two ways, of increasing strength:

1. **Multi-engine corroboration** (SOLVERS.md §6: ≥2 independent solvers agree =
   `checked`). The same SMT artifact is decided by **z3** and by **bitwuzla** —
   different codebases — and they must agree `unsat`. This is the *unreachable*
   analogue of the native-vs-bridged cross-check, and it runs anywhere both
   engines are present.

2. **A bit-blasted certificate** (SOLVERS.md §5 row 4: `unsat` bit-blasted →
   DRAT/LRAT → a dedicated proof checker = `proved`). **bitwuzla** bit-blasts the
   BV query to DIMACS (`--write-cnf`), **cadical** refutes it and emits a DRAT
   proof, and an **independent** checker re-validates the proof. Two checker
   rungs, by strength: the preferred chain elaborates the DRAT to LRAT with
   `drat-trim` (untrusted elaborator) and re-validates with **`cake_lpr`**, the
   *formally verified* CakeML checker; without `cake_lpr`, `drat-trim` itself
   checks the DRAT (independent but unverified). The producers (bitwuzla,
   cadical) and the elaborator are untrusted; the checker is the trust anchor.
   The bit-blaster's faithfulness (BV → CNF) is in the TCB — the known
   limitation that keeps this short of trust-free BV (issue #2).

On a host without any proof checker the certificate is *produced* but not
independently checked, so the result stays `checked` and records
`proved`-pending. The TCB is always recorded (SOLVERS.md §6)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any

from ..core.solver import Verdict
from ..pairs.btor2_smtlib.translate import translate


class CheckerUnavailable(RuntimeError):
    """Raised when no independent DRAT/LRAT proof checker can be located."""


@dataclass(frozen=True)
class ProvedResult:
    verdict: Verdict
    tier: str                       # "proved" | "checked" | "reproducible"
    method: str                     # how it was established
    engines: list[str] = field(default_factory=list)   # agreeing solvers
    certificate: bytes | None = None     # the DRAT proof, when produced
    checker_ok: bool | None = None       # independent checker result (None = not run)
    tcb: list[str] = field(default_factory=list)        # trusted computing base (§6)
    provenance: dict = field(default_factory=dict)


# ------------------------------------------------------------------ tools

def _find(*names: str) -> str | None:
    for n in names:
        if os.environ.get(n.upper().replace("-", "_")):
            return os.environ[n.upper().replace("-", "_")]
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def bitblast_cnf(artifact: bytes) -> str | None:
    """Bit-blast an SMT (QF_BV) artifact to DIMACS CNF via ``bitwuzla
    --write-cnf`` — the independent bit-blaster (not z3's, whose tactic solves
    the goal during preprocessing). Returns ``None`` when bitwuzla decides the
    query *without* bit-blasting (a closed system folded away in preprocessing,
    so there is no SAT-level CNF to certify). Raises if bitwuzla is absent."""
    bw = _find("bitwuzla")
    if not bw:
        raise CheckerUnavailable("bitwuzla not found (needed to bit-blast)")
    text = artifact.decode("utf-8") if isinstance(artifact, (bytes, bytearray)) else str(artifact)
    with tempfile.TemporaryDirectory() as d:
        smt, cnf = os.path.join(d, "q.smt2"), os.path.join(d, "q.cnf")
        with open(smt, "w") as f:
            f.write(text)
        subprocess.run([bw, "--write-cnf", cnf, smt], capture_output=True,
                       text=True, timeout=300)
        if not os.path.exists(cnf):
            return None
        with open(cnf) as f:
            return f.read()


def drat_proof(cnf: str) -> tuple[bool, bytes | None]:
    """Refute a DIMACS CNF with cadical, returning ``(is_unsat, drat_bytes)``.
    A ``drat`` proof is returned only on UNSAT (cadical exit code 20)."""
    cad = _find("cadical")
    if not cad:
        raise CheckerUnavailable("cadical not found (needed to emit a DRAT proof)")
    with tempfile.TemporaryDirectory() as d:
        cnf_p, drat_p = os.path.join(d, "q.cnf"), os.path.join(d, "q.drat")
        with open(cnf_p, "w") as f:
            f.write(cnf)
        proc = subprocess.run([cad, "--no-binary", "-q", cnf_p, drat_p],
                              capture_output=True, text=True, timeout=300)
        if proc.returncode != 20:  # 20 = UNSAT; 10 = SAT; else error/unknown
            return False, None
        with open(drat_p, "rb") as f:
            return True, f.read()


def check_drat(cnf: str, drat: bytes) -> bool:
    """Independently verify a DRAT proof against its CNF with ``drat-trim``.
    Raises ``CheckerUnavailable`` when no checker is present. Returns whether
    it VERIFIED."""
    checker = _find("drat-trim", "drattrim")
    if not checker:
        raise CheckerUnavailable("no DRAT checker found (drat-trim)")
    with tempfile.TemporaryDirectory() as d:
        cnf_p, drat_p = os.path.join(d, "q.cnf"), os.path.join(d, "q.drat")
        with open(cnf_p, "w") as f:
            f.write(cnf)
        with open(drat_p, "wb") as f:
            f.write(drat)
        proc = subprocess.run([checker, cnf_p, drat_p], capture_output=True,
                              text=True, timeout=300)
    # The status line is exactly "s VERIFIED"; a failure prints
    # "s NOT VERIFIED", which a naive substring match would accept — the
    # vacuity a negative control caught (a bogus proof against a
    # satisfiable CNF must come back False).
    return any(line.strip() == "s VERIFIED" or line.startswith("s VERIFIED ")
               for line in (proc.stdout + proc.stderr).splitlines())


def elaborate_lrat(cnf: str, drat: bytes) -> bytes | None:
    """Elaborate a DRAT proof into LRAT with ``drat-trim -L`` — an *untrusted*
    transformation (the verified checker re-validates the result against the
    CNF from scratch, so a wrong elaboration can only cause a FAIL, never a
    wrong VERIFIED). Returns ``None`` when elaboration fails."""
    tool = _find("drat-trim", "drattrim")
    if not tool:
        raise CheckerUnavailable("drat-trim not found (needed to elaborate LRAT)")
    with tempfile.TemporaryDirectory() as d:
        cnf_p, drat_p = os.path.join(d, "q.cnf"), os.path.join(d, "q.drat")
        lrat_p = os.path.join(d, "q.lrat")
        with open(cnf_p, "w") as f:
            f.write(cnf)
        with open(drat_p, "wb") as f:
            f.write(drat)
        proc = subprocess.run([tool, cnf_p, drat_p, "-L", lrat_p],
                              capture_output=True, text=True, timeout=300)
        if not os.path.exists(lrat_p):
            return None
        ok = any(line.strip() == "s VERIFIED" or line.startswith("s VERIFIED ")
                 for line in (proc.stdout + proc.stderr).splitlines())
        if not ok:
            return None
        with open(lrat_p, "rb") as f:
            return f.read()


def check_lrat_verified(cnf: str, lrat: bytes) -> bool:
    """Verify an LRAT proof against its CNF with ``cake_lpr`` — the
    **formally verified** checker (CakeML: the checker's soundness is
    machine-proved down to the binary). Raises ``CheckerUnavailable`` when
    absent. Returns whether it VERIFIED.

    Caution twin to the drat-trim lesson: cake_lpr exits 0 even when
    checking FAILS (failure prints ``c Checking failed ...``); the exact
    status line ``s VERIFIED UNSAT`` is the only success signal."""
    checker = _find("cake_lpr")
    if not checker:
        raise CheckerUnavailable("cake_lpr not found (verified LRAT checker)")
    with tempfile.TemporaryDirectory() as d:
        cnf_p, lrat_p = os.path.join(d, "q.cnf"), os.path.join(d, "q.lrat")
        with open(cnf_p, "w") as f:
            f.write(cnf)
        with open(lrat_p, "wb") as f:
            f.write(lrat)
        proc = subprocess.run([checker, cnf_p, lrat_p], capture_output=True,
                              text=True, timeout=300)
    return any(line.strip() == "s VERIFIED UNSAT"
               for line in (proc.stdout + proc.stderr).splitlines())


# ------------------------------------------------------------------ orchestration

def corroborate(artifact: bytes) -> dict[str, Any]:
    """Decide ``artifact`` with every *available* independent SMT engine (the
    shared inventory: z3, bitwuzla, boolector, cvc5, yices2 — whichever are
    present). Returns per-engine verdicts, whether ≥2 agree, and — if they
    diverge — a ``disagreement`` map, which localizes a translator-or-solver bug
    (SOLVERS.md §7) rather than silently trusting one engine."""
    from .inventory import available_smt_backends

    verdicts: dict[str, Verdict] = {}
    for backend in available_smt_backends():
        try:
            verdicts[backend.id] = backend.decide(artifact).verdict
        except Exception:  # an engine that errors mid-run is simply skipped
            continue
    vals = set(verdicts.values())
    return {"verdicts": verdicts,
            "agree": len(verdicts) >= 2 and len(vals) == 1,
            "verdict": next(iter(vals)) if len(vals) == 1 else Verdict.UNKNOWN,
            "disagreement": ({e: v.value for e, v in verdicts.items()}
                             if len(vals) > 1 else None)}


def prove_unreachable(system: Any, k: int) -> ProvedResult:
    """Certify that no ``bad`` is reachable within ``k`` steps, as strongly as the
    available tools allow (SOLVERS.md §5-6). See the module docstring."""
    artifact = translate({"system": system, "k": k})
    corr = corroborate(artifact)
    engines = sorted(corr["verdicts"])
    prov: dict[str, Any] = {"k": k, "verdicts": {e: v.value for e, v in corr["verdicts"].items()}}
    if corr["disagreement"]:  # engines diverged — a translator-or-solver bug (§7)
        prov["disagreement"] = corr["disagreement"]

    # Only an agreed unsat is an unreachability claim worth certifying.
    if corr["verdict"] is not Verdict.UNREACHABLE:
        return ProvedResult(verdict=corr["verdict"],
                            tier="checked" if corr["agree"] else "reproducible",
                            method="multi-engine", engines=engines,
                            tcb=engines, provenance=prov)

    tier = "checked" if corr["agree"] else "reproducible"
    tcb = list(engines)

    # Try to produce and independently check a bit-blasted DRAT certificate.
    certificate: bytes | None = None
    checker_ok: bool | None = None
    method = "multi-engine"
    try:
        cnf = bitblast_cnf(artifact)
        if cnf is None:
            prov["certificate_skipped"] = "decided without bit-blasting (no CNF to certify)"
        elif (proof := drat_proof(cnf))[0] and proof[1] is not None:
            certificate = proof[1]
            method = "bitblast-drat"
            prov["bitblaster"], prov["sat_solver"] = "bitwuzla", "cadical"
            try:
                # Prefer the *formally verified* checker: elaborate the DRAT
                # to LRAT (drat-trim, untrusted — a wrong elaboration can only
                # FAIL the verified re-check, never fake a VERIFIED) and
                # validate with cake_lpr. If cake_lpr *rejects*, do NOT fall
                # back to the unverified checker: record the rejection.
                lrat = (elaborate_lrat(cnf, certificate)
                        if _find("cake_lpr") else None)
                if lrat is not None:
                    checker_ok = check_lrat_verified(cnf, lrat)
                    method = "bitblast-drat-lrat"
                    prov["checker"] = _find("cake_lpr")
                    prov["elaborator"] = "drat-trim (untrusted)"
                    prov["lrat_bytes"] = len(lrat)
                    if checker_ok:
                        tier = "proved"
                        tcb = ["bitwuzla:bit-blast", "cake_lpr:verified"]
                else:
                    # No verified checker (or elaboration failed): the
                    # independent-but-unverified drat-trim check.
                    checker_ok = check_drat(cnf, certificate)
                    prov["checker"] = _find("drat-trim", "drattrim")
                    if checker_ok:
                        tier = "proved"
                        tcb = ["bitwuzla:bit-blast",
                               os.path.basename(prov["checker"] or "drat-trim")]
            except CheckerUnavailable:
                prov["proved_pending"] = "no independent DRAT/LRAT checker on host"
    except CheckerUnavailable as exc:
        prov["certificate_skipped"] = str(exc)

    return ProvedResult(verdict=Verdict.UNREACHABLE, tier=tier, method=method,
                        engines=engines, certificate=certificate,
                        checker_ok=checker_ok, tcb=tcb, provenance=prov)
