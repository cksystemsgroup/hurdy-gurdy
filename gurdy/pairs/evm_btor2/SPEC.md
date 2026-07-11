# Translation specification — `evm-btor2` (stack/arithmetic + byte-memory + storage + control-flow + terminal slice)

A self-contained, reviewable spec for the EVM → BTOR2 translator `T` and its
target-to-source interpreter `L` ([`PAIRING.md`](../../../PAIRING.md) §2, §6).
Anyone who has read the source bytecode and this spec can reproduce `T`'s
output byte-for-byte (the predictability test) — though the pair declares
`checked` fidelity, since faithfulness is established by the commuting-square
oracle every run, not by a written derivation alone.

## 0. Scope (stack/arithmetic + byte-addressed memory + persistent storage + control flow + terminal halts)

In scope, over 256-bit words: the **full push family** **`PUSH1` (0x60)** ..
**`PUSH32` (0x7f)** (an `n`-byte big-endian inline immediate) and **`PUSH0`
(0x5f)** (the constant-0 push, *no* inline immediate), the binary
arithmetic **`ADD` (0x01)** / **`MUL` (0x02)** / **`SUB` (0x03)**, the
unsigned **`DIV` (0x04)** / **`MOD` (0x06)** and the **signed** **`SDIV` (0x05)**
/ **`SMOD` (0x07)** (each division/modulo with the EVM **by-zero = 0** special
case, and `SDIV` additionally with the **`INT_MIN / -1`** wrap-to-`INT_MIN`
case), the stack shuffles **`POP` (0x50)**, the **duplications** **`DUP1`
(0x80)** .. **`DUP16` (0x8f)**, the **swaps** **`SWAP1` (0x90)** .. **`SWAP16`
(0x9f)**, **`STOP` (0x00)**, the **byte-addressed memory ops** **`MLOAD`
(0x51)** / **`MSTORE` (0x52)** / **`MSTORE8` (0x53)**, the **persistent
storage ops** **`SLOAD` (0x54)** / **`SSTORE` (0x55)**, the **control-flow
ops** **`JUMP` (0x56)** / **`JUMPI` (0x57)** / **`JUMPDEST` (0x5b)** / **`PC`
(0x58)**, and the **terminal/halt ops** **`RETURN` (0xf3)** / **`REVERT`
(0xfd)** / **`INVALID` (0xfe)** — the bv256 stack family plus an `Array bv256
bv8` memory, an `Array bv256 bv256` storage, the **first non-linear control
flow** (a dynamic `pc` resolved against the static `JUMPDEST` set, §1.7), and a
**halt-status observable** `status` that records *why* a run halted (success /
revert / exceptional, §1.8). Every other EVM opcode hard-aborts at
decode/translate time with `unsupported: evm:<MNEMONIC>` (BENCHMARKS.md §3) —
never silently dropped. `MSIZE` and gas / `CALL` / `CREATE` / `LOG` are
deliberately deferred. Status `partial`; coverage 86 / 144 spec opcodes (32 PUSH
+ PUSH0 + 16 DUP + 16 SWAP + ADD/MUL/SUB/DIV/MOD/SDIV/SMOD/POP/STOP +
MLOAD/MSTORE/MSTORE8 + SLOAD/SSTORE + JUMP/JUMPI/JUMPDEST/PC +
RETURN/REVERT/INVALID). Built on EVM shared interpreter **v0.9**.

## 1. The EVM machine model

A bounded-stack abstraction of the EVM execution semantics
([`languages/evm`](../../../languages/evm/README.md)), shared by `T`, the source
interpreter `I_s`, and `L`:

- **`pc`** — a **byte** offset into the bytecode. A `PUSH{n}` (`1 ≤ n ≤ 32`)
  carries its `n`-byte big-endian immediate *inline* (the bytes at `pc+1 … pc+n`),
  so it advances `pc` by `n+1` (`PUSH1` by 2, … `PUSH32` by 33); every other
  in-scope opcode advances `pc` by 1.
- **Operand stack** — `STACK_SIZE = 16` cells `s0 … s15`, each a 256-bit word,
  plus a depth **`sp`** = the number of live items. `s{i}` holds the item at
  depth `i`; `s0` is the bottom, `s{sp-1}` the top.
- **Memory** — a **byte-addressed, zero-initialized, unbounded** region `mem`
  (a byte map `addr ↦ byte`). `MSTORE`/`MLOAD` operate on the 32-byte
  **big-endian** word at a byte offset; `MSTORE8` on a single byte. EVM gas /
  the memory-expansion cost is **out of scope** (the data is modeled, not the
  cost). The **memory observable** in `π` is a fixed window `m0 … m{W-1}` of the
  lowest `W = MEM_WINDOW = 64` memory bytes, each a byte `0..255` — a bit-vector
  projection of the byte map (see §1.5 / §3 for why a window, not the whole
  array).
- **Storage** — a **persistent, zero-initialized** 256-bit-key → 256-bit-value
  map `storage` (a word map `key ↦ value`; both key and value are full bv256
  words, *unlike* the byte-addressed memory). `SSTORE`/`SLOAD` operate on the
  whole word at a key — no byte assembly. EVM gas / warm-cold accounting /
  refunds are **out of scope** (the data is modeled, not the cost). The
  **storage observable** in `π` is a fixed window `s_at_0 … s_at_{S-1}` of the
  values at keys `0 … S-1` (`S = STORE_WINDOW = 8`), each a full bv256 word — the
  word-keyed analogue of the memory window (see §1.6 / §3).
- **`halted`** — a 1-bit flag, set by `STOP`, by running off the end of the
  bytecode, by `RETURN` / `REVERT` / `INVALID` (§1.8), by an exceptional halt
  (stack underflow/overflow), or by a `JUMP`/`JUMPI` to a position that is not a
  valid `JUMPDEST` (the invalid-jump exceptional halt, §1.7). It stays exactly
  `status ≠ running`.
- **`status`** — an 8-bit **halt-status** observable recording *why* the run
  halted: `running = 0`, `success = 1` (`STOP` / off-the-end / `RETURN`),
  `revert = 2` (`REVERT`), `exceptional = 3` (`INVALID` / underflow / overflow /
  invalid jump). See §1.8.

**Cell-update rule (the load-bearing convention).** Popped cells are **left
with their stale value** — never cleared. This is what lets `T` and `I_s` agree
cell-by-cell under the projection without modeling a "cleared" sentinel.

### Per-opcode transition (post-step state)

Let `δ = n+1` be the instruction length of a `PUSH{n}` (`PUSH1` → 2, … `PUSH32`
→ 33); every other in-scope opcode has length 1. `a := s{sp-1}` is the top,
`b := s{sp-2}` the next. For `DUP{n}`/`SWAP{n}` the index `n` is `1 ≤ n ≤ 16`.
**Every "exceptional halt" row below also sets `status := exceptional`**; the
table writes only `halted := 1` for brevity, and §1.8 covers the success/revert
statuses that the terminal ops set.

| opcode | guard | effect |
|--------|-------|--------|
| `PUSH{n} v` (`1 ≤ n ≤ 32`) | `sp ≥ 16` | exceptional halt: `halted := 1`, `pc += δ` |
|             | else      | `s{sp} := v` (`v` = big-endian `n`-byte immediate); `sp += 1`; `pc += δ` |
| `PUSH0`   | `sp ≥ 16` | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp} := 0` (the constant 0, no inline immediate); `sp += 1`; `pc += 1` |
| `ADD`     | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp-2} := (a + b) mod 2²⁵⁶`; `sp -= 1`; `pc += 1` |
| `MUL`     | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp-2} := (a · b) mod 2²⁵⁶`; `sp -= 1`; `pc += 1` |
| `SUB`     | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp-2} := (a − b) mod 2²⁵⁶` (top minus next); `sp -= 1`; `pc += 1` |
| `DIV`     | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp-2} := (b = 0 ? 0 : ⌊a / b⌋)` (unsigned; by-zero **= 0**); `sp -= 1`; `pc += 1` |
| `MOD`     | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp-2} := (b = 0 ? 0 : a mod b)` (unsigned; by-zero **= 0**); `sp -= 1`; `pc += 1` |
| `SDIV`    | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp-2} := (b = 0 ? 0 : (a = INT_MIN ∧ b = −1 ? INT_MIN : trunc(a / b)))` (signed, truncating; by-zero **= 0**, **`INT_MIN / −1` = `INT_MIN`**); `sp -= 1`; `pc += 1` |
| `SMOD`    | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp-2} := (b = 0 ? 0 : a srem b)` (signed remainder, **sign of the dividend**; by-zero **= 0**); `sp -= 1`; `pc += 1` |
| `POP`     | `sp < 1`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `sp -= 1` (top dropped, cell left stale); `pc += 1` |
| `DUP{n}`  | `sp < n` or `sp ≥ 16` | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp} := s{sp-n}` (copy the n-th item onto the top); `sp += 1`; `pc += 1` |
| `SWAP{n}` | `sp < n+1` | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | swap `s{sp-1}` ↔ `s{sp-1-n}` (top with the (n+1)-th item); `sp` unchanged; `pc += 1` |
| `MLOAD`   | `sp < 1`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `off := a` (top); `s{sp-1} := mem[off..off+31]` (32-byte big-endian word, zero-filled where never written); `sp` unchanged (offset popped, word pushed); `pc += 1` |
| `MSTORE`  | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `off := a` (top), `val := b` (next); `mem[off..off+31] := BE₃₂(val)` (most significant byte at `off`); `sp -= 2`; `pc += 1` |
| `MSTORE8` | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `off := a` (top), `val := b` (next); `mem[off] := val mod 256` (the low byte); `sp -= 2`; `pc += 1` |
| `SLOAD`   | `sp < 1`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `key := a` (top); `s{sp-1} := storage[key]` (full bv256 word, `0` where never written); `sp` unchanged (key popped, value pushed); `pc += 1` |
| `SSTORE`  | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `key := a` (top), `val := b` (next); `storage[key] := val`; `sp -= 2`; `pc += 1` |
| `JUMPDEST`| —         | no-op marker; `pc += 1` (no stack/halt effect) |
| `PC`      | `sp ≥ 16` | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp} := off` (the byte offset of *this* `PC`); `sp += 1`; `pc += 1` |
| `JUMP`    | `sp < 1`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else, `a ∈ JD` | `sp -= 1`; `pc := a` (the popped `dest` is a valid `JUMPDEST`) |
|           | else      | exceptional halt: `sp -= 1`; `halted := 1`, `pc += 1` (invalid jump) |
| `JUMPI`   | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else, `b = 0` | not taken: `sp -= 2`; `pc += 1` (fall through) |
|           | else, `b ≠ 0 ∧ a ∈ JD` | taken: `sp -= 2`; `pc := a` (valid `JUMPDEST`) |
|           | else, `b ≠ 0` | exceptional halt: `sp -= 2`; `halted := 1`, `pc += 1` (invalid) |
| `STOP`    | —         | success halt: `halted := 1`, `status := success`, `pc += 1` |
| `RETURN`  | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | success halt: `off := a` (top), `len := b` (next) consumed; `sp -= 2`; `halted := 1`, `status := success`, `pc += 1` (return data `mem[off..off+len]`, already in `π`) |
| `REVERT`  | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | revert halt: `off := a` (top), `len := b` (next) consumed; `sp -= 2`; `halted := 1`, `status := revert`, `pc += 1` |
| `INVALID` | —         | exceptional halt: `halted := 1`, `status := exceptional`, `pc += 1` (no operands) |

`ADD`/`MUL` are commutative; `SUB`/`DIV`/`MOD`/`SDIV`/`SMOD` are non-commutative
with `a` = top, `b` = next (`SUB` = `a − b`, `DIV` = `⌊a / b⌋`, `MOD` = `a mod
b`), so operand order is load-bearing. EVM `SUB`/`MUL` wrap mod 2²⁵⁶, which the
BTOR2 `sub`/`mul` on bv256 do natively — no explicit masking needed. **`DIV`/`MOD`
are unsigned**, and EVM defines **division/modulo by zero as `0`** (not a trap):
`DIV(a, 0) = 0`, `MOD(a, 0) = 0`. The BTOR2 `udiv`/`urem`, however, carry the
*SMT-LIB* by-zero convention (all-ones for `bvudiv`, the dividend for `bvurem`),
so the lowering wraps them in an explicit zero-guard — `ite(b = 0, 0, …)` (§2) —
to recover EVM's `= 0`.

**`SDIV`/`SMOD` are signed** (two's-complement) over bv256, and use **truncating**
(round-toward-zero, C-style) division, which is exactly what BTOR2 `sdiv`/`srem`
compute — `srem` already takes the **sign of the dividend**, matching EVM. They
have two EVM special cases the SMT operators do not carry as-is: (i) **by-zero =
`0`** (BTOR2 `sdiv` by zero gives all-ones/1, `srem` gives the dividend), and
(ii) **`SDIV(INT_MIN, −1) = INT_MIN`** — signed overflow that *wraps* with no
trap (`2²⁵⁵` truncated to 256 bits is `INT_MIN` itself, the bv256 value with only
the top bit set). So the lowering wraps `sdiv`/`srem` in explicit guards (§2):
`SDIV(a, b) = ite(b = 0, 0, ite(a = INT_MIN ∧ b = −1, INT_MIN, sdiv(a, b)))` and
`SMOD(a, b) = ite(b = 0, 0, srem(a, b))`, with `INT_MIN = 2²⁵⁵` and `−1` =
all-ones. The interpreter mirrors these exactly (signed-interpret the operands,
truncating quotient/remainder, the same two guards). Stack underflow/overflow are
EVM *exceptional halts* — a defined, deterministic edge that sets `halted`,
distinct from an *unsupported opcode* (a typed abort).

`DUP{n}` and `SWAP{n}` are pure stack shuffles keyed on the index `n` the
opcode byte encodes (`DUP{n} = 0x80 + (n-1)`, `SWAP{n} = 0x90 + (n-1)`):
`DUP{n}` reads `s{sp-n}` (the `DUP1` lowering with read index `sp-1` generalized
to `sp-n`) and writes `s{sp}`; `SWAP{n}` reads the top `s{sp-1}` and the
(n+1)-th item `s{sp-1-n}` and writes each into the other's slot, leaving `sp`
unchanged. Both read the *current* cells, so the swap is simultaneous. **The
bounded stack (`STACK_SIZE = 16`) is load-bearing here:** `DUP16` needs depth 16
for its read but then overflows on the write, and `SWAP16` needs depth 17 (top +
17th item) which the 16-cell stack can never reach — so `DUP16` and `SWAP16`
*always* take the exceptional-halt edge in this slice (the real EVM's
1024-deep stack would let them succeed). The square holds for these halting
edges exactly as for the value-changing ones.

### 1.5 Memory (`MLOAD` / `MSTORE` / `MSTORE8`)

Memory is a **byte-addressed, zero-initialized, unbounded** byte map. The three
ops all read their **byte offset** from the top of the stack (`off := s{sp-1}`):

- **`MSTORE off, val`** (`off` top, `val` next) writes the 32-byte **big-endian**
  encoding of `val` to `mem[off..off+31]` — the *most significant* byte at `off`,
  the *least significant* at `off+31` — then drops both operands (`sp -= 2`).
- **`MLOAD off`** reads the 32-byte big-endian word at `mem[off..off+31]` (bytes
  never written read as `0`) and writes it back to `s{sp-1}`; the offset is
  popped and the word pushed, so `sp` is **unchanged**.
- **`MSTORE8 off, val`** writes only `val mod 256` (the low byte) to `mem[off]`,
  then drops both operands (`sp -= 2`).

All three exceptional-halt on stack underflow (`MLOAD` needs 1 item, the stores
need 2). EVM gas / the memory-expansion cost is **out of scope** — the data is
modeled, not the cost.

**Observable, not the whole array.** The shared BTOR2 evaluator's trace exposes
only **bit-vector** state, not array state ([`languages/btor2/eval.py`](../../../gurdy/languages/btor2/eval.py)
`step` records bv states only), so memory cannot be projected as an array. The
memory observable in `π` is therefore a fixed **window** `m0 … m{W-1}` (`W =
MEM_WINDOW = 64`) of the lowest `W` memory bytes, each a `bv8` — a bit-vector
projection both `I_s` (the byte map) and `T` (window states reading the array,
§2) expose identically. A store/load *outside* the window is still validated
because its loaded value lands on the **stack** (already in `π`); the window
adds direct observation of writes that are never read back.

### 1.6 Storage (`SLOAD` / `SSTORE`)

Storage is a **persistent, zero-initialized** 256-bit-key → 256-bit-value word
map — the word-keyed analogue of memory, but *simpler*: keys and values are both
full bv256 words, so there is **no byte assembly** (a single array read/write,
not 32 chained ones). Both ops read their **key** from the top of the stack
(`key := s{sp-1}`):

- **`SSTORE key, val`** (`key` top, `val` next) sets `storage[key] := val`, then
  drops both operands (`sp -= 2`).
- **`SLOAD key`** reads `storage[key]` (keys never written read as `0`) and writes
  it back to `s{sp-1}`; the key is popped and the value pushed, so `sp` is
  **unchanged**.

`SSTORE` exceptional-halts on `sp < 2`, `SLOAD` on `sp < 1`. EVM gas / warm-cold
accounting / refunds are **out of scope** — the data is modeled, not the cost.

**Observable, not the whole array** (as for memory, §1.5). The storage observable
in `π` is a fixed **window** `s_at_0 … s_at_{S-1}` (`S = STORE_WINDOW = 8`) of the
values at keys `0 … S-1`, each a `bv256` — a bit-vector projection both `I_s` (the
word map) and `T` (window states reading the storage array, §2) expose
identically. A store/load at a key *outside* the window is still validated because
its loaded value lands on the **stack** (already in `π`); the window adds direct
observation of writes that are never read back.

### 1.7 Control flow (`JUMP` / `JUMPI` / `JUMPDEST` / `PC`)

The **first non-linear control flow**. The EVM is byte-addressed and its jump
destinations are *dynamic* — `JUMP`/`JUMPI` pop the target *byte offset* off the
stack — but the set of **valid** targets is statically fixed by the bytecode.

- **The valid-target set `JD`.** A jump may only land on a **`JUMPDEST` (0x5b)**
  byte. `JD` is computed by a one-pass scan of the bytecode that records every
  offset holding a `0x5b`, **skipping the inline immediate bytes of each
  `PUSH{n}`** — so a `0x5b` that falls *inside* a `PUSH` immediate is **not** a
  valid destination (the standard EVM jump-destination-analysis rule). `JD` is the
  single source of truth `T` and `I_s` share (`interp.jumpdests`).
- **`JUMPDEST` (0x5b)** — a **no-op** marking a valid target: `pc += 1`, no stack
  or `halted` effect. (A `JUMP` lands here when its `dest ∈ JD`, so the PC-keyed
  dispatch simply continues from `off+1`.)
- **`PC` (0x58)** — pushes the **byte offset of the `PC` instruction itself**:
  `s{sp} := off`, `sp += 1`, `pc += 1` (overflow `sp ≥ 16` → exceptional halt).
  It is the `PUSH{n}` lowering with the immediate replaced by the constant `off`.
- **`JUMP` (0x56)** — pops `dest := s{sp-1}` (`sp -= 1`); if `dest ∈ JD` sets
  `pc := dest`, else exceptional halt (`halted := 1`, `pc := off+1`). Stack
  underflow (`sp < 1`) → exceptional halt.
- **`JUMPI` (0x57)** — pops `dest := s{sp-1}` then `cond := s{sp-2}` (`sp -= 2`);
  if `cond ≠ 0` resolve `dest` as for `JUMP` (valid → `pc := dest`, invalid →
  halt); if `cond = 0` fall through (`pc := off+1`). Underflow (`sp < 2`) → halt.

A jump to a non-`JUMPDEST` is an EVM **exceptional halt** (a defined,
deterministic edge that sets `halted` and advances `pc` to `off+1`), exactly the
existing halt edge used for underflow/overflow — *not* a typed `unsupported`
abort. EVM gas / out-of-gas is **out of scope** (an unbounded loop simply runs to
the interpreter's `max_steps` / the BMC unrolling bound `k`).

**The dynamic-`pc` lowering** (mirrored exactly by `I_s`). `JUMP`/`JUMPI` lower the
dynamic destination as an **ITE chain over the static `JD` offsets**:

```
target := ite(dest = jd0, jd0, ite(dest = jd1, jd1, …, off+1))
is_valid := (dest = jd0) ∨ (dest = jd1) ∨ … ∨ (dest = jd_{k-1})
```

with `jd0 < jd1 < …` the **sorted** offsets of `JD` (so the chain's node order is
deterministic in the bytecode). The default of the `target` chain is `off+1`,
which is exactly the post-step `pc` on the invalid-jump halt edge, so `target`
serves both the valid (`pc := dest`) and the invalid (`pc := off+1`, `halted`)
cases. `JUMPI` additionally gates on `taken := (cond ≠ 0)`:
`chosen := ite(taken, target, off+1)`. The invalid-jump halt is
`is_valid = false ∧ active ∧ ¬underflow` (and, for `JUMPI`, `∧ taken`). This
makes `pc` a **function of the popped value** within the bounded program — the
direct analogue of how `riscv-btor2`/`aarch64-btor2` lower a dynamic/conditional
`pc` as an `ite` over the next-pc — and a back-edge (a `dest` earlier than `off`)
is just an earlier offset in the same `JD` chain, decided over a bounded
unrolling.

### 1.8 Terminal/halt ops (`RETURN` / `REVERT` / `INVALID`) and the halt-status model

The **first halts that carry a *why***. Up to v0.8 every halt set the same
`halted` flag; v0.9 adds a small **halt-status observable** `status` (a `bv8`,
values `0..3`) so the commuting square checks *why* a run stopped, not just
*that* it stopped:

| `status` | value | set by |
|----------|-------|--------|
| `running` | 0 | not halted |
| `success` | 1 | `STOP`, running off the end, `RETURN` |
| `revert` | 2 | `REVERT` |
| `exceptional` | 3 | `INVALID`, stack underflow/overflow, an invalid jump |

`halted` stays exactly `status ≠ running`, so all pre-v0.9 observables are
unchanged (`STOP`/off-the-end remain `success`; every underflow/overflow/
invalid-jump edge that set `halted` now also sets `status := exceptional`). The
three terminal ops:

- **`PUSH0` (0x5f)** — not a halt, but lands here as the v0.9 stack op it pairs
  with: pushes the **constant 0** (`s{sp} := 0`, `sp += 1`, `pc += 1`), with no
  inline immediate (so it is *not* in the `PUSH{n}` width family); `sp ≥ 16` →
  exceptional halt. It is the `PUSH{n}` lowering with the immediate fixed to 0.
- **`RETURN` (0xf3)** — pops `off := s{sp-1}` (top) then `len := s{sp-2}` (next),
  consuming both (`sp -= 2`), and **halts with `status := success`**. The return
  data is `mem[off..off+len]`, **already observable** through the memory window
  (`m0 … m{W-1}`) — no new return-data state is introduced; the operands are
  consumed and the run halts successfully. Stack underflow (`sp < 2`) → exceptional
  halt.
- **`REVERT` (0xfd)** — pops `off` + `len` exactly as `RETURN` (`sp -= 2`) and
  **halts with `status := revert`** (a distinct terminal status from `success`).
  Underflow (`sp < 2`) → exceptional halt.
- **`INVALID` (0xfe)** — **halts with `status := exceptional`**; consumes no
  operands (`sp` unchanged, `pc += 1`).

These are *defined halt edges* (like underflow/overflow), **not** typed
`unsupported` aborts. EVM gas / out-of-gas, return-data buffers consumed by a
caller, and the `CALL`/`CREATE`/`LOG` machinery stay **out of scope**.

### 1.9 Bitwise ops (`AND` / `OR` / `XOR` / `NOT` / `ISZERO`) — v0.10

Bit-parallel logical ops over bv256 (built on EVM shared interpreter **v0.10**),
mirroring `interp.py`'s branches exactly:

| opcode | guard | effect |
|--------|-------|--------|
| `AND` (0x16) | `sp < 2` | exceptional halt: `halted := 1`, `pc += 1` |
|              | else     | `s{sp-2} := a & b` (bitwise, `a` = top, `b` = next); `sp -= 1`; `pc += 1` |
| `OR` (0x17)  | `sp < 2` | exceptional halt: `halted := 1`, `pc += 1` |
|              | else     | `s{sp-2} := a | b`; `sp -= 1`; `pc += 1` |
| `XOR` (0x18) | `sp < 2` | exceptional halt: `halted := 1`, `pc += 1` |
|              | else     | `s{sp-2} := a ^ b`; `sp -= 1`; `pc += 1` |
| `NOT` (0x19) | `sp < 1` | exceptional halt: `halted := 1`, `pc += 1` |
|              | else     | `s{sp-1} := ~a` (256-bit complement of the top); `sp` unchanged; `pc += 1` |
| `ISZERO` (0x15) | `sp < 1` | exceptional halt: `halted := 1`, `pc += 1` |
|                 | else     | `s{sp-1} := (a = 0 ? 1 : 0)`; `sp` unchanged; `pc += 1` |

`AND`/`OR`/`XOR` are commutative binary ops folded into the binary block (§1.4):
the result is the single BTOR2 `op2` (`and`/`or`/`xor` on bv256), written to
`s{sp-2}` with `sp -= 1`. `NOT` is a unary pop-1/push-1: the result is
`op1("not", …, a)` written back to the top `s{sp-1}`, `sp` unchanged. `ISZERO` is
a unary pop-1/push-1 whose result is the bv1 predicate `eq(a, 0)` zero-extended to
bv256 (`uext` of the bv1 to bv256 gives the constant `1`/`0`), written to
`s{sp-1}`, `sp` unchanged. All exceptional-halt on stack underflow.

## 2. The BTOR2 transition system `T(p)`

`T` decodes the fixed bytecode into `(pc, opcode, immediate)` instructions
(aborting on any unsupported opcode), then emits one BTOR2 transition system:

- **State:** `pc` (bv256), `s0 … s15` (bv256), `sp` (bv256), `halted` (bv1), and
  the halt-status `status` (bv8, v0.9 — emitted in **every** program, since every
  halt carries a *why*; unlike the conditional mem/storage states it is always
  present, right after `halted`).
  When the program touches memory: an array `mem` (`Array bv256 bv8`) and the
  window states `m0 … m{W-1}` (`bv8`). These are emitted **only** if some
  `MLOAD`/`MSTORE`/`MSTORE8` is present (mirroring `ebpf-btor2`'s conditional
  `mem` array), so non-memory programs are byte-identical to before. When the
  program touches storage: an array `storage` (`Array bv256 bv256`) and the
  window states `s_at_0 … s_at_{S-1}` (`bv256`), emitted **only** if some
  `SLOAD`/`SSTORE` is present — and emitted *after* the memory states, so adding
  storage does not shift any memory node id, and a program that uses neither stays
  byte-identical.
- **Init:** `pc := entry`, `s{i} := init_stack[i]` (default 0),
  `sp := init_sp` (default 0), `halted := 0`, `status := running (0)`. The `mem`
  and `storage` arrays are zero-initialized (the evaluator's array default), and
  each window state (`m{i}` / `s_at_{i}`) `:= 0`.
- **Next (PC-keyed ITE dispatch).** For each decoded instruction at byte offset
  `off`, with `active = (pc == off) ∧ ¬halted`, the per-opcode effect of §1.4
  is folded into the running `next_*` expressions via `ite(active, …, prev)`.
  The dynamic reads `s{sp-1}` / `s{sp-2}` of
  `ADD`/`MUL`/`SUB`/`DIV`/`MOD`/`SDIV`/`SMOD`,
  `s{sp-n}` of `DUP{n}`, and `s{sp-1}` / `s{sp-1-n}` of `SWAP{n}`, and the
  dynamic write targets `s{sp}` (`PUSH{n}`/`DUP{n}`) / `s{sp-2}` (arithmetic) /
  `s{sp-1}` and `s{sp-1-n}` (`SWAP{n}`), are realized as **index muxes**: a chain
  of `ite(index == j, s_j, …)` over the 16 cells. For `ADD`/`MUL`/`SUB` the result
  is the BTOR2 op (`add`/`mul`/`sub` on bv256, which already wrap mod 2²⁵⁶). For
  the unsigned `DIV`/`MOD` the result is the **zero-guarded**
  `ite(b = 0, 0, udiv(a, b))` / `ite(b = 0, 0, urem(a, b))` — the explicit guard
  is what recovers EVM's by-zero `= 0` from BTOR2's SMT `udiv`/`urem` by-zero
  convention. For the signed `SDIV`/`SMOD` the result is built over BTOR2
  `sdiv`/`srem` (truncating; `srem` takes the sign of the dividend) with explicit
  guards: `SDIV = ite(b = 0, 0, ite(a = INT_MIN ∧ b = −1, INT_MIN, sdiv(a, b)))`
  (the inner guard, `eq(a, INT_MIN) ∧ eq(b, all-ones)`, recovers the EVM
  `INT_MIN / −1` wrap) and `SMOD = ite(b = 0, 0, srem(a, b))`, with the constants
  `INT_MIN = 2**255` and `−1` = all-ones (`MASK256`). `POP` only decrements `sp`
  (no cell write); `SWAP{n}` writes two
  cells but leaves `sp` unchanged. This is the single source of truth `L`
  mirrors, so the cross-check compares two realizations of the same rule.
- **Memory lowering (array read/write).** The offset `off := s{sp-1}` is selected
  by the same index mux as the stack ops. **`MSTORE`** lowers to 32 chained
  array `write`s — byte `i` is `slice(val, 8·(31−i)+7, 8·(31−i))` written at
  `off + i`, so the most significant byte lands at `off` (big-endian).
  **`MSTORE8`** is a single `write` of `slice(val, 7, 0)` at `off`. **`MLOAD`**
  is 32 array `read`s `concat`enated big-endian (byte at `off` most significant)
  into a bv256 word, written back to `s{sp-1}` by the write mux. The array update
  is guarded `mem' := ite(do, written, mem)` (an `ite` over the array sort), so an
  underflow/inactive cycle leaves `mem` unchanged. Each **window state** advances
  by `next(m{i}) := read(mem', i)` (the post-step array at the fixed address `i`),
  so the bit-vector trace carries the memory observable into `π` exactly as the
  interpreter's byte map does. This array read/write lowering mirrors
  `ebpf-btor2`'s `_load`/`_store`; the byte order differs (EVM memory is
  big-endian, the eBPF MEM-mode loads are little-endian).
- **Storage lowering (array read/write, word-keyed).** The key `key := s{sp-1}` is
  selected by the same index mux as the stack ops. **`SLOAD`** is a *single* array
  `read` `storage[key]` (a never-written key reads the array default `0`), written
  back to `s{sp-1}` by the write mux. **`SSTORE`** is a *single* array
  `write(storage, key, val)`; the array update is guarded
  `storage' := ite(do, written, storage)`, so an underflow/inactive cycle leaves
  `storage` unchanged. Each **window state** advances by
  `next(s_at_{i}) := read(storage', i)` (the post-step array at the fixed key `i`),
  carrying the storage observable into `π`. This is the byte-memory lowering
  *without* the 32-byte big-endian assembly — word in, word out.
- **Control-flow lowering (dynamic `pc`).** `JUMPDEST` only advances `pc`. `PC`
  is the `PUSH{n}` lowering with the immediate replaced by the constant `off`. The
  dynamic destination of `JUMP`/`JUMPI` is `dest := s{sp-1}` (an index mux, as for
  the stack ops), resolved against the static `JD` set via the ITE/OR chains of
  §1.7 over the **sorted** offsets: `target := ite(dest = jd0, jd0, …, off+1)` and
  `is_valid := ⋁_i (dest = jd_i)`. `next_pc` is `ite(active, ite(underflow, off+1,
  resolved), prev)` (where `resolved` is `target` for `JUMP`, `ite(taken, target,
  off+1)` for `JUMPI`) — so `pc` advances to `off+1` on the underflow/invalid halt
  edge (mirroring the interpreter's `pc+1`) and to the popped target on a valid
  jump. The invalid-jump halt folds into `next_halted` as `ite(halt_here, 1,
  prev)` with `halt_here = (active ∧ underflow) ∨ (do ∧ [taken ∧] ¬is_valid)`.
  This is the direct EVM analogue of how `riscv-btor2`/`aarch64-btor2` fold a
  conditional/dynamic next-pc into the transition `ite`.
- **Terminal/halt-status lowering.** `PUSH0` is the `PUSH{n}` lowering with the
  immediate constant `0` and a 1-byte advance. The halt status folds through a
  single helper `halt_with(cond, kind)` that, on `cond`, sets `next_halted :=
  ite(cond, 1, prev)` **and** `next_status := ite(cond, kind, prev)` — so the
  status is recorded at exactly the same edges as `halted`. The pre-v0.9 halts use
  `kind = exceptional` (`halt_with(halt_here, exceptional)` everywhere a `halted`
  fold used to stand, including underflow/overflow/invalid-jump); `STOP` and
  off-the-end use `success`. `RETURN`/`REVERT` decode like a two-pop op: on the
  clean `do` cycle (`active ∧ ¬underflow`, `sp -= 2`) they `halt_with(do,
  success|revert)`, and on the underflow edge `halt_with(active ∧ underflow,
  exceptional)` (the two conditions are disjoint, so the fold order is
  immaterial). `INVALID` is `halt_with(active, exceptional)` with no stack effect.
  The return/revert data range `mem[off..off+len]` needs no new state — it is
  already in the memory window. `next(status, next_status)` is emitted once,
  alongside `next(halted, …)`.
- **Property (optional).** `property = {"stack_eq": [depth, val]}` emits a
  `bad` signal `s{depth} == val`, so a downstream reasoning bridge
  ([`btor2-smtlib`](../../../pairs/btor2-smtlib/README.md)) can decide
  reachability.

`T` requires **bv256** in the shared BTOR2 evaluator
([`languages/btor2`](../../../languages/btor2/README.md)); the memory ops
additionally use its **array** sort (`Array bv256 bv8`), and the storage ops a
second array sort (`Array bv256 bv256`) — both already exercised by the evaluator
(`ebpf-btor2` uses the byte array), reused here unchanged.

### Determinism

`T` is pure in `(code, entry, init_stack, init_sp, property)`. The dispatch is
keyed on byte offsets (a list, not a set), the cell loop, the 32-byte memory
read/write loops, the `MEM_WINDOW` window loop, and the `STORE_WINDOW` window loop
all run over fixed ranges, the `JUMPDEST` set `JD` is materialized as a **sorted
list** of offsets (the jump-resolution ITE/OR chains fold over it in offset order,
never a set's hash order), and node ids are allocated monotonically by the shared
`Builder`; the output is then `canonicalize`d (native-checker node ordering). No
iteration, hash, filesystem, or timestamp order reaches the bytes. Twice-and-diff
holds.

## 3. The projection `π`

```
π = { pc, sp, s0 … s15, m0 … m{W-1}, s_at_0 … s_at_{S-1}, halted, status }
                                  (W = MEM_WINDOW = 64, S = STORE_WINDOW = 8)
```

The memory window `m0 … m{W-1}` is the bit-vector projection of the byte map
(§1.5); the storage window `s_at_0 … s_at_{S-1}` is the bit-vector projection of
the word map (§1.6). Both are present in *every* source row (zero where the region
is untouched); `L` zero-fills each for a BTOR2 trace that omits the corresponding
window states (a program touching neither memory nor storage), so the equality up
to `π` holds whether or not a program uses memory and/or storage. The halt-status
`status` (§1.8) is present in *every* row (the BTOR2 `status` state is
unconditional), so the square checks *why* a run halted — distinguishing a
`success` (`STOP`/off-the-end/`RETURN`) from a `revert` (`REVERT`) and an
`exceptional` (`INVALID`/underflow/overflow/invalid-jump) halt — not merely *that*
it did.

The bottom edge of the commuting square is equality *up to* `π`: the EVM
behavior `I_s(p)` and the carried-back behavior `L(I_t(T(p)))` must agree on
every field of `π` at every step. The carry-back `L` reads the BTOR2 behavior's
state values (keyed by the symbols `T` emitted) and re-expresses them in the
EVM observable shape — the identity on `π`, since `T` named its state variables
to match `I_s`'s observables.

## 4. Soundness story (`checked`)

`T` and `L` share one source of truth — the per-opcode lowering of §1.4 — and
the commuting-square oracle runs both on the same inputs each run, asserting
`I_s(p) ≡_π L(I_t(T(p)))` and localizing any divergence to a (step, observable).
The BTOR2 run's first row is the *initial* state, so the source trace aligns
with the BTOR2 trace shifted by one cycle. The shared EVM interpreter is to be
anchored to **KEVM** as the gold oracle (future work; `languages/evm` brief).
For a `reachable` property, a BTOR2 witness replays through `L` to the
source-level stack behavior that exhibits it (carry-back).

## 5. Fidelity

**`checked`** — the square is validated under `π` on the test corpus every run
via the framework oracle. Not `proved`: there is no machine-checked certificate
that the square commutes for all inputs, only validation on the inputs tried.
