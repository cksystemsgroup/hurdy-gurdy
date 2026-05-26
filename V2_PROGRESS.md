# `evm-btor2` Progress — Live State

> The single source of truth for "where is the `evm-btor2` bootstrap
> right now." Each iteration appends one entry at the top. Older
> entries stay for history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-05-26T16:40:00Z — P6: JUMPI lowering + seed 0004 oracle coverage

- **Phase**: P6 complete.
- **What changed**: Added `lower_jumpi` to `library.py` (opcode 0x57, gas=10).
  Lowering: pops TOS (`dest`, bv256 → truncated to bv16 via `slice`) and NOS
  (`cond`, bv256); if `cond == 0` falls through (`pc += 1`), else jumps to
  `dest16`; `sp -= 2`; trap conditions: `sp < 2` (underflow) and `gas < 10`
  (OOG).  Wired into `translator.py` opcode router (0x57 → `lower_jumpi` before
  0x5b JUMPDEST), and exported from `translation/__init__.py`.  9 new library
  tests (fall-through pc, taken-branch pc, sp decrement, gas, OOG trap,
  underflow trap, halted noop, round-trip).  3 new oracle tests for seed 0004
  (`600035600757005b604260005500`): without-witness UNSAT, with `calldata{31:1}`
  SAT, `witness_step=8`.  249 tests total, all green.
- **Next iteration's planned work**: P7 — add `ISZERO` (0x15) and `DUP1` (0x80)
  lowering to expand scope to seed 0005; then wire `AlignmentOracle` to the
  pair harness for full end-to-end spec-JSON-to-result pipeline.
- **Open BLOCKERs**: none.

## 2026-05-26T16:00:00Z — P5: AlignmentOracle

- **Phase**: P5 complete.
- **What changed**: Created `gurdy/pairs/evm_btor2/oracle/` package with
  `alignment.py` (`AlignmentResult` frozen dataclass, `AlignmentOracle.check`
  method) and `__init__.py`.  `AlignmentOracle.check(spec, witness_binding=None)`
  translates the spec's bytecode via `translate_bytecode`, wraps the BTOR2 text
  in a `CompiledArtifact`, builds a `Btor2ReasoningBinding` from the optional
  `witness_binding` dict (forwarded as `state_init_by_symbol`), runs
  `Btor2ReasoningInterpreter.run` up to `spec.analysis.bound` (default 100)
  steps, and returns `AlignmentResult(bad_fired, witness_step, btor2_model)`.
  11 new tests in `test_oracle_alignment.py` covering: seed 0001 SAT
  (bad_fired=True, witness_step=3), bound-too-small UNSAT (bound=3),
  bound-just-enough SAT (bound=4), wrong-value UNSAT, seed 0002 without
  witness UNSAT / with calldata{31:1} SAT (witness_step=4), seed 0003
  OOS-trap UNSAT (MSTORE8+RETURN not in P4 opcode set → trap=1 → bad
  requires NOT trap → never fires), and btor2_model non-empty in both
  SAT and UNSAT cases.  236 tests total, all green.
- **Next iteration's planned work**: P6 — wire `AlignmentOracle` to the
  harness (`gurdy/pairs/evm_btor2/harness.py` or equivalent) so the
  full `evm-btor2` pair pipeline is exercisable end-to-end from a spec
  JSON file; add JUMPI (0x57) lowering to expand scope to seeds 0004–0005.
- **Open BLOCKERs**: none.

## 2026-05-26T15:20:00Z — P4: translate_bytecode (full dispatcher)

- **Phase**: P4 complete.
- **What changed**: Created `gurdy/pairs/evm_btor2/translation/translator.py`
  with `translate_bytecode(bytecode, spec) -> str` — the main P4 entry
  point.  It orchestrates all six SCHEMA.md §13 layers: header → machine
  states → context inputs (with spec assumptions) → init clauses →
  PC-keyed ITE dispatch (`_build_dispatch` iterates `pc_lowerings` in
  reverse, wrapping each as nested `ite(pc==offset, result, prev)`) →
  `next` clauses → bad property from `ReachProperty` (`_emit_bad_expr`
  handles STOP/REVERT/STORAGE_EQ/RETURNDATA_EQ).  Includes helpers:
  `_lower_insn` (routes 0x00 STOP, 0x01 ADD, 0x35 CALLDATALOAD, 0x55
  SSTORE, 0x5b JUMPDEST, 0x60 PUSH1; all others → `_lower_oos`),
  `_lower_jumpdest` (pc+=1, gas-=1), and `_lower_oos` (trap=1, halted=1,
  SCHEMA.md §16).  Updated `translation/__init__.py` to export
  `translate_bytecode`.  11 new tests in
  `test_translation_translator.py` covering: BTOR2 round-trips (STOP,
  PUSH1+STOP, seed-0001, ADD), STOP sets halted / not trap, PUSH1+STOP
  bad fires at step 1, **seed 0001** (PUSH1 0x42 / PUSH1 0x00 / SSTORE /
  STOP) bad fires at step 3 and not before, wrong-value doesn't fire,
  out-of-scope opcode traps.  225 tests total, all green.
- **Next iteration's planned work**: P5 — alignment oracle skeleton:
  create `gurdy/pairs/evm_btor2/oracle/` package with
  `AlignmentOracle` that runs `translate_bytecode` to produce a BTOR2
  model, feeds it to the reasoning interpreter up to `spec.analysis.bound`
  steps, and returns an `AlignmentResult` indicating whether bad fired
  (SAT witness found) or not (UNSAT up to bound).  Wire to the harness
  and exercise with all 5 corpus seeds (0001–0005), checking that
  seeds 0001–0003 produce SAT results and that the bound is respected.
- **Open BLOCKERs**: none.

---

## 2026-05-26T14:40:00Z — P4: lower_sstore + lower_calldataload

- **Phase**: P4 in progress.
- **What changed**: Extended `gurdy/pairs/evm_btor2/translation/library.py`
  with `lower_sstore(builder, machine_nids)` (pops slot/value from TOS/NOS,
  writes `sto[slot]:=value`, sets `sto_warm[slot]:=1`, 2-case warm/cold gas
  model: `SSTORE_GAS_COLD=2200` / `SSTORE_GAS_WARM=100` from
  `sto_warm[slot][0:0]`, underflow+OOG trap guards, sp−=2, pc+=1) and
  `lower_calldataload(builder, machine_nids, ctx_nids)` (pops offset from
  TOS, reads 32 bytes big-endian from `calldata[offset..offset+31]` via
  31 concat operations producing a bv256 word, replaces TOS in place so
  net sp=0, gas−=3, pc+=1; intermediate bitvec sorts bv16–bv248 auto-
  declared by `Btor2Builder.declare_sort`).  Updated `__init__.py` to
  export both lowerings and constants.  24 new tests in
  `test_translation_library.py` (11 SSTORE + 10 CALLDATALOAD + 3 constant
  checks) covering structure, concrete storage write, warm/cold gas costs,
  trap paths (OOG, underflow), and BTOR2 round-trips.  214 tests total,
  all green.
- **Next iteration's planned work**: P4 continued — implement a
  `translate_bytecode(bytecode: bytes, spec: EvmBtor2Spec) -> str` function
  in `translation/translator.py` that: (1) disassembles the bytecode,
  (2) calls `emit_header + emit_machine_states + emit_context_inputs +
  emit_init_clauses`, (3) for each opcode position builds one
  `EvmLoweringResult` per PC offset, (4) wires a PC-keyed ITE dispatch tree
  (SCHEMA.md §13) wiring all `next` clauses, (5) emits the `bad` property
  from the spec's `ReachProperty`; then test by translating corpus seed
  0001 (PUSH1/PUSH1/SSTORE/STOP, `storage_eq slot=0 value=66`) and
  verifying that the BTOR2 model round-trips cleanly.
- **Open BLOCKERs**: none.

---

## 2026-05-26T14:00:00Z — P4: lower_stop + lower_add

- **Phase**: P4 in progress.
- **What changed**: Extended `gurdy/pairs/evm_btor2/translation/library.py`
  with `lower_stop(builder, machine_nids)` (sets `halted=1`, `trap`
  unchanged, zero gas cost, all other states frozen; no-exec guard
  prevents double-halt) and `lower_add(builder, machine_nids)` (pops TOS
  and NOS from `stack[sp-1]`/`stack[sp-2]`, pushes their bv256 sum at
  `stack[sp-2]`, sp−=1, gas−=3, pc+=1; underflow check `sp<2` and
  out-of-gas check trigger trap/halted sticky flags via same exec-ITE
  pattern as PUSH1).  Updated `translation/__init__.py` to export both
  new lowerings and their constants (`STOP_GAS`, `ADD_GAS`, `ADD_SIZE`).
  23 new tests in `test_translation_library.py` (7 for STOP, 11 for ADD,
  plus constant/structure checks) covering semantics, trap conditions,
  no-op-when-halted, and BTOR2 round-trip.  Note: discovered that "no
  trap on clean exec" tests must cap max_steps=1 because the same
  single-opcode dispatch model re-applies the lowering each step (step 1
  of ADD hits underflow since sp=1 after step 0).  190 tests total, all
  green.
- **Next iteration's planned work**: P4 continued — implement
  `lower_sstore(builder, machine_nids)` (slot=stack[sp-1],
  value=stack[sp-2], sto'=write(sto,slot,value), sp−=2, gas per
  EIP-2929/3529 cold/warm schedule, pc+=1) and
  `lower_calldataload(builder, machine_nids, ctx_nids)` (reads 32 bytes
  from `calldata[offset..offset+31]`, pushes bv256 result, sp+=1,
  gas−=3, pc+=1); then wire a `dispatch_single(builder, opcode,
  machine_nids, ctx_nids, spec)` function that routes by opcode to the
  correct lowering; exercise by building a BTOR2 model for seed 0001
  (PUSH1/PUSH1/SSTORE/STOP) and verifying the `storage_eq` property.
- **Open BLOCKERs**: none.

---

## 2026-05-26T13:20:00Z — P4: lower_push1 + EvmLoweringResult

- **Phase**: P4 in progress.
- **What changed**: Created `gurdy/pairs/evm_btor2/translation/library.py`
  with `EvmLoweringResult` (12-field dataclass mirroring `MACHINE_STATE_VARS`)
  and `lower_push1(builder, machine_nids, immediate)`.  `lower_push1`
  computes BTOR2 next-state nid expressions for a PUSH1 instruction:
  stack-overflow check (`uext(sp,246)==1024`), out-of-gas check
  (`gas < 3`), `exec = not(no_exec OR trap_from_op)` guard, normal-path
  ITE mux for `sp`/`stack`/`pc`/`gas`, and sticky `trap`/`halted`.
  Unchanged states (`mem`, `mem_words`, `sto`, `sto_warm`, `returndata`,
  `returndatasize`) alias the input state nids.  Updated
  `translation/__init__.py` to export `EvmLoweringResult`, `lower_push1`,
  `PUSH1_GAS`, and `PUSH1_SIZE`.  20 new tests in
  `test_translation_library.py` covering result structure, all-fields
  int check, unchanged/changed nid invariants, sp/pc/gas/stack concrete
  semantics via reasoning interpreter, OOG trap (sp/pc/gas frozen),
  already-halted/trapped no-op, round-trip, and immediate edge cases
  (0x00 and 0xFF).  167 tests total, all green.
- **Next iteration's planned work**: P4 continued — implement
  `lower_stop(builder, machine_nids)` (sets `halted=1` cleanly, no trap,
  freezes all other states) and `lower_add(builder, machine_nids)` (pops
  two bv256 operands, pushes their bv256 sum, gas -= 3, pc += 1); then
  add a `build_single_opcode_model(builder, spec, immediate)` dispatch
  helper that wires header + machine + context + init + single-opcode
  lowering + bad-property for a STOP/PUSH1/ADD bytecode; exercise with
  corpus seeds 0001–0003 in BTOR2 emission tests.
- **Open BLOCKERs**: none.

---

## 2026-05-26T12:40:00Z — P4: emit_context_inputs + emit_init_clauses

- **Phase**: P4 in progress.
- **What changed**: Created `gurdy/pairs/evm_btor2/translation/layers.py`
  with `emit_context_inputs(builder, spec)` and `emit_init_clauses(builder,
  spec, machine_nids)`.  `emit_context_inputs` declares all 13 SCHEMA.md §4
  symbolic context variables as BTOR2 states held constant via self-loop
  `next` clauses, emits address-validity constraints
  (`caller[255:160]==0`, `origin[255:160]==0`), pins `chainid=1` by
  default, and translates `CallerPin`, `CallvaluePin`, `OriginPin`,
  `CalldatasizePin`, and `CalldataBytePin` spec assumptions to `constraint`
  nodes.  `emit_init_clauses` emits BTOR2 `init` nodes for all six scalar
  machine states (`sp`, `mem_words`, `pc`, `trap`, `halted`,
  `returndatasize`) to zero; applies `GasLimitPin` as a `gas` init value;
  encodes `StoragePin` and `StorageWarm` as `constraint(read(sto/sto_warm,
  slot)==value)` nodes (all-steps; step-0 guard deferred to P5).  Updated
  `translation/__init__.py` to export both layer functions.  21 new tests in
  `test_translation_layers.py` covering structure, assumption types, init
  presence, pin values, and full-emission BTOR2 round-trip.  147 tests
  total, all green.
- **Next iteration's planned work**: P4 continued — implement
  `gurdy/pairs/evm_btor2/translation/library.py` with a minimal opcode
  lowering function `lower_push1(builder, machine_nids, immediate)` that
  emits the BTOR2 `next` clauses for `sp`, `stack`, `pc`, and `gas` for a
  PUSH1 instruction; then write hand-traced BTOR2 output tests verifying the
  resulting model evaluates correctly via the reasoning interpreter.
- **Open BLOCKERs**: none.

---

## 2026-05-26T12:20:00Z — P3+P4: halted/trap interpreter test + Btor2Builder skeleton

- **Phase**: P3 complete; P4 begun.
- **What changed**: Added 3 tests to `test_reasoning_interp.py` using a
  minimal halted/trap 2-state BTOR2 model that mirrors EVM SCHEMA.md §3.1
  bv1 machine flags (`halted'=or(halted, counter==3)`, `trap'=halted`,
  `bad=and(halted,trap)`). Traced: bad fires at step 4 when both flags
  become 1 simultaneously; tests cover exact step, under-bound (no fire),
  and layer_values membership for halted/trap nids.  Created
  `gurdy/pairs/evm_btor2/translation/builder.py` (`Btor2Builder`) with:
  `EVM_BITVEC_SORTS` (bv1/8/10/16/64/256), `EVM_ARRAY_SORTS`
  (stack_t/mem_t/sto_t), `MACHINE_STATE_VARS` (12 symbols from §3.1+§3.2),
  `emit_header()` (declares all 9 sorts), `emit_machine_states()` (declares
  all 12 state variables with correct sort nids, returns symbol→nid dict),
  plus core builder helpers (const, add/sub/mul/and/or/xor/not/ite/eq/ult
  etc., uext/sext/slice/concat, read/write, state/init/next/bad/constraint).
  Updated `translation/__init__.py` to export `Btor2Builder`.  22 new tests
  in `test_translation_builder.py` covering sort idempotency, state counts,
  constant ops, arithmetic helpers, and BTOR2 round-trip via printer/parser.
  126 tests total, all green.
- **Next iteration's planned work**: P4 continued — implement
  `gurdy/pairs/evm_btor2/translation/layers.py` with `emit_context_inputs()`
  that declares the symbolic context state variables from SCHEMA.md §3.3
  (caller, callvalue, calldata, calldatasize, block vars) using the builder,
  plus `emit_init_clauses()` that wires zero-init for all machine states and
  applies StoragePin / GasLimitPin / StorageWarm assumptions from the spec.
- **Open BLOCKERs**: none.

---

## 2026-05-26T12:00:00Z — P2+P3: JUMPI corpus seeds 0004–0005 + reasoning_interp skeleton

- **Phase**: P2 complete; P3 begun.
- **What changed**: Added 2 JUMPI-based corpus seeds:
  `0004-jumpi-sstore-on-taken` (storage_eq slot=0 value=0x42, SAT —
  solver must find any non-zero calldata word to take the JUMPI branch
  reaching the SSTORE) and `0005-jumpi-sstore-on-not-taken`
  (storage_eq slot=0 value=1, SAT — solver must find calldata[0..31]=1
  so ISZERO produces 0, JUMPI is NOT taken, and fall-through reaches
  SSTORE(slot=0, calldata)).  Both seeds verified against the P2
  concrete executor (executor.run) and round-trip through
  `EvmBtor2Spec.from_jsonable`.  Created
  `gurdy/pairs/evm_btor2/btor2/` subpackage — domain-free BTOR2 AST
  (nodes.py), parser (parser.py), evaluator (evaluator.py), printer
  (printer.py) — verbatim port of `v2-bootstrap:riscv-btor2/btor2/`
  with imports redirected to the local package and tagged
  `BTOR2_PACKAGE_VERSION = "1.0.0"`.  Created
  `gurdy/pairs/evm_btor2/reasoning_interp/interpreter.py`
  (`Btor2ReasoningInterpreter`, `INTERPRETER_VERSION = "1.0.0"`,
  `PAIR_ID = "evm-btor2"`) and `bindings.py`
  (`Btor2ReasoningBinding` with EVM SCHEMA.md §3 symbol names),
  adapted from riscv-btor2.  28 new tests in
  `tests/pairs/evm_btor2/test_reasoning_interp.py` covering BTOR2
  parser, evaluator (add/eq/ite/sort-mismatch), multi-step interpreter
  (counter model, bad-firing step, state override), and corpus seed
  round-trips for all 5 seeds.  104 tests total, all green.
- **Next iteration's planned work**: P3 continued — write a second
  BTOR2 interpreter test using a minimal 2-state model that mirrors the
  EVM SCHEMA.md halted/trap variables (bv1 states); then begin P4
  skeleton: `gurdy/pairs/evm_btor2/translation/` module stub with a
  `Btor2Builder` helper that emits sort declarations for the 6 sorts in
  SCHEMA.md §2 and the machine-state variable declarations from §3.1.
- **Open BLOCKERs**: none.

---

## 2026-05-26T00:00:00Z — P2: JUMPI/RETURN/MSTORE8 coverage + seed corpus (3 tasks)

- **Phase**: P2 in progress.
- **What changed**: Added 7 tests to `tests/pairs/evm_btor2/test_source_interp.py`
  covering the three opcodes that were implemented but untested: JUMPI
  (taken path, not-taken path, invalid-dest trap), RETURN (single-byte
  returndata via MSTORE8, 32-byte word via MSTORE), and MSTORE8 (single-byte
  write verified by MLOAD, and truncation of upper bytes confirmed).  76 tests
  total, all green.  Created the first three hand-crafted seed tasks in
  `bench/evm-btor2/corpus/seed/`: `0001-sstore-unconditional`
  (storage_eq, slot 0 = 0x42, SAT), `0002-sstore-from-calldata`
  (storage_eq, slot 0 = 1 via free calldata, SAT), and
  `0003-return-fixed-byte` (returndata_eq, offset 0 = [0x42], SAT).  Each
  seed has `task.bin`, `task.toml`, and `task.spec.json` that round-trips
  through `EvmBtor2Spec.from_jsonable`.
- **Next iteration's planned work**: P2 continued — add 2 more corpus seeds
  exercising JUMPI-based conditional branching (storage_eq only reachable on
  one branch, testing that the solver finds the right calldata witness); then
  begin P3 skeleton: `gurdy/pairs/evm_btor2/reasoning_interp/` module stub,
  porting the BTOR2 parser from `v2-bootstrap:gurdy/pairs/riscv_btor2/` and
  adapting it to the EVM SCHEMA.md variable names.
- **Open BLOCKERs**: none.

---

## 2026-05-25T00:00:00Z — P2: concrete EVM executor + bytecode disassembler

- **Phase**: P2 in progress.
- **What changed**: Implemented `gurdy/pairs/evm_btor2/source_interp/disasm.py`
  (`Instruction` dataclass, `disassemble()`, `compute_jumpdest_table()`) and
  `gurdy/pairs/evm_btor2/source_interp/executor.py` (`MachineState`,
  `EvmContext`, `StepRecord`, `step()`, `run()`).  The executor covers the
  full P1 opcode set: all arithmetic (ADD–SIGNEXTEND), comparison/bitwise
  (LT–SAR), environment vars (CALLER, CALLVALUE, CALLDATALOAD, CALLDATACOPY,
  CODESIZE, etc.), block vars (COINBASE–GASLIMIT), stack/memory/storage
  (POP, MLOAD, MSTORE, MSTORE8, MSIZE, GAS, PUSH0, PUSH1–32, DUP1–16,
  SWAP1–16, SLOAD, SSTORE), control flow (JUMP, JUMPI, JUMPDEST, PC), and
  termination (STOP, RETURN, REVERT, INVALID).  Gas model: static costs from
  §10.1, EXP byte-count dynamic (§10.2), memory expansion Cmem formula (§7.1),
  EIP-2929 SLOAD cold/warm (§8), EIP-2929/3529 SSTORE six-case schedule
  (§10.4).  Trap semantics: stack overflow/underflow, invalid jump dest,
  out-of-gas, out-of-scope opcode (§11/§16).  Shadow mode records per-step
  stack/memory/storage reads and writes.  `__init__.py` exports the public
  API.  17 new tests in `tests/pairs/evm_btor2/test_source_interp.py`
  covering 5 hand-traced sequences (ADD, MUL+SUB, JUMP+JUMPDEST, SSTORE+SLOAD,
  CALLDATALOAD), memory round-trip, trap cases, disassembler, and shadow mode.
  69 tests total, all green.
- **Next iteration's planned work**: P2 continued — JUMPI coverage (conditional
  branch, both taken and not-taken paths); RETURN with returndata; MSTORE8;
  extend corpus with ≥ 3 hand-crafted bytecode seeds in
  `bench/evm-btor2/corpus/seed/` exercising the storage_eq and returndata_eq
  reach properties.
- **Open BLOCKERs**: none.

---

## 2026-05-24T00:00:00Z — P1: SCHEMA.md v1.0.0 frozen; EvmBtor2Spec implemented

- **Phase**: P1 complete.
- **What changed**: `SCHEMA.md` frozen at v1.0.0 — specifies sorts
  (`bv1/8/10/16/64/256`, three array sorts), machine state variables
  (`sp`, `stack`, `mem`, `mem_words`, `sto`, `sto_warm`, `pc`, `gas`,
  `trap`, `halted`, `returndata`, `returndatasize`), symbolic context
  inputs (CALLER, CALLVALUE, ORIGIN, calldata, block vars), gas model
  (full static costs table + EXP dynamic + memory expansion +
  EIP-2929/3529 SSTORE schedule), opcode lowering table for the
  pure-function P1 subset, layer structure (header → machine → context
  → constraint → dispatch → binding → bad), and reach-property
  encoding (`revert` / `stop` / `storage_eq` / `returndata_eq`).
  `spec.py` implements `EvmBtor2Spec` (BaseSpec subclass), all eight
  assumption types, `ReachProperty`, `AnalysisDirective`, JSON
  round-trip (`from_jsonable`), and `validate_evm_btor2_spec`
  (52 tests green, `tests/pairs/evm_btor2/test_spec.py`).
- **Next iteration's planned work**: P2 — source interpreter skeleton:
  bytecode disassembler (opcode + immediate decoder), concrete EVM
  executor for the pure-function P1 opcode set (stack machine +
  memory + storage + calldata), trap semantics, shadow mode
  (per-instruction stack/memory/storage read-write records).
  Target: `gurdy/pairs/evm_btor2/source_interp/` and
  `tests/pairs/evm_btor2/test_source_interp.py` with ≥ 5 hand-traced
  bytecode sequences covering arithmetic, control flow, and storage.
- **Open BLOCKERs**: none.

---

## 2026-05-22T00:00:00Z — P0: package + bench scaffold

- **Phase**: P0 complete.
- **What changed**: Created `gurdy/pairs/evm_btor2/` package skeleton
  (`__init__.py`, `spec.py`, `SCHEMA.md`, `source/`, `source_interp/`,
  `reasoning_interp/`, `translation/`, `lift/`, `solvers/`); added
  `bench/evm-btor2/corpus/{seed,external}/`, `harness.py`,
  `oracle_align.py`, `oracle_cross.py`, `engine_bench.py`,
  `baselines/{smtchecker,hevm,hurdy_gurdy,pareto}.py`;
  `tests/pairs/evm_btor2/`.  `gurdy/core/` already matched
  `v2-bootstrap` — no copy needed.  Package imports cleanly.
- **Next iteration's planned work**: P1 — define `SCHEMA.md` v1.0.0
  for the pure-function subset (no `CALL`/`DELEGATECALL`), single
  contract, BMC engine, `reach`-property `QuestionSpec`.  Freeze
  SCHEMA.md and stub `EvmBtor2Spec` + validator in `spec.py`.
- **Open BLOCKERs**: none.

---

## 2026-05-17T00:00:00Z — Branch bootstrap

- **Phase**: pre-P0. Nothing implemented yet on this branch.
- **What's here**: `V2_BOOTSTRAP.md` (spec), `V2_AGENT_LOOP.md`
  (procedure), `V2_PROGRESS.md` (this file),
  `bench/evm-btor2/SCOPE.md` (benchmark scope). Everything else
  is inherited from `main`.
- **Next iteration's planned work**: P0 — scaffold the
  `gurdy/pairs/evm_btor2/` package and `bench/evm-btor2/`
  directory shape per `V2_BOOTSTRAP.md` §5. Copy `gurdy/core/`
  primitives from `v2-bootstrap` where they conform.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).
