import Calculus.Contract

/-!
# The frontier model (FRONTIER-PLAN.md §1, Phase 1)

The frontier theorems live one level above the calculus: they quantify
over registries, questions, and growth, not over behaviors. So this
file does **not** re-derive the instrument — it consumes it as an
interface — and the whole model is one structure, designed from
scratch for the theorems it must carry:

* A **registry** is a predicate over *items* — anything admission
  ratchets over: a pair (an edge) or a language-attached capability
  (a solver, a checker, an anchor).
* A **candidate** (for one fixed question) is the finite list of
  admitted items an answer would rest on — its hops plus the
  destination capabilities it invokes. Pairs for edges, capabilities
  for nodes, one list: the plan's route-level currency (§1.6).
* Answerability is a **filtration**: `Stage ok G k` is the set of
  admitted candidates surviving the first `k` conditions. The
  platform instantiates `N = 5` conditions in diagnosis order —
  connectivity, loss, shape, cost, trust. The filtration shrinks as
  `k` grows and grows as `G` grows, and those two monotonicities are
  the entire model: F2, F3, and the chain lemma that seeds F4 are
  their consequences.

Plan ↔ Lean:
* F2 (monotone exploration)      — `answerable_mono`
* F3 (complete local gradient)   — `diagnosis_total` (a first failing
  condition exists), `diagnosis_unique` (it is well-defined),
  `diagnosis_progress` (it never regresses under growth),
  `diagnosis_strict_progress` (an adequate extension advances it)
* F4 seed (relative completeness) — `adequate_chain_answerable`:
  `N` adequate extensions answer the question; fairness and gate
  liveness exist exactly to supply them
* Currency (§1.6)                — `lifecycle_ratchet` (status only
  advances, evidence travels), `conditional_plan_sound` (a mixed
  route's conditional contract is a lower bound on its realized
  contract once every frontier hop is discharged)

What the diagnosis *names* (that the target, if admitted, discharges
the failing condition) is the specification of `why_not` — an
instantiation obligation the implementation meets by construction —
and enters here only as the `Reaches ok G' (k+1)` hypothesis of the
strict-progress and chain lemmas.
-/

namespace Calculus

namespace Frontier

/-! ## Registries, candidates, and the answerability filtration -/

/-- A registry state: which items (pairs, capabilities) are admitted. -/
abbrev Registry (Item : Type) := Item → Prop

/-- Registry extension: growth is additive — everything admitted stays
admitted (the ratchet's shape at this level). -/
def Registry.Sub {Item : Type} (G G' : Registry Item) : Prop :=
  ∀ i, G i → G' i

/-- A candidate rests only on admitted items. (The empty candidate is
vacuously available; the first condition of any instantiation rejects
it — junk candidates are what conditions are for.) -/
def available {Item : Type} (G : Registry Item) (r : List Item) : Prop :=
  ∀ i, i ∈ r → G i

variable {Item : Type}

/-- The filtration: candidates available in `G` surviving the first
`k` conditions `ok 0, …, ok (k-1)`. -/
def Stage (ok : Nat → List Item → Prop) (G : Registry Item)
    (k : Nat) (r : List Item) : Prop :=
  available G r ∧ ∀ j, j < k → ok j r

/-- Some admitted candidate survives the first `k` conditions. -/
def Reaches (ok : Nat → List Item → Prop) (G : Registry Item)
    (k : Nat) : Prop :=
  ∃ r, Stage ok G k r

/-- Answerable under `N` conditions: some candidate survives them all. -/
def Answerable (ok : Nat → List Item → Prop) (N : Nat)
    (G : Registry Item) : Prop :=
  Reaches ok G N

theorem stage_mono {ok : Nat → List Item → Prop} {G G' : Registry Item}
    (h : Registry.Sub G G') {k : Nat} {r : List Item} :
    Stage ok G k r → Stage ok G' k r :=
  fun ⟨ha, hc⟩ => ⟨fun i hi => h i (ha i hi), hc⟩

theorem stage_antitone {ok : Nat → List Item → Prop} {G : Registry Item}
    {j k : Nat} (hjk : j ≤ k) {r : List Item} :
    Stage ok G k r → Stage ok G j r :=
  fun ⟨ha, hc⟩ => ⟨ha, fun i hi => hc i (Nat.lt_of_lt_of_le hi hjk)⟩

theorem reaches_mono {ok : Nat → List Item → Prop} {G G' : Registry Item}
    (h : Registry.Sub G G') {k : Nat} :
    Reaches ok G k → Reaches ok G' k :=
  fun ⟨r, hr⟩ => ⟨r, stage_mono h hr⟩

theorem reaches_antitone {ok : Nat → List Item → Prop} {G : Registry Item}
    {j k : Nat} (hjk : j ≤ k) : Reaches ok G k → Reaches ok G j :=
  fun ⟨r, hr⟩ => ⟨r, stage_antitone hjk hr⟩

/-- Level `0` is always reached (by the empty candidate — see
`available`). This is what makes the diagnosis total rather than
partial: the filtration starts inhabited and fails, if it fails, at a
condition. -/
theorem reaches_zero {ok : Nat → List Item → Prop} {G : Registry Item} :
    Reaches ok G 0 := by
  refine ⟨[], fun i hi => ?_, fun j hj => ?_⟩
  · cases hi
  · exact absurd hj (Nat.not_lt_zero j)

/-- **F2 (monotone exploration).** Growth never loses an answer: the
answerable set is monotone in the registry. (That standing *verdicts*
stand is the pair-level ratchet, `ratchet_preserves_faithful`.) -/
theorem answerable_mono {ok : Nat → List Item → Prop} {N : Nat}
    {G G' : Registry Item} (h : Registry.Sub G G') :
    Answerable ok N G → Answerable ok N G' :=
  reaches_mono h

/-! ## The diagnosis: first failure exists, is unique, and only advances -/

/-- The diagnosis verdict: the first `k` conditions are survivable and
the next is not — condition `k` (0-indexed) is the question's first
failing obstacle. -/
def FirstFail (ok : Nat → List Item → Prop) (G : Registry Item)
    (k : Nat) : Prop :=
  Reaches ok G k ∧ ¬ Reaches ok G (k + 1)

/-- Boundary crossing: a predicate true at `0` and false at `N` fails
first somewhere below `N`. (The one classical step of the model:
an unanswerable question does not *name* its failing condition
constructively; the platform's `why_not` computes it because the five
conditions are decidable there.) -/
private theorem crossing {P : Nat → Prop} :
    ∀ N, P 0 → ¬ P N → ∃ k, k < N ∧ P k ∧ ¬ P (k + 1)
  | 0, h0, hN => absurd h0 hN
  | N + 1, h0, hN =>
    Classical.byCases
      (fun hPN : P N => ⟨N, Nat.lt_succ_self N, hPN, hN⟩)
      (fun hPN : ¬ P N =>
        match crossing N h0 hPN with
        | ⟨k, hk, hcross⟩ => ⟨k, Nat.lt_succ_of_lt hk, hcross⟩)

/-- **F3, totality.** An unanswerable question has a first failing
condition, below `N`. The diagnosis is a total function on the open
set, not a heuristic. -/
theorem diagnosis_total {ok : Nat → List Item → Prop} {N : Nat}
    {G : Registry Item} (h : ¬ Answerable ok N G) :
    ∃ k, k < N ∧ FirstFail ok G k :=
  crossing N reaches_zero h

/-- **F3, well-definedness.** The filtration is nested, so the first
failing condition is unique — "the" obstacle is honest vocabulary. -/
theorem diagnosis_unique {ok : Nat → List Item → Prop}
    {G : Registry Item} {k k' : Nat}
    (h : FirstFail ok G k) (h' : FirstFail ok G k') : k = k' := by
  have h₁ : ¬ k < k' := fun hlt => h.2 (reaches_antitone hlt h'.1)
  have h₂ : ¬ k' < k := fun hlt => h'.2 (reaches_antitone hlt h.1)
  omega

/-- **F3, progress.** Under growth the first failing condition never
regresses: the diagnosis index is monotone along the loop. -/
theorem diagnosis_progress {ok : Nat → List Item → Prop}
    {G G' : Registry Item} (hsub : Registry.Sub G G') {k k' : Nat}
    (h : FirstFail ok G k) (h' : FirstFail ok G' k') : k ≤ k' := by
  have h₁ : ¬ k' < k :=
    fun hlt => h'.2 (reaches_antitone hlt (reaches_mono hsub h.1))
  omega

/-- **F3, strict progress.** An *adequate* extension — one that
discharges the failing condition, so some admitted candidate survives
one level further — strictly advances the diagnosis (or answers the
question, in which case no `FirstFail` exists at all). -/
theorem diagnosis_strict_progress {ok : Nat → List Item → Prop}
    {G' : Registry Item} {k k' : Nat}
    (hadeq : Reaches ok G' (k + 1)) (h' : FirstFail ok G' k') : k < k' := by
  have h₁ : ¬ k' < k + 1 := fun hlt => h'.2 (reaches_antitone hlt hadeq)
  omega

/-- **The chain lemma (the seed of F4).** Along a growing chain of
registries in which every diagnosis is answered by an adequate
extension, `N` steps answer the question: the diagnosis index is
bounded by `N` and strictly increases, so it runs out of room. This is
the entire mathematical content of relative completeness — fairness
and gate liveness (F4's named assumptions) exist exactly to supply
`hadeq` at every step. -/
theorem adequate_chain_answerable {ok : Nat → List Item → Prop} {N : Nat}
    (Gs : Nat → Registry Item)
    (hchain : ∀ n, Registry.Sub (Gs n) (Gs (n + 1)))
    (hadeq : ∀ n k, FirstFail ok (Gs n) k → Reaches ok (Gs (n + 1)) (k + 1)) :
    Answerable ok N (Gs N) := by
  have inv : ∀ n, Answerable ok N (Gs n) ∨
      ∃ k, n ≤ k ∧ FirstFail ok (Gs n) k := by
    intro n
    induction n with
    | zero =>
      by_cases h : Answerable ok N (Gs 0)
      · exact Or.inl h
      · obtain ⟨k, _, hff⟩ := diagnosis_total h
        exact Or.inr ⟨k, Nat.zero_le k, hff⟩
    | succ n ih =>
      cases ih with
      | inl h => exact Or.inl (answerable_mono (hchain n) h)
      | inr h =>
        obtain ⟨k, hnk, hff⟩ := h
        by_cases h' : Answerable ok N (Gs (n + 1))
        · exact Or.inl h'
        · obtain ⟨k', _, hff'⟩ := diagnosis_total h'
          have : k < k' := diagnosis_strict_progress (hadeq n k hff) hff'
          exact Or.inr ⟨k', by omega, hff'⟩
  cases inv N with
  | inl h => exact h
  | inr h =>
    obtain ⟨k, hNk, hff⟩ := h
    exact reaches_antitone hNk hff.1

/-! ## The currency: the tier ratchet and conditional plans (§1.6) -/

/-- The registry's tiers, in lifecycle order: `frontier` (design
unknown — a required contract plus its evidence payload, derived from
the books), `registered` (design known), `«partial»` and `built`
(achieved contract, measured). -/
inductive Tier
  | frontier | registered | «partial» | built
deriving DecidableEq, Repr

def Tier.rank : Tier → Nat
  | .frontier => 0
  | .registered => 1
  | .«partial» => 2
  | .built => 3

instance : LE Tier := ⟨fun a b => a.rank ≤ b.rank⟩

/-- A pair's bookkeeping state: its tier and its evidence payload. -/
structure PairState (Evidence : Type) where
  tier : Tier
  payload : Evidence → Prop

/-- One promotion: the tier strictly advances and the payload only
grows — evidence travels with the pair. -/
def Promotes {E : Type} (s s' : PairState E) : Prop :=
  s.tier.rank < s'.tier.rank ∧ ∀ e, s.payload e → s'.payload e

/-- Any number of promotions. -/
inductive Lifecycle {E : Type} : PairState E → PairState E → Prop
  | refl (s) : Lifecycle s s
  | step {s t u} : Promotes s t → Lifecycle t u → Lifecycle s u

/-- **The status ratchet (§1.6).** Along any lifecycle the tier only
advances and the evidence only accumulates: a `built` pair still
carries the demand that created it — its causal history, from demand
through design evidence to measured closure. -/
theorem lifecycle_ratchet {E : Type} {s s' : PairState E}
    (h : Lifecycle s s') :
    s.tier ≤ s'.tier ∧ ∀ e, s.payload e → s'.payload e := by
  induction h with
  | refl s => exact ⟨Nat.le_refl _, fun _ h => h⟩
  | step hp _ ih =>
    exact ⟨Nat.le_trans (Nat.le_of_lt hp.1) ih.1,
           fun e he => ih.2 e (hp.2 e he)⟩

end Frontier

namespace Contract

theorem le_refl (c : Contract) : c ≤ c :=
  ⟨AClass.le_refl _, Nat.le_refl _⟩

theorem le_trans {c d e : Contract} (h₁ : c ≤ d) (h₂ : d ≤ e) : c ≤ e :=
  ⟨AClass.le_trans h₁.1 h₂.1, Direction.le_trans h₁.2 h₂.2⟩

/-- The meet is monotone in both arguments — the order-theoretic fact
behind discharge. -/
theorem comp_mono {c c' d d' : Contract} (hc : c ≤ c') (hd : d ≤ d') :
    c.comp d ≤ c'.comp d' :=
  le_comp (le_trans (comp_le_left c d) hc)
          (le_trans (comp_le_right c d) hd)

end Contract

namespace Frontier

/-- Hop-for-hop domination of one plan by another. Discharging a
mixed route instantiates it: an achieved hop dominates itself
(`Contract.le_refl`), and a frontier hop's *required* contract is
dominated by the *achieved* contract of the pair that discharges it. -/
inductive Dominates : List Contract → List Contract → Prop
  | nil : Dominates [] []
  | cons {c c' : Contract} {l l' : List Contract} :
      c ≤ c' → Dominates l l' → Dominates (c :: l) (c' :: l')

/-- A plan's composed contract: the meet of its hops, folded from a
first hop. -/
def planContract (c : Contract) (l : List Contract) : Contract :=
  l.foldl Contract.comp c

/-- **Conditional-plan soundness under discharge (§1.6).** A mixed
route's conditional contract — frontier hops contributing their
required contracts — is a lower bound on the realized contract once
every frontier hop is discharged by a pair whose achieved contract
dominates its requirement. Conditional plans never overpromise. -/
theorem conditional_plan_sound {c c' : Contract} {l l' : List Contract}
    (hc : c ≤ c') (hl : Dominates l l') :
    planContract c l ≤ planContract c' l' := by
  induction hl generalizing c c' with
  | nil => exact hc
  | cons hd _ ih => exact ih (Contract.comp_mono hc hd)

end Frontier

end Calculus
