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

**Interpreter version `0.4`** (`gurdy/languages/aarch64/`, interp v0.3 → v0.4):
a strictly **additive** widening (AGENTS.md §3, BENCHMARKS.md §5) of the `0.3`
family (`ADD`/`SUB` immediate + `MOVZ` + `SUBS`/`CMP` + `B.cond`, all 64-bit)
that introduces the **unconditional branch** and the **addition NZCV write**:

- **`B` / `BL`** — the unconditional branch. `pc := pc + SignExtend(imm26)*4`,
  *always taken* (the `B.cond` lowering with condition = true). Opcode `0b000101`
  (`B`) / `0b100101` (`BL`, bit[31] = the link bit). `BL` additionally writes the
  link register `x30 := pc + 4` (the return address). Reads/writes no flags.
- **`ADDS (immediate)` / `CMN`** (64-bit) — the flag-setting add. `result =
  read(Rn) + imm` written to `Rd` (`CMN Xn,#imm` = `ADDS XZR,Xn,#imm`, the write
  discarded), and it **sets** the NZCV flags with the **addition** `C`/`V`
  definitions (distinct from `SUBS`'s): `N = result<63>`, `Z = (result == 0)`,
  `C` = unsigned carry-out of `read(Rn) + imm` (the 65-bit sum overflows 64 bits),
  `V` = signed overflow of the add (`Rn<63> == imm<63>` and `result<63> ≠ Rn<63>`).
  NZCV is packed `N=bit3, Z=bit2, C=bit1, V=bit0`. The *source* field 31 is `SP`,
  the *destination* field 31 is `XZR`.

The prior `0.3` family is unchanged: `SUBS`/`CMP` (the flag-setting subtract,
with the *subtraction* `C`(no-borrow)/`V` definitions) and `B.cond` (the
conditional pc update over the full standard condition table).

The `0.1`/`0.2`/`0.3` behavior is byte-for-byte unchanged, and the narrower
`decode` (`ADD`-only), `decode_insn` (`ADD`/`SUB`/`MOVZ`), and `decode_insn_v3`
(+`SUBS`/`CMP`+`B.cond`) decoders are retained verbatim (the `0.4` family is
decoded by the new `decode_insn_v4`), so the cross-checked **`aarch64-sail`**
route — which shares the narrower decoders as its rejection gate and executes
only the `0.3` ops — is undisturbed until its sibling agent mirrors the new ops.
Every other A64 instruction still hard-aborts with a typed `unsupported` (incl.
`BC.cond`, the 32-bit forms, and the move-wide siblings `MOVN`/`MOVK`). Widening
toward the base ISA (register-form ALU, loads/stores), and the Sail-ARM/QEMU
differential, remain future work.

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): Arm's
**Architecture Compliance Kit** (the same suite that validated `sail-arm`,
golden state), subject to its licensing; compiled C suites otherwise. Drives
the AArch64→BTOR2 branch cross-check (`aarch64-btor2` vs `aarch64-sail` →
`sail-btor2`).

## Pairs over this language

- [`aarch64-btor2`](../../pairs/aarch64-btor2/README.md) — source.
- [`aarch64-sail`](../../pairs/aarch64-sail/README.md) — source.
