# Translation specification — `aarch64-sail` (ALU + flag-set + branches + memory: `ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `ADDS`/`CMN`, `B.cond`, `B`/`BL`, `LDR`/`STR`)

This is the self-contained, reviewable specification the `aarch64-sail`
translator implements mechanically (PAIRING.md §2). The translator (`T`,
`translate.py`) binds an AArch64 image into the **Sail object** the shared Sail
interpreter executes via its *additive* AArch64 arm
(`languages/sail/aarch64.py`); the target-to-source interpreter (`L`,
`lift.py`) re-projects the Sail-model state back onto the AArch64 observables.
The commuting square is cross-checked by running both under the projection `π`
(PAIRING.md §6).

Status: **partial** (PAIRING.md §1 "Start thin, then widen"). Sail interp `0.6`
adds the **first memory access** — the 64-bit unsigned-offset `LDR`/`STR` — to
the `0.5` family (`ADD`/`SUB` immediate + `MOVZ` + `SUBS`/`CMP` + `ADDS`/`CMN` +
the conditional `B.cond` + the unconditional `B`/`BL` — all 64-bit), the **same
in-scope set `aarch64-btor2` covers** (their covered sets coincide **exactly**,
19/23 — full branch agreement restored); everything else hard-aborts with a
typed `unsupported: aarch64:<construct>` (BENCHMARKS.md §3).

## Why this pair exists

The *indirect* arm of the AArch64→BTOR2 branch. Paired with `sail-btor2`, it is
a second, independent encoding of A64 into BTOR2 — to be cross-checked at BTOR2
against the direct `aarch64-btor2` route (PATHS.md §4-5), the same
fidelity-raising structure RISC-V has via `riscv-sail`. It therefore covers the
**same in-scope set** (`ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `ADDS`/`CMN`, `B.cond`,
`B`/`BL`, `LDR`/`STR` — all 64-bit) on the **same spec-derived yardstick** and
with the **same `π`** as `aarch64-btor2`, so the two routes decide the same
constructs and their covered sets coincide exactly (19/23).

## Languages

- **Source.** AArch64 (A64), the shared interpreter `languages/aarch64`
  (interpreter version `0.5`) — reused **unchanged** as `I_s`, never forked; it
  already decodes `ADD`/`SUB` immediate + `MOVZ` + `SUBS`/`CMP` + `ADDS`/`CMN` +
  `B.cond` + `B`/`BL` + the 64-bit unsigned-offset `LDR`/`STR` via
  `decode_insn_v5`, and exposes the byte-memory window `m0`–`m{MEM_WINDOW-1}`.
  Observables (post-step, ARCHITECTURE.md §5): `pc` (byte address), `x0`–`x30`,
  `sp`, `nzcv` (the NZCV flags as a bv4, packed `N=bit3, Z=bit2, C=bit1, V=bit0`),
  the memory window `m0`–`m{MEM_WINDOW-1}` (the lowest `MEM_WINDOW = 64` memory
  bytes), `halted`.
- **Target.** Sail, the shared interpreter `languages/sail` (interpreter version
  `0.6`) — reused as `I_t`. This pair contributes an **additive** AArch64 arm to
  that interpreter (`languages/sail/aarch64.py`, dispatched on the Sail object's
  `isa=aarch64` tag); the RISC-V path is left byte-for-byte unchanged, so the
  `riscv-sail` and `sail-btor2` dependents stay valid (AGENTS.md §3 — a
  versioned event; the version bump is `0.5 → 0.6`, widening the A64 arm from
  `ADD`/`SUB`/`MOVZ` + `SUBS`/`CMP` + `ADDS`/`CMN` + `B.cond` + `B`/`BL` to also
  lower the 64-bit unsigned-offset `LDR`/`STR` over a byte-addressed,
  little-endian memory (a Python byte map; the `Expr` IR is QF_BV-only, so only
  the LE byte-assembly is a Sail-derived `Expr` tree) with the additive `m{i}`
  memory-window observable, mirroring the `aarch64-btor2` `0.5` widening so the
  two AArch64→BTOR2 routes decide the same constructs again, fully).

## The Sail object `T` emits

A deterministic JSON record (keys sorted for byte-stability):

```
{ "isa": "aarch64",
  "words": [u32, ...],        # the A64 instruction words, in order
  "entry": int,               # base byte address (pc is a byte address)
  "init_regs": {field: u64},  # initial GPRs; field 31 => sp
  "init_sp": u64,             # initial stack pointer (default 1<<20)
  "init_nzcv": u4,            # initial NZCV flags (default 0)
  "init_mem": {addr: byte} }  # initial byte-addressed memory seed (default empty)
```

`T` first runs every word through the **shared widened AArch64 decoder**
(`languages/aarch64.decode_insn_v5`) — the single rejection point, the *same*
`0.5` gate `aarch64-btor2` uses — so an out-of-scope word hard-aborts before it
can enter the Sail object. The `isa` tag is what dispatches the Sail interpreter
to its A64 arm and is emitted unconditionally. The `init_mem` seed is passed
through so both routes start from the same memory.

## Projection `π`

`{pc, x0..x30, sp, nzcv, m0..m{MEM_WINDOW-1}, halted}` — the AArch64
interpreter's observables read out of the Sail ARM model's state
(`MEM_WINDOW = 64`). This is the exact set the cross-check compares, and it is
**identical** to `aarch64-btor2`'s projection (the `m{i}` window included), so
the branch cross-check at BTOR2 compares like with like (pairs/aarch64-sail
brief).

## The lowering rules (the in-scope family)

The Sail interpreter's A64 arm executes each instruction by evaluating its
**Sail-derived `Expr` tree** over the shared QF_BV vocabulary
(`languages/sail/expr`), the *same* evaluator the RISC-V Sail route uses. The
shared `decode_insn_v5` tags each in-scope word with an op kind
(`add`/`sub`/`movz`/`subs`/`adds`/`bcond`/`b`/`ldr`/`str`) and the operands
`(rd, rn, imm)` (for `LDR`/`STR`, `rd` is the transfer register `Rt` and `rn` is
the base register; plus `cond`/`offset`/`link` for the branches); the per-op
`Expr` mirrors `aarch64-btor2`'s datapath bit-for-bit (one source of truth). The
ALU ops are a single register write with successor `next pc := pc + 4` and
`nzcv := nzcv`; `SUBS`/`CMP` and `ADDS`/`CMN` add the NZCV write (with the
subtraction and addition `C`/`V` definitions respectively); `B.cond` writes only
`pc` (a conditional successor); `B`/`BL` write `pc` unconditionally (`BL` also
writes the link register `x30`); `LDR`/`STR` access the byte-addressed memory
(successor `pc + 4`, no flag write). The *decode* is the shared decoder's; the
*semantics* — including the `SUBS`/`CMP` and `ADDS`/`CMN` flag packs, the
`B.cond` condition predicate, and the `LDR`/`STR` LE byte-assembly — is the
independent Sail `Expr` realization, not the hand-written `+`/`-` of the AArch64
interpreter nor the BTOR2 ITE datapath of `aarch64-btor2`. That independence is
what makes the branch a real cross-check.

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

### `ADDS (immediate)` / `CMN (immediate)`, 64-bit — the addition NZCV write

Same Add/subtract-immediate class with `op=0, S=1` (`CMN Xn, #imm` is
`ADDS XZR, Xn, #imm`). `imm` is the 12-bit immediate, optionally `LSL #12`. The
*source* field 31 is **SP**; the *destination* field 31 is the **zero register
`XZR`** (so `ADDS XZR, …` = `CMN`: the register write is discarded, only `nzcv`
is set). **The `C`/`V` definitions are the *addition* versions — distinct from
`SUBS`'s subtraction definitions.**

```
result := evaluate( add( var("a",64), const(imm,64) ),  {a: read(Rn)} )   (mod 2^64)
write(Rd, result)                       (Rn == 31 reads `sp`; Rd == 31 is XZR: discarded)
NZCV   := evaluate( pack4( N, Z, C, V ), {a: read(Rn)} )   where
            N = slice[63:63] result
            Z = eq(result, 0)
            C = slice[64:64]( zext(a,65) + zext(imm,65) )   (1 == unsigned carry-out)
            V = and( not(xor(a<63>, imm<63>)), xor(result<63>, a<63>) )   (signed overflow)
```

`C` is the **carry-out**: both operands are zero-extended to 65 bits, added (a
bv65 `add`), and bit 64 is sliced out (`= 1` iff the 65-bit sum overflowed 64
bits). `V` is the *same-sign-in* (`not(a<63> xor imm<63>)`) and *sign-flip-out*
(`result<63> xor a<63>`) conjunction. **Contrast with `SUBS`:** there
`C = ¬ult(a, imm)` (no-borrow) and `V` uses *different-sign-in*; here `C` is the
carry-out and `V` uses *same-sign-in* — the addition flag definitions. The four
bv1 flags are `concat`-packed MSB-first into the bv4 `nzcv`, the whole pack one
`Expr` tree evaluated by the same `evaluate`, mirroring `interp._adds_flags` and
`aarch64-btor2._adds_nzcv` bit-for-bit.

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
`BC.cond` (bit[4] = 1, FEAT_HBC) remains out of scope and hard-aborts.

### `B` / `BL` — the unconditional branch

Encoding (A64): `op 0 0 1 0 1 imm26` (Unconditional branch (immediate) class,
bits[30:26] = `00101`; bit[31] = `op` is the **link bit**: `0` = `B`, `1` = `BL`).
`imm26` (bits[25:0]) is a signed instruction offset; the byte displacement is
`offset = SignExtend(imm26, 26) * 4`, and the branch target is `pc + offset`. The
branch is **always taken** — it is the `B.cond` lowering with the condition fixed
to `true`. `B` reads/writes no flags and no registers; `BL` additionally writes
the link register `x30 := pc + 4` (the byte address of the instruction after the
`BL` — the return address):

```
B :   next pc := pc + offset                         (always taken)
BL:   x30     := pc + 4                               (link register = return addr)
      next pc := pc + offset
```

The A64 arm computes the successor directly (`pc := pc + offset`, mod 2^64) — an
always-taken successor needs no condition `Expr`, the degenerate `cond = true`
case of `B.cond`. For `BL`, `x30` is written `pc + 4` *before* the branch. This
mirrors `interp._execute`'s `OP_B` case (`if link: x30 := pc + 4; next_pc :=
pc + offset`) and `aarch64-btor2`'s `OP_B` lowering bit-for-bit. Backward
branches (a negative `imm26`) are the loop back-edge and fall out for free; a
forward branch past the code end triggers the off-end halt.

### `LDR` / `STR` (64-bit, unsigned offset) — the first memory access

Encoding (A64): `size 1 1 1 V 0 1 opc imm12 Rn Rt` (Load/store register, unsigned
immediate class — bits[29:27] = `111`, bit[26] `V` = 0, bits[25:24] = `01`).
`size` (bits[31:30]) = `11` is the 64-bit form (the only width in scope). `opc`
(bits[23:22]): `00` = `STR` (store), `01` = `LDR` (load). `imm12` (bits[21:10]) is
the **unsigned** offset, **scaled by the access size 8**: `imm = imm12 * 8`. The
base `Rn` (bits[9:5]) field 31 is **SP**; the transfer `Rt` (bits[4:0]) field 31
is the **zero register `XZR`** (a store of `XZR` writes 0; a load to `XZR` is
discarded) — never SP. The effective address is `ea = read(Rn) + imm` (mod 2^64).

```
STR:  mem[ea .. ea+7] := bytes_LE( (Rt == 31) ? 0 : read(Rt) )   (Rn 31 => SP base)
LDR:  Rt := word_LE( mem[ea .. ea+7] )    (Rt == 31 is XZR: load discarded)
```

**Memory model.** Memory is byte-addressed and **little-endian** (AArch64 is LE),
held as a Python byte map in the executor state — exactly the RISC-V Sail
executor's shape. The Sail `Expr` IR is QF_BV-only (no arrays), so the *bytes*
live in the map and only the **LE byte-assembly datapath** is a Sail-derived
`Expr` tree, mirroring `aarch64-btor2`'s `_mem_load_le` / `_mem_store_le`
bit-for-bit:

- **`LDR`**: the 8 bytes `mem[ea + i]` (`i = 0..7`, byte `i` read from the map,
  default 0) bind to byte variables `b0..b7`, and the value is
  `evaluate( concat(b7, …, concat(b1, b0)) )` — a bv64 with `b0` (the byte at
  `ea`) least significant (LE). `Rt`'s register is written the loaded value (no
  write when `Rt == 31` = XZR).
- **`STR`**: byte `i` of the bv64 value is `evaluate( slice[8i+7 : 8i](v) )` and
  written to `mem[ea + i]` (the byte at `ea` is `slice[7:0]`, the least
  significant, = LE). A store of `XZR` (`Rt == 31`) writes the constant 0.

**The memory window.** The post-step memory observable reaches `π` through a
fixed window of bv8 bytes `m0 .. m{MEM_WINDOW-1}` (`MEM_WINDOW = 64`): `m{i}` is
`mem[i]` after each step (default 0). The shared AArch64 interpreter exposes the
identical `m{i}` bytes, so the cross-check compares memory step-for-step; and
`aarch64-btor2`'s BTOR2 window-state nodes track the same bytes, so the branch
cross-check at BTOR2 compares like with like. (64 bytes covers the low-address
accesses of the corpus; it is a window, not the whole address space.) `LDR`/`STR`
read/write no flags; the successor pc is the ALU fall-through `pc + 4`.

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
   reads/writes the `sp` slot for field 31. For `SUBS`/`CMP` and `ADDS`/`CMN` the
   *source* field 31 is SP but the *destination* field 31 is the **zero register
   `XZR`** (the `CMP`/`CMN` write-discard). For `MOVZ` (move-wide) it is instead
   the **zero register `XZR`**: a write to `Rd == 31` is discarded, not routed to
   `sp`. For `LDR`/`STR` the *base* field 31 (`Rn`) is **SP** but the *transfer*
   field 31 (`Rt`) is **`XZR`** (a load to `XZR` is discarded; a store of `XZR`
   writes 0) — never `SP`, so the field-31 split is *within a single instruction*.
   (Note: this is exactly why the RISC-V Sail executor — 32 GPRs, `x0`
   hardwired-zero, no `sp`/`nzcv` — cannot represent A64 directly; hence the
   additive A64 arm rather than a reuse of the RISC-V path.)
3. **NZCV.** `ADD`/`SUB`/`MOVZ`, `B`/`BL` and `LDR`/`STR` leave `NZCV` unchanged;
   `SUBS`/`CMP` writes it with the *subtraction* definitions (`C = ¬ult(a, imm)`
   no-borrow, `V` from *different-sign* operands) and `ADDS`/`CMN` with the
   *addition* definitions (`C` = unsigned carry-out of the 65-bit `a + imm` sum,
   `V` from *same-sign* operands); both share `N = result<63>`, `Z = result == 0`.
   **The addition and subtraction `C`/`V` definitions are genuinely distinct** —
   got right per op. `B.cond` reads `NZCV` and writes only `pc`. `nzcv`'s presence
   keeps `π` compatible with `aarch64-btor2`.
4. **`B.cond` is the first op whose successor is not `pc + 4`** — RV64's
   conditional branches (`BEQ`/…) are the analogue, but compare *registers*
   rather than read a flag register; A64 separates the compare (`SUBS`/`CMP`/
   `ADDS`/`CMN`, which set `NZCV`) from the branch (`B.cond`, which reads `NZCV`).
   `B`/`BL` are the *unconditional* successor (`pc + offset`, `offset` =
   sign-extended `imm26 * 4`); `BL` writes the return address to `x30`, the
   analogue of RV64's `JAL rd`.
5. **Memory.** `LDR`/`STR` access byte-addressed memory at `read(Rn) + imm`
   (`imm = imm12 * 8`, the 12-bit unsigned offset scaled by the 8-byte access
   size), **little-endian** (AArch64 is LE — the byte at `ea` is the least
   significant). Memory is a Python byte map (zero-initialized; bytes never written
   read 0); only the LE byte-assembly is a Sail-derived `Expr` tree (the IR is
   QF_BV-only, no arrays). The observable reaches `π` through the fixed window
   `m0..m{MEM_WINDOW-1}`. **No alignment restriction** — the byte map handles any
   `ea`. RV64's `LD`/`SD` are the direct analogue with the same LE byte order; A64
   scales the unsigned offset by the access size where RV64 uses a signed byte
   offset, and A64's `Rt` field 31 is `XZR` (RV64 `x0`).

## Out of scope (hard-aborts, itemized in the `unsupported` histogram)

The 32-bit (`sf=0`) forms, the move-wide siblings `MOVN`/`MOVK`, `BC.cond`
(FEAT_HBC), the **narrower-width and other-mode loads/stores** (`LDRB`/`STRB` and
the other byte/halfword widths, the 32-bit `LDR`/`STR` `size=10`, `LDRSW`, and the
pre/post-index and unscaled `LDUR`/`STUR` modes — only the 64-bit `size=11`
*unsigned-offset* form is in scope), and every other encoding (`NOP`, `RET`, …)
raise `unsupported: aarch64:<construct>` at decode time — never silently dropped or
mis-lowered. The shared `decode_insn_v5` is the single rejection point, used by
`T` and by the Sail A64 arm alike.

## Fidelity

`checked` — the commuting-square oracle walks `I_s(p)` against `L(I_t(T(p)))`
under `π` on the test corpus every run, and the coverage probes assert the typed
aborts. This *also* validates the shared AArch64 interpreter against the
Sail-derived realization — a strong independent check, exactly as `riscv-sail`
does for RISC-V. Evidence: `tests/test_aarch64_sail_pair.py` (per-op square for
`ADD`/`SUB`/`MOVZ`, plus `SUBS`/`CMP` setting each of `N`/`Z`/`C`/`V` and
`ADDS`/`CMN` setting each of `N`/`Z`/`C`(unsigned carry-out)/`V`(signed overflow)
— the latter with a carry-out case, a signed-overflow case, the `CMN` discard, the
SP source, and that ADDS's `C`/`V` differ from `SUBS`'s on the same operands —
`B.cond` taken vs not-taken over the full condition table + a `CMP`-then-`B.EQ`
branching program and a back-branch loop, the unconditional `B`/`BL` (a forward
`B` skipping an instruction, a backward `B` loop back-edge, and `BL`'s link
register `x30`); the `0.6` memory ops — a `STR`-then-`LDR` round-trip, a load from
never-written memory returning 0, the SP-relative addressing form, the
little-endian `m{i}` window byte order, the `Rt = XZR` store-zero / load-discard,
and a mixed memory+ALU program; twice-and-diff determinism for both `T` and the
Sail A64 arm over a program that exercises `LDR`/`STR`; carry-back of a
branch-taken, a `BL`, and an `LDR`-result+memory-window run; coverage/rejection/
ratchet and a coverage-level **equality** check that the two routes' covered sets
coincide exactly; and a branch-agreement check against `aarch64-btor2` covering the
`SUBS`/`CMP` and `ADDS`/`CMN` flag packs, the full `B.cond` condition table, the
unconditional `B`/`BL`, and the `LDR`/`STR` memory ops + the `m{i}` window — the
SP-vs-XZR field-31 distinction included).

**Honest non-claims.** This is *not* `proved`. There is no Arm `sail_riscv_sim`
equivalent wired here (the RISC-V Sail differential is RISC-V-only), so an
**Arm Sail-emulator differential is named future work**, not evidence claimed
here (pairs/aarch64-sail brief "Oracle / tooling gap"). The independent oracle
this slice actually has is the commuting-square cross-check and the
branch-agreement with `aarch64-btor2`.
