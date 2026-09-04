# Mechanization — the kernel's proved half (KERNEL.md §9)

Two developments, one per half of what the kernel computes, with no
dependencies beyond the Lean core and an axiom audit printed at every
build:

- `Kernel/Key.lean` — the result order of `kernel/results.py`, for
  exactly the key of KERNEL.md §5: `(level, bound, grade, gap)`, the
  gap an `Option Nat` with `none` ("no check ever ran") below every
  finite gap and a smaller gap better; the fold step keeps the
  incumbent only while it is strictly better (latest wins among
  equals). It proves:
  1. the order is a strict partial order — `Key.lt_irrefl`,
     `Key.lt_trans`, `Key.lt_asymm` (axiom-free);
  2. best-per-question is monotone under log append — `best_mono`,
     the ratchet;
  3. once settled, always settled — `settled_ratchet`;
  4. at a fixed level and bound, grades only move up and the gap never
     grows — `le_same_value`, `same_value_ratchet`; with
     `grade_moves_key`, `gap_moves_key`, and `first_check_moves_key`
     saying that a grade-raising replay is a strict improvement
     exactly when it moves the grade or the gap.
- `Kernel/Trust.lean` — the residual trust of `kernel/driver.py`:
  `residual hops gap judge = (hops.take gap).flatten ++ judge`, the
  lineage meet over the gap segment plus the judge. It proves the meet
  is exactly that (`mem_residual`), and its consequences:
  `residual_gap_zero` (gap 0 rests on the judge alone — certified is
  route-independent), `residual_mono` (a smaller gap never adds
  trust), `residual_check_removes_upstream` (hops beyond the check
  point, the stop included, contribute nothing), `residual_stop_free`
  and `residual_le_whole` (the search's own descent is gone once
  anything checked).

`Kernel.lean` imports both and prints the axiom audit. Build with
`lake build`; the toolchain is pinned in `lean-toolchain`.

The standing obligations of §9 therefore stand as follows:

| §9 obligation | status |
|---|---|
| result order strict | proved, four-part key, axiom-free |
| best-per-question monotone (ratchet) | proved (`propext`, `Quot.sound` via `List.foldl_append`) |
| once settled, always settled | proved |
| at fixed level and bound, gap never grows, grades only move up | proved |
| the trust meet is well-defined over the gap segment | proved, with its four consequences |

What the model does not cover, said so the layout never overstates:
the proofs are about the order and the meet as functions of keys and
lineages, not about the Python that computes them — that
correspondence is the job of `kernel/tests/test_order.py`, which runs
the same properties against `results.key` on random records — and the
`bound` is a natural number under an order-embedding of the Python's
stand-ins (`-1`, `k`, `inf`, and the witness above `inf`), which
lexicographic order cannot distinguish from the original.

The Era-4 development this grew from (the three-part key) is in the
history of this directory at the 2026-09 consolidation.
