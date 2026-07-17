# Mechanization of the calculus (Lean 4)

The compositional core of the paper, mechanized in Lean 4
(`leanprover/lean4:v4.31.0`, pinned in `lean-toolchain`), with **no
dependencies beyond the Lean core library** — no mathlib. Build:

```sh
# elan (the Lean toolchain manager) fetches the pinned toolchain:
lake build
```

The build prints the axiom audit (`Calculus/Audit.lean`). There are no
`sorry`s.

## Paper ↔ Lean map

| Paper | Lean (namespace `Calculus`) | File |
|---|---|---|
| Def. 3.1 (Language), behaviors | `Language`, `Beh` | `Basic.lean` |
| Def. 3.2 (Interpreter), partiality as typed abort | `Interp` (`Option`-valued) | `Basic.lean` |
| Def. 3.3 (Projection), lifted pointwise | `projB` | `Basic.lean` |
| Defs. 3.4/3.5 (Pair, Faithfulness) | `Pair`, `FaithfulAt`, `FaithfulOn` | `Basic.lean` |
| "π ⊆ π₁" (generalized) | `Factors`, `Factors.congrB` | `Basic.lean` |
| Def. 3.6 (Support) | `Supported` | `Basic.lean` |
| §3.3 composite | `Pair.comp` | `Basic.lean` |
| **Thm. 3.7 (Pasting)** | `pasting`; iterated: `pasting₃` | `Pasting.lean` |
| **Cor. 3.8 (Localization)** | `localization` | `Pasting.lean` |
| Def. 4.1 (Assurance classes) | `AClass` + chain lemmas (`min_le_left`, …) | `Fidelity.lean` |
| **Prop. 4.2 (Weakest link), sound half** | `weakest_link_universal` | `Fidelity.lean` |
| **Thm. 4.3 (Re-establishment)** | `reestablishment` | `Fidelity.lean` |
| **Lem. 4.4 (Disagreement localizes)** | `disagreement_localizes` (+ `kfaithful_of_faithful`, `both_faithful_agree`) | `Fidelity.lean` |
| **Lem. 4.5 (Agreement corroborates)** | `agreement_corroborates` | `Fidelity.lean` |
| Def. 4.6 / **Prop. 4.7 (Ratchet)** | `Extends`, `CoveredAt`, `CountsAt`, `ratchet_preserves_faithful`, `ratchet_coverage_mono` | `Ratchet.lean` |
| **Thm. 4.8 (Existential self-certification)** | `existential_self_certifying` | `EndToEnd.lean` |
| Routes (n-ary), §3.3 | `ILang`, `Route`, `Route.toPair`, `Route.Coherent`, `Route.OkAt` | `Telescope.lean` |
| **Thm. 3.7, telescoped** | `Route.route_pasting` | `Telescope.lean` |
| **Cor. 3.8, telescoped** | `Route.route_localization` (+ `faithful_reproject`) | `Telescope.lean` |
| **Thm. 4.9 (Universal answers)** | `universal_needs_machinery` | `EndToEnd.lean` |
| **Thm. 4.9 clause (iv) (Specialization)** | `Specialization`, `CommutesWithSpecialization`, `universal_from_open_artifact` | `Specialization.lean` |
| Def. 3.10 (Directional pair; lax faithfulness) | `Direction`, `DPair`, `LaxFaithfulAt` | `Lax.lean` |
| **Prop. 3.11(i) (Lax pasting; direction meet)** | `lax_pasting`; telescoped: `DRoute.lax_route_pasting`, `DRoute.direction_exact_iff` (exact hop = identity embedding: `laxFaithful_of_faithful`) | `Lax.lean` |
| **Prop. 3.11(ii) (Universal transfer)** | `lax_universal_transfer` | `Lax.lean` |
| **Exactness = identity embedding** (the arXiv v2 characterization: the exact square is the directional square's `W = id` special case) | `laxFaithful_id_iff_faithful` | `Lax.lean` |
| **Contract algebra** (the arXiv v3 composition statement: a route's contract — assurance class × direction — is the componentwise meet, the weakest hop on every axis at once) | `Contract`, `Contract.comp_glb`, `Direction.comp_eq_min` | `Contract.lean` |
| **F2 (monotone exploration)** (FRONTIER-PLAN.md §1.3; frontier paper §5) | `Frontier.answerable_mono` | `Frontier.lean` |
| **F3 (complete local gradient)**: totality, well-definedness, progress, strict progress of the first-failing condition | `Frontier.diagnosis_total`, `Frontier.diagnosis_unique`, `Frontier.diagnosis_progress`, `Frontier.diagnosis_strict_progress` | `Frontier.lean` |
| **F4 seed (chain lemma)**: `N` adequate extensions answer the question — fairness and gate liveness exist to supply them | `Frontier.adequate_chain_answerable` | `Frontier.lean` |
| **F5 (saturation terminates)**: in-set target signatures form a finite pool and never recur once admitted, so the in-set demand empties within `pool.length` iterations — and the fixpoint is an emptiness check (`gurdy saturation`) | `Frontier.saturation_terminates` | `Frontier.lean` |
| **Status ratchet** (§1.6 currency: tiers only advance, evidence travels) | `Frontier.Tier`, `Frontier.lifecycle_ratchet` | `Frontier.lean` |
| **Conditional-plan soundness under discharge** (§1.6: mixed routes never overpromise) | `Frontier.Dominates`, `Frontier.conditional_plan_sound`, `Contract.comp_mono` | `Frontier.lean` |

(Def. 3.10 / Prop. 3.11 are the arXiv version's directional-squares
subsection of §3; the POPL submission does not contain them. Numbered
references above follow the POPL version; the arXiv v3 restructure
renumbers Thm. 4.8/4.9 → 4.6/4.7 and Def. 4.6/Prop. 4.7 → 5.1/5.2 —
labels are unchanged, so `\Cref` resolves in both.)

## Modeling choices (mirroring the paper)

- **Purity by construction**: components are Lean functions, so
  determinism (the premise of Prop. 3.9) is definitional and Prop. 3.9
  itself is not restated.
- **Partiality is `Option`**: `none` is the typed `unsupported` abort;
  covered fragments are definedness sets.
- **Projections are compression maps** `Obs → γ`; the paper's
  field-subset projection is the restriction special case, and
  "π ⊆ π₁" becomes factoring (`Factors`).
- **Hypotheses are the TCB**: theorems take each component-output
  witness explicitly, so a statement's trusted base is literally its
  hypothesis list — e.g. `existential_self_certifying` assumes
  adequacy of the source interpreter and *nothing else*.
- **The frontier model consumes the calculus, it does not re-derive
  it** (`Frontier.lean`): answerability is a *filtration* — admitted
  candidate lists shrinking through `N` ordered conditions (the
  platform's five: connectivity, loss, shape, cost, trust), growing
  with the registry — and a candidate is the list of admitted *items*
  an answer rests on, pairs and language capabilities alike (the
  route-level currency). F2, F3, and the chain lemma are consequences
  of the filtration's two monotonicities; what the diagnosis *names*
  is `why_not`'s specification, entering only as the `Reaches (k+1)`
  hypothesis of the strict-progress and chain lemmas.

## Axiom audit (from `Audit.lean`, checked at every build)

- **Axiom-free**: `disagreement_localizes`, `agreement_corroborates`,
  `existential_self_certifying`, `ratchet_preserves_faithful`,
  `ratchet_coverage_mono`, `laxFaithful_of_faithful`,
  `laxFaithful_id_iff_faithful`, `Direction.comp_eq_min`.
- **`propext` only**: `pasting`, `pasting₃`, `weakest_link_universal`,
  `reestablishment`, `universal_needs_machinery`, `faithful_reproject`,
  `kfaithful_of_faithful`, `lax_pasting`, `lax_universal_transfer`,
  `DRoute.direction_exact_iff`;
  `Route.route_pasting` and `DRoute.lax_route_pasting` add `Quot.sound`
  (structural-recursion equations), as does `Contract.comp_glb`
  (structure eta).
- **Classical** (`Classical.choice`): `localization` and its telescoped
  form `Route.route_localization` — the
  contrapositive case split; an unfaithful route names no witness by
  itself.

## Deliberately not mechanized (paper-proved / meta)

- The fieldwise keep/loss computation and the retiming (window) case
  (Appendix A.2) — syntactic side conditions over a concrete carry-back
  representation.
- The optimality halves of Prop. 4.2 (counterexample meta-statements
  over models) and the grade set `G` (evidence provenance, not a
  mathematical object — the point of the `G` / `𝔸` separation).
- The non-transfer of existential verdicts across an `over` square
  (Prop. 3.11(ii)'s negative half) — a counterexample meta-statement,
  like the optimality halves; the positive discipline is
  `existential_self_certifying`'s carried-back replay.
