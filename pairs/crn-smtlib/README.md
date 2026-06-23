# Pair — `crn-smtlib`  ·  CRN → SMT-LIB

*Status: **partial** (uni- + bimolecular + catalysis / multi-product +
synthesis + degradation + self-loop + **multiple-reactions** + empty-network —
`A -> B`, `A + B -> C`, `2 A -> B`, `A -> 2 B`, `A -> B + C`, `0 -> A`, `A -> 0`,
`A -> A`, ≥2 reactions, 0 reactions; 10/10 probed construct classes). The
non-CS reasoning bridge.*

Translate a chemical reaction network, under discrete-population
(Petri-net) semantics, into SMT-LIB (`QF_LIA`) for **bounded reachability**,
decided by an SMT solver. This is the second reasoning hub (SMT-LIB
alongside BTOR2) and the evidence the architecture is **field-blind**: the
source language is chemistry, not code.

## Built so far (PAIRING.md §1 "start thin, then widen")

The fully-widened slice (`gurdy/`): ten in-scope reaction classes —
the **unimolecular reaction `A -> B`**, both **bimolecular** shapes
(`A + B -> C`, two distinct unit reactants; `2 A -> B`, one doubled reactant),
both **catalysis / multi-product** shapes (`A -> 2 B`, one doubled product /
amplification; `A -> B + C`, two distinct unit products), **synthesis** `0 -> A`
(an empty reactant side, always enabled), **degradation** `A -> 0` (an empty
product side), **self-loop** `A -> A` (a product also among the reactants — net
stoichiometry 0 on the shared species, the enabledness precondition still
required), **multiple-reactions** (≥2 reactions whose per-step firing *selects*
which one fires) and **empty-network** (no reactions — only stuttering) — with
any number of spectator species, translated end-to-end through the commuting
square. The remaining out-of-scope reaction *shapes* hard-abort
`unsupported: crn:<construct>` (BENCHMARKS.md §3).

The bimolecular, catalysis, synthesis, and degradation widenings were *additive*
over the unimolecular schema (PAIRING.md §2,
[`SCHEMA.md`](../../gurdy/pairs/crn_smtlib/SCHEMA.md)): the same per-step firing
flag and per-species `ite`-guarded update, with the enabledness precondition
generalized to one linear `(>= x_r Rc[r])` conjunct per reactant (`(>= xA 2)` for
`2 A`; `(and (>= xA 1) (>= xB 1))` for `A + B`; the bare unimolecular `(>= xA 1)`
for catalysis and degradation; and the empty conjunction — the literal `true` —
for synthesis, which has no reactant) and the update driven by the *net*
stoichiometry `Pc[s] - Rc[s]` (so `A -> 2 B` is `B` net `+2`, `A -> B + C` is
`+1` on each product, `0 -> A` is `A` net `+1` with no decrement, and `A -> 0` is
`A` net `-1` with no increment). The two per-reaction molecularities (reactant,
product) jointly cover `(1,1)`, `(2,1)`, `(1,2)`, `(0,1)` (synthesis), `(1,0)`
(degradation) — *not* `(2,2)`: a molecularity-2 product is admitted only on a
single-unit reactant side, and the two empty sides are admitted one at a time
(`0 -> 0` stays out of scope as a no-op).

The **multiple-reactions, self-loop and empty-network** widenings (this round)
are likewise additive and stay inside the same `QF_LIA` fragment. The
single-firing-flag schema generalizes to **per-reaction flags** `f<i>_t`: a
per-step **mutual-exclusion** constraint (the pairwise
`(or (not f<i>_t) (not f<j>_t))`, emitted only when ≥2 reactions) makes the firing
*select* at most one reaction, and each species' update becomes a **nested `ite`
chain** in reaction order (each level guarded by that reaction's flag, applying
its net stoichiometry, falling through to `x<s>_t`). A **self-loop** `A -> A` is
admitted as a net-zero update (the shared species is preserved) with its
enabledness precondition `(>= xA 1)` intact. An **empty network** emits no firing
flags and reduces the per-species update to the pure stutter `(= x<s>_{t+1}
x<s>_t)`, so the target is reachable iff it equals the initial marking. Crucially,
**the single-reaction case reduces byte-for-byte to the pre-widening schema** (no
mutex clause, a one-level `ite` chain), so every prior byte-exact test still
passes, and **no shared interpreter changed** — the CRN stepper already replays a
schedule that names which reaction fires each step (multi-reaction), nets a
self-loop to zero (subtract-then-add), and stutters an empty network, so its
version is **not** bumped. (The shared SMT-LIB `QF_LIA` evaluator and the z3
solver inventory are likewise reused unchanged: `smt_model_ok` is verified to
agree with the CRN-interpreter replay `witness_ok` on a multi-reaction
`reachable` whose schedule uses both reactions, on a self-loop, and on an
empty-network.)

- Translator `T` — `gurdy/pairs/crn_smtlib/translate.py` (schema-determined
  `QF_LIA` unrolling; per-reaction-flag firing schema with mutual exclusion and
  nested-`ite` net-stoichiometry updates).
- Target-to-source interpreter `L` — `gurdy/pairs/crn_smtlib/lift.py` (decode
  the per-step firing flags into a schedule naming which reaction fired, replay
  through the CRN interpreter — reaction-count-aware now, otherwise unchanged).
- Projection `π` + commuting-square `cross_check` — `gurdy/pairs/crn_smtlib/__init__.py`.
- The **shared CRN interpreter** `I_s` (CRN's first touch, so contributed
  here) — `gurdy/languages/crn/` (loader `model.py`, Petri-net stepper
  `eval.py`).
- Construct inventory — `gurdy/pairs/crn_smtlib/inventory.py`.
- The self-contained schema/specification —
  [`gurdy/pairs/crn_smtlib/SCHEMA.md`](../../gurdy/pairs/crn_smtlib/SCHEMA.md).
- Tests — `tests/test_crn_interp.py`, `tests/test_crn_smtlib.py` (run with
  `python -m unittest discover -s tests`).

### Coverage — `partial`, 10/10 probed reaction classes

Construct coverage against CRN's spec-enumerable reaction-class inventory
(`gurdy/pairs/crn_smtlib/inventory.py`): **10/10 probed classes covered**
(`unimolecular`, `bimolecular-hetero`, `bimolecular-homo`, `catalysis`,
`catalyst-pair`, `synthesis`, `degradation`, `self-loop`, `multiple-reactions`,
`empty-network`) — up from 7/10 (and 5/10, 3/10, 1/10 before that) under the
coverage ratchet (BENCHMARKS.md §5: coverage only grows, nothing dropped). The
`unsupported` histogram over the inventory is now **empty** — no probed reaction
class is blocked.

Status stays **`partial`**, not `built`: the *shapes a single reaction may take*
are still bounded (reactant/product molecularity ≤ 2, a molecularity-2 product
only on a unit reactant side), so these out-of-scope reaction shapes still
hard-abort `unsupported: crn:<construct>`, each exercised by a dedicated
**rejection test** (so the headline denominator stays 10) rather than an
inventory probe:

| out-of-scope shape | abort |
|--------------------|-------|
| reactant molecularity ≥ 3 (`A + B + C`, `3 A`) — including inside a multi-reaction network | `crn:trimolecular` |
| product molecularity ≥ 3 (`A -> 3 B`), or a molecularity-2 product on a non-unit reactant side (`2 A -> 2 B`, `A + B -> 2 C`) | `crn:catalysis` |
| both sides empty (`0 -> 0`, a no-op) | `crn:empty-reaction` |

Each reaction in a network is validated independently, so an out-of-scope
reaction inside an otherwise-fine multi-reaction network still hard-aborts. A
public benchmark suite (BioModels/SBML, PRISM/STORM) is **not yet wired** —
pending: the multi-reaction loader can now ingest such models, but the in-scope
per-reaction shapes (molecularity ≤ 2) and the bounded-reachability question still
need an adapter; this is the natural next increment.

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
  `test_catalysis_pair_schema_byte_exact` for `A -> B + C`,
  `test_multiple_reactions_schema_byte_exact` for `A -> B, B -> C`,
  `test_self_loop_schema_byte_exact` for `A -> A`,
  `test_empty_network_schema_byte_exact` for the zero-reaction network) and the
  twice-and-diff determinism tests for `T` (uni-, bimolecular, catalysis,
  synthesis/degradation, and multi-reaction/self-loop/empty, byte-reproducible
  across `PYTHONHASHSEED`; the single-reaction bytes are *unchanged* by this
  widening — the per-reaction-flag schema reduces to a one-level `ite` chain with
  no mutex clause, identically).
- A `sat` decision is verified by **witness replay**: the firing-flag witness
  is replayed through the deterministic CRN interpreter (`witness_ok`) and the
  solver's claimed per-step populations are cross-checked against the
  interpreter's regrown ones (`model_matches_replay`) — SOLVERS.md §4, this
  *is* the commuting-square replay-and-project check. Independently, the emitted
  `QF_LIA` script is re-evaluated under the solver's model by the shared SMT-LIB
  interpreter (`smt_model_ok`), which **agrees** with the replay on every
  bimolecular, catalysis, synthesis/degradation, multi-reaction, self-loop and
  empty-network `reachable` decision (`TestBimolecularWithZ3`,
  `TestCatalysisWithZ3`, `TestSynthesisDegradationWithZ3`,
  `TestMultipleReactionsWithZ3`, `TestSelfLoopWithZ3`, `TestEmptyNetworkWithZ3`
  assert `smt_model_ok == witness_ok`; the multi-reaction `reachable` schedule is
  asserted to use **both** reactions).

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
- **Multiple-reactions, self-loop, empty-network widened in (7/10 → 10/10).**
  The three remaining probed classes were turned from typed `unsupported` aborts
  into covered constructs under the ratchet. The lesson: the structurally
  significant one — **multiple-reactions** — generalized the *single firing flag*
  into **per-reaction flags** with a per-step **mutual-exclusion** constraint (the
  firing *selects* at most one reaction) and a **nested `ite` chain** for the
  per-species update (one level per reaction). Because the shared CRN stepper
  already replays a schedule that *names which reaction fires each step*, the
  carry-back extended naturally (decode the one-hot flags into reaction indices);
  the whole widening lived in the *pair*'s translator schema and `L`, with **no
  shared-interpreter version bump**. Self-loop (`A -> A`) fell out for free — the
  net-stoichiometry update already preserves a net-zero species, and the
  enabledness precondition is still required (the interpreter's subtract-then-add
  nets to zero, exercised by `test_fires_self_loop_net_zero`). Empty-network is the
  degenerate case of the same schema: no firing flags, the `ite` chain is the bare
  fall-through, so the update is a pure stutter and the target is reachable iff it
  equals the init marking. The key invariant held: **the single-reaction case
  reduces byte-for-byte to the pre-widening schema** (no mutex clause, one-level
  `ite`), so every prior byte-exact test passes unchanged.
- **Future widening (named, not done):** the in-scope *per-reaction shapes* are
  still bounded — reactant molecularity ≥ 3 (`crn:trimolecular`), a molecularity-2
  product on a non-unit reactant side or product molecularity ≥ 3
  (`crn:catalysis`), and the both-empty `0 -> 0` (`crn:empty-reaction`) remain
  typed `unsupported` aborts, ready to be turned into covered constructs under the
  ratchet. Wiring a public CRN suite (BioModels/SBML, PRISM/STORM) is now
  *unblocked on the loader* (the multi-reaction arm ingests multi-reaction
  networks), but still needs an adapter to the in-scope per-reaction shapes and the
  bounded-reachability question — the natural next increment.

## Notes for the implementing agent

- The shared CRN interpreter implements the discrete Petri-net semantics;
  validate it against a PRISM/Maude oracle ([`languages/crn`](../../languages/crn/README.md)).
  (Not yet wired — the slice's tests pin the semantics against hand-computed
  trajectories; an external PRISM/Maude differential is future work.)
- Solvers/checkers are SMT-LIB's shared inventory; this pair wires none of
  its own ([`SOLVERS.md`](../../SOLVERS.md)).
