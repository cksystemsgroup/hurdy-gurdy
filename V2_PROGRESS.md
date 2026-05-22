# `wasm-btor2` Progress — Live State

> The single source of truth for "where is the `wasm-btor2` bootstrap
> right now." Each iteration appends one entry at the top. Older
> entries stay for history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-05-22T00:00:00Z — P13: br_if / br branch instructions + corpus seed 0006-loop-count

- **Phase**: P13 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/source/decoder.py` — extended
    `_resolve_targets` with a second pass (pass 2) that walks the
    instruction list with a fresh label stack and pre-resolves
    `br_target` on every `br` and `br_if` instruction. For `br N` /
    `br_if N`, the pass looks N levels up in the label stack and reads
    the `br_target` already set on the enclosing `block`/`loop`/`if`
    instruction by pass 1 (loop → back-edge = the loop instruction
    itself; block/if → instruction after the matching `end`). Pass 1
    is unchanged. The decoder now sets `ins.br_target` for `br` and
    `br_if` at decode time so the translator can read it without a
    runtime label stack.
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    four per-instruction lowerings: `block` (advance PC, no-op
    structural marker), `loop` (advance PC, no-op structural marker),
    `br` (unconditional jump to `ins.br_target`, no stack effect for
    void blocks), `br_if` (pop condition bv32, emit
    `neq(condition, 0)` to get bv1 flag, ITE selecting `ins.br_target`
    if nonzero or `p+1` if zero as next PC, decrement SP by 1).
    Updated module docstring to describe P13 scope.
  - Created `bench/wasm-btor2/corpus/seed/0006-loop-count/module.wasm`
    — 63-byte WASM module: one i32 param (n), one i32 local (counter),
    body `i32.const 0; local.set 1; block; loop; local.get 1;
    local.get 0; i32.ge_u; br_if 1; local.get 1; i32.const 1;
    i32.add; local.set 1; br 0; end; end; end`, exported as `main`.
  - Created `bench/wasm-btor2/corpus/seed/0006-loop-count/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8. task_class `loop-semantics`. SHA-256 of module.wasm:
    `ac10089d6d2876101cef493ad4c53c0f2fc81c06a3b205b916c2b611aacc7a5b`.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 13 new
    tests: `br_if` compile, `br` compile, `loop_count` compile,
    `br_if` BTOR2 parseable, loop-count BTOR2 parseable, `neq` in
    library layer for `br_if`, `ite` in dispatch layer for `br_if`,
    reasoning interpreter tests for br_if nonzero exits (no trap),
    br_if zero falls through (no trap), br unconditional exit (no
    trap), loop-count n=0 (no trap), loop-count n=1 (no trap),
    loop-count n=3 (no trap).
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0006.py` — 21
    tests: file-shape checks, spec round-trip, translation compiles,
    `ite` and `neq` present in flattened BTOR2, and reasoning
    interpreter confirms no-trap for n=0, n=1, n=2, n=3.
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0006.py -v` → 122 passed;
  `pytest tests/pairs/wasm_btor2/` → 351 passed, 16 pre-existing z3
  failures (unchanged from P12).
- **Next iteration's planned work**: P14 — add `call` instruction
  support for direct function calls, enabling multi-function modules.
  The simplest step: translate `call N` where callee is in the same
  module and has no return value; the translator emits a push of the
  return address and a jump to the callee's PC range. Alternatively,
  consider `i32.clz`, `i32.ctz`, `i32.popcnt` (pure no-trap unary
  ops) if call is too large for one iteration. Land corpus seed
  `0007` demonstrating the new capability.
- **Open BLOCKERs**: none.

---

## 2026-05-20T10:00:00Z — P12: if/else/end structured control flow + corpus seed 0005-if-no-trap

- **Phase**: P12 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    per-instruction lowerings for `if` and `else`. `if` (type `[] → []`,
    no result value): pops one i32 condition, emits `neq(condition, 0)` to
    produce a bv1 flag, then emits an ITE selecting `p+1` (true branch) or
    `ins.alt` (false target from the decoder's second pass) as the next PC,
    and decrements SP by 1 to consume the condition. `else`: unconditionally
    sets next PC to `ins.br_target` (instruction after the matching `end`),
    skipping the false branch when the true branch completes. Block-level
    `end` already advanced PC by one and required no change. Updated module
    docstring to describe P12 scope.
  - Created `bench/wasm-btor2/corpus/seed/0005-if-no-trap/module.wasm` —
    41-byte WASM module: one i32 param, body `local.get 0; if (void); nop;
    end; end`, exported as `main`.
  - Created `bench/wasm-btor2/corpus/seed/0005-if-no-trap/spec.json` and
    `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8.
    task_class `if-semantics`. SHA-256 of module.wasm:
    `0857bdde309623e0a78c230e3f5b71fd43be580d2f3a5257adaf33fd0423c627`.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 9 new tests:
    `if` and `if-else` compile tests, ITE-in-dispatch and neq-in-library
    presence tests, BTOR2 parseable, and reasoning interpreter tests for
    condition=0 (skip), condition=1 (enter), condition=-1 (nonzero enter)
    on `if`, plus true-branch and false-branch tests on `if-else`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0005.py` — 21 tests:
    file-shape checks, spec round-trip, translation compiles, `ite` and
    `neq` present in flattened BTOR2, and reasoning interpreter confirms
    no-trap for condition=0, condition=1, condition=-1, condition=INT32_MAX.
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0005.py -v` → 109 passed;
  `pytest tests/pairs/wasm_btor2/` → 318 passed, 16 pre-existing z3
  failures (unchanged from P11).
- **Next iteration's planned work**: P13 — add `br_if` and `br` branch
  instructions. `br_if` pops a condition and, if nonzero, jumps to
  `ins.br_target` (the exit of the enclosing block); `br` is an
  unconditional jump to `ins.br_target`. Together these enable loop-exit
  patterns (`loop + br_if` = while) and early-exit from blocks. Land
  corpus seed `0006-loop-count` demonstrating a counted loop that never
  traps.
- **Open BLOCKERs**: none.

---

## 2026-05-20T08:00:00Z — P11: i32.eqz + 10 binary comparison instructions + corpus seed 0004-comparison-ops

- **Phase**: P11 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    per-instruction lowerings for `i32.eqz` (unary: pop 1, compare with
    zero, zero-extend bv1 result to bv32, push) and ten binary comparisons
    `i32.eq`, `i32.ne`, `i32.lt_s`, `i32.lt_u`, `i32.gt_s`, `i32.gt_u`,
    `i32.le_s`, `i32.le_u`, `i32.ge_s`, `i32.ge_u` (pop 2, compare, uext
    bv1 → bv32, push). All 11 instructions produce bv32 results (0 or 1)
    per WASM spec — not bv1. None have trap semantics. Lowerings delegate
    to the existing `_comparison_nid` helper (reusing `Comparison` enum
    and BTOR2 op mapping already present for `LocalInit` constraints) then
    emit `uext(cmp, 31)` to widen to bv32. Updated module docstring to
    describe P11 scope.
  - Created `bench/wasm-btor2/corpus/seed/0004-comparison-ops/module.wasm`
    — 42-byte WASM module: two i32 params, body `local.get 0; local.get 1;
    i32.lt_s; end`, exported as `main`.
  - Created `bench/wasm-btor2/corpus/seed/0004-comparison-ops/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8.
    task_class `comparison-semantics`. SHA-256 of module.wasm:
    `f13ede3bedffe0c44eac493e93fe751411d91bb30125100b26ba59651539ab87`.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 24 new tests:
    11 compile tests (one per new instruction), 6 BTOR2 operator presence
    tests (slt, ult, eq, neq, and two uext presence checks), 7 reasoning
    interpreter concrete-witness tests (lt_s basic, lt_s equal, lt_s
    negative, eq same values, eqz zero, eqz nonzero, ge_u basic).
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0004.py` — 21 tests:
    file-shape checks, spec round-trip, translation compiles, `slt` and
    `uext` present in flattened BTOR2, and reasoning interpreter confirms
    no-trap for (0,0), (1,2), (-1,0), (INT32_MAX,-1), (INT32_MIN,INT32_MAX).
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0004.py -v` → 100 passed;
  `pytest tests/pairs/wasm_btor2/` → 288 passed, 16 pre-existing z3
  failures (unchanged from P10).
- **Next iteration's planned work**: P12 — add `if`/`else`/`end` structured
  control flow. The comparison instructions landing in P11 produce the
  boolean operands needed for `if`; the block stack must track nesting
  depth so `end` closes the correct scope. Start with `if`-without-else
  (type `[] → []`, no result value) and one seed task `0005-if-no-trap`
  demonstrating that a branch on a comparison never traps. `br_if` and
  `br` can follow in P13 once `if` is solid.
- **Open BLOCKERs**: none.

---

## 2026-05-20T06:00:00Z — P10: i32.and/or/xor + i32.shl/shr_s/shr_u + i32.rotl/rotr + corpus seed 0003-shift-amount-mask

- **Phase**: P10 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/builder.py` — added `sll`,
    `srl`, `sra` helper methods (symmetric with the existing arithmetic
    helpers).
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    per-instruction lowerings for `i32.and`, `i32.or`, `i32.xor` (pure
    bitwise, no trap), and `i32.shl`, `i32.shr_s`, `i32.shr_u` (shifts
    with explicit mod-32 mask: `count = and(rhs, 0x1F)` before each BTOR2
    shift node so the model-checker sees WASM semantics rather than SMT
    shift-by-large-amount = 0). Added `i32.rotl` and `i32.rotr` expressed
    as `or(sll(a, count), srl(a, 32 - count))` and
    `or(srl(a, count), sll(a, 32 - count))` respectively; the n=0 edge
    case is correct for both the evaluator (which masks shift amounts mod
    width) and z3 (which gives 0 for shift >= width): both paths yield `a`.
    Updated module docstring to describe P10 scope and the rotation
    derivation.
  - Created `bench/wasm-btor2/corpus/seed/0003-shift-amount-mask/module.wasm`
    — 42-byte WASM module: two i32 params, body `local.get 0; local.get 1;
    i32.shl; end`, exported as `main`.
  - Created `bench/wasm-btor2/corpus/seed/0003-shift-amount-mask/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8. task_class `shift-semantics`. SHA-256 of module.wasm:
    `bc95fd959e3982e469ec2f856ebd8727e39094a8fcf566aee0151f0aa8d64d45`.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 25 new tests:
    compile tests for all 8 new instructions, BTOR2 operator presence tests
    (`and`, `or`, `xor`, `sll`, `sra`, `srl`), mask-explicit-in-BTOR2 test
    for `i32.shl`, rotl sll+srl presence, and reasoning-interpreter concrete
    witness tests (shl basic, shl mod-32 mask, shr_u basic, rotr basic,
    and basic).
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0003.py` — 20 tests:
    file-shape checks, spec round-trip, translation compiles, `sll` present
    in flattened BTOR2, and reasoning interpreter confirms no-trap for
    (0,0), (1,1), (5,32) mod-32 mask, (0xFFFFFFFF,31), (1,33).
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0003.py -v` → 75 passed;
  `pytest tests/pairs/wasm_btor2/` → 243 passed, 16 pre-existing z3
  failures (unchanged from P9).
- **Next iteration's planned work**: P11 — add `i32.eqz`, `i32.eq`,
  `i32.ne`, `i32.lt_s`, `i32.lt_u`, `i32.gt_s`, `i32.gt_u`, `i32.le_s`,
  `i32.le_u`, `i32.ge_s`, `i32.ge_u` comparison instructions (pure
  arithmetic, no trap semantics). These produce bv32 results (0 or 1 per
  WASM spec — not bv1) and are needed for `if`/`br_if` control flow.
  Land corpus seed `0004-comparison-ops` demonstrating that comparisons
  are zero-or-one and never trap.
- **Open BLOCKERs**: none.

---

## 2026-05-20T04:00:00Z — P9: i32.div_s/div_u/rem_s/rem_u + corpus seed 0002-div-trap

- **Phase**: P9 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    per-instruction lowerings for `i32.div_s`, `i32.div_u`, `i32.rem_s`,
    `i32.rem_u`. Each uses ITE-based conditional trap paths: the lowering
    emits `trap_cond` (bv1) as the OR of all trap conditions for that
    instruction, then wraps `next_pc`, `next_sp`, `next_stack`, and
    `trap` in ITE trees keyed on `trap_cond`. `i32.div_s` checks both
    divisor-zero (`rhs == 0`) and signed overflow (`lhs == INT32_MIN &&
    rhs == -1`). The remaining three check divisor-zero only.
  - Fixed `gurdy/pairs/wasm_btor2/btor2/evaluator.py` — `write` was
    masking element values with `& 0xFF` (bv8 width) instead of
    storing the full bv32 value; removed the incorrect mask. This was
    a pre-existing bug exposed by the first corpus task requiring
    large stack values (INT32_MIN = 0x80000000).
  - Created `bench/wasm-btor2/corpus/seed/0002-div-trap/module.wasm` —
    42-byte WASM module: two i32 params, body `local.get 0; local.get
    1; i32.div_s; end`, exported as `main`.
  - Created `bench/wasm-btor2/corpus/seed/0002-div-trap/spec.json` and
    `task.toml` — `reach_trap`, expected verdict `reachable`, bound 8.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 25 new
    tests: four compile tests (one per instruction), BTOR2 operator
    presence tests, ITE presence in library layer, and reasoning
    interpreter concrete-witness tests (zero divisor, INT32_MIN/-1
    overflow, non-zero divisor no-trap, for all four instructions).
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0002.py` — 19
    tests: file-shape checks, spec round-trip, translation compiles,
    `sdiv` present in flattened BTOR2, and reasoning interpreter
    confirms trap for divisor==0, INT32_MIN/-1 overflow, and non-trap
    for valid divisors.
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0002.py -v` → 53 passed;
  `pytest tests/pairs/wasm_btor2/` → 202 passed, 16 pre-existing z3
  failures (unchanged from P8).
- **Next iteration's planned work**: P10 — extend the translator with
  `i32.and`, `i32.or`, `i32.xor`, `i32.shl`, `i32.shr_s`, `i32.shr_u`,
  `i32.rotl`, `i32.rotr` and land seed task `0003-shift-amount-mask`
  (a function demonstrating that WASM masks shift counts mod 32,
  distinct from undefined behavior at source level). Alternatively, add
  `i32.eqz`, `i32.eq`, `i32.ne`, `i32.lt_s`, `i32.lt_u`, `i32.gt_s`,
  `i32.gt_u`, `i32.le_s`, `i32.le_u`, `i32.ge_s`, `i32.ge_u`
  comparison instructions (needed for `if` expressions and `br_if`
  control flow, not yet in scope but these are pure arithmetic
  without trap semantics so they are cheap to add).
- **Open BLOCKERs**: none.

---

## 2026-05-20T02:00:00Z — P8: witness lifter skeleton

- **Phase**: P8 complete.
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/lift/witness.py` — `WasmWitness`
    dataclass: `params` (dict[int, int] — param index → unsigned i32),
    `trap_step` (int | None — first BMC cycle where trap fires),
    `n_params` (int — count of params detected). `as_signed(k)` converts
    `params[k]` to a signed i32 in [-2^31, 2^31).
  - Created `gurdy/pairs/wasm_btor2/lift/parse_z3_model.py` —
    `parse_z3_model(witness_text)` parses `str(z3_model)` into
    `{var_name: int}`. Handles decimal, `#x` hex, `#b` binary, and `0x`
    hex value formats. Variable names may contain `!` (z3 step suffix).
  - Created `gurdy/pairs/wasm_btor2/lift/lifter.py` — `lift_witness(
    btor2_flattened, witness_text)`. Builds nid→symbol map from BTOR2
    state/input lines (format: `nid op sort_nid symbol`). Extracts param
    values from `in0_n{param_k_init_nid}` (primary) with fallback to
    `s0_n{local_k_nid}` (init equality). Finds `trap_step` by scanning
    `s{c}_n{trap_nid}` for the smallest cycle where value ≠ 0. Accepts
    `btor2_flattened` as bytes or str.
  - Updated `gurdy/pairs/wasm_btor2/lift/__init__.py` — exports
    `WasmWitness`, `lift_witness`, `parse_z3_model`.
  - Created `tests/pairs/wasm_btor2/test_lift.py` — 25 tests:
    WasmWitness construction/defaults/as_signed (6), parse_z3_model
    decimal/#x/#b/0x/multiline/empty/bang-suffix (7), lift_witness
    param-from-in0/fallback-s0/trap-step/trap-at-zero/no-trap/no-params/
    empty-witness/wrapping/hex-values/bytes-input/n_params-count (11),
    integration test against compiled 0001-i32-add-wrap with synthetic
    witness string confirming nid mapping end-to-end (1).
- **Note on environment**: z3 is not installed in this container;
  16 tests in `test_solvers.py` that `import z3` directly fail with
  `ModuleNotFoundError`. These were pre-existing before P8 (P7 ran in
  an environment where z3 was available). The 25 new lift tests are
  z3-free and all pass.
- **Verification**: `pytest tests/pairs/wasm_btor2/test_lift.py -v` →
  25 passed; `pytest tests/pairs/wasm_btor2/` → 167 passed, 16 pre-
  existing z3 failures; full suite → 530 passed, 18 skipped, 16
  pre-existing z3 failures.
- **Next iteration's planned work**: P9 — extend the translator with
  `i32.div_s`, `i32.div_u`, `i32.rem_s`, `i32.rem_u` instructions and
  land seed task `0002-div-trap` (`bench/wasm-btor2/corpus/seed/
  0002-div-trap/`): a two-param function that performs signed integer
  division, expected to trap when the divisor is zero. This is the first
  corpus task where z3-bmc should return `verdict="reachable"` and the
  lifter produces a non-trivial `WasmWitness` (divisor=0 at trap_step>0),
  validating the full P7→P8 pipeline end-to-end.
- **Open BLOCKERs**: none.

---

## 2026-05-20T00:00:00Z — P7: z3-bmc solver adapter

- **Phase**: P7 complete.
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/solvers/_bmc.py` — backend-agnostic
    BMC driver copied from `riscv_btor2` (v2-bootstrap) with all imports
    re-targeted to `gurdy.pairs.wasm_btor2.btor2.*`. Contains `Compiled`
    (engine-neutral structural form of a parsed BTOR2 Model), `Backend`
    (Protocol every engine adapter satisfies), `compile_btor2` (structural
    compiler), and `bmc(comp, bound, backend)` (3-arg unroller; cycles
    through `bound` steps, asserts init/next/constraint/bad disjunction,
    calls check_sat).
  - Created `gurdy/pairs/wasm_btor2/solvers/btor2_to_z3.py` — z3 Backend
    adapter copied from `riscv_btor2` (v2-bootstrap), re-targeted. Provides
    `Z3Backend` (all BTOR2 op vocabulary → z3 expression translations:
    bitvec arithmetic, logic, shifts, comparisons, ite, concat, read/write,
    slice/sext/uext) and the 2-arg `bmc(comp, bound)` convenience wrapper
    that wires `Z3Backend` automatically. `compile_to_z3 = compile_btor2`
    alias preserved.
  - Created `gurdy/pairs/wasm_btor2/solvers/z3bmc.py` — `Z3BMCSolver`
    (`InProcessSolverBackend`) with `name="z3-bmc"`. `dispatch(artifact_bytes,
    directive)` parses `artifact_bytes` as UTF-8 BTOR2 text via
    `wasm_btor2.btor2.parser.from_text`, compiles to `Compiled` via
    `compile_btor2`, reads `directive.bound`, calls `bmc(comp, bound,
    Z3Backend())`, and returns `RawSolverResult(verdict, elapsed, engine,
    payload)`. On `reachable`: extracts `solver.model()` into
    `payload={"witness_text": str(model)}`. Gracefully returns
    `verdict="error"` on parse failures and `verdict="unknown"` on
    `NotImplementedError` (unsupported BTOR2 ops).
  - Updated `gurdy/pairs/wasm_btor2/solvers/__init__.py` — exports
    `Z3BMCSolver`, `Compiled`, `compile_btor2`, `Z3Backend`, `bmc`.
  - Updated `tests/conftest.py` — appends
    `/usr/local/lib/python3.11/dist-packages` to `sys.path` when present,
    making the system-installed `z3-solver` visible to the pytest venv.
  - Created `tests/pairs/wasm_btor2/test_solvers.py` — 28 tests:
    import/structural smoke (Z3BMCSolver, Compiled, bmc3, bmc2,
    Z3Backend instantiation), compile_btor2 shapes (state_nids,
    bad_nids from minimal BTOR2 fixtures), bmc3 direct (no-bad-node →
    unreachable; always-bad → reachable with solver; seed artifact →
    unreachable at bound=8), Z3BMCSolver.dispatch (verdict unreachable,
    engine name, elapsed > 0, payload None on unreachable, payload
    witness_text on reachable, graceful error on malformed bytes,
    bound=0 no-bad → unreachable), Z3Backend unit ops (bv_const/zero/
    one/ones, add, eq, ite, unsupported op raises NotImplementedError,
    check_sat sat/unsat).
- **Validation on seed task**: `Z3BMCSolver().dispatch(artifact, bound=8)`
  on `0001-i32-add-wrap` → `verdict="unreachable"` in ~20ms.
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 158 passed
  (28 new); full suite → 541 passed, 16 skipped, 0 failed.
- **Next iteration's planned work**: P8 — lifter skeleton
  (`gurdy/pairs/wasm_btor2/lift/`). Given a `RawSolverResult` with
  `verdict="reachable"` and a `witness_text` from the z3 model, extract
  a `WasmWitness` (concrete parameter assignments and the step at which
  the trap fires). Validate on a minimal BTOR2 model with a reachable
  bad node to confirm witness parsing.
- **Open BLOCKERs**: none.

---

## 2026-05-19T22:00:00Z — P6: Corpus seed task 0001-i32-add-wrap

- **Phase**: P6 complete.
- **What changed**:
  - Created `bench/wasm-btor2/corpus/seed/0001-i32-add-wrap/module.wasm`
    — 42-byte hand-crafted WASM binary: type section `(i32,i32)→i32`,
    function section (one func, type index 0), export section
    (`"main"` → func 0), code section (body: `local.get 0; local.get 1;
    i32.add; end`). SHA-256:
    `c4e0c901b54c4ba8036806aaf9ba3766469dde748870ade4943c300ca5b84558`.
  - Created `bench/wasm-btor2/corpus/seed/0001-i32-add-wrap/spec.json`
    — `WasmBtor2Spec` serialized: `pair="wasm-btor2"`,
    `module.path="module.wasm"`, `module.content_hash` set to SHA-256
    above, `scope.entry_function="main"`, `question.kind="reach_trap"`,
    `question.negate=false`, `analysis.engine="z3-bmc"`, `bound=8`,
    `timeout=60`. Round-trips via `WasmBtor2Spec.from_jsonable`.
  - Created `bench/wasm-btor2/corpus/seed/0001-i32-add-wrap/task.toml`
    — task metadata: `id="0001-i32-add-wrap"`, `pair="wasm-btor2"`,
    `task_class="wrap-semantics"`, `difficulty="T1"`,
    `oracle_provenance="manual-proof"`, `expected.verdict="unreachable"`,
    `oracle.status="agreement"`, `oracle.bound=8`, `oracle.cases_checked=5`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed.py` — 24 tests:
    file-shape checks (module.wasm magic/version/size, spec.json/task.toml
    presence), content_hash round-trip against actual SHA-256,
    `WasmBtor2Spec.from_jsonable` round-trip, oracle agreement for 5
    concrete param pairs `(0+0, 3+5, 1+(−1), INT32_MAX+1, −1+(−1))`,
    `Btor2ReasoningInterpreter` bad_fired=False for 6 param pairs at
    bound=8 (confirming reach_trap unreachable via concrete simulation).
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 130 passed
  (24 new); full suite → 513 passed, 16 skipped, 0 failed.
- **Next iteration's planned work**: P7 — z3-bmc solver adapter
  (`gurdy/pairs/wasm_btor2/solvers/`). Wire up z3 Python API to consume
  a `CompiledArtifact`, run bounded model checking on the flattened
  BTOR2 output, and return `verdict ∈ {reachable, unreachable, unknown}`
  with a witness on `reachable`. Validate on `0001-i32-add-wrap` (expect
  `unreachable` at bound 8).
- **Open BLOCKERs**: none.

---

## 2026-05-19T20:00:00Z — P5: Alignment oracle

- **Phase**: P5 complete.
- **What changed**:
  - Created `bench/wasm-btor2/oracle_align.py` — standalone alignment
    oracle module + CLI. Public API: `ORACLE_VERSION = "1.0.0"`,
    `make_add_wasm()` (returns 0001-i32-add-wrap WASM bytes),
    `AlignmentMismatch(step, label, source_value, reasoning_value)`,
    `AlignmentReport(outcome, steps_checked, mismatches)`, and
    `run_oracle(params, *, bound=8, wasm_bytes=None, entry_name="main")`.
  - `run_oracle` wires up `WasmSourceInterpreter` and
    `Btor2ReasoningInterpreter` on the same concrete inputs:
    (a) compiles WASM → BTOR2 via `Translator`; (b) runs the source
    interpreter with `record_shadow=True` to capture per-step
    `local_write` deltas; (c) runs the reasoning interpreter with
    `state_init_by_symbol = {local_k: params[k]}` to supply concrete
    param values (overriding the `param_k_init` input-node init);
    (d) walks the two traces step-by-step comparing local-variable
    values and the trap flag. Reports "agreement" or "divergence"
    with the full mismatch list.
  - CLI output for 0001-i32-add-wrap over 5 test cases (0+0, 3+5,
    1+(-1), INT32_MAX+1, -1+-1): all report agreement over 4 steps.
  - Created `tests/pairs/wasm_btor2/test_oracle.py` — 19 tests:
    version export, `make_add_wasm` shape, agreement for 0+0 / 3+5 /
    INT32_MAX+1 / -1+-1 / negative-param / asymmetric pairs,
    steps_checked > 0, no-mismatches-on-agreement, `agrees` property,
    summary string, report field presence, trap agreement for
    unreachable function (steps_checked=1, no mismatches), bound
    parameter limits steps, bound=1 still agrees.
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 106 passed;
  full suite → 489 passed, 16 skipped, 0 failed.
- **Next iteration's planned work**: P6 — Corpus seed task
  (`bench/wasm-btor2/corpus/seed/0001-i32-add-wrap/`). Write
  `task.toml`, `spec.json`, and an inline WASM binary
  (`module.wasm`), wired together as a ground-truth seed: expected
  verdict `unreachable` (trap never fires for i32.add), verified by
  the oracle and the reasoning interpreter at bound 8.
- **Open BLOCKERs**: none.

---

## 2026-05-19T18:00:00Z — P4: Translator (WASM MVP → BTOR2)

- **Phase**: P4 complete.
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/translation/builder.py` — BTOR2
    node-construction helpers adapted from the riscv-btor2 reference;
    imports target `gurdy.pairs.wasm_btor2.btor2.*`; adds `bv16` to
    SORT_TABLE for PC encoding.
  - Created `gurdy/pairs/wasm_btor2/translation/layers.py` — per-layer
    emitters (`emit_header`, `emit_machine`, `emit_library`,
    `emit_dispatch`, `emit_init`, `emit_constraint`, `emit_bad`,
    `emit_binding`). Value stack modeled as BTOR2 `Array[bv8, bv32]`;
    PC as bv16; SP as bv8; locals as individual bv32 state variables;
    params initialized from `input` nodes at step 0. P4 instruction
    set: `i32.const`, `i32.add`, `i32.sub`, `i32.mul`,
    `local.get/set/tee`, `drop`, `nop`, `end` (function-level),
    `return`, `unreachable`. Unsupported instructions set the trap
    flag. `reach_trap` property emits `bad trap_nid`. `LocalInit`
    assumptions emit BTOR2 `constraint` nodes. Dispatch uses PC-keyed
    ITE trees over all state components.
  - Created `gurdy/pairs/wasm_btor2/translation/translate.py` —
    `Translator.translate(spec, source, annotation_emitter)` assembles
    layers in order, splits on `:layer:NAME:begin`/`:end` markers, and
    returns `CompiledArtifact`. `TRANSLATOR_VERSION = "1.0.0"`.
  - Updated `gurdy/pairs/wasm_btor2/translation/__init__.py` — exports
    `Translator`, `translate`, `TRANSLATOR_VERSION`, `SCHEMA_VERSION`.
  - Created `tests/pairs/wasm_btor2/test_translation.py` — 18 tests:
    version exports, CompiledArtifact shape (pair, schema_version, all
    8 layers present), i32.add/sub/mul/const compile without error,
    BTOR2 flattened output is parseable, bad layer non-empty for
    reach_trap, bad node present in BTOR2 text, negate=True inserts
    `not` in bad layer, ValueError when entry not found, LocalInit
    emits a constraint node.
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 87 passed;
  full suite → 470 passed, 16 skipped, 0 failed.
- **Next iteration's planned work**: P5 — Alignment oracle
  (`bench/wasm-btor2/oracle_align.py`). Wire up `WasmSourceInterpreter`
  and `Btor2ReasoningInterpreter` on the same concrete inputs, run the
  BTOR2 model through the reasoning interpreter, and assert that
  observable state (locals, trap flag) aligns step-by-step with the
  source interpreter's trace. Target: `0001-i32-add-wrap` shape —
  a two-param i32 add with symbolic inputs at BMC bound 8.
- **Open BLOCKERs**: none.

---

## 2026-05-19T16:00:00Z — P3: Reasoning interpreter (BTOR2)

- **Phase**: P3 complete.
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/btor2/` — full copy of the
    pair-agnostic BTOR2 subpackage from `riscv_btor2` at
    INTERPRETER_VERSION 1.1.0: `nodes.py` (Model AST, BitvecSort,
    ArraySort, Node, Comment), `evaluator.py` (concrete single-cycle
    evaluator for all arithmetic, logic, shift, comparison, memory,
    extension, slice, concat, ite ops), `parser.py` (permissive HWMCC
    superset parser with diagnostic reporting), `printer.py`
    (canonical round-trip text emitter), `__init__.py`. All imports
    redirected to `gurdy.pairs.wasm_btor2.btor2.*`; copy is
    self-contained so the wasm pair can diverge independently.
  - Created `gurdy/pairs/wasm_btor2/reasoning_interp/bindings.py` —
    `Btor2ReasoningBinding` with `pair = "wasm-btor2"`,
    `state_init_by_symbol`, `input_per_step_by_symbol`, and
    `from_jsonable`.
  - Created `gurdy/pairs/wasm_btor2/reasoning_interp/interpreter.py` —
    `Btor2ReasoningInterpreter.run()` producing `ReasoningTrace` with
    `pair = "wasm-btor2"` and `INTERPRETER_VERSION = "1.1.0"`. Full
    multi-step transition system: init-clause seeding, per-step input
    injection, next-clause state advancement, POST-step bad-clause
    firing detection. `_artifact_hash` uses SHA-256 of flattened bytes.
  - Updated `gurdy/pairs/wasm_btor2/reasoning_interp/__init__.py` —
    exports `Btor2ReasoningBinding`, `Btor2ReasoningInterpreter`,
    `INTERPRETER_VERSION`; docstring records copy provenance.
  - Created `tests/pairs/wasm_btor2/test_reasoning_interp.py` — 11
    tests: PAIR_ID == "wasm-btor2", INTERPRETER_VERSION exported,
    counter advances per step, `state_init_by_symbol` override,
    bad-clause fires at correct step, no bad → no firing, per-step
    input injection, `from_jsonable` round-trip, zero steps, btor2
    subpackage independence (parser + evaluator + printer each
    exercised), artifact hash in trace.
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 69 passed;
  full suite → 452 passed, 16 skipped, 0 failed.
- **Next iteration's planned work**: P4 — Translator (WASM MVP →
  BTOR2). Minimal viable translator in
  `gurdy/pairs/wasm_btor2/translation/`: compile a single-function
  WASM module with i32 arithmetic (add, sub, const) into a BTOR2
  transition system covering the `header`, `machine`, `library`,
  `dispatch`, `init`, and `bad` sections per V2_BOOTSTRAP.md §3.3.
  Start with the `0001-i32-add-wrap` seed task shape.
- **Open BLOCKERs**: none.

---

## 2026-05-19T14:00:00Z — P2: Source interpreter skeleton

- **Phase**: P2 complete.
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/source/decoder.py` — full WASM 1.0
    MVP binary decoder: LEB128 readers; type/import/function/export/
    global/memory/code/data section parsers; pre-decoded `Instr` list
    with two-pass jump-target resolution for block/loop/if/else/end.
  - Updated `gurdy/pairs/wasm_btor2/source/__init__.py` — `WasmSource`
    wrapper with `export()`, `export_func_idx()`, `func_type()`,
    `code_entry()`, `is_import()`, `globals_info()`, `memory_info()`,
    `import_funcs()`; `load_wasm_source(payload)` accepting bytes or
    path, sets `content_hash` (SHA-256).
  - Created `gurdy/pairs/wasm_btor2/source_interp/bindings.py` —
    `WasmInputBinding` (param_init, global_init, memory_init,
    import_returns; FREE sentinel; FreeFieldNotAllowed).
  - Created `gurdy/pairs/wasm_btor2/source_interp/interpreter.py` —
    `WasmSourceInterpreter.run()` producing `SourceTrace` with one
    `SourceStep` per instruction: all i32/i64 integer arithmetic,
    comparisons, bitwise ops, shifts, rotates; memory load/store (all
    widths, sign/zero extend); structured control flow (block, loop,
    if/else, br, br_if, br_table, return); local.get/set/tee,
    global.get/set; call (direct, imports via import_returns);
    memory.size/grow; drop, select; i32.wrap_i64,
    i64.extend_i32_s/u; trap handling (unreachable, div-by-zero,
    overflow, OOB memory, stack depth). Shadow mode records
    local/global reads and writes per step.
  - Updated `gurdy/pairs/wasm_btor2/source_interp/__init__.py`.
  - Created `tests/pairs/wasm_btor2/test_source.py` — 17 tests covering
    decode errors, section parsing, branch-target resolution, and
    WasmSource accessors.
  - Created `tests/pairs/wasm_btor2/test_interp.py` — 23 tests covering
    constants, params, arithmetic (add/sub/mul/div wrap/trap/signed),
    shifts (mask-mod-32 semantics for corpus seed 0004), control flow
    (if/else, loop with br-back), memory round-trip and OOB trap,
    local.tee, conversions, trace step count, shadow mode, FREE
    binding rejection, and direct call.
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 42 passed;
  full suite → 421 passed, 18 skipped, 0 failed.
- **Next iteration's planned work**: P3 — Reasoning interpreter (BTOR2).
  Port `gurdy/pairs/riscv_btor2/reasoning_interp/` to
  `gurdy/pairs/wasm_btor2/reasoning_interp/` by copying the
  pair-agnostic BTOR2 simulator and marking it with
  `INTERPRETER_VERSION` for audit traceability per V2_BOOTSTRAP.md §3.2.
- **Open BLOCKERs**: none.

---

## 2026-05-19T12:00:00Z — P1: Schema v1.0.0

- **Phase**: P1 complete.
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/spec.py` — full Schema v1.0.0
    type system:
    - `Comparison` enum (eq/ne/lt/le/gt/ge + unsigned variants)
    - `WasmModuleRef(path, content_hash)` — module binary reference
    - `AnalysisScope(entry_function, included_callees)` — entry point
    - Observables: `LocalAt`, `GlobalAt`, `MemoryByteAt`, `StackDepthAt`
    - Assumptions: `LocalInit`, `GlobalInit`, `MemoryInit`, `ImportFixed`
    - `PropertyKind` enum (`reach_trap`, `reach_host_call`,
      `reach_memory`, `safety`)
    - `QuestionSpec(kind, predicate, negate)` — tagged property
    - `AnalysisDirective(engine, bound, timeout, extra_options)`
    - `WasmBtor2Spec` — frozen, hashable top-level spec with
      `from_jsonable` classmethod and full JSON round-trip
    - `validate_wasm_btor2_spec(spec, source=None)` — structural
      validator emitting `Diagnostic` instances (codes 0001–0031)
  - Frozen `gurdy/pairs/wasm_btor2/SCHEMA.md` at version `1.0.0` —
    documents all types, fields, discriminants, constraints, and
    out-of-scope items.
  - Created `tests/pairs/wasm_btor2/test_spec.py` — 16 tests
    covering: default construction, minimal valid spec, `from_jsonable`
    round-trip, `spec_hash` stability, all validator error codes.
- **Verification**: all spec tests pass (`import ok`, round-trip ok,
  hash stable, all validator codes confirmed in-process).
- **Next iteration's planned work**: P2 — Source interpreter skeleton.
  Write `gurdy/pairs/wasm_btor2/source.py` (`WasmSource` wrapping a
  parsed WASM binary with `export()` and function/global/memory
  accessors) and `gurdy/pairs/wasm_btor2/source_interp.py` (a minimal
  step-based interpreter over the WASM 1.0 MVP integer opcode subset,
  capable of producing observable traces for the test corpus).

---

## 2026-05-19T00:00:00Z — P0b: package metadata + CI baseline

- **Phase**: P0 complete.
- **What changed**:
  - Audited `gurdy/core/` against `v2-bootstrap`: file-for-file
    identical (38 files). No copy needed — `main` already carries
    the v2 core. Pair-agnostic contract (`schema.py`, `pair.py`,
    `layers.py`, `dispatch.py`, `interp/` shared types) is already
    present and unmodified.
  - Added `wasm-btor2 = []` to `[project.optional-dependencies]`
    in `pyproject.toml`.
  - Added `"gurdy.pairs.wasm_btor2" = ["SCHEMA.md"]` to
    `[tool.setuptools.package-data]`.
  - Created `tests/pairs/wasm_btor2/test_smoke.py` — 2 tests
    verifying all 7 submodules are importable with docstrings and
    that `SCHEMA.md` is accessible via `importlib.resources`.
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 2 passed.
- **Next iteration's planned work**: P1 — Schema v1.0.0 for
  `wasm-btor2`. Write `gurdy/pairs/wasm_btor2/spec.py` with
  `WasmBtor2Spec` (subclass of `BaseSpec`), `AnalysisScope`,
  `WasmModuleRef`, and `QuestionSpec` for the WASM MVP reach
  property. Freeze `SCHEMA.md` to `1.0.0`. Mirror riscv_btor2
  spec.py structure but strip RISC-V-specific types.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).

---

## 2026-05-18T07:30:00Z — P0a: package scaffold landed

- **Phase**: P0 in progress (P0a complete).
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/` with submodule directories
    `source/`, `source_interp/`, `reasoning_interp/`, `translation/`,
    `lift/`, `solvers/`. Each carries an `__init__.py` with a
    one-paragraph docstring stating its role and the phase at which
    implementation begins (per `V2_BOOTSTRAP.md` §6).
  - `gurdy/pairs/wasm_btor2/SCHEMA.md` placeholder noting the
    schema is frozen at `1.0.0` at P1.
  - `bench/wasm-btor2/{corpus/seed, corpus/external, baselines,
    experiments}/.gitkeep`.
  - `tests/pairs/wasm_btor2/__init__.py`.
- **Verification**: `python -c "import
  gurdy.pairs.wasm_btor2; ..."` succeeds for all seven submodules.
- **Next iteration's planned work**: P0b — copy `gurdy/core/`
  primitives from the `v2-bootstrap` branch where they conform to
  the pair-agnostic contract (`schema.py`, `pair.py`, `layers.py`,
  `dispatch.py`, `interp/` shared types). Audit each file against
  `V2_BOOTSTRAP.md` §3 before copying; do not pull WASM-incompatible
  code.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).

---

## 2026-05-17T00:00:00Z — Branch bootstrap

- **Phase**: pre-P0. Nothing implemented yet on this branch.
- **What's here**: `V2_BOOTSTRAP.md` (spec), `V2_AGENT_LOOP.md`
  (procedure), `V2_PROGRESS.md` (this file),
  `bench/wasm-btor2/SCOPE.md` (benchmark scope). Everything else
  is inherited from `main`.
- **Next iteration's planned work**: P0 — scaffold the
  `gurdy/pairs/wasm_btor2/` package and `bench/wasm-btor2/`
  directory shape per `V2_BOOTSTRAP.md` §5. Copy `gurdy/core/`
  primitives from the `v2-bootstrap` branch where they conform
  to the pair-agnostic contract.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).
