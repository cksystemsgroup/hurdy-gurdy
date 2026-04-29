# Condition B — pair-equipped

You have everything Condition A has, plus:

- The `{{PAIR_ID}}` pair's tool surface (see the `tools` parameter
  on this request). The four tools are:
  - `compile(spec_json)` — translates a `RiscvBtor2Spec` to BTOR2,
    returning a content-addressed `artifact_id` plus diagnostics.
  - `dispatch(artifact_id, directive)` — runs the named solver
    against the artifact. `directive` is an `AnalysisDirective`
    (`engine`, `bound`, `timeout`, `havoc_registers`, `extra_options`).
    Returns a `RawSolverResult` (`verdict`, `elapsed`, `payload`,
    `reason`).
  - `lift(artifact_id, raw_result)` — translates a raw solver
    output back to source-level steps and (for `proved` verdicts)
    a lifted invariant. Returns a `LiftedResult` whose `trace`
    field has the per-cycle (pc, mnemonic, regs) you need to fill
    in the witness JSON.
  - `introspect(spec_json)` — runs the spec validator without
    compiling. Use this when you suspect your spec is malformed.

- The pair's schema document at `{{SCHEMA_URL}}`. Read it for the
  state-variable naming, lowering rules, and verdict semantics.

- A starter spec.json (below). The `binary.path`, `scope`, and
  default `analysis` are filled in; the **`property` and any
  task-specific assumptions are left for you to fill in** based on
  the question above. Do not invent fields the pair does not declare;
  if a question shape is not encodable in this spec language, emit
  `unknown` with reason `"coverage gap"`.

```json
{{STARTER_SPEC_JSON}}
```

## Workflow guidance (non-binding)

A typical successful B-condition session looks like:

1. Read `SCHEMA.md` if you have not already.
2. Translate the natural-language question into a `Property.expression`
   (and any `CycleInvariant`s).
3. Call `introspect` to confirm the spec is well-formed.
4. Call `compile` to get an `artifact_id`.
5. Call `dispatch` with the default engine. If the result is
   `unknown` due to bound exhaustion or timeout, increase `bound`
   and re-dispatch; if it's `unknown` due to engine incompleteness,
   try a different engine.
6. If the result is `reachable`, call `lift` to get the source-level
   trace and read off the witness fingerprint (bad_pc, anchor cycle,
   register values).
7. Emit the final answer JSON.

You may deviate from this; the grading is on the final answer, not
the path.

## What this pair will not do

The schema deliberately excludes floating point, atomics, vector,
privileged ISA, CSR-write effects, concurrency, and memory havoc
(see `SCHEMA.md` §13). If the question requires any of these, the
correct verdict is `unknown` with reason `"coverage gap"`.
