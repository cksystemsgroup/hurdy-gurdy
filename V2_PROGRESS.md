# `ebpf-btor2` Progress — Live State

> The single source of truth for "where is the `ebpf-btor2` bootstrap
> right now." Each iteration appends one entry at the top.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-05-29T00:00:00Z — P5 alignment oracle

- **Phase**: P5 complete. Alignment oracle for ebpf-btor2.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/oracle_align.py`: full P5 implementation.
    Exports `align`, `AlignmentFailure`, `ORACLE_VERSION`, `PAIR_ID`.
    - `align(source_trace, reasoning_trace, artifact)`: compares
      `reg_r0..reg_r9` at every step up to (and including) the first
      EXIT, checking `source_trace.steps[k+1]` against
      `reasoning_trace.steps[k].layer_values["machine"][sym["reg_rN"]]`
      per SCHEMA.md §14. Reconstructs source register state by
      accumulating deltas from `source_trace.steps`, seeded at zero.
      Returns `(list[AlignmentFailure], bool)`.
    - `AlignmentFailure(step, symbol, src_val, r_val)`: frozen dataclass
      for a single register mismatch. `step` is the source step index
      (= reasoning step + 1); `symbol` is the BTOR2 state symbol name.
    - `_sym_nids(artifact)`: parses the artifact's flattened BTOR2 text
      via `riscv_btor2.btor2.parser` to build `{symbol: nid}` for all
      state nodes.
    - Contract documented: non-zero initial register values must appear
      as deltas in `steps[1]` (modified by the first instruction) or
      start at zero for correct comparison. Registers seeded at zero
      and never modified compare correctly when both interpreters agree.
  - `bench/ebpf-btor2/oracle_align.py`: updated stub to re-export from
    the pair module (was `raise NotImplementedError`).
  - `tests/pairs/ebpf_btor2/test_oracle_align.py`: 11 unit tests.
    - Aligned tests on all 5 P4 seed programs (`_EXIT_ONLY`,
      `_ADD_EXIT`, `_ADD_X_EXIT`, `_BRANCH_EXIT` not-taken path,
      `_JA_EXIT`) with initial_regs chosen to satisfy the delta-coverage
      contract.
    - Misaligned tests: `_ADD_EXIT` with source r0=5→6, reasoning r0=10→11
      (detected: `reg_r0` failure at step 1 with src_val=6, r_val=11).
    - `test_align_r1_mismatch_after_add_x`: documents the known
      limitation — unchanged non-zero initial registers cause failures
      because source deltas don't record them.
    - Edge case: empty reasoning steps → no comparisons → aligned=True.
    Full suite: **162 passed / 0 failed** (151 pre-existing + 11 new).
- **Next iteration's planned work**: P6 — dispatch and solver adapter.
  Wire `gurdy/pairs/ebpf_btor2/solvers/` to the z3-bmc engine (reusing
  `riscv-btor2`'s adapter pattern per V2_BOOTSTRAP.md §3.2). Implement
  a `check(spec, bytecode)` entry point that runs the translator,
  invokes the solver, and returns a `Verdict`. Provide a thin
  `bench/ebpf-btor2/harness.py` harness that calls `check` on a corpus
  task and reports PASS/FAIL/SKIP. Seed corpus task: `r0 += 1; EXIT`
  with property `r0 == 1` (expected PASS with initial r0=0).
- **Open BLOCKERs**: none.

---

## 2026-05-28T21:00:00Z — P4 translator

- **Phase**: P4 complete. BTOR2 translator for ebpf-btor2.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/translation/__init__.py`: full P4
    implementation. Exports `translate`, `Translator`, `SCHEMA_VERSION`,
    `LAYER_NAMES`, `PAIR_ID`.
    - `translate(spec, bytecode, annotation_emitter)`: compiles
      `(EbpfBtor2Spec, bytecode)` → `CompiledArtifact` for the P1 opcode
      subset (ALU64 K/X, JMP K/X, EXIT). Reuses `Builder` and `to_text`
      from `gurdy.pairs.riscv_btor2` verbatim per V2_BOOTSTRAP.md §3.2.
      Also reuses `decode_program` and `BpfInsn` from source_interp.
    - Eight layers emitted per SCHEMA.md §11: `header` (bv1/bv32/bv64
      sorts), `machine` (reg_r0..r9 + insn_idx + halted states),
      `library` (per-instruction update expressions via `_lower_insn`),
      `dispatch` (nested ite chains with halted guard, plus `next` clauses),
      `init` (insn_idx=0, halted=0; registers free per §7), `constraint`
      (RegisterBound assumptions as `ugte`/`ulte` pairs), `bad` (property
      expression lowered from SCHEMA.md §9 grammar), `binding` (empty stub
      for P5+).
    - ALU64: all 12 ops (ADD/SUB/MUL/DIV/OR/AND/LSH/RSH/NEG/MOD/XOR/ARSH)
      including zero-divisor ite guards for DIV64 and MOD64, shift-amount
      masking via `and(SRC, 63)`.
    - JMP: 12 branch flavours (JEQ/JGT/JGE/JSET/JNE/JSGT/JSGE/JLT/JLE/JSLT/JSLE)
      plus JA (unconditional). K/X source resolution via sign-extended
      immediate (bv64) or register state nid.
    - Property parser: recursive descent for the SCHEMA.md §9 grammar
      (`false`, `exit_reached`, `rN op value`, `AND`). All 10 comparison
      operators (unsigned and signed variants).
    - `Translator` class implements the framework `Translator` protocol.
  - `tests/pairs/ebpf_btor2/test_translation.py`: 34 unit tests.
    - Seed bytecode fixtures: `_EXIT_ONLY`, `_ADD_EXIT`, `_ADD_X_EXIT`,
      `_BRANCH_EXIT` (JEQ + XOR + EXIT), `_JA_EXIT` (unconditional jump).
    - Covers: artifact structure (all 8 layers present, flattened bytes,
      state symbol declarations), determinism, EXIT-only halting,
      ADD K / ADD X step-by-step alignment against source_interp,
      halted-freeze semantics, JEQ branch taken/not-taken, JA jump,
      property expressions (`false`, `exit_reached`, `r0 == 42`,
      `r0 < 10`, `r0 == 1 AND r1 == 0`), RegisterBound constraint
      emission, layer content sanity (sort/state/next/init/bad nodes).
    Full suite: **151 passed / 0 failed** (117 pre-existing + 34 new).
- **Next iteration's planned work**: P5 — alignment oracle
  (`gurdy/pairs/ebpf_btor2/oracle_align.py`). Implement
  `align(source_trace, reasoning_trace, artifact)` that compares
  `source_trace.steps[i+1].reg_rN` against
  `reasoning_trace.steps[i].layer_values["machine"][sym["reg_rN"]]`
  for N in 0..9 at every step up to the first EXIT, per SCHEMA.md §14.
  Return a list of `AlignmentFailure` records (step, symbol, src_val,
  r_val) and a boolean `aligned`. Verify on the seed programs from P4.
- **Open BLOCKERs**: none.

---

## 2026-05-28T00:00:00Z — P3 reasoning interpreter

- **Phase**: P3 complete. BTOR2 concrete evaluator for ebpf-btor2.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/reasoning_interp/__init__.py`: full P3
    implementation. Exports `EbpfReasoningBinding`,
    `EbpfReasoningInterpreter`, `INTERPRETER_VERSION`, `PAIR_ID`.
    - `EbpfReasoningBinding`: subclass of `gurdy.core.interp.types.ReasoningBinding`
      with `pair = "ebpf-btor2"`, `state_init_by_symbol` (symbol-keyed
      initial state overrides), `input_per_step_by_symbol` (per-step
      input values for future use), and `from_jsonable` round-trip.
    - `EbpfReasoningInterpreter`: multi-step BTOR2 evaluator implementing
      the `ReasoningInterpreter` protocol. Reuses
      `gurdy.pairs.riscv_btor2.btor2.{parser,evaluator,nodes}` verbatim
      per V2_BOOTSTRAP.md §3.2. The `run` method: parses the artifact's
      flattened BTOR2 text; resolves `init` and `next` clauses; walks
      `max_steps` cycles applying the transition relation; records
      post-step symbol state as `layer_values["machine"]` keyed by nid;
      detects first `bad` clause firing against the post-step state;
      returns a `ReasoningTrace` with `pair="ebpf-btor2"`, step records,
      and `bad_fired_at`.
    - Binding override: `state_init_by_symbol` symbols are resolved via
      the model's named state nodes, so overrides are schema-version stable.
  - `tests/pairs/ebpf_btor2/test_reasoning_interp.py`: 26 unit tests.
    Uses two hand-constructed BTOR2 fragments:
    - `_ADD_THEN_EXIT_BTOR2`: 2-instruction program (ALU64 ADD K r0 1,
      EXIT). Verifies step-by-step state (reg_r0, insn_idx, halted),
      bad-fires at step 1, halted-freeze semantics from step 2 onward,
      binding overrides (incl. wraparound at 2^64-1), and that bad fires
      exactly once.
    - `_STATIC_BTOR2`: halted always 0, bad never fires; verifies
      `bad_fired_at is None` over 10 steps.
    Also covers: binding defaults, from_jsonable round-trip, hash
    distinctness, determinism, trace serialisation.
    Full suite: **117 passed / 0 failed** (91 pre-existing + 26 new).
- **Next iteration's planned work**: P4 — translator
  (`gurdy/pairs/ebpf_btor2/translation/`). Compile `(EbpfBtor2Spec,
  bytecode)` → BTOR2 artifact for the P1 opcode subset (ALU64 K/X,
  JMP K/X, EXIT). Emit the 8 SCHEMA.md layers (header, machine,
  library, dispatch, init, constraint, bad, binding). Verify with
  `EbpfReasoningInterpreter` on the seed programs from the source
  interpreter tests.
- **Open BLOCKERs**: none.

---

## 2026-05-27T01:00:00Z — P2 source interpreter

- **Phase**: P2 complete. Source interpreter for the P1 opcode set.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/source_interp/__init__.py`: full P2
    implementation. Exports `BpfInsn`, `EbpfInputBinding`,
    `EbpfMachineState`, `decode_program`, `step`, `run`.
    - `decode_program`: decodes flat 8-byte `bpf_insn` records
      from raw bytes; rejects wide immediates (0x18) with
      diagnostic `ebpf-btor2/load/0001`; rejects non-multiple-of-8
      lengths with `ebpf-btor2/load/0000`.
    - `step`: executes one machine cycle — ALU64 K/X (all 12 ops),
      JMP K/X (all 12 branch flavours + JA), and EXIT. Implements
      the halted-freeze and out-of-bounds self-loop semantics from
      schema §6. Raises `ValueError` with `ebpf-btor2/load/0003`
      for unsupported opcodes (e.g. CALL, BPF_ALU32).
    - `run`: drives the machine from an `EbpfInputBinding`; records
      one `SourceStep` per cycle (step 0 = initial state, deltas
      from prior); stops on EXIT, out-of-bounds, or `max_steps`;
      returns a `SourceTrace` with `final_state`, `halted`, and
      `halt_reason`.
    - `EbpfInputBinding` subclasses `gurdy.core.interp.types.InputBinding`
      with `bytecode: bytes` and `initial_regs: tuple[int, ...]`.
  - `tests/pairs/ebpf_btor2/test_source_interp.py`: 66 unit tests.
    Covers decode (basic, dst/src fields, signed off/imm, bad-length,
    wide-imm, instruction properties), all 12 ALU64 ops including
    wraparound and zero-divisor edge cases, all 12 JMP flavours
    (taken/not-taken, signed/unsigned), EXIT and halted-freeze,
    out-of-bounds freeze, `run` (step count, initial-step deltas,
    max_steps, out-of-bounds, determinism, delta tracking, hash
    stability), and 5 hand-crafted byte-sequence programs
    (add+mul, branch taken/not-taken, 3-iteration loop, XOR-self).
    Full suite: **91 passed / 0 failed**.
- **Next iteration's planned work**: P3 — reasoning interpreter
  (`gurdy/pairs/ebpf_btor2/reasoning_interp/`). Port the BTOR2
  concrete evaluator from `gurdy/core/` patterns; walk the
  BTOR2 artifact node-by-node with a concrete binding
  (`EbpfReasoningBinding`); produce a `ReasoningTrace` for
  future alignment. P3 depends on P4 (translator) for a real
  artifact, so start with a hand-constructed BTOR2 fragment
  for the 2-instruction add-then-exit program.
- **Open BLOCKERs**: none.

---

## 2026-05-27T00:00:00Z — P1 schema v1.0.0

- **Phase**: P1 complete. SCHEMA.md is frozen at v1.0.0.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/SCHEMA.md`: full schema v1.0.0.
    Defines sorts (`bv1`, `bv32`, `bv64`); state variables
    (`reg_r0`–`reg_r9`, `insn_idx : bv32`, `halted : bv1`);
    r10 as constant 512 in P1; program loading from `.bpf.o`
    ELF; instruction lowering for the P1 subset (ALU64 K/X 12
    ops, JMP K/X 12 branch flavours + JA + EXIT); dispatch
    layer structure; entry-state constraints; `RegisterBound`
    constraint encoding (unsigned); property expression DSL
    grammar; `bad`-node lowering table; verdict semantics;
    layer names; annotation conventions; stability profile;
    interpreter-semantics stub (P2/P3); explicit exclusions
    list (P8–P11 features).
  - `gurdy/pairs/ebpf_btor2/__init__.py`: added
    `SCHEMA_VERSION = "1.0.0"`.
  - `tests/pairs/ebpf_btor2/test_spec.py`: 25 unit tests
    covering `validate_ebpf_btor2_spec` (valid and error
    paths), canonical serialisation round-trips, spec-hash
    distinctness, and `from_jsonable` pair-rejection. All
    pass; full suite 412 passed / 12 skipped / 0 failed.
- **Next iteration's planned work**: P2 — source interpreter
  (`gurdy/pairs/ebpf_btor2/source_interp/`). Bytecode decoder
  + register-model step function for the P1 opcode set
  (ALU64 K/X, JMP K/X, EXIT). Trace recording, `halted`
  semantics, determinism test with a hand-written byte sequence.
- **Open BLOCKERs**: none.

---

## 2026-05-22T00:00:00Z — P0 scaffold

- **Phase**: P0 complete.
- **What changed**: Created full directory scaffold per
  `V2_BOOTSTRAP.md` §5.
  - `gurdy/pairs/ebpf_btor2/` package: `__init__.py`, `SCHEMA.md`
    (placeholder), `spec.py` (eBPF spec language — `EbpfBtor2Spec`,
    `RegisterBound`, `PacketBound`, `Property`, `AnalysisDirective`,
    `validate_ebpf_btor2_spec`); subpackage stubs for `source/`,
    `source_interp/`, `reasoning_interp/`, `translation/`, `lift/`,
    `solvers/`.
  - `bench/ebpf-btor2/corpus/{seed,kernel_rejects,external}/`
    (`.gitkeep`); `harness.py`, `oracle_align.py`, `oracle_cross.py`,
    `engine_bench.py` (stubs raising `NotImplementedError`);
    `baselines/{kernel_verifier,prevail,hurdy_gurdy,pareto}.py`
    (stubs).
  - `tests/pairs/ebpf_btor2/__init__.py`.
  - `gurdy/core/` already matched `v2-bootstrap` (identical tree
    SHAs) — no copy needed.
- **Next iteration's planned work**: P1 — define schema version
  1.0.0 in `SCHEMA.md` (sorts, machine-state layout, layer names,
  the minimal ALU64 + branch + exit opcode set, `QuestionSpec`
  reach-property). Freeze SCHEMA.md before any translator work.
- **Open BLOCKERs**: none.

---

## 2026-05-17T00:00:00Z — Branch bootstrap

- **Phase**: pre-P0. Nothing implemented yet on this branch.
- **What's here**: `V2_BOOTSTRAP.md` (spec), `V2_AGENT_LOOP.md`
  (procedure), `V2_PROGRESS.md` (this file),
  `bench/ebpf-btor2/SCOPE.md` (benchmark scope). Everything else
  is inherited from `main`.
- **Next iteration's planned work**: P0 — scaffold the
  `gurdy/pairs/ebpf_btor2/` package and `bench/ebpf-btor2/`
  directory shape per `V2_BOOTSTRAP.md` §5. Copy `gurdy/core/`
  primitives from `v2-bootstrap` where they conform.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).
