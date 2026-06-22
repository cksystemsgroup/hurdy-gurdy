# crn-smtlib translation schema (`predicted`)

This is the self-contained, reviewable specification the translator `T`
implements mechanically (PAIRING.md §2). Given the source network, the step
bound `k`, and a target marking, the emitted SMT-LIB script is determined
**byte-for-byte** by the rules below — no adaptive choices, no hashing, no
timestamps. Anyone with the source, the bound, and this schema can reproduce the
output exactly (the `predicted` predictability test).

## Scope (the covered reaction classes)

In scope: a network of **exactly one reaction** `R0`. Concretely three reaction
classes (each with reactant and product side disjoint — no self-loop):

- **unimolecular** `A -> B` — one unit reactant, one unit product, distinct;
- **bimolecular** — total reactant tokens (reactant molecularity) = 2 with a
  single unit product: either two distinct unit reactants `A + B -> C`, or one
  doubled reactant `2 A -> B` (dimerization);
- **catalysis / multi-product** — one unit reactant (reactant molecularity 1)
  with a product of molecularity 2: `A -> 2 B` (one doubled product /
  amplification) or `A -> B + C` (two distinct unit products).

So the two molecularities (reactant, product) jointly cover `(1,1)`, `(2,1)`,
`(1,2)` — *not* `(2,2)`: a molecularity-2 product is admitted only on a
single-unit reactant side. Any number of declared species (the others are
spectators). Every product species must be distinct from every reactant species
(no self-loop).

Everything else hard-aborts with a typed `unsupported: crn:<construct>`
(BENCHMARKS.md §3), never a silent drop:

| construct | abort |
|---|---|
| no reactions | `crn:empty-network` |
| ≥2 reactions | `crn:multiple-reactions` |
| no reactant (`0 -> A`) | `crn:synthesis` |
| no product (`A -> 0`) | `crn:degradation` |
| reactant molecularity ≥ 3 (`A + B + C`, `3 A`) | `crn:trimolecular` |
| product molecularity ≥ 3 (`A -> 3 B`), or a molecularity-2 product on a non-unit reactant side (`2 A -> 2 B`, `A + B -> 2 C`) | `crn:catalysis` |
| a product is also a reactant (`A -> A`, `A + B -> A`, `A -> A + C`) | `crn:self-loop` |
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
3. **transition** — for `t = 0 .. k-1`, in this order. Let `Rc[s]` be species
   `s`'s reactant coefficient (0 if absent) and `Pc[s]` its product coefficient.
   - enabledness: one `(>= x<r>_t Rc[r])` conjunct per reactant species `r`, in
     reaction order — firing requires every reactant present in at least its
     stoichiometric coefficient (the Petri-net precondition, **linear** in the
     marking). With one reactant the guard is the bare atom; with two it is
     `(and <atom_1> <atom_2>)`. Asserted as `(assert (=> f0_t <guard>))`.
     (Unimolecular `A -> B`: `(>= xA_t 1)`. `2 A -> B`: `(>= xA_t 2)`.
     `A + B -> C`: `(and (>= xA_t 1) (>= xB_t 1))`.)
   - per species `s` (network order), the guarded update
     `(assert (= x<s>_{t+1} (ite f0_t <upd(s)> x<s>_t)))` where `<upd(s)>` is the
     *net* stoichiometry `n = Pc[s] - Rc[s]`: `(- x<s>_t |n|)` if `n < 0`,
     `(+ x<s>_t n)` if `n > 0`, else `x<s>_t` (spectator / net-zero species
     preserved). When `f0_t` is false the species is preserved either way.
     (Unimolecular `A -> B`: `A` net `-1` ⇒ `(- xA_t 1)`, `B` net `+1` ⇒
     `(+ xB_t 1)` — byte-identical to the pre-widening emission. Catalysis
     `A -> 2 B`: `A` net `-1`, `B` net `+2` ⇒ `(+ xB_t 2)`. Multi-product
     `A -> B + C`: `A` net `-1`, `B` net `+1`, `C` net `+1`.)
4. **bad** — reach the target marking at *some* step. For `t = 0 .. k`, build
   the per-step conjunct over the target's species (network order):
   `(and (= x<s>_t <count>) ...)` (a bare atom if only one species is named).
   Assert their disjunction: `(assert (or <conj_0> ... <conj_k>))` (a bare
   conjunct if `k = 0`).
5. `(check-sat)`.

The script is `sat` iff some firing schedule of `R0` reaches the target marking
within `k` discrete steps. The bimolecular and catalysis encodings extend the
unimolecular one *additively* — same per-step firing schema (one `f0_t` flag, one
`ite`-guarded update per species), only the consumption/production coefficients
and the number of enabledness conjuncts change — so the QF_LIA fragment is
unchanged. Catalysis touches only the *product* coefficients (`Pc`), so its
enabledness is the bare unimolecular `(>= xA_t 1)` and its only departure from
the unimolecular bytes is a larger increment on the product side(s).

## Carry-back `L` and the soundness story

A `sat` model binds each `f0_t` and `x<s>_t`. `L` reads the `f0_t` flags into a
firing **schedule** (`0` where fired, stutter otherwise) and **replays** it
through the shared CRN interpreter `I_s` (SOLVERS.md §4: the solver only
proposes; the deterministic interpreter disposes). Soundness (PAIRING.md §6) is
byte-prediction (this schema) **plus** model validation:

- `witness_ok` — the replay's post-step markings actually reach the target;
- `model_matches_replay` — the solver's claimed per-step populations equal the
  interpreter's regrown ones (catches any arithmetic-vs-Petri-net divergence).

The SMT-level evaluator check (`smt_model_ok`) re-evaluates the emitted `QF_LIA`
script under the solver's model with the shared SMT-LIB interpreter (`Int` over
arbitrary-precision integers, interp v0.2 — the QF_LIA arm). For a `reachable`
verdict it must hold and must **agree** with the CRN-interpreter replay
(`witness_ok` / `model_matches_replay`); a divergence is a translator-or-solver
fault. The bimolecular enabledness (`>=`) and the bimolecular / catalysis
net-stoichiometry updates (`+` / `-` / `ite`, with the larger product increment
for `A -> 2 B`) stay inside that already-built QF_LIA fragment, so no
shared-language change is needed for these widenings (AGENTS.md §3). The
CRN-interpreter replay remains the deterministic, authoritative witness check;
`smt_model_ok` corroborates it independently at the SMT level.

## Projection `π`

The species populations per step (network order) — `projection_for(net)` — and
the reach/unreach verdict. The commuting-square check `cross_check` runs
`I_s(p)` on the witness's schedule and aligns it, under `π`, against
`L(I_t(T(p)))` (the same replay), so a faithful pair makes the two traces
identical at every step and observable.
