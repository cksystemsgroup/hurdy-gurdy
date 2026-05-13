# Rubric LLM prompt template

The §9.7 rubric LLM grades **T4 lift quality** (the soft-judgment
piece of the benchmark). Verdict and witness are graded
deterministically by `matcher.py`; this prompt only handles `lift`.

The rubric LLM runs **blind to condition and to the model under
test** (BENCHMARKING.md §6) — the harness strips `condition`,
`model_slot`, and any vendor identifiers from the input before
invoking the rubric. A ≥ 10% sample of transcripts is also graded
by hand against the same rubric (see `manual_grading.md`).

This file ships in two pieces — a **system prompt** that's locked
across the whole benchmark, and a **user-prompt template** that
the harness fills in per transcript. Both are part of the §7
pre-registration commit; editing either after pre-reg invalidates
the affected cells.

## Vendor and model

The rubric LLM is pinned in `bench/riscv-btor2/llms.md` under the
`rubric_llm` slot. Active pin: `openai/gpt-4.1-mini` routed via
GitHub Models (deterministic mode: `temperature=0.0`, `top_p=1.0`,
`max_tokens=4096`). The pin was moved from `claude-sonnet-4-6` to
`openai/gpt-4.1-mini` during v0.1.1 because Anthropic billing was
parked; the change is logged in `llms.md`'s resolution log and
contributed to invalidating the original `v0.1.0-prereg` tag.
Substituting the rubric model again is a pre-reg-invalidating
change.

## System prompt (verbatim)

```
You are a rubric grader. You score one piece of a transcript: the
LLM's source-level *explanation* of why the verdict on a small
RV64IMC analysis question is what it is. Your job is to assign a
0/1/2 score and a one-sentence rationale.

You do NOT see which model produced the transcript, which
condition the run was in, or any solver verdicts beyond what is in
the transcript itself. Do not speculate about these. Score only
what the transcript contains.

You will be given:
- TASK: the question text, the source program, and the expected
  source-level cause of the verdict (the perfect-score reference).
- OBSERVED: the LLM's emitted `lift` field (cause_pc,
  cause_mnemonic, explanation).
- TRANSCRIPT: the LLM's prior reasoning, included for context.
  You may consult it but the score is on `OBSERVED.lift`.

Score (0/1/2) per `bench/riscv-btor2/rubric/lift_schema.md`:

  2  cause_pc matches expected (or any acceptable_alternative_pcs)
     AND the explanation captures the source-level mechanism.
  1  one half is right, the other partially right. Examples:
     - PC matches but explanation hand-waves ("the compiler did
       something tricky") instead of naming the mechanism.
     - Explanation names the mechanism correctly but cause_pc is
       off by one instruction within the same lowering family.
  0  neither half is right, or the explanation contradicts the
     schema (asserts wrong semantics), or `OBSERVED.lift` is null.

Output STRICTLY this JSON object — nothing before, nothing after:

{
  "score":   0 | 1 | 2,
  "reason":  "<one sentence, ≤ 30 words>",
  "matched_pc":  true | false,
  "matched_explanation": true | false
}

Be strict. The rubric is calibrated on the assumption that 1 is
genuinely partial — give 1 only when you can name BOTH the right
half and the missing-or-partial half.
```

## User prompt template

The harness fills in the placeholders below from the task and the
transcript. `{{...}}` placeholders match `prompts/README.md`'s
convention.

```
TASK
====

Task id: {{TASK_ID}}
Difficulty: T4
Lowering-sensitive: {{LOWERING_SENSITIVE}}

Question:

{{QUESTION_TEXT}}

Source (`source.S`):

```asm
{{SOURCE_S}}
```

Disassembly:

```
{{DISASSEMBLY}}
```

Expected verdict: {{EXPECTED_VERDICT}}

Expected lift (the perfect-score reference; the OBSERVED need not
match this verbatim, only substantively):

  expected_cause_pc:        {{EXPECTED_CAUSE_PC}}
  expected_cause_mnemonic:  {{EXPECTED_CAUSE_MNEMONIC}}
  acceptable_alternative_pcs: {{ACCEPTABLE_ALTERNATIVE_PCS}}
  expected_explanation_summary:

{{EXPECTED_EXPLANATION_SUMMARY}}

  expected_keywords (soft signal): {{EXPECTED_KEYWORDS}}


OBSERVED
========

The LLM under test emitted this `lift` field as part of its final
answer JSON:

{{OBSERVED_LIFT_JSON}}


TRANSCRIPT (context)
====================

{{TRANSCRIPT_TEXT}}


Score the OBSERVED lift per the rubric. Output strictly the JSON
shape from the system prompt — no preamble, no postscript, no
markdown fence.
```

## Placeholder list

| Placeholder | Source |
|---|---|
| `{{TASK_ID}}` | `task.toml [task.id]` |
| `{{LOWERING_SENSITIVE}}` | `task.toml [task.lowering_sensitive]` |
| `{{QUESTION_TEXT}}` | `task.toml [question.text]` |
| `{{SOURCE_S}}` | `<task>/source.S` |
| `{{DISASSEMBLY}}` | `objdump -d source.elf` |
| `{{EXPECTED_VERDICT}}` | `task.toml [expected.verdict]` |
| `{{EXPECTED_CAUSE_PC}}` | `task.toml [lift.expected_cause_pc]` (hex) |
| `{{EXPECTED_CAUSE_MNEMONIC}}` | `task.toml [lift.expected_cause_mnemonic]` |
| `{{ACCEPTABLE_ALTERNATIVE_PCS}}` | `task.toml [lift.acceptable_alternative_pcs]` (list of hex) |
| `{{EXPECTED_EXPLANATION_SUMMARY}}` | `task.toml [lift.expected_explanation_summary]` |
| `{{EXPECTED_KEYWORDS}}` | `task.toml [lift.expected_keywords]` |
| `{{OBSERVED_LIFT_JSON}}` | the `lift` object from the LLM's final-answer JSON, pretty-printed |
| `{{TRANSCRIPT_TEXT}}` | full text of the transcript (model-message stream), with vendor identifiers redacted |

## Redactions before invocation

The harness strips the following from `{{TRANSCRIPT_TEXT}}` before
passing to the rubric LLM, to keep blindness:

- The model name / vendor (any `claude-`, `gpt-`, `gemini-`,
  `llama-` etc. tokens replaced with `<MODEL>`).
- The condition (`A`/`B`/`C`/`D`) — replaced with `<CONDITION>`.
- The slot id (`slot_A`, `slot_B`) — replaced with `<SLOT>`.

The harness records the redaction count in the run manifest's
per-cell row so a reviewer can audit.

## Anchors (one example each per score)

These ship with the prompt to calibrate the grader. They are
**not** filled into the prompt at runtime — they're authored
references kept here so a reviewer can audit the calibration.

### Score 2 (perfect)

Task: 0003-addiw-sign-ext (T4, hypothetical lift annotation).

```
expected_cause_pc:       0x10004
expected_cause_mnemonic: ADDIW
expected_explanation_summary:
  ADDIW computes the 32-bit add and sign-extends the result to 64
  bits. With bit 31 of the result set, x{rd} ends up
  0xFFFFFFFF80000000, not the bare 0x80000000 a naive 32-bit
  reading would predict.

OBSERVED.lift:
  cause_pc:       65540        # = 0x10004
  cause_mnemonic: ADDIW
  explanation:    ADDIW does its addition in 32 bits, then sign-
                  extends to 64. The high bit of the result is set,
                  so the sign extension fills with 1s, giving
                  0xFFFFFFFF80000000 in x10 — not 0x80000000.
```

Score 2: PC matches; the mechanism (32-bit add + sign-extend +
high-bit) is fully named. Different wording from the reference,
but substantively equivalent.

### Score 1 (partial)

```
OBSERVED.lift:
  cause_pc:       65540
  cause_mnemonic: ADDIW
  explanation:    The result of the addition isn't what you'd
                  expect because of how 32-bit ops work in RV64.
```

Score 1: PC matches but the explanation hand-waves; doesn't name
"sign-extend" or distinguish the high-bit case. `matched_pc=true`,
`matched_explanation=false`.

### Score 0 (incorrect)

```
OBSERVED.lift:
  cause_pc:       65536
  cause_mnemonic: LUI
  explanation:    LUI loaded the wrong immediate.
```

Score 0: cause_pc points at the LUI, which is *correct as far as
loading 0xFFFFFFFF80000000 into x5 goes* — but the question's
verdict (x10 == 0x80000000 unreachable) hinges on what ADDIW does,
not what LUI did. Wrong target. The explanation doesn't fix this.

## What the rubric output feeds into

Per `bench/riscv-btor2/manifest_schema.json`'s
`runs[].graded.lift_score`. T1/T2/T3 rows emit `null`; T4 rows
emit `0`/`1`/`2`. Aggregate per-cell tables (§5) report the mean
and per-class breakdown.
