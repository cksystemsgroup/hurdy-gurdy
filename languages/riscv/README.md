# Language — RISC-V

The RISC-V instruction set: the platform's central **machine** language.
It sits between the high-level source (C) and the reasoning targets (BTOR2,
directly and via Sail), so its shared interpreter is exercised by three
pairs.

## Formal semantics (source of truth)

The RISC-V ISA specification. A program is an ELF image (a base ISA plus
the extensions a pair declares in scope — e.g. integer, multiply/divide,
compressed); its meaning is the architectural state transition the
specification defines for each instruction, including the behaviors C
leaves undefined (overflow wraps, shift amounts mask, division by zero and
`INT_MIN / -1` have defined results, byte/halfword load signedness is
fixed). Capturing exactly these defined-on-RISC-V-but-undefined-in-C
behaviors is why C is paired through RISC-V.

A pair states the ISA extensions, address width, and any platform
conventions it assumes; the language itself is the specification.

## Shared interpreter

**Role: source and target.** RISC-V is a *target* of `c-riscv` and a
*source* of `riscv-btor2` and `riscv-sail`. One interpreter serves all
three.

Contract ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5):

- **Input.** A RISC-V program (loaded image) plus an input binding —
  initial register and memory state, a step bound, and a halting condition.
- **Behavior.** A trace of **post-step** architectural states.
- **Observables (the projectable fields).** The program counter, the
  general-purpose registers, and a halt flag, at minimum; a pair's
  projection `π` selects a subset of these. Extensions to the observable
  set (CSRs, memory regions) are versioned additions.
- **Determinism.** Pure; identical program + binding → identical trace,
  byte-for-byte, on any host. Ships a twice-and-diff check.

This interpreter is the `I_s` for `riscv-btor2` and `riscv-sail`, and the
`I_t` whose behavior `c-riscv`'s square is checked against downstream. It is
one of the most-shared interpreters in the registry (alongside BTOR2's);
build it deliberately and version any change to it.

## Pairs over this language

- [`c-riscv`](../../pairs/c-riscv/README.md) — target.
- [`riscv-btor2`](../../pairs/riscv-btor2/README.md) — source.
- [`riscv-sail`](../../pairs/riscv-sail/README.md) — source.
