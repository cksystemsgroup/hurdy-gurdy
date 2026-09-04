/-!
# The result order (KERNEL.md §5, §9)

`kernel/results.py` orders results per question by the key
`(level, bound, grade, gap)` — level 0 a partial, 1 a universal claim
below the asked bound, 2 settled; then the bound; then the grade rung
(ungraded < claimed < checked < certified); then the gap, where a
*smaller* gap is better and "no check ever ran" sits below every
finite gap — and takes the best-so-far over an append-only log, the
latest record winning among equal keys.

This file proves, for exactly that key, the properties of §9 that are
about the order:

* the order is strict (irreflexive, transitive, asymmetric);
* best-per-question is **monotone under log append** — the ratchet;
* **once settled, always settled** — the frontier never re-opens;
* at a fixed level and bound, **grades only move up the ladder and
  the gap never grows** — in particular a grade-raising replay
  (`regrade`), which keeps the value and moves only grade and gap, is
  a strict improvement exactly when it moves either.

The model is deliberately the Python's shape: `bound` is a natural
number under an order-embedding of the Python's stand-ins (`-1` for
"no bound reached" maps to `0`, a bound `k` to `k+1`, and `inf` above
all of them — lexicographic order does not see the embedding), `gap`
is `Option Nat` with `none` = "no check ever ran", `pick` is the fold
step of `results.best`, and `best` is its fold. No dependencies beyond
the Lean core.
-/

namespace Kernel

/-! ## The gap component: smaller is better, `none` below everything -/

/-- `GapLt a b`: `b` is a strictly better gap than `a`. -/
def GapLt : Option Nat → Option Nat → Prop
  | none, none => False
  | none, some _ => True
  | some _, none => False
  | some g, some g' => g' < g

instance (a b : Option Nat) : Decidable (GapLt a b) := by
  cases a <;> cases b <;> simp [GapLt] <;> infer_instance

theorem GapLt.irrefl (a : Option Nat) : ¬ GapLt a a := by
  cases a with
  | none => exact fun h => h
  | some g => exact Nat.lt_irrefl g

theorem GapLt.trans {a b c : Option Nat} (h₁ : GapLt a b) (h₂ : GapLt b c) :
    GapLt a c := by
  cases a <;> cases b <;> cases c
  · exact (h₁ : False).elim
  · exact (h₁ : False).elim
  · exact (h₂ : False).elim
  · trivial
  · exact (h₁ : False).elim
  · exact (h₁ : False).elim
  · exact (h₂ : False).elim
  · exact Nat.lt_trans h₂ h₁

/-! ## The key -/

/-- The order key of a result for one fixed question (`results.key`). -/
structure Key where
  level : Nat
  bound : Nat
  grade : Nat
  gap   : Option Nat
deriving DecidableEq, Repr

/-- Strict lexicographic order — `results.better`. -/
def Key.lt (a b : Key) : Prop :=
  a.level < b.level
    ∨ (a.level = b.level ∧ (a.bound < b.bound
    ∨ (a.bound = b.bound ∧ (a.grade < b.grade
    ∨ (a.grade = b.grade ∧ GapLt a.gap b.gap)))))

instance (a b : Key) : Decidable (a.lt b) := by
  unfold Key.lt; infer_instance

/-- Non-strict companion. -/
def Key.le (a b : Key) : Prop := a.lt b ∨ a = b

/-! ## The order is strict -/

theorem Key.lt_irrefl (a : Key) : ¬ a.lt a := by
  intro h
  rcases h with h | ⟨_, h | ⟨_, h | ⟨_, h⟩⟩⟩
  · exact Nat.lt_irrefl _ h
  · exact Nat.lt_irrefl _ h
  · exact Nat.lt_irrefl _ h
  · exact GapLt.irrefl _ h

theorem Key.lt_trans {a b c : Key} (h₁ : a.lt b) (h₂ : b.lt c) :
    a.lt c := by
  rcases h₁ with l₁ | ⟨el₁, b₁ | ⟨eb₁, g₁ | ⟨eg₁, p₁⟩⟩⟩ <;>
  rcases h₂ with l₂ | ⟨el₂, b₂ | ⟨eb₂, g₂ | ⟨eg₂, p₂⟩⟩⟩
  -- level strictly rises somewhere: the level decides
  · exact Or.inl (Nat.lt_trans l₁ l₂)
  · exact Or.inl (el₂ ▸ l₁)
  · exact Or.inl (el₂ ▸ l₁)
  · exact Or.inl (el₂ ▸ l₁)
  · exact Or.inl (el₁ ▸ l₂)
  -- levels equal throughout: the bound decides
  · exact Or.inr ⟨el₁.trans el₂, Or.inl (Nat.lt_trans b₁ b₂)⟩
  · exact Or.inr ⟨el₁.trans el₂, Or.inl (eb₂ ▸ b₁)⟩
  · exact Or.inr ⟨el₁.trans el₂, Or.inl (eb₂ ▸ b₁)⟩
  · exact Or.inl (el₁ ▸ l₂)
  · exact Or.inr ⟨el₁.trans el₂, Or.inl (eb₁ ▸ b₂)⟩
  -- bounds equal throughout: the grade decides
  · exact Or.inr ⟨el₁.trans el₂, Or.inr ⟨eb₁.trans eb₂,
      Or.inl (Nat.lt_trans g₁ g₂)⟩⟩
  · exact Or.inr ⟨el₁.trans el₂, Or.inr ⟨eb₁.trans eb₂,
      Or.inl (eg₂ ▸ g₁)⟩⟩
  · exact Or.inl (el₁ ▸ l₂)
  · exact Or.inr ⟨el₁.trans el₂, Or.inl (eb₁ ▸ b₂)⟩
  · exact Or.inr ⟨el₁.trans el₂, Or.inr ⟨eb₁.trans eb₂,
      Or.inl (eg₁ ▸ g₂)⟩⟩
  -- grades equal throughout: the gap decides
  · exact Or.inr ⟨el₁.trans el₂, Or.inr ⟨eb₁.trans eb₂,
      Or.inr ⟨eg₁.trans eg₂, GapLt.trans p₁ p₂⟩⟩⟩

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

/-- Along `le`, the level never falls — the heart of the settled
ratchet: a lexicographically-larger key cannot sit at a lower level. -/
theorem Key.le_level {a b : Key} (h : a.le b) : a.level ≤ b.level := by
  cases h with
  | inl hlt =>
    rcases hlt with h | ⟨h, _⟩
    · exact Nat.le_of_lt h
    · exact Nat.le_of_eq h
  | inr heq => exact heq ▸ Nat.le_refl _

/-! ## Best-so-far over an append-only log -/

/-- The fold step of `results.best`: the incumbent survives only
while it is strictly better; among equal keys the newcomer — the
latest adjudication — wins (KERNEL.md §5). -/
def pick : Option Key → Key → Option Key
  | none, k => some k
  | some m, k => if k.lt m then some m else some k

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

/-- Keys are totally comparable: either one is strictly better, or
they are equal. This is what lets the newcomer replace the incumbent
on ties without ever losing ground. -/
theorem Key.lt_or_eq_or_gt (a b : Key) : a.lt b ∨ a = b ∨ b.lt a := by
  rcases Nat.lt_trichotomy a.level b.level with hl | hl | hl
  · exact Or.inl (Or.inl hl)
  · rcases Nat.lt_trichotomy a.bound b.bound with hb | hb | hb
    · exact Or.inl (Or.inr ⟨hl, Or.inl hb⟩)
    · rcases Nat.lt_trichotomy a.grade b.grade with hg | hg | hg
      · exact Or.inl (Or.inr ⟨hl, Or.inr ⟨hb, Or.inl hg⟩⟩)
      · -- the gap decides, or everything is equal
        rcases ha : a.gap with _ | ga <;> rcases hb' : b.gap with _ | gb
        · refine Or.inr (Or.inl ?_)
          cases a; cases b; simp at hl hb hg ha hb'; simp [hl, hb, hg, ha, hb']
        · exact Or.inl (Or.inr ⟨hl, Or.inr ⟨hb, Or.inr ⟨hg, by simp [ha, hb', GapLt]⟩⟩⟩)
        · exact Or.inr (Or.inr (Or.inr ⟨hl.symm, Or.inr ⟨hb.symm, Or.inr ⟨hg.symm, by simp [ha, hb', GapLt]⟩⟩⟩))
        · rcases Nat.lt_trichotomy gb ga with hgap | hgap | hgap
          · exact Or.inl (Or.inr ⟨hl, Or.inr ⟨hb, Or.inr ⟨hg, by simp [ha, hb', GapLt, hgap]⟩⟩⟩)
          · refine Or.inr (Or.inl ?_)
            cases a; cases b; simp at hl hb hg ha hb'; simp [hl, hb, hg, ha, hb', hgap]
          · exact Or.inr (Or.inr (Or.inr ⟨hl.symm, Or.inr ⟨hb.symm, Or.inr ⟨hg.symm, by simp [ha, hb', GapLt, hgap]⟩⟩⟩))
      · exact Or.inr (Or.inr (Or.inr ⟨hl.symm, Or.inr ⟨hb.symm, Or.inl hg⟩⟩))
    · exact Or.inr (Or.inr (Or.inr ⟨hl.symm, Or.inl hb⟩))
  · exact Or.inr (Or.inr (Or.inl hl))

/-- One fold step never loses ground: the incumbent is kept when it is
strictly better, and otherwise replaced by a key that is at least as
good. -/
theorem pick_grows (acc : Option Key) (k : Key) :
    Below acc (pick acc k) := by
  cases acc with
  | none => trivial
  | some m =>
    by_cases h : k.lt m
    · simp [pick, h]; exact Key.le_refl m
    · simp [pick, h]
      rcases Key.lt_or_eq_or_gt m k with hlt | heq | hgt
      · exact Or.inl hlt
      · exact Or.inr heq
      · exact absurd hgt h

theorem foldl_grows (l : List Key) :
    ∀ acc : Option Key, Below acc (l.foldl pick acc) := by
  induction l with
  | nil => intro acc; exact Below.refl acc
  | cons k t ih =>
    intro acc
    exact Below.trans (pick_grows acc k) (ih (pick acc k))

/-- **The ratchet** (KERNEL.md §5): appending to the log can only
improve the best result — a property of the data structure. -/
theorem best_mono (l l' : List Key) : Below (best l) (best (l ++ l')) := by
  unfold best
  rw [List.foldl_append]
  exact foldl_grows l' (l.foldl pick none)

/-! ## The frontier never re-opens -/

/-- Settled = level 2 (a replayed witness, or a universal claim
covering the asked bound). -/
def Settled (k : Key) : Prop := 2 ≤ k.level

/-- **Once settled, always settled**: a question that left the
frontier never returns to it, whatever is appended. -/
theorem settled_ratchet (l l' : List Key) (k : Key)
    (hb : best l = some k) (hs : Settled k) :
    ∃ k', best (l ++ l') = some k' ∧ Settled k' := by
  have h := best_mono l l'
  rw [hb] at h
  cases hbest : best (l ++ l') with
  | none => rw [hbest] at h; exact absurd h (by intro hh; exact hh)
  | some k' =>
    rw [hbest] at h
    exact ⟨k', rfl, Nat.le_trans hs (Key.le_level h)⟩

/-! ## The grade ladder and the gap, at a fixed level and bound -/

/-- The rungs (KERNEL.md §4), strict: an ungraded partial below
`claimed` below `checked` below `certified`. -/
inductive Grade | ungraded | claimed | checked | certified
deriving DecidableEq, Repr

def Grade.idx : Grade → Nat
  | .ungraded => 0
  | .claimed => 1
  | .checked => 2
  | .certified => 3

theorem ladder_strict :
    Grade.idx .ungraded < Grade.idx .claimed
      ∧ Grade.idx .claimed < Grade.idx .checked
      ∧ Grade.idx .checked < Grade.idx .certified := by
  exact ⟨Nat.lt_succ_self 0, Nat.lt_succ_self 1, Nat.lt_succ_self 2⟩

/-- At fixed level and bound, a grade improvement is a key
improvement, whatever the gaps. -/
theorem grade_moves_key {level bound g g' : Nat} {p p' : Option Nat}
    (h : g < g') :
    Key.lt ⟨level, bound, g, p⟩ ⟨level, bound, g', p'⟩ :=
  Or.inr ⟨rfl, Or.inr ⟨rfl, Or.inl h⟩⟩

/-- At fixed level, bound, and grade, a smaller gap is a key
improvement — a grade-raising replay that carries a certificate one
hop closer to home strictly improves the best path. -/
theorem gap_moves_key {level bound g : Nat} {p p' : Option Nat}
    (h : GapLt p p') :
    Key.lt ⟨level, bound, g, p⟩ ⟨level, bound, g, p'⟩ :=
  Or.inr ⟨rfl, Or.inr ⟨rfl, Or.inr ⟨rfl, h⟩⟩⟩

/-- A first check on evidence that never had one is a key
improvement: `none` is below every finite gap. -/
theorem first_check_moves_key {level bound g : Nat} (n : Nat) :
    Key.lt ⟨level, bound, g, none⟩ ⟨level, bound, g, some n⟩ :=
  gap_moves_key (by simp [GapLt])

/-- **At a fixed level and bound, grades only move up and the gap
never grows** (KERNEL.md §9): if a key at least as good as `a` shares
`a`'s level and bound, then its grade is higher, or its grade is equal
and its gap is no worse. Since `regrade` keeps the value — hence level
and bound — this is exactly what it may do to a stored result. -/
theorem le_same_value {a b : Key} (h : a.le b)
    (hl : a.level = b.level) (hb : a.bound = b.bound) :
    a.grade < b.grade ∨ (a.grade = b.grade ∧ (a.gap = b.gap ∨ GapLt a.gap b.gap)) := by
  cases h with
  | inr heq => exact Or.inr ⟨by rw [heq], Or.inl (by rw [heq])⟩
  | inl hlt =>
    rcases hlt with h | ⟨_, h | ⟨_, h | ⟨hg, hp⟩⟩⟩
    · exact absurd hl (Nat.ne_of_lt h)
    · exact absurd hb (Nat.ne_of_lt h)
    · exact Or.inl h
    · exact Or.inr ⟨hg, Or.inr hp⟩

/-- The same, read off the log: whatever is appended after a settled
best at some bound, the best at that same level and bound can only
have moved up the ladder or closer to home. -/
theorem same_value_ratchet (l l' : List Key) (a b : Key)
    (ha : best l = some a) (hb : best (l ++ l') = some b)
    (hl : a.level = b.level) (hbd : a.bound = b.bound) :
    a.grade < b.grade ∨ (a.grade = b.grade ∧ (a.gap = b.gap ∨ GapLt a.gap b.gap)) := by
  have h := best_mono l l'
  rw [ha, hb] at h
  exact le_same_value h hl hbd

end Kernel
