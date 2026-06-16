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
`sail-btor2` branch, AArch64 can get an **`aarch64-sail`** pair that reuses
`sail-btor2`, giving a second, independent encoding of A64 into BTOR2 to
cross-check against `aarch64-btor2` ([`PATHS.md`](../../PATHS.md) §4). The
Sail ARM model is also the gold oracle for the shared interpreter below.
This branch is a **suggestion**, not yet registered.

## Shared interpreter

**Role: source.** One deterministic AArch64 executor over an input binding
→ a trace of post-step architectural states. Observables: program counter,
`x0`–`x30`, `sp`, the `NZCV` flags, and a halt/trap flag
([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5). Validate it against the
Sail ARM model (or QEMU) as an external oracle. Shared by every AArch64
pair (today `aarch64-btor2`; `aarch64-sail` if added).

## Pairs over this language

- [`aarch64-btor2`](../../pairs/aarch64-btor2/README.md) — source.
