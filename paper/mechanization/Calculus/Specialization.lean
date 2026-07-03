import Calculus.EndToEnd

/-!
# The specialization obligation

Clause (iv) of Theorem 4.9: the symbolic artifact the solver consumes
must denote the family of closed translations the squares check —
*translation commutes with input specialization*. The platform
translates the open program **once**; the solver's universal verdict
ranges over the target-side instantiations of that single artifact.
This file states the obligation and proves that, together with it, the
per-instance-translation hypothesis of `universal_needs_machinery` is
discharged from the one open translation the platform actually
performs.

As everywhere in this mechanization, hypotheses are the TCB: the
target-side reading of "the solver's verdict covers every
instantiation" (`hZ`) is exactly the reasoning language's input
semantics, and the obligation itself (`commutes`) is what each
reasoning pair discharges by construction of its encoding.
-/

namespace Calculus

/-- An input-specialization structure for an open program over inputs
`X`: closing substitutions on both sides of a pair. `specA x` closes
the source program at input `x`; `specZ x` instantiates the symbolic
target artifact at (the image of) `x`. -/
structure Specialization (A Z : Language) (X : Type) : Type where
  specA : X → A.Prog → A.Prog
  specZ : X → Z.Prog → Z.Prog

/-- **The specialization obligation** (Theorem 4.9, clause (iv)):
translating the closed instance agrees with instantiating the one open
translation, at every input. -/
def CommutesWithSpecialization {A Z : Language} {γ : Type}
    (R : Pair A Z γ) (S : Specialization A Z X)
    (p₀ : A.Prog) (z₀ : Z.Prog) : Prop :=
  ∀ x : X, R.T (S.specA x p₀) = some (S.specZ x z₀)

/-- **Theorem 4.9 from one open artifact.** With the specialization
obligation, `universal_needs_machinery`'s per-instance translations
are derived rather than assumed: the platform translates the open
program once (`hopen`), the obligation supplies every instance's
translation, and the certified target-side verdict over the artifact's
instantiations (`hZ`) yields the universal source-side conclusion for
the family `fun x => S.specA x p₀`. -/
theorem universal_from_open_artifact
    {A Z : Language} {γᵣ κ : Type} {X : Type}
    {sem IA : Interp A} {IZ : Interp Z} {R : Pair A Z γᵣ}
    {p₀ : A.Prog} {z₀ : Z.Prog} {S : Specialization A Z X}
    {K : A.Obs → κ}
    (hK : Factors K R.π)
    (adequacy : ∀ q b, IA q = some b → sem q = some b)
    {φ : Beh κ → Prop} {φZ : Beh Z.Obs → Prop}
    (_hopen : R.T p₀ = some z₀)
    (commutes : CommutesWithSpecialization R S p₀ z₀)
    (hIZ : ∀ x, ∃ bZ, IZ (S.specZ x z₀) = some bZ)
    (hcarry : ∀ x bZ, IZ (S.specZ x z₀) = some bZ →
      ∃ r, R.carry bZ = some r)
    (hIA : ∀ x, ∃ b, IA (S.specA x p₀) = some b)
    (hfaith : ∀ x, FaithfulAt IA IZ R (S.specA x p₀))
    (hcorr : ∀ bZ r, R.carry bZ = some r → φ (projB K r) → φZ bZ)
    (hZ : ∀ x bZ, IZ (S.specZ x z₀) = some bZ → ¬ φZ bZ) :
    ∀ x b, sem (S.specA x p₀) = some b → ¬ φ (projB K b) := by
  refine universal_needs_machinery (p := fun x => S.specA x p₀)
    hK adequacy ?_ hIA hfaith hcorr ?_
  · intro x
    obtain ⟨bZ, hbZ⟩ := hIZ x
    obtain ⟨r, hr⟩ := hcarry x bZ hbZ
    exact ⟨S.specZ x z₀, bZ, r, commutes x, hbZ, hr⟩
  · intro x z bZ hT hIZ'
    have hz : S.specZ x z₀ = z := Option.some.inj ((commutes x).symm.trans hT)
    exact hZ x bZ (hz ▸ hIZ')

end Calculus
