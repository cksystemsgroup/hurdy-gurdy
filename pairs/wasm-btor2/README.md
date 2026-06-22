# Pair — `wasm-btor2`  ·  WebAssembly → BTOR2

*Status: **partial** (i32-stack core: `i32.const`, `local.get`, `i32.add`,
`i32.eqz`, `select`). A vertical slice widened with the **conditional `select`**
(and the `i32.eqz` comparison that feeds it), each carried end-to-end through the
commuting square; every other Wasm opcode hard-aborts with a typed
`Unsupported`. Implementation: [`gurdy/pairs/wasm_btor2/`](../../gurdy/pairs/wasm_btor2/)
+ the shared Wasm interpreter [`gurdy/languages/wasm/`](../../gurdy/languages/wasm/)
(interp v0.2); spec: [`gurdy/pairs/wasm_btor2/SPEC.md`](../../gurdy/pairs/wasm_btor2/SPEC.md);
tests: [`tests/test_wasm_btor2_pair.py`](../../tests/test_wasm_btor2_pair.py).*

Translate an integer-only WebAssembly 1.0 module into a BTOR2 transition
system. Wasm is attractive here because its **standard is itself a formal
operational semantics** ([`languages/wasm`](../../languages/wasm/README.md)),
so the source side is unusually well-defined.

## Delivered slice (this `partial`)

- **Constructs covered end-to-end:** `i32.add` over two i32 operands (consts /
  locals); the **conditional `select`** — `select(v1, v2, c)` lowering to
  `ite(c ≠ 0, v1, v2)` in BTOR2 — and the comparison `i32.eqz`
  (`uext₃₁(eq(x, 0))`) that produces a 0/1 condition for it; with `i32.const` and
  `local.get` as the operand producers. A single straight-line i32 function body,
  lowered one instruction per cycle to a PC-keyed ITE dispatch over a BTOR2
  transition system (mirroring the `ebpf-btor2` / `riscv-btor2` pattern).
  `select` / `i32.eqz` are pure value-stack ops — they reuse the existing
  static-stack-height SSA unchanged (no new control flow). See the
  [spec](../../gurdy/pairs/wasm_btor2/SPEC.md).
- **Fidelity: `checked`** — the commuting-square oracle validates
  `I_s(p) ≡_π L(I_t(T(p)))` under `π` on the corpus + inventory every run.
  Evidence: the corpus in `tests/test_wasm_btor2_pair.py` (including `select`
  cond-true / cond-false and `select` over an `i32.eqz` condition) and the
  per-construct inventory (100% of the in-scope set). Not inflated to `proved`.
- **Construct coverage:** 5/5 of the declared in-scope set
  (`i32.const`, `local.get`, `i32.add`, `i32.eqz`, `select`);
  `inventory.coverage().fraction == 1.0`. (Was 3/3 before this widening — the
  coverage ratchet only grows.)
- **`unsupported` histogram** (the gap made visible — every entry hard-aborts,
  no silent drop; `inventory.unsupported_histogram()`): **41 constructs**, one
  task each, spanning the rest of the i32 opcode space and beyond —
  `i32.sub`, `i32.mul`, `i32.div_s`, `i32.div_u`, `i32.rem_s`, `i32.rem_u`,
  `i32.and`, `i32.or`, `i32.xor`, `i32.shl`, `i32.shr_s`, `i32.shr_u`,
  `i32.rotl`, `i32.rotr`, `i32.eq`, `i32.ne`, `i32.lt_s`, `i32.lt_u`,
  `i32.gt_s`, `i32.gt_u`, `i32.le_s`, `i32.le_u`, `i32.ge_s`, `i32.ge_u`,
  `i64.add`, `f32.add`, `local.set`, `local.tee`, `i32.load`,
  `i32.store`, `drop`, `nop`, `block`, `loop`, `if`, `br`, `br_if`,
  `return`, `call`, `unreachable`, `memory.size`. (Was 43 before this widening —
  `i32.eqz` and `select` moved to covered. Widen construct-by-construct under the
  coverage ratchet, [`BENCHMARKS.md`](../../BENCHMARKS.md) §5.)
- **Reasoning bridge:** the optional `property={"top_eq": V}` emits a BTOR2
  `bad := halted ∧ (s0 == V)`, decided end-to-end through the reused
  `btor2-smtlib` → z3 path, the witness replayed back to the Wasm result.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** WebAssembly — [`languages/wasm`](../../languages/wasm/README.md).
- **Target.** BTOR2 — [`languages/btor2`](../../languages/btor2/README.md).
- **Translator `T`.** A spec-derived lowering of the in-scope Wasm subset to a
  BTOR2 transition system. Deterministic and schema-predictable. *This slice
  covers the i32 value-stack core (`i32.const`, `local.get`, `i32.add`), the
  conditional `select`, and the comparison `i32.eqz` over a straight-line body;
  locals are read-only and linear memory / structured control flow are future
  widening, not yet in scope.*
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
- Anchoring the interpreter to **WasmCert / the reference interpreter** is still
  open (the `checked` evidence here is the self-graded square + the in-scope
  inventory). Wiring the official `.wast` spec-test suite is the next coverage
  step ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4); construct widening (the rest
  of the i32 binops and comparisons — all already in the histogram) goes one
  opcode at a time under the coverage ratchet.
- **Structured control flow** (`block`/`loop`/`br`/`if`) will break the static
  single-successor assumption and is the first place the PC-keyed dispatch needs
  generalizing; **linear memory** wants the BTOR2 `Array` the eBPF lowering
  already demonstrates.
