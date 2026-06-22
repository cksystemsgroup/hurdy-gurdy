# Translation specification — `wasm-btor2` (partial slice)

This is the self-contained, byte-predictable lowering the translator `T`
implements and the target-to-source interpreter `L` mirrors. It governs the
implementation: where code and spec disagree, the code is wrong
([`PAIRING.md`](../../../PAIRING.md) §2).

## 0. Scope (the i32 value-stack core, end-to-end)

In scope — the i32 **value-stack core** of a single straight-line Wasm
function body. The operand producers, the conditional `select` / the unary
comparison `i32.eqz`, and the full **i32 binary-operator family** (each pops two
i32 and pushes one):

| Wasm instruction | binary opcode | reduction rule (informal) |
|------------------|---------------|---------------------------|
| `i32.const c`    | `0x41`        | push `c` (mod 2³²) |
| `local.get x`    | `0x20`        | push the value of local `x` |
| `i32.eqz`        | `0x45`        | pop `x`, push `1` if `x == 0` else `0` |
| `select`         | `0x1b`        | pop `c`, `v2`, `v1`; push `v1` if `c ≠ 0` else `v2` |
| `i32.add`        | `0x6a`        | pop `b`, pop `a`, push `(a + b) mod 2³²` |
| `i32.sub`        | `0x6b`        | push `(a − b) mod 2³²` |
| `i32.mul`        | `0x6c`        | push `(a · b) mod 2³²` |
| `i32.and`        | `0x71`        | push `a & b` |
| `i32.or`         | `0x72`        | push `a | b` |
| `i32.xor`        | `0x73`        | push `a ^ b` |
| `i32.shl`        | `0x74`        | push `a << (b mod 32)` (mod 2³²) |
| `i32.shr_s`      | `0x75`        | push `a >>ₐ (b mod 32)` (arithmetic, sign-extending) |
| `i32.shr_u`      | `0x76`        | push `a >>ₗ (b mod 32)` (logical, zero-filling) |
| `i32.eq`         | `0x46`        | push `1` if `a == b` else `0` |
| `i32.ne`         | `0x47`        | push `1` if `a ≠ b` else `0` |
| `i32.lt_s`/`lt_u`| `0x48`/`0x49` | push `1` if `a < b` (signed / unsigned) else `0` |
| `i32.gt_s`/`gt_u`| `0x4a`/`0x4b` | push `1` if `a > b` (signed / unsigned) else `0` |
| `i32.le_s`/`le_u`| `0x4c`/`0x4d` | push `1` if `a ≤ b` (signed / unsigned) else `0` |
| `i32.ge_s`/`ge_u`| `0x4e`/`0x4f` | push `1` if `a ≥ b` (signed / unsigned) else `0` |

Throughout, `a` is the second-from-top operand (pushed first) and `b` the top
operand (pushed last). `i32.const` / `local.get` are the operand producers;
`select` is the **conditional** construct (`i32.eqz` is the comparison that
produces a 0/1 condition for it). The **shifts mask the amount mod 32** exactly
as the Wasm spec does, and the **signed** comparisons (`_s`) / `shr_s` treat the
operands as two's-complement, the **unsigned** (`_u`) / `shr_u` as plain u32.

`i32.div_s` / `i32.div_u` / `i32.rem_s` / `i32.rem_u` stay **out of scope** this
slice — they trap on a zero divisor (and `INT_MIN / -1` overflow), which needs a
trap edge the straight-line single-successor schedule does not yet model — and so
keep hard-aborting. **Every other Wasm opcode hard-aborts** with
`Unsupported("wasm-btor2", <opcode>)` at translate time — never a silent drop
([`BENCHMARKS.md`](../../../BENCHMARKS.md) §3). The out-of-scope histogram is
attached by `inventory.unsupported_histogram()`.

Every in-scope op is a pure value-stack operation — it changes the
statically-known stack height (a binop net −1, `select` net −2, `i32.eqz` net 0)
but never the single-successor `pc + 1` control flow, so they all fit the same
static-stack-height SSA the slice already uses with no new machinery.
(Structured control flow — `block`/`loop`/`if`/`br` — remains future widening; it
is what first breaks the single-successor assumption.)

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
| `i32.eqz`     | `s_{h-1} := uext₃₁(eq(s_{h-1}, 0))` | `i+1` | `h` |
| `select`      | `s_{h-3} := ite(neq(s_{h-1}, 0), s_{h-3}, s_{h-2})` | `i+1` | `h-2` |
| i32 binop     | `s_{h-2} := f(a, b)` where `a = s_{h-2}`, `b = s_{h-1}` | `i+1` | `h-1` |

`sp` is set to the active instruction's post-height. `halted` is set to 1 once
`next_pc == M` (off the end). Slots above `sp` keep stale values and are *not*
part of the projection.

`i32.eqz` widens `eq(x,0)` back to the i32 result `1`/`0` with `uext` (extend by
31 bits); `select` lowers to the BTOR2 `ite` over the bv1 condition `neq(c, 0)` —
picking `s_{h-3}` (=`v1`) when `c ≠ 0` else `s_{h-2}` (=`v2`), exactly the Wasm
`select` rule.

The **i32 binary-operator family** all share the same `s_{h-2} := f(s_{h-2},
s_{h-1})` slot write (a binop pops two, pushes one — net −1). The per-construct
BTOR2 op `f` is the single source of truth (`translate.BTOR2_BINOP`,
mirroring `interp.I32_BINOPS`):

| Wasm op | BTOR2 lowering `f(a, b)` (width 32 unless noted) |
|---------|--------------------------------------------------|
| `i32.add` | `add(a, b)` — modular 2³², matching the Wasm `iadd_32` rule |
| `i32.sub` | `sub(a, b)` |
| `i32.mul` | `mul(a, b)` |
| `i32.and` | `and(a, b)` |
| `i32.or`  | `or(a, b)` |
| `i32.xor` | `xor(a, b)` |
| `i32.shl` | `sll(a, and(b, 31))` — amount masked mod 32 |
| `i32.shr_u` | `srl(a, and(b, 31))` — logical, amount masked mod 32 |
| `i32.shr_s` | `sra(a, and(b, 31))` — arithmetic, amount masked mod 32 |
| `i32.eq`  | `uext₃₁(eq(a, b))` |
| `i32.ne`  | `uext₃₁(neq(a, b))` |
| `i32.lt_s` / `lt_u` | `uext₃₁(slt(a, b))` / `uext₃₁(ult(a, b))` |
| `i32.gt_s` / `gt_u` | `uext₃₁(sgt(a, b))` / `uext₃₁(ugt(a, b))` |
| `i32.le_s` / `le_u` | `uext₃₁(slte(a, b))` / `uext₃₁(ulte(a, b))` |
| `i32.ge_s` / `ge_u` | `uext₃₁(sgte(a, b))` / `uext₃₁(ugte(a, b))` |

The arithmetic / bitwise ops are width-32 `op2` whose bv32 result is the pushed
value (modular 2³²). The **shifts** mask the amount with `and(b, 31)` before the
BTOR2 `sll`/`srl`/`sra` because BTOR2's shift ops do *not* take the amount mod
the width whereas Wasm does. The **comparisons** are bv1 BTOR2 predicates widened
to the i32 result `1`/`0` with `uext` (extend by 31 bits); the **signed**
variants use the signed BTOR2 predicate (`slt`/`sgt`/`slte`/`sgte`,
two's-complement), the **unsigned** variants the unsigned one
(`ult`/`ugt`/`ulte`/`ugte`). Each lowering is the one source of truth the
interpreter mirrors per construct.

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
  mirrors the official operational semantics for these rules and can be
  anchored to WasmCert / the reference interpreter (future work). This is
  `checked` ("validated on the inputs we tried"), **not** `proved`.
- **Shared-interpreter version** ([`AGENTS.md`](../../../AGENTS.md) §3): adding
  the rest of the i32 binary-operator family (`sub`/`mul`/`and`/`or`/`xor`, the
  shifts `shl`/`shr_u`/`shr_s`, and the comparisons `eq`/`ne`/`lt_*`/`gt_*`/
  `le_*`/`ge_*`) was an *additive* change to the shared Wasm interpreter, bumping
  its `INTERP_VERSION` `0.2 → 0.3` (each is a new pop-two-push-one rule; no
  existing rule's value changed; the prior `0.1`/`0.2` square stayed
  byte-for-byte green). The earlier `0.1 → 0.2` bump added `select` + `i32.eqz`.
  `wasm-btor2` is currently the only pair over `languages/wasm`, so it is the
  only square re-validated.

## 6. Determinism

`T`, the Wasm interpreter, and `L` are pure functions of their inputs. `T`'s
output is byte-identical on repeat (`Builder` allocates node ids monotonically
and `model.canonicalize` fixes node order); no hash/iteration/filesystem/time
leaks. A twice-and-diff test ships for both `T` and the interpreter.
