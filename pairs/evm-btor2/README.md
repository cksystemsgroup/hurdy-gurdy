# Pair — `evm-btor2`  ·  EVM → BTOR2

*Status: **partial** — the stack/arithmetic slice (the full push family
`PUSH1`..`PUSH32`, `ADD`/`MUL`/`SUB`, the unsigned `DIV`/`MOD` and the signed
`SDIV`/`SMOD`, `POP`, the duplications `DUP1`..`DUP16`, the swaps
`SWAP1`..`SWAP16`, `STOP` over 256-bit words), the byte-addressed memory ops
`MLOAD`/`MSTORE`/`MSTORE8`, the persistent storage ops `SLOAD`/`SSTORE`, **plus
the control-flow ops `JUMP`/`JUMPI`/`JUMPDEST`/`PC`** (the first non-linear
control flow) is built end-to-end through the commuting square; 82 / 144
spec-derived opcodes covered. Every other opcode hard-aborts
`unsupported: evm:<opcode>`. Not yet `built` (PAIRING.md §1 "start thin"). Built
on EVM shared interpreter **v0.8**.*

Translate EVM bytecode (a pure-function, single-contract subset) into a
BTOR2 transition system over 256-bit words and arrays.

## Implemented slice (PAIRING.md §1, §7)

- **Constructs covered end-to-end:** the single-successor bv256 stack family —
  the full push family `PUSH1` (0x60) .. `PUSH32` (0x7f), binary arithmetic
  `ADD` (0x01) / `MUL` (0x02) / `SUB` (0x03), the unsigned `DIV` (0x04) /
  `MOD` (0x06) and the signed `SDIV` (0x05) / `SMOD` (0x07), stack shuffles
  `POP` (0x50), the duplications `DUP1` (0x80) .. `DUP16` (0x8f), the swaps
  `SWAP1` (0x90) .. `SWAP16` (0x9f), and `STOP` (0x00) — over a bounded bv256
  operand stack (`STACK_SIZE = 16`). `SUB` is top-minus-next; `SUB`/`MUL` wrap
  mod 2²⁵⁶ via the native BTOR2 `sub`/`mul` on bv256. `DIV`/`MOD` are unsigned
  with the EVM **by-zero = 0** special case, lowered as
  `ite(b==0, 0, udiv/urem(a,b))` (an explicit guard, since BTOR2 `udiv`/`urem`
  carry the SMT by-zero convention, not EVM's). `SDIV`/`SMOD` are signed
  (two's-complement, **truncating**) over BTOR2 `sdiv`/`srem` with explicit
  guards: `SDIV = ite(b==0, 0, ite(a==INT_MIN ∧ b==-1, INT_MIN, sdiv(a,b)))`
  (recovering the EVM **by-zero = 0** *and* the **`INT_MIN/-1` = `INT_MIN`** wrap)
  and `SMOD = ite(b==0, 0, srem(a,b))` (the remainder takes the sign of the
  dividend, as `srem` already does). `DUP{n}` copies `s{sp-n}` onto `s{sp}`;
  `SWAP{n}` swaps `s{sp-1}` with `s{sp-1-n}` (depth unchanged) — both index-mux
  lowerings keyed on the `n` the opcode byte encodes. The **byte-addressed memory
  ops** `MLOAD` (0x51) / `MSTORE` (0x52) / `MSTORE8` (0x53) lower over a BTOR2
  `Array bv256 bv8` (zero-initialized, unbounded): `MSTORE` writes the 32-byte
  **big-endian** word (32 chained array writes, MSB at `off`), `MSTORE8` writes
  the low byte, `MLOAD` reads 32 bytes back big-endian onto the stack. Memory is
  observed in `π` via a fixed `MEM_WINDOW = 64`-byte window `m0..m63` (`bv8`
  states mirroring the array's low bytes), since the shared BTOR2 trace exposes
  bit-vector, not array, state. The **persistent storage ops** `SLOAD` (0x54) /
  `SSTORE` (0x55) lower over a second BTOR2 array `Array bv256 bv256`
  (zero-initialized) — a word-keyed word map, so each is a *single* array
  read/write (no byte assembly): `SSTORE` writes `storage[key] := val`, `SLOAD`
  reads `storage[key]` (0 if never written) back onto the stack. Storage is
  observed in `π` via a fixed `STORE_WINDOW = 8`-key window `s_at_0..s_at_7`
  (`bv256` states mirroring the values at keys 0..7). The **control-flow ops**
  `JUMP` (0x56) / `JUMPI` (0x57) / `JUMPDEST` (0x5b) / `PC` (0x58) are the **first
  non-linear control flow**: `JUMPDEST` is a no-op marker, `PC` pushes the current
  instruction's byte offset, and `JUMP`/`JUMPI` pop a *dynamic* destination and
  resolve it against the statically-scanned set of `JUMPDEST` byte offsets via an
  ITE chain `next_pc := ite(dest == jd0, jd0, …, off+1)` (the same shape
  `riscv-btor2`/`aarch64-btor2` use for a dynamic/conditional pc), with `halted`
  set when `dest` matches no `JUMPDEST`. The `JUMPDEST` scan skips `PUSH`-immediate
  bytes (a `0x5b` inside an immediate is not a target). Off-the-end execution,
  stack underflow/overflow, and a jump to a non-`JUMPDEST` are EVM exceptional
  halts (defined edges), distinct from the typed `unsupported` abort; under the
  bounded 16-cell stack `DUP16`/`SWAP16` always take that halt edge. `PUSH0` and
  `MSIZE` stay deferred; EVM gas / out-of-gas is out of scope (an unbounded loop
  runs to the interpreter's `max_steps` / the BMC unrolling bound `k`).
- **Files.** Translator `T` + carry-back `L` + coverage inventory + spec:
  `gurdy/pairs/evm_btor2/` (`translate.py`, `lift.py`, `inventory.py`,
  `SPEC.md`, `__init__.py`). Shared EVM interpreter (contributed by this pair,
  first touch): `gurdy/languages/evm/` (`interp.py`, `asm.py`). The reused BTOR2
  array support (`languages/btor2/`) is **unchanged**. Tests:
  `tests/test_evm_btor2_pair.py`.
- **Fidelity: `checked`.** The commuting-square oracle validates
  `I_s(p) ≡_π L(I_t(T(p)))` under `π` on the test corpus every run; the emitted
  `bad` is additionally decided through `btor2-smtlib` (z3), with the witness
  replayed back through `L`. Not inflated to `proved`: validated on the inputs
  tried, no all-inputs certificate.
- **Coverage 82 / 144 opcodes (56.9 %).** Covered: the full push family
  `PUSH1`..`PUSH32` (32), `DUP1`..`DUP16` (16), `SWAP1`..`SWAP16` (16), plus
  `ADD`/`MUL`/`SUB`/`DIV`/`MOD`/`SDIV`/`SMOD`, `POP`, `STOP` (9), the
  byte-addressed memory ops `MLOAD`/`MSTORE`/`MSTORE8` (3), the persistent
  storage ops `SLOAD`/`SSTORE` (2), and the control-flow ops
  `JUMP`/`JUMPI`/`JUMPDEST`/`PC` (4). `unsupported` histogram: every other EVM
  opcode blocks one task — 62 distinct opcodes (`PUSH0`,
  `ADDMOD`/`MULMOD`/`EXP`/`SIGNEXTEND`, `LT`/`GT`/`EQ`/`ISZERO`,
  `AND`/`OR`/`XOR`/`NOT`/`SHL`/`SHR`/`SAR`/`BYTE`, `MSIZE`, the
  environment/block opcodes, `LOG0..4`, `CALL`/`RETURN`/`REVERT`, …), each ×1
  over the inventory's one-probe-per-opcode denominator
  (`gurdy/pairs/evm_btor2/inventory.py`; `coverage()`).

### What this slice taught us (PAIRING.md §9)

- A bounded bv256 stack modeled as fixed state cells `s0..s15` + a depth `sp`
  (rather than a BTOR2 array) keeps the slice purely bit-vector and lets the
  translator and `L` share the exact per-opcode cell-update rule — including
  *not clearing popped cells* — so the square aligns cell-by-cell. Byte-memory
  (`Array bv256 bv8`, v0.6) and storage (`Array bv256 bv256`, v0.7) take the
  array path (`languages/btor2` already supports it, used by `ebpf-btor2`); the
  array contents reach `π` via fixed **window observables** (`m0..m63`,
  `s_at_0..s_at_7`) since the shared BTOR2 trace exposes bit-vector state only.
- bv256 round-trips through the shared BTOR2 I/O and evaluator with no special
  casing (confirmed first, per the brief's note), and the `bad` decides cleanly
  through the existing `btor2-smtlib` z3 bridge.
- *Widening round (3/144 → 9/144, interp v0.1 → v0.2):* `MUL`/`SUB` reuse the
  `ADD` lowering verbatim — only the BTOR2 op kind (`add`/`mul`/`sub`) changes,
  and all three wrap mod 2²⁵⁶ natively on bv256, so no masking was needed. `SUB`
  is the one non-commutative case (top minus next), so operand order is part of
  the spec. `POP` is the simplest opcode (only `sp -= 1`; the dropped cell is
  left stale, exactly the cell-update convention `ADD` already relies on).
  `DUP1` is a read-`s{sp-1}`/write-`s{sp}` pair reusing both the index mux and
  the write mux. `PUSH2`/`PUSH4` generalize `PUSH1` by keying the inline-operand
  width (and the `pc` advance) on a single `asm.PUSH_WIDTH` map shared by the
  interpreter and the translator — the only source-of-truth change the widths
  needed. All single-successor, no jump-dest machinery, so the existing PC-keyed
  ITE dispatch absorbed them unchanged.
- *Widening round (9/144 → 11/144, interp v0.2 → v0.3):* `DIV`/`MOD` reuse the
  `ADD`/`MUL`/`SUB` arithmetic branch wholesale (same underflow guard, index
  muxes, write mux, `sp`/`pc` update) — only the `total` expression differs. The
  one subtlety: the BTOR2 `udiv`/`urem` already implement a by-zero *convention*,
  but the **SMT-LIB** one (all-ones for `bvudiv`, the dividend for `bvurem`),
  which is *not* EVM's by-zero `= 0`. So the lowering wraps them in an explicit
  guard `ite(b==0, 0, udiv/urem(a,b))` and the interpreter mirrors it with
  `0 if b==0 else a//b` / `a%b`; for unsigned operands Python's flooring `//`/`%`
  coincide with truncating unsigned division, so no signed handling crept in. The
  signed `SDIV`/`SMOD` stay deferred (their EVM `INT_MIN/-1` special case is a
  separate round). The square holds on the normal *and* the by-zero cases.
- *Widening round (11/144 → 71/144, interp v0.3 → v0.4):* the **full
  stack-manipulation family** — `PUSH3`/`PUSH5..PUSH32`, `DUP2..DUP16`,
  `SWAP1..SWAP16` — landed as three *generic* rules keyed on the index the
  opcode byte encodes, not 60 copy-pasted ones. PUSH was already keyed on
  `asm.PUSH_WIDTH`, so widening it to all 32 widths was a pure data change
  (`{0x60+(n-1): n}`); the interp's PUSH branch and the translator's PUSH
  lowering were untouched. `DUP{n}` is the `DUP1` lowering with the read index
  generalized from `sp-1` to `sp-n` (one shared `asm.DUP_N` map); `SWAP{n}`
  is a new but small rule — read `s{sp-1}` and `s{sp-1-n}` via the existing
  index mux, write each into the other's slot with two write muxes, `sp`
  unchanged. The load-bearing subtlety is the **bounded 16-cell stack**:
  `DUP16` (needs depth 16 to read, then overflows on the write) and `SWAP16`
  (needs depth 17, unreachable) can *never* succeed in this slice — they always
  take the exceptional-halt edge, and the square holds for that edge just as for
  the value-changing widths. `PUSH0` (no inline immediate) stays deferred; it is
  a distinct lowering, not part of the `PUSH_WIDTH` family. The single
  source-of-truth maps (`asm.PUSH_WIDTH`/`DUP_N`/`SWAP_N`) are shared by the
  interpreter, the translator, and the coverage probes, so all three agree by
  construction.
- *Widening round (71/144 → 73/144, interp v0.4 → v0.5):* the **signed**
  `SDIV`/`SMOD` reuse the existing binary-arithmetic branch wholesale (same
  underflow guard, index muxes, write mux, `sp`/`pc` update) — only the `total`
  expression differs. The pleasant surprise: BTOR2 `sdiv`/`srem` already compute
  exactly EVM's **truncating** (toward-zero) quotient and **sign-of-dividend**
  remainder (confirmed against `gurdy/languages/btor2/eval.py`), so no manual
  sign juggling was needed in the lowering. The two EVM special cases the SMT
  operators do *not* carry are added as explicit guards, mirroring the `DIV`/`MOD`
  pattern: (i) **by-zero = 0** (BTOR2 `sdiv` by zero is all-ones/1, `srem` is the
  dividend), and (ii) **`SDIV(INT_MIN, -1) = INT_MIN`** — signed overflow that
  wraps, encoded as `ite(eq(a, INT_MIN) ∧ eq(b, -1), INT_MIN, sdiv(a,b))` with
  `INT_MIN = 2²⁵⁵` (top bit only) and `-1` = all-ones (`MASK256`). The interpreter
  needed real care here: Python's `//`/`%` *floor*, which rounds negative
  quotients the wrong way, so the signed branch computes `±(abs(a)//abs(b))` /
  `±(abs(a)%abs(b))` toward zero — never reusing the unsigned `DIV`/`MOD` code.
  The square holds on positive/negative operands, both by-zero cases, the
  sign-of-dividend distinction, *and* the `INT_MIN/-1` wrap.
- *Widening round (73/144 → 76/144, interp v0.5 → v0.6):* the **byte-addressed
  memory ops** `MLOAD`/`MSTORE`/`MSTORE8` — the first slice to leave the pure
  bit-vector model and use a BTOR2 **array** (`Array bv256 bv8`, zero-init,
  unbounded), reusing `languages/btor2`'s array support **unchanged** (it was
  already exercised by `ebpf-btor2`, whose `_load`/`_store` were the template).
  The one genuinely new design problem: **the shared BTOR2 evaluator's trace
  exposes only bit-vector state, not array state** (`step` records bv states
  only), so the memory contents can't be projected as an array. The fix is a
  fixed **memory-window observable** — `MEM_WINDOW = 64` `bv8` states `m0..m63`
  whose `next` reads the post-step array at the fixed addresses `0..63`, mirrored
  by the interpreter's byte-map window. `π` gains `m0..m63`; `L` zero-fills them
  for non-memory traces (the array + window states are emitted *conditionally*,
  like `ebpf-btor2`'s `mem`), so non-memory programs are byte-identical to v0.5.
  A store/load *outside* the window is still validated because its loaded value
  lands on the stack (already in `π`); the window adds direct observation of
  writes never read back. Byte order is the EVM's: `MSTORE`/`MLOAD` are 32-byte
  **big-endian** (MSB at `off`), the mirror of eBPF's little-endian MEM loads —
  the same `_load`/`_store` shape, only the `concat`/`slice` order flips. `MSTORE`
  pops `off` (top) then `val` (next); `MLOAD` pops `off` and pushes the word in
  the same slot (`sp` unchanged). The square holds on round-trips, never-written
  loads (-> 0), `MSTORE8` single-byte writes, overlapping word/byte writes,
  out-of-window offsets, and all three underflow halts.
- *Widening round (76/144 → 78/144, interp v0.6 → v0.7):* the **persistent
  storage ops** `SLOAD`/`SSTORE` — the byte-memory pattern, *simpler*. Storage is
  a **word-keyed word map** (`Array bv256 bv256`, zero-init), so where `MSTORE`
  assembled 32 big-endian byte writes and `MLOAD` 32 byte reads, `SSTORE` is a
  *single* `write(storage, key, val)` and `SLOAD` a *single* `read(storage, key)`
  — no `concat`/`slice`, no byte order. Everything else carried over verbatim from
  the memory round: the offset/key index mux, the guarded array update
  `storage' := ite(do, written, storage)`, the conditional emission (the array +
  window states appear *only* when the body uses storage), and a fixed
  **storage-window observable** — `STORE_WINDOW = 8` `bv256` states `s_at_0..s_at_7`
  whose `next` reads the post-step array at keys `0..7`, mirrored by the
  interpreter's word-map window. `π` gains `s_at_0..s_at_7`; `L` zero-fills them
  for non-storage traces. The storage states are emitted *after* the memory
  states, so adding storage shifts no memory node id — confirmed byte-identical to
  v0.6 for both non-storage and memory-only programs (twice-and-diff + diff vs the
  pre-change translator). The square holds on store-then-load round-trips,
  never-written loads (→ 0), overwrites, full-bv256-word values (bits above
  2¹²⁸), out-of-window keys, memory-and-storage-together programs, and both
  underflow halts; a witness for an `SLOAD` result carries back through `L` (with
  the storage window). `MSIZE` and control flow stay deferred.
- *Widening round (78/144 → 82/144, interp v0.7 → v0.8):* the **control-flow ops**
  `JUMP`/`JUMPI`/`JUMPDEST`/`PC` — the **first non-linear control flow**, the
  round that finally makes `pc` a non-trivial function of the program's data.
  EVM jumps are *dynamic* (the destination is popped off the stack) but bounded:
  a jump may only land on a `JUMPDEST`, and the set of valid `JUMPDEST` byte
  offsets is statically scanned from the bytecode (skipping `PUSH`-immediate bytes
  — a `0x5b` inside an immediate is not a target). So the dynamic destination is
  lowered as an **ITE chain over the (sorted) `JUMPDEST` offsets**,
  `next_pc := ite(dest == jd0, jd0, ite(dest == jd1, jd1, …, off+1))`, with
  `halted` set when `dest` matches none of them — the same shape
  `riscv-btor2`/`aarch64-btor2` use to fold a dynamic/conditional next-pc into the
  transition `ite` (studied first, per the brief). The interpreter mirrors it
  exactly via a shared `interp.jumpdests` scanner. The one load-bearing subtlety
  was the **pc on the halt edge**: every existing op advances `pc := off+1`
  whenever *active* (even on an underflow halt), so `JUMP`/`JUMPI` had to do the
  same — `next_pc := ite(active, ite(underflow, off+1, resolved), prev)` — rather
  than only writing pc on the non-underflow path (otherwise the underflow-halt row
  diverged on `pc`). A jump to a non-`JUMPDEST` reuses the existing exceptional-halt
  edge (a defined edge, not a typed `unsupported` abort), so no new halt machinery
  was needed. EVM gas / out-of-gas is out of scope: an unbounded loop simply runs
  to the interpreter's `max_steps` / the BMC bound `k`. The square holds on an
  unconditional `JUMP` skipping an instruction, a `JUMPI` taken vs not-taken, a
  **back-edge loop** (a `JUMPI` to an earlier `JUMPDEST`, counting down, decided
  over a bounded unrolling), a forward branch diamond, a jump to a non-`JUMPDEST`
  (the halt edge), the underflow halts, and `PC`/`JUMPDEST`; a witness for a value
  computed *after* a `JUMP` carries back through `L`, and a control-flow
  reachability decides through the `btor2-smtlib` z3 bridge. `PUSH0`/`MSIZE`/gas
  /`CALL`/`RETURN`/`REVERT`/logs stay deferred. Non-control-flow programs are
  byte-identical to v0.7 (the control-flow nodes are emitted only for the
  control-flow opcodes; the `jumpdests` scan emits no BTOR2).

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** EVM — [`languages/evm`](../../languages/evm/README.md).
- **Target.** BTOR2 — [`languages/btor2`](../../languages/btor2/README.md).
- **Translator `T`.** A spec-derived per-opcode lowering to a BTOR2
  transition system: a 256-bit stack, byte-addressed memory and
  word-addressed storage as arrays, `pc`, halt/`REVERT`; PC-keyed dispatch;
  init/next/constraint/bad. Deterministic and schema-predictable. Requires
  bv256.
- **Source interpreter.** The **shared** EVM interpreter
  ([`languages/evm`](../../languages/evm/README.md)) — reused; contributed
  by this pair if first.
- **Target interpreter.** The **shared** BTOR2 interpreter — reused.
- **Target-to-source interpreter `L`.** Decodes a BTOR2/solver witness into
  an EVM behavior (calldata/environment + the reaching run). Pair-owned.

## Projection `π`

Post-step stack / memory / storage-delta / halt observables (as the EVM
interpreter exposes them) mapped onto the BTOR2 state variables.

*Slice `π` (as built):* `{ pc, sp, s0 … s15, m0 … m63, s_at_0 … s_at_7, halted }`
— the program counter (a byte offset), the operand-stack depth, the 16 bv256
stack cells, the `MEM_WINDOW = 64`-byte memory window (`bv8` each, the lowest
memory bytes), the `STORE_WINDOW = 8`-key storage window (`bv256` each, the values
at keys 0..7), and the halt flag. Both the byte-memory and storage observables are
*windows*, not the whole arrays, because the shared BTOR2 trace exposes bit-vector
state only (see SPEC.md §1.5 / §1.6). A store/load outside a window is still
validated because its loaded value lands on the stack (already in `π`).

## Fidelity target + evidence

- **`checked`** — the commuting-square oracle under `π` on a corpus; the
  bv256 + array translator output is additionally corroborated by deciding
  it native-vs-bridged through [`btor2-smtlib`](../btor2-smtlib/README.md)
  ([`SOLVERS.md`](../../SOLVERS.md) §7).
- Certificates lift discharged questions to `proved`.

## Soundness story

Lowering vs. witness replay cross-check under `π`; the shared EVM
interpreter is anchored to **KEVM** (or EVM-Dafny / eth-isabelle) as the
gold reference ([`languages/evm`](../../languages/evm/README.md),
[`PAIRING.md`](../../PAIRING.md) §6).

## Notes for the implementing agent

- v2 absorbed the EVM translator but never registered it as a pair because
  its translator emitted a flat BTOR2 string; the registration work is to
  restructure it into a faithful **layered** artifact ([`ARCHITECTURE.md`](../../ARCHITECTURE.md)).
- Reuse the BTOR2 core; contribute the shared EVM interpreter validated
  against KEVM. Confirm bv256 + arrays round-trip in the BTOR2 I/O first.
