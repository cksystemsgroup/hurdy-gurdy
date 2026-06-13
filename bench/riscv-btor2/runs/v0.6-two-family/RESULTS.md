# v0.6 — two-family A/B/C results (the first §7-grade run)

**Date:** 2026-06-12 → 2026-06-13. **Corpus tag:**
`riscv-btor2-bench-v0.6-prereg`. **Matrix:** 28 tasks (25 C-corpus +
3 iter-43 UB wedges) × conditions A/B/C × seeds 1–3 = 252 cells per
model. **Both models complete: 252/252, 0 unresolved errors.**

**Models — two unrelated families** (BENCHMARKING.md §7):

| Slot | Family | Model | Routing |
|---|---|---|---|
| `slot_CC_haiku` | Anthropic | `claude-haiku-4-5-20251001` | `claude` CLI + bench MCP server |
| `slot_A` | Google | `gemini-2.5-flash` | AI Studio direct, **paid tier** |

This is the first run in the benchmark's history that satisfies §7's
"≥ 2 LLMs from unrelated families" bar. Seeds are 3 of §7's
recommended ≥ 5; extend with `--seeds 4,5` (the JSONL resume skips
completed cells). Conditions are the §3 required trio: A (source-
only), B (pair-equipped), C (solver-only, hand-written encoding).

## Headline — verdict accuracy (correct / cells, 3 seeds)

| Subset | Cond | Haiku | Gemini |
|---|---|---:|---:|
| **All (28 tasks)** | A | 76/84 (90%) | 68/84 (81%) |
| | **B** | **84/84 (100%)** | **71/84 (85%)** |
| | C | 78/84 (93%) | 57/84 (68%) |
| **Lowering-sensitive (13)** | A | 34/39 (87%) | 31/39 (79%) |
| | **B** | **39/39 (100%)** | **35/39 (90%)** |
| | C | 34/39 (87%) | 24/39 (62%) |
| **UB wedges (8)** | A | 19/24 (79%) | 17/24 (71%) |
| | **B** | **24/24 (100%)** | **20/24 (83%)** |
| | C | 19/24 (79%) | 13/24 (54%) |

## Hallucination rate — wrong verdict at stated confidence ≥ 0.8

| Subset | A | B | C |
|---|---:|---:|---:|
| Haiku, all | 5 | **0** | 6 |
| Gemini, all | 12 | **1** | 15 |
| Haiku, UB wedges | 3 | **0** | 5 |
| Gemini, UB wedges | 7 | **1** | 7 |

## The two findings the run was designed to produce

**1. B beats both A and C, in both families, with the gap widening on
the lowering-sensitive subset.** Accuracy is highest under B in every
subset for both models. On the UB wedges — C-undefined-but-RV64-
defined behavior — B is 100% (Haiku) and 83% (Gemini) vs A's 79% / 71%.

**2. C does not recover B — so the pair's value is not "access to a
solver."** This is the §3.C control, and it lands hard. Given the
*same z3* but no pair (the LLM hand-writes its own encoding), UB-wedge
accuracy is **no better than source-only and often worse**: Haiku
19/24 under both A and C; Gemini *drops* from 17/24 (A) to 13/24 (C).
Worse, C's hallucination rate is the highest of the three conditions
for both models (Haiku 6, Gemini 15) — a hand-rolled encoding lends
false authority to the same C-standard misreading the model makes
unaided. The improvement under B is therefore attributable to the
pair's schema-pinned RV64 lowering that the translation carries and a
hand encoding lacks, exactly the attribution BENCHMARKING.md §3
requires condition C to isolate.

**Corollary — the pair nearly eliminates confident errors.** B's
hallucination count collapses to 0 (Haiku) and 1 (Gemini) from
double digits under C. For a verifier-style use case this is the
metric that matters most (§5).

## Cost profile (median tokens in+out)

| | A | B | C |
|---|---:|---:|---:|
| Haiku | 8 868 | **5 100** | 10 092 |
| Gemini | 3 294 | 31 009 | 11 098 |

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
clears all three; Gemini still misses on a minority of seeds (its B
wedge score is 20/24, not perfect), which is itself informative: the
pair supplies the correct lowering, but the weaker model does not
always act on it. The other five wedges (0116, 0118, 0121, 0125,
0261) are essentially solved under B for both models.

## Reproduction

- `slot_CC_haiku/` and `slot_A/`: `runs.jsonl` (raw, incl. stale
  error rows from resume passes), `transcripts/` (lossless, §8.4),
  `manifest.json` (§8.7, 252 runs each).
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

- Seeds 4–5 (§7 wants ≥ 5).
- Rubric-LLM grading of T4 lift quality over the committed
  transcripts (§9.7).
- The §7 leakage and determinism checks logged into the manifest.
