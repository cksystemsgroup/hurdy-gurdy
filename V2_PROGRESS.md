# `ebpf-btor2` Progress — Live State

> The single source of truth for "where is the `ebpf-btor2` bootstrap
> right now." Each iteration appends one entry at the top.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

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
