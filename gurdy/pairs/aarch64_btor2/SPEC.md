# Translation specification — `aarch64-btor2` (thin `ADD (immediate)` slice)

This is the self-contained, reviewable specification the `aarch64-btor2`
translator implements mechanically (PAIRING.md §2). The translator (`T`,
`translate.py`) and the target-to-source interpreter (`L`, `lift.py`) share one
source of truth — the per-instruction lowering below and the shared AArch64
decoder (`languages/aarch64/interp.py:decode`) — so the commuting square is
cross-checked by running both under the projection `π` (PAIRING.md §6).

Status: **partial** (PAIRING.md §1 "Start thin, then widen"). Exactly one
in-scope construct; everything else hard-aborts with a typed
`unsupported: aarch64:<construct>` (BENCHMARKS.md §3).

## Languages

- **Source.** AArch64 (A64), the shared interpreter `languages/aarch64`
  (interpreter version `0.1`). Observables (post-step, ARCHITECTURE.md §5):
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

## The one lowering rule — `ADD (immediate)`, 64-bit

Encoding (A64): `sf=1 op=0 S=0 1 0 0 0 1 sh imm12 Rn Rd`. The shared `decode`
yields `(rd, rn, imm)` where `imm = imm12 << (12 if sh==01 else 0)`, and a
register field value `31` denotes **SP** (this encoding class has no zero
register). The effect, mirrored bit-for-bit by `T` and the interpreter:

```
result   := read(Rn) + imm            (mod 2^64)
write(Rd, result)                      (Rn/Rd == 31 read/write `sp`)
next pc  := a + 4
nzcv     := nzcv                        (ADD does not set flags; only ADDS does)
```

`T` lowers `result` to a BTOR2 `add` over the `Rn` node and a `constd` of `imm`,
writes it into the `Rd` (or `sp`) next-state via the `active` ITE, advances `pc`
to `a+4`, and threads `nzcv` through unchanged.

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
2. **Register field 31 = SP**, not a hardwired zero register (RV64 `x0`). The
   lowering reads/writes the `sp` node for field 31.
3. **`ADD` leaves `NZCV` unchanged.** Only `ADDS` writes flags (out of scope),
   so `nzcv` is threaded through untouched; its presence keeps `π` compatible
   with `aarch64-sail`.

## Out of scope (hard-aborts, itemized in the `unsupported` histogram)

`SUB (immediate)`, `ADDS`/`SUBS` (flag-setting), the 32-bit (`sf=0`) form, and
every non-`Add/subtract-immediate` encoding (`MOVZ`, `NOP`, `RET`, `LDR`, `B`,
…) raise `unsupported: aarch64:<construct>` at decode time — never silently
dropped or mis-lowered. The decoder is the single rejection point, shared by
`T` and the interpreter.

## Fidelity

`checked` — the commuting-square oracle walks `I_s(p)` against `L(I_t(T(p)))`
under `π` on the test corpus every run, and the coverage probes assert the
typed aborts. Evidence: `tests/test_aarch64_btor2_pair.py` (square +
twice-and-diff determinism + carry-back + coverage/rejection), and the
end-to-end decide→witness→carry-back through `btor2-smtlib` (z3-gated).
`proved`-tier certificates are future work (pairs/aarch64-btor2 brief).
