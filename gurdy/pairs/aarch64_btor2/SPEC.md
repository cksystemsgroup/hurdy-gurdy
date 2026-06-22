# Translation specification — `aarch64-btor2` (simple-ALU slice: `ADD`/`SUB` imm + `MOVZ`)

This is the self-contained, reviewable specification the `aarch64-btor2`
translator implements mechanically (PAIRING.md §2). The translator (`T`,
`translate.py`) and the target-to-source interpreter (`L`, `lift.py`) share one
source of truth — the per-instruction lowering below and the shared AArch64
decoder (`languages/aarch64/interp.py:decode_insn`) — so the commuting square is
cross-checked by running both under the projection `π` (PAIRING.md §6).

Status: **partial** (PAIRING.md §1 "Start thin, then widen"). A small family of
simple, no-flag / no-control-flow ALU register writes is in scope; everything
else hard-aborts with a typed `unsupported: aarch64:<construct>`
(BENCHMARKS.md §3).

## Languages

- **Source.** AArch64 (A64), the shared interpreter `languages/aarch64`
  (interpreter version `0.2`). Observables (post-step, ARCHITECTURE.md §5):
  `pc` (byte address), `x0`–`x30`, `sp`, `nzcv` (the NZCV flags as a bv4),
  `halted`.
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
| `nzcv`   | bv4  | condition flags N,Z,C,V |
| `halted` | bv1  | 1 once `pc` has left the code region |

`init`: `pc = entry`; `xr = init_regs[r]` (default 0); `sp = init_sp`
(default `1<<20`, matching the interpreter's `SP_DEFAULT`); `nzcv = init_nzcv`
(default 0); `halted = 0`.

The program is fixed, so the next-state of every node is a **PC-keyed ITE
dispatch**: for each instruction at byte address `a = entry + 4*i`, an
`active = (pc == a) ∧ ¬halted` guard selects that instruction's effect.

## The lowering rules (the in-scope ALU family)

The shared `decode_insn` tags each in-scope word with an op kind
(`add`/`sub`/`movz`) and the operands `(rd, rn, imm)`. `T` and the interpreter
mirror the *same* per-op effect bit-for-bit (one source of truth); each effect
is a single register write with successor `next pc := a + 4` and `nzcv := nzcv`.

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

1. **PC is a byte address** keyed on `entry + 4*i`; fall-through is `pc + 4`.
   (RV64 is identical at 4 bytes; RV64C's 2-byte compressed case has no analogue
   here.)
2. **Register field 31 is encoding-class-dependent.** For `ADD`/`SUB`
   (immediate) it is **SP** (RV64 `x0` is a hardwired zero — A64 has no zero
   register *in this class*), so the lowering reads/writes the `sp` node. For
   `MOVZ` (move-wide) it is the **zero register `XZR`**: the write is discarded,
   not routed to `sp`. (RV64 `x0` is the closest analogue to XZR.)
3. **`ADD`/`SUB`/`MOVZ` leave `NZCV` unchanged.** Only the flag-setting
   `ADDS`/`SUBS` forms (out of scope) write flags, so `nzcv` is threaded through
   untouched; its presence keeps `π` compatible with `aarch64-sail`.

## Out of scope (hard-aborts, itemized in the `unsupported` histogram)

The flag-setting `ADDS`/`SUBS`, the 32-bit (`sf=0`) forms, the move-wide
siblings `MOVN`/`MOVK`, and every other encoding (`NOP`, `RET`, `LDR`, `B`, …)
raise `unsupported: aarch64:<construct>` at decode time — never silently dropped
or mis-lowered. `decode_insn` is the single rejection point, shared by `T` and
the interpreter. (The original `ADD`-only `decode` is retained verbatim for the
`aarch64-sail` route, which still uses it as its rejection gate and executes only
`ADD`; the new ops land in `aarch64-sail` when its sibling agent mirrors them.)

## Fidelity

`checked` — the commuting-square oracle walks `I_s(p)` against `L(I_t(T(p)))`
under `π` on the test corpus every run, and the coverage probes assert the
typed aborts. Evidence: `tests/test_aarch64_btor2_pair.py` (per-op square +
twice-and-diff determinism + carry-back + coverage/rejection), and the
end-to-end decide→witness→carry-back through `btor2-smtlib` (z3-gated, incl. a
`MOVZ`+`SUB` program). `proved`-tier certificates are future work
(pairs/aarch64-btor2 brief).
