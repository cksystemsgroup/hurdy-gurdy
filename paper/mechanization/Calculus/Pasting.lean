import Calculus.Basic

/-!
# Pasting and localization

Theorem 3.7 (pasting, with the support condition), its three-hop
iteration, and Corollary 3.8 (localization). The hypotheses
`hT₁ / hIB / hΛ₁` are the middle-column definedness witnesses the paper
folds into `p ∈ dom(P₂ ∘ P₁)`; determinism (functions) is what
collapses the composite's own witnesses onto them.
-/

namespace Calculus

/-- **Theorem 3.7 (Pasting).** If `P₁` is faithful at `p`, `P₂` is
faithful at `q = T₁(p)`, `π` factors through `π₁`, and `carry₁` is
`(π₂ ⇒ π)`-supported, then the composite is faithful at `p` w.r.t. `π`. -/
theorem pasting
    {A B C : Language} {γ₁ γ₂ γ : Type}
    {IA : Interp A} {IB : Interp B} {IC : Interp C}
    {P₁ : Pair A B γ₁} {P₂ : Pair B C γ₂} {π : A.Obs → γ}
    {p : A.Prog} {q : B.Prog} {bB : Beh B.Obs} {bA₁ : Beh A.Obs}
    (hT₁ : P₁.T p = some q)
    (hIB : IB q = some bB)
    (hΛ₁ : P₁.carry bB = some bA₁)
    (hπ : Factors π P₁.π)
    (hsup : Supported P₁.carry P₂.π π)
    (h₁ : FaithfulAt IA IB P₁ p)
    (h₂ : FaithfulAt IB IC P₂ q) :
    FaithfulAt IA IC (P₁.comp P₂ π) p := by
  intro r bA bC bA₂ hTc hIA hIC hΛc
  -- The composite translator's witness collapses onto q by determinism.
  simp only [Pair.comp, hT₁, Option.bind_some] at hTc
  -- Unpack the composite carry-back: bC ↦ bB' ↦ bA₂.
  simp only [Pair.comp] at hΛc
  cases hbc : P₂.carry bC with
  | none => rw [hbc] at hΛc; simp at hΛc
  | some bB' =>
    rw [hbc, Option.bind_some] at hΛc
    -- (1) P₁'s square at p, restricted from π₁ to π.
    have e1 : projB π bA = projB π bA₁ :=
      hπ.congrB (h₁ hT₁ hIA hIB hΛ₁)
    -- (2) P₂'s square at q: the two B-behaviors agree under π₂.
    have e2 : projB P₂.π bB = projB P₂.π bB' := h₂ hTc hIB hIC hbc
    -- (3) Support transports (2) through carry₁.
    have e3 : projB π bA₁ = projB π bA₂ := hsup hΛ₁ hΛc e2
    exact e1.trans e3

/-- Three-hop pasting, by iterating `pasting` — the shape of the
paper's spine `C → RISC-V → BTOR2 → SMT-LIB`. Each additional hop
demands exactly one more factoring and one more support condition. -/
theorem pasting₃
    {A B C D : Language} {γ₁ γ₂ γ₃ γ₁₂ γ : Type}
    {IA : Interp A} {IB : Interp B} {IC : Interp C} {ID : Interp D}
    {P₁ : Pair A B γ₁} {P₂ : Pair B C γ₂} {P₃ : Pair C D γ₃}
    {π₁₂ : A.Obs → γ₁₂} {π : A.Obs → γ}
    {p : A.Prog} {q : B.Prog} {r : C.Prog}
    {bB : Beh B.Obs} {bC : Beh C.Obs} {bB₁ : Beh B.Obs}
    {bA₁ bA₂ : Beh A.Obs}
    (hT₁ : P₁.T p = some q) (hT₂ : P₂.T q = some r)
    (hIB : IB q = some bB) (hIC : IC r = some bC)
    (hΛ₂ : P₂.carry bC = some bB₁) (hΛ₁ : P₁.carry bB = some bA₁)
    (hΛ₁' : P₁.carry bB₁ = some bA₂)
    (hπ₁₂ : Factors π₁₂ P₁.π) (hsup₁₂ : Supported P₁.carry P₂.π π₁₂)
    (hπ : Factors π π₁₂) (hsup : Supported (P₁.comp P₂ π₁₂).carry P₃.π π)
    (h₁ : FaithfulAt IA IB P₁ p)
    (h₂ : FaithfulAt IB IC P₂ q)
    (h₃ : FaithfulAt IC ID P₃ r) :
    FaithfulAt IA ID ((P₁.comp P₂ π₁₂).comp P₃ π) p := by
  have h₁₂ : FaithfulAt IA IC (P₁.comp P₂ π₁₂) p :=
    pasting hT₁ hIB hΛ₁ hπ₁₂ hsup₁₂ h₁ h₂
  have hT₁₂ : (P₁.comp P₂ π₁₂).T p = some r := by
    simp only [Pair.comp, hT₁, Option.bind_some]; exact hT₂
  have hΛ₁₂ : (P₁.comp P₂ π₁₂).carry bC = some bA₂ := by
    simp only [Pair.comp, hΛ₂, Option.bind_some]; exact hΛ₁'
  have hππ : Factors π (P₁.comp P₂ π₁₂).π := hπ
  intro s bA bD bA' hTc hIA hID hΛc
  exact pasting hT₁₂ hIC hΛ₁₂ hππ hsup h₁₂ h₃ hTc hIA hID hΛc

/-- **Corollary 3.8 (Localization).** Under the support condition, a
failing composite square indicts one of the two inner squares.
(Classical: an unfaithful route names no witness by itself; the square
oracle then finds the least failing step and field, which here is the
computable content of `FaithfulAt` being a decidable check per run.) -/
theorem localization
    {A B C : Language} {γ₁ γ₂ γ : Type}
    {IA : Interp A} {IB : Interp B} {IC : Interp C}
    {P₁ : Pair A B γ₁} {P₂ : Pair B C γ₂} {π : A.Obs → γ}
    {p : A.Prog} {q : B.Prog} {bB : Beh B.Obs} {bA₁ : Beh A.Obs}
    (hT₁ : P₁.T p = some q)
    (hIB : IB q = some bB)
    (hΛ₁ : P₁.carry bB = some bA₁)
    (hπ : Factors π P₁.π)
    (hsup : Supported P₁.carry P₂.π π)
    (hfail : ¬ FaithfulAt IA IC (P₁.comp P₂ π) p) :
    ¬ FaithfulAt IA IB P₁ p ∨ ¬ FaithfulAt IB IC P₂ q := by
  by_cases h₁ : FaithfulAt IA IB P₁ p
  · by_cases h₂ : FaithfulAt IB IC P₂ q
    · have hp : FaithfulAt IA IC (P₁.comp P₂ π) p :=
        pasting hT₁ hIB hΛ₁ hπ hsup h₁ h₂
      exact False.elim (hfail hp)
    · exact Or.inr h₂
  · exact Or.inl h₁

end Calculus
