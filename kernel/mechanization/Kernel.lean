/-!
# The kernel's proved properties (KERNEL.md §6)

The kernel's result order, mechanized. `kernel/results.py` orders
results per question by the key `(level, bound, grade)` — level 0 a
partial, 1 a universal claim below the asked bound, 2 terminal — and
takes the best-so-far over an append-only log. This file proves the
four properties the design leans on:

* the order is strict (irreflexive, transitive, asymmetric);
* best-per-question is **monotone under log append** — the ratchet;
* **once terminal, always terminal** — the frontier never re-opens;
* along the ratchet the key only rises, so bounds and grades only
  improve (`claimed < checked < certified` is the grade ladder's
  strictness, stated as `ladder_strict`).

The model is deliberately the Python's shape: a key is three naturals,
`pick` is the fold step of `results.best`, and `best` is its fold. No
dependencies beyond the Lean core. Axiom audit (printed by the build):
the order lemmas and `grade_moves_key` are axiom-free;
`best_mono` and `terminal_ratchet` rest on `propext` + `Quot.sound`
(via `List.foldl_append`), the same trusted base the Calculus
development documents.
-/

namespace Kernel

/-- The order key of a result for one fixed question
(`results.key`): level, then bound, then grade index. -/
structure Key where
  level : Nat
  bound : Nat
  grade : Nat
deriving DecidableEq, Repr

/-- Strict lexicographic order — `results.better`. -/
def Key.lt (a b : Key) : Prop :=
  a.level < b.level
    ∨ (a.level = b.level ∧ (a.bound < b.bound
    ∨ (a.bound = b.bound ∧ a.grade < b.grade)))

instance (a b : Key) : Decidable (a.lt b) := by
  unfold Key.lt; infer_instance

/-- Non-strict companion. -/
def Key.le (a b : Key) : Prop := a.lt b ∨ a = b

/-! ## The order is strict -/

theorem Key.lt_irrefl (a : Key) : ¬ a.lt a := by
  intro h
  cases h with
  | inl h => exact Nat.lt_irrefl _ h
  | inr h =>
    cases h.2 with
    | inl h => exact Nat.lt_irrefl _ h
    | inr h => exact Nat.lt_irrefl _ h.2

theorem Key.lt_trans {a b c : Key} (h₁ : a.lt b) (h₂ : b.lt c) :
    a.lt c := by
  cases h₁ with
  | inl l₁ =>
    cases h₂ with
    | inl l₂ => exact Or.inl (Nat.lt_trans l₁ l₂)
    | inr e₂ => exact Or.inl (Nat.lt_of_lt_of_le l₁ (Nat.le_of_eq e₂.1))
  | inr e₁ =>
    cases h₂ with
    | inl l₂ => exact Or.inl (Nat.lt_of_le_of_lt (Nat.le_of_eq e₁.1) l₂)
    | inr e₂ =>
      refine Or.inr ⟨e₁.1.trans e₂.1, ?_⟩
      cases e₁.2 with
      | inl b₁ =>
        cases e₂.2 with
        | inl b₂ => exact Or.inl (Nat.lt_trans b₁ b₂)
        | inr g₂ => exact Or.inl (Nat.lt_of_lt_of_le b₁ (Nat.le_of_eq g₂.1))
      | inr g₁ =>
        cases e₂.2 with
        | inl b₂ => exact Or.inl (Nat.lt_of_le_of_lt (Nat.le_of_eq g₁.1) b₂)
        | inr g₂ =>
          exact Or.inr ⟨g₁.1.trans g₂.1, Nat.lt_trans g₁.2 g₂.2⟩

theorem Key.lt_asymm {a b : Key} (h : a.lt b) : ¬ b.lt a :=
  fun h' => Key.lt_irrefl a (Key.lt_trans h h')

theorem Key.le_refl (a : Key) : a.le a := Or.inr rfl

theorem Key.le_trans {a b c : Key} (h₁ : a.le b) (h₂ : b.le c) :
    a.le c := by
  cases h₁ with
  | inl hlt₁ =>
    cases h₂ with
    | inl hlt₂ => exact Or.inl (Key.lt_trans hlt₁ hlt₂)
    | inr heq => exact heq ▸ Or.inl hlt₁
  | inr heq => exact heq ▸ h₂

/-- Along `le`, the level never falls — the heart of the terminal
ratchet: a lexicographically-larger key cannot sit at a lower level. -/
theorem Key.le_level {a b : Key} (h : a.le b) : a.level ≤ b.level := by
  cases h with
  | inl hlt =>
    cases hlt with
    | inl h => exact Nat.le_of_lt h
    | inr h => exact Nat.le_of_eq h.1
  | inr heq => exact heq ▸ Nat.le_refl _

/-! ## Best-so-far over an append-only log -/

/-- The fold step of `results.best`: keep the incumbent unless the
newcomer is strictly better — ties never churn, so the map is
deterministic. -/
def pick : Option Key → Key → Option Key
  | none, k => some k
  | some m, k => if m.lt k then some k else some m

/-- Best result over a log, in log order. -/
def best (l : List Key) : Option Key := l.foldl pick none

/-- `none` sits below everything; `some` compares by `le`. -/
def Below : Option Key → Option Key → Prop
  | none, _ => True
  | some _, none => False
  | some a, some b => a.le b

theorem Below.refl (o : Option Key) : Below o o := by
  cases o with
  | none => trivial
  | some a => exact Key.le_refl a

theorem Below.trans {o₁ o₂ o₃ : Option Key}
    (h₁ : Below o₁ o₂) (h₂ : Below o₂ o₃) : Below o₁ o₃ := by
  cases o₁ with
  | none => trivial
  | some a =>
    cases o₂ with
    | none => exact absurd h₁ (by intro h; exact h)
    | some b =>
      cases o₃ with
      | none => exact absurd h₂ (by intro h; exact h)
      | some c => exact Key.le_trans h₁ h₂

/-- One fold step never loses ground. -/
theorem pick_grows (acc : Option Key) (k : Key) :
    Below acc (pick acc k) := by
  cases acc with
  | none => trivial
  | some m =>
    by_cases h : m.lt k
    · simp [pick, h]; exact Or.inl h
    · simp [pick, h]; exact Key.le_refl m

theorem foldl_grows (l : List Key) :
    ∀ acc : Option Key, Below acc (l.foldl pick acc) := by
  induction l with
  | nil => intro acc; exact Below.refl acc
  | cons k t ih =>
    intro acc
    exact Below.trans (pick_grows acc k) (ih (pick acc k))

/-- **The ratchet** (KERNEL.md §3): appending to the log can only
improve the best result — the old F2, now a property of the data
structure. -/
theorem best_mono (l l' : List Key) : Below (best l) (best (l ++ l')) := by
  unfold best
  rw [List.foldl_append]
  exact foldl_grows l' (l.foldl pick none)

/-! ## The frontier never re-opens -/

/-- Terminal = level 2 (a replayed witness, or a universal claim
covering the asked bound). -/
def Terminal (k : Key) : Prop := 2 ≤ k.level

/-- **Once terminal, always terminal**: a question that left the
frontier never returns to it, whatever is appended. -/
theorem terminal_ratchet (l l' : List Key) (k : Key)
    (hb : best l = some k) (ht : Terminal k) :
    ∃ k', best (l ++ l') = some k' ∧ Terminal k' := by
  have h := best_mono l l'
  rw [hb] at h
  cases hbest : best (l ++ l') with
  | none => rw [hbest] at h; exact absurd h (by intro hh; exact hh)
  | some k' =>
    rw [hbest] at h
    exact ⟨k', rfl, Nat.le_trans ht (Key.le_level h)⟩

/-! ## The grade ladder -/

/-- The universal grades, strict naming (KERNEL.md §2): `certified` is
reserved for source re-discharge; a replayed witness shares its rung. -/
inductive Grade | claimed | checked | certified
deriving DecidableEq, Repr

def Grade.idx : Grade → Nat
  | .claimed => 1
  | .checked => 2
  | .certified => 3

/-- The ladder is strict, so at a fixed level and bound the order of
keys is exactly the order of grades — grades only improve along the
ratchet. -/
theorem ladder_strict :
    Grade.idx .claimed < Grade.idx .checked
      ∧ Grade.idx .checked < Grade.idx .certified := by
  exact ⟨Nat.lt_succ_self 1, Nat.lt_succ_self 2⟩

/-- At fixed level and bound, a grade improvement is exactly a key
improvement. -/
theorem grade_moves_key {level bound g g' : Nat} (h : g < g') :
    Key.lt ⟨level, bound, g⟩ ⟨level, bound, g'⟩ :=
  Or.inr ⟨rfl, Or.inr ⟨rfl, h⟩⟩

end Kernel

/-! ## Axiom audit (the build prints each theorem's trusted base) -/

#print axioms Kernel.best_mono
#print axioms Kernel.terminal_ratchet
#print axioms Kernel.Key.lt_trans
#print axioms Kernel.grade_moves_key
