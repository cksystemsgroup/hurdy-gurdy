# Pair — `wasm-btor2`  ·  WebAssembly → BTOR2

*Status: **partial** (i32-stack core: `i32.const`, `local.get`, `i32.eqz`,
`select`, and the full **i32 binary-operator family** — `i32.add`/`sub`/`mul`/
`and`/`or`/`xor`, the shifts `shl`/`shr_u`/`shr_s`, and the comparisons
`eq`/`ne`/`lt_{s,u}`/`gt_{s,u}`/`le_{s,u}`/`ge_{s,u}`; 23/23 in-scope). Each is
carried end-to-end through the commuting square; every other Wasm opcode
hard-aborts with a typed `Unsupported`. Implementation:
[`gurdy/pairs/wasm_btor2/`](../../gurdy/pairs/wasm_btor2/) + the shared Wasm
interpreter [`gurdy/languages/wasm/`](../../gurdy/languages/wasm/) (interp v0.3);
spec: [`gurdy/pairs/wasm_btor2/SPEC.md`](../../gurdy/pairs/wasm_btor2/SPEC.md);
tests: [`tests/test_wasm_btor2_pair.py`](../../tests/test_wasm_btor2_pair.py).*

Translate an integer-only WebAssembly 1.0 module into a BTOR2 transition
system. Wasm is attractive here because its **standard is itself a formal
operational semantics** ([`languages/wasm`](../../languages/wasm/README.md)),
so the source side is unusually well-defined.

## Delivered slice (this `partial`)

- **Constructs covered end-to-end:** the **i32 binary-operator family** — the
  arithmetic / bitwise ops `i32.add`/`sub`/`mul`/`and`/`or`/`xor` (each a
  width-32 BTOR2 `op2`, modular 2³²), the shifts `i32.shl`/`shr_u`/`shr_s`
  (lowered with the amount masked `& 31`, replicating Wasm's mod-32 shift rule),
  and the comparisons `i32.eq`/`ne`/`lt_{s,u}`/`gt_{s,u}`/`le_{s,u}`/`ge_{s,u}`
  (each `uext₃₁` of the matching signed/unsigned BTOR2 predicate, pushing the
  i32 result `1`/`0`); the **conditional `select`** — `select(v1, v2, c)`
  lowering to `ite(c ≠ 0, v1, v2)` — and the unary comparison `i32.eqz`
  (`uext₃₁(eq(x, 0))`); with `i32.const` and `local.get` as the operand
  producers. A single straight-line i32 function body, lowered one instruction
  per cycle to a PC-keyed ITE dispatch over a BTOR2 transition system (mirroring
  the `ebpf-btor2` / `riscv-btor2` pattern). All are pure value-stack ops — they
  reuse the existing static-stack-height SSA unchanged (no new control flow). See
  the [spec](../../gurdy/pairs/wasm_btor2/SPEC.md).
- **Fidelity: `checked`** — the commuting-square oracle validates
  `I_s(p) ≡_π L(I_t(T(p)))` under `π` on the corpus + inventory every run.
  Evidence: the corpus in `tests/test_wasm_btor2_pair.py` (including per-op
  arithmetic/bitwise/shift checks, **shift-amount mod-32 masking**, and
  **signed-vs-unsigned comparisons that give different results** on a negative
  operand, plus a mixed-op program and carry-back) and the per-construct
  inventory (100% of the in-scope set). Not inflated to `proved`.
- **Construct coverage:** 23/23 of the declared in-scope set
  (`i32.const`, `local.get`, `i32.eqz`, `select`, and the 19-op binary family
  `add`/`sub`/`mul`/`and`/`or`/`xor`/`shl`/`shr_u`/`shr_s`/`eq`/`ne`/`lt_s`/
  `lt_u`/`gt_s`/`gt_u`/`le_s`/`le_u`/`ge_s`/`ge_u`);
  `inventory.coverage().fraction == 1.0`. (Was 5/5 before this widening — the
  coverage ratchet only grows.)
- **`unsupported` histogram** (the gap made visible — every entry hard-aborts,
  no silent drop; `inventory.unsupported_histogram()`): **23 constructs**, one
  task each, spanning the rest of the i32 opcode space and beyond —
  `i32.div_s`, `i32.div_u`, `i32.rem_s`, `i32.rem_u` (kept out: they need a
  div-by-zero **trap edge**, a later round), `i32.rotl`, `i32.rotr`,
  `i64.add`, `f32.add`, `local.set`, `local.tee`, `i32.load`, `i32.store`,
  `drop`, `nop`, `block`, `loop`, `if`, `br`, `br_if`, `return`, `call`,
  `unreachable`, `memory.size`. (Was 41 before this widening — the 18
  arithmetic/bitwise/shift/comparison ops moved to covered. Widen
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
  covers the i32 value-stack core (`i32.const`, `local.get`), the conditional
  `select` and the unary comparison `i32.eqz`, and the full i32 binary-operator
  family (`add`/`sub`/`mul`/`and`/`or`/`xor`, the shifts `shl`/`shr_u`/`shr_s`,
  and the comparisons `eq`/`ne`/`lt_{s,u}`/`gt_{s,u}`/`le_{s,u}`/`ge_{s,u}`) over
  a straight-line body; `div`/`rem` (trap edge), locals being read-only, linear
  memory, and structured control flow are future widening, not yet in scope.*
- **Source interpreter.** The **shared** Wasm interpreter
  ([`languages/wasm`](../../languages/wasm/README.md)) — reused; contributed
  by this pair if first.
- **Target interpreter.** The **shared** BTOR2 interpreter — reused.
- **Target-to-source interpreter `L`.** Decodes a BTOR2/solver witness into
  a Wasm stack-machine behavior. Pair-owned.

## Projection `π`

`π = (pc, halted, sp, stack, locals)` — the post-step program counter, halt
flag, value-stack depth, the live value stack (slots `s0..s{sp-1}`), and the
i32 locals (as the Wasm interpreter exposes them) mapped onto the BTOR2 state
variables. (Linear-memory observables join `π` when memory enters scope.)

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
- Anchoring the interpreter to **WasmCert / the reference interpreter** is still
  open (the `checked` evidence here is the self-graded square + the in-scope
  inventory). Wiring the official `.wast` spec-test suite is the next coverage
  step ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4). The remaining i32 ops still in
  the histogram — `div_s`/`div_u`/`rem_s`/`rem_u` (the **trap edge** round) and
  the rotates `rotl`/`rotr` — go one opcode at a time under the coverage ratchet;
  `div`/`rem` are the next non-mechanical step because they introduce the pair's
  first trap/halt-on-fault edge.
- **Structured control flow** (`block`/`loop`/`br`/`if`) will break the static
  single-successor assumption and is the first place the PC-keyed dispatch needs
  generalizing; **linear memory** wants the BTOR2 `Array` the eBPF lowering
  already demonstrates.
