# Translation specification — `aarch64-sail` (ALU + flag-set + cond. branch: `ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `B.cond`)

This is the self-contained, reviewable specification the `aarch64-sail`
translator implements mechanically (PAIRING.md §2). The translator (`T`,
`translate.py`) binds an AArch64 image into the **Sail object** the shared Sail
interpreter executes via its *additive* AArch64 arm
(`languages/sail/aarch64.py`); the target-to-source interpreter (`L`,
`lift.py`) re-projects the Sail-model state back onto the AArch64 observables.
The commuting square is cross-checked by running both under the projection `π`
(PAIRING.md §6).

Status: **partial** (PAIRING.md §1 "Start thin, then widen"). Sail interp `0.4`
adds the first NZCV write (`SUBS`/`CMP` immediate) and the first conditional
control flow (`B.cond`) to the `0.2`/`0.3` simple-ALU family
(`ADD (immediate)`, `SUB (immediate)`, `MOVZ` — all 64-bit), the **same in-scope
set `aarch64-btor2` covers** (their covered sets coincide exactly, 11/15);
everything else hard-aborts with a typed `unsupported: aarch64:<construct>`
(BENCHMARKS.md §3).

## Why this pair exists

The *indirect* arm of the AArch64→BTOR2 branch. Paired with `sail-btor2`, it is
a second, independent encoding of A64 into BTOR2 — to be cross-checked at BTOR2
against the direct `aarch64-btor2` route (PATHS.md §4-5), the same
fidelity-raising structure RISC-V has via `riscv-sail`. It therefore covers the
**same in-scope set** (`ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `B.cond` — all 64-bit)
on the **same spec-derived yardstick** and with the **same `π`** as
`aarch64-btor2`, so the two routes decide the same constructs and their covered
sets coincide exactly (11/15).

## Languages

- **Source.** AArch64 (A64), the shared interpreter `languages/aarch64`
  (interpreter version `0.3`) — reused **unchanged** as `I_s`, never forked; it
  already decodes `ADD`/`SUB` immediate + `MOVZ` + `SUBS`/`CMP` + `B.cond` via
  `decode_insn_v3`. Observables (post-step, ARCHITECTURE.md §5): `pc` (byte
  address), `x0`–`x30`, `sp`, `nzcv` (the NZCV flags as a bv4, packed
  `N=bit3, Z=bit2, C=bit1, V=bit0`), `halted`.
- **Target.** Sail, the shared interpreter `languages/sail` (interpreter version
  `0.4`) — reused as `I_t`. This pair contributes an **additive** AArch64 arm to
  that interpreter (`languages/sail/aarch64.py`, dispatched on the Sail object's
  `isa=aarch64` tag); the RISC-V path is left byte-for-byte unchanged, so the
  `riscv-sail` and `sail-btor2` dependents stay valid (AGENTS.md §3 — a
  versioned event; the version bump is `0.3 → 0.4`, widening the A64 arm from
  `ADD`/`SUB`/`MOVZ` to also lower `SUBS`/`CMP` (the NZCV pack) and `B.cond` (the
  conditional `pc` update), mirroring the `aarch64-btor2` `0.3` widening so the
  two AArch64→BTOR2 routes decide the same constructs again).

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

`T` first runs every word through the **shared widened AArch64 decoder**
(`languages/aarch64.decode_insn_v3`) — the single rejection point, the *same*
`0.3` gate `aarch64-btor2` uses — so an out-of-scope word hard-aborts before it
can enter the Sail object. The `isa` tag is what dispatches the Sail interpreter
to its A64 arm and is emitted unconditionally.

## Projection `π`

`{pc, x0..x30, sp, nzcv, halted}` — the AArch64 interpreter's observables read
out of the Sail ARM model's state. This is the exact set the cross-check
compares, and it is **identical** to `aarch64-btor2`'s projection, so the branch
cross-check at BTOR2 compares like with like (pairs/aarch64-sail brief).

## The lowering rules (the in-scope family)

The Sail interpreter's A64 arm executes each instruction by evaluating its
**Sail-derived `Expr` tree** over the shared QF_BV vocabulary
(`languages/sail/expr`), the *same* evaluator the RISC-V Sail route uses. The
shared `decode_insn_v3` tags each in-scope word with an op kind
(`add`/`sub`/`movz`/`subs`/`bcond`) and the operands `(rd, rn, imm)` (plus
`cond`/`offset` for `B.cond`); the per-op `Expr` mirrors `aarch64-btor2`'s
datapath bit-for-bit (one source of truth). The ALU ops are a single register
write with successor `next pc := pc + 4` and `nzcv := nzcv`; `SUBS`/`CMP` adds the
NZCV write; `B.cond` writes only `pc` (a conditional successor). The *decode* is
the shared decoder's; the *semantics* — including the `SUBS`/`CMP` flag pack and
the `B.cond` condition predicate — is the independent Sail `Expr` realization,
not the hand-written `+`/`-` of the AArch64 interpreter nor the BTOR2 ITE datapath
of `aarch64-btor2`. That independence is what makes the branch a real cross-check.

### `ADD (immediate)`, 64-bit

`imm = imm12 << (12 if sh==01 else 0)`; field `31` ⇒ **SP** (this encoding class
has no zero register).

```
result := evaluate( add( var("a",64), const(imm,64) ),  {a: read(Rn)} )   (mod 2^64)
write(Rd, result)                      (Rn/Rd == 31 read/write `sp`)
```

### `SUB (immediate)`, 64-bit

Same Add/subtract-immediate class with `op=1`; same `LSL #12` and field-31-=-SP
semantics as `ADD`. The `Expr` is the QF_BV `sub`.

```
result := evaluate( sub( var("a",64), const(imm,64) ),  {a: read(Rn)} )   (mod 2^64)
write(Rd, result)                      (Rn/Rd == 31 read/write `sp`)
```

### `MOVZ`, 64-bit

Move-wide class (`opc=10`); `imm = imm16 << (16*hw)` for `hw ∈ {0,1,2,3}`
(LSL #0/#16/#32/#48). MOVZ has **no source register** and *zeroes* the rest of
`Rd`. In the move-wide class field `31` is the **zero register `XZR`**, not SP —
a write to `Rd == 31` is **discarded**, not routed to `sp` (this SP-vs-XZR
field-31 distinction is the only real subtlety; the A64 arm gets it right).

```
result := evaluate( const(imm,64), {} )   (imm already placed at hw*16, rest 0)
write(Rd, result)                          (Rd == 31 is XZR: the write is discarded)
```

The `Expr` for MOVZ is the bare `const(imm,64)` (no `add`/`sub`); the immediate
already carries the `hw*16` shift, exactly as in `aarch64-btor2`.

### `SUBS (immediate)` / `CMP (immediate)`, 64-bit — the first NZCV write

Same Add/subtract-immediate class with `op=1, S=1` (`CMP Xn, #imm` is
`SUBS XZR, Xn, #imm`). `imm` is the 12-bit immediate, optionally `LSL #12`. The
*source* field 31 is **SP**; the *destination* field 31 is the **zero register
`XZR`** (so `SUBS XZR, …` = `CMP`: the register write is discarded, only `nzcv`
is set).

```
result := evaluate( sub( var("a",64), const(imm,64) ),  {a: read(Rn)} )   (mod 2^64)
write(Rd, result)                       (Rn == 31 reads `sp`; Rd == 31 is XZR: discarded)
NZCV   := evaluate( pack4( N, Z, C, V ), {a: read(Rn)} )   where
            N = slice[63:63] result
            Z = eq(result, 0)
            C = not( ult(a, imm) )                          (1 == no borrow: a >=u imm)
            V = and( xor(a<63>, imm<63>), xor(result<63>, a<63>) )   (signed overflow)
```

`N`/`Z`/`C`/`V` are each a 1-bit `Expr`, then `concat`-packed MSB-first into the
bv4 `nzcv` (`((N::Z)::C)::V`). The whole pack is one `Expr` tree, evaluated by the
same `evaluate` — so the flag *datapath* is Sail-derived, mirroring
`interp._subs_flags` and `aarch64-btor2._subs_nzcv` bit-for-bit.

### `B.cond` — the first conditional control flow

Encoding (A64): `0101010 0 imm19 0 cond` (bits[31:24] = `01010100`, bit[4] = 0).
`imm19` (bits[23:5]) is a signed instruction offset; the byte displacement is
`offset = SignExtend(imm19, 19) * 4`, and the branch target is `pc + offset`.
`cond` (bits[3:0]) is the standard 4-bit condition code. `B.cond` reads `NZCV`
and writes neither registers nor flags — only `pc`:

```
next pc := ite( cond(NZCV), pc + offset, pc + 4 )
```

`cond(NZCV)` is built as a 1-bit `Expr` over the packed `nzcv` bv4 and evaluated
(`evaluate(cond_expr(cond), {nzcv})`): bits `N`/`Z`/`C`/`V` are sliced out,
`cond[3:1]` selects the base predicate, and `cond[0]` inverts it (except
`AL`/`NV` = `111x`, always true). The full table:

| `cond` | name | predicate |
|-------:|------|-----------|
| `0000`/`0001` | EQ/NE | `Z == 1` / `Z == 0` |
| `0010`/`0011` | CS(HS)/CC(LO) | `C == 1` / `C == 0` |
| `0100`/`0101` | MI/PL | `N == 1` / `N == 0` |
| `0110`/`0111` | VS/VC | `V == 1` / `V == 0` |
| `1000`/`1001` | HI/LS | `C ∧ ¬Z` / `¬(C ∧ ¬Z)` |
| `1010`/`1011` | GE/LT | `N == V` / `N ≠ V` |
| `1100`/`1101` | GT/LE | `¬Z ∧ (N == V)` / `¬(¬Z ∧ (N == V))` |
| `1110`/`1111` | AL/NV | always / always |

This is exactly `interp.cond_holds` / `aarch64-btor2._cond_node`, bit-for-bit.
`BC.cond` (bit[4] = 1, FEAT_HBC) and the unconditional `B`/`BL` remain out of
scope and hard-abort.

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
2. **Register field 31 is encoding-class-dependent.** For `ADD`/`SUB`
   (immediate) it is **SP**, not a hardwired zero register — the A64 arm
   reads/writes the `sp` slot for field 31. For `SUBS`/`CMP` the *source* field
   31 is SP but the *destination* field 31 is the **zero register `XZR`** (the
   `CMP` write-discard). For `MOVZ` (move-wide) it is instead the **zero register
   `XZR`**: a write to `Rd == 31` is discarded, not routed to `sp`. (Note: this is
   exactly why the RISC-V Sail executor — 32 GPRs, `x0` hardwired-zero, no
   `sp`/`nzcv` — cannot represent A64 directly; hence the additive A64 arm rather
   than a reuse of the RISC-V path.)
3. **NZCV.** `ADD`/`SUB`/`MOVZ` leave `NZCV` unchanged; `SUBS`/`CMP` is the only
   in-scope op that writes it (`ADDS` stays out of scope this round). `B.cond`
   reads `NZCV` and writes only `pc`. `nzcv`'s presence keeps `π` compatible with
   `aarch64-btor2`.
4. **`B.cond` is the first op whose successor is not `pc + 4`** — RV64's
   conditional branches (`BEQ`/…) are the analogue, but compare *registers*
   rather than read a flag register; A64 separates the compare (`SUBS`/`CMP`,
   which sets `NZCV`) from the branch (`B.cond`, which reads `NZCV`).

## Out of scope (hard-aborts, itemized in the `unsupported` histogram)

The flag-setting `ADDS` (the addition NZCV write — deferred this round), the
32-bit (`sf=0`) forms, the move-wide siblings `MOVN`/`MOVK`, the unconditional
`B`/`BL`, `BC.cond` (FEAT_HBC), and every other encoding (`NOP`, `RET`, `LDR`, …)
raise `unsupported: aarch64:<construct>` at decode time — never silently dropped
or mis-lowered. The shared `decode_insn_v3` is the single rejection point, used
by `T` and by the Sail A64 arm alike.

## Fidelity

`checked` — the commuting-square oracle walks `I_s(p)` against `L(I_t(T(p)))`
under `π` on the test corpus every run, and the coverage probes assert the typed
aborts. This *also* validates the shared AArch64 interpreter against the
Sail-derived realization — a strong independent check, exactly as `riscv-sail`
does for RISC-V. Evidence: `tests/test_aarch64_sail_pair.py` (per-op square for
`ADD`/`SUB`/`MOVZ`, plus `SUBS`/`CMP` setting each of `N`/`Z`/`C`/`V` and
`B.cond` taken vs not-taken over the full condition table + a `CMP`-then-`B.EQ`
branching program and a back-branch loop; twice-and-diff determinism for both `T`
and the Sail A64 arm; carry-back of a branch-taken run; coverage/rejection/ratchet
and a coverage-level **equality** check that the two routes' covered sets coincide
exactly; and a branch-agreement check against `aarch64-btor2` covering the
`SUBS`/`CMP` flag pack and the full `B.cond` condition table — the SP-vs-XZR
field-31 distinction included).

**Honest non-claims.** This is *not* `proved`. There is no Arm `sail_riscv_sim`
equivalent wired here (the RISC-V Sail differential is RISC-V-only), so an
**Arm Sail-emulator differential is named future work**, not evidence claimed
here (pairs/aarch64-sail brief "Oracle / tooling gap"). The independent oracle
this slice actually has is the commuting-square cross-check and the
branch-agreement with `aarch64-btor2`.
