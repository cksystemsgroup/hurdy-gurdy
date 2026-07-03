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

## Axiom audit (from `Audit.lean`, checked at every build)

- **Axiom-free**: `disagreement_localizes`, `agreement_corroborates`,
  `existential_self_certifying`, `ratchet_preserves_faithful`,
  `ratchet_coverage_mono`.
- **`propext` only**: `pasting`, `pasting₃`, `weakest_link_universal`,
  `reestablishment`, `universal_needs_machinery`, `faithful_reproject`,
  `kfaithful_of_faithful`;
  `Route.route_pasting` adds `Quot.sound` (structural-recursion
  equations).
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
