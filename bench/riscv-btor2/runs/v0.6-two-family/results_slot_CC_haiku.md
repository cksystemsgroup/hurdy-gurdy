# v0.6 — slot_CC_haiku results (Anthropic half of the two-family run)

**Date:** 2026-06-12. **Model:** `claude-haiku-4-5-20251001` via the
`claude` CLI + bench MCP server. **Matrix:** 28 tasks (25 C-corpus +
3 iter-43 UB wedges) × conditions A/B/C × seeds 1–3 = 252 cells.
**Completion:** 252/252, 0 error rows. Manifest:
`slot_CC_haiku/manifest.json`. Corpus tag:
`riscv-btor2-bench-v0.6-prereg`.

> **Status: one family of two.** The Gemini half (`slot_A`) is
> in progress (16/252 cells; free-tier daily quota; resumes per the
> README). Until it completes, these are single-vendor numbers.
> Seeds are 3 of §7's ≥ 5; extend with `--seeds 4,5` before
> publication-grade claims.

## Headline (3 seeds × 28 tasks per condition)

| Metric | A (source-only) | B (pair) | C (solver-only) |
|---|---:|---:|---:|
| Verdict accuracy | 76/84 (90.5%) | **84/84 (100%)** | 78/84 (92.9%) |
| UB-wedge accuracy (8 tasks × 3) | 19/24 (79%) | **24/24 (100%)** | 19/24 (79%) |
| Hallucinations (wrong @ conf ≥ 0.8) | 5 (3 on wedges) | **0** | 6 (5 on wedges) |
| Median tokens (in+out) | 8 868 | **5 100** | 10 092 |

## The §3.C finding — the condition this run existed to measure

**C does not recover B.** Given the same solver (z3) but no pair —
the LLM hand-writes its own encoding — wedge accuracy stays at A's
level (79% vs 79%), and hallucinations get *worse* than A on the
wedges (5 vs 3): a hand-rolled encoding lends false authority to the
same C-level misreading. The pair's value is therefore not "access
to a solver"; it is the schema-pinned RV64 lowering that the
translation carries and the hand encoding lacks. This is the
defensible form of the claim BENCHMARKING.md §3 requires condition C
for.

Secondary observations:

- **B is also the cheapest condition** (median 5 100 tokens vs
  8 868 / 10 092): compile→dispatch→lift replaces speculative
  reasoning tokens.
- **Failures concentrate on three wedges** under both A and C:
  `0115-c-int-overflow`, `0117-c-int-min-div-neg-one`,
  `0300-c-neg-int-min` — all "C says UB, RV64 defines it" cases
  where the model (like CBMC) reasons from the C standard. The other
  five wedges (0116, 0118, 0121, 0125, 0261) were never missed under
  any condition at these seeds.
- Two non-wedge misses (byteswap at -O1/-O3 under A; one under C)
  are bound/loop-reasoning slips, not lowering issues.

## Caveats

- Hallucination counts are computed from per-transcript
  `observed.confidence` (the JSONL `RunRecord` does not carry the
  confidence field); the metric is wrong-verdict at stated
  confidence ≥ 0.8 per BENCHMARKING.md §5.
- Witness-fingerprint grading applies to the corpus's reachable
  tasks only; per-cell results are in `runs.jsonl` (`graded`).
- Rubric-LLM grading of T4 lift quality has not run yet (requires
  `GITHUB_TOKEN` rate budget); transcripts are committed for it.
