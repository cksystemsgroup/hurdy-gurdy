import Kernel.Key
import Kernel.Trust

/-!
# The kernel's proved properties (KERNEL.md §9)

Two developments, one per half of what the kernel computes:

* `Kernel.Key` — the result order `(level, bound, grade, gap)` of
  `kernel/results.py`: strict; the ratchet; once settled, always
  settled; at a fixed level and bound, grades only move up and the
  gap never grows.
* `Kernel.Trust` — the residual trust of `kernel/driver.py`: the
  lineage meet over the gap segment plus the judge that ran, and what
  follows — gap 0 rests on the judge alone, every arrival check
  removes everything upstream of it, a smaller gap never adds trust.

The axiom audit below is printed at every build: each theorem with the
axioms it rests on. The order lemmas are axiom-free; the fold lemmas
rest on `propext` and `Quot.sound` via `List.foldl_append`.
-/

/-! ## Axiom audit -/

#print axioms Kernel.Key.lt_trans
#print axioms Kernel.Key.lt_asymm
#print axioms Kernel.best_mono
#print axioms Kernel.settled_ratchet
#print axioms Kernel.grade_moves_key
#print axioms Kernel.gap_moves_key
#print axioms Kernel.same_value_ratchet
#print axioms Kernel.residual_gap_zero
#print axioms Kernel.residual_mono
#print axioms Kernel.residual_check_removes_upstream
#print axioms Kernel.residual_stop_free
