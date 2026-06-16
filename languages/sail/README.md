# Language — Sail

Sail is a language for **describing instruction-set architectures**: an ISA
written in Sail has an executable, formally-specified semantics, and the
RISC-V architecture has an official Sail model. In the registry Sail is the
*mediating* language of the second RISC-V→BTOR2 route: `riscv-sail` lifts a
RISC-V program into its Sail-model execution, and `sail-btor2` lowers Sail
to a BTOR2 transition system. That route exists to be **cross-checked
against the direct `riscv-btor2` route** — two independent encodings of
RISC-V semantics meeting at BTOR2 ([`PATHS.md`](../../PATHS.md) §4–5).

## Formal semantics (source of truth)

The Sail language's formal semantics, instantiated at **the RISC-V model in
Sail** (the official, executable specification). The meaning of the Sail
object here is the architectural behavior that model defines — which is, by
construction, the RISC-V ISA. The value of routing through Sail is exactly
that this is a *different artifact* expressing the *same* ISA than the
hand-built `riscv-btor2` translator, so agreement between the two routes is
real corroboration and disagreement localizes a genuine bug.

A pair states which Sail model and version it pins; the language is the Sail
semantics.

## Shared interpreter

**Role: source and target.** Sail is a *target* of `riscv-sail` and a
*source* of `sail-btor2`. One interpreter serves both.

Contract ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5):

- **Input.** A Sail object (the pinned RISC-V model applied to a program
  image) plus a binding — initial state and a step bound.
- **Behavior.** A trace of **post-step** states of the Sail model's
  architectural state.
- **Observables.** The architectural state the model exposes — chosen so
  that it projects onto the *same* observable space as the RISC-V
  interpreter ([`languages/riscv`](../riscv/README.md)), because the whole
  point of the Sail route is to compare against the direct route at BTOR2.
  Keeping the projections compatible across the two routes is a shared
  obligation of `riscv-sail` and `riscv-btor2`.
- **Determinism.** Pure; pinned model + program + binding → identical trace.

The Sail model is large; an agent may build this interpreter by **driving
the Sail-generated executable model** rather than re-implementing it, as
long as the result is deterministic and exposes the observable conventions
above ([`PAIRING.md`](../../PAIRING.md) §9 open question on large
interpreters).

## Pairs over this language

- [`riscv-sail`](../../pairs/riscv-sail/README.md) — target.
- [`sail-btor2`](../../pairs/sail-btor2/README.md) — source.
