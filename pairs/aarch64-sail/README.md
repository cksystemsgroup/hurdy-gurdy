# Pair — `aarch64-sail`  ·  AArch64 → SAIL

*Status: **partial** (ALU + flag-set + branches + memory + 32-bit W forms:
`ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `ADDS`/`CMN`, `B.cond`, `B`/`BL`, `LDR`/`STR`,
and their 32-bit W variants). A vertical slice is built —
`gurdy/pairs/aarch64_sail/` (`translate.py` = `T`, `lift.py` = `L`,
`inventory.py`, `SPEC.md`), tested by `tests/test_aarch64_sail_pair.py`. Motivated
by the research in [`REGISTRY.md`](../../REGISTRY.md) — Arm has an official Sail
model.*

Lift an AArch64 program into its execution under the **ARM model written in
Sail** (`sail-arm`, auto-translated from Arm's ASL and validated against
Arm's Architecture Compliance Kit). Paired with `sail-btor2`, this is the
**indirect** arm of an AArch64→BTOR2 branch, to be cross-checked against the
direct `aarch64-btor2` translator — the same fidelity-raising structure
RISC-V has via `riscv-sail` ([`PATHS.md`](../../PATHS.md) §4–5). Its reason
to exist is that corroboration: two independent encodings of A64 semantics
meeting at BTOR2.

## What is built (the slice)

The ALU family `ADD (immediate)`, `SUB (immediate)`, `MOVZ`, the NZCV writes
(`SUBS`/`CMP` **and** `ADDS`/`CMN` immediate), the conditional **and**
unconditional control flow (`B.cond`, `B`/`BL`), the first memory access — the
64-bit unsigned-offset `LDR`/`STR` — **and the 32-bit (W-register) forms** of the
ALU/flag-setting immediate instructions (`ADD`/`SUB`/`MOVZ` W and
`SUBS`/`CMP`/`ADDS`/`CMN` W) — the **same in-scope set** and the **same** `π` as
`aarch64-btor2` — translated end-to-end through the commuting square; every other
A64 instruction hard-aborts with a typed
`unsupported: aarch64:<construct>` ([`BENCHMARKS.md`](../../BENCHMARKS.md) §3).
The translator binds the A64 image into a Sail object tagged `isa=aarch64`; the
shared Sail interpreter runs it via an **additive** AArch64 arm
(`gurdy/languages/sail/aarch64.py`) that evaluates each instruction's
Sail-derived `Expr` tree — `ADD`/`ADDS`→`a + imm`, `SUB`/`SUBS`→`a - imm`,
`MOVZ`→the constant `imm`, the `SUBS`/`CMP` and `ADDS`/`CMN` **NZCV packs**
(`N`/`Z`/`C`/`V`, with the subtraction and addition `C`/`V` definitions
respectively) and the `B.cond` **condition predicate** also built as `Expr` trees
over the same vocabulary and evaluated; the unconditional `B`/`BL` is the
always-taken `pc := pc + offset` (`BL` also writes `x30 := pc + 4`); and
`LDR`/`STR` access a **byte-addressed, little-endian memory** (a Python byte map
in the executor state — the `Expr` IR is QF_BV-only, so the bytes live there and
only the **LE byte-assembly** — the `concat` of loaded bytes / the `slice` of the
stored value — is a Sail-derived `Expr` tree, mirroring `aarch64-btor2`'s
`_mem_load_le`/`_mem_store_le`), the effective address `read(Rn) + imm`
(`imm = imm12 * 8`; base field 31 = `SP`, transfer field 31 = `XZR`), carried into
`π` through the `m0`–`m63` memory window. The **32-bit (W-register) forms** compute
on the **low 32 bits** of the source (`slice(a, 31, 0)`), do the op at width 32, and
**zero-extend** the bv32 result into the 64-bit `Xd` (its upper 32 bits become 0 —
A64 zero-extends a W write, the divergence from RV64's sign-extending `*W` ops); the
`SUBS`/`ADDS` W flags are packed at **32-bit** width (sign bit 31, `Z` over the
32-bit result, `C` from the no-borrow / 33-bit carry-out, `V` from the 32-bit signed
overflow) — all realized as `Expr` trees (`slice`/`zext`/width-32 ops) matching
`aarch64-btor2`'s `width`-parameterized datapath bit-for-bit — all independent of
both the hand-written AArch64 `+`/`-`/byte-map and the `aarch64-btor2` BTOR2 ITE
datapath, which is what makes the branch a real cross-check. This widening
**mirrors** the just-merged `aarch64-btor2` 32-bit W-form widening so the two
AArch64→BTOR2 routes decide the same constructs again and their **covered sets +
projections coincide exactly** (full branch agreement restored — the agreement test
is back to `assertEqual`). The Sail interpreter version bumped `0.6 → 0.7` (a
versioned event, [`AGENTS.md`](../../AGENTS.md) §3); the change is strictly additive
(the RISC-V path and the prior 64-bit `ADD`/`SUB`/`MOVZ` + `SUBS`/`CMP` +
`ADDS`/`CMN` + `B.cond` + `B`/`BL` + `LDR`/`STR` behavior are byte-for-byte
unchanged) and the `riscv-sail` / `sail-btor2` dependents stay green. The
translate-edge rejection gate switched from the `0.5` `decode_insn_v5` to the `0.6`
`decode_insn_v6` (exactly as `aarch64-btor2` does).

### Coverage / `unsupported` histogram

Construct coverage **27 / 33** probes (was 19/23; the coverage ratchet only grows
— 8 new in-scope probes (the W forms of `ADD`/`SUB`/`MOVZ` (×2: LSL #0 and #16)/
`SUBS`/`CMP`/`ADDS`/`CMN`), promoting the prior out-of-scope `ADD_imm_w` into
covered, nothing dropped, [`BENCHMARKS.md`](../../BENCHMARKS.md) §5). The in-scope
family translates in all its legal forms — `ADD` (base, `LSL #12`, SP source, SP
dest), `SUB` (base, SP src+dst), `MOVZ` (base, `LSL #16`), `SUBS`, `CMP`, `B.cond`,
`B`, `BL`, `ADDS`, `CMN`, `LDR`/`STR` (base, offset, SP-relative), and the 32-bit W
forms `ADD`/`SUB`/`MOVZ`/`SUBS`/`CMP`/`ADDS`/`CMN` W — and the 6 out-of-scope probes
all hard-abort, measured on the **same** spec-derived 33-probe slice as
`aarch64-btor2` (`inventory.py`, `coverage()`; a test pins that the two covered sets
coincide **exactly**):

| out-of-scope probe | typed abort |
|--------------------|-------------|
| `LDR_imm_w`   | `unsupported: aarch64:ldr.w` (32-bit `LDR`, `size=10`) |
| `LDRB_imm`    | `unsupported: aarch64:ldr.b` (`LDRB`, byte width) |
| `STRB_imm`    | `unsupported: aarch64:str.b` (`STRB`, byte width) |
| `MOVZ_w_hw2`  | `unsupported: aarch64:movz.w.hw=0b10` (reserved 32-bit shift) |
| `MOVN_imm`    | `unsupported: aarch64:movn` (move-wide sibling) |
| `MOVK_imm`    | `unsupported: aarch64:movk` (move-wide sibling) |

Each is itemized, none silently dropped — the honest-failure rule
([`BENCHMARKS.md`](../../BENCHMARKS.md) §3).

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** AArch64 — [`languages/aarch64`](../../languages/aarch64/README.md).
- **Target.** Sail — [`languages/sail`](../../languages/sail/README.md).
- **Translator `T`** (`translate.py`). Binds an AArch64 image (+ scope) into a
  Sail object — a deterministic JSON record `{isa:"aarch64", words, entry,
  init_regs, init_sp, init_nzcv, init_mem}` (keys sorted for byte-stability) —
  that the shared Sail interpreter executes. The translator is thin; the semantics
  live in the Sail interpreter's A64 arm. Decoding is delegated to the shared
  widened AArch64 decoder (`decode_insn_v6`), the single rejection point. *(Driving
  the Sail-generated `sail-arm` executable directly, rather than the in-house
  Sail-derived `Expr` realization, is the natural widening path — see "Oracle /
  tooling gap".)*
- **Source interpreter.** The **shared** AArch64 interpreter
  ([`languages/aarch64`](../../languages/aarch64/README.md)) — reused **as-is,
  unchanged** at v0.6 (it already decodes `ADD`/`SUB` immediate + `MOVZ` +
  `SUBS`/`CMP` + `ADDS`/`CMN` + `B.cond` + `B`/`BL` + the 64-bit unsigned-offset
  `LDR`/`STR` + the 32-bit W-register ALU/flag forms via `decode_insn_v6`, and
  exposes the `m0`–`m63` memory window).
- **Target interpreter.** The **shared** Sail interpreter
  ([`languages/sail`](../../languages/sail/README.md)) — reused; this pair
  contributes an **additive, versioned** A64 arm to it (`isa=aarch64` dispatch,
  v0.6 → v0.7 — widened from `ADD`/`SUB`/`MOVZ` + `SUBS`/`CMP` + `ADDS`/`CMN` +
  `B.cond` + `B`/`BL` + the 64-bit unsigned-offset `LDR`/`STR` to also lower the
  **32-bit (W-register) forms** of the ALU/flag immediate ops — the op runs at width
  32 over `slice(a, 31, 0)` and the bv32 result zero-extends into `Xd`, the
  `SUBS`/`ADDS` W flags packed at 32-bit width), leaving the RISC-V path
  byte-for-byte unchanged.
- **Target-to-source interpreter `L`.** Carries a Sail-model behavior back
  to an AArch64 behavior by re-projecting the Sail architectural state onto
  the AArch64 observables (including the `m0`–`m63` memory window). Because both
  ends describe the same ISA, this is largely a re-projection. Pair-owned.

## Projection `π`

The AArch64 observables — post-step `pc`, `x0`–`x30`, `sp`, `NZCV`, the memory
window `m0`–`m63`, halt/trap — read out of the Sail ARM model's state. `π`
**must match** `aarch64-btor2`'s projection so the branch cross-check at BTOR2
compares like with like ([`pairs/aarch64-btor2`](../aarch64-btor2/README.md)); a
test pins the **equality** of the two projections (the `m{i}` window included).

## Fidelity target + evidence

- **`checked`** (achieved on the slice) — the commuting-square oracle walks the
  shared AArch64 interpreter's trace against `L(I_sail(T(p)))` under `π` on the
  test corpus every run (`square()`, `tests/test_aarch64_sail_pair.py`), with
  twice-and-diff determinism for both `T` and the additive Sail A64 arm,
  carry-back (incl. of a branch-taken, a `BL`, and an `LDR`-result+memory-window
  run), and the coverage/rejection/ratchet probes. This also validates the shared
  AArch64 interpreter against the independent Sail-derived realization — a strong
  cross-check, exactly as `riscv-sail` does for RISC-V — and a branch-agreement
  check confirms `aarch64-btor2` and `aarch64-sail` decide the `ADD`/`SUB`/`MOVZ`
  effects, the `SUBS`/`CMP` and `ADDS`/`CMN` flag packs (`N`/`Z`/`C`/`V`, with the
  subtraction and addition `C`/`V` definitions), the full `B.cond` condition table,
  the unconditional `B`/`BL` (with `BL`'s link register), the `LDR`/`STR` memory ops
  (the little-endian `m{i}` window included), and the **32-bit (W-register) ALU/flag
  forms** (the zero-extend into `Xd` and the 32-bit flag packs — incl. a 32-bit-only
  carry and a 32-bit-only signed-overflow that do *not* occur as 64-bit ops)
  identically under `π` (including the SP-vs-XZR field-31 distinction, split *within*
  `LDR`/`STR`: base `Rn` SP, transfer `Rt` XZR), and that the two routes' covered
  sets coincide **exactly** (the agreement test back to `assertEqual`).
- **Honest non-claim:** *not* `proved`, and the official-`sail-arm`-emulator
  differential is **named future work**, not evidence claimed here (no Arm Sail
  emulator is wired — see "Oracle / tooling gap").

## Soundness story

Direct commuting-square check against the shared Sail interpreter, plus —
carried onward by `sail-btor2` — the **branch** against the direct
`aarch64-btor2` route at BTOR2 ([`PAIRING.md`](../../PAIRING.md) §6,
[`PATHS.md`](../../PATHS.md) §4).

## Notes for the next agent (what this slice taught us)

- Both shared interpreters were already built, so this pair reused both and
  contributed *only* `T`, `L`, `π`, and the additive Sail A64 arm. `π` is kept
  byte-identical to `aarch64-btor2` — the branch is the point (a test pins the
  equality of the two projections).
- **Why the A64 arm had to be additive, not a reuse of the RISC-V path.** The
  RISC-V Sail executor has 32 GPRs with `x0` hardwired-zero and *no* `sp` /
  `nzcv` state, while A64 needs 31 GPRs **plus** a distinct `sp` (register field
  31) and `nzcv`. There aren't enough RISC-V registers to host A64's 32 live
  values, and compiling A64 into RISC-V words inside `T` would bury RISC-V as a
  *hidden* intermediate language ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §9)
  — forbidden. So the honest route is a native A64 arm in the Sail interpreter,
  which is what was built (strictly additive, version-bumped).
- **Widening path.** Add the next A64 constructs to the shared AArch64 decoder
  (the single source of truth) and to the Sail A64 arm's `Expr` lowering in
  lockstep; the coverage ratchet keeps it monotone. *(Done so far: `SUB`
  immediate + `MOVZ` (`0.2 → 0.3`), then `SUBS`/`CMP` + `B.cond` (`0.3 → 0.4`),
  then the unconditional `B`/`BL` + the addition flag-set `ADDS`/`CMN` (`0.4 →
  0.5`), then the **first memory access** — the 64-bit unsigned-offset `LDR`/`STR`
  (`0.5 → 0.6`), then the **32-bit (W-register) ALU/flag forms** (`0.6 → 0.7`),
  each mirroring `aarch64-btor2`'s widening. The `SUBS`/`CMP` and
  `ADDS`/`CMN` **NZCV packs** and the `B.cond` **condition predicate** are all
  built as `Expr` trees over the shared QF_BV vocabulary and evaluated by the same
  `evaluate` — so the flag/condition datapath is Sail-derived too, not hand
  Python; for `SUBS` `C = ¬ult(a, imm)` is the no-borrow flag, for `ADDS` `C` is
  the unsigned carry-out (`slice[64:64](zext(a,65) + zext(imm,65))`) and `V` uses
  *same-sign-in* (distinct from `SUBS`'s *different-sign-in*), and the four flags
  are `concat`-packed MSB-first into the bv4 `nzcv`. Subtleties: field 31 is **SP**
  for `ADD`/`SUB`, **XZR** for `MOVZ`, and for `SUBS`/`CMP`/`ADDS`/`CMN` the
  *source* field 31 is **SP** while the *destination* is **XZR** (the `CMP`/`CMN`
  write-discard); `B.cond` is the first op whose successor is not `pc + 4`, and
  `B`/`BL` are the unconditional successor (`BL` writes the link register `x30`).)*
- **The 32-bit (W-register) forms (`0.6 → 0.7`).** The Add/subtract-immediate and
  Move-wide classes each have a `sf = 0` (W) form; `decode_insn_v6` tags it
  `width = 32`. The one real subtlety vs the 64-bit forms is the
  operand/result/flag **width**, realized entirely in the `Expr` IR: the source
  operand is `slice(a, 31, 0)` (a bv32), the op runs at width 32, and the bv32
  result is `zext`-ed to bv64 before the write — so the upper 32 bits of `Xd`
  become 0 (**A64 zero-extends a W write** — the divergence from RV64's
  sign-extending `*W` ops). The `SUBS`/`ADDS` W flags are packed at 32-bit width
  (the same `_subs_nzcv_expr` / `_adds_nzcv_expr` templates, now parameterized by
  `dec.width`: sign bit `width - 1` = 31, `Z` over the 32-bit result, `C` the
  no-borrow / bit-`width` carry-out of the `width + 1`-bit sum, `V` the 32-bit
  signed overflow). This makes a 32-bit result genuinely distinct from a 64-bit one
  whenever the source has high bits set (ignored then cleared) or the add/sub
  carries/overflows at the 32-bit boundary but not the 64-bit one — the
  branch-agreement corpus pins exactly those 32-bit-only carry/overflow cases.
  Field-31 semantics are unchanged (`ADD`/`SUB` W → `WSP`; `SUBS`/`ADDS` W source
  `WSP` / destination `WZR`; `MOVZ` W → `WZR`); the branches and the (64-bit)
  `LDR`/`STR` ignore `width`. The shared AArch64 source interpreter and the
  `aarch64-btor2` translator are the one source of truth (`_execute`'s `w32` path /
  the `width`-parameterized BTOR2 datapath); the Sail arm mirrors them in `Expr`.
- **Memory in a QF_BV interpreter.** The Sail `Expr` IR is **QF_BV-only — no
  arrays** — so unlike `aarch64-btor2` (which models memory as a BTOR2
  `Array bv64 bv8`), the Sail route keeps the *bytes* in a Python byte map in the
  executor state (exactly the RISC-V Sail executor's shape) and lets only the
  **LE byte-assembly** be a Sail-derived `Expr` tree: `LDR` is the `concat` of the
  8 loaded byte-variables (`b0` = the byte at `ea`, least significant), `STR` is
  the 8 `slice[8i+7:8i]` extractions of the stored value. So the *value* datapath
  stays Sail-derived (independent of the hand-written byte-map and the BTOR2 array
  ITE chain), while memory itself is just state — and the `m0`–`m63` window makes
  it projectable, identical byte-for-byte to `aarch64-btor2`'s window. That is what
  let the branch-agreement test go back to full `assertEqual` (no array support
  needed in the `Expr` IR; the brief's "can't model the memory array cleanly"
  blocker did not arise — the byte-map + window pattern is exactly how the RISC-V
  Sail arm already does memory).
- **Oracle / tooling gap (still open — named future work).** The development
  image ([`DOCKER.md`](../../DOCKER.md)) pins the *Sail-RISCV* emulator
  (`sail_riscv_sim`), the oracle for `riscv-sail`. The analogous **ARM Sail
  emulator** (driving the official `sail-arm` executable as the gold oracle for
  this pair, the way `riscv-sail` differentials against `sail_riscv_sim`) is
  **not yet in the image** and is **not** part of this slice's evidence — adding
  it (a new pinned layer) is the next fidelity step.
