# Translation specification — `evm-btor2` (pure stack/arithmetic slice)

A self-contained, reviewable spec for the EVM → BTOR2 translator `T` and its
target-to-source interpreter `L` ([`PAIRING.md`](../../../PAIRING.md) §2, §6).
Anyone who has read the source bytecode and this spec can reproduce `T`'s
output byte-for-byte (the predictability test) — though the pair declares
`checked` fidelity, since faithfulness is established by the commuting-square
oracle every run, not by a written derivation alone.

## 0. Scope (pure stack/arithmetic slice)

In scope, over 256-bit words: the push immediates **`PUSH1` (0x60)** /
**`PUSH2` (0x61)** / **`PUSH4` (0x63)**, the binary arithmetic **`ADD` (0x01)**
/ **`MUL` (0x02)** / **`SUB` (0x03)**, the stack shuffles **`POP` (0x50)** /
**`DUP1` (0x80)**, and **`STOP` (0x00)** — the single-successor bv256 stack
family, with no jump-dest / control-flow machinery. Every other EVM opcode
hard-aborts at decode/translate time with `unsupported: evm:<MNEMONIC>`
(BENCHMARKS.md §3) — never silently dropped. Control flow
(`JUMP`/`JUMPI`), `DIV`/`MOD`, memory, and storage are deliberately deferred to
later rounds. Status `partial`; coverage 9 / 144 spec opcodes. Built on EVM
shared interpreter **v0.2**.

## 1. The EVM machine model

A bounded-stack abstraction of the EVM execution semantics
([`languages/evm`](../../../languages/evm/README.md)), shared by `T`, the source
interpreter `I_s`, and `L`:

- **`pc`** — a **byte** offset into the bytecode. A `PUSH{n}` carries its
  `n`-byte big-endian immediate *inline* (the bytes at `pc+1 … pc+n`), so it
  advances `pc` by `n+1` (`PUSH1` by 2, `PUSH2` by 3, `PUSH4` by 5); every other
  in-scope opcode advances `pc` by 1.
- **Operand stack** — `STACK_SIZE = 16` cells `s0 … s15`, each a 256-bit word,
  plus a depth **`sp`** = the number of live items. `s{i}` holds the item at
  depth `i`; `s0` is the bottom, `s{sp-1}` the top.
- **`halted`** — a 1-bit flag, set by `STOP`, by running off the end of the
  bytecode, or by an exceptional halt (stack underflow/overflow).

**Cell-update rule (the load-bearing convention).** Popped cells are **left
with their stale value** — never cleared. This is what lets `T` and `I_s` agree
cell-by-cell under the projection without modeling a "cleared" sentinel.

### Per-opcode transition (post-step state)

Let `δ = n+1` be the instruction length of a `PUSH{n}` (`PUSH1` → 2, `PUSH2`
→ 3, `PUSH4` → 5); every other in-scope opcode has length 1. `a := s{sp-1}` is
the top, `b := s{sp-2}` the next.

| opcode | guard | effect |
|--------|-------|--------|
| `PUSH{n} v` | `sp ≥ 16` | exceptional halt: `halted := 1`, `pc += δ` |
|             | else      | `s{sp} := v` (`v` = big-endian `n`-byte immediate); `sp += 1`; `pc += δ` |
| `ADD`     | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp-2} := (a + b) mod 2²⁵⁶`; `sp -= 1`; `pc += 1` |
| `MUL`     | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp-2} := (a · b) mod 2²⁵⁶`; `sp -= 1`; `pc += 1` |
| `SUB`     | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp-2} := (a − b) mod 2²⁵⁶` (top minus next); `sp -= 1`; `pc += 1` |
| `POP`     | `sp < 1`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `sp -= 1` (top dropped, cell left stale); `pc += 1` |
| `DUP1`    | `sp < 1` or `sp ≥ 16` | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `s{sp} := s{sp-1}`; `sp += 1`; `pc += 1` |
| `STOP`    | —         | `halted := 1`, `pc += 1` |

`ADD`/`MUL` are commutative; `SUB` is `a − b` (**top minus next**), so operand
order is load-bearing. EVM `SUB`/`MUL` wrap mod 2²⁵⁶, which the BTOR2 `sub`/`mul`
on bv256 do natively — no explicit masking needed. Stack underflow/overflow are
EVM *exceptional halts* — a defined, deterministic edge that sets `halted`,
distinct from an *unsupported opcode* (a typed abort).

## 2. The BTOR2 transition system `T(p)`

`T` decodes the fixed bytecode into `(pc, opcode, immediate)` instructions
(aborting on any unsupported opcode), then emits one BTOR2 transition system:

- **State:** `pc` (bv256), `s0 … s15` (bv256), `sp` (bv256), `halted` (bv1).
- **Init:** `pc := entry`, `s{i} := init_stack[i]` (default 0),
  `sp := init_sp` (default 0), `halted := 0`.
- **Next (PC-keyed ITE dispatch).** For each decoded instruction at byte offset
  `off`, with `active = (pc == off) ∧ ¬halted`, the per-opcode effect of §1.4
  is folded into the running `next_*` expressions via `ite(active, …, prev)`.
  The dynamic reads `s{sp-1}` / `s{sp-2}` of `ADD`/`MUL`/`SUB` and `s{sp-1}` of
  `DUP1`, and the dynamic write targets `s{sp}` (`PUSH{n}`/`DUP1`) / `s{sp-2}`
  (arithmetic), are realized as **index muxes**: a chain of
  `ite(index == j, s_j, …)` over the 16 cells. The arithmetic kind is the BTOR2
  op (`add`/`mul`/`sub` on bv256, which already wrap mod 2²⁵⁶); `POP` only
  decrements `sp` (no cell write). This is the single source of truth `L`
  mirrors, so the cross-check compares two realizations of the same rule.
- **Property (optional).** `property = {"stack_eq": [depth, val]}` emits a
  `bad` signal `s{depth} == val`, so a downstream reasoning bridge
  ([`btor2-smtlib`](../../../pairs/btor2-smtlib/README.md)) can decide
  reachability.

`T` requires **bv256** in the shared BTOR2 evaluator
([`languages/btor2`](../../../languages/btor2/README.md)); it uses no arrays in
this slice.

### Determinism

`T` is pure in `(code, entry, init_stack, init_sp, property)`. The dispatch is
keyed on byte offsets (a list, not a set), the cell loop runs over a fixed
range, and node ids are allocated monotonically by the shared `Builder`; the
output is then `canonicalize`d (native-checker node ordering). No iteration,
hash, filesystem, or timestamp order reaches the bytes. Twice-and-diff holds.

## 3. The projection `π`

```
π = { pc, sp, s0 … s15, halted }
```

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
