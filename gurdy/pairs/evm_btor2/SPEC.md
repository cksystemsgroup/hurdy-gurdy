# Translation specification — `evm-btor2` (stack/arithmetic + byte-memory + storage slice)

A self-contained, reviewable spec for the EVM → BTOR2 translator `T` and its
target-to-source interpreter `L` ([`PAIRING.md`](../../../PAIRING.md) §2, §6).
Anyone who has read the source bytecode and this spec can reproduce `T`'s
output byte-for-byte (the predictability test) — though the pair declares
`checked` fidelity, since faithfulness is established by the commuting-square
oracle every run, not by a written derivation alone.

## 0. Scope (stack/arithmetic + byte-addressed memory + persistent storage)

In scope, over 256-bit words: the **full push family** **`PUSH1` (0x60)** ..
**`PUSH32` (0x7f)** (an `n`-byte big-endian inline immediate), the binary
arithmetic **`ADD` (0x01)** / **`MUL` (0x02)** / **`SUB` (0x03)**, the
unsigned **`DIV` (0x04)** / **`MOD` (0x06)** and the **signed** **`SDIV` (0x05)**
/ **`SMOD` (0x07)** (each division/modulo with the EVM **by-zero = 0** special
case, and `SDIV` additionally with the **`INT_MIN / -1`** wrap-to-`INT_MIN`
case), the stack shuffles **`POP` (0x50)**, the **duplications** **`DUP1`
(0x80)** .. **`DUP16` (0x8f)**, the **swaps** **`SWAP1` (0x90)** .. **`SWAP16`
(0x9f)**, **`STOP` (0x00)**, the **byte-addressed memory ops** **`MLOAD`
(0x51)** / **`MSTORE` (0x52)** / **`MSTORE8` (0x53)**, and the **persistent
storage ops** **`SLOAD` (0x54)** / **`SSTORE` (0x55)** — the single-successor
bv256 stack family plus an `Array bv256 bv8` memory and an `Array bv256 bv256`
storage, with no jump-dest / control-flow machinery. Every other EVM opcode
hard-aborts at decode/translate time with `unsupported: evm:<MNEMONIC>`
(BENCHMARKS.md §3) — never silently dropped. Control flow (`JUMP`/`JUMPI`),
**`PUSH0`** (it carries no immediate), and `MSIZE` are deliberately deferred.
Status `partial`; coverage 78 / 144 spec opcodes (32 PUSH + 16 DUP + 16 SWAP +
ADD/MUL/SUB/DIV/MOD/SDIV/SMOD/POP/STOP + MLOAD/MSTORE/MSTORE8 + SLOAD/SSTORE).
Built on EVM shared interpreter **v0.7**.

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
  bytecode, or by an exceptional halt (stack underflow/overflow).

**Cell-update rule (the load-bearing convention).** Popped cells are **left
with their stale value** — never cleared. This is what lets `T` and `I_s` agree
cell-by-cell under the projection without modeling a "cleared" sentinel.

### Per-opcode transition (post-step state)

Let `δ = n+1` be the instruction length of a `PUSH{n}` (`PUSH1` → 2, … `PUSH32`
→ 33); every other in-scope opcode has length 1. `a := s{sp-1}` is the top,
`b := s{sp-2}` the next. For `DUP{n}`/`SWAP{n}` the index `n` is `1 ≤ n ≤ 16`.

| opcode | guard | effect |
|--------|-------|--------|
| `PUSH{n} v` (`1 ≤ n ≤ 32`) | `sp ≥ 16` | exceptional halt: `halted := 1`, `pc += δ` |
|             | else      | `s{sp} := v` (`v` = big-endian `n`-byte immediate); `sp += 1`; `pc += δ` |
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
| `STOP`    | —         | `halted := 1`, `pc += 1` |

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

## 2. The BTOR2 transition system `T(p)`

`T` decodes the fixed bytecode into `(pc, opcode, immediate)` instructions
(aborting on any unsupported opcode), then emits one BTOR2 transition system:

- **State:** `pc` (bv256), `s0 … s15` (bv256), `sp` (bv256), `halted` (bv1).
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
  `sp := init_sp` (default 0), `halted := 0`. The `mem` and `storage` arrays are
  zero-initialized (the evaluator's array default), and each window state
  (`m{i}` / `s_at_{i}`) `:= 0`.
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
all run over fixed ranges, and node ids are allocated monotonically by the shared
`Builder`; the output is then `canonicalize`d (native-checker node ordering). No
iteration, hash, filesystem, or timestamp order reaches the bytes. Twice-and-diff
holds.

## 3. The projection `π`

```
π = { pc, sp, s0 … s15, m0 … m{W-1}, s_at_0 … s_at_{S-1}, halted }
                                  (W = MEM_WINDOW = 64, S = STORE_WINDOW = 8)
```

The memory window `m0 … m{W-1}` is the bit-vector projection of the byte map
(§1.5); the storage window `s_at_0 … s_at_{S-1}` is the bit-vector projection of
the word map (§1.6). Both are present in *every* source row (zero where the region
is untouched); `L` zero-fills each for a BTOR2 trace that omits the corresponding
window states (a program touching neither memory nor storage), so the equality up
to `π` holds whether or not a program uses memory and/or storage.

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
