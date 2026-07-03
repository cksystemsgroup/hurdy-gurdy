import Calculus.Basic

/-!
# The ratchet

Proposition 4.7: additive extensions preserve every faithfulness
verdict on the old domain, and per-construct coverage (covered ∧
faithful) is monotone. The failure half of the proposition — a
non-extension update can silently flip verdicts — is a meta-statement
over models (any concrete counterexample witnesses it) and is what the
versioned-event discipline exists for.
-/

namespace Calculus

/-- `f'` extends `f`: defined wherever `f` is, with the same value —
the paper's `I' ⊒ I`. -/
def Extends {α β : Type} (f' f : α → Option β) : Prop :=
  ∀ a b, f a = some b → f' a = some b

theorem Extends.refl {α β : Type} (f : α → Option β) : Extends f f :=
  fun _ _ h => h

theorem Extends.trans {α β : Type} {f g h : α → Option β}
    (hfg : Extends f g) (hgh : Extends g h) : Extends f h :=
  fun a b hb => hfg a b (hgh a b hb)

/-- A program is *covered* by the four components when the whole square
is defined at it. -/
def CoveredAt {A B : Language} {γ : Type}
    (IA : Interp A) (IB : Interp B) (P : Pair A B γ) (p : A.Prog) : Prop :=
  ∃ q bA bB bA', P.T p = some q ∧ IA p = some bA ∧
    IB q = some bB ∧ P.carry bB = some bA'

/-- Per-construct counting (Definition 4.6, at the granularity of
probe programs): a probe counts iff covered *and* faithful. -/
def CountsAt {A B : Language} {γ : Type}
    (IA : Interp A) (IB : Interp B) (P : Pair A B γ) (p : A.Prog) : Prop :=
  CoveredAt IA IB P p ∧ FaithfulAt IA IB P p

/-- **Proposition 4.7 (Ratchet), preservation half.** Extensions of all
four components preserve faithfulness at every point of the old domain:
on old-domain points the new components return the old values
(determinism), so the old verdict transfers verbatim. -/
theorem ratchet_preserves_faithful
    {A B : Language} {γ : Type}
    {IA' IA : Interp A} {IB' IB : Interp B} {P' P : Pair A B γ}
    (hA : Extends IA' IA) (hB : Extends IB' IB)
    (hT : Extends P'.T P.T) (hΛ : Extends P'.carry P.carry)
    (hπ : P'.π = P.π)
    {p : A.Prog}
    (hdom : CoveredAt IA IB P p)
    (h : FaithfulAt IA IB P p) :
    FaithfulAt IA' IB' P' p := by
  obtain ⟨q, bA, bB, bA', hT₀, hIA₀, hIB₀, hΛ₀⟩ := hdom
  intro q₁ bA₁ bB₁ bA₁' hT₁ hIA₁ hIB₁ hΛ₁
  -- New-component witnesses collapse onto the old ones (determinism).
  have hq : q₁ = q := by
    have := hT p q hT₀; rw [hT₁] at this
    exact Option.some.inj this
  subst hq
  have hbA : bA₁ = bA := by
    have := hA p bA hIA₀; rw [hIA₁] at this
    exact Option.some.inj this
  subst hbA
  have hbB : bB₁ = bB := by
    have := hB q₁ bB hIB₀; rw [hIB₁] at this
    exact Option.some.inj this
  subst hbB
  have hbA' : bA₁' = bA' := by
    have := hΛ bB₁ bA' hΛ₀; rw [hΛ₁] at this
    exact Option.some.inj this
  subst hbA'
  rw [hπ]
  exact h hT₀ hIA₀ hIB₀ hΛ₀

/-- Coverage is monotone under extensions: whatever counted, still
counts. Hence per-construct coverage ratchets over project history. -/
theorem ratchet_coverage_mono
    {A B : Language} {γ : Type}
    {IA' IA : Interp A} {IB' IB : Interp B} {P' P : Pair A B γ}
    (hA : Extends IA' IA) (hB : Extends IB' IB)
    (hT : Extends P'.T P.T) (hΛ : Extends P'.carry P.carry)
    (hπ : P'.π = P.π)
    {p : A.Prog}
    (h : CountsAt IA IB P p) :
    CountsAt IA' IB' P' p := by
  obtain ⟨⟨q, bA, bB, bA', hT₀, hIA₀, hIB₀, hΛ₀⟩, hfaith⟩ := h
  refine ⟨⟨q, bA, bB, bA', hT p q hT₀, hA p bA hIA₀,
    hB q bB hIB₀, hΛ bB bA' hΛ₀⟩, ?_⟩
  exact ratchet_preserves_faithful hA hB hT hΛ hπ
    ⟨q, bA, bB, bA', hT₀, hIA₀, hIB₀, hΛ₀⟩ hfaith

end Calculus
