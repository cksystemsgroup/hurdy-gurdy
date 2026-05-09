# `riscv-btor2` rubric

Pair-specific instantiation of BENCHMARKING.md §6 ("Oracle and
scoring") and §9.7 ("Grading rubric"). Defines the contract that
turns a transcript from condition A/B/C/D into a graded outcome.

## What gets graded

A transcript carries a final answer of the form:

```json
{
  "verdict": "reachable" | "unreachable" | "proved" | "unknown",
  "confidence": 0.87,
  "witness":   { ... } | null,
  "lift":      { ... } | null,
  "reason":    "..."
}
```

`witness` is required when `verdict == "reachable"`; `lift` is
required for T4 tasks (BENCHMARKING.md §4.2). `confidence` is a
self-reported probability in [0, 1]; calibration is reported per §5.

## Three grading paths

| Path | Trigger | What it checks | Mechanism |
|---|---|---|---|
| **Verdict-only** | T1/T2/T3 with `expected.verdict ∈ {unreachable, proved, unknown}` | observed verdict == expected verdict | `matcher.py` (deterministic) |
| **Witness fingerprint** | Any task with `expected.verdict == "reachable"` | verdict matches AND every field in `[witness]` matches the observed witness | `matcher.py` (deterministic) |
| **Lift quality** | `task.difficulty == "T4"` | observed lift identifies the source-level cause | rubric LLM, blind to condition+model, with manual sample (§6) |

The verdict and witness checks are *deterministic*. Only the lift
quality check uses an LLM grader, and a ≥ 10% manual sample with
inter-rater agreement is reported per §6.

## Files

```
rubric/
├── README.md             # this file
├── witness_schema.md     # contract for task.toml [witness] +
│                         #   the witness JSON shape the LLM emits
├── lift_schema.md        # T4 only: task.toml [lift] +
│                         #   the lift JSON shape the LLM emits
├── rubric_prompt.md      # the §9.7 rubric LLM's system + user
│                         #   prompts, with anchor examples for 0/1/2
├── manual_grading.md     # human-grader instructions for the ≥10%
│                         #   sample called out by §6
├── matcher.py            # deterministic verdict + witness checker;
│                         #   self-tests against the seed tasks
└── rubric_llm.py         # T4 lift grading: builds the rubric prompt
                          #   from rubric_prompt.md, calls MODELS["rubric"],
                          #   parses the 0/1/2 score. Used by harness.grade().
```

## Lifecycle

1. **Pre-registration (§7).** This README, `witness_schema.md`,
   `matcher.py`, and the `task.toml [witness]` tables for every task
   are committed in a tagged commit *before* condition B/C runs.
2. **Run.** Condition B/C harness collects per-task transcripts,
   each producing the JSON above.
3. **Auto-grade.** `matcher.py` runs over every transcript; emits
   per-task `{ verdict_correct, witness_match, … }`.
4. **Rubric LLM.** For T4 tasks, the rubric LLM scores `lift` 0/1/2.
   Prompt and model are pinned alongside the corpus tag.
5. **Manual sample.** A random ≥ 10% of transcripts is graded by
   hand. Disagreements with the rubric LLM are resolved by a second
   reviewer; resolution rate is part of the §8.5 artifact bundle.
6. **Aggregate.** Per-cell tables (§5).

## What this rubric deliberately does not do

- **Grade the trace shape** — there are many witness traces of
  different lengths that satisfy the same fingerprint. The rubric
  checks the *fingerprint*, not the path.
- **Reward shorter witnesses** — a verbose-but-correct witness scores
  the same as a tight one. Cost-to-answer (§5) is reported separately.
- **Penalise the LLM for choosing a different valid engine.** The
  task's `spec.json` recommends an engine; the LLM is free to switch
  under condition B as long as the verdict and witness stand.
- **Cross-check the witness against the BTOR2 trace** — the rubric
  trusts the lifted observation. Cross-checking the lift output
  against the raw solver payload is a `lift`-correctness concern, not
  a grading concern, and lives in the framework's tests.
