# Translation specification — `aarch64-btor2` (ALU + flag-set + branches + memory + 32-bit W forms: `ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `ADDS`/`CMN`, `B.cond`, `B`/`BL`, `LDR`/`STR`, and their 32-bit W variants)

This is the self-contained, reviewable specification the `aarch64-btor2`
translator implements mechanically (PAIRING.md §2). The translator (`T`,
`translate.py`) and the target-to-source interpreter (`L`, `lift.py`) share one
source of truth — the per-instruction lowering below and the shared AArch64
decoder (`languages/aarch64/interp.py:decode_insn_v6`) — so the commuting square
is cross-checked by running both under the projection `π` (PAIRING.md §6).

Status: **partial** (PAIRING.md §1 "Start thin, then widen"). Interp `0.6` adds
the **32-bit (W-register) forms** of the ALU/flag-setting immediate instructions —
`ADD`/`SUB`/`MOVZ` W and `SUBS`/`CMP`/`ADDS`/`CMN` W — to the `0.5` family
(the 64-bit `ADD`/`SUB`/`MOVZ` + `SUBS`/`CMP` + `ADDS`/`CMN` + `B.cond` +
`B`/`BL` + `LDR`/`STR`); everything else hard-aborts with a typed
`unsupported: aarch64:<construct>` (BENCHMARKS.md §3).

## Languages

- **Source.** AArch64 (A64), the shared interpreter `languages/aarch64`
  (interpreter version `0.6`). Observables (post-step, ARCHITECTURE.md §5):
  `pc` (byte address), `x0`–`x30`, `sp`, `nzcv` (the NZCV flags as a bv4, packed
  `N=bit3, Z=bit2, C=bit1, V=bit0` — MSB-first), the memory window
  `m0`–`m{MEM_WINDOW-1}` (the lowest `MEM_WINDOW = 64` memory bytes, each `0..255`),
  `halted`.
- **Target.** BTOR2, the shared interpreter `languages/btor2` (reused, never
  forked — it already supports arrays).

## Projection `π`

`{pc, x0..x30, sp, nzcv, m0..m{MEM_WINDOW-1}, halted}` — the AArch64 interpreter's
observables mapped onto identically-named BTOR2 state variables (`MEM_WINDOW = 64`).
This is the exact set the cross-check compares. The register/flag/control prefix
is kept compatible with the registered `aarch64-sail` branch; the memory-window
fields `m{i}` are the additive `0.5` extension (the `aarch64-sail` sibling mirrors
the same window when it adds `LDR`/`STR` — until then `aarch64-sail`'s `π` is the
non-memory prefix of this one, a subset, pairs/aarch64-btor2 brief).

## Target state (the BTOR2 transition system `T` emits)

One state node per observable. The register/flag/control state is all
bit-vectors; the byte-addressed memory is a BTOR2 **array**, plus a fixed
bit-vector observable window over its lowest bytes (the BTOR2 trace exposes only
bit-vector state, not arrays):

| node     | sort | meaning |
|----------|------|---------|
| `pc`     | bv64 | byte address of the next instruction |
| `x0..x30`| bv64 | general registers |
| `sp`     | bv64 | stack pointer |
| `nzcv`   | bv4  | condition flags, packed `N=bit3, Z=bit2, C=bit1, V=bit0` |
| `mem`    | `Array bv64 bv8` | byte-addressed data memory (little-endian); emitted only when the program uses `LDR`/`STR` |
| `m0..m{MEM_WINDOW-1}` | bv8 | the memory-window observable: `m{i}` tracks `mem[i]` after each step; emitted only when `mem` is |
| `halted` | bv1  | 1 once `pc` has left the code region |

`init`: `pc = entry`; `xr = init_regs[r]` (default 0); `sp = init_sp`
(default `1<<20`, matching the interpreter's `SP_DEFAULT`); `nzcv = init_nzcv`
(default 0); `halted = 0`; each `m{i} = init_mem[i]` (default 0). The `mem` array
itself is zero-initialized (bytes never written read 0); an initial-memory seed is
supplied to the BTOR2 array through the interpreter's per-state override (the
cross-check `square()` threads `init_mem` into both sides).

The program is fixed, so the next-state of every node is a **PC-keyed ITE
dispatch**: for each instruction at byte address `a = entry + 4*i`, an
`active = (pc == a) ∧ ¬halted` guard selects that instruction's effect. The
successor pc is `a + 4` for every op except the branches: `B.cond`'s successor is
a condition-ITE (below), and `B`/`BL`'s successor is unconditionally `a + offset`.

## The lowering rules (the in-scope family)

The shared `decode_insn_v6` tags each in-scope word with an op kind
(`add`/`sub`/`movz`/`subs`/`adds`/`bcond`/`b`/`ldr`/`str`), a `width` (`64` for the
X-register forms, `32` for the W-register forms — `0.6`), and the operands
`(rd, rn, imm)` (for `LDR`/`STR`, `rd` is the transfer register `Rt` and `rn` is
the base register; plus `cond`/`offset`/`link` for the branches). `T` and the
interpreter mirror the *same* per-op effect bit-for-bit (one source of truth). The
ALU ops are a single register write with successor `next pc := a + 4`;
`ADD`/`SUB`/`MOVZ` leave `nzcv` untouched, `SUBS`/`CMP` and `ADDS`/`CMN` write it
(with the subtraction and addition `C`/`V` definitions respectively), `B.cond`
writes only `pc`, `B`/`BL` write `pc` unconditionally (`BL` also writes the link
register `x30`), and `LDR`/`STR` access `mem` (with successor `a + 4`, no flag
write). The 32-bit (W) ALU/flag forms compute on the low 32 bits, zero-extend the
result into the 64-bit destination, and (for `SUBS`/`ADDS` W) set the flags at
32-bit width — see "The 32-bit (W-register) forms" below.

### `ADD (immediate)`, 64-bit

Encoding (A64): `sf=1 op=0 S=0 1 0 0 0 1 sh imm12 Rn Rd` (Add/subtract-immediate
class, bits[28:24] = `10001`). `imm = imm12 << (12 if sh==01 else 0)`; a register
field value `31` denotes **SP** (this encoding class has no zero register).

```
result := read(Rn) + imm              (mod 2^64)
write(Rd, result)                      (Rn/Rd == 31 read/write `sp`)
```

`T` lowers `result` to a BTOR2 `add` over the `Rn` node and a `constd` of `imm`.

### `SUB (immediate)`, 64-bit

Same Add/subtract-immediate class with `op=1`. Same `LSL #12` and field-31-=-SP
semantics as `ADD`. `T` lowers `result` to a BTOR2 `sub`.

```
result := read(Rn) - imm              (mod 2^64)
write(Rd, result)                      (Rn/Rd == 31 read/write `sp`)
```

### `MOVZ`, 64-bit

Encoding (A64): `sf=1 opc=10 1 0 0 1 0 1 hw imm16 Rd` (Move-wide class,
bits[28:23] = `100101`; `opc=10` is MOVZ). `imm = imm16 << (16*hw)` for
`hw ∈ {0,1,2,3}` (LSL #0/#16/#32/#48). MOVZ has **no source register** and
*zeroes* the rest of `Rd`. In the Move-wide class field `31` is the **zero
register `XZR`**, not SP — a write to `Rd == 31` is **discarded**.

```
result := imm                          (imm16 placed at hw*16, all other bits 0)
write(Rd, result)                      (Rd == 31 is XZR: the write is discarded)
```

`T` lowers `result` to the `constd` of `imm` directly (no `add`/`sub`), and emits
**no** state-node update when `Rd == 31` (the XZR sink).

### `SUBS (immediate)` / `CMP (immediate)`, 64-bit — the first NZCV write

Same Add/subtract-immediate class with `op=1, S=1` (`CMP Xn, #imm` is
`SUBS XZR, Xn, #imm`). `imm` is the 12-bit immediate, optionally `LSL #12`. The
*source* field 31 is **SP**; the *destination* field 31 is the **zero register
`XZR`** (so `SUBS XZR, …` = `CMP`: the register write is discarded, only `nzcv`
is set).

```
result := read(Rn) - imm               (mod 2^64)        (Rn == 31 reads `sp`)
write(Rd, result)                       (Rd == 31 is XZR: the write is discarded)
NZCV := { N = result<63>,
          Z = (result == 0),
          C = (read(Rn) >=u imm),       (1 == no borrow)
          V = (Rn<63> ≠ imm<63>) ∧ (result<63> ≠ Rn<63>) }   (signed overflow)
```

`T` lowers `result` to a BTOR2 `sub`; `N` is a `slice[63:63]` of the result, `Z`
an `eq` with 0, `C` an `ugte`, and `V` an `and` of two sign-difference `xor`s,
then the four bv1 flags are `concat`-packed MSB-first into the bv4 `nzcv`. This
exactly mirrors `interp._subs_flags`.

### `ADDS (immediate)` / `CMN (immediate)`, 64-bit — the addition NZCV write

Same Add/subtract-immediate class with `op=0, S=1` (`CMN Xn, #imm` is
`ADDS XZR, Xn, #imm`). `imm` is the 12-bit immediate, optionally `LSL #12`. The
*source* field 31 is **SP**; the *destination* field 31 is the **zero register
`XZR`** (so `ADDS XZR, …` = `CMN`: the register write is discarded, only `nzcv`
is set). **The `C`/`V` definitions are the *addition* versions — distinct from
`SUBS`'s subtraction definitions.**

```
result := read(Rn) + imm               (mod 2^64)        (Rn == 31 reads `sp`)
write(Rd, result)                       (Rd == 31 is XZR: the write is discarded)
NZCV := { N = result<63>,
          Z = (result == 0),
          C = unsigned carry-out of read(Rn) + imm,       (1 == the 65-bit sum
                                                            overflows 64 bits)
          V = (Rn<63> = imm<63>) ∧ (result<63> ≠ Rn<63>) }  (signed overflow:
                                                              same-sign operands,
                                                              result sign flips)
```

`T` lowers `result` to a BTOR2 `add`; `N` is a `slice[63:63]` of the result, `Z`
an `eq` with 0, and **`C` is the carry-out**: both operands are `uext`-ed to 65
bits, added (a bv65 `add`), and bit 64 is `slice`-d out (`= 1` iff the sum
overflowed 64 bits). `V` is an `and` of *same-sign-in* (`not (Rn<63> xor imm<63>)`)
and *sign-flip-out* (`result<63> xor Rn<63>`). The four bv1 flags are
`concat`-packed MSB-first into the bv4 `nzcv`. This exactly mirrors
`interp._adds_flags`. **Contrast with `SUBS`:** there `C = (Rn >=u imm)`
(no-borrow) and `V` uses *different-sign-in*; here `C` is the carry-out of the add
and `V` uses *same-sign-in* — the addition flag definitions.

### `B.cond` — the first conditional control flow

Encoding (A64): `0101010 0 imm19 0 cond` (bits[31:24] = `01010100`, bit[4] = 0).
`imm19` (bits[23:5]) is a signed instruction offset; the byte displacement is
`offset = SignExtend(imm19, 19) * 4`, and the branch target is `a + offset`.
`cond` (bits[3:0]) is the standard 4-bit condition code. `B.cond` reads `NZCV`
and writes neither registers nor flags — only `pc`:

```
next pc := ite( cond(NZCV), a + offset, a + 4 )
```

`cond(NZCV)` is built bit-for-bit from `interp.cond_holds`: bits `N`/`Z`/`C`/`V`
are sliced out of `nzcv`, `cond[3:1]` selects the base predicate, and `cond[0]`
inverts it (except `AL`/`NV` = `111x`, always true). The full table:

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

The successor pc is then threaded into the PC-keyed dispatch the same way as the
ALU fall-through, so a single `next pc` ITE chain carries both straight-line and
branch successors. `BC.cond` (bit[4] = 1, FEAT_HBC) remains out of scope and
hard-aborts.

### `B` / `BL` — the unconditional branch

Encoding (A64): `op 0 0 1 0 1 imm26` (Unconditional branch (immediate) class,
bits[30:26] = `00101`; bit[31] = `op` is the **link bit**: `0` = `B`, `1` = `BL`).
`imm26` (bits[25:0]) is a signed instruction offset; the byte displacement is
`offset = SignExtend(imm26, 26) * 4`, and the branch target is `a + offset`. The
branch is **always taken** — it is the `B.cond` lowering with the condition fixed
to `true`. `B` reads/writes no flags and no registers; `BL` additionally writes
the link register `x30 := a + 4` (the byte address of the instruction after the
`BL` — the return address):

```
B :   next pc := a + offset                         (always taken)
BL:   x30     := a + 4                               (link register = return addr)
      next pc := a + offset
```

`T` lowers `next pc` to `ite(active, a + offset, next pc)` (no condition node —
unconditional) threaded into the same `next pc` ITE chain as the ALU fall-through
and `B.cond`. For `BL`, `x30`'s next-state node additionally becomes
`ite(active, a + 4, next x30)`. This exactly mirrors `interp._execute`'s `OP_B`
case (`if link: x30 := pc + 4; next_pc := pc + offset`). Backward branches (a
negative `imm26`) are the loop back-edge and fall out for free, as does the
off-end halt (a forward branch past `code_hi`).

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

**Memory model.** Memory is a BTOR2 **`Array bv64 bv8`** (byte-addressed,
**little-endian** — AArch64 is LE), emitted *only* when the program contains an
`LDR`/`STR` (mirroring `evm-btor2` / `ebpf-btor2`'s conditional `mem` array). The
array is zero-initialized (bytes never written read 0). `T` lowers:

- **`STR`**: a chain of 8 array `write`s — `write(mem, ea + i, value<8i+7:8i>)` for
  `i = 0..7` (the byte at `ea` is `value<7:0>`, the least significant, = LE).
  `next mem := ite(active, written, next mem)`.
- **`LDR`**: 8 array `read`s `read(mem, ea + i)` `concat`-assembled with the byte
  at `ea` least significant (`concat(byte_i_high, …, byte_0_low)`) into a bv64
  loaded value. `Rt`'s next-state becomes `ite(active, loaded, next Rt)` (no write
  when `Rt == 31` = XZR).

These mirror `interp._mem_load` / `interp._mem_store` byte-for-byte (one source of
truth). The successor pc is the ALU fall-through `a + 4`. `LDR`/`STR` read/write no
flags.

**The memory window.** The BTOR2 trace exposes only bit-vector state, not arrays
(`languages/btor2/eval.py`), so the memory observable reaches `π` through a fixed
window of bv8 state nodes `m0..m{MEM_WINDOW-1}` (`MEM_WINDOW = 64`): each `m{i}`
is `init`-ed to `init_mem[i]` (default 0) and its next-state is
`read(next mem, i)` — i.e. it tracks the post-step memory array at the fixed byte
address `i`. The source interpreter exposes the identical `m{i}` bytes, so the
cross-check compares memory step-for-step. (64 bytes covers the low-address
accesses of the corpus; it is a window, not the whole address space.)

### The 32-bit (W-register) forms of the ALU/flag immediate ops — interp `0.6`

The Add/subtract-immediate (`ADD`/`SUB`/`SUBS`/`ADDS`) and Move-wide (`MOVZ`)
classes each have a **32-bit form** selected by `sf = 0` (the `Wd`/`Wn` operands).
`decode_insn_v6` accepts `sf = 0` and tags the decoded instruction with
`width = 32` (the X-register forms stay `width = 64`); the op kind, the
`SP`-as-field-31 source semantics (the 32-bit stack pointer `WSP`), the `XZR`
destination for `SUBS`/`ADDS`/`MOVZ` (the 32-bit `WZR`), and the optional `LSL #12`
are otherwise unchanged. `MOVZ` W additionally restricts `hw ∈ {0,1}` (LSL #0/#16);
`hw ∈ {2,3}` is reserved for the 32-bit form and hard-aborts.

**The one real subtlety vs the 64-bit forms** is the operand/result/flag width:

```
src32    := read(Rn)<31:0>                  (the low 32 bits of the source register)
result32 := src32  ⊕  imm<31:0>             (⊕ = + for ADD/ADDS, - for SUB/SUBS;
                                             = imm<31:0> for MOVZ — no source reg)
write(Rd, ZeroExtend(result32, 64))         (Rd's upper 32 bits become 0)
```

So:

- **Zero-extend into `Xd`.** The 32-bit `result32` is written to `Wd`, which
  zero-extends into the full 64-bit `Xd` — the **upper 32 bits of `Xd` become 0**
  (not preserved). `T` lowers the source operand to `slice(Rn, 31, 0)` (a bv32),
  does the op at width 32, and writes `uext(64, result32, 32)` (zero-extend the bv32
  to bv64) into `Rd`'s state node. The interpreter masks the source to 32 bits,
  computes mod 2³², and writes the (already `< 2⁶⁴`) result directly. For `ADD`/`SUB`
  W to `WSP` (field 31), the same zero-extended bv64 is written to `sp`.
- **32-bit flags.** For `SUBS`/`CMP` W and `ADDS`/`CMN` W the `NZCV` flags are
  computed on the **32-bit** result, at 32-bit width:
  - `N = result32<31>` (bit 31, not bit 63);
  - `Z = (result32 == 0)` (the 32-bit result, not the 64-bit one);
  - `C` — for `SUBS` W, `(src32 >=u imm32)` (no 32-bit borrow); for `ADDS` W, the
    unsigned carry-out of the **33-bit** sum (`src32` and `imm32` zero-extended by one
    bit, added, bit 32 sliced out);
  - `V` — signed overflow at 32-bit width (operands' sign bit is bit 31; for `SUBS`
    W the different-sign-in rule, for `ADDS` W the same-sign-in rule — exactly the
    64-bit rules but at the 32-bit sign bit).

  `T` builds these with the same `_subs_nzcv` / `_adds_nzcv` node templates, now
  parameterized by `width = 32` (the sign bit is `width - 1 = 31`, the carry-out is
  bit `width = 32` of the `width + 1 = 33`-bit sum, `Z` compares against `constd(32,
  0)`). The interpreter mirrors them in `_subs_flags32` / `_adds_flags32`. The
  packed bv4 `nzcv` (`N=bit3, Z=bit2, C=bit1, V=bit0`) is identical in shape to the
  64-bit forms — only the width of the intermediate computation differs.

This makes a 32-bit result genuinely distinct from the 64-bit one whenever the
source has high bits set (the high half is ignored and then cleared) or the add/sub
carries/overflows at the 32-bit boundary but not the 64-bit one. The branches and
`LDR`/`STR` are 64-bit only this round (they ignore `width`).

## Halting

There is **no halt instruction** in this slice. `halted` is set when `pc`
leaves `[code_lo, code_hi)` — `off_end = ¬(code_lo ≤ pc < code_hi) ∧ ¬halted`,
`next halted = ite(off_end, 1, halted)` — exactly mirroring the interpreter's
"ran off the end" halt. This makes the two traces align step-for-step under
`π` (the BTOR2 trace is the source trace shifted by one cycle, since BTOR2's
first row is the initial state).

## Reachability property (optional)

`property = {"reg_eq": [field, value]}` emits a BTOR2 `bad` for
`reg(field) == value` (`field == 31` ⇒ `sp`), so a question is decidable
through the shared `btor2-smtlib` bridge; a `reachable` witness replays back to
the AArch64 fact via `L` (the carry-back). A memory round-trip
(`STR` then `LDR`) carries through the same path — a witness reaching a loaded-value
`reg_eq` requires the store/load to have executed.

## A64-vs-RV64 divergence notes (auditable portability assumptions)

1. **PC is a byte address** keyed on `entry + 4*i`; the ALU fall-through is
   `pc + 4`, a taken `B.cond` is `a + offset` (`offset` = sign-extended
   `imm19 * 4`), and `B`/`BL` are unconditionally `a + offset`
   (`offset` = sign-extended `imm26 * 4`). (RV64 is identical at 4 bytes; RV64C's
   2-byte compressed case has no analogue here. RV64's conditional branches
   (`BEQ`/…) are the analogue of `B.cond`, but compare *registers* rather than
   read a flag register — A64 separates the compare (`SUBS`/`CMP`/`ADDS`/`CMN`,
   which set `NZCV`) from the branch (`B.cond`, which reads `NZCV`). `BL` is the
   analogue of RV64's `JAL rd` — an unconditional branch that writes a return
   address — here fixed to the link register `x30`.)
2. **Register field 31 is encoding-class-dependent.** For `ADD`/`SUB`
   (immediate) it is **SP** (RV64 `x0` is a hardwired zero — A64 has no zero
   register *in this class*), so the lowering reads/writes the `sp` node. For
   `SUBS`/`CMP` and `ADDS`/`CMN` the *source* field 31 is SP but the *destination*
   field 31 is the **zero register `XZR`** (the `CMP`/`CMN` write-discard). For
   `MOVZ` (move-wide) field 31 is **`XZR`**: the write is discarded, not routed
   to `sp`. For `LDR`/`STR` the *base* field 31 (`Rn`) is **SP** but the *transfer*
   field 31 (`Rt`) is **`XZR`** (a load to `XZR` is discarded; a store of `XZR`
   writes 0) — never `SP`. (RV64 `x0` is the closest analogue to XZR.)
3. **NZCV.** `ADD`/`SUB`/`MOVZ`, `B`/`BL` and `LDR`/`STR` leave `NZCV` unchanged.
   `SUBS`/`CMP` writes it with the *subtraction* definitions (`C = Rn >=u imm`
   no-borrow, `V` from *different-sign* operands) and `ADDS`/`CMN` with the
   *addition* definitions (`C` = unsigned carry-out of the 65-bit sum, `V` from
   *same-sign* operands); both share `N = result<63>`, `Z = result == 0`. **The
   addition and subtraction `C`/`V` definitions are genuinely distinct** — get them
   right per op. `B.cond` reads `NZCV` and writes only `pc`. `nzcv`'s presence
   keeps the non-memory `π` prefix compatible with `aarch64-sail`.
4. **Memory.** `LDR`/`STR` access byte-addressed memory at `read(Rn) + imm`
   (`imm = imm12 * 8`, the 12-bit unsigned offset scaled by the 8-byte access
   size), **little-endian** (AArch64 is LE — the byte at `ea` is the least
   significant). Memory is an `Array bv64 bv8` (zero-initialized), lowered to byte
   `read`/`write` chains; the observable reaches `π` through the fixed window
   `m0..m{MEM_WINDOW-1}`. **No alignment restriction** — the byte-addressed model
   handles any `ea` (a misaligned access simply spans whatever 8 byte addresses).
   RV64's `LD`/`SD` are the direct analogue with the same LE byte order; A64 scales
   the unsigned offset by the access size where RV64 uses a signed byte offset, and
   A64's `Rt` field 31 is `XZR` (RV64 `x0`).
5. **32-bit (`W`-register) forms zero-extend; flags are 32-bit.** A `W`-register
   write zero-extends into the 64-bit `X` register — the **upper 32 bits become 0**
   (`sf = 0` selects this; `T` writes `uext(64, result32, 32)`). This is the *exact*
   analogue of RV64's `*W` instructions (`ADDIW`/`ADDW`/…), which sign-extend the
   32-bit result into the 64-bit register — A64 **zero-extends** where RV64
   **sign-extends**, the one genuine divergence here. The flags for `SUBS`/`ADDS` W
   are computed at 32-bit width (sign bit = bit 31, carry-out = bit 32 of the 33-bit
   sum), so a 32-bit carry/overflow is independent of the 64-bit one — a high-half
   of the source is ignored, and a value like `0x80000000 - 1` overflows the signed
   *32-bit* range (`V = 1`) while the same value does not overflow as a 64-bit
   subtract.

## Out of scope (hard-aborts, itemized in the `unsupported` histogram)

The move-wide siblings `MOVN`/`MOVK` (32- and 64-bit), the reserved 32-bit `MOVZ`
shift (`hw ∈ {2,3}`, LSL #32/#48 has no W form), `BC.cond` (FEAT_HBC), the
**narrower-width and other-mode loads/stores** (`LDRB`/`STRB` and the other
byte/halfword widths, the 32-bit `LDR`/`STR` `size=10`, `LDRSW`, and the
pre/post-index and unscaled `LDUR`/`STUR` modes — only the 64-bit `size=11`
*unsigned-offset* `LDR`/`STR` is in scope), and every other encoding (`NOP`,
`RET`, …) raise `unsupported: aarch64:<construct>` at decode time — never silently
dropped or mis-lowered. `decode_insn_v6` is the single rejection point, shared by
`T` and the interpreter. (The narrower `decode` (ADD only), `decode_insn`
(`ADD`/`SUB`/`MOVZ`), `decode_insn_v3` (+`SUBS`/`CMP`+`B.cond`), `decode_insn_v4`
(+`B`/`BL`+`ADDS`/`CMN`) and `decode_insn_v5` (+64-bit `LDR`/`STR`) are retained
verbatim as the `aarch64-sail` route's rejection gate; the `0.6` ops — the 32-bit
W-register ALU/flag forms — land in `aarch64-sail` when its sibling agent mirrors
them — AGENTS.md §3. The 32-bit ALU/flag forms are now **in scope** (`width = 32`),
so they no longer abort here.)

## Fidelity

`checked` — the commuting-square oracle walks `I_s(p)` against `L(I_t(T(p)))`
under `π` on the test corpus every run, and the coverage probes assert the
typed aborts. Evidence: `tests/test_aarch64_btor2_pair.py` (per-op square,
including each of `N`/`Z`/`C`/`V` set by `SUBS`/`CMP` and by `ADDS`/`CMN` — the
latter with its addition `C`(carry-out)/`V`(signed-overflow) definitions, a
carry-out case, a signed-overflow case, and the `CMN` discard — `B.cond` taken
vs not-taken for `EQ`/`NE`/`LT`/`GE`/`HI`/…, a branching program, a back-branch
loop, an unconditional forward `B` skipping an instruction, a backward `B` loop
back-edge, and `BL`'s link register; the `0.5` memory ops — a `STR`-then-`LDR`
round-trip, a load from never-written memory returning 0, the SP-relative
addressing form, the little-endian `m{i}` window byte order, the `Rt = XZR`
store-zero / load-discard, and a mixed memory+ALU program; the `0.6` 32-bit W
forms — `ADD`/`SUB` W zero-extending into `Xd` (incl. a case where the 64-bit and
32-bit results differ because the source has high bits set, and a 32-bit wrap),
`SUBS`/`ADDS` W setting `N`/`Z`/`C`/`V` on the 32-bit result (a 32-bit
carry/overflow case distinct from the 64-bit one, cross-checked against the matching
64-bit op which does *not* set the flag), `MOVZ` W (incl. LSL #16 and the `WZR`
discard), `ADD` W to `WSP`, the `CMP`/`CMN` W discards, and a mixed W+X program;
twice-and-diff determinism over a program that exercises `LDR`/`STR` and the W
forms; carry-back of a branch-taken, a `BL`, an `LDR`-result+memory-window, and a
32-bit-W-result witness; coverage/rejection of `LDRB`/`STRB`/32-bit `LDR`/`MOVK`/
`MOVN`/reserved `MOVZ` hw=2), and the end-to-end decide→witness→carry-back through
`btor2-smtlib` (z3-gated, incl. `CMP`+`B.cond`, `ADDS`, unconditional-`B`, a
`STR`/`LDR` memory round-trip, and a 32-bit-W reachability program).
`proved`-tier certificates are future work (pairs/aarch64-btor2 brief).
