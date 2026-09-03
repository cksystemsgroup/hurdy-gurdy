import Calculus.Fidelity
import Calculus.Lax

/-!
# The contract algebra

A pair's composable declaration as one object — its assurance class
(`Fidelity.lean`) paired with its square direction (`Lax.lean`) —
ordered componentwise, with route composition the componentwise meet.
This is the order theory behind the paper's single composition
statement ("contracts compose by the meet"): the *semantic* content of
each component is the already-mechanized theorem —
`weakest_link_universal` for the class coordinate, `lax_pasting` /
`DRoute.lax_route_pasting` with `DRoute.direction_exact_iff` for the
direction coordinate — and this file proves the algebra those results
compose under: `Contract.comp` is the greatest lower bound, so a
route's contract is exactly the weakest hop's on every axis at once.
-/

namespace Calculus

namespace Direction

/-- The strength order on directions: an exact square asserts strictly
more than an over-approximating one. -/
def rank : Direction → Nat
  | .exact => 1
  | .over => 0

instance : LE Direction := ⟨fun a b => a.rank ≤ b.rank⟩

instance (a b : Direction) : Decidable (a ≤ b) :=
  inferInstanceAs (Decidable (a.rank ≤ b.rank))

theorem le_trans {a b c : Direction} (h₁ : a ≤ b) (h₂ : b ≤ c) : a ≤ c :=
  Nat.le_trans h₁ h₂

/-- Composition (Proposition 3.11(i)'s meet) *is* the order-theoretic
minimum on the chain `over < exact`. -/
theorem comp_eq_min (a b : Direction) :
    a.comp b = if a.rank ≤ b.rank then a else b := by
  cases a <;> cases b <;> decide

theorem comp_le_left (a b : Direction) : a.comp b ≤ a := by
  cases a <;> cases b <;> decide

theorem comp_le_right (a b : Direction) : a.comp b ≤ b := by
  cases a <;> cases b <;> decide

theorem le_comp {a b c : Direction} (ha : c ≤ a) (hb : c ≤ b) :
    c ≤ a.comp b := by
  revert ha hb
  cases a <;> cases b <;> cases c <;> decide

end Direction

/-- A pair's (or route's) composable declaration: the assurance class of
its guarantee and the direction of its square. The projection/keep-set
coordinate composes by `Factors`/intersection (Basic.lean, the pasting
hypotheses) and the measured-cost coordinate is empirical (the ledger),
so the mechanized product carries the two logical coordinates. -/
structure Contract where
  aclass : AClass
  dir : Direction
deriving DecidableEq

namespace Contract

instance : LE Contract :=
  ⟨fun c d => c.aclass ≤ d.aclass ∧ c.dir ≤ d.dir⟩

/-- Route composition of contracts: the componentwise meet — weakest
link on the class chain, direction meet on `over < exact`. -/
def comp (c d : Contract) : Contract :=
  ⟨min c.aclass d.aclass, c.dir.comp d.dir⟩

theorem comp_le_left (c d : Contract) : c.comp d ≤ c :=
  ⟨AClass.min_le_left _ _, Direction.comp_le_left _ _⟩

theorem comp_le_right (c d : Contract) : c.comp d ≤ d :=
  ⟨AClass.min_le_right _ _, Direction.comp_le_right _ _⟩

theorem le_comp {c d e : Contract} (hc : e ≤ c) (hd : e ≤ d) :
    e ≤ c.comp d :=
  ⟨AClass.le_min hc.1 hd.1, Direction.le_comp hc.2 hd.2⟩

/-- **The contract algebra.** `comp` is the greatest lower bound: a
route's contract is the weakest hop's on every axis at once, and
nothing stronger is entailed — the paper's single composition
statement, with the semantic content of each coordinate discharged by
`weakest_link_universal` (class) and `lax_pasting` /
`DRoute.lax_route_pasting` (direction). -/
theorem comp_glb (c d e : Contract) :
    e ≤ c.comp d ↔ e ≤ c ∧ e ≤ d := by
  constructor
  · intro h
    exact ⟨⟨AClass.le_trans h.1 (AClass.min_le_left _ _),
            Direction.le_trans h.2 (Direction.comp_le_left _ _)⟩,
           ⟨AClass.le_trans h.1 (AClass.min_le_right _ _),
            Direction.le_trans h.2 (Direction.comp_le_right _ _)⟩⟩
  · intro ⟨hc, hd⟩
    exact le_comp hc hd

end Contract

end Calculus
