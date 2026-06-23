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

**Also in scope — the division / remainder family with the trap edge.** The
eight ops `i32.div_s` / `div_u` / `rem_s` / `rem_u` (opcodes `0x6d`–`0x70`) and
the i64 analogues `i64.div_s` / `div_u` / `rem_s` / `rem_u` (`0x7f`–`0x82`) each
pop two operands of their width and push one of the same width, **but can trap**.
A Wasm **trap** is a *defined, observable* outcome (not undefined behavior, and
not the typed `unsupported` abort): it halts the body with a `trapped`
observable set. The exact trap conditions (`b` is the divisor, the top operand;
`a` the dividend, pushed first, at the operand width `w`):

- **`div_u` / `rem_u` / `div_s` / `rem_s` trap when the divisor `b == 0`;**
- **`div_s` additionally traps on the signed overflow `INT_MIN / -1`** — for i32
  `a == 0x8000_0000 ∧ b == 0xFFFF_FFFF`, the i64 analogue at `w = 64`;
- **`rem_s` does *not* trap on `INT_MIN % -1`** — it yields `0` (the BTOR2 `srem`
  already gives this directly).

Everywhere else the result is the usual two's-complement value (truncating,
round-toward-zero division). The **width conversions** `i32.wrap_i64`,
`i64.extend_i32_{s,u}` (the only ops that move a value between the two widths),
the rotates, f32/f64, memory and structured control flow stay out of scope.
**Every other Wasm opcode hard-aborts** with `Unsupported("wasm-btor2",
<opcode>)` at translate time — never a silent drop
([`BENCHMARKS.md`](../../../BENCHMARKS.md) §3). The out-of-scope histogram is
attached by `inventory.unsupported_histogram()`.

Every in-scope op is a value-stack operation — it changes the statically-known
stack height (a binop / div-rem net −1, `select` net −2, `eqz` net 0) and the
statically-known stack *type*. The arith / bitwise / compare / shift family never
touches the single-successor `pc + 1` control flow, so they fit the static-stack
SSA with no new control machinery. The **div/rem family adds the pair's first
*halt-on-fault* edge**: a trap is still a single-successor instruction (`pc → pc +
1`), but it also raises a sticky `trapped` / `halted` state, so it needs *no*
PC-dispatch change — only the two extra state vars and the trap-gating `ite`s.
(Structured control flow — `block`/`loop`/`if`/`br` — remains future widening; it
is what first breaks the single-successor assumption.)

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
{ pc, halted, trapped, sp, stack=(v0,…,v_{sp-1}), locals=(l0,…,l_{N-1}) }
```

`pc` indexes the body; `halted` is true once `pc` runs off the end **or a div/rem
trap fires**; `trapped` is true once a defined Wasm trap fired (a div/rem fault) —
a trap implies `halted`, but an off-the-end halt is `halted` without `trapped`;
`sp` is the value-stack depth; `stack` lists the live slots bottom-to-top. Stack
and local values are plain (width-masked) integers — an i32 value and the low 32
bits of the BTOR2 slot that holds it are the same integer, so `π` compares them
directly.

## 2. The BTOR2 transition system `T(p)` emits

`pc` / `sp` are bv32, `halted` is bv1. A **local** `l_k` is bv32 for an i32 local
and bv64 for an i64 local (its declared type). A **value-stack slot** `s_j` is
allocated at the **widest value type it ever holds** over the body
(`slot_width[j] ∈ {32, 64}`): a slot used only for i32 stays bv32 — so a body
that uses only i32 is **byte-for-byte identical** to the previous i32-only
lowering — while a slot that ever holds an i64 becomes bv64. The `trapped` state
var is emitted **only when the body contains a div/rem op** (`has_trap`), so a
trap-free body stays byte-for-byte identical to the prior lowering — the same
conditional-emission discipline the slot widths follow. For a body of length `M`,
`N` locals, and static max stack depth `D = max_stack`:

| State var | width | init | meaning |
|-----------|-------|------|---------|
| `pc`      | 32 | `entry` (0) | instruction index |
| `halted`  | 1  | 0 | off-the-end **or trapped** flag |
| `trapped` *(only if `has_trap`)* | 1 | 0 | a defined Wasm div/rem trap fired (sticky) |
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
| div/rem (width `w`) | `s_{h-2} := ite(trap_i, 0, g(a, b))`; **and** `trapped := 1` when `active_i ∧ trap_i` | `i+1` | `h-1` |

`sp` is set to the active instruction's post-height. `halted` is set to 1 once
`next_pc == M` (off the end) **or `next_trapped == 1`** (a trap halts the body).
`trapped` is sticky once set (no instruction is active while halted), so the
trapped state persists across the remaining cycles. Slots above `sp` keep stale
values and are *not* part of the projection.

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

### The division / remainder family and the trap edge

The eight div/rem ops are the single source of truth `translate.BTOR2_DIVREM`,
mirroring `interp.DIVREM_OPS`. Each pops two operands of width `w` (`a = s_{h-2}`
the dividend, `b = s_{h-1}` the divisor) and writes `s_{h-2}` — but it is gated by
a **trap condition** `trap_i` (a bv1 node):

| Wasm op | non-trapping value `g(a, b)` | `trap_i` |
|---------|------------------------------|----------|
| `div_u` | `udiv(a, b)` | `eq(b, 0)` |
| `rem_u` | `urem(a, b)` | `eq(b, 0)` |
| `div_s` | `sdiv(a, b)` | `eq(b, 0) ∨ (eq(a, INT_MIN) ∧ eq(b, −1))` |
| `rem_s` | `srem(a, b)` | `eq(b, 0)` |

where `INT_MIN = 1 << (w−1)` and `−1` is the all-ones constant `not(0)` at width
`w`. The BTOR2 `udiv`/`urem`/`sdiv`/`srem` already give the correct
two's-complement (truncating) value, **including `srem` of `INT_MIN % −1 = 0`** —
which is exactly why `rem_s` does *not* trap on `INT_MIN % −1`. The slot write is

```
s_{h-2} := uext( ite(trap_i, 0, g(a, b)) )       # 0 is the trap sentinel
```

and, when `active_i ∧ trap_i`, `trapped := 1` (which forces `halted := 1`). On a
trap the result slot holds the sentinel `0` and `sp := h−1`, so the trapped
post-state agrees byte-for-byte between `T` and the interpreter (which freezes the
same `0` and signals its internal trap). The trap is a **halt-on-fault edge** — a
defined Wasm outcome, distinct from the off-the-end halt and from the typed
`unsupported` abort.

### Optional property (`bad` signal)

If `program["property"] = {"top_eq": V}`, `T` emits
`bad := halted ∧ (s0 == V)`: "the body's single result value equals `V` once
halted." `V` and the equality are taken at slot 0's allocated width
(`slot_width[0]`, bv64 if slot 0 ever holds an i64). A downstream `btor2-smtlib`
decide answers reachability of that `bad`.

## 3. The projection `π`

```
π = (pc, halted, trapped, sp, stack, locals)
```

`stack` is compared as the tuple of **live** slot integers `(s0,…,s_{sp-1})`.
`trapped` is the div/rem trap observable (a defined Wasm fault). This is what the
pair promises to preserve and exactly what the commuting-square oracle checks. A
divergence is localized to a (step, observable).

## 4. The target-to-source interpreter `L`

`L` reads a BTOR2 behavior (rows keyed `pc, halted, trapped, sp, s0.., l0..`) and
re-expresses each row in the source observable shape of §1: `stack` is the
slice `(s0,…,s_{sp-1})`, `locals` is `(l0,…,l_{N-1})`. The slot values arrive as
plain integers already masked to each slot's width by the BTOR2 evaluator, so
`L` needs **no per-slot type table** — an i32 value sliced into a bv64 slot reads
back as the same integer the source interpreter holds. `trapped` is read straight
from the BTOR2 `trapped` state var; a trap-free body emits no such var, so `L`
defaults `trapped` to `False` — matching the source interpreter, which emits
`False` on every non-trapping state. Because the slice is driven by the carried
`sp`, `L` is self-contained — it needs no static schedule of its own. The same
decoder consumes a BTOR2 solver / `btor2-smtlib` witness.

## 5. Faithfulness and fidelity

- **Soundness story** ([`PAIRING.md`](../../../PAIRING.md) §6): the per-construct
  lowering above is the single source of truth that both `T` and `L` mirror; the
  commuting-square oracle runs `I_s(p)` against `L(I_t(T(p)))` under `π` on a
  corpus (now including i64 programs that overflow 32 bits, signed-vs-unsigned
  i64 compares, mod-64 shift masking, `i64.eqz` pushing an i32, a mixed i32+i64
  program exercising per-slot type tracking, and the **div/rem family** — normal
  signed-vs-unsigned division/remainder that differ on a negative operand, the
  div-by-zero trap, the `div_s` `INT_MIN / −1` overflow trap, the `rem_s`
  `INT_MIN % −1 = 0` no-trap, and a trapping run replayed through `L` — at both
  widths) and asserts agreement, localizing any divergence.
- **Fidelity: `checked`** — the square is validated against the shared Wasm
  interpreter every run on the pair's corpus and inventory. The Wasm interpreter
  mirrors the official operational semantics for these rules and can be
  anchored to WasmCert / the reference interpreter (future work). This is
  `checked` ("validated on the inputs we tried"), **not** `proved`.
- **Shared-interpreter version** ([`AGENTS.md`](../../../AGENTS.md) §3): adding
  the **division / remainder family** (`{i32,i64}.div_s`/`div_u`/`rem_s`/`rem_u`)
  with the Wasm **trap** semantics — a new `trapped` observable, a zero-divisor
  or `div_s` `INT_MIN / −1` overflow trap (a *defined* halt, distinct from the
  typed `unsupported` abort) — was an *additive* change to the shared Wasm
  interpreter, bumping its `INTERP_VERSION` `0.4 → 0.5`. No existing rule's value
  changed and the `trapped` field defaults `False` on every prior state, so the
  `0.1`…`0.4` square stayed byte-for-byte green. On the BTOR2 side the `trapped`
  state var and trap edge are emitted **only when the body contains a div/rem op**
  (`has_trap`), so every div/rem-free body's BTOR2 output is byte-for-byte
  identical to the prior lowering (verified by diff). The pair's
  `translator_version` bumped `0.1 → 0.2` (the lowering changed, invalidating
  caches). The earlier interp bumps added the i64 value type (`0.3 → 0.4`), the
  i32 binop family (`0.2 → 0.3`), and `select` + `i32.eqz` (`0.1 → 0.2`).
  `wasm-btor2` is currently the only pair over `languages/wasm`, so it is the only
  square re-validated.

## 6. Determinism

`T`, the Wasm interpreter, and `L` are pure functions of their inputs. `T`'s
output is byte-identical on repeat (`Builder` allocates node ids monotonically
and `model.canonicalize` fixes node order); no hash/iteration/filesystem/time
leaks. A twice-and-diff test ships for both `T` and the interpreter, at both
widths and including a div/rem program (a trapping `div_s` and a `rem_u`).
