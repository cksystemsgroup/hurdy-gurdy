"""Pono as BTOR2's **unbounded** native engine — the registered ``pono``
solver brief's adapter (SOLVERS.md §2.1; ``solvers/brief.py``).

``native_btor2`` wires the *bounded* composite (btormc BMC + canary-
controlled ``-kmax`` exhaustion). This module is the unbounded leg the
``native-procedure`` board demand ``d4c59dafc402`` cites: pono's
k-induction (``ind``) and bit-level IC3 (``ic3bits``) can answer
``unreachable`` **for every bound**, which is what closes a question
deeper BMC provably cannot (the campaign's exponential-in-k curves).

The adapter stays thin (SOLVERS.md §3): one pinned binary, one declared
wall cap per run (the shared ``DECIDE_TIMEOUT_S``), output normalized by
the shared ``parse_verdict``. On ``sat`` pono dumps a BTOR2-format
witness (``--witness --dump-btor2-witness``) so the caller can replay it
through the shared interpreter — the same evidence path btormc's ``.wit``
takes (SOLVERS.md §4); a run whose witness cannot be extracted still
carries its verdict, and the caller must treat it as unconfirmed.

Unbounded runs are booked with ``k=None``: there is no unrolling bound,
the wall is the budget — and the failure-mode curve fit
(``tools/saturation_report.py``) reads only bounded points, so the
probe curves stay one engine, one meaning.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from typing import Any

from ..core.solver import Verdict
from .native_btor2 import DECIDE_TIMEOUT_S, parse_verdict

#: The unbounded modes the brief's portfolio composes (player's choice,
#: SOLVERS.md §3 "enumerate, don't choose" — the adapter runs the one
#: mode it is handed).
UNBOUNDED_MODES = ("ic3bits", "ind")

#: Frame/depth ceiling handed to ``-k`` for unbounded modes: far beyond
#: any bound the campaign asks about — the wall cap is the real budget,
#: and this keeps ``check_until`` from stopping early.
UNBOUNDED_FRAMES = 10_000


class PonoUnavailable(RuntimeError):
    """Raised when the pono binary cannot be located."""


def _count_bads(text: str) -> int:
    """The number of ``bad`` properties. Pono checks exactly one
    property per run (``--prop``, default 0) where btormc checks them
    all — an adapter that read a single-property ``unsat`` as "the
    system is unreachable" would lie on multi-bad systems (caught by
    the solver gate's forced-bad mutants)."""
    count = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[0].isdigit() and parts[1] == "bad":
            count += 1
    return count


def find_pono() -> str | None:
    return os.environ.get("PONO") or shutil.which("pono")


class PonoBtor2Checker:
    id = "pono"

    #: Independence accounting (solvers/brief.py): pono's model-checking
    #: layer is its own codebase, but its verdicts come through the
    #: smt-switch default stack — bitwuzla, which descends from
    #: boolector. Declared in full, so btormc agreement stays honestly
    #: same-family (``reproducible``), never laundered to ``checked``.
    lineage = ("pono", "smt-switch", "bitwuzla", "boolector")

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or find_pono()

    def available(self) -> bool:
        return bool(self.binary) and (
            os.path.exists(self.binary)
            or shutil.which(self.binary) is not None)

    def decide(self, system: Any, *, mode: str = "ic3bits",
               k: int = UNBOUNDED_FRAMES) -> tuple[Verdict, str | None]:
        """Run one engine mode over **every** ``bad`` property (pono is
        per-property; the question is any-bad, btormc's reading):
        ``reachable`` on the first property that answers ``sat`` (with
        pono's dumped BTOR2-format witness, or ``None`` when extraction
        failed — the verdict then stands unconfirmed and the caller
        must not book ``reachable`` on it); ``unreachable`` only when
        every property answers ``unsat``; anything mixed stays
        ``unknown``. ``TimeoutExpired`` propagates: the wall cap is a
        declared budget (per property run) and mapping it to
        ``resource-out`` is the caller's booking."""
        binary = self.binary
        if not binary or not (os.path.exists(binary)
                              or shutil.which(binary) is not None):
            raise PonoUnavailable("pono not found (set $PONO or PATH)")
        text = (system.decode("utf-8")
                if isinstance(system, (bytes, bytearray)) else str(system))
        all_unsat = True
        for prop in range(max(1, _count_bads(text))):
            verdict, witness = self._decide_prop(text, mode, k, prop)
            if verdict is Verdict.REACHABLE:
                return verdict, witness
            all_unsat = all_unsat and verdict is Verdict.UNREACHABLE
        return (Verdict.UNREACHABLE if all_unsat
                else Verdict.UNKNOWN), None

    def _decide_prop(self, text: str, mode: str, k: int,
                     prop: int) -> tuple[Verdict, str | None]:
        from ..core import ledger

        with tempfile.NamedTemporaryFile("w", suffix=".btor2",
                                         delete=False) as f:
            f.write(text)
            path = f.name
        witpath = path + ".wit"
        try:
            with ledger.timed(
                    "decide",
                    hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    engine=f"pono-{mode}", language="btor2",
                    k=(k if mode == "bmc" else None), prop=prop,
                    size=len(text)):
                proc = subprocess.run(
                    [self.binary, "-e", mode, "-k", str(k),
                     "-p", str(prop), "--witness",
                     "--dump-btor2-witness", witpath, path],
                    capture_output=True, text=True,
                    timeout=DECIDE_TIMEOUT_S)
            verdict = parse_verdict(proc.stdout + "\n" + proc.stderr)
            witness = None
            if verdict is Verdict.REACHABLE and os.path.exists(witpath):
                with open(witpath, encoding="utf-8") as f:
                    witness = f.read()
            return verdict, witness
        finally:
            os.unlink(path)
            if os.path.exists(witpath):
                os.unlink(witpath)
