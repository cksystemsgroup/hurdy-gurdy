# Condition D — source-level verifier baseline (CBMC)

You have everything Condition A has, plus:

- A single tool, `cbmc` (see the `tools` parameter on this
  request), which runs the same CBMC binary the bench's
  `condition_d_reference.py` uses. CBMC consumes **C source**
  directly (not RV64 binaries), with no help from the
  `riscv-btor2` pair (no schema, no compile, no lift).

- `cbmc(c_source, options)` returns:
  ```json
  {
    "verdict":  "successful" | "failed" | "inconclusive" | "unknown" | "error",
    "stdout":   "<cbmc raw output>",
    "stderr":   "<cbmc stderr>",
    "elapsed":  <seconds>
  }
  ```

  CBMC's verdict semantics (different from the bench's!):
  - `successful` — no property violation found within the unwind.
  - `failed`     — at least one property fails (a check, an
                   assertion, or an arithmetic-overflow trap).
  - `inconclusive` / `unknown` — CBMC couldn't decide.
  - `error`      — CBMC binary missing or crashed.

  **Mapping to the bench's verdict vocabulary is your job.** The
  bench asks "is the trap function reachable?"; CBMC checks
  whether assertions in your source can fail. The natural
  rewrite: replace `if (cond) trap();` calls with
  `__CPROVER_assert(!(cond), "trap reachable");`, then
  - CBMC `successful` ⇒ trap not reachable ⇒ bench
    `unreachable`.
  - CBMC `failed`     ⇒ trap reachable     ⇒ bench
    `reachable`.
  - CBMC `inconclusive`/`unknown` ⇒ bench `unknown`.

  Beware: CBMC also flags **C-standard undefined behaviour**
  (signed overflow, divide-by-zero, shift-amount-out-of-range,
  ...) as failed properties. If the bench's question turns on
  one of these, CBMC may emit `failed` for the UB check while
  the rewritten `__CPROVER_assert` itself succeeds — which
  means CBMC says "this C program has UB" rather than "the
  trap is reachable." Inspect `stdout` to distinguish: look for
  which property failed (`overflow`, `division-by-zero`,
  `shift_distance`, `assertion`, ...).

- Same wall-clock budget as Conditions A and B.

You do **not** have:

- The `riscv-btor2` pair's `compile` / `dispatch` / `lift` /
  `introspect` tools.
- Any annotation, spec language, or starter `spec.json`.
- Condition C's `solve` tool.

## What this condition isolates

Condition D is the BENCHMARKING.md §3.D source-level baseline.
It answers: "is the pair (B) better than reasoning from the C
source through a generic source-level verifier?" The strongest
case for the pair is the **lowering-sensitive subset**: tasks
where the C source's standard semantics (undefined behaviour,
implementation-defined behaviour, language-level
under-specification) hide what the RV64 lowering makes explicit.
On those tasks CBMC tends to say "I cannot certify this — there's
UB" while the bench's pair says "the actual RV64 semantics are
well-defined and the property holds."

The bench's offline `condition_d_reference.py` already
demonstrates this: 5 of the 25 v0.4 C tasks (the lowering-
sensitive UB cases) FAIL CBMC despite holding on RV64. Your
sweep replicates that measurement with an LLM in the loop.

## The C source

`{{TASK_ID}}` is a bare-metal C program. Its source:

```c
{{SOURCE_C}}
```

The bench's question (the *positive* form, which becomes the
property under test) is:

> {{QUESTION_TEXT}}

The trap pattern: `if (cond) trap();` calls a separate `trap`
function whose only effect is to halt. The bench measures
"can this trap function be reached from `_start`?" An
`unreachable` verdict means the assertion holds; a `reachable`
verdict means the assertion fires.

## Workflow guidance (non-binding)

1. Read the C source. Decide whether the question can be
   answered by direct reasoning or whether you need CBMC.
2. If invoking CBMC: rewrite the source — at minimum, rename
   `_start` → `main` and convert each `if (cond) trap();` to
   `__CPROVER_assert(!(cond), "trap reachable");`. Drop the
   `trap` function definition (no callers remain). Inline asm
   (`__asm__ volatile ("ebreak");`) is silently ignored by
   CBMC.
3. Call `cbmc(c_source=<rewritten source>, options={"unwind": <n>})`.
   Pick `unwind` large enough to cover every loop. The
   bench-side reference uses 100 by default.
4. Map CBMC's verdict to the bench vocabulary (see above). If
   CBMC reports `failed`, inspect `stdout` to see *which*
   property failed: an assertion failure → trap is genuinely
   reachable; a UB check (`overflow`, `division-by-zero`,
   `shift_distance`, ...) → CBMC found UB but the bench may
   still say `unreachable` if the RV64 lowering defines the
   behaviour.
5. If CBMC's verdict is `failed` due to a UB check, decide
   whether to commit to the literal CBMC mapping (`reachable`)
   or to reason that the RV64 lowering would handle the UB
   well-defined-ly (and answer `unreachable`). Either is
   defensible; the choice is graded as part of the
   condition-D measurement.

If you cannot produce a faithful encoding within the budget,
emit `unknown` rather than guessing. As in Condition A, the
headline penalty is wrong-with-high-confidence, not honest
`unknown`.
