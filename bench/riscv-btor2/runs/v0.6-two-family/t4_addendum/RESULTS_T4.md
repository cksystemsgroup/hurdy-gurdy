# v0.6 T4 addendum — lift-quality (§9.7 rubric) results

**Date:** 2026-06-14. **Why this exists:** the pre-registered v0.6
slice (C tasks 0100–0124 + wedges) is entirely T1/T2, so the §9.7
rubric — which grades *only* the T4 `lift` causal-explanation field —
had nothing to score on the main run. This addendum runs the corpus's
5 T4 tasks (all assembly: `0001`, `0003`, `0005`, `0011`, `0013`) so
the rubric is actually exercised.

**Matrix:** 5 T4 tasks × A/B/C × seeds 1–5 = 75 cells per model;
both models complete, 0 errors. **Rubric:** `gpt-4.1-mini` via GitHub
Models, blind (model/condition/slot tokens redacted before grading),
0/1/2 per `rubric/lift_schema.md`. 150 cells graded, 0 ungradeable.

## Lift-quality scores (mean of 0/1/2; score distribution; null-lift count)

| Model | A (source-only) | B (pair) | C (solver-only) |
|---|---:|---:|---:|
| Haiku 4.5 | 1.96 · [2:24 1:1 0:0] · 0 null | 1.96 · [2:24 1:1 0:0] · 0 null | 1.92 · [2:23 1:2 0:0] · 0 null |
| Gemini 2.5 Flash | **1.84** · [2:21 1:4 0:0] · 0 null | 1.36 · [2:15 1:4 0:6] · **6 null** | 1.60 · [2:18 1:4 0:3] · 3 null |

## Findings — an honest neutral/negative result that sharpens the claim

**1. The pair does not improve lift quality; LLMs already explain
causes well from the assembly directly.** Source-only (A) lift quality
is high for both models (Haiku 1.96, Gemini 1.84). Producing a
source-level causal explanation of a verdict is something these models
do well unaided — so it is *not* where the pair's value lies. This is
consistent with, and sharpens, the main v0.6 result: the pair's
contribution is **verdict correctness on lowering-sensitive code**
(where A/C fail and B succeeds), not prose explanation quality.

**2. For the weaker model, condition B can *degrade* lift quality —
the tool workflow crowds out the structured field.** Gemini's lift
mean drops from 1.84 (A) to 1.36 (B), driven entirely by **6 null
lifts**: absorbed in the multi-turn compile→dispatch→lift loop, the
model sometimes omits the `lift` object altogether. When it *does*
emit one under B the quality is fine (15/25 score-2). Haiku shows no
such effect (0 nulls, 1.96 under both A and B) — it is strong enough
to hold both the tool loop and the output contract. So the cost is
model-dependent: the pair's tool surface imposes an output-discipline
load that a weaker model pays in dropped structured fields.

**3. The §9.7 rubric machinery works as designed.** Blind grading
(redactions logged per cell), 0/1/2 calibrated, null-lift auto-zero,
0 ungradeable across 150 cells. The 0/1/2 distribution is
discriminating (not all-2), and the cross-condition signal is real.

## Caveats

- 5 tasks × 5 seeds is a small T4 corpus (per BENCHMARKING.md §4.2 a
  full corpus wants ≈25% T4; these 5 are all the corpus has). Treat
  the means as indicative, not tight.
- These are **assembly** tasks; condition A is source-only on
  `source.S`. They were excluded from the main v0.6 slice precisely
  because they have no C-source baseline — so this addendum is a
  *separate* slice, not part of the pre-registered v0.6 numbers.
- Lift grading was added post-hoc over saved transcripts
  (`grade_lift_pass.py`), decoupled from the matrix run and
  re-runnable. Required a prompt fix first (below).

## Harness fix that made this measurable

The first T4 run scored 0 on every cell. Root cause: the prompt said
"`lift` is required for tasks tagged T4 in `task.toml`", but the model
never receives `task.toml` and cannot read files, so it had no way to
know a task was T4 and correctly emitted `lift: null`. Fixed by
injecting a `{{LIFT_DIRECTIVE}}` from `Task.difficulty` — a strong
"you MUST emit cause_pc/cause_mnemonic/explanation" block for T4,
empty for T1/T2/T3 (so the pre-registered main-slice prompts are
unchanged). After the fix, 66/75 (Gemini) and 75/75 (Haiku)
transcripts carry a real lift. See `harness.py` `assemble_prompt` and
`prompts/_base.md`.

## Reproduction

- `slot_*/runs.jsonl`, `transcripts/`, `manifest.json` — the matrix.
- `slot_*/lift_scores.jsonl` — one rubric row per cell
  (score, matched_pc, matched_explanation, reason, redactions).
- `grade_lift_pass.py` — the post-hoc grader; re-run with
  `--slot-dir <slot>`. Requires `GITHUB_TOKEN` (rubric slot) and the
  `openai` SDK.
