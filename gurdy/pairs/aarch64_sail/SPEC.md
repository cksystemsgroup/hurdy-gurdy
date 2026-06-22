# Translation specification — `aarch64-sail` (thin `ADD (immediate)` slice)

This is the self-contained, reviewable specification the `aarch64-sail`
translator implements mechanically (PAIRING.md §2). The translator (`T`,
`translate.py`) binds an AArch64 image into the **Sail object** the shared Sail
interpreter executes via its *additive* AArch64 arm
(`languages/sail/aarch64.py`); the target-to-source interpreter (`L`,
`lift.py`) re-projects the Sail-model state back onto the AArch64 observables.
The commuting square is cross-checked by running both under the projection `π`
(PAIRING.md §6).

Status: **partial** (PAIRING.md §1 "Start thin, then widen"). Exactly one
in-scope construct; everything else hard-aborts with a typed
`unsupported: aarch64:<construct>` (BENCHMARKS.md §3).

## Why this pair exists

The *indirect* arm of the AArch64→BTOR2 branch. Paired with `sail-btor2`, it is
a second, independent encoding of A64 into BTOR2 — to be cross-checked at BTOR2
against the direct `aarch64-btor2` route (PATHS.md §4-5), the same
fidelity-raising structure RISC-V has via `riscv-sail`. It therefore covers the
**same construct** (`ADD (immediate)`, 64-bit) with the **same `π`** as
`aarch64-btor2`, so the two routes decide the same thing.

## Languages

- **Source.** AArch64 (A64), the shared interpreter `languages/aarch64`
  (interpreter version `0.1`) — reused as `I_s`, never forked. Observables
  (post-step, ARCHITECTURE.md §5): `pc` (byte address), `x0`–`x30`, `sp`,
  `nzcv` (the NZCV flags as a bv4), `halted`.
- **Target.** Sail, the shared interpreter `languages/sail` (interpreter version
  `0.2`) — reused as `I_t`. This pair contributes an **additive** AArch64 arm to
  that interpreter (`languages/sail/aarch64.py`, dispatched on the Sail object's
  `isa=aarch64` tag); the RISC-V path is left byte-for-byte unchanged, so the
  `riscv-sail` and `sail-btor2` dependents stay valid (AGENTS.md §3 — a
  versioned event; the version bump is `0.1 → 0.2`).

## The Sail object `T` emits

A deterministic JSON record (keys sorted for byte-stability):

```
{ "isa": "aarch64",
  "words": [u32, ...],        # the A64 instruction words, in order
  "entry": int,               # base byte address (pc is a byte address)
  "init_regs": {field: u64},  # initial GPRs; field 31 => sp
  "init_sp": u64,             # initial stack pointer (default 1<<20)
  "init_nzcv": u4 }           # initial NZCV flags (default 0)
```

`T` first runs every word through the **shared AArch64 decoder**
(`languages/aarch64.decode`) — the single rejection point — so an out-of-scope
word hard-aborts before it can enter the Sail object. The `isa` tag is what
dispatches the Sail interpreter to its A64 arm and is emitted unconditionally.

## Projection `π`

`{pc, x0..x30, sp, nzcv, halted}` — the AArch64 interpreter's observables read
out of the Sail ARM model's state. This is the exact set the cross-check
compares, and it is **identical** to `aarch64-btor2`'s projection, so the branch
cross-check at BTOR2 compares like with like (pairs/aarch64-sail brief).

## The one lowering rule — `ADD (immediate)`, 64-bit

The Sail interpreter's A64 arm executes each instruction by evaluating its
**Sail-derived `Expr` tree** over the shared QF_BV vocabulary (`languages/sail/expr`),
the *same* evaluator the RISC-V Sail route uses. For `ADD (immediate)`:

```
result := evaluate( add( var("a",64), const(imm,64) ),  {a: read(Rn)} )   (mod 2^64)
write(Rd, result)                      (Rn/Rd == 31 read/write `sp`)
next pc := pc + 4
nzcv    := nzcv                         (ADD does not set flags; only ADDS does)
```

The decode (`(rd, rn, imm)`, with `imm = imm12 << (12 if sh==01 else 0)` and
field `31` ⇒ SP) is the shared decoder's; the *semantics* is the independent
Sail `Expr` realization — not the hand-written `+` of the AArch64 interpreter
nor the BTOR2 ITE datapath of `aarch64-btor2`. That independence is what makes
the branch a real cross-check.

## Soundness story (PAIRING.md §6)

`T` and `L` share one source of truth — the per-construct lowering above and the
shared AArch64 decoder — and the commuting-square oracle runs both on the same
inputs, asserting agreement under `π`. Because both interpreters record
**post-step** state and both halt by running off the end of code, the two
traces align **step-for-step** (no one-cycle shift; that shift is only the BTOR2
route's, whose first row is the initial state). A divergence localizes to a
(step, observable). Onward, carried by `sail-btor2`, the **branch** corroborates
against the direct `aarch64-btor2` route at BTOR2 (PATHS.md §4).

## Halting

There is **no halt instruction** in this slice. The Sail A64 arm appends a final
`halted=True` state when `pc` leaves `[entry, entry + 4·n)` — exactly mirroring
the shared AArch64 interpreter's "ran off the end" halt — so the two traces
share the same length and align under `π`.

## A64-vs-RV64 divergence notes (auditable assumptions, carried from the source)

1. **PC is a byte address**; the fall-through is `pc + 4` (A64 instructions are
   4 bytes). No RV64C 2-byte compressed case exists in A64.
2. **Register field 31 = SP**, not a hardwired zero register. The A64 arm
   reads/writes the `sp` slot for field 31. (Note: this is exactly why the
   RISC-V Sail executor — 32 GPRs, `x0` hardwired-zero, no `sp`/`nzcv` — cannot
   represent A64 directly; hence the additive A64 arm rather than a reuse of the
   RISC-V path.)
3. **`ADD` leaves `NZCV` unchanged.** Only `ADDS` writes flags (out of scope),
   so `nzcv` is threaded through untouched; its presence keeps `π` compatible
   with `aarch64-btor2`.

## Out of scope (hard-aborts, itemized in the `unsupported` histogram)

`SUB (immediate)`, `ADDS`/`SUBS` (flag-setting), the 32-bit (`sf=0`) form, and
every non-`Add/subtract-immediate` encoding (`MOVZ`, `NOP`, `RET`, `LDR`, `B`,
…) raise `unsupported: aarch64:<construct>` at decode time — never silently
dropped or mis-lowered. The shared decoder is the single rejection point, used
by `T` and by the Sail A64 arm alike.

## Fidelity

`checked` — the commuting-square oracle walks `I_s(p)` against `L(I_t(T(p)))`
under `π` on the test corpus every run, and the coverage probes assert the typed
aborts. This *also* validates the shared AArch64 interpreter against the
Sail-derived realization — a strong independent check, exactly as `riscv-sail`
does for RISC-V. Evidence: `tests/test_aarch64_sail_pair.py` (square +
twice-and-diff determinism for both `T` and the Sail A64 arm + carry-back +
coverage/rejection + a branch-agreement sanity check against `aarch64-btor2`).

**Honest non-claims.** This is *not* `proved`. There is no Arm `sail_riscv_sim`
equivalent wired here (the RISC-V Sail differential is RISC-V-only), so an
**Arm Sail-emulator differential is named future work**, not evidence claimed
here (pairs/aarch64-sail brief "Oracle / tooling gap"). The independent oracle
this slice actually has is the commuting-square cross-check and the
branch-agreement with `aarch64-btor2`.
