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

## Interpreter build brief

*Status: **partial** — the RV64IM set is built (`gurdy/languages/riscv/`,
base integer + the M extension, tests in `tests/test_riscv_interp.py`), with
static ELF64 image loading (`load_elf`, tests in `tests/test_riscv_elf.py`,
exercised against a real `riscv64-unknown-elf-gcc` binary); the C extension
and the `sail_riscv_sim` differential are pending. A standalone deliverable
on the framework MVP-1
([`FRAMEWORK.md`](../../FRAMEWORK.md) §6). Bootstrap-critical — three pairs
(`c-riscv`, `riscv-btor2`, `riscv-sail`) reuse it.*

- **MVP scope.** RV64I base integer plus the M and C extensions the first
  pairs declare; `run(image, binding, max_steps) -> trace` of post-step `pc`,
  `x1..x31`, and `halted`. Unsupported instructions hard-abort
  `unsupported: <mnemonic>` ([`BENCHMARKS.md`](../../BENCHMARKS.md) §3).
- **Oracle.** Differential against the pinned **`sail_riscv_sim`**
  ([`DOCKER.md`](../../DOCKER.md)) on the same images.
- **Coverage target.** Full RV64I, then M/C; measured against the opcode
  inventory and the **riscv-tests / riscv-arch-test** slice
  ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4).
- **Acceptance.** Deterministic (twice-and-diff); matches `sail_riscv_sim`
  step-for-step on the coverage slice under the observable projection.
- **Thin-first** ([`PAIRING.md`](../../PAIRING.md) §1): land arithmetic +
  branch + load/store at `partial`, then widen.

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): **riscv-tests**
and **riscv-arch-test** (architecture compliance, golden state) as pinned
submodules, plus **riscv-torture** for fuzz/mutation coverage. These also
drive the RISC-V-origin paths and the RISC-V→BTOR2 branch cross-check.

## Pairs over this language

- [`c-riscv`](../../pairs/c-riscv/README.md) — target.
- [`riscv-btor2`](../../pairs/riscv-btor2/README.md) — source.
- [`riscv-sail`](../../pairs/riscv-sail/README.md) — source.
