# The gate paper

The **sixth generation's paper**: a new submission, not a version of
the instrument paper (arXiv, `../arxiv.tex`) or the frontier paper
(`../frontier/`). Its contribution is the design in which every
executable of a verification system is untrusted generated text
admitted through one gate, with grades computed as geometry from where
an interpreter run judged the evidence, and the measurement of that
design at one frozen commit. Shares only `../references.bib` with the
other two papers; the preamble is from scratch. `make` builds
`gate.pdf` (latexmk, pdflatex + bibtex; `make clean` removes the build
products and keeps the PDF).

**Title:** *Judged Whole — One Gate for Untrusted Verification
Infrastructure.*

**Era and tag.** The paper describes **Era 6** (`KERNEL.md` and
`HISTORY.md` at the root) exactly as it stands at tag
**`era6-campaign-2`** (commit `da73e30`, 2026-09-08): the design after
the 2026-09-04 vocabulary consolidation, the registry after the reverse
edge, the four boards after the first plays of the two pinned rungs and
the ten-minute IC3 pass. The tag is frozen. **The paper is not edited to
track later commits**; where a later change to the tree invalidates a
claim, the note goes here, dated, never into the paper silently (the
rule `HISTORY.md` states for every paper in this directory). Nothing
below the table is such a note yet.

**Venue and constraints.** Target PLDI 2027: `acmsmall`, single column,
`review` and `anonymous` options on; double-blind (no author names, no
funding, no institution, no repository URL; the project's own earlier
papers cited in the third person — the preprint's bib entry lives in
`gate-extra.bib` because the shared one in `../references.bib` carries
the repository URL in its note); at most 20 pages of text excluding
the bibliography; no appendix.

Sections: §1 introduction (the sentence, the design in brief, the
kernel, the measurements, contributions, what is not claimed); §2 one
question, two routes (`README.md`'s story in `KERNEL.md`'s words, the
square as the first figure); §3 the design (`KERNEL.md` §1–§8, §12, in
its order: kinds, the three judgments and the two unjudged crossings,
frames that do not align, evidence, grades as geometry, routes and the
order, the ledger, the generation rule, the gate, the loop); §4 the
kernel made solid four ways (`KERNEL.md` §9); §5 what was admitted (the
registry, in admission order, and the trusted base as `base` prints
it); §6 measurements (every number from `runs/`); §7 related work; §8
limitations and conclusion.

## Where every number comes from

Every number in the paper was read from the tree at `era6-campaign-2`
(`git show era6-campaign-2:<path>`). The boards regenerate
byte-identically from the logs (`python3 -m kernel.driver report
runs/<name>`), so a count "from `frontier.md`" is a count from
`log.jsonl` under the order of `KERNEL.md` §5; where a breakdown is not
printed on the board (witnesses per search, partial notes, per-iteration
states) it was computed from `log.jsonl` with that order.

| number in the paper | read from |
|---|---|
| hwmcc24-mini 44 of 74; 15 certified ∀ (13 `btor2-ind`, 2 `btor2-ic3`), 9 witnesses (4 bmc, 3 sim, 2 ind), 20 covering claims (2 of them `all(inf)` by `btor2-sim`), 30 open; residual of every certified answer | `runs/hwmcc24-mini/frontier.md` line 3 and the table rows; per-search split from the `route` column |
| hwmcc24-mini after the first campaign: 43 of 74 after four plays, 14 certified (13 `induction` + 1 `clauses`), 9 witnesses, 20 claims | `runs/hwmcc24-mini/log.jsonl`, best-per-question over iterations 0–3 (iterations 2 and 3 give the same board) |
| hwmcc24-mini reverse-edge pass: 74 partials — 41 `ERR reachable`, 17 refused above 64 bits, 12 existential, 4 budget | `runs/hwmcc24-mini/log.jsonl`, iteration 4 (`via: btor2--c`), `value.progress.note` |
| the ten-minute pass (Table 3): best before, results, spent seconds; 1 proof, 3 claims (one larger), 6 killed | `runs/hwmcc24-mini/log.jsonl`, iteration 5 (`caps.wall_s` 600, `via: btor2-ic3`, `only:` the ten questions); "best before" from the board after iteration 3 |
| hwmcc24-mini official verdicts: 7 open unsolved, 23 solved (17 unsat, 6 sat); the ten questions' verdicts | `runs/hwmcc24-mini/benchmark.json`, field `official` per question |
| svcomp25-mini 26 of 79; 5 certified ∀ (4 `c-ai`, 1 `c--btor2>btor2-ind`), 14 witnesses (12 via RISC-V, 2 via `c--btor2>btor2-sim`), 7 covering claims, 53 open; depths 11–300 on the 31 hard tasks | `runs/svcomp25-mini/frontier.md` line 3 and the table rows |
| svcomp25-mini first campaign: 3 proofs `checked` at gap 1 with k = 7, 6, 3; regrade times 0.55/0.41/0.51 s and 0.82/0.42/0.58 s; the fourth proof (`safe5`, k = 6, 0.19 s); 8 covering claims at the campaign's end | `runs/svcomp25-mini/log.jsonl`: `grade: checked` records of iterations 1–2, the six `regrade` records (no iteration), iteration 3 (`only: safe19 safe20 safe5 unsafe6`) |
| `c-ai` on svcomp25-mini: four proofs at 0.038 s each; 75 partials (38 `ERR reachable`, 37 existential) | `runs/svcomp25-mini/log.jsonl`, iteration 4 (`via: c-ai`) |
| walls: 60 s hardware; software 60 s in the first play (14 tasks), 30 s in iterations 1–3, 60 s since | the `play` event records (`caps.wall_s`) in both logs |
| svcomp25-mini official: every task solved by ≥ 1 verifier; 53 open = 30 true + 23 false; the 31 hard tasks | `runs/svcomp25-mini/benchmark.json`, `official`; `registry/domains/software/manifest.json` (notes: 79 = 37 exists at inf, 25 forall at 100, 17 forall at inf; 31 hard) |
| hwmcc24-mid 47 of 80; 12 certified ∀ (all `btor2-ind`), 8 witnesses (6 bmc, 1 sim, 1 ind), 27 covering claims (21 ind, 6 bmc; 26 at ask 20, `unsafe3` at ask 30), 33 open | `runs/hwmcc24-mid/frontier.md` line 3 and the table rows |
| hwmcc24-mid partials: sim `free bits exceed enumeration` on 79; interval route 35 budget / 23 refused; 21 killed at twice the wall (14 ind, 4 interval, 2 bmc, 1 ic3); 6 `rc=1` (3 ind, 3 ic3) | `runs/hwmcc24-mid/log.jsonl`, `value.progress.note` per route |
| hwmcc24-mid official: 8 open ∀∞ unsolved by all eight solvers; 17 open bounded unsat, 8 open existential sat; `unsafe3` sat | `runs/hwmcc24-mid/benchmark.json`, `official` |
| hwmcc24-arrays 1 of 55; witness at depth 6 (bmc 0.5 s, ind again); 99 claims (50 bmc, 49 ind), deepest 66; 38 asks ∀∞; sim and ic3 refuse 55 each, reverse edge 55, nested arrays 4 machines refused by both bounded searches, 1 inductive run killed | `runs/hwmcc24-arrays/frontier.md`; `runs/hwmcc24-arrays/log.jsonl` (`value.progress.note`; the `unsafe1` records) |
| hwmcc24-arrays official: 38 of 54 open unsolved by all 5 solvers, 16 solved (3 unsat, 13 sat) | `runs/hwmcc24-arrays/benchmark.json`, `official` |
| 32 certified universal answers across the boards (15 + 5 + 12 + 0) | the four boards |
| registry: 11 language entries, 5 pair entries, 10 search entries, 2 domains; 3 languages, 4 pairs, 5 searches by name; 4 certificate checkers under three form names (`induction` at both hubs, `clauses`, `ranges`), 7 judges | `git ls-tree era6-campaign-2 registry/*/` (directory names) |
| trusted base (Table 1): vectors, controls, anchors per judge | `registry/languages/{btor2@5,c@5,riscv}/manifest.json`, `admission.{vectors,controls,evidence}`; `registry/domains/*/manifest.json`, `admission.anchors` |
| judge sizes 390 / 1,620 / 1,618 / 1,422 / 4,534 / 3,935 / 603 lines | `wc -l` of `registry/languages/btor2@5/interp.py`, `…/evidence/induction/check.py`, `…/evidence/clauses/check.py`, `registry/languages/c@5/interp.py`, `…/evidence/induction/check.py`, `…/evidence/ranges/check.py`, `registry/languages/riscv/interp.py` |
| exchange rates 3.65 / 5.37 / 3.13 (and 3.97 for `c--btor2` revision 1), 4.19 for `btor2--c` | `registry/pairs/*/manifest.json`, `admission.ledger.dilution_bytes` |
| `btor2--c`: corpus 17 (6 + 8 + 3), 6 certificates (4 `ranges`, 1 k-induction, 1 clause invariant), 13 mutants (4 prog, 2 wit, 3 cert, 2 stimulus map, 2 bound map), fragment refusals, 57 of 74 translate | `registry/pairs/btor2--c/manifest.json`, `admission.channels`, `admission.stimulus_map`, `admission.bound_map`, `notes` |
| `btor2-bmc` accelerator byte-agreed on 6 corpus machines | `registry/searches/btor2-bmc/manifest.json`, `admission.accelerator.agreed` |
| revision histories (`btor2-sim@2/@3`, `btor2-ind@2/@3`, `btor2-ic3@2`; 4 and 13 crashed programs) | the `notes` of `registry/searches/*/manifest.json` |
| BTOR2 vectors 11 hand-written machines; C vectors 12; 1,045 clang agreements | `registry/domains/hardware/manifest.json`, `registry/domains/software/manifest.json` (`anchors`) |
| hwmcc24-mini = 23% of the HWMCC'24 bit-vector track; 31 hard SV-COMP tasks | `registry/domains/*/manifest.json`, `notes` |
| kernel 2,654 lines: driver 689, gate 1,238, registry 191, results 419, runner 85, `__init__` 32 | `wc -l kernel/*.py` |
| Lean 502 lines (`Kernel.lean` 35, `Key.lean` 327, `Trust.lean` 140); theorem names; axiom audit | `wc -l kernel/mechanization/**/*.lean`; `kernel/mechanization/README.md`; `lake build` output at the tag (order lemmas axiom-free; fold and residual lemmas `propext`, `Quot.sound`; `residual_gap_zero` `propext` only) |
| tests 2,077 lines, eight test modules and the toy registry; the refusals and forgeries listed | `wc -l kernel/tests/*.py`; `kernel/tests/__init__.py`; test names in `test_gate.py`, `test_forge.py`, `test_seal.py`, `test_registry.py` |
| second lineage 727 lines; protocol, one disclosure, eleven ambiguities | `wc -l kernel/second/*.py`; `kernel/second/README.md` |
| fifty words of the vocabulary | `KERNEL.md` §12, the bold entries of its table |
| dates: 2026-08-20 restart; first campaign 2026-08-29/30; reverse edge and rungs 2026-09-06/07 | `KERNEL.md` (head), `HISTORY.md` Era 6 |
| fifth-generation boards 46 of 74, 5 of 55, 45 of 80; the BDD search | `HISTORY.md` Era 5 |

Two sentences of the prose at the tag differ from its log, and the
paper follows the log: `README.md` and `HISTORY.md` say the ten-minute
pass wrote "four larger bounded claims" (the log has three claims, of
which one, `open6`, is larger than the incumbent; two equal it), and
`README.md` says "eight machines with nested arrays" lie outside the
inductive search's fragment on hwmcc24-arrays (the log has eight
partials saying so, on four machines, from the two bounded searches).

## Notes after the tag

**2026-09-14.** Three searches were admitted after the tag —
`btor2-pdr`, `btor2-sim@4`, `c-ai@2` — so the registry holds more
search entries than §5 counts, and the conclusion's "what moves the
boards next" has candidates the boards have not yet been played
through.

**2026-10-03.** Fault injection was built and run (`kernel/faults`;
`README.md` at the root has the numbers), and the three languages were
revised with vectors and controls: `btor2@6`, `c@6` and (2026-10-04)
`c@7`, `riscv@2`. No
judge's text changed and no board moved, but Table 1 (vectors and
controls per judge) and the counts of language entries in §5 describe
the tag, not the tree; the limitation "the judges are not all small"
now has a measurement beside it — half of 700 sampled judge mutants
refused at the tag's revisions — and the claim that a transport can
lose a grade and never forge one has 16,720 plays behind it, none
wrong and `certified`.

**2026-10-04.** The three searches were played through their own
routes: the boards stand at 45 of 74, 26 of 79, 47 of 80, and 12 of
55, with 48 universal answers certified at gap 0 (the paper: 44, 26,
47, 1, and 32). The paper's statements that no result carries the
corroborated flag, and that what moves the boards next is a search
that reasons differently, are both overtaken: `btor2-pdr`, of a
lineage disjoint from the earlier searches', corroborates 29 and 22
verdicts on the two hardware boards it moved, and `btor2-sim@4` moved
the array rung.

**2026-10-05.** `btor2-pdr` was played on svcomp25-mini as well (26 of
79 still; one bare claim lifted to a certificate at C, so 6 certified
universal answers there and 49 across the boards), and the tree was
tagged **`era6-campaign-3`**. That tag is what the re-cut of this
paper is to be written against; until then the paper describes
`era6-campaign-2` and the notes above say where the tree has moved.
