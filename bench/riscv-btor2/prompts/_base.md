# Shared base — concatenated into every condition's prompt

You are answering a single yes/no/unknown question about an RV64IMC
program. Your task is `{{TASK_ID}}`.

## Verdict vocabulary

You must commit to exactly one of:

- **`reachable`** — there is a finite execution that satisfies the
  question's positive form (e.g., "the bad state is reached").
- **`unreachable`** — within the analysis bound the question's
  positive form is *not* satisfied. This is a bounded claim; it says
  nothing about behaviour past the bound.
- **`proved`** — the question is settled at all depths (an inductive
  proof, not a bounded one). Only emit this if you can produce or
  identify the inductive invariant.
- **`unknown`** — you cannot decide. Emit this rather than guessing.
  Stating `unknown` with high confidence is preferred over a wrong
  high-confidence verdict.

## Required output

Reason aloud as much as you want, then end your reply with **one**
JSON object inside a fenced code block. The harness extracts the
**last** ` ```json ... ``` ` block in your reply. Schema:

```json
{
  "verdict":    "reachable" | "unreachable" | "proved" | "unknown",
  "confidence": <number in [0, 1]>,
  "reason":     "≤ 2 sentences explaining the answer",
  "witness":    <object | null>,
  "lift":       <object | null>
}
```

`witness` is **required** when `verdict == "reachable"` and **must
be `null` otherwise**. Schema for `witness`:

```json
{
  "bad_pc":       <integer; the PC at the step where the question
                   is satisfied>,
  "anchor_step":  <integer cycle number, 0-indexed from entry>,
  "final_regs":   { "<reg_number_as_string>": <integer>, ... },
  "executed_pcs": [ <integer>, ... ]
}
```

Register keys are integers 0..31 written as JSON strings (e.g.,
`"10"` for x10). Values are uint64; you may write them as decimal
integers or `"0x..."` strings.

`lift` is required only for tasks tagged T4 in `task.toml`; otherwise
emit `null`. The grading rubric for `lift` is in
`bench/riscv-btor2/rubric/`.

## Honesty

- If you are unsure, set `confidence` low and explain. Wrong-with-
  high-confidence ("hallucination") is the headline metric the
  benchmark tracks (BENCHMARKING.md §5).
- Do not fabricate witness fields. A `null` witness with a correct
  `unknown` verdict scores higher than an invented witness with a
  guessed `reachable`.
- The grader is deterministic on `verdict` and on the `witness`
  fingerprint listed in `task.toml`. It does not reward verbose
  prose, hand-waved invariants, or padding.

## The question

{{QUESTION_TEXT}}

## The program

Source (`source.S`):

```asm
{{SOURCE_S}}
```

Disassembled instructions (`riscv64-unknown-elf-objdump -d
source.elf`):

```
{{DISASSEMBLY}}
```
