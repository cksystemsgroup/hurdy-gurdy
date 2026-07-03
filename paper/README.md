# POPL 2027 milestone snapshot (July 2026)

This directory is a **milestone snapshot**: a paper-shaped account of what
hurdy-gurdy can do **right now** (July 2026), written against the POPL 2027
deadline (July 9, 2026). **Submitted to POPL 2027 on 2026-07-03** (tag
`popl27-submitted` is the as-submitted version); the revision pass after
that tag closed the internal review's open items with new experiments
(conjoined coverage, the compliance-derived benchmark, the certified
factorization exhibit, the escape-rate and LLM-player experiments, the
disjoint-decision branch, the mechanized specialization obligation) —
see `reviews/2026-07-03-popl-style-review.md`'s addendum.

- `main.tex` + `sections/` — the paper (acmart `sigplan`, double-blind
  `review,anonymous` mode). **Note:** the live repo is public and named in
  the text's provenance; an actual double-blind submission requires an
  anonymized artifact snapshot and scrubbing the lineage references.
- `results/` — machine-generated evidence: the capability matrix, the
  branch-agreement and case-study runs, the bugs-caught table mined from
  history, timings. Regenerate with `make results` (see `results/README.md`).
- `mechanization/` — the calculus core mechanized in Lean 4 (core
  library only, sorry-free, axiom audit printed at build): pasting +
  localization, weakest link, re-establishment, branch lemmas, ratchet,
  both end-to-end theorems, the n-ary route telescope, and the
  specialization obligation of Thm 4.9(iv). `lake build` (see
  `mechanization/README.md`).
- `Makefile` — `make` builds `main.pdf` via `latexmk`; `make results`
  re-runs the harness.

Snapshot claims are **as-of-now** measurements, not aspirations: coverage
numbers are the per-construct conjunction (covered ∧ faithful) recorded in
the registry at this commit; the `proved` tier is reported exactly as far
as its independent checker actually runs today.
