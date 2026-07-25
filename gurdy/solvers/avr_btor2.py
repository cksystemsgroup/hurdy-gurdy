"""AVR as BTOR2's second unbounded native engine — the registered
``avr`` solver brief's adapter (SOLVERS.md §2.1; ``solvers/brief.py``).

AVR (Averroes v2, HWMCC'20 winner) proves reachability properties by
IC3-style equality abstraction over the word-level netlist. It is the
first engine on the platform whose declared lineage — ``(avr, yices)``,
host-built Yices2-only with the Boolector and MathSAT backends compiled
out — is disjoint from both btormc's (``boolector``) and pono's
(``pono, smt-switch, bitwuzla, boolector``): its unbounded agreement is
the platform's first cross-lineage corroboration for the campaign's
``bounded: false`` claims (``solvers/brief.independent``).

The adapter stays thin (SOLVERS.md §3): one pinned checkout driven
through ``avr.py`` (``--backend y2``), the declared budgets passed
straight through (``--timeout`` CPU-seconds, ``--memout`` MB — the
RAM-discipline cap), the verdict read from the machine-readable
``result.pr`` (``avr-h``/``avr-h_triv`` proof, ``avr-v`` cex,
``avr-f_to``/``avr-f_to_q``/``avr-f_mo`` spent budget, anything else an
abstention). AVR checks **all** bad properties natively (any-bad — no
per-property loop needed). On ``v`` it dumps a BTOR2-format witness
(``cex.witness``) the shared interpreter replays — the same evidence
path btormc's ``.wit`` takes; a witness AVR's abstraction leaves
degenerate (no input assignments under a constraint) will fail replay
and the caller must treat the verdict as unconfirmed.

An AVR proof is unbounded (``h`` = the property holds at every depth),
so runs are booked with ``k=None``: the failure-mode curve fits read
only bounded points, one engine, one meaning per curve.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from typing import Any

from ..core.solver import Verdict

#: The declared budgets, matching the amended portfolio wall
#: (brief.py): CPU-seconds handed to ``avr.py --timeout``; the adapter
#: adds a 60 s wall grace before killing the process group.
AVR_WALL_S = 600

#: ``avr.py --memout`` in MB — the RAM-discipline cap (16 GB host,
#: prior OOM history: half the machine, never the default 118 GB).
AVR_MEMOUT_MB = 8192

#: result.pr vocabulary (src/reach/reach_core.cpp) → verdicts.
_RESULTS = {
    "avr-h": Verdict.UNREACHABLE,
    "avr-h_triv": Verdict.UNREACHABLE,
    "avr-v": Verdict.REACHABLE,
    "avr-f_to": Verdict.RESOURCE_OUT,
    "avr-f_to_q": Verdict.RESOURCE_OUT,
    "avr-f_mo": Verdict.RESOURCE_OUT,
}


class AvrUnavailable(RuntimeError):
    """Raised when the AVR checkout cannot be located."""


def find_avr() -> str | None:
    """The AVR checkout directory (containing ``avr.py``): ``$AVR`` or
    the conventional host build at ``~/avr``."""
    for cand in (os.environ.get("AVR"), os.path.expanduser("~/avr")):
        if cand and os.path.isfile(os.path.join(cand, "avr.py")):
            return cand
    return None


class AvrBtor2Checker:
    id = "avr"

    #: Independence accounting (solvers/brief.py): the host build
    #: compiles only the Yices 2 backend (ENABLE_BT=0, ENABLE_M5=0),
    #: so the ancestry is exactly avr + yices — disjoint from every
    #: other btor2 engine on the platform.
    lineage = ("avr", "yices")

    def __init__(self, avr_dir: str | None = None) -> None:
        self.avr_dir = avr_dir or find_avr()

    def available(self) -> bool:
        return bool(self.avr_dir) and os.path.isfile(
            os.path.join(self.avr_dir, "avr.py"))

    def decide(self, system: Any, *,
               wall_s: int = AVR_WALL_S) -> tuple[Verdict, str | None]:
        """One wall-capped AVR run over every ``bad`` property (native
        any-bad): ``unreachable`` is an unbounded proof, ``reachable``
        carries the dumped BTOR2 witness (or ``None`` when the file is
        missing — the verdict then stands unconfirmed and the caller
        must not book ``reachable`` on it). ``TimeoutExpired``
        propagates only for the wall-grace kill; AVR's own ``f_to`` /
        ``f_mo`` self-reports map to ``resource-out`` directly."""
        if not self.available():
            raise AvrUnavailable("avr not found (set $AVR or build ~/avr)")
        text = (system.decode("utf-8")
                if isinstance(system, (bytes, bytearray)) else str(system))
        from ..core import ledger

        work = tempfile.mkdtemp(prefix="avr-")
        path = os.path.join(work, "q.btor2")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            with ledger.timed(
                    "decide",
                    hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    engine="avr-y2", language="btor2", k=None,
                    size=len(text)):
                proc = subprocess.Popen(
                    [sys.executable, os.path.join(self.avr_dir, "avr.py"),
                     "-o", work, "-n", "q", "--backend", "y2",
                     "--witness", "--timeout", str(wall_s),
                     "--memout", str(AVR_MEMOUT_MB), path],
                    cwd=self.avr_dir, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True)
                try:
                    proc.wait(timeout=wall_s + 60)
                except subprocess.TimeoutExpired:
                    # avr.py's own CPU timer should have fired; the
                    # wall grace catches a hung frontend. Kill the
                    # whole session (avr.py spawns vwn/dpa/reach_y2).
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    raise
            outdir = os.path.join(work, "work_q")
            try:
                with open(os.path.join(outdir, "result.pr"),
                          encoding="utf-8") as f:
                    result = f.read().strip()
            except FileNotFoundError:
                return Verdict.UNKNOWN, None
            verdict = _RESULTS.get(result, Verdict.UNKNOWN)
            witness = None
            witpath = os.path.join(outdir, "cex.witness")
            if verdict is Verdict.REACHABLE and os.path.exists(witpath):
                with open(witpath, encoding="utf-8") as f:
                    witness = f.read()
            return verdict, witness
        finally:
            shutil.rmtree(work, ignore_errors=True)
