# `evm-btor2` Progress — Live State

> The single source of truth for "where is the `evm-btor2` bootstrap
> right now." Each iteration appends one entry at the top. Older
> entries stay for history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

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
