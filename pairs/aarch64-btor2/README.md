# Pair — `aarch64-btor2`  ·  AArch64 → BTOR2

*Status: **partial** — an ALU + flag-set + branch slice
(`ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `ADDS`/`CMN`, `B.cond`, `B`/`BL`) is built and
mergeable (`gurdy/pairs/aarch64_btor2/`, `gurdy/languages/aarch64/`, interp v0.4);
see "Implementation status" below. Ported from v2.*

Translate an AArch64 (A64) ELF into a BTOR2 transition system, the same
shape as `riscv-btor2` on a second ISA. Its purpose is to demonstrate the
translator architecture is **ISA-portable**: the same layered encoding,
re-aimed at A64's register file and instruction semantics. The C-undefined-
but-ISA-defined wedge (signed overflow, shift masking, `mul` truncation)
reproduces here because the C side is identical — only the defining ISA
changes.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** AArch64 — [`languages/aarch64`](../../languages/aarch64/README.md).
- **Target.** BTOR2 — [`languages/btor2`](../../languages/btor2/README.md).
- **Translator `T`.** A spec-derived per-instruction lowering from an
  AArch64 image (+ scope) to a BTOR2 transition system: state for
  `x0`–`x30`, `sp`, `pc`, `NZCV`, a trap flag, and memory as an array;
  PC-keyed dispatch; init/next/constraint/bad. Deterministic and
  schema-predictable. Each A64-vs-RV64 semantic difference is documented
  inline in the schema as a divergence note, so every ISA-portability
  assumption is auditable.
- **Source interpreter.** The **shared** AArch64 interpreter
  ([`languages/aarch64`](../../languages/aarch64/README.md)) — reused;
  contributed by this pair if it is the first AArch64 pair built.
- **Target interpreter.** The **shared** BTOR2 interpreter
  ([`languages/btor2`](../../languages/btor2/README.md)) — reused.
- **Target-to-source interpreter `L`.** Decodes a BTOR2/solver witness into
  an AArch64 behavior (initial register/memory state + the reaching run).
  Pair-owned.

## Projection `π`

Post-step `pc`, `x0`–`x30`, `sp`, `NZCV`, halt/trap — the AArch64
interpreter's observables mapped onto the BTOR2 state variables.

## Fidelity target + evidence

- **`checked`** — the commuting-square oracle walks the shared AArch64
  interpreter's trace against `L(I_btor2(T(p)))` under `π` on a corpus;
  divergences localize to a step/observable.
- Ship re-checkable certificates (inductive invariant / k-induction) to lift
  discharged questions to `proved` ([`SOLVERS.md`](../../SOLVERS.md) §5–6).

## Soundness story

Lowering and witness replay share one source of truth (the per-instruction
encoding); a cross-check runs both under `π`
([`PAIRING.md`](../../PAIRING.md) §6).

## Fidelity-raising branch (registered)

Arm has an official **Sail** model (`sail-arm`, from ASL). The registered
**[`aarch64-sail`](../aarch64-sail/README.md)** pair, reusing `sail-btor2`,
gives a second, independent A64→BTOR2 encoding to cross-check against this
one — the same branch RISC-V has ([`PATHS.md`](../../PATHS.md) §4). Keep this
pair's projection `π` compatible with `aarch64-sail`.

## Notes for the implementing agent

- Maximize reuse of the BTOR2 core and the riscv-btor2 layer shape; only the
  register-file (machine) and per-instruction (library) layers are
  ISA-specific.
- Validate the shared AArch64 interpreter against the Sail ARM model or QEMU.

## Implementation status — ALU + flag-set + branch slice (widened 2026-06-23)

A vertical slice with both NZCV-write ops and both conditional and unconditional
control flow is built end-to-end through the commuting square and is mergeable at
**`partial`** (PAIRING.md §1). It does **not** attempt the whole A64 ISA. This is a
coverage-ratchet **widening** of the prior slice (BENCHMARKS.md §5):
`11/15 → 15/17`, interp `v0.3 → v0.4`.

- **In-scope constructs:**
  - *(0.3, unchanged)* `ADD`/`SUB` (immediate) + `MOVZ` (each a pure register
    write, successor `pc+4`, no `NZCV` write); `SUBS`/`CMP` (immediate) — the
    NZCV write with the *subtraction* `C`(no-borrow)/`V` definitions; `B.cond` —
    the conditional pc update over the full standard condition table.
  - **`B` / `BL`, unconditional branch** — the **unconditional pc update**.
    `pc := a + offset` (always taken — the `B.cond` lowering with condition =
    true), with `offset` the sign-extended `imm26 * 4`. Opcode `0b000101` (`B`) /
    `0b100101` (`BL`, bit[31] = link bit). `BL` additionally writes the link
    register `x30 := a + 4` (the return address — the analogue of RV64's
    `JAL rd`). Reads/writes no flags. Threaded into the same PC-dispatch `next pc`
    ITE chain as `B.cond`/the fall-through; backward branches (loop back-edges)
    and the off-end halt fall out for free.
  - **`ADDS (immediate)` / `CMN (immediate)`, 64-bit** — the **addition NZCV
    write**. `CMN Xn, #imm` = `ADDS XZR, Xn, #imm`. `result = read(Rn) + imm`
    written to `Rd` (the *source* field 31 = SP, the *destination* field 31 = XZR,
    so `CMN` discards the write); NZCV set as `N = result<63>`,
    `Z = (result == 0)`, **`C` = unsigned carry-out of `Rn + imm`** (the 65-bit
    sum overflows 64 bits), **`V` = signed overflow of the add**
    (`Rn<63> == imm<63>` and `result<63> ≠ Rn<63>`). NZCV is packed
    `N=bit3, Z=bit2, C=bit1, V=bit0`. **These `C`/`V` definitions are the
    *addition* versions — distinct from `SUBS`'s subtraction definitions.**

  Each is translated `T → I_btor2 → L`, cross-checked under `π` by the framework
  oracle, including an unconditional forward `B` (skipping an instruction), a
  backward `B` loop back-edge, `BL`'s link register, and each of `ADDS`/`CMN`'s
  N/Z/C(carry-out)/V(signed-overflow) flags.
- **Out of scope → typed hard-abort.** Every other A64 instruction raises
  `unsupported: aarch64:<construct>` at the shared `decode_insn_v4` (one
  rejection point for `T` and the interpreter) — never a silent drop. This now
  includes only `BC.cond` (FEAT_HBC), the 32-bit (`sf=0`) forms, the move-wide
  siblings `MOVN`/`MOVK`, loads/stores, and the rest of the ISA.
- **Shared AArch64 interpreter widened** (`gurdy/languages/aarch64/`,
  interpreter version **`0.4`**) — a strictly **additive** bump of the standalone
  shared deliverable (AGENTS.md §3): the `0.1`/`0.2`/`0.3` behavior is
  byte-for-byte unchanged, and the narrower `decode` (ADD-only), `decode_insn`
  (`ADD`/`SUB`/`MOVZ`), and `decode_insn_v3` (+`SUBS`/`CMP`+`B.cond`) decoders are
  retained verbatim as the **`aarch64-sail`** route's rejection gate, so that
  cross-checked route is undisturbed until its sibling agent mirrors the new ops
  (the `0.4` family is decoded by the new `decode_insn_v4`). Observables
  unchanged: `pc` (byte address), `x0`–`x30`, `sp`, `nzcv` (bv4), `halted`. The
  BTOR2 interpreter is **reused** unchanged.
- **Translation spec:** `gurdy/pairs/aarch64_btor2/SPEC.md` (self-contained;
  rule-for-rule per op, the exact NZCV flag definitions for `SUBS`/`CMP` **and**
  `ADDS`/`CMN` (with an explicit note that their `C`/`V` differ), the full
  `B.cond` condition table, the `B`/`BL` unconditional-branch lowering, and the
  A64-vs-RV64 divergence notes — incl. the SP-vs-XZR field-31 distinction, the
  compare/branch split, and the `BL`/`JAL` link-register analogue).
- **Fidelity:** **`checked`** — evidence is the commuting-square oracle on the
  test corpus (`tests/test_aarch64_btor2_pair.py`), with per-flag `SUBS`/`CMP`
  and `ADDS`/`CMN` tests (each of N/Z/C/V, incl. a carry-out case and a
  signed-overflow case, plus the `CMN` discard and a SUBS-vs-ADDS flag-difference
  check), `B.cond` taken-vs-not-taken across `EQ`/`NE`/`LT`/`GE`/`HI`/`LS`/`CS`/
  `CC`, a full 16×cond-code × 16×NZCV cross-check that the interpreter's
  `cond_holds` and the translator's branch ITE share one truth table, the
  unconditional `B` forward-skip and backward loop back-edge, `BL`'s link
  register, twice-and-diff determinism for `T` and the interpreter, carry-back of
  a branch-taken and a `BL` BTOR2 witness through `L`, and the end-to-end
  decide→witness→carry-back through `btor2-smtlib` (z3-gated, incl. `CMP`+`B.cond`,
  `ADDS`, and unconditional-`B` reachability programs). Honest tier —
  "validated on the inputs we tried," not `proved`.
- **Scope deferred (named future work, not silently dropped):** memory as an
  array, the trap flag, `BC.cond` (FEAT_HBC), the 32-bit (`sf=0`) forms, the
  move-wide siblings `MOVN`/`MOVK`, loads/stores, register-form ALU
  (`ADD`/`SUB`/`ADDS`/`SUBS` shifted-register), and the
  C-undefined-but-ISA-defined wedge (`SDIV` edges, shift masking, `MUL`
  truncation) — each lands as a further widening step under the coverage ratchet
  (BENCHMARKS.md §5). The brief's "memory as an array" and "trap flag" target
  state remain in the *design* (`π` already carries `nzcv`/`halted`).

### Construct coverage + `unsupported` histogram

Measured over the pair's spec-derived slice (`inventory.py`,
`gurdy/pairs/aarch64_btor2`; covered may only grow and nothing previously covered
drops — a *new* construct entering scope adds its probe, growing numerator and
denominator together): **15 / 17 probes covered = 0.882** (was `11/15`). The
covered 15 are the in-scope family in its legal forms — the eleven `0.3` probes
(`ADD_imm`, `ADD_imm_lsl12`, `ADD_imm_sp_src`, `ADD_imm_sp_dst`, `SUB_imm`,
`SUB_imm_sp`, `MOVZ`, `MOVZ_lsl16`, `SUBS_imm`, `CMP_imm`, `Bcond`) plus the four
`0.4` probes `B`, `BL`, `ADDS_imm`, `CMN_imm` (the prior out-of-scope `ADDS`/`B`
probes are promoted into covered). The 2 remaining out-of-scope probes each
hard-abort, itemized:

| `unsupported` construct | probes blocked |
|--------------------------|---------------:|
| `add.immediate.w` (32-bit, `sf=0`) | 1 |
| `opcode=0xf9400000` (LDR — memory) | 1 |

The status stays `partial` until the in-scope set widens toward the brief's
base-ISA target (a machine ISA must fully cover its declared base ISA to reach
`built`, BENCHMARKS.md §5).

### What the open questions taught us (PAIRING.md §9)

- The `riscv-btor2` / `ebpf-btor2` BTOR2-hub shape ports cleanly to a second
  ISA: the BTOR2 core, the PC-keyed ITE dispatch, the `square()` one-cycle
  trace shift, and the `{"reg_eq": [...]}` property hook were reused verbatim;
  only the decoder, the register file (SP vs a zero register), and the
  byte-addressed PC are ISA-specific — confirming the architecture is
  ISA-portable as the brief predicted.
- **The conditional pc update fits the straight-line translator cleanly.** The
  existing PC-keyed dispatch already threads a `next_pc` ITE chain (one
  `ite(active, fall, next_pc)` per instruction); making `fall` itself a
  condition-ITE (`ite(cond(NZCV), a+offset, a+4)`) for `B.cond` introduced
  conditional control flow with no structural change to the dispatch — backward
  branches (loops) and the off-end halt fall out for free. The first NZCV write
  is just one more state node threaded the same way (`next_nzcv`).
- **Compare/branch split vs RISC-V's fused branch.** A64 separates the flag-set
  compare (`SUBS`/`CMP`/`ADDS`/`CMN`, which write `NZCV`) from the branch
  (`B.cond`, which reads `NZCV`), where RV64's `BEQ`/… fuse the comparison into
  the branch. The shared `nzcv` state node (carried in `π` since the first slice
  for exactly this reason) is what makes the split expressible without changing
  the projection.
- **The unconditional branch is the always-taken `B.cond`.** Adding `B`/`BL`
  needed no new structural machinery: `B`'s next-pc is the `B.cond` lowering with
  the condition node replaced by a constant `true` (`next pc := ite(active,
  a+offset, next pc)`), and `BL` is that plus one more state-node write
  (`x30 := ite(active, a+4, next x30)`) — the same `ite(active, …, next)` thread
  every register write already uses. The off-end halt and backward-branch loops
  fall out unchanged. This is the `B.cond`-fits-cleanly lesson taken to its
  endpoint.
- **Addition vs subtraction flags are genuinely distinct — and easy to get
  subtly wrong.** `ADDS`'s `C` is the *unsigned carry-out* (built as a bv65 add
  with bit 64 sliced out) and its `V` uses *same-sign-in* operands, whereas
  `SUBS`'s `C` is *no-borrow* (`Rn >=u imm`) and its `V` uses *different-sign-in*.
  Mirroring the interpreter's `_adds_flags` and the translator's `_adds_nzcv`
  from one written definition (SPEC.md), then testing each flag (incl. a carry-out
  and a signed-overflow case) and an explicit SUBS-vs-ADDS difference, is what
  keeps the two flag definitions from drifting.
- **Widening a shared decoder under a branch-agreement constraint (again).** The
  `aarch64-sail` route shares this language's decoder and its `translate` uses it
  as the sole rejection gate. Widening the *shared* `decode_insn_v3` to accept
  `B`/`BL`/`ADDS` would have broken that route's rejection boundary until its
  sibling caught up. The additive resolution — keep `decode_insn_v3` as the `0.3`
  gate, add a richer `decode_insn_v4` for the `0.4` family, and switch only this
  pair's `T` and the shared `run` to it — repeats the `0.1→0.2→0.3` pattern: one
  pair widens without forcing a lockstep change on its branch sibling (AGENTS.md
  §3). The coverage-parity branch-agreement check is, in this transient window, a
  *subset* check (sail ⊆ btor2, the difference being exactly `B`/`BL`/`ADDS`/
  `CMN`), restored to equality when the sibling mirrors the `0.4` ops.
