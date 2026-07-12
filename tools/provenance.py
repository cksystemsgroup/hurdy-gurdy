"""tools/provenance.py — author-diversity provenance (SCALING.md §9, Phase 7).

The external differential is the **actual root of trust**, and it must never be
author-able by the agents building the pairs. Model-diversity alone is
insufficient — two models can misread the same manual identically — so the
artifact-derived external differential is what a corroborating branch rests on.
This module validates the *coordinator-attested* provenance record that
establishes author-disjointness, so a green gate is trustworthy without a human.

A **provenance record** (coordinator-attested, not builder-self-reported) names,
per pair, the legs that produced it — each with the authoring agent, its model
family, and the semantic artifact it derived from — plus whether the pair's
fidelity rests on a corroborating external differential (``requires_diversity``).

An **attestation ledger** records, coordinator-side, which agent contributed
which interpreter, and which semantic artifacts are *external* (coordinator-
registered, not builder-writable — the Sail model, the prose manual).

The checks, mapped to §9:

* **Coordinator attestation.** Provenance must be attested by the coordinator,
  not self-reported by the builder — else it is worthless as an author-diversity
  claim (§4). A record that is not coordinator-attested is rejected.
* **Interpreter/pair separation.** An interpreter-contributing agent must not
  also author a pair over that interpreter — a self-consistent ``T+Λ+I_s`` would
  pass its own square. Any leg agent that (per the ledger) contributed the pair's
  source or target interpreter is rejected.
* **Author-diversity, rooted in an external artifact.** For a pair whose fidelity
  rests on a corroborating differential, the legs must span **≥2 model families**
  *and* **≥2 semantic artifacts**; model diversity alone (same artifact) is
  rejected. And every leg's semantic artifact must be a *registered external*
  artifact — an artifact the pair's own agents could author is not a root of
  trust and is escalated.

The engine is pure (dicts in, verdict out); a thin CLI validates records on disk.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import dataclass, field

# Verdicts (aligned with tools/merge_queue.py so they compose).
OK = "OK"
ESCALATE = "ESCALATE"   # needs a human (an unregistered artifact — possibly builder-authored)
REJECT = "REJECT"       # a hard author-disjointness violation


@dataclass
class Ledger:
    """Coordinator-side attestation state (not builder-writable)."""
    # agent -> the interpreters (languages) that agent contributed
    interpreter_contributions: dict[str, list[str]] = field(default_factory=dict)
    # the semantic artifacts registered as *external* (Sail model, prose manual, …)
    external_artifacts: set[str] = field(default_factory=set)

    def contributed_by(self, agent: str) -> set[str]:
        return set(self.interpreter_contributions.get(agent, []))


def _legs(record: dict) -> list[dict]:
    return record.get("legs", [])


def check(record: dict, ledger: Ledger) -> tuple[str, list[str]]:
    """Validate one pair's provenance record against the ledger. Returns
    ``(verdict, reasons)`` — the worst verdict wins (REJECT > ESCALATE > OK)."""
    reasons: list[str] = []
    verdict = OK

    def fail(kind: str, msg: str) -> None:
        nonlocal verdict
        reasons.append(msg)
        if kind == REJECT or verdict == REJECT:
            verdict = REJECT
        elif kind == ESCALATE:
            verdict = ESCALATE

    # 1. coordinator attestation (never self-reported)
    if record.get("attested_by") != "coordinator":
        fail(REJECT, "provenance is not coordinator-attested (self-reported "
                     "provenance cannot establish author-diversity, §4)")

    source, target = record.get("source"), record.get("target")
    legs = _legs(record)

    # 2. interpreter/pair separation
    for leg in legs:
        agent = leg.get("agent")
        for lang in ledger.contributed_by(agent):
            if lang in (source, target):
                fail(REJECT, f"agent {agent!r} contributed interpreter {lang!r} and "
                             f"also authors a pair over it — a self-consistent "
                             f"T+Λ+I_s passes its own square (§9)")

    # 3. author-diversity rooted in an external artifact
    if record.get("requires_diversity"):
        if len(legs) < 2:
            fail(REJECT, "author-diversity required, but the record has fewer than "
                         "two corroborating legs")
        else:
            families = {leg.get("model_family") for leg in legs}
            artifacts = {leg.get("semantic_artifact") for leg in legs}
            if len(families) < 2:
                fail(REJECT, "model diversity insufficient — the corroborating legs "
                             "share a model family")
            if len(artifacts) < 2:
                fail(REJECT, "legs derive from the same semantic artifact — model "
                             "diversity alone cannot catch a shared misreading (§9)")
        for leg in legs:
            art = leg.get("semantic_artifact")
            if art not in ledger.external_artifacts:
                fail(ESCALATE, f"semantic artifact {art!r} is not a registered "
                               f"external artifact — it may be builder-authorable, "
                               f"which is not a root of trust (§9)")

    return verdict, reasons


# --- CLI ---------------------------------------------------------------------

def _ledger_from(data: dict) -> Ledger:
    return Ledger(
        interpreter_contributions=data.get("interpreter_contributions", {}),
        external_artifacts=set(data.get("external_artifacts", [])),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("record", help="JSON provenance record for one pair")
    ap.add_argument("--ledger", required=True,
                    help="JSON attestation ledger (interpreter_contributions, "
                         "external_artifacts)")
    args = ap.parse_args()
    record = json.loads(pathlib.Path(args.record).read_text())
    ledger = _ledger_from(json.loads(pathlib.Path(args.ledger).read_text()))
    verdict, reasons = check(record, ledger)
    print(json.dumps({"pair": record.get("pair"), "verdict": verdict,
                      "reasons": reasons}, indent=2))
    return 0 if verdict == OK else 1


if __name__ == "__main__":
    raise SystemExit(main())
