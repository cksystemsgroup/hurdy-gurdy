# crn-smtlib translation schema (`predicted`)

This is the self-contained, reviewable specification the translator `T`
implements mechanically (PAIRING.md §2). Given the source network, the step
bound `k`, and a target marking, the emitted SMT-LIB script is determined
**byte-for-byte** by the rules below — no adaptive choices, no hashing, no
timestamps. Anyone with the source, the bound, and this schema can reproduce the
output exactly (the `predicted` predictability test).

## Scope (the minimal vertical slice)

In scope: a network of **exactly one unimolecular reaction** `R0 : A -> B` —
one reactant species with coefficient 1, one product species with coefficient 1,
the two distinct. Any number of declared species (the others are spectators).

Everything else hard-aborts with a typed `unsupported: crn:<construct>`
(BENCHMARKS.md §3), never a silent drop:

| construct | abort |
|---|---|
| no reactions | `crn:empty-network` |
| ≥2 reactions | `crn:multiple-reactions` |
| no reactant (`0 -> A`) | `crn:synthesis` |
| no product (`A -> 0`) | `crn:degradation` |
| ≥2 reactant tokens (`A + B`, `2 A`) | `crn:bimolecular` |
| ≥2 product tokens (`A -> 2 B`, `A -> B + C`) | `crn:catalysis` |
| reactant == product (`A -> A`) | `crn:self-loop` |
| missing / empty target marking | `crn:no-target` |
| target names an undeclared species | `crn:target-species` |
| `k < 0` | `crn:negative-bound` |

## Logic

`QF_LIA` — quantifier-free linear integer arithmetic. Populations are `Int`,
firing decisions are `Bool`.

## Variables (emitted first, steps-major, species in network order)

- `x<s>_<t> : Int` — population of species `s` after step `t`, for every species
  `s` and `t = 0 .. k`. Declared in `t`-ascending, then network-species order.
- `f0_<t> : Bool` — did `R0` fire during step `t`, for `t = 0 .. k-1`.

## Constraints (emitted in this fixed order)

1. **init** — `(assert (= x<s>_0 <init s>))` for each species `s` (network
   order), where `<init s>` is its declared initial count (0 if unset).
2. **domain** — `(assert (>= x<s>_t 0))` for every species `s` and `t = 0 .. k`
   (steps-major, network-species order): populations are non-negative.
3. **transition** — for `t = 0 .. k-1`, in this order:
   - enabledness: `(assert (=> f0_t (>= x<A>_t 1)))` — firing requires the
     reactant present;
   - per species `s` (network order), the guarded update
     `(assert (= x<s>_{t+1} (ite f0_t <upd(s)> x<s>_t)))` where
     `<upd(s)>` is `(- x<s>_t 1)` if `s` is the reactant `A`,
     `(+ x<s>_t 1)` if `s` is the product `B`, else `x<s>_t` (spectators
     preserved). When `f0_t` is false the species is preserved either way.
4. **bad** — reach the target marking at *some* step. For `t = 0 .. k`, build
   the per-step conjunct over the target's species (network order):
   `(and (= x<s>_t <count>) ...)` (a bare atom if only one species is named).
   Assert their disjunction: `(assert (or <conj_0> ... <conj_k>))` (a bare
   conjunct if `k = 0`).
5. `(check-sat)`.

The script is `sat` iff some firing schedule of `R0` reaches the target marking
within `k` discrete steps.

## Carry-back `L` and the soundness story

A `sat` model binds each `f0_t` and `x<s>_t`. `L` reads the `f0_t` flags into a
firing **schedule** (`0` where fired, stutter otherwise) and **replays** it
through the shared CRN interpreter `I_s` (SOLVERS.md §4: the solver only
proposes; the deterministic interpreter disposes). Soundness (PAIRING.md §6) is
byte-prediction (this schema) **plus** model validation:

- `witness_ok` — the replay's post-step markings actually reach the target;
- `model_matches_replay` — the solver's claimed per-step populations equal the
  interpreter's regrown ones (catches any arithmetic-vs-Petri-net divergence).

The SMT-level evaluator check (`smt_model_ok`) uses the shared SMT-LIB
interpreter, which is the `QF_ABV` fragment only; it declines this `QF_LIA`
script (returns `None`), and extending it would be a versioned change to a
shared interpreter outside this pair's scope (AGENTS.md §3). The CRN-interpreter
replay is the authoritative, deterministic witness check.

## Projection `π`

The species populations per step (network order) — `projection_for(net)` — and
the reach/unreach verdict. The commuting-square check `cross_check` runs
`I_s(p)` on the witness's schedule and aligns it, under `π`, against
`L(I_t(T(p)))` (the same replay), so a faithful pair makes the two traces
identical at every step and observable.
