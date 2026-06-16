# Pair — `aarch64-sail`  ·  AArch64 → SAIL

*Status: **registered** (not yet built). Motivated by the research in
[`REGISTRY.md`](../../REGISTRY.md) — Arm has an official Sail model.*

Lift an AArch64 program into its execution under the **ARM model written in
Sail** (`sail-arm`, auto-translated from Arm's ASL and validated against
Arm's Architecture Compliance Kit). Paired with `sail-btor2`, this is the
**indirect** arm of an AArch64→BTOR2 branch, to be cross-checked against the
direct `aarch64-btor2` translator — the same fidelity-raising structure
RISC-V has via `riscv-sail` ([`PATHS.md`](../../PATHS.md) §4–5). Its reason
to exist is that corroboration: two independent encodings of A64 semantics
meeting at BTOR2.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** AArch64 — [`languages/aarch64`](../../languages/aarch64/README.md).
- **Target.** Sail — [`languages/sail`](../../languages/sail/README.md).
- **Translator `T`.** Built **from the ARM model in Sail**: bind an AArch64
  image (+ scope) into the pinned `sail-arm` model — the Sail object the
  shared Sail interpreter then executes. The translator is thin; the
  semantics live in the model. Deterministic; pin the Sail ARM model and
  version.
- **Source interpreter.** The **shared** AArch64 interpreter
  ([`languages/aarch64`](../../languages/aarch64/README.md)) — reused.
- **Target interpreter.** The **shared** Sail interpreter
  ([`languages/sail`](../../languages/sail/README.md)) — reused; it runs
  whichever Sail object it is given (here the ARM model). Contributed by
  whichever Sail pair lands first.
- **Target-to-source interpreter `L`.** Carries a Sail-model behavior back
  to an AArch64 behavior by re-projecting the Sail architectural state onto
  the AArch64 observables. Because both ends describe the same ISA, this is
  largely a re-projection. Pair-owned.

## Projection `π`

The AArch64 observables — post-step `pc`, `x0`–`x30`, `sp`, `NZCV`,
halt/trap — read out of the Sail ARM model's state. `π` **must match**
`aarch64-btor2`'s projection so the branch cross-check at BTOR2 compares
like with like ([`pairs/aarch64-btor2`](../aarch64-btor2/README.md)).

## Fidelity target + evidence

- **`checked`** — the commuting-square oracle walks the shared AArch64
  interpreter's trace against `L(I_sail(T(p)))` under `π`. This also
  validates the shared AArch64 interpreter against the official Arm Sail
  model — a strong independent check, exactly as `riscv-sail` does for
  RISC-V.

## Soundness story

Direct commuting-square check against the shared Sail interpreter, plus —
carried onward by `sail-btor2` — the **branch** against the direct
`aarch64-btor2` route at BTOR2 ([`PAIRING.md`](../../PAIRING.md) §6,
[`PATHS.md`](../../PATHS.md) §4).

## Notes for the implementing agent

- Reuse the shared AArch64 and Sail interpreters; if first to touch Sail,
  contribute the model-agnostic Sail interpreter
  ([`languages/sail`](../../languages/sail/README.md)) — prefer driving the
  Sail-generated ARM model executable over re-implementing it.
- Keep `π` projection-compatible with `aarch64-btor2`; the branch is the
  point.
- **Oracle / tooling gap.** The development image ([`DOCKER.md`](../../DOCKER.md))
  currently pins the *Sail-RISCV* emulator (`sail_riscv_sim`), the oracle
  for `riscv-sail`. An **ARM Sail emulator** is the analogous oracle for
  this pair and is **not yet in the image** — add it (a new pinned layer)
  as part of building this pair.
