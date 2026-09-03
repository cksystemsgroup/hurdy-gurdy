import Calculus.Pasting

/-!
# The route telescope

n-ary routes as a dependently-typed chain of pairs, generalizing the
binary composition of `Pasting.lean`: `Route.route_pasting` is
Theorem 3.7 iterated along an arbitrary telescope, and
`Route.route_localization` is Corollary 3.8 in its inductive, "some
hop fails" form.

Design notes:

* Interpreters are language-owned (§3.2 of the paper), so the telescope
  runs over `ILang` — a language bundled with its interpreter — and the
  intermediate languages (with their interpreters) are existentially
  packed inside the chain's constructors.
* At each junction the composite projection is chosen canonically as
  the head pair's own `π` (so `Factors` holds by reflexivity); this is
  without loss of generality, because any weaker projection factors
  through it — `faithful_reproject` transports faithfulness along any
  further compression.
* The side conditions the paper attaches "pairwise along the route" —
  the support conditions — form the recursive predicate
  `Route.Coherent`; the per-hop oracle passes and middle-column
  definedness witnesses form `Route.OkAt`. `route_pasting` consumes
  exactly these, hop by hop, through the binary `pasting`.
-/

namespace Calculus

/-- A language bundled with its (language-owned) interpreter. -/
structure ILang : Type 1 where
  L : Language
  I : Interp L

/-- A route: a nonempty chain of pairs. Intermediate languages and
per-hop projection codomains are existentially packed. -/
inductive Route : ILang → ILang → Type 1 where
  | one  {A B : ILang} {γ : Type} (P : Pair A.L B.L γ) : Route A B
  | cons {A B Z : ILang} {γ : Type} (P : Pair A.L B.L γ) (R : Route B Z) :
      Route A Z

namespace Route

/-- The composed pair of a route: fold the binary composite, choosing
the head's own projection at each junction. -/
def toPair : {A Z : ILang} → Route A Z → (γ : Type) × Pair A.L Z.L γ
  | _, _, .one P => ⟨_, P⟩
  | _, _, .cons P R => ⟨_, P.comp (toPair R).2 P.π⟩

/-- The support conditions along the telescope (Definition 3.6 at every
junction, against the composed remainder's projection). -/
def Coherent : {A Z : ILang} → Route A Z → Prop
  | _, _, .one _ => True
  | _, _, .cons P R => Supported P.carry (toPair R).2.π P.π ∧ Coherent R

/-- The run record at `p`: every hop's square passes (the inline oracle
verdicts), with the middle-column definedness witnesses threaded to the
next hop. These are exactly the hypotheses of the binary `pasting`,
chained. -/
def OkAt : {A Z : ILang} → Route A Z → A.L.Prog → Prop
  | A, Z, .one P, p => FaithfulAt A.I Z.I P p
  | A, _, .cons (B := B) P R, p =>
      FaithfulAt A.I B.I P p ∧
      ∃ q bB bA₁, P.T p = some q ∧ B.I q = some bB ∧
        P.carry bB = some bA₁ ∧ OkAt R q

/-- Middle-column definedness alone (no faithfulness) — what
localization needs to run the pasting argument hypothetically. -/
def DefinedAt : {A Z : ILang} → Route A Z → A.L.Prog → Prop
  | _, _, .one _, _ => True
  | _, _, .cons (B := B) P R, p =>
      ∃ q bB bA₁, P.T p = some q ∧ B.I q = some bB ∧
        P.carry bB = some bA₁ ∧ DefinedAt R q

/-- Some hop's square fails at its input program — the inductive form
of "the failure localizes". -/
def SomeHopFailsAt : {A Z : ILang} → Route A Z → A.L.Prog → Prop
  | A, Z, .one P, p => ¬ FaithfulAt A.I Z.I P p
  | A, _, .cons (B := B) P R, p =>
      ¬ FaithfulAt A.I B.I P p ∨ ∃ q, P.T p = some q ∧ SomeHopFailsAt R q

/-- **Theorem 3.7, telescoped.** A coherent route whose every hop
passes at the run's programs is faithful end to end. -/
theorem route_pasting :
    ∀ {A Z : ILang} (R : Route A Z), Coherent R →
      ∀ {p : A.L.Prog}, OkAt R p →
        FaithfulAt A.I Z.I (toPair R).2 p := by
  intro A Z R
  induction R with
  | @one A₀ Z₀ γ₀ P =>
    intro _ p hok
    simp only [toPair]
    intro s bA bZ bA' hTc hIAc hIZc hΛc
    exact hok hTc hIAc hIZc hΛc
  | @cons A₀ B₀ Z₀ γ₀ P R ih =>
    intro hcoh p hok
    obtain ⟨hsupp, hcohR⟩ := hcoh
    obtain ⟨hP, q, bB, bA₁, hT, hIB, hΛ, hokR⟩ := hok
    simp only [toPair]
    intro s bA bZ bA' hTc hIAc hIZc hΛc
    exact pasting hT hIB hΛ (Factors.rfl P.π) hsupp hP (ih hcohR hokR)
      hTc hIAc hIZc hΛc

/-- **Corollary 3.8, telescoped.** If a coherent, defined route's
composite square fails at `p`, some hop's square fails at its input —
per-hop localization for arbitrary telescopes. (Classical, like the
binary corollary.) -/
theorem route_localization :
    ∀ {A Z : ILang} (R : Route A Z), Coherent R →
      ∀ {p : A.L.Prog}, DefinedAt R p →
        ¬ FaithfulAt A.I Z.I (toPair R).2 p → SomeHopFailsAt R p := by
  intro A Z R
  induction R with
  | @one A₀ Z₀ γ₀ P =>
    intro _ p _ hfail
    simp only [toPair] at hfail
    simp only [SomeHopFailsAt]
    exact hfail
  | @cons A₀ B₀ Z₀ γ₀ P R ih =>
    intro hcoh p hdef hfail
    obtain ⟨hsupp, hcohR⟩ := hcoh
    obtain ⟨q, bB, bA₁, hT, hIB, hΛ, hdefR⟩ := hdef
    simp only [SomeHopFailsAt]
    by_cases hP : FaithfulAt A₀.I B₀.I P p
    · by_cases hR : FaithfulAt B₀.I Z₀.I (toPair R).2 q
      · -- both halves faithful ⇒ the composite is faithful: contradiction.
        exfalso
        apply hfail
        simp only [toPair]
        intro s bA bZ bA' hTc hIAc hIZc hΛc
        exact pasting hT hIB hΛ (Factors.rfl P.π) hsupp hP hR
          hTc hIAc hIZc hΛc
      · exact Or.inr ⟨q, hT, ih hcohR hdefR hR⟩
    · exact Or.inl hP

end Route

/-- Re-project a pair to any further compression of its declared
projection. -/
def Pair.reproject {A B : Language} {γ γ' : Type}
    (P : Pair A B γ) (π' : A.Obs → γ') : Pair A B γ' :=
  { T := P.T, carry := P.carry, π := π' }

/-- Faithfulness transports along projection weakening: the canonical
head-projection choice in `Route.toPair` is without loss of
generality. -/
theorem faithful_reproject {A B : Language} {γ γ' : Type}
    {IA : Interp A} {IB : Interp B} {P : Pair A B γ}
    {π' : A.Obs → γ'} (hfac : Factors π' P.π)
    {p : A.Prog} (h : FaithfulAt IA IB P p) :
    FaithfulAt IA IB (P.reproject π') p := by
  intro q bA bB bA' hT hIA hIB hΛ
  exact hfac.congrB (h hT hIA hIB hΛ)

end Calculus
