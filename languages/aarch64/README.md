# Language — AArch64

The AArch64 (ARMv8-A, A64) instruction set: a second **machine** language,
ported from the RISC-V shape to prove the translator architecture is
ISA-portable. Source of `aarch64-btor2`.

## Formal semantics (source of truth)

The Arm Architecture Reference Manual for A-profile. A program is an
AArch64 ELF image (a base integer + load/store + branch subset at first;
floating point, SVE/NEON, atomics, and privileged state are out of scope
until a pair declares them); its meaning is the architectural state
transition Arm defines, including the behaviors C leaves undefined
(`SDIV`/`UDIV` by zero yields 0, but `SDIV INT_MIN, -1` is `INT_MIN`; shift
amounts mask; `MUL` truncates). These defined-on-AArch64-but-undefined-in-C
behaviors are the analogue of the RISC-V wedge.

## Formal model — a Sail model exists

Arm's architecture is available as a **Sail** model (`sail-arm`),
auto-translated from Arm's internal **ASL** definition and validated by
running the Sail-generated emulator against Arm's Architecture Compliance
Kit. (Arm's **Morello**/CHERI-Arm is likewise a full Sail model.)

This matters for fidelity: exactly as RISC-V has the `riscv-sail` →
`sail-btor2` branch, AArch64 has the **registered**
[`aarch64-sail`](../../pairs/aarch64-sail/README.md) → `sail-btor2` route — a
second, independent encoding of A64 into BTOR2 to cross-check against
`aarch64-btor2` ([`PATHS.md`](../../PATHS.md) §4). The Sail ARM model is also
the gold oracle for the shared interpreter below.

## Shared interpreter

**Role: source.** One deterministic AArch64 executor over an input binding
→ a trace of post-step architectural states. Observables: program counter,
`x0`–`x30`, `sp`, the `NZCV` flags, and a halt/trap flag
([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5). Validate it against the
Sail ARM model (or QEMU) as an external oracle. Shared by `aarch64-btor2`
and `aarch64-sail`.

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): Arm's
**Architecture Compliance Kit** (the same suite that validated `sail-arm`,
golden state), subject to its licensing; compiled C suites otherwise. Drives
the AArch64→BTOR2 branch cross-check (`aarch64-btor2` vs `aarch64-sail` →
`sail-btor2`).

## Pairs over this language

- [`aarch64-btor2`](../../pairs/aarch64-btor2/README.md) — source.
- [`aarch64-sail`](../../pairs/aarch64-sail/README.md) — source.
