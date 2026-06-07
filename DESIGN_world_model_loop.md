# Design note — hurdy-gurdy as a verified world model

> **Status: design note, exploratory.** This document argues a *usage
> pattern*, not a new framework feature. Everything it describes is
> composed from the existing translator- and interpreter-layer tools
> (`README.md` "The LLM-facing surface"); hurdy-gurdy gains no new
> responsibility. The pattern lives entirely in the LLM's logic, where
> all reasoning belongs.

## The question

Can hurdy-gurdy play the role a *world model* plays in a model-based
agent — the component that, given a state and a candidate action,
predicts the outcome — so that an agent can run the loop:

```text
    propose action → predict outcome → validate prediction → act → repeat
```

with hurdy-gurdy supplying the *validate* step (and, optionally, the
*predict* step) deterministically?

Short answer: **yes, and unusually well — but only for worlds that are
instances of a supported pair's source language.** Within that scope
hurdy-gurdy is a *stronger* world model than the learned kind (it is
exact, it can quantify over all inputs rather than roll out one
trajectory, and it audits its own faithfulness); outside that scope it
does not apply, because it has no model of dynamics it cannot formally
describe and no sensor on a real environment that drifts from its model.

## The structural fit

The commuting square already contains a forward model and a checker. Two
of the five interpreter-layer tools *are* a world model:

| World-model concept            | hurdy-gurdy realization                              |
|--------------------------------|-----------------------------------------------------|
| state                          | the source instance + an `InputBinding`             |
| action                         | inputs / a `BranchPin` / a code edit (see below)    |
| transition `T(state, action)`  | the source interpreter, via `simulate(...)`         |
| outcome / observation          | the returned `SourceTrace` (projected observables)  |
| reward / goal predicate        | the spec's properties, via `check(...)`             |
| "does this hold for *all* actions?" | `compile` → `dispatch` → `lift` (a proof/refutation) |
| "did the model lie?"           | `cross_check(...)` / `replay(...)`                  |

The agent's *prediction* is the LLM's conjecture about what the outcome
or its goal-predicate will be; the *validation* is hurdy-gurdy returning
the deterministic truth.

## The loop, mapped to tool calls

The signatures below are the real ones
(`gurdy/core/tools/*`):

- `compile_spec(spec, *, source_payload=None) -> CompiledArtifact`
- `simulate(spec, binding, max_steps, *, source_payload=None, record_shadow=False) -> SourceTrace`
- `check(spec, binding, max_steps, *, source_payload=None) -> SpecEvaluation`
- `dispatch(artifact, directive) -> RawSolverResult`
- `lift(artifact, raw) -> facts`
- `replay(artifact, raw) -> JoinedTrace`
- `cross_check(spec, source_binding, reasoning_binding, max_steps, *, source_payload=None, artifact=None) -> CrossCheckReport`

One iteration:

1. **State.** The LLM holds the current source instance and an
   `InputBinding` describing the state (and the prefix of actions taken
   so far).
2. **Propose action.** The LLM picks a candidate action and encodes it —
   as concrete input cells, a `BranchPin` that flips a decision at step
   *k*, or (for code-acting agents) an edit to the source instance.
3. **Predict.** The LLM states what it expects the outcome / goal
   predicate to be. Optionally it makes the prediction *exact* by running
   `simulate(spec, binding, max_steps)` itself — a single deterministic
   rollout.
4. **Validate.** Two strengths are available, and the LLM chooses:
   - *Concrete:* `check(spec, binding, max_steps)` — does this specific
     action produce the predicted, acceptable outcome on this one
     trajectory? Cheap, no solver.
   - *Universal:* `compile_spec(spec)` → `dispatch(artifact,
     spec.analysis)` → `lift(...)` — is the bad outcome reachable for
     *any* input, or the good property guaranteed for *all* inputs? A
     proof/refutation over the whole action-or-input space. On
     refutation, `replay(artifact, raw)` returns the counterexample
     trajectory grounded at the source level — exactly the feedback the
     LLM needs to revise the action.
   - *Faithfulness (optional but cheap insurance):* `cross_check(...)`
     confirms the world model didn't lie — the translated and
     interpreted views agree on the projected observables.
5. **Act.** The LLM commits only to an action whose prediction validated.
6. **Observe & repeat.** Fold the outcome into the next `InputBinding`
   and loop.

Action-tree search is native, not bolted on: the v1.1.0 "same prefix,
flip at step *k*" machinery (`BranchPin` + partial bindings + the
`record_shadow` interpreter mode / volatile layer, SCHEMA.md §14) is
precisely branching from a shared state prefix to explore alternative
actions. MCTS-style rollout over actions falls out of the same question
compiler that drives whole-program BMC.

## Why it is a *stronger* world model than the learned kind

- **Exact, not approximate.** Predictions are correct by construction
  within the formal semantics — no model bias, no hallucinated dynamics.
  This is model-predictive control with a *known* model, not "learn the
  dynamics from observations."
- **It quantifies; it does not merely roll out.** A learned world model
  predicts one trajectory for one action. The `dispatch` path answers
  "for *all* inputs / *any* input" — a guarantee a rollout cannot give.
  An agent can validate not just "this action is fine *here*" but "this
  action is fine *for every input it could face*."
- **Self-auditing.** `cross_check` verifies the model is faithful to the
  source semantics. A world model that checks itself before the agent
  trusts it.
- **Source-grounded counterexamples.** A refuted prediction comes back
  as a concrete, replayable trajectory at source level — actionable
  feedback, not an opaque "no."

## Where it is *narrower* — the honest boundaries

The thesis holds **only when the world is an instance of a supported
pair's source language with a deterministic interpreter** (the
interpreter-layer-gated pairs; `PAIRING.md` §11). Three consequences the
agent designer must respect:

- **The world must be formalizable as computation.** hurdy-gurdy models
  programs (RISC-V / C / Wasm), reaction networks (CRN), molecules
  (SMILES) — not an arbitrary physical environment. You cannot model
  dynamics you cannot write down. Learned world models earn their keep
  precisely where dynamics are *unknown*; that is the complement of
  hurdy-gurdy's strength, not a competitor to it.
- **`simulate` is the model, not the environment.** Closing the loop
  against *reality* means observing the real outcome and correcting model
  drift. hurdy-gurdy has no sensor on a world that diverges from its
  source instance and cannot detect when the instance stops describing
  the environment. The loop is sound only insofar as the source instance
  faithfully models the world.
- **Validation inherits the usual limits.** Decidability bounds the
  universal path (`unknown` is a legitimate verdict); the action and its
  outcome must be expressible in the pair's spec vocabulary; and a
  prediction validated *through a chain* (e.g. `c-riscv` → `riscv-btor2`)
  inherits the weaker `reproducible` trust tier of the compile hop,
  re-established by the CBMC differential — not the `transparent` tier of
  a pure pair.

## The sweet spot

The model-error-free case is when **the world *is* the computation** —
then `simulate` *is* the environment and the second boundary above
vanishes:

- **a code-acting agent** (program repair / synthesis): action = a code
  edit, world = the program. Predict the edit's effect, *prove* it
  preserves the property over all inputs, commit. The loop closes with
  zero model error.
- **a smart-contract agent** (the EVM pair in the taxonomy, not yet
  pair-complete): action = a transaction, world = chain state — a
  near-perfect instance.
- **a chemistry agent** (CRN / SMILES): action = a reaction or
  perturbation; validate the reachable states.

For hybrid or physical settings, the most useful framing is
**hurdy-gurdy as a verified shield rather than the predictor**: let the
LLM (or a learned model) predict cheaply and generally, and use
hurdy-gurdy to validate the *formalizable subset* of an action's
consequences; only validated actions execute. That is "shielding" in
safe-RL terms — a soundness gate on an otherwise-approximate world model.

## Worked example — a code-acting agent on the `C → RV64 → BTOR2` chain

The world is a C function the agent is editing; the goal is "no signed
division by zero on any input." This reuses the existing chain
(`gurdy/chains/c_to_btor2.py`) and corpus shape (cf.
`bench/riscv-btor2/corpus/0125-c-sdiv-by-zero`).

1. **State.** Current C source instance; spec property = "trap state
   unreachable," analysis directive = bounded reachability with an
   inductive fallback.
2. **Propose action.** The agent proposes an edit: add a guard
   `if (d == 0) return 0;` before the division.
3. **Predict.** "After this edit, the trap is unreachable for all
   inputs."
4. **Validate (universal).**
   - `compile_spec(spec)` lowers the edited C instance through the chain
     to a layered BTOR2 artifact (deterministically — same edit, same
     bytes).
   - `dispatch(artifact, spec.analysis)` runs the engine.
   - Verdict `proved`/`unreachable` → prediction validated. Verdict
     `reachable` → `replay(artifact, raw)` hands back the concrete input
     that still divides by zero, grounded as `BTOR2 nid → ELF pc → C
     file:line`; the agent revises the edit and loops.
5. **Faithfulness (optional).** `cross_check(spec, src_binding,
   reas_binding, max_steps)` on a sample input confirms the chain didn't
   misrepresent the program before the agent trusts the `proved` verdict.
6. **Act.** Commit the edit only on a validated prediction.
7. **Repeat** for the next edit.

The instructive subtlety — already demonstrated by the corpus wedge
tasks (`0125`, `0261`, `0300`) — is that the prediction is validated
about the *actual lowered instance* (the RV64 behavior), which can differ
from C-source intuition. A C-level tool may false-positive where the
RV64 semantics are defined; the agent acting on RV64 wants the verdict
about the world it will actually run in. That is exactly what this loop
delivers.

## Relationship to the rest of the project

- This pattern needs **no schema change and no new tool.** It is a
  consumer of the existing surface.
- It does, however, lean on the **interpreter layer** (`simulate`,
  `check`, `cross_check`, `replay`), so it is only available for pairs
  that declare deterministic source and reasoning interpreters
  (`PAIRING.md` §11). Today the full set works on `riscv-btor2`.
  `aarch64-btor2` has its `projection.py` landed, so the `cross_check`
  (faithfulness) leg works there too — source simulator vs. BTOR2
  interpreter agree step-for-step; the `check` leg still awaits its
  `predicate_evaluator`, the remaining aarch64 parity item (`PLAN.md`
  Stage 7.E).
- The faithfulness leg (`cross_check`) is exactly the alignment contract
  the **P1 alignment oracle** operationalizes corpus-wide
  (`bench/riscv-btor2/oracle_align.py`). Hardening P1 directly hardens
  the "did the model lie?" guarantee this loop depends on.

## Open questions deferred until evidence

- Whether a thin convenience wrapper (`predict_and_validate(spec,
  action)`) is worth adding to the bench harness, or whether composing
  the primitives in the LLM's logic is cleaner (current bias: compose;
  no wrapper until a second consumer wants it).
- Whether the universal path's `unknown` verdicts are frequent enough in
  an acting loop to warrant a standard "fall back to concrete `check` on
  the sampled action" policy, or whether that, too, is the LLM's call.
- For the shielding use, how the LLM should partition an action's
  consequences into "formalizable (validate here)" vs. "not (handle
  elsewhere)" — likely pair- and task-specific.
