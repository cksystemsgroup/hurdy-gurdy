# Pair — `wasm-btor2`  ·  WebAssembly → BTOR2

*Status: **partial** (integer value-stack core at **two widths** — the producers
`i32.const`, `i64.const`, `local.get`, the conditional `select`, the unary
comparisons `i32.eqz` / `i64.eqz`, and the full **binary-operator family at each
width** — `{i32,i64}.add`/`sub`/`mul`/`and`/`or`/`xor`, the shifts
`shl`/`shr_u`/`shr_s` (mod 32 / mod 64), and the comparisons
`eq`/`ne`/`lt_{s,u}`/`gt_{s,u}`/`le_{s,u}`/`ge_{s,u}` (pushing an i32 result);
44/44 in-scope). The value stack now carries **both bv32 and bv64 slots**, each
slot's value type tracked statically. Each construct is carried end-to-end
through the commuting square; every other Wasm opcode hard-aborts with a typed
`Unsupported`. Implementation:
[`gurdy/pairs/wasm_btor2/`](../../gurdy/pairs/wasm_btor2/) + the shared Wasm
interpreter [`gurdy/languages/wasm/`](../../gurdy/languages/wasm/) (interp v0.4);
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
  Evidence: the corpus in `tests/test_wasm_btor2_pair.py` (including the i32
  per-op checks, plus the new i64 checks — **a 64-bit value that does not fit in
  32 bits**, i64 wrap mod 2⁶⁴, **mod-64 shift masking**, **signed-vs-unsigned
  i64 compares that differ** on a negative operand, **`i64.eqz` pushing an i32**,
  a **mixed i32+i64 program** and a slot reused across widths exercising the
  per-slot type tracking, an i64 carry-back, and an i64 property bridge) and the
  per-construct inventory (100% of the in-scope set). Not inflated to `proved`.
- **Construct coverage:** 44/44 of the declared in-scope set
  (`i32.const`, `i64.const`, `local.get`, `i32.eqz`, `i64.eqz`, `select`, and the
  two 19-op binary families `add`/`sub`/`mul`/`and`/`or`/`xor`/`shl`/`shr_u`/
  `shr_s`/`eq`/`ne`/`lt_s`/`lt_u`/`gt_s`/`gt_u`/`le_s`/`le_u`/`ge_s`/`ge_u` at i32
  and i64); `inventory.coverage().fraction == 1.0`. (Was 23/23 before this
  widening — the coverage ratchet only grows; +21 i64 ops.)
- **`unsupported` histogram** (the gap made visible — every entry hard-aborts,
  no silent drop; `inventory.unsupported_histogram()`): **31 constructs**, one
  task each, spanning the rest of the opcode space —
  `i32.div_s`/`div_u`/`rem_s`/`rem_u` and `i64.div_s`/`div_u`/`rem_s`/`rem_u`
  (kept out: they need a div-by-zero **trap edge**, a later round),
  `i32.rotl`/`rotr`, `i64.rotl`/`rotr`, the **width conversions**
  `i32.wrap_i64` / `i64.extend_i32_s` / `i64.extend_i32_u`, `f32.add`,
  `local.set`, `local.tee`, `i32.load`, `i32.store`, `drop`, `nop`, `block`,
  `loop`, `if`, `br`, `br_if`, `return`, `call`, `unreachable`, `memory.size`.
  (Was 23 before this widening — `i64.add` moved to covered, and the i64
  div/rem/rotates + the three width conversions were added to the out-of-scope
  probes. Widen construct-by-construct under the coverage ratchet,
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
  `local.get`), the conditional `select`, the unary comparisons `i32.eqz` /
  `i64.eqz`, and the full binary-operator family at each width
  (`add`/`sub`/`mul`/`and`/`or`/`xor`, the shifts `shl`/`shr_u`/`shr_s`, and the
  comparisons `eq`/`ne`/`lt_{s,u}`/`gt_{s,u}`/`le_{s,u}`/`ge_{s,u}`) over a
  straight-line body, with per-slot value-type tracking; `div`/`rem` (trap edge),
  the i32↔i64 width conversions, locals being read-only, linear memory, and
  structured control flow are future widening, not yet in scope.*
- **Source interpreter.** The **shared** Wasm interpreter
  ([`languages/wasm`](../../languages/wasm/README.md)) — reused; contributed
  by this pair if first.
- **Target interpreter.** The **shared** BTOR2 interpreter — reused.
- **Target-to-source interpreter `L`.** Decodes a BTOR2/solver witness into
  a Wasm stack-machine behavior. Pair-owned.

## Projection `π`

`π = (pc, halted, sp, stack, locals)` — the post-step program counter, halt
flag, value-stack depth, the live value stack (slots `s0..s{sp-1}`, now bv32 or
bv64 per slot), and the locals (i32 or i64 by declaration, as the Wasm
interpreter exposes them) mapped onto the BTOR2 state variables. Stack/local
values are compared as integers, so an i32 value and the low 32 bits of a wider
slot agree directly. (Linear-memory observables join `π` when memory enters
scope.)

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
- Anchoring the interpreter to **WasmCert / the reference interpreter** is still
  open (the `checked` evidence here is the self-graded square + the in-scope
  inventory). Wiring the official `.wast` spec-test suite is the next coverage
  step ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4). The remaining ops still in
  the histogram — `{i32,i64}.div_s`/`div_u`/`rem_s`/`rem_u` (the **trap edge**
  round), the rotates `{i32,i64}.rotl`/`rotr`, and the width conversions — go one
  family at a time under the coverage ratchet; `div`/`rem` are the next
  non-mechanical step because they introduce the pair's first trap/halt-on-fault
  edge.
- **Structured control flow** (`block`/`loop`/`br`/`if`) will break the static
  single-successor assumption and is the first place the PC-keyed dispatch needs
  generalizing; **linear memory** wants the BTOR2 `Array` the eBPF lowering
  already demonstrates.
