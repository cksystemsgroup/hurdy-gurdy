# Translation specification — `aarch64-btor2` (ALU + flag-set + cond. branch: `ADD`/`SUB`/`MOVZ`, `SUBS`/`CMP`, `B.cond`)

This is the self-contained, reviewable specification the `aarch64-btor2`
translator implements mechanically (PAIRING.md §2). The translator (`T`,
`translate.py`) and the target-to-source interpreter (`L`, `lift.py`) share one
source of truth — the per-instruction lowering below and the shared AArch64
decoder (`languages/aarch64/interp.py:decode_insn_v3`) — so the commuting square
is cross-checked by running both under the projection `π` (PAIRING.md §6).

Status: **partial** (PAIRING.md §1 "Start thin, then widen"). Interp `0.3` adds
the first NZCV write (`SUBS`/`CMP` immediate) and the first conditional control
flow (`B.cond`) to the `0.2` simple-ALU family; everything else hard-aborts with
a typed `unsupported: aarch64:<construct>` (BENCHMARKS.md §3).

## Languages

- **Source.** AArch64 (A64), the shared interpreter `languages/aarch64`
  (interpreter version `0.3`). Observables (post-step, ARCHITECTURE.md §5):
  `pc` (byte address), `x0`–`x30`, `sp`, `nzcv` (the NZCV flags as a bv4, packed
  `N=bit3, Z=bit2, C=bit1, V=bit0` — MSB-first), `halted`.
- **Target.** BTOR2, the shared interpreter `languages/btor2` (reused, never
  forked).

## Projection `π`

`{pc, x0..x30, sp, nzcv, halted}` — the AArch64 interpreter's observables
mapped onto identically-named BTOR2 state variables. This is the exact set the
cross-check compares, and it is kept compatible with the registered
`aarch64-sail` branch (pairs/aarch64-btor2 brief).

## Target state (the BTOR2 transition system `T` emits)

One state node per observable, all bit-vectors:

| node     | sort | meaning |
|----------|------|---------|
| `pc`     | bv64 | byte address of the next instruction |
| `x0..x30`| bv64 | general registers |
| `sp`     | bv64 | stack pointer |
| `nzcv`   | bv4  | condition flags, packed `N=bit3, Z=bit2, C=bit1, V=bit0` |
| `halted` | bv1  | 1 once `pc` has left the code region |

`init`: `pc = entry`; `xr = init_regs[r]` (default 0); `sp = init_sp`
(default `1<<20`, matching the interpreter's `SP_DEFAULT`); `nzcv = init_nzcv`
(default 0); `halted = 0`.

The program is fixed, so the next-state of every node is a **PC-keyed ITE
dispatch**: for each instruction at byte address `a = entry + 4*i`, an
`active = (pc == a) ∧ ¬halted` guard selects that instruction's effect. The
successor pc is `a + 4` for every op except `B.cond`, whose successor is itself
a condition-ITE (below) — the first conditional pc update.

## The lowering rules (the in-scope family)

The shared `decode_insn_v3` tags each in-scope word with an op kind
(`add`/`sub`/`movz`/`subs`/`bcond`) and the operands `(rd, rn, imm)` (plus
`cond`/`offset` for `B.cond`). `T` and the interpreter mirror the *same* per-op
effect bit-for-bit (one source of truth). The ALU ops are a single register
write with successor `next pc := a + 4`; `ADD`/`SUB`/`MOVZ` leave `nzcv`
untouched, `SUBS`/`CMP` writes it, and `B.cond` writes only `pc`.

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
branch successors. `BC.cond` (bit[4] = 1, FEAT_HBC) and the unconditional `B`/`BL`
remain out of scope and hard-abort.

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
the AArch64 fact via `L` (the carry-back).

## A64-vs-RV64 divergence notes (auditable portability assumptions)

1. **PC is a byte address** keyed on `entry + 4*i`; the ALU fall-through is
   `pc + 4`, and a taken `B.cond` is `a + offset` with `offset` the
   sign-extended `imm19 * 4`. (RV64 is identical at 4 bytes; RV64C's 2-byte
   compressed case has no analogue here. RV64's conditional branches (`BEQ`/…)
   are the analogue of `B.cond`, but compare *registers* rather than read a flag
   register — A64 separates the compare (`SUBS`/`CMP`, which sets `NZCV`) from
   the branch (`B.cond`, which reads `NZCV`).)
2. **Register field 31 is encoding-class-dependent.** For `ADD`/`SUB`
   (immediate) it is **SP** (RV64 `x0` is a hardwired zero — A64 has no zero
   register *in this class*), so the lowering reads/writes the `sp` node. For
   `SUBS`/`CMP` the *source* field 31 is SP but the *destination* field 31 is the
   **zero register `XZR`** (the `CMP` write-discard). For `MOVZ` (move-wide)
   field 31 is **`XZR`**: the write is discarded, not routed to `sp`. (RV64 `x0`
   is the closest analogue to XZR.)
3. **NZCV.** `ADD`/`SUB`/`MOVZ` leave `NZCV` unchanged; `SUBS`/`CMP` is the only
   in-scope op that writes it (`ADDS` stays out of scope this round). `B.cond`
   reads `NZCV` and writes only `pc`. `nzcv`'s presence keeps `π` compatible
   with `aarch64-sail`.

## Out of scope (hard-aborts, itemized in the `unsupported` histogram)

The flag-setting **`ADDS`** (the addition NZCV write — deferred this round), the
32-bit (`sf=0`) forms, the move-wide siblings `MOVN`/`MOVK`, the unconditional
`B`/`BL`, `BC.cond` (FEAT_HBC), and every other encoding (`NOP`, `RET`, `LDR`, …)
raise `unsupported: aarch64:<construct>` at decode time — never silently dropped
or mis-lowered. `decode_insn_v3` is the single rejection point, shared by `T` and
the interpreter. (The narrower `decode` (ADD only) and `decode_insn`
(`ADD`/`SUB`/`MOVZ`) are retained verbatim as the `aarch64-sail` route's
rejection gate, which executes only those ops; the `0.3` ops land in
`aarch64-sail` when its sibling agent mirrors them — AGENTS.md §3.)

## Fidelity

`checked` — the commuting-square oracle walks `I_s(p)` against `L(I_t(T(p)))`
under `π` on the test corpus every run, and the coverage probes assert the
typed aborts. Evidence: `tests/test_aarch64_btor2_pair.py` (per-op square,
including each of `N`/`Z`/`C`/`V` set by `SUBS`/`CMP` and `B.cond` taken vs
not-taken for `EQ`/`NE`/`LT`/`GE`/`HI`/… plus a branching program and a
back-branch loop; twice-and-diff determinism; carry-back of a branch-taken
witness; coverage/rejection), and the end-to-end decide→witness→carry-back
through `btor2-smtlib` (z3-gated, incl. a `CMP`+`B.cond` reachability program).
`proved`-tier certificates are future work (pairs/aarch64-btor2 brief).
