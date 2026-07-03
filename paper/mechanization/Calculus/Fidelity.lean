import Calculus.Pasting

/-!
# The fidelity algebra

§4 of the paper: assurance classes and their chain (Definition 4.1),
weakest-link composition for the universal class (Proposition 4.2's
sound half — the classes below `universal` assert nothing a theorem
could compose, and optimality is a meta-statement over models),
per-run re-establishment (Theorem 4.3), and the branch lemmas
(Lemmas 4.4 / 4.5).

Note what is *not* here, deliberately: the `replay` class (purity) is
by construction in this model, and the grade set `G` (predicted /
proved / …) differs from classes only in evidence provenance, which is
not a mathematical object — exactly the paper's point in separating
`G` from `𝔸`.
-/

namespace Calculus

/-- Assurance classes (Definition 4.1): the totally ordered logical
forms a grade's guarantee can take. -/
inductive AClass : Type
  | none | replay | perrun | universal
deriving DecidableEq, Repr

namespace AClass

/-- The chain position: none < replay < perrun < universal. -/
def rank : AClass → Nat
  | .none => 0
  | .replay => 1
  | .perrun => 2
  | .universal => 3

instance : LE AClass := ⟨fun a b => a.rank ≤ b.rank⟩
instance : Min AClass := ⟨fun a b => if a.rank ≤ b.rank then a else b⟩

instance (a b : AClass) : Decidable (a ≤ b) :=
  inferInstanceAs (Decidable (a.rank ≤ b.rank))

theorem le_refl (a : AClass) : a ≤ a := Nat.le_refl _

theorem le_trans {a b c : AClass} (h₁ : a ≤ b) (h₂ : b ≤ c) : a ≤ c :=
  Nat.le_trans h₁ h₂

theorem min_le_left (a b : AClass) : min a b ≤ a := by
  show (if a.rank ≤ b.rank then a else b).rank ≤ a.rank
  split <;> omega

theorem min_le_right (a b : AClass) : min a b ≤ b := by
  show (if a.rank ≤ b.rank then a else b).rank ≤ b.rank
  split <;> omega

theorem le_min {a b c : AClass} (ha : c ≤ a) (hb : c ≤ b) :
    c ≤ min a b := by
  have ha' : c.rank ≤ a.rank := ha
  have hb' : c.rank ≤ b.rank := hb
  show c.rank ≤ (if a.rank ≤ b.rank then a else b).rank
  split <;> omega

end AClass

/-- **Proposition 4.2, sound half (universal ∧ universal).** If `P₁` is
faithful on `C₁` and `P₂` on `C₂`, the composite is faithful on the
pulled-back fragment: those `p ∈ C₁` whose middle column is defined and
lands in `C₂`. The classes below `universal` cap the conjunction
exactly because their guarantee predicates range over smaller sets
(`perrun`: the oracle-passed set — see `reestablishment`) or assert
nothing (`replay`, `none`). -/
theorem weakest_link_universal
    {A B C : Language} {γ₁ γ₂ γ : Type}
    {IA : Interp A} {IB : Interp B} {IC : Interp C}
    {P₁ : Pair A B γ₁} {P₂ : Pair B C γ₂} {π : A.Obs → γ}
    {C₁ : A.Prog → Prop} {C₂ : B.Prog → Prop}
    (hπ : Factors π P₁.π)
    (hsup : Supported P₁.carry P₂.π π)
    (h₁ : FaithfulOn IA IB P₁ C₁)
    (h₂ : FaithfulOn IB IC P₂ C₂) :
    FaithfulOn IA IC (P₁.comp P₂ π) (fun p =>
      C₁ p ∧ ∃ q bB bA₁, P₁.T p = some q ∧ C₂ q ∧
        IB q = some bB ∧ P₁.carry bB = some bA₁) := by
  intro p hp
  obtain ⟨hC₁, q, bB, bA₁, hT₁, hC₂, hIB, hΛ₁⟩ := hp
  exact pasting hT₁ hIB hΛ₁ hπ hsup (h₁ p hC₁) (h₂ q hC₂)

/-- **Theorem 4.3 (Per-run re-establishment).** A run whose hops each
pass the inline square oracle is faithful end to end, regardless of the
hops' static grades: "the oracle passed at `p`" *is* `FaithfulAt … p`,
so re-establishment is pasting applied to the run's own programs. The
statement is `pasting` itself; this alias records the reading. -/
theorem reestablishment
    {A B C : Language} {γ₁ γ₂ γ : Type}
    {IA : Interp A} {IB : Interp B} {IC : Interp C}
    {P₁ : Pair A B γ₁} {P₂ : Pair B C γ₂} {π : A.Obs → γ}
    {p : A.Prog} {q : B.Prog} {bB : Beh B.Obs} {bA₁ : Beh A.Obs}
    (hT₁ : P₁.T p = some q)
    (hIB : IB q = some bB)
    (hΛ₁ : P₁.carry bB = some bA₁)
    (hπ : Factors π P₁.π)
    (hsup : Supported P₁.carry P₂.π π)
    (oracle₁ : FaithfulAt IA IB P₁ p)
    (oracle₂ : FaithfulAt IB IC P₂ q) :
    FaithfulAt IA IC (P₁.comp P₂ π) p :=
  pasting hT₁ hIB hΛ₁ hπ hsup oracle₁ oracle₂

section Branching

/-! ## Branch corroboration (Lemmas 4.4 and 4.5)

Two routes from `A` to (possibly different) reasoning targets, compared
under a common keep-projection `K`. `K`-faithfulness of a route at `p`
is the proposition `projB K r = projB K bA`: the route's carried-back
behavior matches the direct interpretation under `K`. Route-level
faithfulness under a route's own projection entails it whenever `K`
factors through that projection (`kfaithful_of_faithful`). -/

variable {A : Language} {κ : Type} {K : A.Obs → κ}
variable {bA r₁ r₂ : Beh A.Obs}

/-- A route faithful under its own projection is `K`-faithful for any
`K` factoring through it. -/
theorem kfaithful_of_faithful
    {Z : Language} {γᵣ : Type}
    {IA : Interp A} {IZ : Interp Z} {R : Pair A Z γᵣ}
    {p : A.Prog} {z : Z.Prog} {bZ : Beh Z.Obs}
    (hK : Factors K R.π)
    (hT : R.T p = some z) (hIA : IA p = some bA)
    (hIZ : IZ z = some bZ) (hΛ : R.carry bZ = some r₁)
    (h : FaithfulAt IA IZ R p) :
    projB K r₁ = projB K bA :=
  (hK.congrB (h hT hIA hIZ hΛ)).symm

/-- Two `K`-faithful routes agree at `p` (the easy direction that makes
Lemma 4.4 a localization statement). -/
theorem both_faithful_agree
    (h₁ : projB K r₁ = projB K bA) (h₂ : projB K r₂ = projB K bA) :
    projB K r₁ = projB K r₂ :=
  h₁.trans h₂.symm

/-- **Lemma 4.4 (Disagreement localizes).** Disagreeing routes cannot
both be `K`-faithful — so at least one route has a failing hop, which
`localization` then pins down. (Stated constructively as the negated
conjunction.) -/
theorem disagreement_localizes
    (hne : projB K r₁ ≠ projB K r₂) :
    ¬ (projB K r₁ = projB K bA ∧ projB K r₂ = projB K bA) :=
  fun ⟨h₁, h₂⟩ => hne (both_faithful_agree h₁ h₂)

/-- **Lemma 4.5 (Agreement corroborates).** Agreeing routes are
`K`-faithful together or unfaithful together — the residue is exactly
the coincident (common-mode) defect the diversity assumption addresses. -/
theorem agreement_corroborates
    (hag : projB K r₁ = projB K r₂) :
    (projB K r₁ = projB K bA) ↔ (projB K r₂ = projB K bA) :=
  ⟨fun h => hag.symm.trans h, fun h => hag.trans h⟩

end Branching

end Calculus
