import Calculus.Basic
import Calculus.Pasting
import Calculus.Telescope

/-!
# Directional squares (the lax extension)

Mechanization of the paper's §"Directional squares: abstraction as a
pair" — Definition 3.10 (directional pair; lax faithfulness) and
Proposition 3.11 (direction composes; universal transfer).

Modeling choices, continuous with the rest of the mechanization:

* **Open programs are families.** As in `EndToEnd.lean`, an open
  program is its family of closed instances, indexed by its closing
  valuations; the translated artifact `T(p)` is likewise the family of
  its target-side instantiations. The witness embedding `W` maps
  source valuations to target valuations, and the lax square at `x` is
  the *closed, exact* square between `p x` and `t (W x)` —
  `LaxFaithfulAt` is `FaithfulAt`'s comparison run along `W`, so the
  square-oracle machinery is unchanged, exactly as the paper says.
* **Direction is data.** `Direction.comp` is the meet on the chain
  `exact > over`; a directional pair carries its direction, composites
  compose it, and `DRoute.direction_exact_iff` is the "exact iff every
  hop is" clause of Proposition 3.11(i).
* **An exact hop contributes the identity embedding**
  (`laxFaithful_of_faithful`): a pair faithful at every closed
  instance is lax-faithful along `id`, which is how exact and over
  hops mix in one telescope.
* **Universal transfer takes no direction hypothesis.**
  `lax_universal_transfer` holds along any lax-faithful square; the
  paper states it for `over` routes because there it is the *only*
  transfer. Existential verdicts remain subject to the carried-back
  replay (`existential_self_certifying`), whose failure on an `over`
  route is the spurious-counterexample reading — a refinement demand,
  not mechanizable content (a counterexample meta-statement).
-/

namespace Calculus

/-- A square's direction (Definition 3.10): exact (Definition 3.5 its
contract) or over-approximating (the target admits every source
behavior on the kept observables, and possibly more). -/
inductive Direction : Type where
  | exact
  | over
deriving DecidableEq

namespace Direction

/-- Directions compose as the meet on the chain `exact > over`
(Proposition 3.11(i)): a composite is exact iff both hops are. -/
def comp : Direction → Direction → Direction
  | .exact, d => d
  | .over, _ => .over

@[simp] theorem comp_exact_iff (d₁ d₂ : Direction) :
    d₁.comp d₂ = .exact ↔ d₁ = .exact ∧ d₂ = .exact := by
  cases d₁ <;> cases d₂ <;> simp [comp]

end Direction

/-- Lax faithfulness along a witness embedding (Definition 3.10): at
every source valuation `x`, the *closed* square between the source
instance `p x` and the target instance `t (W x)` commutes under `π` —
the target simulates the source along `W`. Target valuations outside
the range of `W` are the abstraction's added behaviors; nothing here
constrains them. -/
@[reducible] def LaxFaithfulAt {A B : Language} {γ : Type} {X Y : Type}
    (IA : Interp A) (IB : Interp B) (P : Pair A B γ)
    (p : X → A.Prog) (t : Y → B.Prog) (W : X → Y) : Prop :=
  ∀ (x : X) {bA : Beh A.Obs} {bB : Beh B.Obs} {bA' : Beh A.Obs},
    IA (p x) = some bA → IB (t (W x)) = some bB →
    P.carry bB = some bA' →
    projB P.π bA = projB P.π bA'

/-- An exact hop enters a lax telescope with the identity embedding: a
pair faithful at every closed instance (whose translator produces the
instance family, `t x = T (p x)`) is lax-faithful along `id`. -/
theorem laxFaithful_of_faithful {A B : Language} {γ : Type} {X : Type}
    {IA : Interp A} {IB : Interp B} {P : Pair A B γ}
    {p : X → A.Prog} {t : X → B.Prog}
    (hT : ∀ x, P.T (p x) = some (t x))
    (h : ∀ x, FaithfulAt IA IB P (p x)) :
    LaxFaithfulAt IA IB P p t id := by
  intro x bA bB bA' hIA hIB hΛ
  exact h x (hT x) hIA hIB hΛ

/-- **Exactness is the identity embedding.** Given the translator tie
`t x = T (p x)`, per-instance faithfulness (the two-sided square of
Definition 3.5) is *precisely* lax faithfulness along `id`: the exact
square is the special case of the directional square where the witness
embedding is the identity — every target valuation is checked, so
nothing is added. The formal anchor of the arXiv version's
"non-lax is the special case" presentation. -/
theorem laxFaithful_id_iff_faithful {A B : Language} {γ : Type} {X : Type}
    {IA : Interp A} {IB : Interp B} {P : Pair A B γ}
    {p : X → A.Prog} {t : X → B.Prog}
    (hT : ∀ x, P.T (p x) = some (t x)) :
    LaxFaithfulAt IA IB P p t id ↔ ∀ x, FaithfulAt IA IB P (p x) := by
  constructor
  · intro h x
    intro q bA bB bA' hTx hIA hIB hΛ
    -- determinism collapses the translator witness onto t x
    have hq : t x = q := Option.some.inj ((hT x).symm.trans hTx)
    exact h x hIA (hq ▸ hIB) hΛ
  · exact laxFaithful_of_faithful hT

/-- A directional pair (Definition 3.10): a pair together with its
declared direction and the witness embedding its lax square is checked
along. Valuation types are per-language (`X` source, `Y` target); an
exact pair is the degenerate `⟨P, .exact, id⟩` (`DPair.ofExact`). -/
structure DPair (A B : Language) (γ : Type) (X Y : Type) : Type where
  P : Pair A B γ
  d : Direction
  W : X → Y

/-- An exact pair as a directional pair: identity embedding. -/
def DPair.ofExact {A B : Language} {γ : Type} (X : Type)
    (P : Pair A B γ) : DPair A B γ X X :=
  ⟨P, .exact, id⟩

/-- The composite of two directional pairs at a chosen projection:
pairs compose as in §3.3, directions as the meet, embeddings by
composition — the data of Proposition 3.11(i). -/
def DPair.comp {A B C : Language} {γ₁ γ₂ γ : Type} {X Y Z : Type}
    (D₁ : DPair A B γ₁ X Y) (D₂ : DPair B C γ₂ Y Z) (π : A.Obs → γ) :
    DPair A C γ X Z where
  P := D₁.P.comp D₂.P π
  d := D₁.d.comp D₂.d
  W := D₂.W ∘ D₁.W

@[simp] theorem DPair.comp_d {A B C : Language} {γ₁ γ₂ γ : Type}
    {X Y Z : Type} (D₁ : DPair A B γ₁ X Y) (D₂ : DPair B C γ₂ Y Z)
    (π : A.Obs → γ) : (D₁.comp D₂ π).d = D₁.d.comp D₂.d := rfl

/-- **Proposition 3.11(i), binary core (lax pasting).** If `D₁` is
lax-faithful from `p` to `t` along `W₁` and `D₂` from `t` to `u` along
`W₂`, then — under the same factoring and support conditions as
Theorem 3.7, with the middle column defined along the embedded
valuations — their composite is lax-faithful from `p` to `u` along the
composed embedding `W₂ ∘ W₁`. The composite's direction is the meet by
construction (`DPair.comp_d`). -/
theorem lax_pasting
    {A B C : Language} {γ₁ γ₂ γ : Type} {X Y Z : Type}
    {IA : Interp A} {IB : Interp B} {IC : Interp C}
    {D₁ : DPair A B γ₁ X Y} {D₂ : DPair B C γ₂ Y Z} {π : A.Obs → γ}
    {p : X → A.Prog} {t : Y → B.Prog} {u : Z → C.Prog}
    (hmid : ∀ x, ∃ bB bA₁, IB (t (D₁.W x)) = some bB ∧
      D₁.P.carry bB = some bA₁)
    (hπ : Factors π D₁.P.π)
    (hsup : Supported D₁.P.carry D₂.P.π π)
    (h₁ : LaxFaithfulAt IA IB D₁.P p t D₁.W)
    (h₂ : LaxFaithfulAt IB IC D₂.P t u D₂.W) :
    LaxFaithfulAt IA IC (D₁.comp D₂ π).P p u (D₁.comp D₂ π).W := by
  intro x bA bC bA₂ hIAx hICx hΛc
  obtain ⟨bB, bA₁, hIBx, hΛ₁⟩ := hmid x
  -- Unpack the composite carry-back: bC ↦ bB' ↦ bA₂.
  simp only [DPair.comp, Pair.comp] at hΛc
  cases hbc : D₂.P.carry bC with
  | none => rw [hbc] at hΛc; simp at hΛc
  | some bB' =>
    rw [hbc, Option.bind_some] at hΛc
    -- (1) D₁'s closed square at x, restricted from π₁ to π.
    have e1 : projB π bA = projB π bA₁ := hπ.congrB (h₁ x hIAx hIBx hΛ₁)
    -- (2) D₂'s closed square at the embedded valuation W₁ x.
    have e2 : projB D₂.P.π bB = projB D₂.P.π bB' :=
      h₂ (D₁.W x) hIBx hICx hbc
    -- (3) Support transports (2) through carry₁.
    have e3 : projB π bA₁ = projB π bA₂ := hsup hΛ₁ hΛc e2
    exact e1.trans e3

/-- A language bundled with its interpreter and an open program: the
closing-valuation type and the family of closed instances. The nodes
of a directional route. -/
structure OLang extends ILang where
  Val  : Type
  prog : Val → L.Prog

/-- A directional route: a nonempty chain of directional pairs whose
witness embeddings connect the nodes' valuation types. -/
inductive DRoute : OLang → OLang → Type 1 where
  | one  {A B : OLang} {γ : Type} (D : DPair A.L B.L γ A.Val B.Val) :
      DRoute A B
  | cons {A B Z : OLang} {γ : Type} (D : DPair A.L B.L γ A.Val B.Val)
      (R : DRoute B Z) : DRoute A Z

namespace DRoute

/-- The composed directional pair of a route: fold `DPair.comp`,
choosing the head's own projection at each junction (as in
`Route.toPair`; without loss of generality by `faithful_reproject`).
Its embedding is the hop-wise composition of the `W_i`, its direction
the meet of the hops'. -/
def toDPair : {A Z : OLang} → DRoute A Z →
    (γ : Type) × DPair A.L Z.L γ A.Val Z.Val
  | _, _, .one D => ⟨_, D⟩
  | _, _, .cons D R => ⟨_, D.comp (toDPair R).2 D.P.π⟩

/-- The support conditions along the telescope (as in
`Route.Coherent`). -/
def Coherent : {A Z : OLang} → DRoute A Z → Prop
  | _, _, .one _ => True
  | _, _, .cons D R =>
      Supported D.P.carry (toDPair R).2.P.π D.P.π ∧ Coherent R

/-- The run record: every hop's lax square passes on its families, and
the middle column is defined along the embedded valuations — the
hypotheses of the binary `lax_pasting`, chained. -/
def Ok : {A Z : OLang} → DRoute A Z → Prop
  | A, Z, .one D => LaxFaithfulAt A.I Z.I D.P A.prog Z.prog D.W
  | A, _, .cons (B := B) D R =>
      LaxFaithfulAt A.I B.I D.P A.prog B.prog D.W ∧
      (∀ x, ∃ bB bA₁, B.I (B.prog (D.W x)) = some bB ∧
        D.P.carry bB = some bA₁) ∧
      Ok R

/-- Every hop is declared exact. -/
def AllExact : {A Z : OLang} → DRoute A Z → Prop
  | _, _, .one D => D.d = .exact
  | _, _, .cons D R => D.d = .exact ∧ AllExact R

/-- **Proposition 3.11(i), telescoped (lax pasting).** A coherent
directional route whose every hop's lax square passes is lax-faithful
end to end, along the composed embedding. -/
theorem lax_route_pasting :
    ∀ {A Z : OLang} (R : DRoute A Z), Coherent R → Ok R →
      LaxFaithfulAt A.I Z.I (toDPair R).2.P A.prog Z.prog
        (toDPair R).2.W := by
  intro A Z R
  induction R with
  | @one A₀ Z₀ γ₀ D =>
    intro _ hok
    simp only [toDPair]
    exact hok
  | @cons A₀ B₀ Z₀ γ₀ D R ih =>
    intro hcoh hok
    obtain ⟨hsupp, hcohR⟩ := hcoh
    obtain ⟨hD, hmid, hokR⟩ := hok
    simp only [toDPair]
    exact lax_pasting hmid (Factors.rfl D.P.π) hsupp hD (ih hcohR hokR)

/-- **Proposition 3.11(i), direction clause.** The composed direction
is exact iff every hop's is — the meet on `exact > over`, folded. -/
theorem direction_exact_iff :
    ∀ {A Z : OLang} (R : DRoute A Z),
      (toDPair R).2.d = .exact ↔ AllExact R := by
  intro A Z R
  induction R with
  | one D => simp only [toDPair, AllExact]
  | cons D R ih =>
    simp only [toDPair, AllExact, DPair.comp_d, Direction.comp_exact_iff]
    rw [ih]

end DRoute

/-- **Proposition 3.11(ii) (Universal transfer).** If no valuation of
the translated artifact — the abstraction's added behaviors included —
exhibits the target-side reading of `φ` (`hZ`), then no source
valuation's run exhibits `φ` on the kept observables. The proof is the
paper's contrapositive one-liner: a source valuation exhibiting `φ`
embeds along `W` to a target valuation exhibiting `φZ`. No direction
hypothesis appears: the theorem holds along any lax-faithful square,
and on an `over` route it is the only transfer — an existential
verdict stays subject to the carried-back replay of Theorem 4.8. -/
theorem lax_universal_transfer
    {A Z : Language} {γ κ : Type} {X Y : Type}
    {IA : Interp A} {IZ : Interp Z} {P : Pair A Z γ}
    {p : X → A.Prog} {t : Y → Z.Prog} {W : X → Y} {K : A.Obs → κ}
    (hK : Factors K P.π)
    {φ : Beh κ → Prop} {φZ : Beh Z.Obs → Prop}
    (hlax : LaxFaithfulAt IA IZ P p t W)
    (hrun : ∀ x, ∃ bZ r, IZ (t (W x)) = some bZ ∧ P.carry bZ = some r)
    (hcorr : ∀ bZ r, P.carry bZ = some r → φ (projB K r) → φZ bZ)
    (hZ : ∀ y bZ, IZ (t y) = some bZ → ¬ φZ bZ) :
    ∀ x b, IA (p x) = some b → ¬ φ (projB K b) := by
  intro x b hb hφ
  obtain ⟨bZ, r, hbZ, hr⟩ := hrun x
  -- The lax square at x, restricted from π to K.
  have hsq : projB K b = projB K r := hK.congrB (hlax x hb hbZ hr)
  exact hZ (W x) bZ hbZ (hcorr bZ r hr (hsq ▸ hφ))

end Calculus
