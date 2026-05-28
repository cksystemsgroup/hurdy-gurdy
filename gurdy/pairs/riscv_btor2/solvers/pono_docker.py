"""Pono via local Docker, with ``proved``-path certificate extraction.

Mirrors ``z3spacer.Z3SpacerSolver``'s contract: on ``proved`` verdicts
populates ``RawSolverResult.payload`` with
``{invariant_smtlib, state_nid_order, canonical_artifact}`` so the
same ``verify_certificate`` checker can re-verify the cert.

Why a separate adapter from ``pono.py``:

- Pono v2.0.0's BTOR2 parser is stricter than the standard and rejects
  hurdy-gurdy's emitted models. This adapter prepends a canonicalize
  pass (see ``btor2_for_pono``) so Pono can read the file.
- macOS hosts don't get Pono natively — the project builds it inside
  the bench Docker image. This adapter runs Pono through ``docker run``.
- The invariant returned by Pono uses ``state<idx>`` naming, where
  ``<idx>`` is the positional index of the state in the BTOR2 file.
  This adapter translates that to the ``s_<nid>`` naming the
  certificate checker expects.
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

from gurdy.core.dispatch.backend import InProcessSolverBackend
from gurdy.core.dispatch.result import RawSolverResult
from gurdy.pairs.riscv_btor2.btor2.parser import from_text
from gurdy.pairs.riscv_btor2.lift.btor2_for_pono import (
    INVAR_RE,
    INVARIANT_ENGINES,
    build_invariant_smtlib,
    canonicalize_for_pono,
)
from gurdy.pairs.riscv_btor2.solvers._bmc import compile_btor2


_DEFAULT_ENGINE = "ic3sa"
_DEFAULT_IMAGE = os.environ.get(
    "HURDY_PONO_DOCKER_IMAGE", "christophkirsch/hurdy-gurdy-bench:latest"
)


@dataclass
class PonoDockerSolver(InProcessSolverBackend):
    name: str = "pono-docker"
    image: str = _DEFAULT_IMAGE
    engine: str = _DEFAULT_ENGINE
    bound: int = 30
    timeout_s: float = 120.0

    def dispatch(
        self, artifact_bytes: bytes, directive: Any
    ) -> RawSolverResult:
        start = time.monotonic()

        engine = str(
            (getattr(directive, "extra_options", {}) or {}).get("engine", self.engine)
        )
        bound = getattr(directive, "bound", None) or self.bound
        timeout = getattr(directive, "timeout", None) or self.timeout_s

        try:
            canon_bytes = canonicalize_for_pono(artifact_bytes.decode("utf-8", "replace"))
        except Exception as e:
            return RawSolverResult(
                verdict="error", elapsed=time.monotonic() - start, engine=self.name,
                reason=f"canonicalize failed: {type(e).__name__}: {e}",
            )

        with tempfile.TemporaryDirectory(prefix="pono-cert-") as td:
            tdpath = Path(td)
            (tdpath / "model.btor2").write_bytes(canon_bytes)
            argv = [
                "docker", "run", "--rm",
                "-v", f"{tdpath}:/work",
                self.image,
                "timeout", str(int(timeout)),
                "pono", "-e", engine, "-k", str(int(bound)),
                "--show-invar", "/work/model.btor2",
            ]
            try:
                proc = subprocess.run(
                    argv, capture_output=True, timeout=timeout + 30,
                )
            except subprocess.TimeoutExpired:
                return RawSolverResult(
                    verdict="unknown", elapsed=time.monotonic() - start,
                    engine=self.name, reason="docker timeout",
                )

        elapsed = time.monotonic() - start
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")

        # Engine error / model rejection.
        if "error" in out and "INVAR" not in out:
            head = (out or err).strip().splitlines()
            reason = head[0] if head else "pono error"
            return RawSolverResult(
                verdict="error", elapsed=elapsed, engine=self.name, reason=reason,
            )

        # Verdict.
        if re.search(r"^unsat\b", out, re.MULTILINE):
            verdict = "proved" if engine in INVARIANT_ENGINES else "unreachable"
        elif re.search(r"^sat\b", out, re.MULTILINE):
            verdict = "reachable"
        else:
            return RawSolverResult(
                verdict="unknown", elapsed=elapsed, engine=self.name,
                reason=(out.strip() or err.strip() or "no output")[:200],
            )

        payload: Any = None
        if verdict == "proved":
            # Pono writes "INVAR:" to stderr (verdict goes to stdout).
            m = INVAR_RE.search(err) or INVAR_RE.search(out)
            if m is None:
                return RawSolverResult(
                    verdict=verdict, elapsed=elapsed, engine=self.name,
                    reason="proved but no INVAR line in stdout/stderr",
                )
            invar_body = m.group(1).strip()
            parsed = from_text(canon_bytes.decode("utf-8", "replace"))
            comp = compile_btor2(parsed.model)
            payload = {
                "invariant_smtlib": build_invariant_smtlib(invar_body, comp),
                "state_nid_order": list(comp.state_nids),
                "canonical_artifact": canon_bytes,
            }

        return RawSolverResult(
            verdict=verdict, elapsed=elapsed, engine=self.name, payload=payload,
        )


__all__ = ["PonoDockerSolver"]
