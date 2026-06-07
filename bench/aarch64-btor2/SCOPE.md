# `aarch64-btor2` benchmark scope

This is the §9.1 instantiation of [BENCHMARKING.md](../../BENCHMARKING.md)
for the `aarch64-btor2` pair. It mirrors the `riscv-btor2` scope
where possible (this is the ISA-portability port) and diverges
only where AArch64 semantics genuinely differ.

## 1. Source language and dialect

- **ISA**: ARMv8-A AArch64 user mode. XLEN is 64.
- **Mode**: user-mode only (EL0). Straight-line and branching
  code; calls to `included_callees` are inlined per the spec's
  `AnalysisScope`.
- **Subset in scope (P1 schema v1.0.0)**:
  - Base integer ISA (~90 opcodes): MOV/MOVZ/MOVN/MOVK, ADD/SUB
    (with shifted register, extended register, immediate),
    MUL/MADD/MSUB/MNEG/UMULL/SMULL/UMULH/SMULH,
    UDIV/SDIV, AND/ORR/EOR/BIC/ORN/EON/MVN, LSL/LSR/ASR/ROR
    (register and immediate forms), SBFX/UBFX/SBFM/UBFM/BFM,
    CMP/CMN/TST, CCMP/CCMN, CSEL/CSINC/CSINV/CSNEG/CSET/CSETM,
    CLZ/CLS/RBIT/REV/REV16/REV32, ADC/SBC.
  - Branches: B, B.cond, BL, BR, BLR, RET, CBZ/CBNZ, TBZ/TBNZ.
  - Loads/stores: LDR/STR (all sizes and signedness), LDP/STP,
    LDUR/STUR, LDAR/STLR (acquire/release; modeled as ordinary
    loads/stores at P1 since concurrency is out of scope).
  - Address arithmetic: ADR, ADRP.
  - PSTATE: NZCV reads via condition codes; explicit MSR/MRS
    deferred.
- **Out of scope at P1** (stable exclusions, may revisit):
  - **F/D floating point**, NEON, SVE, SVE2.
  - **Atomics** (LDXR/STXR exclusive-monitor, LSE atomics).
  - **System / privileged** (EL1+, system registers, exception
    levels, TLB ops, cache maintenance).
  - **Pointer authentication (PAC)** — PACIA/AUTIA family.
  - **Branch Target Identification (BTI)**.
  - **Memory Tagging Extension (MTE)**.
- **Source artifact**: a single statically-linked AArch64 ELF,
  plus an `AnalysisScope(entry_function, included_callees)`.

## 2. Reasoning language and solver inventory

- **Reasoning language**: BTOR2, schema version `1.0.0`. Layered
  shape (header / machine / library / dispatch / init / constraint
  / volatile / bad / binding) — same as `riscv-btor2` v1.1.0,
  with the machine layer specialized:
  - **General-purpose registers**: `x0`–`x30` as 31 `bv64` state
    cells (`xzr` modeled as a constant zero, not a state). `wN`
    is the 32-bit alias of `xN` (zero-extended writes follow
    AArch64 semantics).
  - **SP**: separate `bv64` state.
  - **PC**: `bv64`.
  - **NZCV**: four `bv1` flag state cells (N, Z, C, V).
  - **Memory**: `Array bv64 bv8`.
  - **Trap flag**: `bv1` for halt / fault.

- **Solver inventory**: identical to `riscv-btor2`:

| Engine        | Backend          | Role |
|---------------|------------------|------|
| `z3-bmc`      | z3 4.16.0        | BMC; default. |
| `z3-spacer`   | z3 4.16.0        | Inductive (Horn). |
| `bitwuzla`    | 0.9.0+           | BMC alternative; bitvector-strong. |
| `cvc5`        | 1.3.3+           | BMC alternative; second-vendor cross-check. |
| `pono`        | 2.0.0-beta+      | Subprocess BMC + k-induction. |

Solver adapters copied verbatim from `v2-bootstrap`.

## 3. Property language

Same as `riscv-btor2`: `reach(pc)`, `reach(register_predicate)`,
`reach(memory_predicate)`, `safety(invariant)`.

## 4. Corpus structure

```
bench/aarch64-btor2/corpus/
  seed/
    0001-x0-write-dropped/        # ports from riscv-btor2 0001
    0002-bound-sensitive-loop/    # ports from riscv-btor2 0002
    0007-simple-add-baseline/
    ...
  wedge_ports/                    # the headline reproduction set
    0115-c-int-overflow/
    0116-c-divu-sentinel/         # NOTE: AArch64 div-by-zero
                                  # returns 0, not RV64M's
                                  # all-ones sentinel; ground
                                  # truth must be re-derived
                                  # per AArch64 semantics
    0117-c-int-min-div-neg-one/
    0118-c-shift-amount-mask/
    0121-c-mulw-truncation/       # NOTE: AArch64 has no `mulw`;
                                  # 32-bit MUL via W-regs
                                  # naturally zero-extends
                                  # to 64-bit. Re-derive.
  svcomp_slice/                   # SV-COMP subset compiled to
                                  # AArch64
```

The `wedge_ports/` subdirectory is the P7-P8 measurement target.
Each port has the **same C source** as the corresponding RV64
task but a freshly-derived `task.toml` ground truth — because
AArch64 semantics may produce a different *expected* verdict than
RV64M does for the same C program.

### Per-wedge AArch64 semantic notes

| RV64 wedge       | RV64M behavior                | AArch64 behavior                                                 | Same wedge expected? |
|------------------|-------------------------------|------------------------------------------------------------------|----------------------|
| 0115 signed ovf  | wraps                         | wraps                                                            | YES                  |
| 0116 div-by-zero | returns all-ones sentinel     | returns **0** (no trap; AArch64 SDIV/UDIV behavior)              | YES (different value, same wedge: CBMC will still over-approximate) |
| 0117 INT_MIN/-1  | returns INT_MIN sentinel      | returns **INT_MIN** (same as RV64M)                              | YES                  |
| 0118 shift mask  | masks low bits of shift       | masks shift count mod 32/64                                      | YES                  |
| 0121 mulw trunc  | RV64M `mulw` sign-extends     | AArch64 32-bit MUL via `W` regs naturally produces 32-bit result | YES (re-derive)      |

All five wedges are **expected to reproduce on AArch64**. Per-task
ground-truth re-derivation is required where the *concrete*
behavior differs (notably 0116, where RV64M's all-ones sentinel
becomes AArch64's zero).

## 5. SOTA baselines

- **CBMC** — same adapter as `riscv-btor2` (`baselines/cbmc.py`).
  CBMC reasons on the C source, identical for both ISAs, so it
  produces the **same false positive pattern** in either case.
  This is what makes the wedge reproduction expected.
- **ESBMC**, **SeaHorn**, **Symbiotic** — same as `riscv-btor2`.
- **angr** — adds value here because angr has mature AArch64
  support; new adapter `baselines/angr.py`.
- **Pono (native)** — same adapter, AArch64-compiled BTOR2
  input.

Each baseline gets one adapter under
`bench/aarch64-btor2/baselines/`.

## 6. The wedge class to chase

The same C-UB-but-ISA-defined class as `riscv-btor2`. The
prediction is that all 5 wedges from
`riscv-btor2/baselines/INITIAL_FINDINGS.md` §13 reproduce
verbatim against CBMC, because the C side of the gap is
identical. Where the AArch64 *concrete* behavior differs from
RV64M (notably div-by-zero), the wedge form is the same but the
ground-truth `task.toml` differs.

## 7. Out-of-scope properties

- **Performance / timing** — out of scope.
- **Side-channel** — out of scope.
- **Cache / memory-ordering** — out of scope until atomics +
  multi-thread is in.
- **PAC / BTI / MTE security extensions** — out of scope.

## 8. Cross-toolchain & emulation

- **Toolchain pin**: `aarch64-linux-gnu-gcc` version recorded in
  each `task.toml`. Default expected: GCC 13.x.
- **Source-interpreter external oracle**: `qemu-aarch64-static`
  runs the same ELF; the source interpreter's golden traces are
  compared against QEMU output to validate the interpreter's
  ISA fidelity. (Analogous to how `riscv-btor2` validates
  against Spike.)
