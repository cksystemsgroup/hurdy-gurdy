# Pair — `wasm-btor2`  ·  WebAssembly → BTOR2

*Status: **partial** (integer value-stack core at **two widths** — the producers
`i32.const`, `i64.const`, `local.get`, the local store `local.set`, the
conditional `select`, the unary comparisons `i32.eqz` / `i64.eqz`, the full
**binary-operator family at each width** — `{i32,i64}.add`/`sub`/`mul`/`and`/`or`/`xor`,
the shifts `shl`/`shr_u`/`shr_s` (mod 32 / mod 64), and the comparisons
`eq`/`ne`/`lt_{s,u}`/`gt_{s,u}`/`le_{s,u}`/`ge_{s,u}` (pushing an i32 result), the
division / remainder family `{i32,i64}.div_s`/`div_u`/`rem_s`/`rem_u` with the Wasm
**trap** edge, **and the structured conditional** `if <blocktype> <then> [else
<else>] end`; 54/54 in-scope). The value stack carries **both bv32 and bv64
slots**, each slot's value type tracked statically, and locals are mutable. The
`if` is lowered by the value-stack **branch-merge** (both arms evaluated over a
copy of the incoming static stack, then joined per slot/local with `ite(cond≠0,
then, else)` — the value-stack analogue of the `python-smtlib` SSA branch merge),
with the Wasm validation discipline enforced (i32 condition, both arms balance to
the block result, no `else` only for a void block) or a typed `unsupported`; a
nested `if` is allowed, while `block`/`loop`/`br`/`br_if`/`br_table` stay
out of scope. Each construct is carried end-to-end through the commuting square;
every other Wasm opcode hard-aborts with a typed `Unsupported`. Implementation:
[`gurdy/pairs/wasm_btor2/`](../../gurdy/pairs/wasm_btor2/) + the shared Wasm
interpreter [`gurdy/languages/wasm/`](../../gurdy/languages/wasm/) (interp v0.6);
spec: [`gurdy/pairs/wasm_btor2/SPEC.md`](../../gurdy/pairs/wasm_btor2/SPEC.md);
tests: [`tests/test_wasm_btor2_pair.py`](../../tests/test_wasm_btor2_pair.py).*

Translate an integer-only WebAssembly 1.0 module into a BTOR2 transition
system. Wasm is attractive here because its **standard is itself a formal
operational semantics** ([`languages/wasm`](../../languages/wasm/README.md)),
so the source side is unusually well-defined.

## Delivered slice (this `partial`)

- **Constructs covered end-to-end:** the **binary-operator family at two widths**
  — the arithmetic / bitwise ops `{i32,i64}.add`/`sub`/`mul`/`and`/`or`/`xor`
  (each a width-`w` BTOR2 `op2`, modular 2ʷ), the shifts
  `{i32,i64}.shl`/`shr_u`/`shr_s` (the amount masked `& (w−1)`, replicating
  Wasm's mod-`w` shift rule: mod 32 for i32, mod 64 for i64), and the comparisons
  `{i32,i64}.eq`/`ne`/`lt_{s,u}`/`gt_{s,u}`/`le_{s,u}`/`ge_{s,u}` (each `uext₃₁`
  of the matching signed/unsigned BTOR2 predicate, pushing the **i32** result
  `1`/`0` at *both* widths); the **conditional `select`** — `select(v1, v2, c)`
  lowering to `ite(c ≠ 0, v1, v2)` at the operands' width — and the unary
  comparisons `i32.eqz` / `i64.eqz` (`uext(eq(x, 0))` widened to i32); with
  `i32.const`, `i64.const` and `local.get` as the operand producers. A single
  straight-line function body, lowered one instruction per cycle to a PC-keyed
  ITE dispatch over a BTOR2 transition system (mirroring the `ebpf-btor2` /
  `riscv-btor2` pattern). All are pure value-stack ops — they reuse the
  static-stack SSA, now carrying **per-slot value type** (see below). See the
  [spec](../../gurdy/pairs/wasm_btor2/SPEC.md).
- **Division / remainder with the trap edge (this widening).** The eight ops
  `{i32,i64}.div_s`/`div_u`/`rem_s`/`rem_u` lower to the BTOR2
  `sdiv`/`udiv`/`srem`/`urem` op (the single source of truth `BTOR2_DIVREM`
  mirroring `interp.DIVREM_OPS`), gated by a **trap condition**: the slot write is
  `s_{h-2} := ite(trap, 0, op(a, b))`, and on `active ∧ trap` a new sticky
  `trapped` state var (and hence `halted`) is set. The exact trap conditions
  match the Wasm spec — `div_u`/`rem_u`/`div_s`/`rem_s` **trap on a zero
  divisor**; `div_s` **additionally on the signed overflow `INT_MIN / −1`**
  (i32 `0x8000_0000 / 0xFFFF_FFFF`, the i64 analogue); **`rem_s` does *not* trap
  on `INT_MIN % −1`** — it is `0` (BTOR2 `srem` gives this directly). A trap is a
  *defined, observable* Wasm outcome — distinct from a normal off-the-end halt
  **and** from the typed `unsupported` abort. The `trapped` var + trap edge are
  emitted **only when the body contains a div/rem op**, so every div/rem-free
  body's BTOR2 output stays **byte-for-byte identical** to the prior lowering
  (verified by diff). This is the pair's first **halt-on-fault** edge — but it is
  still single-successor (`pc → pc+1`), so it needed no PC-dispatch change.
- **Structured `if`/`else`/`end` + `local.set` (this widening).** A structured
  `if <blocktype> <then> [else <else>] end` is a **body item** (it occupies one
  `pc` slot, like a flat instruction), lowered by the **branch-merge**: pop the
  i32 condition `c`; evaluate **both arms** symbolically over independent copies
  of the incoming value-stack-slot and local node maps (the value-stack analogue
  of SSA threading); then for every result slot and every local either arm wrote,
  join with `ite(c ≠ 0, then_value, else_value)`. This is exactly the
  `python-smtlib` `if`/`else` SSA branch merge, applied to the value stack. The
  **Wasm validation discipline** is enforced statically (`_type_if`): the
  condition must be i32, both arms must leave exactly the block's declared
  `result` height/types on top of the entry height, and a missing `else` (an
  empty false arm) is legal only for a void block — a malformed `if` (mismatched
  arm heights/types, or a missing `else`/`end` that leaves an arm unbalanced)
  hard-aborts `unsupported`, never a silent wrong lowering. A **nested `if`** is
  just a nested `ite` (the merge recurses). `local.set` (which the void-`if` test
  makes observable) makes **locals mutable**: each local's BTOR2 `next` is now the
  PC-keyed merge of its writes (a body with no `local.set`/`if`-local-write keeps
  `next(l_k) = l_k`, byte-for-byte unchanged). Both the interpreter (it runs the
  *real* taken arm) and the translator (the symbolic merge) mirror one source of
  truth (`_flat_value`). **Still out of scope:** `block`/`loop`/`br`/`br_if`/
  `br_table` — the *real* branching/iteration that breaks the single-successor,
  one-cycle-per-item assumption — and div/rem *inside* an arm (its trap edge
  cannot fire mid branch-merge); both hard-abort named.
- **Per-slot value type (the new machinery).** The value stack holds values of
  two widths, so the static-stack model tracks each slot's **value type**
  (i32 = bv32 vs i64 = bv64), not just height. A physical BTOR2 slot `s_j` is
  allocated at the *widest* type it ever holds; an i32 value landing in a wider
  bv64 slot is zero-extended into the low 32 bits, and an operand read out of a
  wider slot is sliced from those low bits — so the carried integer always
  matches the source interpreter, and **a body that uses only i32 keeps every
  slot at bv32 (the i32 BTOR2 output is byte-for-byte identical, verified by
  diff).** `L` needs no type table: the BTOR2 evaluator already masks each slot
  to its width.
- **Fidelity: `checked`** — the commuting-square oracle validates
  `I_s(p) ≡_π L(I_t(T(p)))` under `π` on the corpus + inventory every run.
  Evidence: the corpus in `tests/test_wasm_btor2_pair.py` (the i32 + i64 per-op
  checks — a 64-bit value that does not fit in 32 bits, i64 wrap mod 2⁶⁴, mod-64
  shift masking, signed-vs-unsigned i64 compares that differ on a negative
  operand, `i64.eqz` pushing an i32, a mixed i32+i64 program and a slot reused
  across widths, an i64 carry-back, an i64 property bridge — plus the **div/rem**
  checks at both widths: **normal signed-vs-unsigned div/rem that differ on a
  negative operand**, the **div-by-zero trap** (all four ops), the **`div_s`
  `INT_MIN / −1` overflow trap**, the **`rem_s` `INT_MIN % −1 = 0` no-trap**, a
  **trap that halts the rest of the body**, and a **trapping run carried back
  through `L`**; plus the **structured-`if` checks** — a value-producing `if`
  decided both ways, a void `if` with a `local.set` in each arm, a void `if` with
  no `else` that skips, a nested `if`, an `if` whose result feeds a later op, an
  i64-result `if`, an `if` branch carried back through `L`, and the malformed
  cases — arm height mismatch / arm type mismatch / missing `else` for a result —
  hard-aborting) and the per-construct inventory (100% of the in-scope set). Not
  inflated to `proved`.
- **Construct coverage:** 54/54 of the declared in-scope set
  (`i32.const`, `i64.const`, `local.get`, `local.set`, `i32.eqz`, `i64.eqz`,
  `select`, `if`, the two 19-op binary families `add`/`sub`/`mul`/`and`/`or`/`xor`/
  `shl`/`shr_u`/`shr_s`/`eq`/`ne`/`lt_s`/`lt_u`/`gt_s`/`gt_u`/`le_s`/`le_u`/`ge_s`/
  `ge_u` at i32 and i64, and the two 4-op div/rem families `div_s`/`div_u`/`rem_s`/
  `rem_u` at i32 and i64); `inventory.coverage().fraction == 1.0`. (Was 52/52
  before this widening — the coverage ratchet only grows; +2 constructs,
  `local.set` and the structured `if`.)
- **`unsupported` histogram** (the gap made visible — every entry hard-aborts,
  no silent drop; `inventory.unsupported_histogram()`): **21 constructs**, one
  task each, spanning the rest of the opcode space —
  `i32.rotl`/`rotr`, `i64.rotl`/`rotr`, the **width conversions**
  `i32.wrap_i64` / `i64.extend_i32_s` / `i64.extend_i32_u`, `f32.add`,
  `local.tee`, `i32.load`, `i32.store`, `drop`, `nop`, `block`,
  `loop`, `br`, `br_if`, `return`, `call`, `unreachable`, `memory.size`.
  (Was 23 before this widening — `local.set` and the structured `if` moved to
  covered. A raw flat `if` opcode with no structure still aborts as `if`, but
  `block`/`loop`/`br`/`br_if`/`br_table` are the real control-flow gap. Widen
  construct-by-construct under the coverage ratchet,
  [`BENCHMARKS.md`](../../BENCHMARKS.md) §5.)
- **Reasoning bridge:** the optional `property={"top_eq": V}` emits a BTOR2
  `bad := halted ∧ (s0 == V)`, decided end-to-end through the reused
  `btor2-smtlib` → z3 path, the witness replayed back to the Wasm result.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** WebAssembly — [`languages/wasm`](../../languages/wasm/README.md).
- **Target.** BTOR2 — [`languages/btor2`](../../languages/btor2/README.md).
- **Translator `T`.** A spec-derived lowering of the in-scope Wasm subset to a
  BTOR2 transition system. Deterministic and schema-predictable. *This slice
  covers the integer value-stack core at i32 and i64 (`i32.const`, `i64.const`,
  `local.get`, `local.set`), the conditional `select`, the unary comparisons
  `i32.eqz` / `i64.eqz`, the full binary-operator family at each width
  (`add`/`sub`/`mul`/`and`/`or`/`xor`, the shifts `shl`/`shr_u`/`shr_s`, and the
  comparisons `eq`/`ne`/`lt_{s,u}`/`gt_{s,u}`/`le_{s,u}`/`ge_{s,u}`), the
  division / remainder family (`div_s`/`div_u`/`rem_s`/`rem_u`) with the Wasm
  **trap** edge, and the **structured conditional** `if`/`else`/`end` (the
  branch-merge) — over a single function body, with per-slot value-type tracking
  and mutable locals; the i32↔i64 width conversions, rotates, linear memory, and
  the *real* control flow (`block`/`loop`/`br`/`br_if`/`br_table`) are future
  widening, not yet in scope.*
- **Source interpreter.** The **shared** Wasm interpreter
  ([`languages/wasm`](../../languages/wasm/README.md)) — reused; contributed
  by this pair if first.
- **Target interpreter.** The **shared** BTOR2 interpreter — reused.
- **Target-to-source interpreter `L`.** Decodes a BTOR2/solver witness into
  a Wasm stack-machine behavior. Pair-owned.

## Projection `π`

`π = (pc, halted, trapped, sp, stack, locals)` — the post-step program counter,
halt flag, **trap flag** (a defined Wasm div/rem trap — a halt-on-fault distinct
from a normal off-the-end halt), value-stack depth, the live value stack (slots
`s0..s{sp-1}`, now bv32 or bv64 per slot), and the locals (i32 or i64 by
declaration, as the Wasm interpreter exposes them) mapped onto the BTOR2 state
variables. Stack/local values are compared as integers, so an i32 value and the
low 32 bits of a wider slot agree directly. A trap-free body emits no `trapped`
state var, so `L` defaults it to `False` — matching the source interpreter.
(Linear-memory observables join `π` when memory enters scope.)

## Fidelity target + evidence

- **`checked`** — the commuting-square oracle under `π` on a corpus.
  Because the Wasm spec is operational, the interpreter can mirror it
  rule-for-rule and itself be checked against **WasmCert** / the reference
  interpreter — an unusually strong source-side oracle.
- Certificates lift discharged questions to `proved`.

## Soundness story

Lowering vs. witness replay cross-check under `π`; the source interpreter is
independently anchored to the mechanized Wasm spec
([`PAIRING.md`](../../PAIRING.md) §6, [`languages/wasm`](../../languages/wasm/README.md)).

## Notes for the implementing agent

- Reuse the BTOR2 core; contribute the shared Wasm interpreter mirroring the
  official semantics, validated against WasmCert/KWasm.
- A `wasm → wasmcert/kwasm → …` route is a possible fidelity-raising branch.

## What this slice learned (for the next widening agent)

- The Wasm validator's **static stack type** is the key simplifier: for a
  straight-line body the value-stack height before every instruction is a
  compile-time constant, so each instruction writes a *statically-known* BTOR2
  slot — no runtime stack-pointer indexing, no arrays needed yet. `sp` is still
  carried as state purely so `L` can slice the live stack for `π`.
- The **conditional `select`** was the cheapest control-shaped construct to add
  because it is *not* control flow: it stays single-successor (`pc + 1`) and only
  changes the static stack height (net −2), so it dropped straight into the
  existing static-stack-height SSA as one extra `_effect` arm
  (`ite(neq(c, 0), v1, v2)`) — no PC-dispatch change. `i32.eqz` (`uext₃₁(eq(x,0))`)
  is the comparison that produces a 0/1 condition for it. Both were an *additive*
  shared-interpreter change (Wasm interp `0.1 → 0.2`, AGENTS.md §3); the
  value-stack-core square stayed byte-for-byte green.
- The **i32 binary-operator family** widening (`0.2 → 0.3`) was even more
  mechanical: every op is a pop-two-push-one, net −1, single-successor write to
  `s_{h-2}`, so the whole family collapses to *one* generic `_effect` arm keyed
  off a `(btor2_op, kind)` table (`translate.BTOR2_BINOP`) that mirrors the
  interpreter's `I32_BINOPS` — `i32.add` is now just one row of it, byte-for-byte
  unchanged. Two subtleties were the only real work: **(1)** Wasm masks the i32
  shift amount mod 32 but BTOR2 `sll`/`srl`/`sra` do not, so the shifts lower as
  `sll(a, and(b, 31))` etc.; **(2)** the signed/unsigned comparison split must
  pick the matching BTOR2 predicate (`slt`/`ult`, …) — a negative operand
  (`0xFFFFFFFF`) makes `lt_s` and `lt_u` give *opposite* answers, which the tests
  pin both ways. `div`/`rem` were deliberately **left out** — they trap on a zero
  divisor, which needs a trap edge the straight-line schedule does not yet model.
- The **i64 value type** widening (`0.3 → 0.4`) was the first to put **two
  widths** on the value stack, so the static-stack model now tracks each slot's
  **value type** (i32 = bv32 vs i64 = bv64), not just height
  (`_static_type_stacks`). The lessons:
  - **Slots are sized to their widest tenant.** A physical slot `s_j` is
    allocated at the widest type it ever holds, so a body using only i32 keeps
    every slot at bv32 — and the emitted BTOR2 is then **byte-for-byte identical**
    to the prior i32-only lowering (verified by diff). The cost is one `uext`
    (extend an i32 value into a wider slot) and one `slice` (read an operand back
    out), both **no-ops at equal width**, which is the byte-identical invariant.
  - **`L` needs no type table.** The BTOR2 evaluator already masks each slot to
    its declared width, so a sliced-in i32 reads back as the same integer the
    source interpreter holds — the carry-back is unchanged.
  - **The interpreter binop/compare tables went width-parametric** (`BINOPS`
    keyed `(in_type, out_type, kind, fn)`), generated once per width. The i32
    family is generated at width 32 / shift-mask 31 — the original semantics —
    so every i32 result stays byte-for-byte. The two width subtleties from the
    i32 round recur with `w`: shifts mask the amount **mod 64** for i64, and the
    signed/unsigned compares now sign-extend at width 64. **Comparisons always
    push i32** at *both* widths (Wasm rule), so `i64.eqz` / `i64.lt_*` write a
    bv32 result into the (possibly bv64) slot, zero-extended.
  - The **width conversions** `i32.wrap_i64` / `i64.extend_i32_{s,u}` — the only
    ops that move a value *between* the widths — were deliberately left out;
    they are the natural next widening now that both sorts exist.
- The **div/rem family + trap edge** widening (`0.4 → 0.5`) was the first
  **halt-on-fault** edge. The lessons:
  - **A trap is *defined* Wasm behavior — a third outcome, not an abort.** It is
    modeled as a new sticky `trapped` observable (implying `halted`), kept
    *distinct* from a normal off-the-end halt **and** from the typed `unsupported`
    abort (an out-of-scope construct). The interpreter signals it with an internal
    `_Trap` that `run` catches to emit one final trapped post-step state; the
    BTOR2 side sets `trapped := 1` on `active ∧ trap_cond`.
  - **The trap stays single-successor**, so it needed *no* PC-dispatch change —
    only two extra state vars (`trapped`, and the implied force of `halted`) and a
    trap-gating `ite` on the slot write: `s_{h-2} := ite(trap, 0, op(a, b))`. The
    div/rem family kept the same one-generic-arm shape the binops use, keyed off a
    `BTOR2_DIVREM` table mirroring `interp.DIVREM_OPS`.
  - **Get the two trap conditions exactly right.** All four ops trap on a **zero
    divisor**; `div_s` *additionally* on the signed overflow `INT_MIN / −1`
    (`a == INT_MIN ∧ b == −1`, with `−1 = not(0)` at width `w`); **`rem_s` does
    *not* trap on `INT_MIN % −1`** — the BTOR2 `srem` already yields `0` there, so
    no special-case is needed (a tempting symmetric trap would be *wrong*). The
    non-trapping div/rem value is exactly the BTOR2 `sdiv`/`udiv`/`srem`/`urem`
    (round-toward-zero), which the pure-Python interpreter mirrors via
    `abs(x)//abs(y)` with the sign applied (Python `//` rounds toward −∞, so the
    naïve `//` would be wrong for negative operands — the tests pin signed vs
    unsigned giving *opposite* answers on `−7`).
  - **Byte-identity is preserved by conditional emission.** The `trapped` state
    var + trap edge are emitted **only when the body contains a div/rem op**
    (`has_trap`), so every div/rem-free body's BTOR2 output is **byte-for-byte
    identical** to the prior lowering (verified by diff against `HEAD`). `L`
    defaults `trapped` to `False` when the var is absent.
- The **structured `if`/`else`/`end`** widening (`0.5 → 0.6`) was the first
  *structured* construct, but it is **not** real control flow — it lowers to a
  pure value-stack **branch-merge**, exactly the `python-smtlib` SSA `if`/`else`
  merge applied to the stack. The lessons:
  - **Make the `if` a single body item, not a flow change.** The body is now a
    list of *items* — a flat `Instr` or a structured `If` — and `pc` indexes the
    items, so a whole `if` block occupies **one** `pc` slot / one cycle and the
    single-successor PC-keyed dispatch is **unchanged**. The interpreter runs the
    real taken arm to completion as one step; the translator merges both arms
    symbolically into one step. Each top-level item still yields exactly one
    post-step trace row, so the square alignment is untouched.
  - **The branch-merge is SSA threading over the value stack.** Each arm is
    evaluated over an independent *copy* of the incoming slot-node / local-node
    maps (the value-stack analogue of an SSA map), threading each instruction's
    result into the map so the next reads it; then the result slots and any
    written local are joined `ite(c ≠ 0, then, else)`. The Wasm height discipline
    guarantees only the result slots and touched locals can differ — exactly the
    join set — so the merge is small and deterministic (ascending slot / local
    order). Both `T` and `I_s` share one per-instruction source of truth
    (`_flat_value` / `interp._execute`).
  - **Enforce the validation rule or abort — never a silent wrong merge.**
    `_type_if` checks the i32 condition and that *both* arms balance to the
    block's declared `result` height **and** types (a missing `else` is the empty
    false arm, legal only for a void block); a mismatch hard-aborts `unsupported:
    wasm-btor2:if`. This is the height/type discipline a missing `end` would also
    violate.
  - **`local.set` makes locals mutable — additively.** Each local's BTOR2 `next`
    becomes the PC-keyed merge of its writes; a body with no `local.set`/
    `if`-local-write keeps `next(l_k) = l_k`, so its output is **byte-for-byte
    identical** to the prior lowering (verified by diff against `main` across the
    full existing corpus). The interp bump `0.5 → 0.6` was strictly additive — a
    body with no `if`/`local.set` runs exactly as before.
  - **div/rem inside an arm is deferred** — its trap (halt-on-fault) edge cannot
    fire half-way through a branch-merge that lowers both arms unconditionally, so
    it hard-aborts inside an arm; both `T` and `I_s` reject the same arm scope.
- Anchoring the interpreter to **WasmCert / the reference interpreter** is still
  open (the `checked` evidence here is the self-graded square + the in-scope
  inventory). Wiring the official `.wast` spec-test suite is the next coverage
  step ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4). The remaining ops still in
  the histogram — the rotates `{i32,i64}.rotl`/`rotr` and the width conversions
  `i32.wrap_i64` / `i64.extend_i32_{s,u}` — go one family at a time under the
  coverage ratchet; both are mechanical now that the trap edge exists.
- **Real control flow** (`block`/`loop`/`br`/`br_if`/`br_table` — branching out
  of a block and *iteration*) is the next big step: unlike the structured `if`
  branch-merge, it breaks the single-successor / one-cycle-per-item assumption and
  is where the PC-keyed dispatch must generalize (a loop needs a real back-edge or
  a BMC unroll, as `python-smtlib`'s `while` does). **Linear memory** wants the
  BTOR2 `Array` the eBPF lowering already demonstrates.
