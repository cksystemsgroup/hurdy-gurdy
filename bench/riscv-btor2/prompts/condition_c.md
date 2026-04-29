# Condition C — solver-only

You have everything Condition A has, plus:

- A single tool, `solve` (see the `tools` parameter on this
  request), which runs **the same solver binaries** the
  `riscv-btor2` pair would use, but with **no translation,
  schema, annotation, or lift help**. You must hand-write the
  encoding yourself.

- `solve(engine, input_language, input_text, options)` returns:
  ```json
  {
    "verdict":  "sat" | "unsat" | "unknown" | "error",
    "stdout":   "<solver output, raw>",
    "stderr":   "<solver stderr>",
    "elapsed":  <seconds>
  }
  ```

  Allowed `(engine, input_language)` pairs:
  | engine | input_language | notes |
  |---|---|---|
  | `z3`    | `smt2`  | `(check-sat)` returns `sat` / `unsat`; `(get-model)` available with `(set-option :produce-models true)` |
  | `pono`  | `btor2` | runs `pono -e bmc --btor -k <bound> /dev/stdin`; `sat` ↔ reachable, `unsat` ↔ unreachable-within-bound |

  v1 limitation: `bitwuzla` and `cvc5` are not exposed under
  Condition C because the bench image ships their Python bindings
  only — no CLI binary in `PATH`. The harness side of Condition C
  shells the same z3 / pono binaries the pair uses internally; if
  you want to cross-check with bitwuzla or cvc5 hand-encodings,
  emit `unknown` with that as the reason.

  `options` may carry per-engine flags as a JSON object (e.g.,
  `{"bound": 20}`); the harness translates them. Engines and
  versions are pinned in the bench image; see `DOCKERHUB.md`.

- Same wall-clock budget as Conditions A and B.

You do **not** have:

- The `riscv-btor2` pair's `compile` / `dispatch` / `lift` /
  `introspect` tools.
- Any annotation, spec language, or starter `spec.json`.
- Any pre-built BTOR2 artifact.

## What this condition isolates

This is the condition that makes Condition B's improvement
defensible. If B beats A only because the pair gives the LLM access
to a solver, then C should also beat A by the same margin. If B
beats both A and C, the delta is attributable to the *pair* (its
schema, its translation, its lift), not to "you gave it a solver."
See BENCHMARKING.md §3 C.

## Workflow guidance (non-binding)

1. Choose an encoding strategy. SMT-LIB2 is the conventional choice
   for z3/bitwuzla/cvc5; pono consumes BTOR2 directly.
2. Hand-write a model of the relevant fragment of the program.
   Decide what to encode (memory, registers, the specific
   instruction sequence) and what to abstract.
3. Express the question as a satisfiability query.
4. Call `solve`.
5. If you get `unknown`, refine the encoding (different engine,
   higher bound, abstraction).
6. Translate the SMT result back to the witness fingerprint required
   by the output schema. Mapping `sat` → `reachable` and `unsat` →
   `unreachable` is *only* correct when your encoding faithfully
   models the program; if not, the verdict is `unknown`.

If you cannot produce a faithful encoding within the budget, emit
`unknown` rather than guessing. As in Condition A, the headline
penalty is wrong-with-high-confidence, not honest `unknown`.
