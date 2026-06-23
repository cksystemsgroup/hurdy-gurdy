# crn-smtlib translation schema (`predicted`)

This is the self-contained, reviewable specification the translator `T`
implements mechanically (PAIRING.md §2). Given the source network, the step
bound `k`, and a target marking, the emitted SMT-LIB script is determined
**byte-for-byte** by the rules below — no adaptive choices, no hashing, no
timestamps. Anyone with the source, the bound, and this schema can reproduce the
output exactly (the `predicted` predictability test).

## Scope (the covered reaction classes)

In scope: a network of **any number of reactions** `R0..R{N-1}` (including zero
and two-or-more), each within one of the per-reaction shapes below:

- **unimolecular** `A -> B` — one unit reactant, one unit product, distinct;
- **bimolecular** — total reactant tokens (reactant molecularity) = 2 with a
  single unit product: either two distinct unit reactants `A + B -> C`, or one
  doubled reactant `2 A -> B` (dimerization);
- **catalysis / multi-product** — one unit reactant (reactant molecularity 1)
  with a product of molecularity 2: `A -> 2 B` (one doubled product /
  amplification) or `A -> B + C` (two distinct unit products);
- **synthesis** `0 -> A` — an empty reactant side (reactant molecularity 0):
  always enabled (the enabledness conjunction is empty = `true`), net `A: +1`;
- **degradation** `A -> 0` — an empty product side (product molecularity 0):
  precondition `xA >= 1`, net `A: -1`;
- **self-loop** `A -> A` — a product species that is also a reactant, so the
  shared species has *net* stoichiometry `0` (preserved by the update); the
  enabledness precondition (`xA >= 1`) is still required.

So the two per-reaction molecularities (reactant, product) jointly cover `(1,1)`,
`(2,1)`, `(1,2)`, `(0,1)` (synthesis), and `(1,0)` (degradation) — *not* `(2,2)`:
a molecularity-2 product is admitted only on a single-unit reactant side. The two
empty sides are admitted **one at a time**: a reaction with *both* sides empty
(`0 -> 0`) is a no-op, not a reaction class, and stays out of scope. A self-loop
(a product also among the reactants) is now in scope (net-zero on the shared
species). Any number of declared species (the others are spectators).

**Reaction count.** Zero reactions (an empty network — only stuttering is
possible, so the target is reachable iff it equals the initial marking), one
reaction (reducing byte-for-byte to the pre-widening single-reaction schema), or
two or more reactions (the per-step firing **selects** which one reaction fires —
a one-hot over the per-reaction firing flags, with at most one true per step) are
all in scope.

Everything else hard-aborts with a typed `unsupported: crn:<construct>`
(BENCHMARKS.md §3), never a silent drop. Each reaction is validated
independently, so an out-of-scope reaction in an otherwise-fine network still
aborts:

| construct | abort |
|---|---|
| both sides empty (`0 -> 0`) | `crn:empty-reaction` |
| reactant molecularity ≥ 3 (`A + B + C`, `3 A`) | `crn:trimolecular` |
| product molecularity ≥ 3 (`A -> 3 B`), or a molecularity-2 product on a non-unit reactant side (`2 A -> 2 B`, `A + B -> 2 C`) | `crn:catalysis` |
| missing / empty target marking | `crn:no-target` |
| target names an undeclared species | `crn:target-species` |
| `k < 0` | `crn:negative-bound` |

## Logic

`QF_LIA` — quantifier-free linear integer arithmetic. Populations are `Int`,
firing decisions are `Bool`.

## Variables (emitted first, steps-major; species then firing flags)

- `x<s>_<t> : Int` — population of species `s` after step `t`, for every species
  `s` and `t = 0 .. k`. Declared in `t`-ascending, then network-species order.
- `f<i>_<t> : Bool` — did reaction `i` fire during step `t`, for every reaction
  `i = 0 .. N-1` and `t = 0 .. k-1` (within a step, reaction order). An empty
  network (`N = 0`) declares no firing flags.

## Constraints (emitted in this fixed order)

1. **init** — `(assert (= x<s>_0 <init s>))` for each species `s` (network
   order), where `<init s>` is its declared initial count (0 if unset).
2. **domain** — `(assert (>= x<s>_t 0))` for every species `s` and `t = 0 .. k`
   (steps-major, network-species order): populations are non-negative.
3. **transition** — for `t = 0 .. k-1`, in this order. Let `Rc_i[s]` be reaction
   `i`'s reactant coefficient for species `s` (0 if absent) and `Pc_i[s]` its
   product coefficient.
   - **mutual exclusion** (emitted only when `N >= 2`): at most one reaction fires
     per step, as pairwise clauses `(assert (or (not f<i>_t) (not f<j>_t)))` for
     `0 <= i < j < N` (lexicographic `(i, j)` order). With one reaction the single
     flag is vacuously exclusive, so the clause is **absent** and the
     single-reaction bytes are unchanged.
   - enabledness: per reaction `i` (reaction order),
     `(assert (=> f<i>_t <guard_i>))` where `<guard_i>` is the conjunction of
     `(>= x<r>_t Rc_i[r])` over reaction `i`'s reactants — firing requires every
     reactant present in at least its stoichiometric coefficient (the Petri-net
     precondition, **linear** in the marking). With one reactant the guard is the
     bare atom; with two it is `(and <atom_1> <atom_2>)`; with **zero** reactants
     (synthesis `0 -> A`) the conjunction is empty and the guard is the literal
     `true` (always enabled). (Unimolecular `A -> B`: `(>= xA_t 1)`. `2 A -> B`:
     `(>= xA_t 2)`. `A + B -> C`: `(and (>= xA_t 1) (>= xB_t 1))`. Synthesis: `true`.
     Self-loop `A -> A`: `(>= xA_t 1)`.)
   - per species `s` (network order), the guarded update as a **nested `ite`
     chain** in reaction order, each level guarded by that reaction's flag and
     falling through to `x<s>_t` when no reaction fired:
     `(assert (= x<s>_{t+1} (ite f0_t <upd_0(s)> (ite f1_t <upd_1(s)> ... x<s>_t))))`,
     where `<upd_i(s)>` is reaction `i`'s *net* stoichiometry `n = Pc_i[s] - Rc_i[s]`:
     `(- x<s>_t |n|)` if `n < 0`, `(+ x<s>_t n)` if `n > 0`, else `x<s>_t`
     (spectator / net-zero — e.g. self-loop — species preserved). With **one**
     reaction the chain is the single `(ite f0_t <upd> x_t)` — the pre-widening
     emission. With **zero** reactions the chain is the bare fall-through, so the
     update is the pure stutter `(assert (= x<s>_{t+1} x<s>_t))`.
     (Unimolecular `A -> B`: `A` net `-1` ⇒ `(- xA_t 1)`, `B` net `+1` ⇒
     `(+ xB_t 1)` — byte-identical to the pre-widening emission. Catalysis
     `A -> 2 B`: `B` net `+2` ⇒ `(+ xB_t 2)`. Synthesis `0 -> A`: `A` net `+1`,
     no decrement. Degradation `A -> 0`: `A` net `-1`, no product increment.
     Self-loop `A -> A`: `A` net `0` ⇒ `xA_t` (preserved).)
4. **bad** — reach the target marking at *some* step. For `t = 0 .. k`, build
   the per-step conjunct over the target's species (network order):
   `(and (= x<s>_t <count>) ...)` (a bare atom if only one species is named).
   Assert their disjunction: `(assert (or <conj_0> ... <conj_k>))` (a bare
   conjunct if `k = 0`).
5. `(check-sat)`.

The script is `sat` iff some firing schedule (selecting at most one reaction per
step) reaches the target marking within `k` discrete steps. The bimolecular,
catalysis, synthesis, degradation, and self-loop encodings extend the
unimolecular one *additively* — same per-step firing schema (per-reaction flag,
nested `ite`-guarded update per species), only the consumption/production
coefficients and the number of enabledness conjuncts change. The multi-reaction
encoding adds only the pairwise mutual-exclusion clause and one extra `ite` level
per reaction; the empty-network encoding drops the firing parts to a pure stutter.
All stay inside the same `QF_LIA` fragment (`Int`, `Bool`, `and`/`or`/`not`/`=>`/
`ite`, `+`/`-`, `>=`/`=`), so no shared-language change is needed (AGENTS.md §3).
Because the single-reaction case reduces byte-for-byte to the pre-widening schema,
the byte-exact tests for `A -> B`, `2 A -> B`, `A + B -> C`, `A -> 2 B`,
`A -> B + C`, `0 -> A`, `A -> 0` are unchanged.

## Carry-back `L` and the soundness story

A `sat` model binds each `f<i>_t` and `x<s>_t`. `L` reads the per-step firing
flags into a firing **schedule** — the index `i` of whichever reaction's flag
`f<i>_t` is true that step (the mutual-exclusion clause makes at most one true),
or a stutter when none is — and **replays** it through the shared CRN interpreter
`I_s` (SOLVERS.md §4: the solver only proposes; the deterministic interpreter
disposes). For one reaction this reduces to "0 where `f0_t` fired, stutter
otherwise"; for an empty network the schedule is all-stutter. Soundness
(PAIRING.md §6) is byte-prediction (this schema) **plus** model validation:

- `witness_ok` — the replay's post-step markings actually reach the target;
- `model_matches_replay` — the solver's claimed per-step populations equal the
  interpreter's regrown ones (catches any arithmetic-vs-Petri-net divergence).

The SMT-level evaluator check (`smt_model_ok`) re-evaluates the emitted `QF_LIA`
script under the solver's model with the shared SMT-LIB interpreter (`Int` over
arbitrary-precision integers, interp v0.2 — the QF_LIA arm). For a `reachable`
verdict it must hold and must **agree** with the CRN-interpreter replay
(`witness_ok` / `model_matches_replay`); a divergence is a translator-or-solver
fault. The multi-reaction mutual exclusion (`or`/`not`), the per-step
reaction-selecting nested `ite`, the self-loop net-zero update (the bare
`x<s>_t`), and the empty-network stutter all stay inside that already-built
`QF_LIA` fragment, so no shared-language change is needed for these widenings
(AGENTS.md §3). The CRN-interpreter replay remains the deterministic,
authoritative witness check; `smt_model_ok` corroborates it independently at the
SMT level — verified to agree on a multi-reaction `reachable` whose schedule uses
both reactions, on a self-loop, and on an empty-network.

## Projection `π`

The species populations per step (network order) — `projection_for(net)` — and
the reach/unreach verdict. The commuting-square check `cross_check` runs
`I_s(p)` on the witness's schedule and aligns it, under `π`, against
`L(I_t(T(p)))` (the same replay), so a faithful pair makes the two traces
identical at every step and observable.
