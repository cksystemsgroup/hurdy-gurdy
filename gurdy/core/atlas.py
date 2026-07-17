"""The fragment atlas — where a shape-blocked demand sits in the known
decidability landscape (FRONTIER-PLAN.md §2.2/O1).

A small, registry-side reference table: for each question shape the
platform's vocabulary knows, the setting in which it is decidable, the
**known crossing** — the classical reduction that would bring it to a
shape an existing hub already decides (most crossings are endo-pairs,
POTENTIAL.md §4: liveness-to-safety, self-composition, monitor
weaving) — and the procedure family that decides it natively. The
frontier derivation annotates shape-blocked targets with their atlas
location, so a demand for "a reasoning language deciding liveness"
arrives naming the literature's answer: *or the liveness-to-safety
endo-pair on the hub you already have*.

Reference data, deliberately static and small: the atlas grows by
ordinary review (it is not builder-writable — the same reasoning as
protected instruments, SCALING.md §9), and a shape it does not know
reads ``uncharted``, never a guess. This is the shape obstacle's
extraction operator made concrete; the cost operator lives in the
report's failure-mode reading (tools/saturation_report.py).
"""

from __future__ import annotations

from typing import Any

#: shape → its place in the landscape. ``crossing`` names the known
#: reduction into an already-decided shape (an endo-pair or bridge a
#: brief could cite); ``native`` the procedure family that decides the
#: shape directly (a new hub, if none is registered).
ATLAS: dict[str, dict[str, Any]] = {
    "reachability": {
        "setting": "finite-state transition systems",
        "status": "decidable",
        "native": "BMC / k-induction / IC3-class model checking",
        "crossing": None,  # already a hub shape
    },
    "bounded-unreachability": {
        "setting": "finite-state transition systems, declared bound k",
        "status": "decidable",
        "native": "BMC with exhaustion (the bounded claim, honestly held)",
        "crossing": None,
    },
    "liveness": {
        "setting": "finite-state transition systems",
        "status": "decidable",
        "native": "nested fixpoints / automata-theoretic model checking",
        "crossing": "liveness-to-safety endo-pair on the hub "
                    "(loop detection; POTENTIAL.md §4)",
    },
    "termination": {
        "setting": "finite-state: decidable; unbounded programs: "
                   "undecidable in general",
        "status": "decidable-in-setting",
        "native": "ranking functions / size-change (unbounded, "
                  "incomplete by necessity)",
        "crossing": "termination-within-bounds as liveness, then "
                    "liveness-to-safety on the hub",
    },
    "ltl": {
        "setting": "finite-state transition systems",
        "status": "decidable",
        "native": "automata-theoretic LTL model checking",
        "crossing": "monitor weaving endo-pair (compile φ to an "
                    "observer whose bad is φ's violation)",
    },
    "ctl": {
        "setting": "finite-state transition systems",
        "status": "decidable",
        "native": "CTL model checking (fixpoint computation)",
        "crossing": "the universal fragment via monitor weaving; full "
                    "CTL wants a branching-time hub — a new reasoning "
                    "language",
    },
    "hypersafety-2": {
        "setting": "2-safety hyperproperties (noninterference, "
                   "determinism, program equivalence)",
        "status": "decidable",
        "native": "product-program reachability",
        "crossing": "self-composition endo-pair (p ↦ p × p), then "
                    "plain reachability on the existing hub",
    },
    "probabilistic-reachability": {
        "setting": "finite Markov chains / MDPs",
        "status": "decidable",
        "native": "probabilistic model checking (PRISM/Storm-class)",
        "crossing": None,  # no reduction to a Boolean hub is honest —
                           # this one really is a new reasoning language
    },
}


def locate(shape: str | None) -> dict[str, Any] | None:
    """The atlas entry for a shape, or an honest ``uncharted`` marker
    for one the atlas does not know. ``None`` for no shape at all."""
    if shape is None:
        return None
    entry = ATLAS.get(shape)
    if entry is None:
        return {"shape": shape, "status": "uncharted",
                "note": "not in the atlas — locate it by review before "
                        "designing anything (the atlas grows like any "
                        "protected instrument)"}
    return {"shape": shape, **entry}
