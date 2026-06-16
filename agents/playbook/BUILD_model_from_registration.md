# Playbook — build a model from a registration (referential)

You are an autonomous builder on branch `model/<id>`. Your contract is
`registry/models/<id>.yaml`. You make a registered formal model **real**:
vendor + pin the upstream model, wire it behind the **Oracle protocol**, realize
the capabilities the registration targets, and get the **model gate** to certify
them.

Unlike a pair builder, you are **referential**: you *have* the model, you work
openly, and your job is *faithfulness to the formal semantics* — not
independence. The Oracle you ship becomes the reference that sandboxed pair
builders are validated against.

## The contract (`registry/models/<id>.yaml`)

- `id`, `language` (the ISA/language this model gives semantics to)
- `source`: pinned upstream — `model_source` (the vendored definition) **and**
  `emulator_release` (the executable binary), as separate axes
- `oracle: { kind: sail | external }`
- `target_capabilities`: a subset of `[executable, proof_export, machine_gen]`
- `conformance_suite`: how the oracle is validated against upstream
- `agent: { playbook, budget }`

## Hard rules (the model gate enforces these; violating them fails certification)

1. **Pin everything.** `model_source` and `emulator_release` are exact; the gate
   asserts the vendored artifact matches. A floating/unverifiable version fails.
2. **Declare only capabilities you can BACK.** Claiming `proof_export` or
   `machine_gen` you cannot actually produce is the cardinal sin: a downstream
   pair's fidelity ceiling is computed from your *certified* capabilities, so an
   overclaim is a lie that propagates. The gate refuses to certify it.
3. **Do not edit pinned registration fields** (`id`, `language`,
   `target_capabilities`). They are read-only to you.
4. **The Oracle is deterministic and must not leak.** It is the reference for
   *sandboxed* pair agents — keep it in the group/model tree, never in a pair
   branch.

## The artifact: an Oracle

Implement `gurdy/core/oracle.py`'s protocol for your model. Capability → method:

- **executable** — `run(program, binding) -> projection`. Required for *every*
  model (shell to the pinned emulator binary, or drive the upstream interpreter).
- **proof_export** — `reference_export()`. A transcribable/mechanized reference
  (e.g. Sail → theorem-prover defs, or a `reference_<isa>.py` transcription that
  you cross-validate against `run`).
- **machine_gen** — `machine_model()` → a verified BTOR2 machine. Sail-class
  models only; reuse `tools/sail_btor2_machine` (generate + verify).

## Loop

1. Read the registration. Vendor the upstream at the pinned `source`; record
   provenance.
2. Implement the Oracle for exactly your `target_capabilities`:
   - *executable*: wire the emulator/interpreter behind `run`; validate against
     `conformance_suite`.
   - *proof_export* (if targeted): produce the mechanized reference and
     cross-validate it against `run`.
   - *machine_gen* (if targeted): generate + verify the BTOR2 machine —
     per-instruction QF_BV lemmas + the fetch/decode/pc harness lemma vs the
     reference. Start with the base integer slice; **state scope honestly**.
3. Self-test: `gurdy model <id>` runs the model gate locally. Feedback, not the
   verdict.
4. Open a PR `model/<id> -> main`. The model gate certifies your capability set;
   that certified set is exactly what bounds every pair that references you.

## Scope guidance

Realize the smallest useful capability first (`executable`), then `proof_export`,
then `machine_gen`. **A model that only runs is valid** — it just caps its pairs
at F2 and says so. Grow `machine_gen` scope (more instructions, then memory /
control flow) incrementally; each widening is a re-verification event.

## You are the reference — and you validate it too

A lemma that *cannot* be discharged, or a conformance divergence, is a signal:
your wiring is wrong, or (rarely) the upstream model is. Minimize to a single
instruction/program, check the spec, and file upstream if the model is the
suspect (after subtracting IDF via `semantics/<group>/idf_allowlist.yaml`).

## What "done" means

`gurdy model <id>` certifies the model at its `target_capabilities` with **no
overclaim**, the `source` pins match the vendored artifact, and the conformance
suite passes. Pairs may then register `source_semantics: { model: <id> }`.
