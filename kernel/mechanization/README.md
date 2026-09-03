# Mechanization — the kernel's proved properties (KERNEL.md §9)

`Kernel.lean` is the Era-4 development, returned at the 2026-09
consolidation as the seed of this generation's. For a three-part
order key `(level, bound, grade)` it proves, with no dependencies
beyond the Lean core and an axiom audit printed at build:

1. the order is a strict partial order (irreflexive, transitive,
   asymmetric);
2. best-per-question is monotone under log append — the ratchet;
3. once settled, always settled — the frontier never re-opens;
4. along the ratchet the key only rises, so bounds and grades only
   improve (`ladder_strict`).

Build with `lake build`; the toolchain is pinned in `lean-toolchain`.

What this generation's key adds, and the development does not yet
cover: `kernel/results.py` orders on **four** parts — `(level, bound,
grade rung, −gap)` — so that a smaller gap is a strict improvement at
the same rung and a grade-raising replay moves the ratchet. The
standing obligations of §9 therefore stand as follows:

| §9 obligation | status |
|---|---|
| result order strict | proved for the Era-4 key; the gap component is not yet in the model |
| best-per-question monotone (ratchet) | same |
| once settled, always settled | same |
| per question the gap never grows, grades only move up | **open** |
| the trust meet is well-defined over the gap segment | **open** |

The port — extend `Key` by the gap, re-prove 1–4, then state and
prove the meet — is named work. This file says exactly that, so the
layout never overstates.
