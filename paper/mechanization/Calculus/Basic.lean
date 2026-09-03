/-!
# The calculus of pairs — basic definitions

Mechanization of §3 of the paper (Definitions 3.1–3.6): languages,
behaviors, projections, interpreters, pairs, faithfulness, projection
factoring (the "π ⊆ π₁" of the paper, generalized to arbitrary
observable-compression maps), and the support condition.

Modeling choices, mirrored from the paper:

* **Purity is by construction.** Interpreters, translators and
  carry-backs are Lean functions, so determinism (§3, Proposition 3.9's
  premise) holds definitionally; the mechanization does not restate it.
* **Partiality is `Option`.** A typed `unsupported` abort is `none`;
  a component's covered fragment is the set of inputs where it is `some`.
* **Projections are compression maps.** The paper's π ⊆ F (a subset of
  named fields, lifted by restriction) is the special case of an
  arbitrary map out of the observable type; "π ⊆ π₁" becomes `Factors`
  (π factors through π₁), which is exactly what the proofs use.
* **Hypotheses are the TCB.** Theorems take the definedness witnesses
  of each component output explicitly, so the trusted base of every
  statement is literally its hypothesis list.
-/

namespace Calculus

/-- A language: programs plus an observable-state type (Definition 3.1,
with the field structure of observables abstracted away). -/
structure Language : Type 1 where
  Prog : Type
  Obs  : Type

/-- A behavior: a finite post-step trace of observable states. -/
abbrev Beh (O : Type) : Type := List O

/-- A projection lifted pointwise to behaviors (Definition 3.3).
Projected behaviors of different lengths are unequal, as in the paper. -/
def projB {O γ : Type} (π : O → γ) (b : Beh O) : Beh γ := b.map π

/-- An interpreter: a partial function from programs to behaviors
(Definition 3.2). Pure by construction. -/
abbrev Interp (L : Language) : Type := L.Prog → Option (Beh L.Obs)

/-- A pair `P : A → B` (Definition 3.4): translator, target-to-source
interpreter (carry-back), and declared projection into `γ`. The two
language interpreters are language-owned and passed separately. -/
structure Pair (A B : Language) (γ : Type) : Type where
  T     : A.Prog → Option B.Prog
  carry : Beh B.Obs → Option (Beh A.Obs)
  π     : A.Obs → γ

/-- The commuting square at `p` (Definition 3.5): whenever every
component is defined at `p`, the directly-interpreted behavior and the
carried-back behavior agree under the declared projection. -/
@[reducible] def FaithfulAt {A B : Language} {γ : Type}
    (IA : Interp A) (IB : Interp B) (P : Pair A B γ) (p : A.Prog) : Prop :=
  ∀ {q : B.Prog} {bA : Beh A.Obs} {bB : Beh B.Obs} {bA' : Beh A.Obs},
    P.T p = some q → IA p = some bA → IB q = some bB →
    P.carry bB = some bA' →
    projB P.π bA = projB P.π bA'

/-- Faithfulness on a fragment (a set of programs). -/
@[reducible] def FaithfulOn {A B : Language} {γ : Type}
    (IA : Interp A) (IB : Interp B) (P : Pair A B γ)
    (C : A.Prog → Prop) : Prop :=
  ∀ p, C p → FaithfulAt IA IB P p

/-- `π` factors through `π₁` — the mechanized form of the paper's
`π ⊆ π₁`: everything `π` observes is recoverable from what `π₁`
observes. -/
def Factors {O γ₁ γ : Type} (π : O → γ) (π₁ : O → γ₁) : Prop :=
  ∃ g : γ₁ → γ, π = g ∘ π₁

/-- Factoring transports behavior agreement: `π₁`-equal behaviors are
`π`-equal (the restriction step in the pasting proof). -/
theorem Factors.congrB {O γ₁ γ : Type} {π : O → γ} {π₁ : O → γ₁}
    (h : Factors π π₁) {b b' : Beh O}
    (hb : projB π₁ b = projB π₁ b') : projB π b = projB π b' := by
  obtain ⟨g, rfl⟩ := h
  simp only [projB] at *
  rw [← List.map_map, ← List.map_map]
  exact congrArg (List.map g) hb

/-- Every projection factors through itself. -/
theorem Factors.rfl {O γ : Type} (π : O → γ) : Factors π π :=
  ⟨id, funext fun _ => Eq.refl _⟩

/-- Factoring composes. -/
theorem Factors.trans {O γ₂ γ₁ γ : Type} {π : O → γ} {π₁ : O → γ₁}
    {π₂ : O → γ₂} (h : Factors π π₁) (h' : Factors π₁ π₂) :
    Factors π π₂ := by
  obtain ⟨g, rfl⟩ := h
  obtain ⟨g', rfl⟩ := h'
  exact ⟨g ∘ g', funext fun _ => Eq.refl _⟩

/-- The support condition (Definition 3.6): the earlier hop's carry-back
must not distinguish behaviors the later hop's projection identifies —
`carry` is `(π₂ ⇒ π)`-supported, exactly as in the paper (a congruence
condition: `π ∘ carry` descends to π₂-equivalence classes). -/
def Supported {A B : Language} {γ₂ γ : Type}
    (carry : Beh B.Obs → Option (Beh A.Obs))
    (π₂ : B.Obs → γ₂) (π : A.Obs → γ) : Prop :=
  ∀ {b b' : Beh B.Obs} {a a' : Beh A.Obs},
    carry b = some a → carry b' = some a' →
    projB π₂ b = projB π₂ b' → projB π a = projB π a'

/-- The candidate composite `P₂ ∘ P₁` at a chosen projection `π`
(§3.3): translate through both, carry back right-to-left. -/
def Pair.comp {A B C : Language} {γ₁ γ₂ γ : Type}
    (P₁ : Pair A B γ₁) (P₂ : Pair B C γ₂) (π : A.Obs → γ) :
    Pair A C γ where
  T := fun p => (P₁.T p).bind P₂.T
  carry := fun bC => (P₂.carry bC).bind P₁.carry
  π := π

end Calculus
