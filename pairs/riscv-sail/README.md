# Pair — `riscv-sail`  ·  RISC-V → SAIL

*Status: **partial** — the ALU + control-flow front is built (`gurdy/pairs/riscv_sail/`):
it lifts a RISC-V program into the Sail model's representation (the decoded
instruction stream + init/property), which `sail-btor2` lowers via the
Sail-derived semantics. Composed as `riscv-sail → sail-btor2 → btor2-smtlib`,
it forms the **indirect** RISC-V→BTOR2 route the path-grader cross-checks
against the direct `riscv-btor2` (branch agreement holds today). Wiring the
real `sail_riscv_sim` model and widening past the ALU slice are the named
pending increments.*

Lift a RISC-V program into its execution under the **official RISC-V model
written in Sail**. Paired with `sail-btor2`, this is the **indirect** arm of
the RISC-V→BTOR2 branch: it routes RISC-V semantics through a *second,
independent* artifact (the Sail model) so the result can be cross-checked
against the direct `riscv-btor2` translator ([`PATHS.md`](../../PATHS.md)
§4–5). Its whole reason to exist is that corroboration.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source language.** RISC-V —
  [`languages/riscv`](../../languages/riscv/README.md).
- **Target language.** Sail —
  [`languages/sail`](../../languages/sail/README.md).
- **Translator `T`.** Built **from the RISC-V model in Sail**: take a RISC-V
  image (+ scope) to the corresponding Sail object — the pinned RISC-V Sail
  model applied to that image — that the Sail interpreter then executes.
  Deterministic; pin the Sail model and version. State exactly what the Sail
  object is and how the image is embedded.
- **Source interpreter.** The **shared** RISC-V interpreter
  ([`languages/riscv`](../../languages/riscv/README.md)) — reused.
- **Target interpreter.** The **shared** Sail interpreter
  ([`languages/sail`](../../languages/sail/README.md)) — reused; if this is
  the first Sail pair built, it **contributes** that interpreter (likely by
  driving the Sail-generated executable model deterministically).
- **Target-to-source interpreter `L`.** Carries a Sail-model behavior back to
  a RISC-V behavior — projecting the Sail architectural state onto the RISC-V
  observables. Because both ends describe the same ISA, this is largely a
  re-projection. Pair-owned.

## Translator detail

The translator is thin: it is the *binding* of a program image into the
pinned Sail RISC-V model. The semantics live in the model, not in this
code. Record the model identity and version; migrating it is a versioned
change that re-validates the square and the branch.

## Projection `π`

The RISC-V observables — post-step program counter, general-purpose
registers, halt/trap — read out of the Sail model's architectural state.
`π` **must match** the RISC-V interpreter's and `riscv-btor2`'s projections
so the branch cross-check at BTOR2 compares like with like
([`languages/sail`](../../languages/sail/README.md)).

## Fidelity target + evidence

- **Declared: `checked`.** Evidence: the commuting-square oracle walks the
  shared RISC-V interpreter's trace against `L(I_sail(T(p)))` under `π`. In
  effect this also validates the shared RISC-V interpreter against the
  official Sail model — a strong independent check.

## Soundness story

The square is checked directly: the RISC-V interpreter and the Sail model,
both executing the same program, must agree on `π` step-for-step. Carried
onward by `sail-btor2`, this route's BTOR2 output is then cross-checked
against the direct route — the branch is the higher-order soundness story
([`PAIRING.md`](../../PAIRING.md) §6; [`PATHS.md`](../../PATHS.md) §4).

## Notes for the implementing agent

- Reuse the shared RISC-V interpreter; contribute the shared Sail
  interpreter to [`languages/sail`](../../languages/sail/README.md) if it
  does not yet exist — prefer driving the Sail-generated model over
  re-implementing it, keeping it deterministic.
- Keep `π` projection-compatible with `riscv-btor2`; the branch is the
  point.
