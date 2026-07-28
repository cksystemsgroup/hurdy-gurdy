"""Berkeley ABC's ``pdr`` on the AIGER encoding — the registered
``abc`` solver brief's adapter (SOLVERS.md §2.1).

ABC's ``pdr`` is the bit-level IC3/PDR reference implementation, from
a codebase disjoint from every SMT stack on the platform. The BTOR2
question reaches it through btor2tools' ``btor2aiger``, which
bit-blasts through Boolector's AIG manager (the ``bitblast-api``
branch — the only Boolector that exports it): that toolchain is part
of the verdict's trust chain and is declared in the lineage, so ABC
agreement corroborates AVR (disjoint) but never btormc or pono (both
carry ``boolector``).

Two empirically-forced rules (host fixtures, 2026-07-26):

* **``fold`` before ``pdr`` is mandatory** — plain ``pdr`` ignores
  AIGER 1.9 invariant constraints and would call a constraint-blocked
  system reachable (caught on the discriminating fixture before the
  gate could catch it live).
* **One property per run** — btor2aiger emits one AIGER ``B`` entry
  per ``bad`` and ABC's ``pdr`` answer on a multi-bad file does not
  say which property it solved. The adapter masks down to a single
  ``bad`` at the BTOR2 level per run (bads are sinks — the same
  dropping the gate's ``mask_bads`` mutant relies on) and aggregates
  any-bad, exactly as the pono adapter loops ``--prop``.

Verdicts: "Output 0 ... was asserted in frame N" is ``reachable`` at
depth N; "Property proved" is the unbounded ``unreachable``. ABC's
counterexample is not yet translated back to a BTOR2 witness (the
named future obligation), so ``reachable`` carries no replayable
witness — the caller books it unconfirmed — and the returned frame is
metadata, not evidence. Unbounded runs book ``k=None``.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any

from ..core.solver import Verdict

#: The declared wall per property run (matches the amended portfolio
#: budget the campaign's other unbounded members play under).
ABC_WALL_S = 600

_ASSERTED = re.compile(r"was asserted in frame (\d+)")


class AbcUnavailable(RuntimeError):
    """Raised when abc or btor2aiger cannot be located."""


def find_abc() -> str | None:
    for cand in (os.environ.get("ABC"),
                 os.path.expanduser("~/abc-route/abc/abc")):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return shutil.which("abc")


def find_btor2aiger() -> str | None:
    for cand in (os.environ.get("BTOR2AIGER"),
                 os.path.expanduser(
                     "~/abc-route/btor2tools/build/bin/btor2aiger")):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return shutil.which("btor2aiger")


def _keep_bad(text: str, keep: int) -> str:
    """The single-property view: every ``bad`` line except the
    ``keep``-th dropped (bads are sinks — nothing references them)."""
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


def _count_bads(text: str) -> int:
    return sum(1 for ln in text.splitlines()
               if len(ln.split()) > 1 and ln.split()[0].isdigit()
               and ln.split()[1] == "bad")


class AbcBtor2Checker:
    id = "abc"

    #: The full trust chain of a verdict: ABC's own PDR + SAT layer,
    #: and the btor2aiger bit-blast through Boolector — declared, so
    #: nothing decided here can corroborate btormc or pono.
    lineage = ("abc", "boolector", "btor2tools")

    def __init__(self, abc: str | None = None,
                 btor2aiger: str | None = None) -> None:
        self.abc = abc or find_abc()
        self.btor2aiger = btor2aiger or find_btor2aiger()

    def available(self) -> bool:
        return bool(self.abc) and bool(self.btor2aiger)

    def decide(self, system: Any, *,
               wall_s: int = ABC_WALL_S) -> tuple[Verdict, str | None]:
        """One ``fold; pdr`` run per ``bad`` property, any-bad
        aggregated: ``reachable`` on the first asserted output (no
        replayable witness — the caller must treat it as unconfirmed),
        ``unreachable`` only when every property is proved.
        ``TimeoutExpired`` propagates (the wall is a declared budget;
        booking it is the caller's job)."""
        v, _frame = self.decide_frame(system, wall_s=wall_s)
        return v, None                    # cex not yet translated back

    def decide_frame(self, system: Any, *,
                     wall_s: int = ABC_WALL_S) -> tuple[Verdict, int | None]:
        """``decide`` plus the asserted frame on the reachable side —
        the depth the gate's decider needs to abstain on a
        counterexample beyond the census bound. The frame is ABC's
        claim, metadata rather than evidence."""
        if not self.available():
            raise AbcUnavailable(
                "abc/btor2aiger not found (set $ABC / $BTOR2AIGER)")
        text = (system.decode("utf-8")
                if isinstance(system, (bytes, bytearray)) else str(system))
        all_proved = True
        for prop in range(max(1, _count_bads(text))):
            verdict, frame = self._decide_prop(text, prop, wall_s)
            if verdict is Verdict.REACHABLE:
                return verdict, frame
            all_proved = all_proved and verdict is Verdict.UNREACHABLE
        return (Verdict.UNREACHABLE if all_proved
                else Verdict.UNKNOWN), None

    def _decide_prop(self, text: str, prop: int,
                     wall_s: int) -> tuple[Verdict, int | None]:
        from ..core import ledger

        single = _keep_bad(text, prop) if _count_bads(text) > 1 else text
        work = tempfile.mkdtemp(prefix="abc-")
        btor = os.path.join(work, "q.btor2")
        aig = os.path.join(work, "q.aig")
        with open(btor, "w", encoding="utf-8") as f:
            f.write(single)
        try:
            with ledger.timed(
                    "decide",
                    hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    engine="abc-pdr", language="btor2", k=None,
                    prop=prop, size=len(text)):
                conv = subprocess.run([self.btor2aiger, btor],
                                      capture_output=True, timeout=60)
                if conv.returncode != 0:
                    # encoding refused: abstain
                    return Verdict.UNKNOWN, None
                with open(aig, "wb") as f:
                    f.write(conv.stdout)
                proc = subprocess.run(
                    [self.abc, "-c", f"read {aig}; fold; pdr"],
                    capture_output=True, text=True, timeout=wall_s)
            out = proc.stdout + "\n" + proc.stderr
            m = _ASSERTED.search(out)
            if m:
                return Verdict.REACHABLE, int(m.group(1))
            if "Property proved" in out:
                return Verdict.UNREACHABLE, None
            return Verdict.UNKNOWN, None
        finally:
            shutil.rmtree(work, ignore_errors=True)
