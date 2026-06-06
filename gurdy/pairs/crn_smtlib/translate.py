"""CRN + reachability spec -> SMT-LIB (QF_LIA bounded unrolling). Transparent.

The encoding is fully specified by ``SCHEMA.md`` — given the CRN, the spec, and
the schema, the SMT-LIB is determined byte-for-byte (the predictability
invariant, in chemistry). Summary: state is one integer count per species at
each of ``N + 1`` time points; at each step a selector ``sel_t in [0, R-1]``
chooses the reaction that fires, gated by reactant availability and applying the
stoichiometric net change; the target is asserted to hold at some step. ``sat``
<=> the target is reachable within ``N`` reaction firings.
"""

from __future__ import annotations

import hashlib
import json

from gurdy.core.annotation.types import Role
from gurdy.core.pair import CompiledArtifact, Layer
from gurdy.pairs.crn_smtlib.model import CrnModel
from gurdy.pairs.crn_smtlib.spec import PAIR_ID, CrnSpec

SCHEMA_VERSION = "0.1.0"

_OP_SMT = {">=": ">=", "==": "=", "<=": "<="}
_META_PREFIX = "; @crn-meta "


def _int(k: int) -> str:
    """SMT-LIB integer literal (negatives are ``(- n)``)."""
    return str(k) if k >= 0 else f"(- {-k})"


def _net_changes(crn: CrnModel) -> list[dict[str, int]]:
    deltas: list[dict[str, int]] = []
    for r in crn.reactions:
        d = {s: 0 for s in crn.species}
        for s, c in r.reactants:
            d[s] -= c
        for s, c in r.products:
            d[s] += c
        deltas.append(d)
    return deltas


def emit_smtlib(spec: CrnSpec, crn: CrnModel) -> str:
    """Render the QF_LIA bounded-reachability SMT-LIB for ``(spec, crn)``."""
    unknown = (set(spec.initial) | {spec.target.species}) - set(crn.species)
    if unknown:
        raise ValueError(
            f"spec references species not in the CRN: {sorted(unknown)} "
            f"(CRN species: {list(crn.species)})"
        )
    if spec.bound < 0:
        raise ValueError("bound must be >= 0")
    if spec.target.op not in _OP_SMT:
        raise ValueError(f"unsupported target op {spec.target.op!r}")

    species = crn.species
    n_reactions = len(crn.reactions)
    n = spec.bound
    deltas = _net_changes(crn)

    meta = {
        "species": list(species),
        "reactions": [r.name for r in crn.reactions],
        "bound": n,
        "target": {
            "species": spec.target.species,
            "op": spec.target.op,
            "value": spec.target.value,
        },
    }
    out: list[str] = [_META_PREFIX + json.dumps(meta, sort_keys=True, separators=(",", ":"))]
    out.append("(set-logic QF_LIA)")

    for t in range(n + 1):
        for s in species:
            out.append(f"(declare-const x_{s}_{t} Int)")
    for t in range(n):
        out.append(f"(declare-const sel_{t} Int)")

    for t in range(n + 1):
        for s in species:
            out.append(f"(assert (>= x_{s}_{t} 0))")
    for t in range(n):
        out.append(f"(assert (and (>= sel_{t} 0) (<= sel_{t} {n_reactions - 1})))")
    for s in species:
        out.append(f"(assert (= x_{s}_0 {spec.initial.get(s, 0)}))")

    for t in range(n):
        for ri, r in enumerate(crn.reactions):
            if r.reactants:
                conj = " ".join(f"(>= x_{s}_{t} {c})" for s, c in r.reactants)
                guard = conj if len(r.reactants) == 1 else f"(and {conj})"
                out.append(f"(assert (=> (= sel_{t} {ri}) {guard}))")
        for s in species:
            expr = "0"
            for ri in reversed(range(n_reactions)):
                expr = f"(ite (= sel_{t} {ri}) {_int(deltas[ri][s])} {expr})"
            out.append(f"(assert (= x_{s}_{t + 1} (+ x_{s}_{t} {expr})))")

    op = _OP_SMT[spec.target.op]
    ts, tv = spec.target.species, spec.target.value
    terms = [f"({op} x_{ts}_{t} {tv})" for t in range(n + 1)]
    target = terms[0] if len(terms) == 1 else f"(or {' '.join(terms)})"
    out.append(f"(assert {target})")

    out.append("(check-sat)")
    out.append("(get-model)")
    return "\n".join(out) + "\n"


class _Translator:
    def translate(self, spec: CrnSpec, source: CrnModel, emitter) -> CompiledArtifact:
        body = emit_smtlib(spec, source).encode("utf-8")
        content_hash = hashlib.sha256(body).hexdigest()
        for i, s in enumerate(source.species):
            emitter.emit("smtlib", i, Role.STATE, source_mapping={"species": s})
        emitter.emit(
            "smtlib",
            len(source.species),
            Role.BAD,
            source_mapping={
                "target": {
                    "species": spec.target.species,
                    "op": spec.target.op,
                    "value": spec.target.value,
                }
            },
        )
        return CompiledArtifact(
            pair=PAIR_ID,
            layers={"smtlib": Layer(name="smtlib", body=body, content_hash=content_hash)},
            annotation=emitter.sidecar,
            flattened=body,
            schema_version=SCHEMA_VERSION,
            spec_hash=spec.spec_hash(),
        )


translate = _Translator()

__all__ = ["SCHEMA_VERSION", "emit_smtlib", "translate"]
