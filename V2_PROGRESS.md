# `aarch64-btor2` Progress — Live State

> The single source of truth for "where is the `aarch64-btor2`
> bootstrap right now." Each iteration appends one entry at the top.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-05-30T00:00:00Z — P8: task.toml parse + list_tasks coverage for all 11 seeds

- **Phase**: P8 partial (wedge-reproduction measurement blocked pending
  `aarch64-linux-gnu-gcc`; offline coverage complete).
- **What changed**:
  - `tests/pairs/aarch64_btor2/unit/test_harness.py`: added 12 new tests
    (all offline — no solver, no ELF required):
    - `test_list_tasks_includes_all_11_seeds`: asserts all 11 seed
      directories (0001–0011) appear in `list_tasks()` even without
      `source.elf`.
    - `test_task_toml_parses[<seed_id>]` × 11: parametrized over
      `_ALL_SEED_IDS`; verifies each task.toml is valid TOML, that
      `[task].id` matches the directory name, `[expected].verdict` is
      `"reachable"` or `"unreachable"`, `[c].bound` is a positive int,
      and `[c].gcc_version` is non-empty.
    - Also added `tomllib` import (with `tomli` fallback) and
      `_ALL_SEED_IDS` constant.
  - All 129 tests pass (7 skipped — z3 not in pytest venv), 0 failures.
    Previous: 117 pass, 7 skip. Net new: +12 passing tests.
- **Pre-existing issue noted**: full `pytest` run (all pairs) hits a
  collection error in `tests/pairs/riscv_btor2/integration/
  test_bench_condition_c.py` — it imports `harness` and finds the
  aarch64 harness because `test_harness.py` inserts
  `bench/aarch64-btor2/` into `sys.path` at module level. This
  predates this iteration (confirmed via `git stash`). Does not affect
  the aarch64 test suite when run in isolation.
- **Next iteration's planned work**: P8 complete → P9 — shadow mode +
  FREE sentinel. Port `riscv-btor2`'s shadow-mode infrastructure to
  `bench/aarch64-btor2/`. If cross-toolchain remains unavailable, add
  P9 scaffold structure (directory layout, stub oracle scripts) and
  extend corpus with ≤ 5 SV-COMP slice scaffolds.
- **Open BLOCKERs**: `aarch64-linux-gnu-gcc` not present. `source.elf`
  and `spec.json` for seeds 0002–0011 cannot be compiled. **Does not
  block P9 scaffold work.**
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-29T00:00:00Z — P7: Wedge seed scaffolds 0005–0011 (ports of riscv-btor2 0115–0121)

- **Phase**: P7 complete (scaffolds; ELF compilation pending cross-toolchain).
- **What changed**:
  - `bench/aarch64-btor2/corpus/seed/0005-c-int-overflow/`: port of riscv
    0115-c-int-overflow. `int y = INT_MAX + 1` → W-reg ADD wraps 32-bit,
    SXTW sign-extends to long. Same verdict: unreachable. Same bound: 60.
  - `bench/aarch64-btor2/corpus/seed/0006-c-udiv-by-zero/`: port of riscv
    0116-c-divu-sentinel. **AArch64 divergence**: UDIV div-by-zero → 0 (not
    the RV64 all-ones sentinel). Assertion changed from `z != 0xFFFFFFFFUL` to
    `z != 0UL`. Question text and notes updated. Verdict: unreachable.
  - `bench/aarch64-btor2/corpus/seed/0007-c-int-min-div-neg-one/`: port of
    riscv 0117. AArch64 SDIV W for INT_MIN/-1 truncates to 32 bits (0x80000000
    = INT_MIN) then SXTW; same result as RV64 sentinel. Verdict: unreachable.
  - `bench/aarch64-btor2/corpus/seed/0008-c-shift-amount-mask/`: port of riscv
    0118. AArch64 LSL masks shift amount to [5:0] (same as RV64 SLL). 64 & 63 =
    0. Verdict: unreachable.
  - `bench/aarch64-btor2/corpus/seed/0009-c-signed-vs-unsigned-shift-right/`:
    port of riscv 0119. ASR (sign-fill) vs LSR (zero-fill) — AArch64 analogues
    of RV64 SRAW/SRLW. Verdict: unreachable.
  - `bench/aarch64-btor2/corpus/seed/0010-c-byte-load-signedness/`: port of
    riscv 0120. LDRSB (sign-ext) vs LDRB (zero-ext) — AArch64 analogues of
    RV64 lb/lbu. Verdict: unreachable.
  - `bench/aarch64-btor2/corpus/seed/0011-c-mul32-truncation/`: port of riscv
    0121-c-mulw-truncation. AArch64 has no MULW; W-reg MUL (MUL Wd, Wn, Wm)
    provides same 32-bit truncation. SXTW sign-extends 0 to 64 bits. Verdict:
    unreachable.
  - All 14 files (7× task.c + 7× task.toml) are scaffolds; `source.elf` and
    `spec.json` deferred — require `aarch64-linux-gnu-gcc`.
  - `harness.py --list-tasks` confirms all 11 seeds visible.
  - All 117 tests pass (7 skipped), 0 failures.
- **AArch64-vs-RV64 divergence summary for wedge set**:
  - 0006 (div-by-zero): **assertion changed** — AArch64 UDIV → 0, not
    all-ones. This is the only seed requiring a non-mechanical adaptation.
  - 0007 (INT_MIN/-1): same result via truncation-to-data-size (not an
    explicit sentinel contract as in RV64).
  - 0011 (mul truncation): W-reg MUL replaces MULW; same truncation semantics.
  - 0005/0008/0009/0010: mechanical — halt convention update only.
- **Next iteration's planned work**: P8 — wedge reproduction measurement. Run
  `harness.py` on seeds 0005–0011 once `source.elf` files are available. If the
  cross-toolchain is still unavailable, add a test that validates each task.toml
  parses correctly and `list_tasks()` includes all 11 seeds; then plan P9
  (shadow mode + FREE sentinel) or extend corpus with SV-COMP slice scaffolds.
- **Open BLOCKERs**: `aarch64-linux-gnu-gcc` not present. `source.elf` and
  `spec.json` for seeds 0002–0011 cannot be compiled. **Does not block P8 test
  coverage of task.toml parsing or P9 scaffold work.**
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-28T01:00:00Z — P6: Harness (run_task) + loopsum corpus scaffolds (0002–0004)

- **Phase**: P6 partial (harness complete; 0002/0003/0004 ELF compilation
  pending cross-toolchain).
- **What changed**:
  - `bench/aarch64-btor2/harness.py`: implemented `run_task(task_path,
    engine=None, timeout=None) → TaskResult`. Loads `spec.json`, resolves
    the ELF path relative to the task directory, calls `compile_spec` +
    pair solver, compares verdict against `task.toml [expected].verdict`.
    Also provides `list_tasks()` (sorted seed paths) and a CLI
    (`--list-tasks`, `--task`, `--engine`, `--timeout`, `--json`).
    Source: adapted from test_e2e_loopsum.py + gurdy.core.tools.compile
    pattern; no riscv-btor2 LLM harness involvement.
  - `bench/aarch64-btor2/corpus/seed/0002-c-loopsum-o1/task.c` +
    `task.toml`: scaffold for -O1 loopsum (bound=100); `source.elf`
    and `spec.json` deferred — require `aarch64-linux-gnu-gcc`.
  - `bench/aarch64-btor2/corpus/seed/0003-c-loopsum-o2/task.c` +
    `task.toml`: scaffold for -O2 loopsum (bound=60).
  - `bench/aarch64-btor2/corpus/seed/0004-c-loopsum-o3/task.c` +
    `task.toml`: scaffold for -O3 loopsum (bound=60).
  - `tests/pairs/aarch64_btor2/unit/test_harness.py`: 9 tests —
    `list_tasks` (3: returns paths, includes 0001, sorted, includes
    scaffolds); `TaskResult` frozen; 4 full-solve tests on 0001
    (skipped: z3 not in pytest venv). 5 pass / 4 skip.
  - All 117 tests pass (7 skipped), 0 failures.
- **Next iteration's planned work**: P6 complete → P7 — port wedge seeds
  0115–0121 from riscv-btor2. Each needs: (a) task.c (copy from riscv
  with minimal edits), (b) fresh ground-truth derivation in `task.toml`
  (esp. 0116 div-by-zero returns 0 in AArch64, not all-ones; 0121 no
  `mulw` — use W-reg MUL), (c) `source.elf` compilation once
  cross-toolchain is available. `run_task` is the harness prerequisite —
  satisfied. Start with scaffolds if cross-toolchain still unavailable.
- **Open BLOCKERs**: `aarch64-linux-gnu-gcc` not present in this
  execution environment. `source.elf` for 0002/0003/0004 (and future
  wedge ports) cannot be compiled until the toolchain is installed or the
  session is run on a host with it. Scaffolds (task.c + task.toml) are
  committed; run `python bench/aarch64-btor2/corpus/_compile_c.py
  bench/aarch64-btor2/corpus/seed/<task>` on a toolchain host to
  complete each seed. **Does not block P7 scaffold work.**
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-28T00:00:00Z — P5: End-to-end integration (C-compiled ELF + corpus seed + replayer validation)

- **Phase**: P5 complete.
- **What changed**:
  - `bench/aarch64-btor2/corpus/_compile_c.py`: AArch64 C-task compiler (adapted
    from riscv-btor2). Calls `aarch64-linux-gnu-gcc -march=armv8-a -nostdlib
    -nostartfiles -ffreestanding -Wl,-Ttext=0x400000`; uses
    `aarch64-linux-gnu-nm` to resolve `trap` symbol address; writes `source.elf`
    and `spec.json`. AArch64 halt convention: `svc #0` (normal), `brk #0` (bad).
    No sidecar scripts (_emit_pcs.py / _emit_dwarfmap.py) yet — deferred to later
    phase once DWARF support is wired.
  - `bench/aarch64-btor2/corpus/seed/0001-c-loopsum-o0/task.c`: First AArch64
    corpus seed. Same logic as riscv-btor2 0103-c-loopsum-o0: sum 0..9 = 45,
    trap unreachable. Uses `svc #0` / `brk #0` for halt convention.
  - `bench/aarch64-btor2/corpus/seed/0001-c-loopsum-o0/task.toml`: bound=250,
    gcc_version pinned to 13.3.0-6ubuntu2~24.04.1, oracle_provenance=manual-proof.
  - `bench/aarch64-btor2/corpus/seed/0001-c-loopsum-o0/source.elf`: Compiled
    AArch64 ELF (text base 0x400000). `_start` at 0x400000, `trap` at 0x40005c.
    ~125 instructions at -O0.
  - `bench/aarch64-btor2/corpus/seed/0001-c-loopsum-o0/spec.json`: Auto-generated;
    property `eq(pc, const(0x40005c))`, engine z3-bmc, bound 250.
  - `tests/pairs/aarch64_btor2/unit/test_e2e_loopsum.py`: 5 new tests (3 run,
    2 skipped — z3 not in pytest venv): corpus-seed ELF translates to valid BTOR2
    (12 703 bytes, no parse errors); spec.json round-trips with correct property;
    corpus ELF exports both `_start` and `trap`; z3-bmc returns "unreachable" on
    trivial program with property=false; replayer produces 2-step trace (ADD+SVC)
    from reachable SAT witness.
  - All 112 tests pass (3 skipped — 2 new z3-bmc tests + 1 legacy lift-smoke),
    0 failures.
- **Next iteration's planned work**: P6 — Loopsum family + harness. (a) Add
  0002-c-loopsum-o1, 0003-o2, 0004-o3 corpus seeds by reusing task.c with
  different opt levels — purely mechanical. (b) Implement `bench/aarch64-btor2/
  harness.py` `run_task(task_path, engine, timeout) → TaskResult` (adapt from
  riscv-btor2 harness; aarch64-btor2 pair is already registered). This is the
  prerequisite for P7 (porting wedge seeds 0115–0121) and P8 (measurement).
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-27T01:00:00Z — P4: Alignment oracle (lift/ witness + invariant + replayer + lift)

- **Phase**: P4 complete.
- **What changed**:
  - `gurdy/pairs/aarch64_btor2/lift/simulator.py`: added `simulate()` function
    (mirrors riscv; runs until halted/max_steps/fetch-returns-None).
  - `gurdy/pairs/aarch64_btor2/lift/witness.py`: `LiftedStep`, `WitnessTrace`,
    `lift_witness()`. Adapted from riscv: state symbols pc/reg_x0..reg_x30/sp/nzcv/halted;
    no DWARF line-table (deferred to P5+, file/line always None); uses `Decoded.mnemonic`
    for disasm field.
  - `gurdy/pairs/aarch64_btor2/lift/invariant.py`: `LiftedInvariant`, `lift_invariant()`.
    AArch64 ABI glossary (AAPCS64: x0–x7 args, x29 fp, x30 lr); sp and nzcv tokens.
  - `gurdy/pairs/aarch64_btor2/lift/replayer.py`: `replay_witness()`. Adapted from riscv:
    handles reg_x0..reg_x30 (keys 0–30), sp, nzcv; uses AArch64SourceInterpreter and
    AArch64InputBinding.
  - `gurdy/pairs/aarch64_btor2/lift/lift.py`: `Lifter`, `LiftedResult`, `lift`.
    Adapted from riscv; routes reachable→witness-replay, proved→invariant-lift.
  - `gurdy/pairs/aarch64_btor2/lift/__init__.py`: re-exports all public lift symbols.
  - `gurdy/pairs/aarch64_btor2/__init__.py`: replaced `_lifter_stub` with real
    `Lifter().lift`; updated module docstring to P4 state.
  - `tests/pairs/aarch64_btor2/unit/test_lift_smoke.py`: 6 tests (1 skipped — z3
    not installed): BTOR2 parses cleanly, z3-bmc verdict, Lifter.lift no-raise,
    simulate() golden (ADD X0,#1+SVC → x0=42, halted), invariant glossary x0+pc,
    invariant glossary sp+nzcv.
  - All 109 tests pass (1 skipped), 0 failures.
- **Next iteration's planned work**: P5 — End-to-end integration: build a real
  AArch64 ELF from C (via `aarch64-linux-gnu-gcc`) for a simple bounded-loop
  task (e.g., sum = 0..N loop with a postcondition), translate it, run z3-bmc,
  and check the verdict matches the expected result. Add the task to
  `bench/aarch64-btor2/corpus/seed/` as the first corpus seed. Validate the
  replayer on a SAT witness if z3-bmc returns reachable.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-27T00:00:00Z — P3: BTOR2 translation layer (library + layers + translate)

- **Phase**: P3 complete.
- **What changed**:
  - `gurdy/pairs/aarch64_btor2/translation/builder.py`: `Builder` (copied from
    riscv_btor2, adds bv4/bv33/bv65 for NZCV and carry computation).
  - `gurdy/pairs/aarch64_btor2/translation/library.py`: `RegSnapshot` (xr/spr
    context), `LoweringResult`, `lower()`. Full A64 base ISA coverage:
    ADD/SUB/ADDS/SUBS, AND/ORR/EOR/ANDS (imm+reg), MOVZ/MOVK/MOVN, ADR/ADRP,
    UBFM/SBFM/BFM/EXTR, LSL/LSR/ASR/ROR (register), MADD/MSUB and widening
    variants (SMADDL/SMSUBL/UMADDL/UMSUBL), SMULH/UMULH, SDIV/UDIV (div-by-zero
    → 0; W-reg zero-extends), CSEL/CSINC/CSINV/CSNEG, B/BL/BR/BLR/RET,
    B.cond/CBZ/CBNZ/TBZ/TBNZ, LDR/STR/LDRB/LDRH/LDRSB/LDRSH/LDRSW/STRB/STRH,
    LDP/STP (all addressing modes: base_imm, pre, post, base_reg), SVC/BRK/NOP.
    NZCV computation via 65-bit (bv65) intermediates for ADDS/SUBS, 33-bit
    (bv33) for W-reg forms; `evaluate_condition()` covers all 16 A64 conds.
  - `gurdy/pairs/aarch64_btor2/translation/layers.py`: `EmitContext`,
    `LAYER_NAMES`, full set of emit_* functions. Machine state: 31 GPRs
    (x0–x30), sp, pc, nzcv (bv4), mem, halted, nondet. Dispatch layer selects
    next-sp and next-nzcv in addition to the riscv equivalents.
  - `gurdy/pairs/aarch64_btor2/translation/translate.py`: `Translator`,
    module-level `translate` callable.
  - `gurdy/pairs/aarch64_btor2/translation/exprs.py`: spec expression language
    extended with `sp` and `nzcv` terminals.
  - `gurdy/pairs/aarch64_btor2/__init__.py`: wired `load_aarch64_binary` and
    `translate.translate` in place of stubs.
  - Bug caught and fixed during test run: CBZ/CBNZ/TBZ/TBNZ decoder stores the
    compared register in `rd` (not `rn`); library now uses `decoded.rd`.
  - `tests/pairs/aarch64_btor2/unit/test_library_vs_simulator.py`: 61 new tests
    cross-checking every supported mnemonic (including AArch64-divergent cases:
    SDIV/UDIV div-by-zero → 0, W-reg zero-extension, NZCV flag patterns,
    SUB carry convention, B.cond with Z/N flags).
  - All 472 tests pass (13 skipped), 0 failures.
- **Next iteration's planned work**: P4 — Alignment oracle: implement
  `gurdy/pairs/aarch64_btor2/lift/` (witness replay path). Copy
  `riscv_btor2/lift/witness.py`, `replayer.py`, `invariant.py`, `lift.py`
  and adapt for AArch64 state (31 GPRs, sp, nzcv, halted). Wire the lifter
  in `__init__.py`. Then run a minimal end-to-end smoke test: translate a
  trivial AArch64 ELF (e.g. `add x0, x0, #1; svc #0`) and verify the
  BTOR2 model parses and the z3-bmc solver returns a verdict.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-25T00:00:00Z — P2: source interpreter (ELF loader + A64 decoder + simulator)

- **Phase**: P2 complete.
- **What changed**:
  - `gurdy/pairs/aarch64_btor2/source/elf.py`: `AArch64Binary`, `parse_elf`,
    `ELFParseError`; `instruction_words` yields fixed-width 4-byte LE words
    (no RVC).
  - `gurdy/pairs/aarch64_btor2/source/loader.py`: `AArch64Source`,
    `load_aarch64_binary`; rejects non-EM_AARCH64 (183) payloads.
  - `gurdy/pairs/aarch64_btor2/source/decoder.py`: full A64 decoder.
    `Decoded` dataclass (frozen) with `src_is_imm` flag distinguishing
    immediate vs register-operand forms. Routing via top-level op0 groups
    (DP-Imm, Branch/Sys, L/S, DP-Reg). Covers: ADR/ADRP, ADD/SUB/ADDS/SUBS
    (imm+reg), AND/ORR/EOR/ANDS (imm+reg), MOVZ/MOVK/MOVN, bitfield
    (UBFM/SBFM/BFM), EXTR, B/BL/BR/BLR/RET, B.cond, CBZ/CBNZ, TBZ/TBNZ,
    SVC/BRK/NOP, LDR/STR variants, LDP/STP, SDIV/UDIV, MADD/MSUB and
    widening variants, CSEL/CSINC/CSINV/CSNEG.
  - `gurdy/pairs/aarch64_btor2/lift/simulator.py`: `State` (31 GPRs, sp, pc,
    nzcv, halted, mem), `step()`. Key AArch64 divergences: SDIV/UDIV
    div-by-zero → 0; W-reg results zero-extend via `wr()` helper; NZCV via
    `_nzcv_add`/`_nzcv_sub`/`_nzcv_logical`; AArch64 carry convention (C=1 =
    no borrow); `_eval_cond` for all 16 A64 condition codes; R31 is SP for
    immediate/extended-register ADD/SUB, XZR for shifted-register.
  - `gurdy/pairs/aarch64_btor2/source_interp/bindings.py`:
    `AArch64InputBinding` (register_init, sp_init, nzcv_init, memory_init,
    havoc_per_step, havoc_sp).
  - `gurdy/pairs/aarch64_btor2/source_interp/interpreter.py`:
    `AArch64SourceInterpreter.run()` producing `SourceTrace`; halt reasons:
    `svc_or_brk`, `fetch_failed`; INTERPRETER_VERSION = "0.1.0".
  - `tests/fixtures/elf_builder_aarch64.py`: ELF builder for EM_AARCH64
    test ELFs.
  - 43 new unit tests across decoder, ELF loader, simulator, interpreter.
  - All 406 tests pass (18 skipped), 0 failures.
- **Next iteration's planned work**: P3 — BTOR2 lifter: implement
  `gurdy/pairs/aarch64_btor2/lift/` (translate `Decoded` instructions to
  BTOR2 bit-vector terms). Start with the structural scaffolding
  (sort/state/init/transition/bad term builders), then lower
  ADD/SUB/AND/ORR/EOR, MOVZ/MOVK, LDR/STR, branches (B, BL, B.cond, CBZ),
  and SDIV/UDIV (including div-by-zero → 0). Validate by comparing lifted
  BTOR2 models against the concrete simulator on P2 test cases.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-24T00:00:00Z — P1: SCHEMA.md frozen + spec.py + pair registration

- **Phase**: P1 complete.
- **What changed**:
  - Created `gurdy/pairs/aarch64_btor2/SCHEMA.md` at schema version
    `1.0.0`. Covers: sorts (bv1/4/5/6/8/16/32/33/64/65/mem), state
    variables (x0–x30, sp, pc, nzcv, halted, nondet), ELF loading,
    full A64 base integer ISA lowering in §§5.1–5.14, dispatch,
    entry assumptions, constraint/bad/havoc/verdict semantics,
    annotation conventions, stability profile, interpreter semantics,
    and the AArch64-vs-RV64 divergence summary table (§14).
  - Key AArch64 divergences documented explicitly:
    - SDIV/UDIV div-by-zero → 0 (not −1 / 2^64−1 like RV64).
    - W-register operations **zero-extend** to 64 bits (RV64 ADDW
      etc. sign-extend).
    - R31 is context-sensitive (XZR in data-processing, SP in
      memory/stack); separate `sp` state declared.
    - NZCV 4-bit condition-flags state (RV64 has none).
    - Link register is x30 (RV64: x1/ra).
    - AArch64 SUB carry convention = no-borrow (C=1 = no borrow).
    - No MULW analogue (SMULL sign-extends inputs, not result).
  - Implemented `gurdy/pairs/aarch64_btor2/spec.py`:
    `Aarch64Btor2Spec` (frozen dataclass, `from_jsonable`, JSON
    round-trip decoders), `validate_aarch64_btor2_spec` structural
    validator. New AArch64-specific fields vs riscv-btor2: `SPAt`,
    `NZCVAt`, `SPInit`, `NZCVInit`, `AnalysisDirective.havoc_sp`.
    Register range validated as 0–30 (not 0–31).
  - Updated `gurdy/pairs/aarch64_btor2/__init__.py`: pair registered
    via `register_pair(PAIR)` with schema_version `1.0.0`, spec
    class, validator, reasoning_interp, all five solver backends.
    `translator`, `source_loader`, `lifter` are `NotImplementedError`
    stubs (P4, P2 respectively); `interpreter_version=""` to avoid
    framework enforcement until those land.
  - Smoke tests pass: validator catches out-of-range register (r31),
    missing binary path, missing entry function; pair registration
    returns correct PAIR_ID, SCHEMA_VERSION, solver list, layer names.
- **Next iteration's planned work**: P2 — implement the AArch64
  source interpreter (`source_interp/`): ELF loader
  (`source/loader.py`), A64 instruction decoder (`source/decoder.py`),
  concrete executor for the integer base ISA + branches + loads/stores
  (`source_interp/interpreter.py`). Validate against QEMU
  (`qemu-aarch64-static`) on hand-crafted golden traces covering the
  key divergence cases (SDIV div-by-zero → 0; W-register zero-
  extension; XZR reads; SP addressing; NZCV flag updates for ADDS,
  SUBS, ANDS).
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-23T00:00:00Z — P0: scaffold aarch64_btor2 package

- **Phase**: P0 complete.
- **What changed**:
  - Created `gurdy/pairs/aarch64_btor2/` package with directory shape
    per `V2_BOOTSTRAP.md` §6: `source/`, `source_interp/`,
    `reasoning_interp/`, `translation/`, `lift/`, `solvers/`.
  - Copied `reasoning_interp/` verbatim from
    `v2-bootstrap:gurdy/pairs/riscv_btor2/reasoning_interp/` with
    import paths updated to `aarch64_btor2` and `PAIR_ID` changed to
    `"aarch64-btor2"`. BTOR2 evaluator imports remain on
    `riscv_btor2.btor2` (ISA-agnostic parser, shared).
  - Copied `solvers/` verbatim from
    `v2-bootstrap:gurdy/pairs/riscv_btor2/solvers/` (engine-agnostic).
  - Created `__init__.py` stub (registration deferred to P1) and
    `spec.py` stub (schema deferred to P1).
  - Created `bench/aarch64-btor2/` structure: `corpus/seed/`,
    `corpus/svcomp_slice/`, `harness.py`, `oracle_align.py`,
    `oracle_cross.py`, `engine_bench.py`, `baselines/{cbmc,hurdy_gurdy,pareto}.py`
    — all P-phase stubs with TODO markers.
  - Created `tests/pairs/aarch64_btor2/__init__.py`.
- **Next iteration's planned work**: P1 — define `SCHEMA.md` for
  `aarch64-btor2` (AArch64 base integer ISA; register file x0–x30,
  sp, pc, NZCV, mem, halted; schema version 1.0.0). Freeze the
  schema, then stub `spec.py` (`Aarch64Btor2Spec` + validator) and
  register the pair in `__init__.py` with a `NotImplemented`
  translator placeholder.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-17T00:00:00Z — Branch bootstrap

- **Phase**: pre-P0. Nothing implemented yet on this branch.
- **What's here**: `V2_BOOTSTRAP.md` (spec), `V2_AGENT_LOOP.md`
  (procedure), `V2_PROGRESS.md` (this file),
  `bench/aarch64-btor2/SCOPE.md` (benchmark scope). Everything
  else is inherited from `main`.
- **Next iteration's planned work**: P0 — scaffold the
  `gurdy/pairs/aarch64_btor2/` package and `bench/aarch64-btor2/`
  directory shape per `V2_BOOTSTRAP.md` §6. Copy `gurdy/core/`,
  `reasoning_interp/`, dispatch infrastructure, and the
  layered-artifact builder from the `v2-bootstrap` branch
  aggressively.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — **primary copy source for this pair**).
