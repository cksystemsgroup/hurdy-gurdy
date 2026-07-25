"""Invariant re-discharge — the certificate route for an **unbounded**
``unreachable`` (issue #2 route (b); SOLVERS.md §5; the languages/btor2
README's witness-checker inventory): an engine that proves a property at
every depth carries an inductive invariant, and pono prints it
(``--show-invar``) as an SMT-LIB term over ``state<id>`` names. This
module extracts that invariant and re-discharges its three obligations
through the same operator mapping the bridge uses
(``pairs/btor2_smtlib/translate.py``), decided by every available SMT
engine:

  base:  Init ∧ C₀ ∧ ¬Inv₀             must be unsat  (holds initially)
  step:  Inv₀ ∧ C₀ ∧ T ∧ C₁ ∧ ¬Inv₁    must be unsat  (inductive)
  safe:  Inv₀ ∧ C₀ ∧ bad₀              must be unsat  (excludes the bad)

Constraints are assumed at both frames of the step obligation — sound
under the per-frame reading the bridge and the native checkers share (a
bad at step ``j`` counts only with every constraint holding at steps
``0..j``, so both ``C_i`` and ``C_{i+1}`` are known along any prefix a
counted bad could sit on).

The upgrade discipline mirrors ``solvers/proved.py``: nothing upgrades
unless a single engine discharges **all three** obligations, and the
result is **independent** only when some discharging engine's declared
lineage is disjoint from pono's (``solvers/brief.py`` — z3 qualifies;
bitwuzla never does, it sits inside pono's own smt-switch stack). Any
engine finding a model *refutes* the certificate and the refutation is
recorded — the fail-safe direction: a wrong or wrongly-mapped invariant
can only fail to upgrade, never fake a certificate. What remains in the
TCB is the bridge's BTOR2→SMT operator mapping itself, recorded — the
same residue the bit-blaster carries in the DRAT chain.

The pono/avr solver briefs still declare ``reachability/unreachable``
UNCHECKABLE: flipping that (a versioned admission event with gate
re-admission) is the follow-up this module is the prerequisite for, so
``tier`` here names what the artifact supports, not what the platform
books today.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any

from ..core.errors import Unsupported
from ..core.solver import Verdict
from ..pairs.btor2_smtlib.translate import (
    _DIRECTIVES,
    _as_system,
    _expr,
    _name,
    _ref,
    _sort_str,
)
from .native_btor2 import parse_verdict
from .pono_btor2 import (
    UNBOUNDED_FRAMES,
    UNBOUNDED_WALL_S,
    PonoUnavailable,
    find_pono,
)


@dataclass(frozen=True)
class RedischargeResult:
    ok: bool                        # one engine discharged every obligation
    independent: bool               # ... some discharger disjoint from pono
    tier: str | None                # "proved" | "reproducible" | None
    invariant: str | None           # the checked term (single-property runs)
    obligations: dict = field(default_factory=dict)   # name -> engine -> verdict
    refuted: list[str] = field(default_factory=list)  # obligations some engine sat
    engines: list[str] = field(default_factory=list)  # full dischargers
    tcb: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)


# ------------------------------------------------------------- extraction

def parse_invariant(output: str) -> str | None:
    """The ``INVAR: <term>`` line of a ``--show-invar`` run, with the
    s-expression balanced across following lines when the printer wraps.
    ``None`` when no invariant was printed."""
    lines = output.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("INVAR:"):
            continue
        term = stripped[len("INVAR:"):].strip()
        depth = term.count("(") - term.count(")")
        j = i
        while depth > 0 and j + 1 < len(lines):
            j += 1
            term += " " + lines[j].strip()
            depth += lines[j].count("(") - lines[j].count(")")
        return term or None
    return None


def extract_invariant(system: Any, *, mode: str = "ic3bits", prop: int = 0,
                      k: int = UNBOUNDED_FRAMES,
                      timeout_s: int = UNBOUNDED_WALL_S) -> str | None:
    """Run pono with ``--show-invar`` on one property and return the
    invariant term, or ``None`` when the run did not prove ``unsat`` (no
    verdict, ``sat``, or an engine that prints no invariant). The wall cap
    is the declared unbounded budget; ``TimeoutExpired`` propagates —
    mapping it to ``resource-out`` is the caller's booking."""
    binary = find_pono()
    if not binary:
        raise PonoUnavailable("pono not found (set $PONO or PATH)")
    if not isinstance(system, (str, bytes, bytearray)):
        raise Unsupported("invariant-redischarge",
                          "pono extraction needs BTOR2 text")
    text = (system.decode("utf-8")
            if isinstance(system, (bytes, bytearray)) else system)
    with tempfile.NamedTemporaryFile("w", suffix=".btor2",
                                     delete=False) as f:
        f.write(text)
        path = f.name
    try:
        proc = subprocess.run(
            [binary, "-e", mode, "-k", str(k), "-p", str(prop),
             "--show-invar", path],
            capture_output=True, text=True, timeout=timeout_s)
        out = proc.stdout + "\n" + proc.stderr
        if parse_verdict(out) is not Verdict.UNREACHABLE:
            return None
        return parse_invariant(out)
    finally:
        os.unlink(path)


# ------------------------------------------------------- obligation scripts

#: pono names BTOR2 terms by node id (``state4`` for node ``4 state``,
#: symbols ignored); the bridge names the same node per frame (``s4_0``).
_PONO_NAME = re.compile(r"\b(state|input)(\d+)\b")


def frame_invariant(sys: Any, invariant: str, t: int) -> str:
    """Rewrite pono's ``state<id>``/``input<id>`` names to the bridge's
    frame-``t`` names. A name whose node does not exist (or is not the
    kind the prefix claims) raises — an unmapped symbol must never reach
    a solver as an implicitly-free variable."""
    sys = _as_system(sys)

    def _sub(m: re.Match) -> str:
        kind, nid = m.group(1), int(m.group(2))
        node = sys.nodes.get(nid)
        if node is None or node.op != kind:
            raise Unsupported("invariant-redischarge",
                              f"invariant names unknown node {m.group(0)}")
        return _name(sys, nid, t)

    return _PONO_NAME.sub(_sub, invariant)


def _frame_lines(sys: Any, t: int) -> list[str]:
    """One frame of declarations/definitions — the bridge's per-step block
    (``translate.py``), reused verbatim so the operator mapping under the
    re-discharge is the one the native-vs-bridged cross-check already
    exercises (SOLVERS.md §7)."""
    lines: list[str] = []
    for s in sys.states():
        lines.append(f"(declare-fun s{s.id}_{t} () {_sort_str(sys, s.sort)})")
    for inp in (n for n in sys.nodes.values() if n.op == "input"):
        lines.append(f"(declare-fun i{inp.id}_{t} () {_sort_str(sys, inp.sort)})")
    for nid in sorted(nid for nid, n in sys.nodes.items()
                      if n.op not in _DIRECTIVES
                      and n.op not in ("state", "input")):
        node = sys.nodes[nid]
        lines.append(f"(define-fun n{nid}_{t} () {_sort_str(sys, node.sort)} "
                     f"{_expr(sys, node, t)})")
    return lines


def _constraint_asserts(sys: Any, t: int) -> list[str]:
    return [f"(assert (= {_ref(sys, n.refs[0], t)} #b1))"
            for n in sys.nodes.values() if n.op == "constraint"]


def obligation_scripts(system: Any, invariant: str, *,
                       prop: int = 0) -> dict[str, bytes]:
    """The three SMT-LIB scripts whose joint ``unsat`` re-discharges the
    invariant for ``bad`` property ``prop`` (pono is per-property). Each
    is a self-contained ``QF_ABV`` script; ``sat`` on any one refutes the
    certificate."""
    sys = _as_system(system)
    bads = sys.bads()
    if not 0 <= prop < len(bads):
        raise ValueError(f"property index {prop} out of range "
                         f"({len(bads)} bad properties)")
    inv0 = frame_invariant(sys, invariant, 0)
    inv1 = frame_invariant(sys, invariant, 1)
    init_asserts = [
        f"(assert (= {_name(sys, n.refs[0], 0)} {_ref(sys, n.refs[1], 0)}))"
        for n in sys.nodes.values() if n.op == "init"]
    next_asserts = [
        f"(assert (= {_name(sys, n.refs[0], 1)} {_ref(sys, n.refs[1], 0)}))"
        for n in sys.nodes.values() if n.op == "next"]
    bad0 = f"(= {_ref(sys, bads[prop].refs[0], 0)} #b1)"
    logic = ["(set-logic QF_ABV)"]
    scripts = {
        "base": (logic + _frame_lines(sys, 0) + init_asserts
                 + _constraint_asserts(sys, 0)
                 + [f"(assert (not {inv0}))", "(check-sat)"]),
        "step": (logic + _frame_lines(sys, 0) + _frame_lines(sys, 1)
                 + next_asserts + _constraint_asserts(sys, 0)
                 + _constraint_asserts(sys, 1)
                 + [f"(assert {inv0})", f"(assert (not {inv1}))",
                    "(check-sat)"]),
        "safe": (logic + _frame_lines(sys, 0) + _constraint_asserts(sys, 0)
                 + [f"(assert {inv0})", f"(assert {bad0})", "(check-sat)"]),
    }
    return {name: ("\n".join(lines) + "\n").encode("utf-8")
            for name, lines in scripts.items()}


# ------------------------------------------------------------ re-discharge

def redischarge_invariant(system: Any, invariant: str, *,
                          prop: int = 0) -> RedischargeResult:
    """Decide the three obligation scripts with every available SMT engine
    and account for the outcome (see the module docstring for the ``ok`` /
    ``independent`` / refutation discipline)."""
    from .brief import BRIEFS
    from .brief import independent as _lineage_independent
    from .inventory import available_smt_backends

    scripts = obligation_scripts(system, invariant, prop=prop)
    verdicts: dict[str, dict[str, str]] = {name: {} for name in scripts}
    per_engine: dict[str, list[Verdict]] = {}
    backends: dict[str, Any] = {}
    for backend in available_smt_backends():
        backends[backend.id] = backend
        for name, artifact in scripts.items():
            try:
                v = backend.decide(artifact).verdict
            except Exception:  # an engine that errors is skipped, not trusted
                verdicts[name][backend.id] = "error"
                continue
            verdicts[name][backend.id] = v.value
            per_engine.setdefault(backend.id, []).append(v)

    refuted = sorted(name for name, per in verdicts.items()
                     if any(v == Verdict.REACHABLE.value for v in per.values()))
    engines = sorted(e for e, vs in per_engine.items()
                     if len(vs) == len(scripts)
                     and all(v is Verdict.UNREACHABLE for v in vs))
    ok = bool(engines) and not refuted
    pono_brief = BRIEFS["pono"]
    indep = ok and any(_lineage_independent(backends[e], pono_brief)
                       for e in engines)
    tier = "proved" if ok and indep else ("reproducible" if ok else None)
    prov: dict[str, Any] = {"prop": prop}
    if ok and not indep:
        prov["independence_note"] = ("discharged only within pono's own "
                                     "declared lineage (solvers/brief.py) — "
                                     "not an independent re-validation")
    return RedischargeResult(
        ok=ok, independent=indep, tier=tier, invariant=invariant,
        obligations=verdicts, refuted=refuted, engines=engines,
        tcb=([f"{e}:re-discharge" for e in engines]
             + ["btor2-smtlib:operator-mapping"] if ok else []),
        provenance=prov)


def certify_unreachable(system: Any, *, mode: str = "ic3bits",
                        timeout_s: int = UNBOUNDED_WALL_S) -> RedischargeResult:
    """The end-to-end route: extract pono's invariant for **every** ``bad``
    property (pono is per-property; the unbounded claim is any-bad) and
    re-discharge each. ``ok`` only when every property's certificate
    checks; extraction stops at the first property pono does not prove —
    the walls are declared budgets, not free retries."""
    sys = _as_system(system)
    bads = sys.bads()
    if not bads:
        raise ValueError("system declares no bad property — nothing to certify")
    text = (system.decode("utf-8")
            if isinstance(system, (bytes, bytearray)) else str(system))
    results: list[RedischargeResult] = []
    obligations: dict[str, dict[str, str]] = {}
    refuted: list[str] = []
    prov: dict[str, Any] = {"mode": mode, "props": {}}
    for prop in range(len(bads)):
        inv = extract_invariant(text, mode=mode, prop=prop,
                                timeout_s=timeout_s)
        if inv is None:
            prov["props"][prop] = ("no invariant — pono did not prove unsat; "
                                   "remaining properties not attempted")
            return RedischargeResult(ok=False, independent=False, tier=None,
                                     invariant=None, obligations=obligations,
                                     refuted=refuted, engines=[], tcb=[],
                                     provenance=prov)
        r = redischarge_invariant(text, inv, prop=prop)
        results.append(r)
        for name, per in r.obligations.items():
            obligations[f"p{prop}/{name}"] = per
        refuted += [f"p{prop}/{name}" for name in r.refuted]
        prov["props"][prop] = {"ok": r.ok, "independent": r.independent,
                               "engines": r.engines}
    ok = all(r.ok for r in results)
    indep = ok and all(r.independent for r in results)
    engines = sorted(set.intersection(*(set(r.engines) for r in results)))
    return RedischargeResult(
        ok=ok, independent=indep,
        tier="proved" if ok and indep else ("reproducible" if ok else None),
        invariant=results[0].invariant if len(results) == 1 else None,
        obligations=obligations, refuted=refuted, engines=engines,
        tcb=([f"{e}:re-discharge" for e in engines]
             + ["btor2-smtlib:operator-mapping"] if ok else []),
        provenance=prov)
