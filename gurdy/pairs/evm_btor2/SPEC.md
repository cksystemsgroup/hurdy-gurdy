# Translation specification — `evm-btor2` (thin slice)

A self-contained, reviewable spec for the EVM → BTOR2 translator `T` and its
target-to-source interpreter `L` ([`PAIRING.md`](../../../PAIRING.md) §2, §6).
Anyone who has read the source bytecode and this spec can reproduce `T`'s
output byte-for-byte (the predictability test) — though the pair declares
`checked` fidelity, since faithfulness is established by the commuting-square
oracle every run, not by a written derivation alone.

## 0. Scope (thin slice)

In scope: the opcodes **`PUSH1` (0x60)**, **`ADD` (0x01)**, and
**`STOP` (0x00)** over 256-bit words — the minimal vertical slice that carries
a `PUSH1 a, PUSH1 b, ADD, STOP` program end-to-end through the commuting square.
Every other EVM opcode hard-aborts at decode/translate time with
`unsupported: evm:<MNEMONIC>` (BENCHMARKS.md §3) — never silently dropped.
Status `partial`; coverage 3 / 144 spec opcodes.

## 1. The EVM machine model

A bounded-stack abstraction of the EVM execution semantics
([`languages/evm`](../../../languages/evm/README.md)), shared by `T`, the source
interpreter `I_s`, and `L`:

- **`pc`** — a **byte** offset into the bytecode. `PUSH1` carries its 1-byte
  immediate *inline* (the byte at `pc+1`), so it advances `pc` by 2;
  `ADD`/`STOP` advance by 1.
- **Operand stack** — `STACK_SIZE = 16` cells `s0 … s15`, each a 256-bit word,
  plus a depth **`sp`** = the number of live items. `s{i}` holds the item at
  depth `i`; `s0` is the bottom, `s{sp-1}` the top.
- **`halted`** — a 1-bit flag, set by `STOP`, by running off the end of the
  bytecode, or by an exceptional halt (stack underflow/overflow).

**Cell-update rule (the load-bearing convention).** Popped cells are **left
with their stale value** — never cleared. This is what lets `T` and `I_s` agree
cell-by-cell under the projection without modeling a "cleared" sentinel.

### Per-opcode transition (post-step state)

| opcode | guard | effect |
|--------|-------|--------|
| `PUSH1 v` | `sp ≥ 16` | exceptional halt: `halted := 1`, `pc += 2` |
|           | else      | `s{sp} := v`; `sp += 1`; `pc += 2` |
| `ADD`     | `sp < 2`  | exceptional halt: `halted := 1`, `pc += 1` |
|           | else      | `a := s{sp-1}`, `b := s{sp-2}`; `s{sp-2} := (a+b) mod 2²⁵⁶`; `sp -= 1`; `pc += 1` |
| `STOP`    | —         | `halted := 1`, `pc += 1` |

Stack underflow/overflow are EVM *exceptional halts* — a defined, deterministic
edge that sets `halted`, distinct from an *unsupported opcode* (a typed abort).

## 2. The BTOR2 transition system `T(p)`

`T` decodes the fixed bytecode into `(pc, opcode, immediate)` instructions
(aborting on any unsupported opcode), then emits one BTOR2 transition system:

- **State:** `pc` (bv256), `s0 … s15` (bv256), `sp` (bv256), `halted` (bv1).
- **Init:** `pc := entry`, `s{i} := init_stack[i]` (default 0),
  `sp := init_sp` (default 0), `halted := 0`.
- **Next (PC-keyed ITE dispatch).** For each decoded instruction at byte offset
  `off`, with `active = (pc == off) ∧ ¬halted`, the per-opcode effect of §1.4
  is folded into the running `next_*` expressions via `ite(active, …, prev)`.
  The dynamic reads `s{sp-1}` / `s{sp-2}` of `ADD`, and the dynamic write
  targets `s{sp}` / `s{sp-2}`, are realized as **index muxes**: a chain of
  `ite(index == j, s_j, …)` over the 16 cells. This is the single source of
  truth `L` mirrors, so the cross-check compares two realizations of the same
  rule.
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
