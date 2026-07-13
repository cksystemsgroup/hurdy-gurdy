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

**Post-`arxiv.1` sources — the arXiv fork (v2 restructure).** The
checked-in `main.pdf` is the snapshot built at tag `arxiv.1` and stays
frozen for POPL (`main.tex` builds a text-identical PDF — verified
rebuild-and-diff 2026-07-13, crosswalk green). Since 2026-07-13 the arXiv
paper is a **partial fork**, no longer a pure `\ifarxiv` overlay:
`arxiv.tex` inputs `sections/calculus-arxiv.tex` and
`appendix/body-arxiv.tex` (live `\Cref`s; the standalone appendix and
`sections/calculus.tex` / `appendix/body.tex` stay untouched for the POPL
flow), while the other shared sections still carry `\ifarxiv`-gated
sentences and table rows. In the fork the **directional square is the
primary notion** and exactness is its identity-embedding special case.
Numbering contract: results 3.1–3.9 keep their numbers (the appendix and
the published v1 refer to them). v1→v2 map: v1 Def. 3.10 (`def:lax`) is
absorbed into Def. 3.5 (faithfulness *is* the directional square;
direction + witness embedding declared in Def. 3.4); v1 Prop. 3.11(i)
(direction composes) moved into Thm. 3.7; v1 Prop. 3.11(ii) remains
**Prop. 3.11** (universal transfer, number preserved); new **Prop. 3.10**
is the exactness characterization (`laxFaithful_id_iff_faithful`,
axiom-free — `mechanization/Calculus/Lax.lean` covers the whole
directional calculus). Intended flow: evolve the arXiv fork freely; update
a future POPL revision by cherry-picking (diff `calculus-arxiv.tex`
against `calculus.tex`).
