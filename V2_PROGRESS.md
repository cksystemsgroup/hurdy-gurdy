# `aarch64-btor2` Progress — Live State

> The single source of truth for "where is the `aarch64-btor2`
> bootstrap right now." Each iteration appends one entry at the top.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-06-01T01:00:00Z — P13: k-induction + Spacer corpus tasks

- **Phase**: P13 complete (offline; cross-toolchain still unavailable but not needed).
- **What changed**:
  - `bench/aarch64-btor2/corpus/_assemble_asm.py`: new assembler helper.
    Assembles `source.S` → `source.elf` using `clang -target aarch64-linux-gnu`
    + `ld.lld` (both available on the host without the cross-toolchain).
    Text segment pinned at `0x400000` (`-Wl,-Ttext=0x400000`) to match the
    seed corpus address convention. CLI: `<task_dir> [--verify]`.
  - `bench/aarch64-btor2/corpus/seed/0012-aarch64-monotonic-x5-spacer/`:
    AArch64 port of riscv-btor2/0020-monotonic-x5-spacer.
    - `source.S`: 6-instruction loop (`ADD x5; MOVZ x6,8; CMP; B.LT; MOVZ x0,0; SVC`).
    - `source.elf`: assembled at `0x400000`–`0x400014` (1 024 bytes).
    - `spec.json`: engine=z3-spacer, bound=null, property=`lt(reg(5), const(0))`,
      assumption=RegisterInit(x5, eq, 0).
    - `task.toml`: task_class=global-invariant, expected=proved, [asm] section.
    - z3-spacer returns `proved` in ~0.49 s (synthesizes invariant x5 ≥ 0).
  - `bench/aarch64-btor2/corpus/seed/0013-aarch64-bounded-counter-spacer/`:
    AArch64 port of riscv-btor2/0045-x5-bounded-counter-spacer.
    - `source.S`: 5-instruction loop (`ADD x5; MOVZ x6,10; CMP; B.LT; SVC`).
    - `source.elf`: assembled at `0x400000`–`0x400010` (1 024 bytes).
    - `spec.json`: engine=z3-spacer, bound=null, property=`gt(reg(5), const(10))`,
      assumption=RegisterInit(x5, eq, 0).
    - `task.toml`: task_class=global-invariant, expected=proved, [asm] section.
    - z3-spacer returns `proved` in ~0.42 s (synthesizes invariant x5 ≤ 10).
  - `tests/pairs/aarch64_btor2/unit/test_spacer_tasks.py`: 21 new tests.
    - `test_required_files_exist` × 2 (parametrized)
    - `test_source_elf_is_aarch64` × 2
    - `test_spec_engine_and_property` × 2
    - `test_spec_has_register_init_x5_eq_0` × 2
    - `test_task_toml_expected_verdict_proved` × 2
    - `test_task_toml_id_matches_directory` × 2
    - `test_spec_parses_via_aarch64_spec_class` × 2
    - `test_assemble_asm_importable` × 1
    - `test_harness_0012_spacer_proves` (z3-required)
    - `test_harness_0013_spacer_proves` (z3-required)
    - `test_harness_spacer_elapsed_under_30s` (z3-required)
    - `test_oracle_cross_0012_inductive_cross_pass` (z3-required)
    - `test_oracle_cross_0013_inductive_cross_pass` (z3-required)
    - `test_oracle_cross_spacer_tasks_use_inductive_profiles` (z3-required)
  - `tests/pairs/aarch64_btor2/unit/test_harness.py`: updated.
    - `_ALL_SEED_IDS` extended with 0012 and 0013.
    - `test_list_tasks_includes_all_11_seeds` → `test_list_tasks_includes_all_seeds`.
    - `test_task_toml_parses`: verdict set extended to include "proved"; `[c]`
      section check made conditional (spacer tasks have `[asm]` not `[c]`).
  - `tests/pairs/aarch64_btor2/unit/test_oracle_cross.py`: updated.
    - `test_main_full_corpus_skips_seeds_without_elf`: updated row count (3 task
      rows instead of 1); added assertions that 0012/0013 appear as CROSS-SKIPPED
      when filtered to `--engines z3-bmc`.
  - All 261 tests pass, 0 failures, 0 skips. Previous: 238. Net new: +23.
- **Key finding**: `clang -target aarch64-linux-gnu` + `ld.lld` can produce
  AArch64 ELFs without the `aarch64-linux-gnu-gcc` cross-toolchain. This
  unblocks assembly-only corpus tasks (including all spacer tasks). C-source
  tasks still require the cross-toolchain for ABI-correct linking.
- **Next iteration's planned work**: P14 — SOTA baselines. Add ESBMC and/or
  SeaHorn to the baselines layer: port `bench/riscv-btor2/baselines/` cbmc.py
  patterns to produce an ESBMC-compatible invocation; run on the C-source seeds
  (0001 has source.elf, 0002–0011 have task.c); add 3–5 tests; update pareto.py
  to include the new baseline tool rows.
- **Open BLOCKERs**: `aarch64-linux-gnu-gcc` not present (C-source compilation
  blocked for seeds 0002–0011). Does not block P14 baseline work on seed 0001.
- **Reference branches**: `main` (v1), `v2-bootstrap` (`riscv-btor2` v2 — primary copy source).

---

## 2026-06-01T00:00:00Z — P12: SV-COMP slice ingestion (streaming) + translator fix

- **Phase**: P12 complete (offline; cross-toolchain still unavailable).
- **What changed**:
  - `bench/aarch64-btor2/corpus/_svcomp_stream.py`: full implementation.
    Fetches a single SV-COMP `.c` + `.yml` pair by raw GitHub URL (no
    sv-benchmarks checkout needed). Key design points:
    - `WHITELIST` — hardcoded frozenset of 10 pick paths mirroring the
      riscv-btor2 0250–0259 slice (`c/bitvector-regression/` ×8,
      `c/loops/` ×2); pinned to sv-benchmarks commit
      `2e1723fde6aa65a250dcb677efa45edaa4b6b631`.
    - Rewriting logic ported from
      `bench/riscv-btor2/corpus/_svcomp_extract.py` with AArch64
      adaptations:
      - Arg registers: `w0..wN` (AArch64 AAPCS64 32-bit) vs. `a0..aN`
        (RV64 LP64).
      - Normal halt: `svc #0`; bad halt: `brk #0` (vs. `ebreak`).
      - `[svcomp_stream]` toml section (not `[svcomp_extract]`).
      - Notes mention aarch64-btor2 and source URL.
    - `stream(pick, task_id, out_root, bound)` — fetches, rewrites,
      emits `original.c`, `original.yml`, `task.c`, `task.toml`.
    - `_try_compile(task_dir)` — calls `_compile_c.py` if
      `aarch64-linux-gnu-gcc` is present; returns `False` (dry-run) if
      absent. No spec.json emitted in dry-run.
    - `main()` CLI: `--pick`, `--task-id`, `--out-root`, `--bound`,
      `--dry-run`.
    - `_fetch(url)` — urllib.request.urlopen; caps at 64 KB.
  - `tests/pairs/aarch64_btor2/unit/test_svcomp_stream.py`: 24 new
    tests (all pass offline):
    - `test_whitelist_*` × 2
    - `test_raw_url_format`
    - `test_parse_yml_unreach_call_*` × 3
    - `test_check_rejects_*` × 3
    - `test_rewrite_main_*` × 6
    - `test_task_toml_*` × 3
    - `test_stream_rejects_unknown_pick`
    - `test_stream_offline_*` × 2
    - `test_main_*` × 2
  - **Latent regression fix**: `gurdy/pairs/aarch64_btor2/__init__.py`
    line 131: changed `translator=_translator_stub` →
    `translator=_translate`. `_translator_stub` was a plain function;
    `pair.translator.translate(...)` in `compile.py` requires a
    `Translator` protocol object. `_translate` (imported from
    `translation.translate`) is the `Translator()` singleton — matching
    the riscv-btor2 pattern. This unmasked 9 z3-dependent failures that
    were previously hidden by z3 not being installed.
  - All 238 tests pass, 0 failures, 0 skips. Previous: 201 pass, 13
    skip (z3 not installed). Net new passing: +37 (24 P12 tests + 9
    fixed z3 tests + 4 formerly-skipped z3 tests that now pass).
- **Next iteration's planned work**: P13 — k-induction + Spacer. Port
  `bench/riscv-btor2/` k-induction support to aarch64: add
  `z3-spacer` + `pono-ind` to the harness integration, add 2–3
  spacer-specific corpus tasks (porting e.g. 0045-x5-bounded-counter-spacer
  or 0020-monotonic-x5-spacer logic to AArch64 C source), and verify
  the spacer path produces expected results on the no-ELF corpus.
- **Open BLOCKERs**: `aarch64-linux-gnu-gcc` not present. `source.elf`
  and `spec.json` for seeds 0002–0011 and svcomp_slice tasks cannot be
  compiled. **Does not block P13 k-induction work on spacer tasks.**
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-31T01:00:00Z — P11: engine_bench + Pareto table

- **Phase**: P11 complete (offline; cross-toolchain still unavailable).
- **What changed**:
  - `bench/aarch64-btor2/engine_bench.py`: full implementation (port of
    `bench/riscv-btor2/engine_bench.py` on main). Key AArch64 adaptations:
    - No `framework_oracle.py` / `iter_questions` — task loading is
      inline via `oracle_cross._load_task()` (task.toml + spec.json).
    - Tasks without `source.elf` emit SKIP rows (`no source.elf
      (cross-toolchain unavailable)`); they do not enter `_measure()`
      and never produce timing stats.
    - `_measure(spec, elf_path, profiles, repeat)` — receives `elf_path`
      explicitly to pass to `compile_spec(spec, source_payload=elf_path)`.
    - No per-question loop: one task = one spec = one row.
    - Imports `_load_task`, `_run_profile`, `profiles_for`,
      `BMC_PROFILES`, `INDUCTIVE_PROFILES` from `oracle_cross`.
    - `_profiles(spec_engine, inductive_only, bmc_only)` helper mirrors
      the riscv version.
    - CLI flags: `--task`, `--corpus`, `--repeat`, `--bmc-only`,
      `--inductive`, `--json`.
  - `bench/aarch64-btor2/baselines/pareto.py`: full implementation
    (port of `bench/riscv-btor2/baselines/pareto.py` on main). Pareto
    logic is ISA-agnostic; only the default `RUNS` path and description
    are aarch64-specific. Implements:
    - `Row`, `ToolAggregate`, `PairwiseStats` dataclasses.
    - `load_runs(runs_dir)` — reads `*.jsonl` files.
    - `aggregate(rows)` — per-tool stats (solved, correct, FP, FN,
      unknown, error, timeout, skip, total_wall_s, median_wall_s).
    - `pareto_pair(rows_a, rows_b)` — strict dominance on
      (correct, wall_s) over commonly-solved tasks.
    - `render_text(by_tool)` — ASCII table with per-tool aggregate +
      Pareto dominance summary anchored on hurdy-gurdy.
    - `main` — `--runs` / `--json` CLI.
  - `tests/pairs/aarch64_btor2/unit/test_engine_bench.py`: 15 new
    tests (12 pass offline, 3 z3-skip):
    - `test_profiles_*` × 5
    - `test_row_text_*` × 3
    - `test_main_skips_task_without_elf`
    - `test_main_json_skip_for_no_elf`
    - `test_main_json_skip_row_structure`
    - `test_main_no_task_match_returns_2`
    - `test_main_seed_0001_z3bmc_text` (z3-skip)
    - `test_main_seed_0001_json_output` (z3-skip)
    - `test_main_full_corpus_skips_seeds_without_elf` (z3-skip)
  - `tests/pairs/aarch64_btor2/unit/test_pareto.py`: 23 new tests
    (all pass offline):
    - `test_row_from_dict_*` × 3
    - `test_load_runs_*` × 4
    - `test_aggregate_*` × 5
    - `test_pareto_pair_*` × 6
    - `test_render_text_*` × 3
    - `test_main_*` × 2
  - All 201 tests pass (13 skipped — z3 not in pytest venv), 0 failures.
    Previous: 166 pass, 10 skip. Net new: +35 passing tests.
- **Next iteration's planned work**: P12 — SV-COMP slice ingestion
  (streaming). Implement `bench/aarch64-btor2/corpus/_svcomp_stream.py`
  to fetch one SV-COMP C file by raw URL (hardcoded whitelist), compile
  it to AArch64 with a pinned cross-toolchain, and emit a `task.toml` +
  `spec.json`. If cross-toolchain is still unavailable, implement the
  fetch + whitelist scaffold as a dry-run (no compile step), mirroring
  the pattern established in P10/P11 for the no-ELF case.
- **Open BLOCKERs**: `aarch64-linux-gnu-gcc` not present. `source.elf`
  and `spec.json` for seeds 0002–0011 cannot be compiled. **Does not
  block P12 streaming scaffold work.**
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-31T00:00:00Z — P10: multi-engine cross oracle

- **Phase**: P10 complete (offline; cross-toolchain still unavailable).
- **What changed**:
  - `bench/aarch64-btor2/oracle_cross.py`: full implementation (port of
    `bench/riscv-btor2/oracle_cross.py` on main). Key AArch64
    adaptations:
    - No `framework_oracle.py` dependency — task loading is inline via
      `task.toml` + `spec.json` (`_load_task()`).
    - Tasks without `source.elf` emit SKIP rows (`no source.elf
      (cross-toolchain unavailable)`); they do not contribute to
      `fail_count` / `mismatch_count` and never set exit code 1.
    - No `pono-docker` / `pono-ind-docker` profiles — those engines are
      not registered for the `aarch64-btor2` pair.
    - No certificate re-verification — `bmc_certificate` /
      `kind_certificate` not yet ported for aarch64.
    - Compilation (ELF → BTOR2) done once per task; dispatch runs per
      profile (same pattern as riscv reference).
    - BMC profiles: z3-bmc, bitwuzla, cvc5, pono.
    - Inductive profiles: z3-spacer, pono-ind (pono with `engine=ind`,
      bound_fallback=10).
    - `INDUCTIVE_PINNED = frozenset({"z3-spacer"})` selects profile set.
  - `tests/pairs/aarch64_btor2/unit/test_oracle_cross.py`: 32 new
    tests (29 pass offline, 3 z3-skip):
    - `test_profiles_for_bmc_engine_returns_bmc_profiles`
    - `test_profiles_for_bitwuzla_returns_bmc_profiles`
    - `test_profiles_for_z3_spacer_returns_inductive_profiles`
    - `test_inductive_profiles_pono_ind_has_engine_extra`
    - `test_no_pono_docker_profiles`
    - `test_verdict_satisfies_*` × 6
    - `test_verdicts_agree_*` × 5
    - `test_summarize_*` × 6
    - `test_render_text_*` × 4
    - `test_main_skips_tasks_without_elf`
    - `test_main_json_emits_skip_for_no_elf`
    - `test_main_no_task_match_returns_2`
    - `test_main_seed_0001_z3bmc_cross_pass` (z3-skip)
    - `test_main_seed_0001_json_output` (z3-skip)
    - `test_main_full_corpus_skips_seeds_without_elf` (z3-skip)
  - All 166 tests pass (10 skipped — z3 not in pytest venv), 0 failures.
    Previous: 137 pass, 7 skip. Net new: +29 passing tests.
- **Next iteration's planned work**: P11 — engine_bench.py / Pareto
  table. Port `bench/riscv-btor2/baselines/pareto.py` and
  `engine_bench.py` to aarch64, exercise on seed 0001. If
  cross-toolchain is still unavailable, implement Pareto scaffold that
  SKIP-rows the 10 seeds without ELF and computes a single-task table
  for seed 0001.
- **Open BLOCKERs**: `aarch64-linux-gnu-gcc` not present. `source.elf`
  and `spec.json` for seeds 0002–0011 cannot be compiled. **Does not
  block P11 pareto scaffold work.**
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

---

## 2026-05-30T01:00:00Z — P9: shadow mode + FREE sentinel

- **Phase**: P9 complete (offline; cross-toolchain still unavailable).
- **What changed**:
  - `gurdy/pairs/aarch64_btor2/source_interp/shadow.py`: new file —
    AArch64 port of `riscv_btor2/source_interp/shadow.py`. Key
    AArch64-specific adaptations:
    - `BRANCH_MNEMONICS = {"B.cond", "CBZ", "CBNZ", "TBZ", "TBNZ"}` —
      conditional branches only (B/BL/BR unconditional not recorded).
    - `LOAD_MNEMONICS` / `STORE_MNEMONICS` updated to A64 vocabulary
      (LDR/LDRB/LDRH/LDRSB/LDRSH/LDRSW/LDP; STR/STRB/STRH/STP).
    - `free_fields_of`: sp_init, nzcv_init, havoc_sp cannot carry FREE
      (typed int|None), so only register_init, memory_init, and
      havoc_per_step are inventoried.
    - `BranchEvent`, `MemoryAccessEvent`, `ShadowRecord` unchanged from
      riscv (structure is ISA-agnostic).
  - `gurdy/pairs/aarch64_btor2/source_interp/interpreter.py`: added
    `record_shadow: bool = False` parameter to `run()`:
    - When False (default): byte-identical v1.0.0 behavior; FREE raises
      `FreeFieldNotAllowed`.
    - When True: FREE cells concretize to 0; per-instruction branch and
      memory events recorded; `final_state["shadow"]` exposed
      (SCHEMA.md §14.6).
    - Branch direction: `taken = new_state.pc != (pre_pc + 4)` — AArch64
      fixed 4-byte instructions (no variable-length as in RV64C).
    - Memory effective address: computed from pre-step state via new
      `_effective_addr()` helper; handles all addr_modes
      (base_imm/base/pre/post/literal/base_reg/ext_reg). Uses
      `simulator._apply_extend` for ext_reg extend/shift computation.
  - `tests/pairs/aarch64_btor2/unit/test_shadow_interpreter.py`: 8 new
    tests:
    - `test_default_run_has_no_shadow_in_final_state`
    - `test_default_run_rejects_free`
    - `test_shadow_records_branch_not_taken` (CBNZ X0, +8 with X0=0)
    - `test_shadow_records_branch_taken` (CBNZ X0, +8 with X0=1)
    - `test_shadow_records_load_event` (LDR X0, [X1, #0])
    - `test_shadow_accepts_free_fields`
    - `test_shadow_free_concretizes_to_zero`
    - `test_shadow_records_free_field_inventory`
  - All 137 tests pass (7 skipped — z3 not in pytest venv), 0 failures.
    Previous: 129 pass, 7 skip. Net new: +8 passing tests.
- **Next iteration's planned work**: P10 — multi-engine cross oracle.
  Implement `bench/aarch64-btor2/oracle_cross.py` (port from
  `bench/riscv-btor2/oracle_cross.py` on main). Oracle runs each
  configured engine (z3-bmc, bitwuzla, pono) on each task and checks
  that all engines agree on the verdict. If cross-toolchain is still
  unavailable, implement oracle_cross as a shell that skips tasks
  without `source.elf` (SKIP row), exercising the scaffold path on
  seed 0001-c-loopsum-o0 alone.
- **Open BLOCKERs**: `aarch64-linux-gnu-gcc` not present. `source.elf`
  and `spec.json` for seeds 0002–0011 cannot be compiled. **Does not
  block P10 oracle_cross shell work.**
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — primary copy source).

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
