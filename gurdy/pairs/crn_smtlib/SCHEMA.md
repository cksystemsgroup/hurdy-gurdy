# `crn-smtlib` schema — CRN → SMT-LIB bounded reachability

A **transparent reasoning pair** (`DESIGN_pair_taxonomy.md`): `in_lang = crn`,
`out_lang = smtlib`, `tier = transparent`. The translation is pure,
deterministic, and fully specified here — given the CRN, the spec, and this
schema, the SMT-LIB is determined byte-for-byte (`PAIRING.md` §5, the
predictability invariant, in chemistry). `out_lang` is a reasoning language: z3
decides the emitted QF_LIA, so a chemistry question becomes *answerable*.

This is the second reasoning pair (after `riscv-btor2`) and the second hub
(SMT-LIB). It also closes the field-blindness arc opened by `smiles-formula`
(Stage 6): there a chemistry input reached a *representation*; here one reaches a
*solver*.

## 1. Input language (`crn`)

A chemical reaction network under **discrete population (Petri-net) semantics**:
state is a vector of non-negative integer molecule counts; a reaction may fire
when each reactant is present at least its stoichiometric coefficient, consuming
reactants and producing products. Text format (one reaction per line, `#`
comments), parsed by `model.parse_crn`:

```
r_fwd: A -> B        # optional name: prefix; coefficients default to 1
B -> A
2 A -> C             # stoichiometric coefficient
-> A                 # inflow  (no reactants — always enabled)
A ->                 # outflow (no products)
```

Species are inferred and **declared in sorted order**, so the encoding is
independent of mention order. Out-of-format input raises `CrnParseError`.

## 2. The question (spec)

`CrnSpec` is a bounded reachability question:

- `initial`: `species -> count` (unmentioned species start at 0);
- `target`: `count[species] <op> value` with `op ∈ {>=, ==, <=}`;
- `bound`: `N`, the maximum number of reaction firings to consider;
- `analysis`: `engine` (default `z3-smt`) and an optional `timeout`.

## 3. Encoding (QF_LIA, deterministic)

For `N = bound`, species `S`, reactions `R = r_0..r_{R-1}` with net change
`Δ_r[s] = (products) − (reactants)`:

- **Variables**: `x_<s>_<t>` (Int) for each species `s`, `t ∈ 0..N` — the count
  of `s` after `t` firings; `sel_<t>` (Int) for `t ∈ 0..N-1` — which reaction
  fires at step `t`.
- **Non-negativity**: `x_<s>_<t> ≥ 0`.
- **Selector domain**: `0 ≤ sel_<t> ≤ R-1`.
- **Initial**: `x_<s>_0 = initial[s]`.
- **Guards**: for each step and reaction with reactants,
  `(sel_t = r) ⇒ ⋀_reactants (x_<s>_t ≥ coeff)` — a reaction fires only when its
  reactants are available.
- **Updates**: `x_<s>_{t+1} = x_<s>_t + ite-chain over sel_t of Δ_r[s]`.
- **Target**: asserted to hold at *some* step — `⋁_{t=0..N} (x_<species>_t <op> value)`.

`(check-sat)` is **sat** iff the target is reachable within `N` firings; the
model is a witness trajectory. A `; @crn-meta {...}` header records species,
reaction names, the bound, and the target so the lifter can ground the model.

## 4. Solver + lift

`z3-smt` (`backend.Z3SmtSolver`) runs the SMT-LIB in z3 in-process: `sat →
reachable`, `unsat → unreachable`, else `unknown`. On `reachable`, the lifter
(`backend.CrnLifter`) reconstructs the per-step trajectory (counts + the firing
reaction name) from the model and the `@crn-meta` header.

## 5. Determinism & preservation

`emit_smtlib` is a pure function of `(spec, crn)`: sorted species, fixed clause
order, fixed Hill-free formatting — same inputs, identical bytes. **Keeps**:
integer species counts, reaction stoichiometry, reachability. **Discards**:
reaction *rates*, kinetics, continuous-time dynamics (the deterministic
mass-action ODE / stochastic CTMC readings of the same CRN are out of scope) —
this is exactly the kind of explicit loss the `Preservation` contract records.

## 6. Scope (raises, does not guess)

Single connected reachability question, integer counts, the three comparison
ops. No rate constants, no continuous/stochastic dynamics, no multi-target
conjunctions (a single `target`). These are deliberate omissions, documented
rather than silently mishandled.
