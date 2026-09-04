/-!
# Residual trust — the meet over the gap segment (KERNEL.md §4, §9)

`kernel/driver.py` computes, for a graded universal result, its
**residual trust**: the lineage meet over the gap segment plus the
judge that ran. Lineages are sets of names of generated procedures;
the meet in the trust lattice — weakest link — is the union of names
one must still trust, so *more* names is *less* trust. A route is a
list of hops (source first), each carrying its lineage; the stop is
the search; the gap `g` counts the hops between the question and the
last arrival check the evidence passed; the judge is the language
whose checker ran there.

    residual hops g judge = ⋃ { lineage(hop i) | i < g } ∪ lineage(judge)

This file states that definition on lists and proves what §9 asks of
it — that it is well-defined as *exactly* that meet, and its three
consequences:

* **gap 0 rests on the judge alone** (`residual_gap_zero`): certified
  is route-independence, as a theorem;
* **each arrival check removes everything upstream of it**
  (`residual_check_removes_upstream`): hops beyond the check point
  contribute nothing, whatever they are;
* **a smaller gap never adds trust** (`residual_mono`): carrying a
  certificate one hop closer to home can only shrink the residual;
* **the stop is never in the residual** (`residual_stop_free`): once
  anything checked, the search's own descent is gone — the solver may
  be garbage; the checker validated the object.

No dependencies beyond the Lean core.
-/

namespace Kernel

/-- A lineage: the names of the generated procedures an artifact
descends from. -/
abbrev Lineage := List String

/-- The residual trust of evidence checked `gap` hops from the
question, by `judge`: the lineages of the hops still between the
question and the check, plus the judge. (`driver._residual_trust`.) -/
def residual (hops : List Lineage) (gap : Nat) (judge : Lineage) : Lineage :=
  (hops.take gap).flatten ++ judge

/-- The whole chain — what a bare claim rests on when nothing checked
(`driver.run_route`: the residual is the route's full lineage, the
stop included). -/
def whole (hops : List Lineage) (stop : Lineage) : Lineage :=
  hops.flatten ++ stop

/-! ## Well-defined: exactly the meet over the gap segment -/

/-- Membership in a prefix is monotone in the prefix length. -/
theorem mem_take_mono {α : Type} :
    ∀ (l : List α) (g g' : Nat), g ≤ g' → ∀ a, a ∈ l.take g → a ∈ l.take g'
  | [], _, _, _, _, h => by simp at h
  | _ :: _, 0, _, _, _, h => by simp at h
  | _ :: _, _ + 1, 0, hle, _, _ => absurd hle (by omega)
  | x :: t, g + 1, g' + 1, hle, a, h => by
    simp only [List.take_succ_cons, List.mem_cons] at h ⊢
    rcases h with h | h
    · exact Or.inl h
    · exact Or.inr (mem_take_mono t g g' (Nat.le_of_succ_le_succ hle) a h)

/-- A member of a prefix is a member of the list. -/
theorem mem_of_mem_take {α : Type} :
    ∀ (l : List α) (n : Nat) (a : α), a ∈ l.take n → a ∈ l
  | [], _, _, h => by simp at h
  | _ :: _, 0, _, h => by simp at h
  | x :: t, n + 1, a, h => by
    simp only [List.take_succ_cons, List.mem_cons] at h ⊢
    rcases h with h | h
    · exact Or.inl h
    · exact Or.inr (mem_of_mem_take t n a h)

/-- A name is in the residual exactly when some hop of the gap segment
carries it or the judge does: the residual *is* the meet. -/
theorem mem_residual {hops : List Lineage} {gap : Nat} {judge : Lineage}
    {x : String} :
    x ∈ residual hops gap judge ↔
      (∃ h, h ∈ hops.take gap ∧ x ∈ h) ∨ x ∈ judge := by
  unfold residual
  simp [List.mem_append, List.mem_flatten]

/-! ## The three consequences -/

/-- **Gap 0 rests on the judge alone**: certified is route-independent
as a theorem, not a definition. -/
theorem residual_gap_zero (hops : List Lineage) (judge : Lineage) :
    residual hops 0 judge = judge := by
  simp [residual]

/-- **A smaller gap never adds trust**: the residual at a check closer
to home is contained in the residual at any check further away. -/
theorem residual_mono {hops : List Lineage} {judge : Lineage}
    {g g' : Nat} (h : g ≤ g') :
    ∀ x, x ∈ residual hops g judge → x ∈ residual hops g' judge := by
  intro x hx
  rw [mem_residual] at hx ⊢
  rcases hx with ⟨hop, hmem, hin⟩ | hj
  · exact Or.inl ⟨hop, mem_take_mono hops g g' h hop hmem, hin⟩
  · exact Or.inr hj

/-- **Each arrival check removes everything upstream of it**: whatever
hops lie beyond the check point — up to and including the stop — the
residual does not see them. -/
theorem residual_check_removes_upstream (hops upstream : List Lineage)
    (gap : Nat) (judge : Lineage) (h : gap ≤ hops.length) :
    residual (hops ++ upstream) gap judge = residual hops gap judge := by
  unfold residual
  rw [List.take_append_of_le_length h]

/-- **The stop is never in the residual**: a name in the residual is
the judge's or some hop's — never the search's own, unless the search
shares descent with a hop or the judge, which lineage declares. -/
theorem residual_stop_free {hops : List Lineage} {gap : Nat}
    {judge : Lineage} {x : String}
    (hx : x ∈ residual hops gap judge) :
    x ∈ judge ∨ ∃ h, h ∈ hops ∧ x ∈ h := by
  rw [mem_residual] at hx
  rcases hx with ⟨hop, hmem, hin⟩ | hj
  · exact Or.inr ⟨hop, mem_of_mem_take hops gap hop hmem, hin⟩
  · exact Or.inl hj

/-- Against the whole chain: once anything checked, the residual is
contained in the hops' descent plus the judge — the search's descent,
present in `whole`, has been removed by the check. -/
theorem residual_le_whole {hops : List Lineage} {gap : Nat}
    {judge stop : Lineage} {x : String}
    (hx : x ∈ residual hops gap judge) :
    x ∈ judge ∨ x ∈ whole hops stop := by
  rcases residual_stop_free hx with hj | ⟨hop, hmem, hin⟩
  · exact Or.inl hj
  · exact Or.inr (by
      unfold whole
      rw [List.mem_append, List.mem_flatten]
      exact Or.inl ⟨hop, hmem, hin⟩)

end Kernel
