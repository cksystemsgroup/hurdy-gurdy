# Pair — `aarch64-sail`  ·  AArch64 → SAIL

*Status: **partial** (simple-ALU slice: `ADD`/`SUB` immediate + `MOVZ`, all
64-bit). A vertical slice is built — `gurdy/pairs/aarch64_sail/`
(`translate.py` = `T`, `lift.py` = `L`, `inventory.py`, `SPEC.md`), tested by
`tests/test_aarch64_sail_pair.py`. Motivated by the research in
[`REGISTRY.md`](../../REGISTRY.md) — Arm has an official Sail model.*

Lift an AArch64 program into its execution under the **ARM model written in
Sail** (`sail-arm`, auto-translated from Arm's ASL and validated against
Arm's Architecture Compliance Kit). Paired with `sail-btor2`, this is the
**indirect** arm of an AArch64→BTOR2 branch, to be cross-checked against the
direct `aarch64-btor2` translator — the same fidelity-raising structure
RISC-V has via `riscv-sail` ([`PATHS.md`](../../PATHS.md) §4–5). Its reason
to exist is that corroboration: two independent encodings of A64 semantics
meeting at BTOR2.

## What is built (the slice)

A small family of simple, no-flag/no-control-flow ALU register writes —
`ADD (immediate)`, `SUB (immediate)` (both 64-bit) and `MOVZ` (64-bit), the
**same in-scope set** and the **same** `π` as `aarch64-btor2` — translated
end-to-end through the commuting square; every other A64 instruction hard-aborts
with a typed `unsupported: aarch64:<construct>`
([`BENCHMARKS.md`](../../BENCHMARKS.md) §3). The translator binds the A64 image
into a Sail object tagged `isa=aarch64`; the shared Sail interpreter runs it via
an **additive** AArch64 arm (`gurdy/languages/sail/aarch64.py`) that evaluates
each instruction's Sail-derived `Expr` tree (`ADD`→`a + imm`, `SUB`→`a - imm`,
`MOVZ`→the constant `imm`) — independent of both the hand-written AArch64
`+`/`-` and the `aarch64-btor2` BTOR2 datapath, which is what makes the branch a
real cross-check. This widening **mirrors** the just-merged `aarch64-btor2`
widening so the two AArch64→BTOR2 routes decide the same constructs and their
covered sets coincide. The Sail interpreter version bumped `0.2 → 0.3` (a
versioned event, [`AGENTS.md`](../../AGENTS.md) §3); the change is strictly
additive (the RISC-V path and the prior `ADD` behavior are byte-for-byte
unchanged) and the `riscv-sail` / `sail-btor2` dependents stay green.

### Coverage / `unsupported` histogram

Construct coverage **8 / 12** probes (was 4/12, the `ADD`-only slice; the
coverage ratchet only grows, [`BENCHMARKS.md`](../../BENCHMARKS.md) §5). The
in-scope family translates in all its legal forms — `ADD` (base, `LSL #12`, SP
source, SP dest), `SUB` (base, SP src+dst), `MOVZ` (base, `LSL #16`) — and the 4
out-of-scope probes all hard-abort, measured on the **same** spec-derived
12-probe slice as `aarch64-btor2` (`inventory.py`, `coverage()`; a test pins that
the two covered sets coincide):

| out-of-scope probe | typed abort |
|--------------------|-------------|
| `ADDS_imm`  | `unsupported: aarch64:adds.immediate` |
| `ADD_imm_w` | `unsupported: aarch64:add.immediate.w` (32-bit `sf=0`) |
| `LDR_imm`   | `unsupported: aarch64:opcode=…` (memory) |
| `B`         | `unsupported: aarch64:opcode=…` (control flow) |

Each is itemized, none silently dropped — the honest-failure rule
([`BENCHMARKS.md`](../../BENCHMARKS.md) §3).

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** AArch64 — [`languages/aarch64`](../../languages/aarch64/README.md).
- **Target.** Sail — [`languages/sail`](../../languages/sail/README.md).
- **Translator `T`** (`translate.py`). Binds an AArch64 image (+ scope) into a
  Sail object — a deterministic JSON record `{isa:"aarch64", words, entry,
  init_regs, init_sp, init_nzcv}` (keys sorted for byte-stability) — that the
  shared Sail interpreter executes. The translator is thin; the semantics live
  in the Sail interpreter's A64 arm. Decoding is delegated to the shared widened
  AArch64 decoder (`decode_insn`), the single rejection point. *(Driving the
  Sail-generated `sail-arm` executable directly, rather than the in-house
  Sail-derived `Expr` realization, is the natural widening path — see "Oracle /
  tooling gap".)*
- **Source interpreter.** The **shared** AArch64 interpreter
  ([`languages/aarch64`](../../languages/aarch64/README.md)) — reused **as-is,
  unchanged** at v0.2 (it already decodes `ADD`/`SUB` immediate + `MOVZ`).
- **Target interpreter.** The **shared** Sail interpreter
  ([`languages/sail`](../../languages/sail/README.md)) — reused; this pair
  contributes an **additive, versioned** A64 arm to it (`isa=aarch64` dispatch,
  v0.2 → v0.3 — widened from `ADD`-only to `ADD`/`SUB`/`MOVZ`), leaving the
  RISC-V path byte-for-byte unchanged.
- **Target-to-source interpreter `L`.** Carries a Sail-model behavior back
  to an AArch64 behavior by re-projecting the Sail architectural state onto
  the AArch64 observables. Because both ends describe the same ISA, this is
  largely a re-projection. Pair-owned.

## Projection `π`

The AArch64 observables — post-step `pc`, `x0`–`x30`, `sp`, `NZCV`,
halt/trap — read out of the Sail ARM model's state. `π` **must match**
`aarch64-btor2`'s projection so the branch cross-check at BTOR2 compares
like with like ([`pairs/aarch64-btor2`](../aarch64-btor2/README.md)).

## Fidelity target + evidence

- **`checked`** (achieved on the slice) — the commuting-square oracle walks the
  shared AArch64 interpreter's trace against `L(I_sail(T(p)))` under `π` on the
  test corpus every run (`square()`, `tests/test_aarch64_sail_pair.py`), with
  twice-and-diff determinism for both `T` and the additive Sail A64 arm,
  carry-back, and the coverage/rejection/ratchet probes. This also validates the
  shared AArch64 interpreter against the independent Sail-derived realization — a
  strong cross-check, exactly as `riscv-sail` does for RISC-V — and a
  branch-agreement check confirms `aarch64-btor2` and `aarch64-sail` decide the
  `ADD`/`SUB`/`MOVZ` effects identically under `π` (including the SP-vs-XZR
  field-31 distinction), and that the two routes' covered sets coincide.
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
  immediate and `MOVZ`, mirroring `aarch64-btor2`'s widening — the Sail `Expr`
  was just `sub(a, imm)` for `SUB` and the bare `const(imm)` for `MOVZ`; the one
  subtlety was field 31, which is **SP** for `ADD`/`SUB` but **XZR** for `MOVZ`
  so the `MOVZ` write to `Rd==31` must be discarded, not routed to `sp`.)*
- **Oracle / tooling gap (still open — named future work).** The development
  image ([`DOCKER.md`](../../DOCKER.md)) pins the *Sail-RISCV* emulator
  (`sail_riscv_sim`), the oracle for `riscv-sail`. The analogous **ARM Sail
  emulator** (driving the official `sail-arm` executable as the gold oracle for
  this pair, the way `riscv-sail` differentials against `sail_riscv_sim`) is
  **not yet in the image** and is **not** part of this slice's evidence — adding
  it (a new pinned layer) is the next fidelity step.
