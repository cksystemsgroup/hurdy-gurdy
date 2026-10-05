# The gate paper

The **sixth generation's paper**: a new submission, not a version of
the instrument paper (arXiv, `../arxiv.tex`) or the frontier paper
(`../frontier/`). Its contribution is the design in which every
executable of a verification system is untrusted generated text
admitted through one gate, with grades computed as geometry from where
an interpreter run judged the evidence — and the measurement of that
design at one frozen commit, against faults nobody shipped. Shares
only `../references.bib` with the other two papers; the preamble is
from scratch. `make` builds `gate.pdf` (latexmk, pdflatex + bibtex;
`make clean` removes the build products and keeps the PDF).

**Title:** *Judged Whole — One Gate for Untrusted Verification
Infrastructure.*

**Era and tag.** The paper describes **Era 6** (`KERNEL.md` and
`HISTORY.md` at the root) exactly as it stands at tag
**`era6-campaign-3`** (commit `1ae7f226`, 2026-10-05): the registry
after the three searches of 2026-09-14 and the vector-only revisions
`btor2@6`, `c@6`, `c@7`, `riscv@2`; the fault-injection deposit under
`kernel/faults/results/`; the four boards after every play through
`btor2-pdr`, `btor2-sim@4`, and `c-ai@2`. The tag is frozen. **The
paper is not edited to track later commits**; where a later change to
the tree invalidates a claim, the note goes at the end of this file,
dated, never into the paper silently (the rule `HISTORY.md` states for
every paper in this directory). This is the paper's second cut: the
first was written against `era6-campaign-2` and is in the history of
this directory up to commit `1ae7f226`.

**Venue and constraints.** Target PLDI 2027 (deadline 2026-11-12
AoE): `acmsmall`, single column, `review` and `anonymous` options on;
double-blind — no author names, no funding, no institution, no
repository URL, **and no system name**: the text says "the system",
never the public name, and cites the project's earlier papers in the
third person (the preprint's bib entry lives in `gate-extra.bib`
because the shared one in `../references.bib` carries the repository
URL in its note). At most 20 pages of text excluding the
bibliography; no appendix. At this cut the text ends on page 20. The
disclosure of generative AI that ACM's Policy on Authorship requires
(the tool by name, and how it was used) is the paragraph *Provenance*
in the introduction, made part of the argument as the instrument
paper's "provenance disclaimer" was: the code and most of the text
are generated, no human reviewed either for semantic correctness, and
what the reader is offered instead is what the system offers in place
of trust in its transports — numbers that regenerate from the
kernel's records, proofs Lean checks, vectors confirmed by tools that
are not generative. The policy's default place is the
acknowledgements, which `acmart` hides under `anonymous`; PLDI 2027's
call for papers had no text on the matter as of 2026-10-05. Two `TODO
author` comments remain in the source: to confirm every sentence of
that paragraph, and of the paragraph on the generator and the human's
role (`sections/registry.tex`).

Sections: §1 introduction (the sentence, the design in brief, the two
claims that can be wrong and how each is tested, provenance,
contributions, what is not claimed); §2 one question, two routes (`README.md`'s story in
`KERNEL.md`'s words, the square as the first figure); §3 the design
(`KERNEL.md` §1–§8, §12); §4 the kernel made solid four ways
(`KERNEL.md` §9), with the order and the residual stated as two
theorems; §5 what was admitted (the registry, and the trusted base as
`base` prints it); §6 measurements — §6.1 fault injection (at the
gate, with the gate taken away, which way a surviving checker leans),
§6.2 closing the survivors, §6.3 the boards, §6.4 what the numbers
say; §7 related work; §8 limitations and conclusion. References added at this cut live in `gate-extra.bib`,
each checked against its publisher's page: the SV-COMP 2025 report,
AutoVerus, AlphaVerus, LeanDojo, and two on mutation testing.

## Where every number comes from

Every number in the paper was read from the tree at `era6-campaign-3`
(`git show era6-campaign-3:<path>`). The boards regenerate
byte-identically from the logs (`python3 -m kernel.driver report
runs/<name>`), and the fault-injection tables from the deposit
(`python3 -m kernel.faults report`); where a breakdown is not printed
there it was computed from the `.jsonl` records with the order of
`KERNEL.md` §5.

| number in the paper | read from |
|---|---|
| 1,672 transport mutants (1,072 of the pairs' twelve files, 600 of the six searches) and 700 judge mutants; 100 per file, two files with fewer sites (55 and 17) | `kernel/faults/results/gate-{pairs,searches,languages}.jsonl`, the `target` records (`sampled`) of the entries bound before the revisions (`btor2@5`, `c@5`, `riscv`) |
| transports at the gate: 736 refused (694 own, 42 conservativity), 936 passed, 528 of those on unexecuted lines | `gate-pairs.jsonl`, `gate-searches.jsonl`: `outcome`, `tier`, `cover` |
| judges before (Table 2, left): 348 refused = 292 own + 26 predecessor + 30 dependents; per judge 80/33/26/61/37/49/62; 25 of BTOR2's interpreter by its predecessor; 11 of RISC-V's by dependents; statements executed 90/54/44/79/63/70/76% | `gate-languages.jsonl`, entries `languages/btor2@5`, `languages/c@5`, `languages/riscv`: `outcome`, `tier`, and the `target` records (`executed` of `statements`) |
| plays (Table 3): 16,720 plays; same 14,156, lost 2,368, gained 63, wrong claimed 127, wrong checked 6, wrong certified 0; the split between pairs and searches; all 133 blamed; 180 (question, route) pairs, 90 unsafe | `kernel/faults/results/play-{pairs,searches}.jsonl`: `plays[].verdict`, `plays[].blamed`, and the `target` records (`questions`) |
| the six wrong checked records: mutants of `pairs/c--btor2@2/T.py` on `svcomp25-mini/unsafe11` over the route to `btor2-pdr`, gap 1 | `play-pairs.jsonl` |
| gate outcome against play outcome: of 736 refused, 46 wrong and 506 lost; of 936 passed, 832 unchanged, 90 lost, 7 wrong (one behind a wrong checked record) | the two deposits joined on (entry, file, node, alt) |
| probe: 255 surviving checker mutants; 245 same, 4 stricter, 6 laxer (BTOR2 clauses 1, BTOR2 induction 4, C induction 1); pools of up to 60 | `kernel/faults/results/probe-languages.jsonl`, entries `languages/btor2@5` and `languages/c@5`: `lean`, and the `probe` records (`accepted`, `refused`) |
| the six holes, by line | `probe-languages.jsonl` (`line`, `detail`) against `registry/languages/{btor2@5,c@5}/evidence/*/check.py` |
| oracles: 301 BTOR2 checks; 896 RISC-V checks; 651 C checks in 34 of 37 programs; five expectations of the generator corrected by the Sail model | `oracles/packs/languages/btor2/operators/checks.jsonl`, `…/riscv/operators/checks.jsonl`, `…/c/tables/testimony.jsonl`, and the `PROVENANCE.md` beside each |
| judges after (Table 2, right): 453 refused, per judge 98/43/42/83/43/55/89; statements 96/61/52/89/69/75/93%; no laxer survivor among 217 checker survivors; thirty interpreter survivors | `gate-languages.jsonl` and `probe-languages.jsonl`, entries `languages/btor2@6`, `languages/c@6` (interpreter), `languages/c@7` (checkers), `languages/riscv@2`; the classification of the thirty in the `notes` of those manifests |
| C's entry admitted in a little over two minutes, its predecessor in under one | measured at admission on the host, 2026-10-04 (not in the tree) |
| boards (Table 4): 45 of 74 (24 certified ∀, 9 witnesses, 12 claims, 29 corroborated, 29 open); 26 of 79 (6, 14, 6, 0, 53); 47 of 80 (19, 8, 20, 22, 33); 12 of 55 (0, 12, 0, 0, 43); 49 certified ∀ and 38 covering claims in all | `runs/*/frontier.md` and `runs/*/log.jsonl`; corroborated by `kernel.results.corroborated` |
| open questions officially: 7 + 22 (16 unsat, 6 sat); 0 + 53 (30 true, 23 false); 8 + 25 (17 unsat, 8 sat); 38 + 5 (3 unsat, 2 sat); 53 unsolved and 105 solved in all; every settled row agrees, one bounded claim beside an unbounded verdict (`hwmcc24-mid` `unsafe3`) | `runs/*/benchmark.json`, field `official` per question |
| the first plays: 43 of 74 and 26 of 79; twelve of fourteen software witnesses over both bridges; three proofs checked at gap 1 then regraded in 0.55, 0.41, 0.51 s | `runs/hwmcc24-mini/log.jsonl` iterations 0–3; `runs/svcomp25-mini/log.jsonl` iterations 0–3 and the `regrade` records |
| the reverse edge: 74 partials — 41 error reachable, 17 refused above 64 bits, 12 existential, 4 budget | `runs/hwmcc24-mini/log.jsonl`, iteration 4 (`via: btor2--c`), `value.progress.note` |
| the rungs' first plays, 47 of 80 and 1 of 55; the ten-minute pass, one proof and six killed | `runs/hwmcc24-{mid,arrays}/log.jsonl` iteration 0; `runs/hwmcc24-mini/log.jsonl` iteration 5 (`caps.wall_s` 600) |
| one turn of the loop: arrays 1 → 12 (eleven witnesses); `btor2-pdr` certifies 22 and 17, one question newly settled, fifteen bare claims lifted on hardware and one on software; 79 partials over the RISC-V road; eleven cones above the cap; 154 partials of `c-ai@2` | `runs/hwmcc24-arrays/log.jsonl` iteration 1; `runs/hwmcc24-mini/log.jsonl` iterations 6–7; `runs/hwmcc24-mid/log.jsonl` iterations 1–2; `runs/svcomp25-mini/log.jsonl` iteration 5 |
| walls: 60 s, two software plays at 30 s, one pass at 600 s | the `play` event records (`caps.wall_s`) |
| registry: 15 language entries, 5 pair entries, 13 search entries, 2 domains; 3 languages, 4 pairs, 6 searches by name; four generator tags | `git ls-tree era6-campaign-3 registry/*/`; `lineage` in the manifests |
| trusted base (Table 1): vectors, controls per judge | `python3 -m kernel.driver base`; `admission` in `registry/languages/{btor2@6,c@7,riscv@2}/manifest.json` |
| judge sizes 390 / 1,620 / 1,618 / 1,422 / 4,534 / 3,935 / 603 lines | `wc -l` of the interpreters and checkers of `btor2@6`, `c@7`, `riscv@2` |
| exchange rates 3.65 / 5.37 / 3.13, and 4.19 for `btor2--c`; its corpus of 17, six certificates, thirteen mutants | `registry/pairs/*/manifest.json`, `admission` |
| `btor2-pdr`: seven corpus machines, three certificates, three mutants | `registry/searches/btor2-pdr/manifest.json`, `admission` |
| the crashes behind `btor2-ind@2` and `btor2-ic3@2` (13 and 4 programs) | the `notes` of `registry/searches/*/manifest.json` |
| hwmcc24-mini = 23% of the HWMCC'24 bit-vector track; 31 hard SV-COMP tasks | `registry/domains/*/manifest.json`, `notes` |
| kernel 2,654 lines: driver 689, gate 1,238, registry 191, results 419, runner 85, `__init__` 32 | `wc -l kernel/*.py` |
| Lean 502 lines; the two theorems as stated; the axiom audit | `kernel/mechanization/Kernel/{Key,Trust}.lean` (`Key.lt_irrefl`, `lt_trans`, `lt_asymm`, `best_mono`, `settled_ratchet`, `same_value_ratchet`, `grade_moves_key`, `gap_moves_key`; `residual_gap_zero`, `residual_mono`, `residual_check_removes_upstream`, `residual_stop_free`); `lake build` output |
| tests 2,259 lines, nine test modules and the toy registry | `wc -l kernel/tests/*.py` |
| second lineage 727 lines; protocol, one disclosure, eleven ambiguities | `wc -l kernel/second/*.py`; `kernel/second/README.md` |
| after the revisions 247 of 700 judge mutants pass admission, 217 of them checker mutants | 700 − 453; Table 2 |

One sentence of the root `README.md` at the tag differs from its log,
and the paper follows the log: the README says the ten-minute pass
wrote "four larger bounded claims" (the log has three claims, of which
one is larger than the incumbent). The paper states only what that
pass proved and what was killed.

## Notes after the tag

None yet.
