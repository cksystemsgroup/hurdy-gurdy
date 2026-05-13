# Condition E — propose-and-check (v1.1.0 question compiler)

You have everything Condition B has — the `{{PAIR_ID}}` pair's tool
surface, its `SCHEMA.md`, the starter spec — **plus** the v1.1.0
question-compiler hook (SCHEMA.md §14): partial input bindings,
shadow-recorded concrete simulation, and `BranchPin` assumptions.

## What's new vs. condition B

- The pair's interpreter exposes a `simulate(spec, binding,
  max_steps, record_shadow)` tool that runs the source program on a
  concrete (or *partially* concrete) input binding and returns a
  trace. When `record_shadow=true`, the trace's
  `final_state.shadow` block exposes a per-step event log:

  - `branch_events`: list of
    `{step, pc, mnemonic, taken}` for every conditional branch.
  - `memory_events`: list of
    `{step, pc, mnemonic, addr, kind, free_dependent}` for every
    load/store. `kind ∈ {"load","store"}`.
  - `free_fields`: which binding cells were left `FREE`. The shadow
    interpreter concretizes free cells to `0` for the actual run; it
    just records that the resulting trace is one of many that would
    satisfy the partial binding (SCHEMA.md §14.8 property 1).

- `RiscvInputBinding` now accepts a `Free` sentinel in place of a
  concrete value. In JSON, a free cell is the literal string
  `"Free"` (the pair's loader maps it to `Free()`):

  ```json
  {
    "register_init": { "1": "Free", "10": 42 },
    "memory_init":   { "4096": "Free" },
    "havoc_per_step": [ { "1": "Free" } ]
  }
  ```

  A binding with `"Free"` cells is rejected by the plain (v1.0.0)
  interpreter — pass `record_shadow=true` to use it.

- `BranchPin` is a new assumption type (SCHEMA.md §14.3) that pins a
  conditional branch's direction at a specific step:

  ```json
  { "type": "BranchPin", "step": <int>, "taken": <bool>, "pc": <int> }
  ```

  A spec carrying `BranchPin` assumptions narrows the BMC search to
  paths whose first `k` branches match the pinned `(step, pc, taken)`
  triples. Pins constructed directly from a shadow trace's
  `branch_events` describe exactly the run you simulated; flipping a
  single pin's `taken` asks "same prefix, opposite branch at step
  k" — the classic concolic-style next-question.

- `CycleInvariant.dual_role: true` (SCHEMA.md §14.4) emits the
  invariant as **both** an assumption (downstream use) and a negated
  `bad` clause in the volatile layer (this question's falsification
  target). Use this to propose an invariant `P` and ask the solver
  "can `P` be falsified within bound?"

## Tools

The `simulate` tool is added to the condition-B surface:

- `simulate(spec, binding, max_steps, record_shadow)` — runs the
  source interpreter; returns `{steps, final_state, halted}`. When
  `record_shadow=true`, `final_state.shadow` carries the event log
  described above.

`compile`, `dispatch`, `lift`, `introspect` are unchanged from
condition B.

The pair's helper `trace_to_branch_pins` is **not** exposed as a
tool — building `BranchPin` objects from `branch_events` is a
mechanical mapping (`step`, `pc`, `taken` carry over verbatim) you
do in the spec JSON you pass to `compile`.

## The propose-and-check pattern

A condition-E session has more degrees of freedom than B. Three
patterns the question compiler enables:

1. **Pinned-prefix search.** Simulate with a concrete (or partial)
   binding to record a branch event log. Construct `BranchPin`
   assumptions from those events. Re-compile and dispatch to ask
   "within this exact path prefix, can the question's positive form
   still be satisfied?" Useful when the path that matters is
   obvious from the source but the BMC bound is too short to reach
   it without help.

2. **Flip-a-branch (next-question).** After a pinned-prefix run,
   flip one pin's `taken` and re-dispatch. The pair guarantees this
   is the *only* path-set change: every other pin is identical. Use
   this to localise a divergence to a specific step.

3. **Propose-an-invariant.** Add a `CycleInvariant` with
   `dual_role: true` to the spec. Compile + dispatch. If the
   volatile bad clause is `unreachable` within bound, the invariant
   survives this question (treat as `proved` only if you have an
   inductive argument; otherwise it's bounded evidence).

You may use any combination, or none (a pure condition-B-style run
is still allowed under E). The grading is on the final answer, not
the path.

## When the propose-check loop is the right move

- The question's natural form needs a longer bound than your engine
  budget allows, *and* the source makes the relevant path obvious.
  Pin the prefix; the solver only searches the suffix.

- Two paths reach the same observable but with different witness
  fingerprints, and you need to know which. Flip a branch pin to
  separate them.

- The question is "does property P hold along this path / under
  this invariant?" and you can write `P` as a `CycleInvariant`.

When in doubt, fall back to condition-B style — the propose-check
hooks are additive, not mandatory.

## Workflow guidance (non-binding)

A typical successful E session looks like:

1. Read `SCHEMA.md` §14 if you haven't already.
2. Translate the natural-language question into a `Property.expression`
   (and any `CycleInvariant`s). Same as condition B.
3. If the question benefits from path-narrowing: call `simulate`
   with `record_shadow=true` on a binding that exercises the path
   of interest. Read off `branch_events`.
4. Build `BranchPin` assumptions from the events (one per
   conditional branch in the path you care about) and place them in
   `spec.assumptions`.
5. Call `compile`, then `dispatch`. The BMC engine now searches
   only paths matching the pins (other paths are softly excluded by
   the `step_count != step OR pc != pin.pc OR …` lowering).
6. If `dispatch` still returns `unknown`, consider flipping one
   pin's `taken` and re-dispatching, or relaxing pins (drop the
   tail) and increasing `bound`.
7. If the question is invariant-shaped, propose a
   `CycleInvariant` with `dual_role: true`; the volatile bad
   clause is the falsification target.
8. Emit the final answer JSON.

## What this pair will not do (unchanged)

The schema's coverage gaps from condition B (no FP, atomics,
vector, privileged ISA, CSR-write effects, concurrency, memory
havoc) apply identically here. v1.1.0 extends what the LLM can
*ask*; it does not extend what the lowering can *encode*.

## Output contract

Unchanged from `_base.md`. Emit one JSON object inside a fenced
code block with `verdict`, `confidence`, `reason`, `witness`,
`lift`. The propose-check loop is internal to your reasoning; the
grader scores only the final answer.

## Starter spec

```json
{{STARTER_SPEC_JSON}}
```
