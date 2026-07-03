# Pair — `aarch64-btor2`  ·  AArch64 → BTOR2

*Status: **partial** — an ALU + flag-set + branch + memory slice
(`ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `ADDS`/`CMN`, `B.cond`, `B`/`BL`, `LDR`/`STR`),
now including the **32-bit (W-register) forms** of the ALU/flag immediate ops, is
built and mergeable (`gurdy/pairs/aarch64_btor2/`, `gurdy/languages/aarch64/`,
interp v0.6); see "Implementation status" below. Ported from v2.*

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

Post-step `pc`, `x0`–`x30`, `sp`, `NZCV`, the memory window
`m0`–`m{MEM_WINDOW-1}` (`MEM_WINDOW = 64` bytes), halt/trap — the AArch64
interpreter's observables mapped onto the BTOR2 state variables. The memory-window
fields are the additive `0.5` extension (the register/flag/control prefix stays
compatible with `aarch64-sail`).

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
one — the same branch RISC-V has ([`ROUTES.md`](../../ROUTES.md) §4). Keep this
pair's projection `π` compatible with `aarch64-sail`.

## Notes for the implementing agent

- Maximize reuse of the BTOR2 core and the riscv-btor2 layer shape; only the
  register-file (machine) and per-instruction (library) layers are
  ISA-specific.
- Validate the shared AArch64 interpreter against the Sail ARM model or QEMU.

## Implementation status — the 32-bit (W-register) ALU/flag forms (widened 2026-06-23)

The latest widening adds the **32-bit (W-register) forms** of the ALU/flag-setting
immediate instructions — `ADD`/`SUB`/`MOVZ` W and `SUBS`/`CMP`/`ADDS`/`CMN` W — on
top of the 64-bit slice below. This is a coverage-ratchet **widening** (BENCHMARKS.md
§5): `19/23 → 27/33`, interp `v0.5 → v0.6`. Still mergeable at **`partial`**
(PAIRING.md §1); it does **not** attempt the whole A64 ISA.

- **The 32-bit W forms (interp 0.6).** `decode_insn_v6` accepts `sf = 0` for the
  Add/subtract-immediate and Move-wide classes, tagging the decoded instruction with
  `width = 32` (the X forms stay `width = 64`). The **one real subtlety** vs the
  64-bit forms is the width:
  - **The op computes on the low 32 bits** of the source register(s)
    (`slice(Rn, 31, 0)`), at width 32 (a bv32 `add`/`sub`, or the `MOVZ` immediate
    which fits in 32 bits — `hw ∈ {0,1}`, LSL #0/#16).
  - **The 32-bit result zero-extends into the full 64-bit `Xd`** — the upper 32 bits
    of `Xd` become **0** (`T` writes `uext(64, result32, 32)`). This is the genuine
    A64-vs-RV64 divergence: RV64's `*W` ops **sign-extend**, A64 **zero-extends**.
  - **The flags are 32-bit.** For `SUBS`/`CMP` W and `ADDS`/`CMN` W the `NZCV` are
    computed on the 32-bit result: `N = result<31>` (bit 31), `Z = (32-bit result ==
    0)`, and `C`/`V` from the 32-bit add/subtract (`C` = no-32-bit-borrow for `SUBS`
    W / unsigned carry-out of the 33-bit sum for `ADDS` W; `V` = signed overflow at
    the 32-bit sign bit). So a 32-bit carry/overflow is independent of the 64-bit one
    (e.g. `0x80000000 - 1` overflows the signed *32-bit* range but not the 64-bit
    one). The `_subs_nzcv` / `_adds_nzcv` node templates are parameterized by
    `width = 32`; the interpreter mirrors them in `_subs_flags32` / `_adds_flags32`.
  - **Field-31 semantics are unchanged** from the 64-bit forms (per class): for
    `ADD`/`SUB` W field 31 is `WSP`; for `SUBS`/`ADDS` W the source field 31 is `WSP`
    but the destination is `WZR`; for `MOVZ` W field 31 is `WZR`.

  Each W form is translated `T → I_btor2 → L`, cross-checked under `π` by the
  framework oracle (incl. a `ADD`/`SUB` W zero-extend with high source bits set, a
  32-bit wrap, `SUBS`/`ADDS` W flag cases distinct from the 64-bit op, `MOVZ` W,
  `ADD` W to `WSP`, the `CMP`/`CMN` W discards, and a mixed W+X program). The 64-bit
  forms below are **byte-for-byte unchanged** (verified: identical translator bytes
  and interpreter traces vs `v0.5`). The branches and `LDR`/`STR` remain 64-bit only
  this round.

## Implementation status — ALU + flag-set + branch + memory slice (widened 2026-06-23)

A vertical slice with both NZCV-write ops, both conditional and unconditional
control flow, **and the first data-memory access** is built end-to-end through the
commuting square and is mergeable at **`partial`** (PAIRING.md §1). It does **not**
attempt the whole A64 ISA. This was a coverage-ratchet **widening** of the prior
slice (BENCHMARKS.md §5): `15/17 → 19/23`, interp `v0.4 → v0.5`.

- **In-scope constructs:**
  - *(0.4, unchanged)* `ADD`/`SUB` (immediate) + `MOVZ` (each a pure register
    write, successor `pc+4`, no `NZCV` write); `SUBS`/`CMP` (immediate) — the
    NZCV write with the *subtraction* `C`(no-borrow)/`V` definitions;
    `ADDS`/`CMN` (immediate) — the NZCV write with the *addition*
    `C`(carry-out)/`V` definitions; `B.cond` — the conditional pc update over the
    full standard condition table; `B`/`BL` — the unconditional pc update (`BL`
    writes the link register `x30 := a + 4`).
  - **`LDR` / `STR` (64-bit, unsigned offset)** — the **first memory access**.
    `STR Xt, [Xn|SP, #imm]` stores the 64-bit `Xt` **little-endian** to
    `mem[read(Rn) + imm]`; `LDR Xt, [Xn|SP, #imm]` loads 64 bits LE back into
    `Xt`. The 12-bit unsigned immediate is **scaled by the access size 8**
    (`imm = imm12 * 8`). Encoding: Load/store register, unsigned immediate
    (`size=11`, bits[29:27]=`111`, `V=0`, bits[25:24]=`01`; `opc=00` STR /
    `01` LDR). The **base** field 31 (`Rn`) is **SP**; the **transfer** field 31
    (`Rt`) is the zero register **XZR** (a store of XZR writes 0, a load to XZR is
    discarded) — never SP. Reads/writes no flags; successor `pc+4`.

  Each is translated `T → I_btor2 → L`, cross-checked under `π` by the framework
  oracle, including a `STR`-then-`LDR` round-trip, a load from never-written
  memory (= 0), the SP-relative `[SP, #imm]` form, the little-endian `m{i}` window
  byte order, and the `Rt = XZR` store-zero / load-discard.
- **Memory model.** Memory is a BTOR2 **`Array bv64 bv8`** (byte-addressed,
  **little-endian** — AArch64 is LE), emitted *only* when the program uses
  `LDR`/`STR` (mirroring `evm-btor2` / `ebpf-btor2`'s conditional `mem` array;
  the shared BTOR2 interpreter already supports arrays — reused unchanged). The
  BTOR2 trace exposes only bit-vector state, not arrays, so the memory observable
  reaches `π` through a fixed window of bv8 states `m0..m{MEM_WINDOW-1}`
  (`MEM_WINDOW = 64`): each `m{i}` tracks `mem[i]` after every step, init-ed from
  `init_mem[i]`. The source interpreter exposes the identical `m{i}` bytes, so the
  cross-check compares memory step-for-step. **No alignment restriction** (the
  byte-addressed model handles any effective address; the brief's fallback was not
  needed).
- **Out of scope → typed hard-abort.** Every other A64 instruction raises
  `unsupported: aarch64:<construct>` at the shared `decode_insn_v6` (one
  rejection point for `T` and the interpreter) — never a silent drop. This now
  includes `BC.cond` (FEAT_HBC), the move-wide siblings `MOVN`/`MOVK` (32- and
  64-bit), the reserved 32-bit `MOVZ` shift (`hw ∈ {2,3}`), the **narrower-width /
  other-mode loads/stores** (`LDRB`/`STRB` and the other byte/halfword widths, the
  32-bit `LDR`/`STR`, `LDRSW`, and the pre/post-index and unscaled `LDUR`/`STUR`
  modes — only the 64-bit unsigned-offset `LDR`/`STR` is in scope), and the rest of
  the ISA. (The 32-bit `sf=0` **ALU/flag** forms are now *in scope* — `width = 32`.)
- **Shared AArch64 interpreter widened** (`gurdy/languages/aarch64/`,
  interpreter version **`0.6`**) — a strictly **additive** bump of the standalone
  shared deliverable (AGENTS.md §3): the `0.1`–`0.5` behavior is byte-for-byte
  unchanged, and the narrower `decode` (ADD-only), `decode_insn`
  (`ADD`/`SUB`/`MOVZ`), `decode_insn_v3` (+`SUBS`/`CMP`+`B.cond`), `decode_insn_v4`
  (+`B`/`BL`+`ADDS`/`CMN`) and `decode_insn_v5` (+64-bit `LDR`/`STR`) decoders are
  retained verbatim as the **`aarch64-sail`** route's rejection gate, so that
  cross-checked route is undisturbed until its sibling agent mirrors the new ops (the
  `0.6` family — the 32-bit W-register ALU/flag forms — is decoded by the new
  `decode_insn_v6`). The `Decoded` record gains an additive `width` field (default
  `64`, set to `32` for the W forms). Observables unchanged: `pc` (byte address),
  `x0`–`x30`, `sp`, `nzcv` (bv4), the memory window `m0`–`m{MEM_WINDOW-1}` (bv8
  each), `halted` (the W result simply zero-extends into the existing 64-bit `x{r}`
  observable). The BTOR2 interpreter is **reused** unchanged.
- **Translation spec:** `gurdy/pairs/aarch64_btor2/SPEC.md` (self-contained;
  rule-for-rule per op, the memory model (the `Array bv64 bv8`, the LE byte
  read/write chains, the `m{i}` window), the exact NZCV flag definitions (both
  widths), the full `B.cond` condition table, the `B`/`BL` and `LDR`/`STR`
  lowerings, **the 32-bit W-register forms (the low-32-bit op, the zero-extend into
  `Xd`, the 32-bit flags)**, and the A64-vs-RV64 divergence notes — incl. the
  SP-vs-XZR field-31 distinction (per-class: base SP vs transfer XZR for
  `LDR`/`STR`), the compare/branch split, the `BL`/`JAL` link-register analogue, the
  `LD`/`SD` memory analogue, and the W **zero-extend** vs RV64's `*W`
  **sign-extend**).
- **Fidelity:** **`checked`** — evidence is the commuting-square oracle on the
  test corpus (`tests/test_aarch64_btor2_pair.py`), with the prior per-flag
  `SUBS`/`CMP` and `ADDS`/`CMN` tests, the `B.cond`/`B`/`BL` control-flow tests,
  the `0.5` memory tests (a `STR`-then-`LDR` round-trip, a zero-read of unwritten
  memory, the SP-relative form, the LE `m{i}` window byte order, the `Rt = XZR`
  store-zero/load-discard, a mixed memory+ALU program), **the `0.6` 32-bit W tests
  (a `ADD`/`SUB` W zero-extend with high source bits set, a 32-bit wrap, `SUBS`/
  `ADDS` W setting `N`/`Z`/`C`/`V` on the 32-bit result — each cross-checked against
  the matching 64-bit op that does *not* set the flag, `MOVZ` W, `ADD` W to `WSP`,
  the `CMP`/`CMN` W discards, a mixed W+X program, and a 32-bit-W carry-back)**,
  twice-and-diff determinism for `T` and the interpreter over a program that
  exercises `LDR`/`STR` and the W forms, carry-back of a branch-taken, a `BL`, an
  `LDR`-result+memory-window, and a 32-bit-W BTOR2 witness through `L`, and the
  end-to-end decide→witness→carry-back through `btor2-smtlib` (z3-gated, incl. a
  `STR`/`LDR` memory round-trip and a 32-bit-W reachability program). Honest tier —
  "validated on the inputs we tried," not `proved`.
- **Scope deferred (named future work, not silently dropped):** the trap flag,
  `BC.cond` (FEAT_HBC), the move-wide siblings `MOVN`/`MOVK` (and the 32-bit `MOVZ`
  with `hw ∈ {2,3}`), the **narrower-width loads/stores** (`LDRB`/`STRB`, halfword,
  32-bit `LDR`/`STR`, `LDRSW`) and the **other addressing modes** (pre/post-index,
  unscaled `LDUR`/`STUR`, register-offset), register-form ALU
  (`ADD`/`SUB`/`ADDS`/`SUBS` shifted-register), and the
  C-undefined-but-ISA-defined wedge (`SDIV` edges, shift masking, `MUL`
  truncation) — each lands as a further widening step under the coverage ratchet
  (BENCHMARKS.md §5). The brief's "memory as an array" target state is **realized**;
  the "trap flag" remains in the *design* (`π` already carries `halted`). (The
  32-bit `sf=0` **ALU/flag** forms are now realized — this widening.)

### Construct coverage + `unsupported` histogram

Measured over the pair's spec-derived slice (`inventory.py`,
`gurdy/pairs/aarch64_btor2`; covered may only grow and nothing previously covered
drops — a *new* construct entering scope adds its probe, growing numerator and
denominator together): **27 / 33 probes covered = 0.818** (was `19/23`). The
covered 27 are the in-scope family in its legal forms — the nineteen `0.5` probes
(`ADD_imm`, `ADD_imm_lsl12`, `ADD_imm_sp_src`, `ADD_imm_sp_dst`, `SUB_imm`,
`SUB_imm_sp`, `MOVZ`, `MOVZ_lsl16`, `SUBS_imm`, `CMP_imm`, `Bcond`, `B`, `BL`,
`ADDS_imm`, `CMN_imm`, `LDR_imm`, `STR_imm`, `LDR_imm_off`, `STR_imm_sp`) plus the
eight `0.6` 32-bit W probes `ADD_imm_w`, `SUB_imm_w`, `MOVZ_w`, `MOVZ_w_lsl16`,
`SUBS_imm_w`, `CMP_imm_w`, `ADDS_imm_w`, `CMN_imm_w` (the prior out-of-scope
`ADD_imm_w` probe is promoted into covered). The 6 remaining out-of-scope probes
each hard-abort, itemized:

| `unsupported` construct | probes blocked |
|--------------------------|---------------:|
| `ldr.w` (32-bit `LDR`, `size=10`) | 1 |
| `ldr.b` (`LDRB`, byte width) | 1 |
| `str.b` (`STRB`, byte width) | 1 |
| `movz.w.hw=0b10` (reserved 32-bit `MOVZ` shift) | 1 |
| `movn` (move-wide sibling) | 1 |
| `movk` (move-wide sibling) | 1 |

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
- **Memory ports straight from the EVM/eBPF BTOR2-hub shape — including the
  array-observability trick.** Adding the first data-memory access needed no new
  BTOR2-core machinery: the `Array bv64 bv8` + conditional emission + the
  per-byte `read`/`write` chains + the `m{i}` window-state pattern were lifted
  verbatim from `evm-btor2` / `ebpf-btor2`. The one non-obvious constraint the
  templates already encode is that **the shared BTOR2 trace exposes only
  bit-vector state, not arrays** — so the memory observable cannot be the array
  itself; it must be a fixed window of bv8 state nodes whose `next` is
  `read(next mem, i)`. The interpreter exposes the identical `m{i}` bytes, and the
  cross-check compares them step-for-step. AArch64-specific were only the
  little-endian byte order (vs EVM's big-endian word), the `imm12 * 8` offset
  scaling, and the **per-class field-31 split taken one step further**: for
  `LDR`/`STR` the *base* `Rn` field 31 is SP but the *transfer* `Rt` field 31 is
  XZR — so `_xt_node` resolves the transfer register separately from `_reg_node`,
  the same SP-vs-XZR distinction the flag-set ops already needed, now split
  *within a single instruction*.
- **The widen-ahead-of-sibling window is now a memory-shaped subset.** The `0.5`
  widening again moves `aarch64-btor2` ahead of `aarch64-sail` (which mirrors
  next): the covered sets differ by exactly the four `LDR`/`STR` probes and the
  projections differ by exactly the `m{i}` window fields. The `aarch64-sail`
  cross-check tests assert this transient subset relationship (sail ⊆ btor2,
  the difference being exactly memory), restored to equality + identical `π` when
  the sibling adds `LDR`/`STR`. The decoder-gate additive pattern (`decode_insn_v5`
  new; `decode_insn_v4` kept as the sail gate) is unchanged.
- **The 32-bit `W` forms are "compute narrow, zero-extend wide" — width is the
  whole subtlety.** Adding the `0.6` `W` forms needed no new state or control
  machinery: a `W` op is the existing `X` lowering with the operand sliced to the
  low 32 bits, the `add`/`sub` at width 32, and the result `uext`-ed back to bv64
  before the *same* `ite(active, …, next)` register write. The two genuine
  subtleties — both caught by tests that contrast a `W` form against the matching
  `X` form on the same inputs — are (1) the result **zero-extends** into `Xd` (the
  upper 32 bits are cleared, *not* preserved; this is also the one A64-vs-RV64
  divergence, since RV64's `*W` ops **sign-extend**), and (2) the flags are computed
  at **32-bit width** (sign bit 31, carry-out bit 32), so a 32-bit carry/overflow
  is independent of the 64-bit one. Parameterizing the flag-node builders
  (`_subs_nzcv`/`_adds_nzcv`) and the interpreter helpers (`_subs_flags32`/
  `_adds_flags32`) by a single `width` kept one source of truth across both widths,
  and (because the 64-bit call sites pass the default `width=64`) left the 64-bit
  translator bytes and interpreter traces **byte-for-byte identical** — verified by
  hashing the `v0.5` outputs against the `v0.6` ones for the whole 64-bit corpus.
- **The widen-ahead window is now a register-width subset.** The `0.6` widening
  again moves `aarch64-btor2` ahead of `aarch64-sail` (which mirrors next): the
  covered sets now differ by exactly the eight 32-bit `W` probes, with `π`
  unchanged (the `W` result lands in the existing 64-bit `x{r}` observable, just
  zero-extended). The `aarch64-sail` cross-check test asserts this transient subset
  relationship (sail ⊆ btor2, the difference being exactly the `W` forms), restored
  to equality when the sibling adds them. The decoder-gate additive pattern
  (`decode_insn_v6` new; `decode_insn_v5` kept as the sail gate) is unchanged.
