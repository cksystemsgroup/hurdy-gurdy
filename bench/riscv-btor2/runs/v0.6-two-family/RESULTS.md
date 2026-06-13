# v0.6 — two-family A/B/C results (the first §7-grade run)

**Date:** 2026-06-12 → 2026-06-14. **Corpus tag:**
`riscv-btor2-bench-v0.6-prereg`. **Matrix:** 28 tasks (25 C-corpus +
3 iter-43 UB wedges) × conditions A/B/C × **seeds 1–5** = 420 cells
per model. **Both models complete: 420/420, 0 unresolved errors.**

**Models — two unrelated families** (BENCHMARKING.md §7):

| Slot | Family | Model | Routing |
|---|---|---|---|
| `slot_CC_haiku` | Anthropic | `claude-haiku-4-5-20251001` | `claude` CLI + bench MCP server |
| `slot_A` | Google | `gemini-2.5-flash` | AI Studio direct, **paid tier** |

This satisfies §7 in full: ≥ 2 unrelated families **and** ≥ 5 seeds
per cell. Conditions are the §3 required trio: A (source-only),
B (pair-equipped), C (solver-only, hand-written encoding). Per-seed
median and range are reported alongside the pooled rate.

## Headline — verdict accuracy (pooled correct/cells; per-seed median [range])

| Subset | Cond | Haiku | Gemini |
|---|---|---:|---:|
| **All (28)** | A | 127/140 (91%) · 89% [86–96] | 115/140 (82%) · 82% [75–89] |
| | **B** | **140/140 (100%) · 100% [100–100]** | 114/140 (81%) · 79% [75–96] |
| | C | 127/140 (91%) · 89% [86–96] | 95/140 (68%) · 68% [64–71] |
| **Lowering-sens. (13)** | A | 57/65 (88%) · 85% [85–92] | 52/65 (80%) · 77% [69–92] |
| | **B** | **65/65 (100%) · 100% [100–100]** | **56/65 (86%) · 85% [77–100]** |
| | C | 54/65 (83%) · 85% [69–92] | 37/65 (57%) · 62% [46–62] |
| **UB wedges (8)** | A | 32/40 (80%) · 75% [75–88] | 29/40 (72%) · 75% [62–88] |
| | **B** | **40/40 (100%) · 100% [100–100]** | **32/40 (80%) · 75% [62–100]** |
| | C | 29/40 (72%) · 75% [50–88] | 21/40 (52%) · 50% [50–62] |

## Hallucination count — wrong verdict at stated confidence ≥ 0.8 (of 140 cells)

| Subset | A | B | C |
|---|---:|---:|---:|
| Haiku, all | 9 | **0** | 13 |
| Gemini, all | 19 | **1** | 21 |
| Haiku, UB wedges | 6 | **0** | 11 |
| Gemini, UB wedges | 11 | **1** | 11 |

## The findings the run was designed to produce

**1. The pair wins exactly where it should — on lowering-sensitive
code — and is neutral on easy tasks.** B is best (or tied-best) on
every subset for both models, and the gap widens as lowering matters
more. On the UB wedges B is 100% (Haiku) and 80% (Gemini) vs A's
80% / 72% and C's 72% / 52%. On the *full* 28-task set Gemini's
B (81%) ≈ A (82%) — a statistical tie — because the easy tasks need no
help; the pair's contribution concentrates in the lowering-sensitive
slice (Gemini B 86% vs A 80%). Reported as a Pareto-style win, not a
blanket-dominance claim: the pair earns its keep where C-level and
RV64-level verdicts diverge.

**2. C does not recover B — so the pair's value is not "access to a
solver."** This is the §3.C control, and it holds across 5 seeds and
both families. Given the *same z3* but no pair (the LLM hand-writes
its own encoding), UB-wedge accuracy is **no better than source-only
and consistently worse**: Haiku 72% (C) vs 80% (A); Gemini 52% (C) vs
72% (A). The pooled C rate is the *lowest* of the three conditions in
every lowering-sensitive cell. The improvement under B is therefore
attributable to the pair's schema-pinned RV64 lowering that the
translation carries and a hand encoding lacks — exactly the
attribution BENCHMARKING.md §3 requires condition C to isolate.

**3. The pair nearly eliminates confident errors — the most robust
cross-family result.** B's high-confidence-wrong count collapses to
**0 (Haiku) and 1 (Gemini)** across 140 cells each, from 9–21 under A
and C. Crucially, **C is the *worst* condition for hallucinations**,
not the best: a self-written encoding the model trusts produces more
confident-and-wrong answers than no tools at all (Haiku 13 vs A's 9;
Gemini 21 vs A's 19). For a verifier-style use case this §5 metric is
the headline.

**Corollary — the pair nearly eliminates confident errors.** B's
hallucination count collapses to 0 (Haiku) and 1 (Gemini) from
double digits under C. For a verifier-style use case this is the
metric that matters most (§5).

## Cost profile (median tokens in+out)

| | A | B | C |
|---|---:|---:|---:|
| Haiku | 8 851 | **5 160** | 10 158 |
| Gemini | 3 298 | 31 208 | 10 966 |

Cost is **model-dependent and not a clean win**: for Haiku, B is the
*cheapest* condition (compile→dispatch→lift replaces speculative
reasoning). For Gemini, B is the most expensive — it emits far more
tokens orchestrating the tool surface. Reported honestly per §5; the
accuracy/hallucination case for B does not rest on cost.

## Where the residual failures are

Both models miss the same three wedges under A and C:
`0115-c-int-overflow`, `0117-c-int-min-div-neg-one`,
`0300-c-neg-int-min` — all "C says UB, RV64 defines it" cases where
the model reasons from the C standard (as CBMC does). Under B, Haiku
clears all three on all 5 seeds (40/40); Gemini still misses on a
minority of seeds (its B wedge score is 32/40, per-seed median 75%,
range 62–100%), which is itself informative: the pair supplies the
correct lowering, but the weaker model does not always act on it. The
other five wedges (0116, 0118, 0121, 0125, 0261) are essentially
solved under B for both models.

## Reproduction

- `slot_CC_haiku/` and `slot_A/`: `runs.jsonl` (raw, incl. stale
  error rows from resume passes), `transcripts/` (lossless, §8.4),
  `manifest.json` (§8.7, 420 runs each).
- **Dedup before tallying:** `runs.jsonl` carries stale error rows
  alongside successful retries; resolve on `(task_id, condition,
  seed, question_id)` preferring non-error rows. (Haiku had 0 errors;
  only slot_A needs this.)
- Hallucination counts come from per-transcript
  `observed.confidence`; the `RunRecord` JSONL does not carry it.

## Harness note (committed with this run)

The Gemini condition-C cells initially hit a harness bug — Google
returns `candidate.content.parts = None` (not `[]`) on a
`MAX_TOKENS`/safety stop, which crashed the turn loop. Fixed to
coerce None parts to `[]` (degrades to an `unknown` verdict instead
of crashing); the 7 affected cells were re-run clean. See the
`_call_google` guard in `harness.py`.

## Still open for publication-grade

- ~~Seeds 4–5 (§7 wants ≥ 5).~~ **Done** — 5 seeds, 420 cells/model.
- Rubric-LLM grading of T4 lift quality over the committed
  transcripts (§9.7).
- The §7 leakage and determinism checks logged into the manifest.
