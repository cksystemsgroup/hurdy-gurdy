# `ebpf-btor2` Progress — Live State

> The single source of truth for "where is the `ebpf-btor2` bootstrap
> right now." Each iteration appends one entry at the top.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-05-29T10:00:00Z — P10 DIV/OR/AND/MOD K corpus tasks

- **Phase**: P10 complete. Immediate-operand arithmetic opcodes exercised end-to-end.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: expanded `CORPUS` from 11 to 16 tasks.
    New bytecode fixtures `_R0_DIV8_EXIT`, `_R0_OR_0X80_EXIT`,
    `_R0_AND_0XF_EXIT`, `_R0_MOD3_EXIT`. Tasks added:
    - `seed/r0_div8_exit_r0_eq_3`: `r0 /= 8; EXIT`. Witness: r0=24 →
      24//8=3. Property `r0 == 3` → `reachable`. First DIV K task.
    - `seed/r0_or_0x80_exit_r0_eq_128`: `r0 |= 0x80; EXIT`. Witness:
      r0=0 → 0|0x80=128. Property `r0 == 128` → `reachable`.
    - `seed/r0_or_0x80_exit_r0_eq_0_unreachable`: OR K always sets bit 7;
      result ≥ 128, so `r0 == 0` → `unreachable`.
    - `seed/r0_and_0xf_exit_r0_eq_15`: `r0 &= 0xf; EXIT`. Witness:
      r0=15 → 15&0xf=15. Property `r0 == 15` → `reachable`.
    - `seed/r0_mod3_exit_r0_eq_2`: `r0 %= 3; EXIT`. Witness: r0=2 →
      2%3=2. Property `r0 == 2` → `reachable`.
    Harness run: **16 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 9 new tests (net, including
    updated count assertion).
    - `TestHarness`: updated count assertion to 16; extended task-IDs.
    - `TestP10Corpus` (8 tests): DIV K r0==3 reachable, r0==0 reachable;
      OR K r0==128 reachable, r0==0 unreachable; AND K r0==15 reachable,
      r0==16 unreachable; MOD K r0==2 reachable, r0==3 unreachable.
    Full suite: **44 passed / 0 failed**.
- **Next iteration's planned work**: P11 — LSH/RSH/ARSH K/X corpus tasks.
  Add 4–6 tasks exercising shift operations: `r0 <<= 2` (LSH K,
  opcode=0x67), `r0 >>= 1` (RSH K, opcode=0x77), `r0 s>>= 1` (ARSH K,
  opcode=0xc7). Interesting cases: LSH overflow (shift beyond 63),
  ARSH on negative value (sign extension), RSH unsigned. Then optionally
  LSH X / RSH X using register shift amounts.
- **Open BLOCKERs**: none.

---

## 2026-05-29T09:00:00Z — P9 multi-register ALU corpus tasks

- **Phase**: P9 complete. Multi-register ALU64_X operations exercised end-to-end.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: expanded `CORPUS` from 8 to 11 tasks.
    New bytecode fixtures `_R1_ADD1_R0_ADD_R1_EXIT`, `_R2_MUL_R3_EXIT`,
    `_R0_SUB_SELF_EXIT`. Tasks added:
    - `seed/r1_add1_r0_add_r1_exit_r0_eq_1`: `r1 += 1; r0 += r1; EXIT`.
      Exercises `src_reg` field (ADD X with dst=r0, src=r1) and two
      distinct register state variables. Witness: initial r0=0, r1=0 →
      r1=1, r0=1 at EXIT. Property `r0 == 1` → `reachable`.
    - `seed/r2_mul_r3_exit_r2_eq_6`: `r2 *= r3; EXIT`.
      MUL X between two free (symbolic) registers. Witness: r2=2, r3=3 →
      r2=6. Property `r2 == 6` → `reachable`.
    - `seed/r0_sub_self_exit_r0_eq_1_unreachable`: `r0 -= r0; EXIT`.
      SUB X self always zeroes r0; r0==1 can never fire. Property
      `r0 == 1` → `unreachable`.
    Harness run: **11 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 7 new tests (net, including
    updated count assertion).
    - `TestHarness`: updated count assertion to 11; extended task-IDs list.
    - `TestP9Corpus` (6 tests): multi-register ADD chain r0==1 reachable,
      r1==1 reachable; MUL X r2==6 reachable, r2==0 reachable; SUB X
      self-zero r0==0 reachable, r0==1 unreachable.
    Full suite: **36 passed / 0 failed**.
- **Next iteration's planned work**: P10 — DIV/MOD/AND/OR ALU64 opcodes.
  Extend corpus with `BPF_DIV` (0x3f K, 0x37 X), `BPF_MOD` (0x9f K,
  0x97 X), `BPF_AND` (0x5f K/X), `BPF_OR` (0x4f K/X). Add 4–6 tasks:
  `r0 /= 2` (initial r0=8 → r0=4), `r0 %= 3` (initial r0=7 → r0=1),
  `r0 &= 0xf` (mask), `r0 |= 0x80` (set bit). Verify translator
  already handles these via the existing `_alu_op` dispatch, and add
  corpus entries to confirm end-to-end correctness.
- **Open BLOCKERs**: none.

---

## 2026-05-29T08:00:00Z — P8 JMP corpus tasks

- **Phase**: P8 complete. Branch dispatch layer exercised under BMC.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: expanded `CORPUS` from 5 to 8 tasks.
    New bytecode fixtures `_JA_SELF_LOOP`, `_ADD_JEQ_SKIP_EXIT`,
    `_JEQ_TAKEN_SKIP_ADD`. Tasks added:
    - `seed/ja_self_loop_unreachable`: `JA -1` (off=-1, target=self).
      Infinite loop; EXIT never reached within any finite BMC bound.
      Property `exit_reached` → `unreachable`. First task that verifies
      non-termination detection.
    - `seed/add_jeq_skip_exit_r0_eq_2`: `r0 += 1; JEQ r0, 99, +1; EXIT`.
      JEQ not-taken path (2 ≠ 99). Witness: initial r0=1 → r0=2 at
      EXIT. Property `r0 == 2` → `reachable`.
    - `seed/jeq_taken_skip_add_r0_eq_0`: `JEQ r0, 0, +1; r0 += 1; EXIT`.
      JEQ taken (r0==0) skips the add. Witness: initial r0=0 → r0=0 at
      EXIT. Property `r0 == 0` → `reachable`.
    Harness run: **8 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 8 new tests (net, including
    updated count assertion).
    - `TestHarness`: updated `test_corpus_has_five_tasks` →
      `test_corpus_has_eight_tasks`; extended `test_corpus_task_ids`.
    - `TestP8Corpus` (6 tests): JA self-loop unreachable, JA+false
      unreachable, JEQ not-taken `r0==2` reachable, JEQ not-taken
      `r0==99` unreachable (JEQ taken → OOB, EXIT unreachable with r0=99),
      JEQ taken `r0==0` reachable, JEQ not-taken fallthrough `r0==2`
      reachable.
    Full suite: **192 passed / 0 failed** (186 pre-existing + 6 new).
- **Next iteration's planned work**: P9 — ALU32 opcode addition or
  multi-register corpus tasks. Extend the source interpreter and
  translator to handle `BPF_ALU32` (32-bit arithmetic, opcode class
  0x04) for the ADD/SUB/MOD/AND/OR/XOR subset. Alternatively: add
  2–3 corpus tasks using `r1`/`r2` registers to confirm that multi-
  register operations are correct end-to-end: (1) `r0 = r1 + r2` style
  (needs MOV or load, out of scope for P1); (2) `r1 += 1; r0 += r1;
  EXIT`, property `r0 == 2` (initial r0=1, r1=0 → r1=1, r0=1+1=2);
  simpler: just add corpus tasks using the existing ALU64_X (register
  source) opcodes with different register pairs. This extends coverage
  of the `src_reg` field decoding and the `reg_rN` state transitions.
- **Open BLOCKERs**: none.

---

## 2026-05-29T07:00:00Z — P7 seed corpus expansion

- **Phase**: P7 complete. Seed corpus expanded to 5 tasks.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: expanded `CORPUS` from 1 to 5 tasks.
    Added internal `_spec()` helper to reduce boilerplate. New bytecode
    fixtures `_R0_XOR_SELF_EXIT` and `_R0_ADD1_ADD1_EXIT`. Removed
    unused `RegisterBound` import. Tasks added:
    - `seed/exit_only_exit_reached`: EXIT-only, `exit_reached` →
      `reachable`. Simplest possible halting program.
    - `seed/r0_xor_self_exit_r0_eq_0`: `r0 ^= r0; EXIT`, property
      `r0 == 0` → `reachable`. XOR-self unconditionally zeroes r0
      regardless of initial value; property always fires.
    - `seed/r0_xor_self_exit_r0_eq_1_unreachable`: same bytecode,
      property `r0 == 1` → `unreachable`. First task that exercises
      the UNSAT path; the solver confirms no trace can satisfy r0==1
      after XOR-self.
    - `seed/r0_add1_add1_exit`: `r0 += 1; r0 += 1; EXIT`, property
      `r0 == 2` → `reachable`. Witness: initial r0=0 → r0=2 at halt.
    Harness run: **5 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 8 new tests (net).
    - `TestHarness`: replaced `test_corpus_nonempty` with
      `test_corpus_has_five_tasks`, `test_corpus_task_ids` (checks all
      5 task IDs present), and `test_all_corpus_tasks_pass_or_skip`.
    - `TestP7Corpus`: 6 direct `check()` tests:
      `exit_only exit_reached`, `xor_self r0==0`, `xor_self r0==1`
      (unreachable), `double_add r0==2`, `double_add r0==0`
      (wraps at 2^64−2 + 2 = 0 mod 2^64, reachable),
      `xor_then_add r0==1` (r0 forced to 0 by XOR then +1 = 1).
    Full suite: **186 passed / 0 failed** (178 pre-existing + 8 new).
- **Next iteration's planned work**: P8 — branch coverage in corpus.
  Add 3–4 corpus tasks exercising the JMP layer: (1) JEQ taken path
  (`r0 += 42; JEQ r0, 42, +N; EXIT_at_target`, property
  `exit_reached` at the target instruction — but this requires
  distinguishing which EXIT fires, which the current schema doesn't
  support directly); simpler: (2) unconditional JA loop-back
  (self-loop, never halts → property `exit_reached` → unreachable);
  (3) JGT taken / not-taken pair. Also consider adding `bound=1` to
  a task to confirm early-termination → unknown (or unreachable within
  1 step). These tasks will confirm the JMP dispatch layer under BMC.
- **Open BLOCKERs**: none.

---

## 2026-05-29T06:00:00Z — P6 dispatch and solver adapter

- **Phase**: P6 complete. Dispatch and solver adapter for ebpf-btor2.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/solvers/z3bmc.py`: full P6 implementation.
    `Z3BMCSolver(InProcessSolverBackend)` with `name="z3-bmc"`.
    `dispatch(artifact_bytes, directive)`:
      - Attempts `import z3`; returns `error` verdict with reason if
        not installed.
      - Parses the flattened BTOR2 text via
        `riscv_btor2.btor2.parser.from_text`; returns `error` on
        parse failure.
      - Compiles to `Compiled` via `compile_btor2` (riscv_btor2 backend
        reused verbatim per V2_BOOTSTRAP.md §3.2).
      - Runs `bmc(comp, bound)` from `btor2_to_z3`; maps
        `NotImplementedError` (unsupported op) to `unknown` verdict.
      - Returns `RawSolverResult` with `payload={"witness_text": ...}`
        when `reachable`.
  - `gurdy/pairs/ebpf_btor2/solvers/__init__.py`: updated from stub to
    export `check(spec, bytecode) -> RawSolverResult` and `Z3BMCSolver`.
    - `check`: translates `bytecode` under `spec`, resolves BMC bound
      (`spec.analysis.bound` if set, else `spec.scope.max_insns`), then
      dispatches to `Z3BMCSolver`.
  - `bench/ebpf-btor2/harness.py`: implemented (was `raise
    NotImplementedError`). Defines `CorpusTask`, `CORPUS` (1 seed task),
    `run_task`, `run_corpus`. Maps `reachable`/`unreachable` to
    PASS/FAIL and `unknown`/`error` to SKIP. CLI: `--list` enumerates
    task IDs; default runs all tasks and exits 0 iff no FAIL.
    Seed task: `r0 += 1; EXIT` with property `r0 == 1`. Registers the
    initial r0 as unconstrained; the z3 solver finds initial r0=0 as
    witness, property fires at halt → `reachable` → PASS.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 16 unit tests.
    - `TestZ3BMCSolverDispatch`: name check, bad-BTOR2 error, `false`
      property is `unreachable`, `r0 == 1` property is `reachable` after
      ADD, witness payload present, result type and engine.
    - `TestCheck`: seed task `reachable`, `false` → `unreachable`,
      `exit_reached` → `reachable`, explicit bound respected, bound
      falls back to `max_insns`, result type, JA+EXIT `exit_reached`
      → `reachable`.
    - `TestHarness`: `run_task` on seed returns PASS, CORPUS non-empty,
      `run_corpus` returns 0.
    Uses `importlib.util.spec_from_file_location` (registered in
    `sys.modules`) to avoid name collision with riscv-btor2 harness.
    Also installed z3-solver into the pytest venv so tests are not
    skipped.
    Full suite: **178 passed / 0 failed** (162 pre-existing + 16 new).
- **Next iteration's planned work**: P7 — seed corpus expansion.
  Extend `CORPUS` in the harness to 5–6 hand-crafted ALU-only tasks
  covering: EXIT-only (`exit_reached` → `reachable`), self-XOR zeroes
  (`r0 ^= r0; EXIT`, property `r0 == 0`), double-add (`r0 += 1; r0 +=
  1; EXIT`, property `r0 == 2`), a structural `false` property
  (`unreachable`), and a branch-not-taken task (`r0 += 1; JEQ r0, 42,
  +1; EXIT`, property `r0 != 42`). Note: `RegisterBound` constraints
  currently apply at every step (BTOR2 `constraint` semantics), not
  just init; initial-register clamping for BMC witness counting should
  be deferred to P8 (schema bump with `init`-layer overrides).
- **Open BLOCKERs**: none.

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
