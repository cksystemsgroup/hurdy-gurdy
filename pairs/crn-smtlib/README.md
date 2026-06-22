# Pair — `crn-smtlib`  ·  CRN → SMT-LIB

*Status: **partial** (minimal vertical slice — the unimolecular reaction
`A -> B`; 1/10 construct classes). The non-CS reasoning bridge.*

Translate a chemical reaction network, under discrete-population
(Petri-net) semantics, into SMT-LIB (`QF_LIA`) for **bounded reachability**,
decided by an SMT solver. This is the second reasoning hub (SMT-LIB
alongside BTOR2) and the evidence the architecture is **field-blind**: the
source language is chemistry, not code.

## Built so far (PAIRING.md §1 "start thin")

A single minimal vertical slice (`gurdy/`): exactly one in-scope reaction
class — the **unimolecular reaction `A -> B`** (one unit reactant, one unit
product, distinct species; any number of spectator species) — translated
end-to-end through the commuting square, with every other construct
hard-aborting `unsupported: crn:<construct>` (BENCHMARKS.md §3).

- Translator `T` — `gurdy/pairs/crn_smtlib/translate.py` (schema-determined
  `QF_LIA` unrolling).
- Target-to-source interpreter `L` — `gurdy/pairs/crn_smtlib/lift.py` (decode
  the per-step firing flags, replay through the CRN interpreter).
- Projection `π` + commuting-square `cross_check` — `gurdy/pairs/crn_smtlib/__init__.py`.
- The **shared CRN interpreter** `I_s` (CRN's first touch, so contributed
  here) — `gurdy/languages/crn/` (loader `model.py`, Petri-net stepper
  `eval.py`).
- Construct inventory — `gurdy/pairs/crn_smtlib/inventory.py`.
- The self-contained schema/specification —
  [`gurdy/pairs/crn_smtlib/SCHEMA.md`](../../gurdy/pairs/crn_smtlib/SCHEMA.md).
- Tests — `tests/test_crn_interp.py`, `tests/test_crn_smtlib.py` (47 tests;
  run with `python -m unittest discover -s tests`).

### Coverage — `partial`, 1/10 reaction classes

Construct coverage against CRN's spec-enumerable reaction-class inventory
(`gurdy/pairs/crn_smtlib/inventory.py`): **1/10 covered** (`unimolecular`).
The `unsupported` histogram (every other class hard-aborts, none silently
dropped):

| construct | abort | probes blocked |
|-----------|-------|----------------|
| `bimolecular`  | `A + B -> C`, `2 A -> B` | 2 |
| `catalysis`    | `A -> 2 B`, `A -> B + C` | 2 |
| `synthesis`    | `0 -> A` | 1 |
| `degradation`  | `A -> 0` | 1 |
| `self-loop`    | `A -> A` | 1 |
| `multiple-reactions` | ≥2 reactions | 1 |
| `empty-network` | no reactions | 1 |

This is an honest `partial`, not a false `built` (BENCHMARKS.md §5); the slice
widens construct-by-construct under the coverage ratchet. A public benchmark
suite (BioModels/SBML, PRISM/STORM) is **not yet wired** — pending, since the
single-reaction slice cannot load multi-reaction networks.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** CRN — [`languages/crn`](../../languages/crn/README.md).
- **Target.** SMT-LIB — [`languages/smtlib`](../../languages/smtlib/README.md).
- **Translator `T`.** A schema-determined unrolling of the Petri-net
  semantics to a step bound `k`: integer population variables per species
  per step, reaction-firing constraints from the stoichiometry, and a
  reachability `bad`. `k` is a caller parameter, not a heuristic.
  Deterministic and **schema-predictable**.
- **Source interpreter.** The **shared** CRN interpreter
  ([`languages/crn`](../../languages/crn/README.md)) — reused; contributed
  by this pair if first.
- **Target interpreter.** SMT-LIB's deterministic model evaluator + text I/O
  ([`languages/smtlib`](../../languages/smtlib/README.md)) — reused.
- **Target-to-source interpreter `L`.** Decodes an SMT model into a CRN
  behavior — the firing sequence and per-step populations reaching the
  target marking. Pair-owned.

## Projection `π`

Per-step species populations and the reachability target — the CRN
interpreter's observables mapped onto the SMT-LIB integer variables.

## Fidelity + evidence

- **`predicted`** (claimed, evidence attached) — given the network, the bound
  `k`, the target marking, and the schema
  ([`SCHEMA.md`](../../gurdy/pairs/crn_smtlib/SCHEMA.md)), the SMT-LIB is
  determined byte-for-byte. Evidence: the byte-exact schema test
  (`test_schema_byte_exact`) and the twice-and-diff determinism tests for both
  `T` and the new CRN interpreter.
- A `sat` decision is verified by **witness replay**: the firing-flag witness
  is replayed through the deterministic CRN interpreter (`witness_ok`) and the
  solver's claimed per-step populations are cross-checked against the
  interpreter's regrown ones (`model_matches_replay`) — SOLVERS.md §4, this
  *is* the commuting-square replay-and-project check.

## Soundness story

Byte-prediction plus model validation: a `sat` model is replayed through the
CRN interpreter under `π` to confirm it actually reaches the target marking
([`PAIRING.md`](../../PAIRING.md) §6). The shared SMT-LIB solver inventory
(z3) is dispatched; this pair wires none of its own.

## What this slice learned (PAIRING.md §9)

- **The shared SMT-LIB evaluator emitted `QF_ABV` only when this slice landed,
  but this pair emits `QF_LIA`** — so `smt_model_ok` initially returned `None`,
  and the authoritative witness check was the CRN-interpreter replay (`witness_ok`
  / `model_matches_replay`), which is sound and deterministic. That gap was then
  closed by its own versioned deliverable: the shared SMT-LIB interpreter gained a
  `QF_LIA` arm (interp v0.2, `gurdy/languages/smtlib/eval.py`), and this pair now
  consumes it — `smt_model_ok` is an **authoritative** independent SMT-level
  witness check that agrees with the replay. The lesson: a fragment gap in a
  shared interpreter is a *versioned shared-language deliverable* (which
  re-validates dependents like `btor2-smtlib`), not a pair-private workaround
  (AGENTS.md §3).
- **Future widening (named, not done):** bimolecular (`A + B -> C`, `2 A -> B`),
  catalysis / multi-product, synthesis/degradation, and multi-reaction networks
  — each is already a typed `unsupported` abort, ready to be turned into a
  covered construct under the ratchet. Wiring a public CRN suite
  (BioModels/SBML, PRISM/STORM) waits on the multi-reaction arm, since the
  single-reaction loader cannot ingest those models.

## Notes for the implementing agent

- The shared CRN interpreter implements the discrete Petri-net semantics;
  validate it against a PRISM/Maude oracle ([`languages/crn`](../../languages/crn/README.md)).
  (Not yet wired — the slice's tests pin the semantics against hand-computed
  trajectories; an external PRISM/Maude differential is future work.)
- Solvers/checkers are SMT-LIB's shared inventory; this pair wires none of
  its own ([`SOLVERS.md`](../../SOLVERS.md)).
