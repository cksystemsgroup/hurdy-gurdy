# `wasm-btor2` Progress — Live State

> The single source of truth for "where is the `wasm-btor2` bootstrap
> right now." Each iteration appends one entry at the top. Older
> entries stay for history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

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
