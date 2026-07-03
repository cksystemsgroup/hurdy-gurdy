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
`aarch64-btor2` ([`ROUTES.md`](../../ROUTES.md) §4). The Sail ARM model is also
the gold oracle for the shared interpreter below.

## Shared interpreter

**Role: source.** One deterministic AArch64 executor over an input binding
→ a trace of post-step architectural states. Observables: program counter,
`x0`–`x30`, `sp`, the `NZCV` flags, the byte-memory window
`m0`–`m{MEM_WINDOW-1}` (`MEM_WINDOW = 64`), and a halt/trap flag
([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5). Validate it against the
Sail ARM model (or QEMU) as an external oracle. Shared by `aarch64-btor2`
and `aarch64-sail`.

**Interpreter version `0.6`** (`gurdy/languages/aarch64/`, interp v0.5 → v0.6):
a strictly **additive** widening (AGENTS.md §3, BENCHMARKS.md §5) of the `0.5`
family (`ADD`/`SUB` immediate + `MOVZ` + `SUBS`/`CMP` + `ADDS`/`CMN` + `B.cond` +
`B`/`BL` + 64-bit `LDR`/`STR`) that introduces the **32-bit (W-register) forms** of
the ALU/flag-setting immediate instructions:

- **`ADD`/`SUB`/`MOVZ` W and `SUBS`/`CMP`/`ADDS`/`CMN` W** (`sf = 0`). The op
  computes on the **low 32 bits** of the source register(s); the 32-bit result
  **zero-extends into the full 64-bit `Xd`** (the upper 32 bits become 0); and the
  flags (for `SUBS`/`ADDS` W) are computed on the **32-bit** result — `N = bit 31`,
  `Z` over the 32-bit result, `C`/`V` from the 32-bit add/subtract (so a 32-bit
  carry/overflow is independent of the 64-bit one). `MOVZ` W restricts `hw ∈ {0,1}`
  (LSL #0/#16). Field-31 semantics are unchanged per class (`ADD`/`SUB` → `WSP`;
  `SUBS`/`ADDS` source `WSP`, destination `WZR`; `MOVZ` → `WZR`). This is the
  zero-extend analogue of RV64's `*W` ops (which *sign*-extend — the one genuine
  divergence). The `Decoded` record gains an additive `width` field (default `64`,
  `32` for the W forms); the 32-bit flag math lives in `_subs_flags32` /
  `_adds_flags32`.

The prior `0.5` family is unchanged: the 64-bit **`LDR` / `STR` (unsigned offset)** —
`STR Xt, [Xn|SP, #imm]` stores the 64-bit `Xt` **little-endian** to
`mem[read(Rn) + imm]`; `LDR Xt, [Xn|SP, #imm]` loads 64 bits LE back into `Xt`
(`imm = imm12 * 8`; base field 31 = `SP`, transfer field 31 = `XZR`; no flags). The
`0.4` family is likewise unchanged: `SUBS`/`CMP` and `ADDS`/`CMN` (the flag-setting
subtract/add, with their respective `C`/`V` definitions), `B.cond` (the conditional
pc update over the full standard condition table), and `B`/`BL` (the unconditional
branch; `BL` writes the link register `x30 := pc + 4`). Memory is a byte map (LE,
zero-initialized — bytes never written read 0); the post-step memory observable is
the fixed window `m0..m{MEM_WINDOW-1}` of the lowest `MEM_WINDOW` bytes.

The `0.1`–`0.5` behavior is byte-for-byte unchanged, and the narrower `decode`
(`ADD`-only), `decode_insn` (`ADD`/`SUB`/`MOVZ`), `decode_insn_v3`
(+`SUBS`/`CMP`+`B.cond`), `decode_insn_v4` (+`B`/`BL`+`ADDS`/`CMN`) and
`decode_insn_v5` (+64-bit `LDR`/`STR`) decoders are retained verbatim (the `0.6`
family — the 32-bit W forms — is decoded by the new `decode_insn_v6`), so the
cross-checked **`aarch64-sail`** route — which shares the narrower decoders as its
rejection gate and executes only the `0.5` ops — is undisturbed until its sibling
agent mirrors the new ops. Every other A64 instruction still hard-aborts with a
typed `unsupported` (incl. `BC.cond`, the move-wide siblings `MOVN`/`MOVK`, the
reserved 32-bit `MOVZ` shift `hw ∈ {2,3}`, and the narrower-width / other-mode
loads/stores `LDRB`/`STRB`, 32-bit `LDR`/`STR`, `LDRSW`, pre/post-index,
`LDUR`/`STUR`). Widening toward the base ISA (register-form ALU, the narrower-width
loads/stores, the other addressing modes), and the Sail-ARM/QEMU differential,
remain future work.

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): Arm's
**Architecture Compliance Kit** (the same suite that validated `sail-arm`,
golden state), subject to its licensing; compiled C suites otherwise. Drives
the AArch64→BTOR2 branch cross-check (`aarch64-btor2` vs `aarch64-sail` →
`sail-btor2`).

## Pairs over this language

- [`aarch64-btor2`](../../pairs/aarch64-btor2/README.md) — source.
- [`aarch64-sail`](../../pairs/aarch64-sail/README.md) — source.
