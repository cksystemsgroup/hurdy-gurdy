"""The independence audit — the gate check that a pair's lowering was built
WITHOUT cribbing the oracle, so its Sail-validation power is genuine.

Per ARCHITECTURE.md anti-gaming invariant #4, an independent (``differential_only``
/ sandboxed) pair must satisfy:

  * **no Sail behavior** — it does not read the Sail emulator oracle
    (``realizations/emulator/oracle.py`` / ``sail_riscv_sim``);
  * **no Sail source / reference crib** — it does not vendor Sail model source
    and does not read the Sail-derived reference (``reference_rv64``);
  * **no machine-model crib** — it does not use the Sail-derived BTOR2 machine
    tool's *construction* internals (``tools.sail_btor2_machine.{generate,
    verify,isa,control}``). The RUNTIME machine path (``...instantiate``) is
    allowed — ``construction: forbidden`` bars it only during the build;
  * **query log empty (or within the training partition)** — for
    ``differential_only`` the agent made zero gate-oracle queries; for
    ``held_out_behavioral`` only training-partition queries.

This audit reads the pair's own source under ``gurdy/hops/<id>/`` (the artifact
the agent produced) and any recorded construction query log. It is a *static +
dynamic* check, and it is non-vacuous: a forbidden import is reported with its
file and line. A clean result is required for merge of a sandboxed hop
(``merge_policy.independence_required``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from gurdy.core.manifest import Manifest
from gate.merge_policy import independence_required

_HOPS_DIR = Path(__file__).resolve().parents[1] / "gurdy" / "hops"

# (label, regex, why) — references that betray a Sail/machine crib. The runtime
# machine path tools.sail_btor2_machine.instantiate is deliberately NOT matched.
_FORBIDDEN = [
    ("sail-behavior",
     re.compile(r"sail_riscv_sim|realizations[./]emulator|emulator\.oracle|emulator\s+import"),
     "reads the Sail emulator (behavioral oracle)"),
    ("sail-reference",
     re.compile(r"\breference_rv64\b"),
     "reads the Sail-derived reference semantics"),
    ("machine-crib",
     re.compile(r"sail_btor2_machine\.(?:generate|verify|isa|control|reference)\b"
                r"|from\s+tools\.sail_btor2_machine\.(?:generate|verify|isa|control)\b"),
     "cribs the Sail-derived machine model's construction internals"),
]


@dataclass
class IndependenceReport:
    ok: bool
    findings: list[str] = field(default_factory=list)   # violations (block merge)
    notes: list[str] = field(default_factory=list)      # informational


def scan_source(text: str, where: str = "<source>") -> list[str]:
    """Return crib findings in one source text (factored out for testing)."""
    out: list[str] = []
    # ignore comments/strings only crudely: we WANT to catch cribs even in
    # comments (a pasted Sail clause in a comment is still a leak), so scan raw.
    for label, rx, why in _FORBIDDEN:
        for m in rx.finditer(text):
            line = text[: m.start()].count("\n") + 1
            out.append(f"{where}:{line}: {label} — {why} ({m.group(0)!r})")
    return out


def audit(manifest: Manifest) -> IndependenceReport:
    """Audit one hop's construction for independence violations."""
    if not independence_required(manifest):
        return IndependenceReport(
            True, notes=[f"independence not required (oracle_access={manifest.oracle_access!r})"])

    pkg = _HOPS_DIR / manifest.id
    if not pkg.is_dir():
        return IndependenceReport(False, findings=[f"hop package {pkg} not found"])

    findings: list[str] = []
    notes: list[str] = []

    # 1) no vendored Sail source in the pair's tree
    for p in sorted(pkg.rglob("*")):
        if p.is_file() and p.suffix in (".sail",):
            findings.append(f"{p.relative_to(_HOPS_DIR)}: vendored Sail source")

    # 2) static crib scan of the pair's python sources
    for py in sorted(pkg.rglob("*.py")):
        findings.extend(scan_source(py.read_text(), str(py.relative_to(_HOPS_DIR))))

    # 3) dynamic: the construction oracle query log. differential_only requires
    #    ZERO gate-oracle queries; held_out_behavioral requires they be confined
    #    to the training partition (held-out queries are refused at runtime, so a
    #    log containing held-out ids would itself be evidence of tampering).
    log = pkg / "construction_oracle_log.json"
    if log.is_file():
        try:
            entries = json.loads(log.read_text())
        except Exception as e:  # noqa: BLE001
            findings.append(f"{log.relative_to(_HOPS_DIR)}: unreadable query log ({e!r})")
            entries = []
        if manifest.oracle_access == "differential_only" and entries:
            findings.append(
                f"{log.relative_to(_HOPS_DIR)}: {len(entries)} gate-oracle queries recorded, "
                f"but differential_only forbids any")
        elif entries:
            notes.append(f"{len(entries)} training-partition oracle queries recorded")
    else:
        notes.append("no construction oracle query log (differential_only expects zero queries — consistent)")

    # 4) the independent (validating) own lowering must EXIST to be audited:
    #    independence is unverifiable over an empty artifact. A stub own path is
    #    therefore a blocking finding for a sandboxed (validator) hop — the
    #    agent has not yet built the thing whose independence we certify.
    own = _own_lowering_status(manifest)
    if own.startswith("stub"):
        findings.append(
            "own (validating) lowering is a stub — no independent artifact to audit; "
            f"oracle_access={manifest.oracle_access!r} requires the agent to build it")
    else:
        notes.append(f"own lowering: {own}")

    return IndependenceReport(ok=not findings, findings=findings, notes=notes)


def _own_lowering_status(manifest: Manifest) -> str:
    import importlib

    from gurdy.hops.base import NotYetImplemented

    try:
        hop = importlib.import_module(f"gurdy.hops.{manifest.id}").HOP
        if "own" not in hop.paths():
            return "no own path declared"
        try:
            hop.translate(None, {}, path="own")
        except NotYetImplemented:
            return "stub (independence is clean but vacuous until the own lowering exists)"
        except Exception:
            pass
        return "implemented"
    except Exception as e:  # noqa: BLE001
        return f"unknown ({e!r})"
