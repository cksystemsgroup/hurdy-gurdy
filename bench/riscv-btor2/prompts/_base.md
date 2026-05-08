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

### Verdict-vs-question polarity (read carefully)

The verdict labels describe the **bad expression** in the spec --
which is true when the property is violated -- not the user's
question directly. SCHEMA.md §8 states the convention; the
mapping you must internalise is:

- The user's question's positive form (e.g., "Can x10 hold the
  value 12?") becomes the **bad expression** (`eq(reg(10), 12)`).
- `reachable` ⇔ bad CAN be satisfied ⇔ the answer to the user's
  positive form is **yes**.
- `unreachable` and `proved` ⇔ bad CANNOT be satisfied (bounded
  vs. inductive respectively) ⇔ the answer is **no**.

A common failure mode: the program deterministically computes
x10 = 12, and you reason "x10 is *always* 12, that's a proof,
so the verdict is `proved`." That is **wrong**. "x10 is always
12" means bad (`x10 = 12`) is *always satisfied*, which makes
the bad expression **reachable**. `proved` would mean
"x10 ≠ 12 ever," which contradicts the program. Same logic
applies if a solver tells you "this property holds": that
phrase is referring to the bad expression's negation; the
verdict you emit must be `reachable` for the user's positive
form, not `proved`.

Asymmetric matcher rule: `proved` is accepted in place of
`unreachable` (it's a stronger no-answer). It is **not**
accepted in place of `reachable` (which is the opposite
direction).

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

### `final_regs` -- err on the side of inclusion

The matcher checks every register the *task* pins; it does NOT
check that you only list the "interesting" ones. Extra registers
are ignored, missing registers are scored as failures. You do not
know which registers the task pins, so the safe rule is:
**list every register your reasoning touched, plus every register
that appears in the source assembly with a non-default value at
any step**. In particular:

- If the program writes `addi xN, ..., ...` for any N, list xN.
- If the program reads xN and the read value matters, list xN.
- If a register's expected value is 0 or some other "obvious"
  number, **still list it**. The matcher cannot distinguish "I
  forgot" from "I think this is unconstrained."
- It is fine to over-include up to all 32 GPRs; only x0 (always 0)
  is safe to omit.

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
