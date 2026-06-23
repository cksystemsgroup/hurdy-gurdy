# Translation specification — `wasm-btor2` (partial slice)

This is the self-contained, byte-predictable lowering the translator `T`
implements and the target-to-source interpreter `L` mirrors. It governs the
implementation: where code and spec disagree, the code is wrong
([`PAIRING.md`](../../../PAIRING.md) §2).

## 0. Scope (the integer value-stack core at two widths, end-to-end)

In scope — the integer **value-stack core** at **two value types**, **i32**
(bv32) and **i64** (bv64), of a single straight-line Wasm function body. The
operand producers, the conditional `select`, the unary comparisons `i32.eqz` /
`i64.eqz`, and the full **binary-operator family at each width** (each pops two
operands of its width and pushes one):

| Wasm instruction | binary opcode | reduction rule (informal) |
|------------------|---------------|---------------------------|
| `i32.const c`    | `0x41`        | push `c` (mod 2³²) |
| `i64.const c`    | `0x42`        | push `c` (mod 2⁶⁴) |
| `local.get x`    | `0x20`        | push the value of local `x` (its declared width) |
| `i32.eqz`        | `0x45`        | pop i32 `x`, push i32 `1` if `x == 0` else `0` |
| `i64.eqz`        | `0x50`        | pop i64 `x`, push **i32** `1` if `x == 0` else `0` |
| `select`         | `0x1b`        | pop i32 `c`, `v2`, `v1` (same type); push `v1` if `c ≠ 0` else `v2` |

For each width `W ∈ {i32, i64}` with operand bit-width `w ∈ {32, 64}` and shift
mask `w−1 ∈ {31, 63}`, the binary-operator family (`a` = second-from-top operand,
pushed first; `b` = top operand):

| Wasm op (`W.<op>`) | result | reduction rule |
|--------------------|--------|----------------|
| `add` / `sub` / `mul` | `W`  | `(a ∘ b) mod 2ʷ` |
| `and` / `or` / `xor`  | `W`  | bitwise at width `w` |
| `shl`            | `W`    | `a << (b mod w)` (mod 2ʷ) |
| `shr_s`          | `W`    | `a >>ₐ (b mod w)` (arithmetic, sign-extending) |
| `shr_u`          | `W`    | `a >>ₗ (b mod w)` (logical, zero-filling) |
| `eq` / `ne`      | **i32**| `1` if `a == b` / `a ≠ b` else `0` |
| `lt_s`/`lt_u`    | **i32**| `1` if `a < b` (signed / unsigned at width `w`) else `0` |
| `gt_s`/`gt_u`    | **i32**| `1` if `a > b` (signed / unsigned) else `0` |
| `le_s`/`le_u`    | **i32**| `1` if `a ≤ b` (signed / unsigned) else `0` |
| `ge_s`/`ge_u`    | **i32**| `1` if `a ≥ b` (signed / unsigned) else `0` |

The i32 family keeps opcodes `0x6a`–`0x76` (arith/shift) and `0x46`–`0x4f`
(compares); the i64 family is `0x7c`–`0x88` (arith/shift) and `0x51`–`0x5a`
(compares). The **shifts mask the amount mod the width** (mod 32 for i32, mod 64
for i64) exactly as the Wasm spec does; the **signed** comparisons (`_s`) /
`shr_s` treat the operands as two's-complement at the operand width, the
**unsigned** (`_u`) / `shr_u` as plain unsigned. **Every comparison yields an
i32** `0`/`1` at *both* widths — Wasm comparisons always produce i32.

`i32.div_*` / `i32.rem_*` / `i64.div_*` / `i64.rem_*` stay **out of scope** this
slice — they trap on a zero divisor (and `INT_MIN / -1` overflow), which needs a
trap edge the straight-line single-successor schedule does not yet model — and
so keep hard-aborting. The **width conversions** `i32.wrap_i64`,
`i64.extend_i32_{s,u}` (the only ops that move a value between the two widths)
also stay out of scope this slice. **Every other Wasm opcode hard-aborts** with
`Unsupported("wasm-btor2", <opcode>)` at translate time — never a silent drop
([`BENCHMARKS.md`](../../../BENCHMARKS.md) §3). The out-of-scope histogram is
attached by `inventory.unsupported_histogram()`.

Every in-scope op is a pure value-stack operation — it changes the
statically-known stack height (a binop net −1, `select` net −2, `eqz` net 0) and
the statically-known stack *type*, but never the single-successor `pc + 1`
control flow, so they all fit the same static-stack SSA the slice already uses
with no new control machinery. (Structured control flow — `block`/`loop`/`if`/`br`
— remains future widening; it is what first breaks the single-successor
assumption.)

Restrictions that make the body well-typed and statically schedulable:

- one function, no calls, no parameters beyond locals;
- straight-line body — no control flow, so every instruction's successor is
  `pc + 1` and the **value-stack height *and per-slot type* before each
  instruction is a static constant** (the Wasm validator's stack type). The
  translator computes these once (`_static_type_stacks`) and rejects any body
  that would underflow or whose operand types disagree with the opcode.

## 1. The machine and its observables

Source observable state (post-step, [`ARCHITECTURE.md`](../../../ARCHITECTURE.md)
§5), as the shared Wasm interpreter (`languages/wasm`) emits it:

```
{ pc, halted, sp, stack=(v0,…,v_{sp-1}), locals=(l0,…,l_{N-1}) }
```

`pc` indexes the body; `halted` is true once `pc` runs off the end; `sp` is the
value-stack depth; `stack` lists the live slots bottom-to-top. Stack and local
values are plain (width-masked) integers — an i32 value and the low 32 bits of
the BTOR2 slot that holds it are the same integer, so `π` compares them directly.

## 2. The BTOR2 transition system `T(p)` emits

`pc` / `sp` are bv32, `halted` is bv1. A **local** `l_k` is bv32 for an i32 local
and bv64 for an i64 local (its declared type). A **value-stack slot** `s_j` is
allocated at the **widest value type it ever holds** over the body
(`slot_width[j] ∈ {32, 64}`): a slot used only for i32 stays bv32 — so a body
that uses only i32 is **byte-for-byte identical** to the previous i32-only
lowering — while a slot that ever holds an i64 becomes bv64. For a body of length
`M`, `N` locals, and static max stack depth `D = max_stack`:

| State var | width | init | meaning |
|-----------|-------|------|---------|
| `pc`      | 32 | `entry` (0) | instruction index |
| `halted`  | 1  | 0 | off-the-end flag |
| `sp`      | 32 | 0 | value-stack depth (carried for `π` / `L`) |
| `l0..l{N-1}` | 32 or 64 | `init_locals[k]` or 0 | locals (read-only in this slice) |
| `s0..s{D-1}` | `slot_width[j]` | 0 | value-stack slots (cleared at init) |

**Per-slot value type.** The value type of every slot before each instruction is
the Wasm validator's static stack type, computed once by `_static_type_stacks`.
A value is always written into a slot at least as wide as the value: an i32 value
landing in a (wider) bv64 slot is **zero-extended** into the low 32 bits (`uext`),
so its carried integer matches the source interpreter's u32 value bit-for-bit.
When an instruction *reads* an operand of width `w` out of a slot allocated
wider, the low `w` bits are **sliced** out (the value sits exactly there). When
slot and operand widths coincide (every i32-only slot), both the extend and the
slice are no-ops — hence the byte-for-byte i32 invariance.

One instruction is dispatched per cycle by a **PC-keyed ITE chain**. For each
instruction `i` with static pre-stack of height `h = len(stacks[i])`, let
`active_i = (pc == i) ∧ ¬halted`. Its next-state effect (each written value
zero-extended to the destination slot's `slot_width`):

| instruction | writes (only when `active_i`) | next `pc` | post-height |
|-------------|-------------------------------|-----------|-------------|
| `i32.const c` | `s_h := c` (bv32) | `i+1` | `h+1` |
| `i64.const c` | `s_h := c` (bv64) | `i+1` | `h+1` |
| `local.get x` | `s_h := l_x` | `i+1` | `h+1` |
| `i32.eqz` / `i64.eqz` | `s_{h-1} := uext(eq(x, 0))` to i32 | `i+1` | `h` |
| `select`      | `s_{h-3} := ite(neq(c, 0), s_{h-3}, s_{h-2})` (operand width) | `i+1` | `h-2` |
| binop (width `w`) | `s_{h-2} := f(a, b)` where `a = s_{h-2}`, `b = s_{h-1}` | `i+1` | `h-1` |

`sp` is set to the active instruction's post-height. `halted` is set to 1 once
`next_pc == M` (off the end). Slots above `sp` keep stale values and are *not*
part of the projection.

`eqz` widens `eq(x,0)` (a bv1 at the operand width `w`) back to the i32 result
`1`/`0` with `uext`; `select` lowers to the BTOR2 `ite` over the bv1 condition
`neq(c, 0)` at the operands' shared width — picking `s_{h-3}` (=`v1`) when `c ≠ 0`
else `s_{h-2}` (=`v2`), exactly the Wasm `select` rule.

The **binary-operator family** all share the same `s_{h-2} := f(s_{h-2},
s_{h-1})` slot write (a binop pops two, pushes one — net −1). The per-construct
BTOR2 op `f` is the single source of truth (`translate.BTOR2_BINOP`, mirroring
`interp.BINOPS`), applied at the **operand width** `w`:

| Wasm op | BTOR2 lowering `f(a, b)` (operand width `w`) |
|---------|----------------------------------------------|
| `add` / `sub` / `mul` / `and` / `or` / `xor` | `op(a, b)` — width `w`, modular 2ʷ |
| `shl` | `sll(a, and(b, w−1))` — amount masked mod `w` |
| `shr_u` | `srl(a, and(b, w−1))` — logical, amount masked mod `w` |
| `shr_s` | `sra(a, and(b, w−1))` — arithmetic, amount masked mod `w` |
| `eq` / `ne` | `uext₃₁(eq(a, b))` / `uext₃₁(neq(a, b))` → i32 |
| `lt_s` / `lt_u` | `uext₃₁(slt(a, b))` / `uext₃₁(ult(a, b))` → i32 |
| `gt_s` / `gt_u` | `uext₃₁(sgt(a, b))` / `uext₃₁(ugt(a, b))` → i32 |
| `le_s` / `le_u` | `uext₃₁(slte(a, b))` / `uext₃₁(ulte(a, b))` → i32 |
| `ge_s` / `ge_u` | `uext₃₁(sgte(a, b))` / `uext₃₁(ugte(a, b))` → i32 |

The arithmetic / bitwise ops are width-`w` `op2` whose bv result is the pushed
value (modular 2ʷ). The **shifts** mask the amount with `and(b, w−1)` before the
BTOR2 `sll`/`srl`/`sra` because BTOR2's shift ops do *not* take the amount mod
the width whereas Wasm does (mod 32 for i32, mod 64 for i64). The **comparisons**
are bv1 BTOR2 predicates widened to the **i32** result `1`/`0` with `uext` (at
*both* operand widths — Wasm comparisons always yield i32); the **signed**
variants use the signed BTOR2 predicate (`slt`/`sgt`/`slte`/`sgte`,
two's-complement at the operand width), the **unsigned** variants the unsigned
one (`ult`/`ugt`/`ulte`/`ugte`). Each lowering is the one source of truth the
interpreter mirrors per construct; the i32 rows are the original lowering
unchanged.

### Optional property (`bad` signal)

If `program["property"] = {"top_eq": V}`, `T` emits
`bad := halted ∧ (s0 == V)`: "the body's single result value equals `V` once
halted." `V` and the equality are taken at slot 0's allocated width
(`slot_width[0]`, bv64 if slot 0 ever holds an i64). A downstream `btor2-smtlib`
decide answers reachability of that `bad`.

## 3. The projection `π`

```
π = (pc, halted, sp, stack, locals)
```

`stack` is compared as the tuple of **live** slot integers `(s0,…,s_{sp-1})`.
This is what the pair promises to preserve and exactly what the commuting-square
oracle checks. A divergence is localized to a (step, observable).

## 4. The target-to-source interpreter `L`

`L` reads a BTOR2 behavior (rows keyed `pc, halted, sp, s0.., l0..`) and
re-expresses each row in the source observable shape of §1: `stack` is the
slice `(s0,…,s_{sp-1})`, `locals` is `(l0,…,l_{N-1})`. The slot values arrive as
plain integers already masked to each slot's width by the BTOR2 evaluator, so
`L` needs **no per-slot type table** — an i32 value sliced into a bv64 slot reads
back as the same integer the source interpreter holds. Because the slice is
driven by the carried `sp`, `L` is self-contained — it needs no static schedule
of its own. The same decoder consumes a BTOR2 solver / `btor2-smtlib` witness.

## 5. Faithfulness and fidelity

- **Soundness story** ([`PAIRING.md`](../../../PAIRING.md) §6): the per-construct
  lowering above is the single source of truth that both `T` and `L` mirror; the
  commuting-square oracle runs `I_s(p)` against `L(I_t(T(p)))` under `π` on a
  corpus (now including i64 programs that overflow 32 bits, signed-vs-unsigned
  i64 compares, mod-64 shift masking, `i64.eqz` pushing an i32, and a mixed
  i32+i64 program exercising per-slot type tracking) and asserts agreement,
  localizing any divergence.
- **Fidelity: `checked`** — the square is validated against the shared Wasm
  interpreter every run on the pair's corpus and inventory. The Wasm interpreter
  mirrors the official operational semantics for these rules and can be
  anchored to WasmCert / the reference interpreter (future work). This is
  `checked` ("validated on the inputs we tried"), **not** `proved`.
- **Shared-interpreter version** ([`AGENTS.md`](../../../AGENTS.md) §3): adding
  the **i64 value type** and its operator family (`i64.const`, `local.get` of an
  i64 local, `i64.add`/`sub`/`mul`/`and`/`or`/`xor`, the shifts `shl`/`shr_u`/
  `shr_s` masked mod 64, `i64.eqz`, and the comparisons `eq`/`ne`/`lt_*`/`gt_*`/
  `le_*`/`ge_*` pushing an i32) was an *additive* change to the shared Wasm
  interpreter, bumping its `INTERP_VERSION` `0.3 → 0.4`. The binop / compare
  logic was generalized to be width-parametric, but every i32 result is
  byte-for-byte identical (the i32 family is generated at width 32 / shift-mask
  31, the original semantics), so the prior `0.1`/`0.2`/`0.3` square stayed
  byte-for-byte green — and the i32-only BTOR2 output is byte-identical (verified
  by diff). The earlier bumps added the i32 binop family (`0.2 → 0.3`) and
  `select` + `i32.eqz` (`0.1 → 0.2`). `wasm-btor2` is currently the only pair
  over `languages/wasm`, so it is the only square re-validated.

## 6. Determinism

`T`, the Wasm interpreter, and `L` are pure functions of their inputs. `T`'s
output is byte-identical on repeat (`Builder` allocates node ids monotonically
and `model.canonicalize` fixes node order); no hash/iteration/filesystem/time
leaks. A twice-and-diff test ships for both `T` and the interpreter, at both
widths.
