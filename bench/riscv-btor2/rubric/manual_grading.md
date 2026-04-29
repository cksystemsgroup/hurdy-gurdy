# Manual grading instructions

The rubric LLM (see `rubric_prompt.md`) is the primary grader for
T4 lift quality. **A random sample of ≥ 10% of T4 transcripts is
also graded by a human** (BENCHMARKING.md §6) so we can report
inter-rater agreement and catch cases where the rubric LLM
systematically mis-grades.

This file is the human grader's contract. It mirrors the rubric
LLM's prompt — same rubric, same input shape — so the two can be
compared directly.

## Who can grade

Anyone who can read the riscv-btor2 SCHEMA.md and a few corpus
tasks well enough to recognize a correct source-level
explanation. No solver background required.

The grader must not have authored any T4 task they're being asked
to grade. The harness enforces this by tracking `oracle_provenance`
in `task.toml` against the grader's identity in the run manifest.

## What you see (per transcript)

The harness packages each grading job as a single JSON object
identical in structure to what the rubric LLM sees, with the
same redactions:

```
{
  "task_id":          "<task slug>",
  "lowering_sensitive": true | false,
  "question":         "<question text>",
  "source_s":         "<source.S>",
  "disassembly":      "<objdump -d output>",
  "expected_verdict": "...",
  "expected_lift": {
    "cause_pc":       <int>,
    "cause_mnemonic": "<string>",
    "acceptable_alternative_pcs": [<int>, ...],
    "explanation_summary": "<reference prose>",
    "keywords":       ["...", ...]
  },
  "observed_lift": {
    "cause_pc":       <int>,
    "cause_mnemonic": "<string>",
    "explanation":    "<the LLM's prose>"
  },
  "transcript":       "<redacted full transcript>"
}
```

You see neither which model produced this, nor which condition
(A/B/C/D) it ran in. Vendor / slot / condition strings are
replaced with `<MODEL>` / `<SLOT>` / `<CONDITION>`. Don't try to
de-anonymize.

## Score (0/1/2)

Same rubric as the LLM grader. Lift schema lives in
`lift_schema.md`; reproduced here for convenience:

| Score | Meaning |
|---:|---|
| **2** | `cause_pc` matches `expected_cause_pc` (or one of `acceptable_alternative_pcs`), AND `explanation` captures the source-level mechanism. |
| **1** | One of the two halves is right and the other is partially right. |
| **0** | Neither half is right, OR the explanation contradicts schema-level semantics, OR `observed_lift` is `null`. |

### What "captures the source-level mechanism" means

- Names the relevant lowering surface (e.g., "sign extension on
  word ops", "byte ordering on multi-byte loads", "branch sense").
- Or names a concrete schema rule (e.g., "writes to x0 are
  dropped", "DIVU by zero returns 2^64-1").
- Or shows the chain of arithmetic that leads to the verdict
  (e.g., "x5 starts at 0, increments to 8, never crosses 0").

What it does *not* mean: lists every instruction in the program,
or restates the question, or asserts a verdict without explaining
the mechanism.

### Typical 1-vs-2 distinction

Score 2 anchors on a explanation that, if read in isolation by a
RISC-V programmer, would let them predict the verdict without
seeing the source. Score 1 lacks that property — the prose is
correct but underspecified.

If you find yourself going back and forth between 1 and 2, default
to 1 and write the doubt into your `notes`.

### Typical 0-vs-1 distinction

Score 0 is for clearly wrong answers (wrong PC, wrong mechanism,
or `null`). If `cause_pc` is right or `explanation` mentions any
real mechanism, lean 1.

## Output format

Submit one JSON object per task you grade. The harness ingests
these into the run manifest under `runs[].graded.lift_score`
alongside the rubric LLM's score.

```json
{
  "task_id":   "0003-addiw-sign-ext",
  "score":     2,
  "matched_pc": true,
  "matched_explanation": true,
  "reason":    "PC matches; explanation names sign-extend and the high-bit case directly.",
  "notes":     "",
  "grader_id": "<hash or pseudonym>",
  "graded_at": "2026-05-15T13:42:00Z"
}
```

`grader_id` may be a stable pseudonym (e.g., `human-A`,
`human-B`); we report inter-rater agreement *between* graders, not
per-grader accuracy.

## Disagreement handling

When the rubric LLM and the human grader differ on a transcript,
the harness flags it in the manifest's per-cell failures list. A
**second human reviewer** (different from the first) breaks the
tie. The resolution is recorded with `resolved_by` and
`resolution_score`; the original disagreement is preserved in
`failures[]` for the §8.5 artifact bundle.

Track the rate of:
- LLM-rubric vs first-human disagreements
- First-human vs second-human disagreements

These two rates together calibrate the rubric LLM's reliability.
The benchmark's headline tables (§5) cite both.

## Sampling

The harness selects ≥ 10% of T4 transcripts at random per
`(model, condition)` cell, with the seed recorded in the run
manifest. The sampling must be done *after* all transcripts are
collected, before either grader sees them.

## What you do NOT do

- **Don't grade verdict.** Verdict is `matcher.py`'s job; if
  `verdict_correct=false` is in the manifest, that's already
  recorded. Your job is the lift quality column.
- **Don't grade witness.** Same.
- **Don't try to reproduce the dispatch.** The verdict is what
  it is; you're scoring the explanation.
- **Don't penalize register-name aliases.** `x10` and `a0`
  refer to the same register. Both are accepted.
- **Don't penalize the LLM for mentioning the schema or the
  pair tooling.** The transcript is from condition A, B, C, or D —
  some will reference the pair, some won't. The lift score is
  about what the explanation *says*, not how the LLM got there.

## A note on Copilot Pro

Copilot Pro gives access to multiple model families (Claude /
GPT / Gemini) through one provider. The rubric LLM at v1 is
pinned to `claude-sonnet-4-6` (per `llms.md`'s `rubric_llm`
slot) regardless of how it's accessed. If the operator has the
Anthropic API directly, that's the canonical path; routing
through Copilot is fine if it preserves the model snapshot id.
