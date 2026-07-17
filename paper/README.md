# The paper (arXiv) and the frontier paper

This directory holds two papers and their shared evidence:

- `arxiv.tex` + `sections/` + `appendix/body-arxiv.tex` — *Untrusted
  Authors, Trusted Answers: A Calculus of Fidelity-Graded Translations*,
  the **arXiv preprint** (de-anonymized single author, funding
  acknowledgments, appendix inlined after the bibliography). `make`
  builds `arxiv.pdf`; `make arxiv-dist` builds the upload bundle.
  **v1** is tag `arxiv.1`; **v2** — the directional-square restructure
  on the two-plane principle, finalized 2026-07-17 — is tag `arxiv.2`.
- `frontier/` — *The hurdy-gurdy Platform: Mapping the Frontier of
  Reducible Decidability in Practice*, a **new submission** in progress
  that cites the arXiv paper (v2) as the instrument (see
  `frontier/README.md` and `FRONTIER-PLAN.md` §4). Shares only
  `references.bib` with the arXiv paper.
- `results/` — machine-generated evidence: the capability matrix, the
  branch-agreement and case-study runs, the bugs-caught table mined from
  history, timings. Regenerate with `make results` (see `results/README.md`).
- `mechanization/` — the calculus core mechanized in Lean 4 (core
  library only, sorry-free, axiom audit printed at build): pasting +
  localization, weakest link, re-establishment, branch lemmas, ratchet,
  both end-to-end theorems, the n-ary route telescope, the
  specialization obligation, the directional (lax) calculus, the
  contract algebra, and the frontier/saturation model
  (`Calculus/Frontier.lean`). `lake build` (see `mechanization/README.md`).

Claims in the arXiv paper are **as-of-snapshot** measurements, not
aspirations: coverage numbers are the per-construct conjunction
(covered ∧ faithful) recorded in the registry at the snapshot commit;
the `proved` tier is reported exactly as far as its independent checker
actually runs.

## The retired POPL 2027 flow

The paper began as a POPL 2027 milestone snapshot, **submitted
2026-07-03** and **rejected for formatting violations** (2026-07-17).
The submission flow — `main.tex`, the frozen POPL section variants, the
standalone supplementary appendix, the internal reviews, the
crosswalk check, and the anonymized-artifact builder
(`scripts/make_anon_artifact.py`) — was removed from the tree on the
rejection; it is preserved intact at tags `popl27-submitted` (the
as-submitted version, with `popl27-submitted.2` and the
`popl27-snapshot.*` series around it). The `\ifarxiv` toggle in
`macros.tex` survives: shared sections still gate arXiv-only material
on it.

## v1 → v2 (the published versions)

**v1** (tag `arxiv.1`) is the POPL-era snapshot as a preprint. **v2**
(tag `arxiv.2`) is a partial fork of the sources, no longer a pure
`\ifarxiv` overlay: `arxiv.tex` inputs the `-arxiv` forks
(`abstract-arxiv.tex`, `intro-arxiv.tex`, `overview-arxiv.tex`,
`calculus-arxiv.tex`, `instantiation-arxiv.tex`,
`appendix/body-arxiv.tex`) while `evaluation.tex`, `related.tex`, and
`conclusion.tex` stay shared with `\ifarxiv`-gated sentences and table
rows.

In v2 the **directional square is the primary notion** and exactness is
its identity-embedding special case. Numbering contract: results
3.1–3.9 keep their v1 numbers. v1 Def. 3.10 (`def:lax`) is absorbed
into Def. 3.5 (faithfulness *is* the directional square; direction +
witness embedding declared in Def. 3.4); v1 Prop. 3.11(i) (direction
composes) moved into Thm. 3.7; v1 Prop. 3.11(ii) remains **Prop. 3.11**
(universal transfer, number preserved); new **Prop. 3.10** is the
exactness characterization (`laxFaithful_id_iff_faithful`, axiom-free —
`mechanization/Calculus/Lax.lean` covers the whole directional
calculus).

v2 is restructured on the **two-plane principle** — how the system
works when used vs. how it evolves, meeting only in the registry and
the books (*answers never write; growth never answers*). The front
matter is short-form: `abstract-arxiv.tex` (the whole story in two
paragraphs) and a halved `intro-arxiv.tex`, with the two-plane diagram
(`fig:planes`, p. 1) and the spine-run diagram (`fig:run`, overview)
carrying what the prose no longer narrates. The technical sections
mirror the front matter exactly — §3 **The machine** (the whole use
plane: calculus, contracts — composition as the componentwise meet,
mechanized as `Contract.comp_glb` — branches, TCB, asymmetry,
mechanization, with 3.1–3.11 stable and the former §4 appended as
3.12+), §4 **The platform**, §5 **The economy** (how it grows: gate,
ratchet, books — one ledger, demand origin-tagged,
recommended-then-registered with the human valve intact; the books'
taxonomy is the five obstacles) — 25 pages total. §4/§5 numbering
diverges from v1 (end-to-end theorems 3.17/3.18; coverage/ratchet
5.1/5.2); labels are unchanged. The evaluation opens with a
four-question reading guide and closes with §6.10 "Post-snapshot
exhibits" — artifact-checkable demonstrations, explicitly not benchmark
claims. This machine/platform/economy skeleton is the intended
blueprint for extending the benchmarks: measure the machine (§6's
correctness and evidence questions), the platform (coverage and scale),
and the economy (campaign corpora, cost calibration) each on their own
plane.

Suggested arXiv v2 comment: "v2: rewritten on the two-plane principle
(the machine, the platform, the economy); directional squares as the
primary notion (exactness = the identity-embedding case, mechanized
incl. the lax telescope); the answerability loop and its economy
(demand books, recommended-then-registered); post-snapshot exhibits."
