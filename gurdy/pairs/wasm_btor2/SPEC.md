# Translation specification — `wasm-btor2` (thin slice)

This is the self-contained, byte-predictable lowering the translator `T`
implements and the target-to-source interpreter `L` mirrors. It governs the
implementation: where code and spec disagree, the code is wrong
([`PAIRING.md`](../../../PAIRING.md) §2).

## 0. Scope (one construct, end-to-end)

In scope — the i32 **value-stack core** of a single straight-line Wasm
function body:

| Wasm instruction | binary opcode | reduction rule (informal) |
|------------------|---------------|---------------------------|
| `i32.const c`    | `0x41`        | push `c` (mod 2³²) |
| `local.get x`    | `0x20`        | push the value of local `x` |
| `i32.add`        | `0x6a`        | pop `b`, pop `a`, push `(a + b) mod 2³²` |

`i32.add` is the headline construct; `i32.const` / `local.get` are the operand
producers it adds. **Every other Wasm opcode hard-aborts** with
`Unsupported("wasm-btor2", <opcode>)` at translate time — never a silent drop
([`BENCHMARKS.md`](../../../BENCHMARKS.md) §3). The out-of-scope histogram is
attached by `inventory.unsupported_histogram()`.

Restrictions that make the body well-typed and statically schedulable:

- one function, no calls, no parameters beyond locals;
- straight-line body — no control flow, so every instruction's successor is
  `pc + 1` and the **value-stack height before each instruction is a static
  constant** (the Wasm validator's stack type). The translator computes these
  heights once (`_static_heights`) and rejects any body that would underflow.

## 1. The machine and its observables

Source observable state (post-step, [`ARCHITECTURE.md`](../../../ARCHITECTURE.md)
§5), as the shared Wasm interpreter (`languages/wasm`) emits it:

```
{ pc, halted, sp, stack=(v0,…,v_{sp-1}), locals=(l0,…,l_{N-1}) }
```

`pc` indexes the body; `halted` is true once `pc` runs off the end; `sp` is the
value-stack depth; `stack` lists the live i32 slots bottom-to-top.

## 2. The BTOR2 transition system `T(p)` emits

All bit-vectors are width 32 except `halted` (width 1). For a body of length
`M`, `N` locals, and static max stack depth `D = max_stack`:

| State var | width | init | meaning |
|-----------|-------|------|---------|
| `pc`      | 32 | `entry` (0) | instruction index |
| `halted`  | 1  | 0 | off-the-end flag |
| `sp`      | 32 | 0 | value-stack depth (carried for `π` / `L`) |
| `l0..l{N-1}` | 32 | `init_locals[k]` or 0 | locals (read-only in this slice) |
| `s0..s{D-1}` | 32 | 0 | value-stack slots (cleared at init) |

One instruction is dispatched per cycle by a **PC-keyed ITE chain**. For each
instruction `i` with static pre-height `h = heights[i]`, let
`active_i = (pc == i) ∧ ¬halted`. Its next-state effect is:

| instruction | writes (only when `active_i`) | next `pc` | post-height |
|-------------|-------------------------------|-----------|-------------|
| `i32.const c` | `s_h := c` | `i+1` | `h+1` |
| `local.get x` | `s_h := l_x` | `i+1` | `h+1` |
| `i32.add`     | `s_{h-2} := add(s_{h-2}, s_{h-1})` | `i+1` | `h-1` |

`sp` is set to the active instruction's post-height. `halted` is set to 1 once
`next_pc == M` (off the end). Slots above `sp` keep stale values and are *not*
part of the projection. `add` is BTOR2 `add` at width 32 — modular 2³²,
matching the Wasm `iadd_32` rule exactly, so the lowering and the interpreter
share one source of truth per construct.

### Optional property (`bad` signal)

If `program["property"] = {"top_eq": V}`, `T` emits
`bad := halted ∧ (s0 == V)`: "the body's single result value equals `V` once
halted." A downstream `btor2-smtlib` decide answers reachability of that `bad`.

## 3. The projection `π`

```
π = (pc, halted, sp, stack, locals)
```

`stack` is compared as the tuple of **live** slots `(s0,…,s_{sp-1})`. This is
what the pair promises to preserve and exactly what the commuting-square oracle
checks. A divergence is localized to a (step, observable).

## 4. The target-to-source interpreter `L`

`L` reads a BTOR2 behavior (rows keyed `pc, halted, sp, s0.., l0..`) and
re-expresses each row in the source observable shape of §1: `stack` is the
slice `(s0,…,s_{sp-1})`, `locals` is `(l0,…,l_{N-1})`. Because the slice is
driven by the carried `sp`, `L` is self-contained — it needs no static schedule
of its own. The same decoder consumes a BTOR2 solver / `btor2-smtlib` witness.

## 5. Faithfulness and fidelity

- **Soundness story** ([`PAIRING.md`](../../../PAIRING.md) §6): the per-construct
  lowering above is the single source of truth that both `T` and `L` mirror; the
  commuting-square oracle runs `I_s(p)` against `L(I_t(T(p)))` under `π` on a
  corpus and asserts agreement, localizing any divergence.
- **Fidelity: `checked`** — the square is validated against the shared Wasm
  interpreter every run on the pair's corpus and inventory. The Wasm interpreter
  mirrors the official operational semantics for these three rules and can be
  anchored to WasmCert / the reference interpreter (future work). This is
  `checked` ("validated on the inputs we tried"), **not** `proved`.

## 6. Determinism

`T`, the Wasm interpreter, and `L` are pure functions of their inputs. `T`'s
output is byte-identical on repeat (`Builder` allocates node ids monotonically
and `model.canonicalize` fixes node order); no hash/iteration/filesystem/time
leaks. A twice-and-diff test ships for both `T` and the interpreter.
