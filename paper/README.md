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
- `appendix/` — the supplementary appendix (detailed proofs; the
  construct-inventory catalog), a **standalone document** per the POPL'27
  call (appendices live in the artifact, not the paper). Its theorem
  numbers are hardcoded to the paper snapshot (crosswalk at the top of
  `appendix.tex`, body shared in `body.tex`); the anonymized artifact
  ships it **built** (`appendix.pdf`), and the paper's proof sketches
  point at it.
- `arxiv.tex` — the **arXiv preprint version**: same sections via the
  `\ifarxiv` toggle in `macros.tex`, de-anonymized single author, funding
  acknowledgments, appendix inlined after the bibliography. Excluded from
  the anonymized artifact.
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

**Post-`arxiv.1` sources — arXiv-only material.** The checked-in `main.pdf`
is the snapshot built at tag `arxiv.1`; `arxiv.pdf` has since been rebuilt
to include §3's *Directional squares* subsection (`sec:lax`: Def. 3.10 lax
faithfulness, Prop. 3.11 direction composition + universal transfer) and
the matching lines in the conclusion and instantiation — **all gated behind
`\ifarxiv`**: the POPL version is deliberately untouched (`main.tex` builds
a text-identical PDF to the submitted snapshot — verified rebuild-and-diff
2026-07-13 — and the directional extension may or may not enter a final
version), so only `make arxiv.pdf` picks the new material up. It is
appended after the last previously numbered result, so the appendix's
frozen crosswalk and every existing theorem number are unchanged in both
documents; `prop:lax` is mechanized (`mechanization/Calculus/Lax.lean`,
same axiom footprint as the exact telescope).
