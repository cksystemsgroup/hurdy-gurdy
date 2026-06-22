# Pair — `crn-smtlib`  ·  CRN → SMT-LIB

*Status: **partial** (uni- + bimolecular + catalysis / multi-product reactions —
`A -> B`, `A + B -> C`, `2 A -> B`, `A -> 2 B`, `A -> B + C`; 5/10 construct
classes). The non-CS reasoning bridge.*

Translate a chemical reaction network, under discrete-population
(Petri-net) semantics, into SMT-LIB (`QF_LIA`) for **bounded reachability**,
decided by an SMT solver. This is the second reasoning hub (SMT-LIB
alongside BTOR2) and the evidence the architecture is **field-blind**: the
source language is chemistry, not code.

## Built so far (PAIRING.md §1 "start thin, then widen")

A widened vertical slice (`gurdy/`): five in-scope reaction classes —
the **unimolecular reaction `A -> B`**, both **bimolecular** shapes
(`A + B -> C`, two distinct unit reactants; `2 A -> B`, one doubled reactant),
and both **catalysis / multi-product** shapes (`A -> 2 B`, one doubled product /
amplification; `A -> B + C`, two distinct unit products) — each with its product
side disjoint from its reactant side (no self-loop), any number of spectator
species, translated end-to-end through the commuting square, with every other
construct hard-aborting `unsupported: crn:<construct>` (BENCHMARKS.md §3).

The bimolecular and catalysis widenings are *additive* over the unimolecular
schema (PAIRING.md §2, [`SCHEMA.md`](../../gurdy/pairs/crn_smtlib/SCHEMA.md)): the
same per-step firing flag and per-species `ite`-guarded update, with the
enabledness precondition generalized to one linear `(>= x_r Rc[r])` conjunct per
reactant (`(>= xA 2)` for `2 A`; `(and (>= xA 1) (>= xB 1))` for `A + B`; the bare
unimolecular `(>= xA 1)` for catalysis, which touches only the product side) and
the update driven by the *net* stoichiometry `Pc[s] - Rc[s]` (so `A -> 2 B` is
`B` net `+2`, and `A -> B + C` is `+1` on each product). The two molecularities
(reactant, product) jointly cover `(1,1)`, `(2,1)`, `(1,2)` — *not* `(2,2)`: a
molecularity-2 product is admitted only on a single-unit reactant side. It all
stays in the same `QF_LIA` fragment, so the unimolecular bytes are unchanged (the
byte-exact test still passes) and **no shared interpreter changed** — the CRN
stepper already handled arbitrary stoichiometry, so its version is **not** bumped.

- Translator `T` — `gurdy/pairs/crn_smtlib/translate.py` (schema-determined
  `QF_LIA` unrolling; net-stoichiometry firing schema).
- Target-to-source interpreter `L` — `gurdy/pairs/crn_smtlib/lift.py` (decode
  the per-step firing flags, replay through the CRN interpreter — unchanged by
  the widening; it is reaction-class-agnostic).
- Projection `π` + commuting-square `cross_check` — `gurdy/pairs/crn_smtlib/__init__.py`.
- The **shared CRN interpreter** `I_s` (CRN's first touch, so contributed
  here) — `gurdy/languages/crn/` (loader `model.py`, Petri-net stepper
  `eval.py`).
- Construct inventory — `gurdy/pairs/crn_smtlib/inventory.py`.
- The self-contained schema/specification —
  [`gurdy/pairs/crn_smtlib/SCHEMA.md`](../../gurdy/pairs/crn_smtlib/SCHEMA.md).
- Tests — `tests/test_crn_interp.py`, `tests/test_crn_smtlib.py` (run with
  `python -m unittest discover -s tests`).

### Coverage — `partial`, 5/10 reaction classes

Construct coverage against CRN's spec-enumerable reaction-class inventory
(`gurdy/pairs/crn_smtlib/inventory.py`): **5/10 covered** (`unimolecular`,
`bimolecular-hetero`, `bimolecular-homo`, `catalysis`, `catalyst-pair`) — up from
3/10 (and 1/10 originally) under the coverage ratchet (BENCHMARKS.md §5: coverage
only grows, nothing dropped). The `unsupported` histogram (every other class
hard-aborts, none silently dropped):

| construct | abort | probes blocked |
|-----------|-------|----------------|
| `synthesis`    | `0 -> A` | 1 |
| `degradation`  | `A -> 0` | 1 |
| `self-loop`    | `A -> A` (product is also a reactant) | 1 |
| `multiple-reactions` | ≥2 reactions | 1 |
| `empty-network` | no reactions | 1 |

Reactant molecularity ≥ 3 (`A + B + C`, `3 A`) is out of scope, hard-aborting
`crn:trimolecular`; a molecularity-2 product on a non-unit reactant side
(`2 A -> 2 B`, `A + B -> 2 C`) or a product molecularity ≥ 3 (`A -> 3 B`) is out
of scope, hard-aborting `crn:catalysis` (each exercised by a dedicated rejection
test rather than an inventory probe, so the headline denominator stays 10). This
is an honest `partial`, not a false `built` (BENCHMARKS.md §5); the slice widens
construct-by-construct under the coverage ratchet. A public benchmark suite
(BioModels/SBML, PRISM/STORM) is **not yet wired** — pending, since the
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
  determined byte-for-byte. Evidence: the byte-exact schema tests
  (`test_schema_byte_exact` for `A -> B`, `test_bimolecular_homo_schema_byte_exact`
  for `2 A -> B`, `test_bimolecular_hetero_schema_byte_exact` for `A + B -> C`,
  `test_catalysis_amplification_schema_byte_exact` for `A -> 2 B`,
  `test_catalysis_pair_schema_byte_exact` for `A -> B + C`) and the twice-and-diff
  determinism tests for `T` (uni-, bimolecular, and catalysis, byte-reproducible
  across `PYTHONHASHSEED`; the unimolecular and bimolecular bytes are *unchanged*
  by this widening — the net-stoichiometry schema reduces identically).
- A `sat` decision is verified by **witness replay**: the firing-flag witness
  is replayed through the deterministic CRN interpreter (`witness_ok`) and the
  solver's claimed per-step populations are cross-checked against the
  interpreter's regrown ones (`model_matches_replay`) — SOLVERS.md §4, this
  *is* the commuting-square replay-and-project check. Independently, the emitted
  `QF_LIA` script is re-evaluated under the solver's model by the shared SMT-LIB
  interpreter (`smt_model_ok`), which **agrees** with the replay on every
  bimolecular and catalysis `reachable` decision (`TestBimolecularWithZ3` and
  `TestCatalysisWithZ3` assert `smt_model_ok == witness_ok`).

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
- **Bimolecular widened in (1/10 → 3/10).** The bimolecular reactions
  (`A + B -> C`, `2 A -> B`) were turned from typed `unsupported` aborts into
  covered constructs under the ratchet. The lesson: because the shared CRN
  stepper already realized arbitrary-stoichiometry Petri-net firing, the whole
  widening lived in the *pair* (the translator's enabledness/net-stoichiometry
  schema and the inventory) — no shared-interpreter version bump, and the
  unimolecular bytes were preserved exactly. The firing schema is the same shape
  as the unimolecular case; only the consumption/production coefficients and the
  count of enabledness conjuncts change, so it stays inside the existing `QF_LIA`
  fragment that `smt_model_ok` already checks.
- **Catalysis / multi-product widened in (3/10 → 5/10).** The catalysis reactions
  (`A -> 2 B`, `A -> B + C`) were turned from typed `unsupported` aborts into
  covered constructs under the ratchet. The lesson: because the net-stoichiometry
  schema already drives the per-species update from `Pc[s] - Rc[s]`, catalysis
  touches *only* the product coefficients `Pc` — its enabledness is the bare
  unimolecular `(>= xA 1)` and its only departure from the unimolecular bytes is a
  larger increment on the product side(s) (`(+ xB 2)` for `A -> 2 B`; a `+1` on
  each of two products for `A -> B + C`). So, again, the whole widening lived in
  the *pair*'s `_check_in_scope` admission and the inventory — no shared-interpreter
  version bump (the CRN stepper already fires multi-product reactions, exercised by
  `test_fires_catalysis_*`), the unimolecular/bimolecular bytes preserved exactly,
  and it stays inside the existing `QF_LIA` fragment `smt_model_ok` already checks.
  Scope was kept honest: a molecularity-2 product is admitted only on a single-unit
  reactant side, so `2 A -> 2 B` (and `A -> 3 B`) still hard-abort `crn:catalysis`.
- **Future widening (named, not done):** synthesis / degradation (an empty side),
  reactant molecularity ≥ 3, doubled-product-on-bimolecular (`2 A -> 2 B`), and
  multi-reaction networks — each is already a typed `unsupported` abort, ready to
  be turned into a covered construct under the ratchet. Wiring a public CRN suite
  (BioModels/SBML, PRISM/STORM) waits on the multi-reaction arm, since the
  single-reaction loader cannot ingest those models.

## Notes for the implementing agent

- The shared CRN interpreter implements the discrete Petri-net semantics;
  validate it against a PRISM/Maude oracle ([`languages/crn`](../../languages/crn/README.md)).
  (Not yet wired — the slice's tests pin the semantics against hand-computed
  trajectories; an external PRISM/Maude differential is future work.)
- Solvers/checkers are SMT-LIB's shared inventory; this pair wires none of
  its own ([`SOLVERS.md`](../../SOLVERS.md)).
