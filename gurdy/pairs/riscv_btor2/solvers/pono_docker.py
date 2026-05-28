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
from gurdy.pairs.riscv_btor2.lift.btor2_for_pono import canonicalize_for_pono
from gurdy.pairs.riscv_btor2.solvers._bmc import (
    Compiled,
    compile_btor2,
    find_sort_for,
)


# Engines that emit invariants and are sound for proved/unreachable claims.
# ic3sa supports arrays + emits invariants; ic3bits/mbic3 don't support
# arrays; ind doesn't expose the invariant.
_DEFAULT_ENGINE = "ic3sa"
_INVARIANT_ENGINES = frozenset({"ic3sa", "ic3ia"})

_DEFAULT_IMAGE = os.environ.get(
    "HURDY_PONO_DOCKER_IMAGE", "christophkirsch/hurdy-gurdy-bench:latest"
)

_INVAR_RE = re.compile(r"^INVAR:\s*(.+)$", re.MULTILINE)
_STATE_REF_RE = re.compile(r"\bstate(\d+)\b")


def _sort_sexpr(sort_nid: int, comp: Compiled) -> str:
    if sort_nid in comp.sort_widths:
        return f"(_ BitVec {comp.sort_widths[sort_nid]})"
    if sort_nid in comp.array_meta:
        idx_s, elt_s = comp.array_meta[sort_nid]
        return f"(Array (_ BitVec {comp.sort_widths[idx_s]}) (_ BitVec {comp.sort_widths[elt_s]}))"
    raise ValueError(f"unknown sort nid {sort_nid}")


def _build_invariant_smtlib(invar_body: str, comp: Compiled) -> str:
    """Translate Pono's invariant body into our SMT-LIB+s_<nid> form.

    Pono prints ``state<nid>`` references where ``<nid>`` is the BTOR2
    node id of the state (not a positional index). We rewrite to
    ``s_<nid>`` and prepend the declare-const block the checker expects.
    """
    state_nid_set = set(comp.state_nids)

    def _sub(m: re.Match[str]) -> str:
        nid = int(m.group(1))
        if nid not in state_nid_set:
            raise ValueError(
                f"INVAR references state{nid} but nid {nid} is not a state "
                f"in the canonical model (states: {sorted(state_nid_set)})"
            )
        return f"s_{nid}"

    body = _STATE_REF_RE.sub(_sub, invar_body)

    decls = []
    for nid in comp.state_nids:
        decls.append(f"(declare-const s_{nid} {_sort_sexpr(find_sort_for(nid, comp), comp)})")
    return "\n".join(decls) + "\n(assert " + body + ")\n"


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
            verdict = "proved" if engine in _INVARIANT_ENGINES else "unreachable"
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
            m = _INVAR_RE.search(err) or _INVAR_RE.search(out)
            if m is None:
                return RawSolverResult(
                    verdict=verdict, elapsed=elapsed, engine=self.name,
                    reason="proved but no INVAR line in stdout/stderr",
                )
            invar_body = m.group(1).strip()
            parsed = from_text(canon_bytes.decode("utf-8", "replace"))
            comp = compile_btor2(parsed.model)
            payload = {
                "invariant_smtlib": _build_invariant_smtlib(invar_body, comp),
                "state_nid_order": list(comp.state_nids),
                "canonical_artifact": canon_bytes,
            }

        return RawSolverResult(
            verdict=verdict, elapsed=elapsed, engine=self.name, payload=payload,
        )


__all__ = ["PonoDockerSolver"]
