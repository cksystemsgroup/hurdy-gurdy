# `wasm-btor2` benchmark scope

This is the §9.1 instantiation of [BENCHMARKING.md](../../BENCHMARKING.md)
for the `wasm-btor2` pair. It defines what the benchmark covers and,
just as importantly, what it does not. Every later artifact (corpus,
prompts, rubric) inherits these boundaries.

## 1. Source language and dialect

- **Spec**: WebAssembly Core 2.0 (W3C Recommendation,
  https://www.w3.org/TR/wasm-core-2/).
- **Subset in scope (P1 schema v1.0.0)**: WASM 1.0 MVP.
  - Numeric types: `i32`, `i64`, `f32`, `f64`. **Float opcodes are
    in scope but deferred to P9** — initial seed corpus is
    integer-only.
  - Numeric instructions (integer): add/sub/mul, div_s/div_u,
    rem_s/rem_u, and/or/xor, shl/shr_s/shr_u/rotl/rotr,
    eqz/eq/ne/lt/gt/le/ge, clz/ctz/popcnt, extend, wrap, trunc.
  - Control flow: block, loop, if/else, br, br_if, br_table, return,
    call, call_indirect, unreachable, drop, select.
  - Memory: load/store (all widths and signedness), memory.size,
    memory.grow, memory.fill, memory.copy, memory.init, data.drop.
  - Tables: get/set, size, grow, fill, copy, init, elem.drop.
  - Variables: local.get/set/tee, global.get/set.
- **Out of scope at P1** (stable exclusions, may revisit later
  with schema bumps):
  - SIMD (`v128`) — full opcode surface deferred.
  - Threads / atomics — concurrency outside scope until P14+.
  - Reference types beyond `funcref` (`externref` deferred).
  - Tail calls (`return_call`, `return_call_indirect`).
  - Exception handling proposal.
  - GC proposal (struct/array/i31).
  - Component model (only core WASM modules).
- **Source artifact**: a single WebAssembly module
  (`.wasm` binary or `.wat` text), plus an `AnalysisScope` selecting
  the entry function and an `included_callees` set. Imports are
  modeled as `Free` bindings unless the spec pins them.

## 2. Reasoning language and solver inventory

- **Reasoning language**: BTOR2, schema version `1.0.0`. The
  schema follows the riscv-btor2 layered shape (header / machine /
  library / dispatch / init / constraint / bad / binding) but with
  a WASM-specific machine layer:
  - **Value stack**: modeled as either a finite array
    (`Array bv32 bv64`) with explicit SP, or as per-step unrolled
    explicit slots when bound is small. Choice pinned in
    `SCHEMA.md`.
  - **Locals / globals**: per-function bv-typed arrays.
  - **Linear memory**: `Array bv32 bv8` (byte-addressed, little
    endian per WASM spec).
  - **Function tables**: `Array bv32 bv32` (index → funcidx).
  - **PC**: `(funcidx, instr_offset)` pair.
  - **Trap flag**: `bv1` set on out-of-bounds, div-by-zero,
    indirect-call-type-mismatch, etc.

- **Solver inventory** (target):

| Engine        | Backend          | Role |
|---------------|------------------|------|
| `z3-bmc`      | z3 4.16.0        | BMC; default engine. |
| `z3-spacer`   | z3 4.16.0        | Inductive (Horn / fixedpoint). |
| `bitwuzla`    | 0.9.0+           | BMC alternative; bitvector-strong. |
| `cvc5`        | 1.3.3+           | BMC alternative; second-vendor cross-check. |
| `pono`        | 2.0.0-beta+      | Subprocess BMC + k-induction. |

The §9.12 multi-engine cross oracle (`oracle_cross.py`) is what
makes bitwuzla / cvc5 / pono load-bearing: every corpus task is
dispatched under every compatible engine, and the agreement matrix
is the §4.5 oracle.

## 3. Property language

A `QuestionSpec` for `wasm-btor2` targets one of:

- **`reach(trap)`** — does the module trap (unreachable, OOB,
  div-by-zero, indirect-call type mismatch, table OOB) within
  `bound` steps starting from `entry_function`?
- **`reach(host_call, args)`** — does the module invoke a host
  import with arguments matching a predicate?
- **`reach(memory_predicate)`** — does linear memory or a global
  ever satisfy a predicate at a structured location?
- **`safety(invariant)`** — does an invariant hold at every step?
  (Inductive engines required.)

Witness format: a sequence of `(input_binding, step_index)` pairs
naming the imports / `Free` cells the lifter reads to render a
source-level counterexample.

## 4. Corpus structure

```
bench/wasm-btor2/corpus/
  seed/
    0001-i32-add-wrap/
      task.toml         # ground truth, expected, notes
      task.wasm         # binary module
      task.wat          # text form (for review)
      task.spec.json    # the QuestionSpec
      task.source.c     # optional: source the wasm was compiled from
    0002-div-trap/
    ...
  external/
    rust-snippet-NNN/   # streamed; one wasm per dir
    ...
```

Seed tasks are hand-crafted and must each pinpoint exactly one
wedge claim (the source-level UB → WASM-defined behavior gap).
External tasks come from public Rust/C/AssemblyScript repos via
the streaming recipe (`V2_AGENT_LOOP.md` §4).

## 5. SOTA baselines

Mandatory comparison baselines for the Pareto table:

- **Manticore-WASM** (`pip install manticore`) — symbolic
  execution, mature.
- **KLEE-WASM** (Galois prototype or research fork) — best-effort
  install; skip-with-note if absent.
- **Crucible-WASM (Galois)** — best-effort; skip-with-note.
- **wasm-smith fuzz seed** (not a verifier, but a coverage
  baseline) — optional.

Each baseline gets one adapter under `bench/wasm-btor2/baselines/`
following the riscv-btor2 pattern (`cbmc.py`, `pono.py`,
`hurdy_gurdy.py`, `pareto.py`).

## 6. The wedge class to chase

The §13 sharper pattern from `riscv-btor2`'s INITIAL_FINDINGS.md
predicts the analogous WASM wedge class:

**Source-language UB that has a defined WASM lowering.** Examples:

- **C signed integer overflow** → WASM `i32.add` is unsigned-wrap
  (modulo 2^32). Defined.
- **C divide-by-zero** → WASM `i32.div_s` / `i32.div_u` traps.
  Defined trap.
- **C `INT_MIN / -1`** → WASM `i32.div_s` traps. Defined trap.
- **C shift amount ≥ width** → WASM `i32.shl` masks shift count
  mod 32. Defined.
- **C type-punned pointer load** → WASM `i32.load` is byte-array
  access. Defined.
- **C uninitialized local read** → WASM locals are zero-initialized
  by spec. Defined.
- **Rust integer overflow in release mode** → WASM `i32.add` wraps
  identically. Defined.

For each, the corpus should contain at least one task where the
source-level verifier (CBMC on the C source, Kani on the Rust
source) produces a false positive while hurdy-gurdy on the
emitted WASM produces the correct verdict.

## 7. Out-of-scope properties

- **Performance / timing properties** — WASM has no defined
  timing model.
- **Side-channel properties** — out of scope until a
  cost-instrumented schema bump.
- **Non-determinism via host imports** — modeled as `Free`
  bindings; the spec must pin the relevant ones for safety
  properties to be provable.
- **Module linking / multi-module programs** — single module
  only at P1; multi-module via a future schema bump.
