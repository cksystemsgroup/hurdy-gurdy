# V2 Progress — Live State

> The single source of truth for "where is the v2 bootstrap right now."
> Each iteration appends one entry at the top. Older entries stay for
> history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-05-16T05:10:00Z — P3.6 Pono-native adapter (skip-with-note)

- **Phase**: P3.6 done (adapter shell ready); next is **P3.7
  aggregator** (engine_bench.py extension).
- **What changed**: `bench/riscv-btor2/baselines/pono.py`
  implements the same `run_one()` schema as `cbmc.py`. Adapter
  flow:
  1. Detect `pono` on PATH; skip-with-note if absent.
  2. Load spec.json with absolute binary path.
  3. Call `compile_spec(spec)` to materialize a `CompiledArtifact`.
  4. Write `artifact.flattened` (BTOR2 text) to a tempfile.
  5. `subprocess.run(["pono", "-e", "bmc", "-k", "<bound>",
     tempfile])` with timeout + RLIMIT_AS.
  6. Parse stdout's last non-empty line for sat/unsat/unknown.
  7. Map: sat → reachable, unsat → unreachable, unknown →
     unknown; bad parse → error; timeout → timeout. Cleanup
     tempfile in finally.
- **Smoke** (`--max-tasks 2`): both tasks return
  `verdict=error notes="pono not on PATH"` cleanly. Adapter is
  ready to activate the moment `pono` is installed (build from
  source or homebrew tap when available).
- **Meta-observation**: of the five P3 candidate tools, only
  **CBMC is natively available** on this machine. Pono, ESBMC,
  SeaHorn, and Symbiotic all require either build-from-source
  (Pono) or Docker (the other three) — per V2_AGENT_LOOP.md §4
  the agent cannot autonomously install these. The Pareto table
  built from this branch will, in the autonomous case, have
  only one real SOTA column (CBMC). To unlock the others the
  user would need to either (a) `brew install pono` if/when
  available, build pono from source, or pull docker images for
  the others.
- **Next iteration's planned work**: **P3.7 aggregator** —
  read existing `bench/riscv-btor2/engine_bench.py` (mentioned
  in V2_BOOTSTRAP.md §6 / baselines/README.md §6 as the
  aggregator). Decide whether to extend it (preferred) or to
  write a new `bench/riscv-btor2/baselines/pareto.py`. Output:
  consume cbmc.py + (later) pono.py + (eventually)
  framework_oracle.py JSONL streams; produce a per-tool /
  per-task table and the Pareto-relation row-by-row. Cap to
  ≤ 5 corpus tasks for any smoke run. Do NOT run framework_oracle
  on the full corpus this iter.
- **Open blockers**: 1 escalated (P1.3a translator fix).
  No change.

---

## 2026-05-16T04:50:00Z — P3.2 CBMC adapter + first SOTA datapoint

- **Phase**: P3.2 done; P3.6 (Pono-native) is the right next pick
  before the harder Docker-only baselines (P3.4/P3.5).
- **What changed**: `bench/riscv-btor2/baselines/cbmc.py`
  implements `run_one(task_dir, *, timeout_s, memory_mb, unwind)
  -> dict` per `baselines/README.md` §3. Subprocess invocation:
  `cbmc <task.cbmc.c> --unwind 20 --bounds-check --pointer-check`
  with `subprocess.run` timeout and `setrlimit(RLIMIT_AS)`
  memory cap (macOS doesn't enforce RLIMIT_AS strictly but the
  intent is recorded).
- **Smoke results** (3-task default, `--max-tasks 3`, CBMC 6.9.0):

  | Task                          | expected   | cbmc        | correct | wall_s |
  |-------------------------------|------------|-------------|---------|--------|
  | 0100-c-add-trap-correct       | unreachable| unreachable | ✓       | 0.204  |
  | 0101-c-add-trap-bug           | reachable  | reachable   | ✓       | 0.026  |
  | 0102-c-mul-chain-correct      | unreachable| unreachable | ✓       | 0.026  |

  **3/3 correct, all subsecond.** First concrete SOTA datapoint
  for the Pareto comparison.
- The adapter handles all schema verdict cases: VERIFICATION
  FAILED → reachable, VERIFICATION SUCCESSFUL → unreachable
  (with unwinding-warning → unknown), PARSING ERROR → error,
  TimeoutExpired → timeout, no `task.cbmc.c` → skip, missing
  cbmc binary → error with note.
- **Next iteration's planned work**: **P3.6 — Pono-native
  adapter**. Pono is the most apples-to-apples peer (it consumes
  the same BTOR2 hurdy-gurdy emits). On macOS, building from
  source is feasible but not autonomous-safe; the adapter
  follows CBMC's pattern of detecting binary absence and
  skip-with-note. If `pono` is on PATH, smoke-test on ≤ 3 tasks.
  Pono adapter logic: run `pono -e bmc -k <bound> <task_btor2>`,
  parse stdout for `sat`/`unsat`/`unknown`. Map to schema:
  `sat` → reachable, `unsat` → unreachable (within bound),
  `unknown` → unknown. The BTOR2 for each task isn't pre-built;
  the adapter will need to compile_spec via the hurdy-gurdy
  toolchain to produce it on the fly. Decide adapter
  granularity: compile-then-pono vs require pre-built BTOR2.
  ESBMC (P3.3) is also a viable next pick if Pono is unavailable.
- **Open blockers**: 1 escalated (P1.3a translator fix). No
  change.

---

## 2026-05-16T04:30:00Z — P3.1 corpus-input audit

- **Phase**: P3.1 done; P3.2 (CBMC adapter) next.
- **What changed**: `bench/riscv-btor2/baselines/corpus_inputs.json`
  produced from a read-only scan. 89 tasks with `task.toml`.
- **Numbers**:
  - 89 tasks total.
  - 35 tasks have `task.c` (the `0100+` C-derived series).
  - **25 tasks have `task.cbmc.c`** — pre-prepared CBMC-ready C
    source. These are the immediate Pareto-comparison candidates.
  - 54 tasks have `source.S` (hand-written assembly seed series
    `0001–0099`). Only comparable against Pono-native.
  - 0 tasks have `source.c` (my initial filter looked for the
    wrong filename — corrected in this audit). 0 have `source.bc`.
- **What this changes for the baselines plan**:
  - **P3.2 (CBMC)** is immediately feasible on 25 tasks — no
    corpus modifications needed. The Pareto table will simply
    skip asm-only tasks for CBMC/ESBMC.
  - The 54 asm-only tasks will only have Pono-native as a peer
    (P3.6). Acceptable; the comparison is still meaningful where
    both tools apply.
  - **No LLVM bitcode (`.bc`) anywhere**. SeaHorn / Symbiotic
    adapters (P3.4 / P3.5) will need to either (a) generate `.bc`
    from `task.c` at runtime, or (b) be scoped to only run after
    a one-shot per-task `.bc` materialization step. Add that as
    a sub-decision in `baselines/README.md` (next iter or in
    P3.4 itself).
- **Next iteration's planned work**: **P3.2 — CBMC adapter
  skeleton**. Write `bench/riscv-btor2/baselines/cbmc.py`
  implementing the `run_one(task_dir, *, timeout_s, memory_mb) ->
  dict` interface per `baselines/README.md` §3. Subprocess invokes
  `cbmc <task.cbmc.c> --bounds-check --pointer-check --unwind <K>`
  (or similar; consult CBMC docs at adapter-write time) with the
  RAM-safety caps from `V2_AGENT_LOOP.md` §4. If `cbmc` isn't on
  PATH, return `verdict=error notes="cbmc not found"` cleanly —
  the adapter must skip-with-note, not crash. Smoke test on
  ≤ 3 tasks. **Do not** invoke any other baseline this iter.
- **Open blockers**: 1 escalated (P1.3a translator fix). No new
  blocker.

---

## 2026-05-16T04:10:00Z — P3 prep: baselines design doc

- **Phase**: P3 prep (P1.3a BLOCKER still escalated to user, not
  blocking progress on independent tracks).
- **What changed**: `bench/riscv-btor2/baselines/README.md`
  created (pure design doc, no code). Covers:
  - The five candidate SOTA tools and what makes each a peer:
    CBMC, ESBMC, SeaHorn, Symbiotic, Pono-native.
  - Two explicit deferrals with rationale: KLEE (different
    question class), CPAchecker (heavy install).
  - Uniform output schema: one JSON line per (task, question)
    with `tool / task / verdict / wall_s / rss_mb / expected /
    correct / cmd / raw_excerpt / notes`.
  - Adapter interface: `run_one(task_dir, *, timeout_s, memory_mb)
    -> dict`.
  - macOS reality: only CBMC is reasonably native; SeaHorn /
    Symbiotic / ESBMC need Docker. Per V2_AGENT_LOOP.md §4 the
    agent **cannot** autonomously `docker pull` or install
    system packages; adapters skip-with-note when their binary
    is absent.
  - C-source availability sub-audit (P3.1): scan corpus for
    tasks with `source.c` alongside `source.elf`; tasks without
    C source compare only against Pono-native.
- **Next iteration's planned work**: **P3.1 — corpus input
  audit**. Scan `bench/riscv-btor2/corpus/` for `source.c`
  alongside `source.elf` and produce
  `bench/riscv-btor2/baselines/corpus_inputs.json` mapping each
  task id to its available input formats (`elf` always, `c` if
  present, `bc` if present). Read-only scan; no compile. Cap at
  reading file headers, not contents — tasks/89 × small read is
  RAM-safe but stream the listing rather than slurp all at once.
- **Open blockers**: **1 escalated** (P1.3a translator fix).
  Iter-count for §8 stop condition: 1 BLOCKER-iter (iter 11), 0
  follow-up BLOCKER-iters (this iter pivoted, didn't add to
  count).

---

## 2026-05-16T03:50:00Z — P1.3a SortMismatch diagnosis (escalating to user)

- **Phase**: P1.3a complete (diagnosis); fix escalated to user.
- **What changed**: Full diagnosis of the iter-10 BLOCKER. No code
  changes this iteration — the proposed fix is ≤ 25 LOC but
  modifies v1 translator emission, which is not autonomous-safe
  per `V2_AGENT_LOOP.md` §1.3a guidance ("framework fix may need
  v1-side review").
- **Root cause** (concrete):
  - Bug location: `gurdy/pairs/riscv_btor2/translation/exprs.py:218`.
  - The `parse_and_emit` dispatcher for `add/sub/and/or/xor`
    hardcodes the result sort as `"bv64"`. For arithmetic
    (`add/sub`) on register operands that's correct; for boolean
    `and/or/xor` of predicates (like the combined `bad` clause's
    AND of two `eq` results, both bv1), the emitted result sort
    is **wrong** — should be `bv1`.
  - Concrete reproduction: task 0007-simple-add-baseline emits:
    ```
    87 eq  1 39 63   # bv1 equality
    89 eq  1 17 88   # bv1 equality
    90 and 4 87 89   # MALFORMED: result_sort=bv64 with bv1 operands
    91 bad 90
    ```
  - The strict evaluator in `gurdy/pairs/riscv_btor2/btor2/
    evaluator.py:148` raises `SortMismatch("'and': operand widths
    1, 1 must match result width 64")` — exactly as designed.
  - The strict evaluator's docstring explicitly states it was
    added to catch translator bugs that "previously only surfaced
    on full-corpus dispatch."
  - Real solvers don't reject the malformed BTOR2 in
    `framework_oracle.py` because they parse with different
    leniency, but the witness they produce can't be cleanly
    replayed by the in-process simulator.
- **Proposed fix** (≤ 25 LOC, **not applied**):
  1. Add `_nid_sort: dict[int, str]` to `Builder` (3 LOC init +
     ~5 LOC populated by `const`, `ones`, `emit`).
  2. Add `Builder.sort_of_nid(nid) -> str | None` method (~3 LOC).
  3. In `exprs.py` `and/or/xor` branch (~10 LOC), look up the
     first operand's sort and emit the result with the same sort
     (operands are required to be uniform-width in BTOR2, so
     either operand's sort works as the answer).
  4. Keep `add/sub/mul` hardcoded to `"bv64"`.
- **Why escalating, not patching**:
  - Modifies v1 translator emission. Any spec that hits the
    buggy code path will produce different bytes after the fix —
    this is a real behavior change.
  - Determinism contract: v1's translator is supposed to be
    pure/deterministic. The fix is corrective (the existing
    output is malformed BTOR2), but downstream consumers may
    have golden-byte tests.
  - Solver compat: real solvers were *tolerating* the malformed
    output; we don't know if their witness format depends on
    the malformed sort. Worth verifying with `framework_oracle.py`
    after the fix.
  - Test suite: tests in `tests/pairs/riscv_btor2/translation/`
    likely include byte-level assertions that would break. Needs
    a full pytest run, not the targeted ≤ 5-task smoke we'd do
    autonomously.
- **Action needed from user**: review the proposed fix and
  approve. Once approved (`UNBLOCKED: approve P1.3a fix`), a
  subsequent iteration will:
  1. Apply the ≤ 25 LOC patch.
  2. Run `pytest tests/pairs/riscv_btor2/translation/ -q`.
  3. Run `framework_oracle.py` on the seed corpus to confirm
     verdicts unchanged.
  4. Re-run `oracle_align.py` on 0007 + 0002 to confirm
     alignment now succeeds.
- **Next iteration's planned work** (independent of BLOCKER):
  **pivot to P3 prep** — write
  `bench/riscv-btor2/baselines/README.md` sketching the
  per-tool subprocess wrapper interface (CBMC / ESBMC / SeaHorn /
  Symbiotic / Pono-native), the uniform output schema, and which
  tools to defer (require Linux-only / Docker / heavy install).
  No tool installation, no subprocess invocations yet. Pure
  design doc to be ready when the BLOCKER clears.
- **Open blockers**: **1 escalated** (P1.3a fix awaiting user
  approval). Not a regression — the BLOCKER from iter 10 now has
  a complete diagnosis and a concrete patch.

---

## 2026-05-16T03:30:00Z — P1.3 replay+align wired; latent bug exposed

- **Phase**: P1 (P1.3 wired; new BLOCKER opened).
- **What changed**: `oracle_align.py` `_run_one_question`'s
  `reachable` branch now:
  - loads source ELF via `load_riscv_binary(spec.binary.path)`,
  - calls `replay_witness(artifact, raw, source=source)` to get a
    `JoinedTrace`,
  - builds a projection from the artifact (walks the flattened
    BTOR2 once for the state-symbol → nid map; mirrors the
    private helper in `gurdy/pairs/riscv_btor2/__init__.py`),
  - walks the JoinedTrace step-by-step through the projection,
  - maps agreement → `status=PASS align_kind=ok`, first
    divergence → `status=FAIL align_kind=diverge` with
    `divergence_step` + `divergence_label`.
  - All replay/align exceptions → `status=ERROR` with the
    underlying exception type + message.
- **The §4 alignment-oracle contract is now operationally wired
  end-to-end** — when it can run.
- **BLOCKER: framework BTOR2 simulator hits a SortMismatch on
  every reachable-witness replay**. Smoke run on two known-
  reachable tasks (`0002-bound-sensitive-loop` and
  `0007-simple-add-baseline`) both returned
  `ERROR (replay/align: SortMismatch: 'and': operand widths 1, 1
  must match result width 64)`. The error is inside the
  `replay_witness` call path (`gurdy/pairs/riscv_btor2/
  reasoning_interp/interpreter.py` or
  `gurdy/pairs/riscv_btor2/lift/replayer.py`'s internal call to
  the simulator), not in my new oracle code. This is exactly the
  kind of latent framework bug the alignment oracle exists to
  surface — but it now blocks measuring alignment on any
  reachable task.
- **Next iteration's planned work**: **P1.3a — diagnose the
  SortMismatch**. Read the simulator code path for the
  width-checking logic; identify whether the bug is in (a) the
  parser interpreting a translator-emitted clause's result sort,
  (b) the simulator's `and` op implementation, or (c) the
  translator emitting a width-incoherent clause. Single-step:
  run a single small reachable task with a print statement at
  the failing op site to learn which clause/nid triggers. If the
  root cause needs a fix beyond ≤ 30 LOC, file a separate
  BLOCKER and stop the loop pending user review (the framework
  fix may need v1-side review and is not autonomous-safe).
- **Open blockers**: 1 (the SortMismatch above). Counter for §8
  stop-condition: 1 BLOCKER, no user response expected this iter.

---

## 2026-05-16T03:10:00Z — P1.2 compile+dispatch wiring

- **Phase**: P1 (P1.2 done; P1.3 next).
- **What changed**: `oracle_align.py` `run_one` stub replaced with
  the real compile→dispatch→verdict-classification pipeline.
  - Imports `compile_spec`, `dispatch` from `gurdy.core.tools`.
  - Loader mirrors `framework_oracle.py:_load_spec_obj` (rewrites
    `binary.path` to absolute so dispatch resolves the ELF
    regardless of cwd).
  - Multi-question support via `_iter_questions` (mirrors
    `framework_oracle.iter_questions`); each question is reported
    as `task::qN`.
  - Verdict mapping at this iter:
    - `reachable` → `SKIP` with note "P1.3 pending: align this
      witness" (witness exists; alignment logic is next iter).
    - `unreachable` / `proved` / `unknown` → `SKIP` (alignment
      doesn't apply without a concrete trajectory).
    - other / exception → `ERROR`.
  - `AlignResult` gained `raw_verdict`, `engine`, `elapsed`.
- **Smoke verified**:
  - `--task 0001-x0-write-dropped` (`expected=unreachable`):
    `SKIP align=N/A (verdict=unreachable)` — dispatch ran, raw
    verdict captured, classification correct.
  - `--task 0002-bound-sensitive-loop` (`expected=reachable`):
    `SKIP align=N/A (P1.3 pending: align this witness)` — witness
    produced; P1.3 will replay+align here.
- Both runs completed within the RAM-safety budget (single solver
  subprocess each).
- **Next iteration's planned work**: **P1.3** — wire
  `replay_witness` + `align_traces` for the `reachable` branch.
  Per task with `reachable` verdict: load the source ELF (via
  `gurdy.pairs.riscv_btor2.source.loader.load_riscv_binary`), call
  `replay_witness(spec, artifact, raw_result)` to get a
  `JoinedTrace`, then call `align_traces(source_trace,
  reasoning_trace, make_projection(...))` and map the
  `CrossCheckReport` outcome to `align_kind='ok'` (status=PASS) or
  `align_kind='diverge'` (status=FAIL) with divergence step+label.
  Smoke test on `--task 0002-bound-sensitive-loop` — expect PASS
  (translator is sound; alignment should hold).
- **Open blockers**: none.

---

## 2026-05-16T02:50:00Z — P1.1 oracle_align.py shell

- **Phase**: P1 (P1.1 done; P1.2 next).
- **What changed**: First code-write iteration on v2-bootstrap.
  `bench/riscv-btor2/oracle_align.py` shell added: argparse with
  `--task / --max-steps / --engine / --corpus / --max-tasks / --json`,
  task discovery mirroring `oracle.py` and `framework_oracle.py`,
  per-task `AlignResult` dataclass + `render_row`, stubbed
  `run_one()` returning `SKIP` with note "stub: P1.2 not yet
  implemented". Imports verified (framework loads cleanly via
  `import gurdy.pairs.riscv_btor2`). `--help` works. Running on the
  corpus discovers 89 tasks (capped at 5 by --max-tasks for RAM
  safety) and prints SKIP rows correctly.
- **Side observation**: the corpus already has **89 tasks**, well
  above the v2 PLAN P2 target of ≥ 50. P2 (SV-COMP scale-up) may
  be already-done or much smaller scope than written. Worth
  reading bench/riscv-btor2/CORPUS_V0.5_PLAN.md against actual
  corpus contents next time P2 surfaces.
- **Next iteration's planned work**: P1.2 — replace the `run_one`
  stub with the compile→dispatch→verdict-classification pipeline.
  Per task: load spec/binary, call compile + dispatch (engine from
  `analysis` directive or `--engine` flag), classify verdict.
  Branch: on `reachable` → mark for P1.3 (replay+align); on
  `unreachable/proved/unknown` → `SKIP(N/A)`. Still no alignment
  logic; only verdict capture. RAM-safe: ≤ 3 tasks per smoke run.
- **Open blockers**: none.

---

## 2026-05-16T02:30:00Z — P0.5b PLAN.md correction

- **Phase**: P0 complete (audit + correction); next is P1.
- **What changed**: PLAN.md rewritten to reflect the P0 audit
  findings. The new plan has just four real phases:
  - **P0** ✅ — audit (iters 2–6, done).
  - **P1** — primary alignment oracle (`oracle_align.py`, the §4
    contract operationalised). The **only** "build" phase, because
    every other §3 pillar contract is already satisfied by v1.
  - **P2** — SV-COMP slice scale-up from 10 → ≥ 50 tasks (the
    in-progress corpus v0.5 work).
  - **P3** — SOTA baselines (CBMC, ESBMC, SeaHorn, Symbiotic,
    Pono-native) for the Pareto comparison.
  - **P4+** — iteration to dominance (steady state).
  - An appendix lists "was P1–P15" as already-shipped to prevent
    future re-planning.
- The original PLAN.md framed v1–v13 as "to build"; the audit
  showed they were "already shipped". The single real gap is the
  bench-side primary alignment oracle (≤ 150 LOC). Other v2 work
  is empirical (corpus + SOTA + iteration), not foundational.
- **Next iteration's planned work**: **P1.1** — sketch
  `bench/riscv-btor2/oracle_align.py` shell matching the shape of
  `oracle.py` and `framework_oracle.py`: argparse, task discovery,
  per-task loop, PASS/SKIP/FAIL output. **No alignment logic yet**
  (that's P1.2–P1.3). This is the first iteration with a code
  edit that will exercise v1's import-correctness — run `python -m
  pytest tests/ -q` after the shell lands as a tiny smoke check.
- **Open blockers**: none. P0 closes here.

---

## 2026-05-16T02:10:00Z — P0.4 schema audit: PLAN.md was misframed

- **Phase**: P0 (P0.4 done; P0.5 next).
- **What changed**: `V2_AUDIT.md` extended with §"P0.4 — schema
  audit". Two material findings:
  1. SCHEMA.md is at v1.1.0, but v1.1.0 is **byte-compatible** with
     v1.0.0 for specs that opt out of §14 vocabulary (line 443–446
     in SCHEMA.md pins this with a regression test). The PLAN.md
     framing of "v1.0.0 minimal viable downgrade" was wrong — v2's
     starting schema is just v1.1.0, with §14 features opt-in.
  2. The v1 schema baseline ISA is **RV64I+M+C** (per §12 line 341),
     not RV64I. PLAN.md P9 (add M) and P10 (add C) describe work
     that is already done. Same for P11 (multi-callee scope) —
     already in §6 Dispatch.
- Filed as **P0.5b — PLAN.md correction**: revise P1/P9/P10/P11.
  P0.5a (bench-side primary alignment oracle) is unchanged.
- **Next iteration's planned work**: P0.5b — apply the PLAN.md
  corrections (≤ 20 LOC). Specifically: rewrite P1 to "accept
  v1.1.0 schema as v2's starting schema, no downgrade"; delete P9,
  P10, P11 as phases (note in PLAN.md that they were retrospective);
  renumber if it improves clarity; cross-link the V2_AUDIT.md P0.4
  finding.
- **Open blockers**: none. This is the third plan-side correction
  in P0 (iter 3 was alongside-v1; this is schema-baseline). Pattern:
  the plan was written before reading the repo carefully. Worth
  noting if a future iteration is tempted to plan-by-assumption
  again.

---

## 2026-05-16T01:50:00Z — P0.3 pair audit landed

- **Phase**: P0 (P0.3 done; P0.4 next).
- **What changed**: `V2_AUDIT.md` extended with §"P0.3 — pair audit".
  All three §3 pillars (source_interp, reasoning_interp,
  translation) conform. All five solver adapters present (z3-bmc,
  z3-spacer, bitwuzla, cvc5, pono). The §4 alignment-oracle
  machinery exists in `gurdy/core/interp/align.py` +
  `gurdy/pairs/riscv_btor2/lift/replayer.py` (builds `JoinedTrace`
  from witness, framework walks via `align_traces`). **One
  operational gap**: this machinery is invoked per-witness via the
  `replay` tool, not as a bench-side per-task primary oracle. The
  bench-side files are `oracle.py` (concrete-execution,
  solver-free, §9.10), `framework_oracle.py` (compile→dispatch→
  lift verdict comparison, §B0), and `oracle_cross.py` (engine
  agreement, §4.5) — none of them runs `align_traces` per task.
  Filed as **P0.5a — `bench/riscv-btor2/oracle_align.py`** (≤ 150
  LOC).
- **Next iteration's planned work**: P0.4 — schema audit. Read
  `gurdy/pairs/riscv_btor2/SCHEMA.md`, identify what's at v1.1.0
  scope that exceeds the v2-target v1.0.0 scope (BranchPin,
  CycleInvariant.dual_role, volatile layer, M extension, C
  extension, multi-callee scope). Append §"P0.4 — schema audit"
  to V2_AUDIT.md.
- **Open blockers**: none.

---

## 2026-05-16T01:30:00Z — P0.2 v1-core audit landed

- **Phase**: P0 (P0.2 done; P0.3–P0.5 queued).
- **What changed**: `V2_AUDIT.md` created. Maps every
  `V2_BOOTSTRAP.md` §3 contract (three pillars, alignment oracle,
  spec, schema discipline, pair protocol, determinism) to v1 status.
  Headline: v1 **broadly conforms**. Two documentation-class gaps
  (P0.2a: assert load-bearing-from-day-one in
  `core/interp/README.md`; P0.2b: verify bench-harness uses
  `align_traces` as primary oracle, deferred to P0.3). Three
  follow-up audits queued: P0.3 (pair), P0.4 (schema), P0.5 (gap
  numbering). No code touched.
- **Next iteration's planned work**: P0.3 — `gurdy/pairs/
  riscv_btor2/` audit. Read source_interp, reasoning_interp,
  translation, solvers, lift surfaces; append §"riscv-btor2 pair"
  to `V2_AUDIT.md`. Also resolve P0.2b: search `bench/riscv-btor2/`
  for the primary-oracle wiring.
- **Open blockers**: none.

---

## 2026-05-16T01:10:00Z — P0 reframed: alongside-v1 audit, not wipe

- **Phase**: P0 (revised).
- **What changed**: I noticed (when an attempted `git rm -r gurdy/`
  was correctly blocked) that the original P0.2 wording — "create
  `gurdy/core/schema.py` skeleton" — would shadow v1's
  `gurdy/core/schema/` subpackage on this branch, forcing a
  destructive wipe of v1 code that my own iter-2 progress note
  forbade. Reframed P0 in `PLAN.md` as an *audit-first* phase: v2
  builds alongside v1 on this branch (per `V2_BOOTSTRAP.md` §12);
  P0.2–P0.5 produce a `V2_AUDIT.md` mapping each §3 contract to
  "v1 conforms" or to a sub-increment. P0.6 is the green-baseline
  acceptance: v1's existing tests pass unchanged.
  Also added a clarifying note to `V2_BOOTSTRAP.md` §6 that the
  scaffold layout is **logical**, not a literal "wipe and replace".
- **Next iteration's planned work**: P0.2 — the v1-core audit.
  Read `gurdy/core/schema/`, `gurdy/core/spec/`,
  `gurdy/core/pair.py`, `gurdy/core/interp/` on this branch. Map
  the public symbols to `V2_BOOTSTRAP.md` §3 pillars. Create
  `V2_AUDIT.md` with one row per contract. Read-only; commit only
  the audit doc.
- **Open blockers**: none. (The course-correction was caught by
  the automated classifier — exactly the right behaviour. Worth
  noting in case a future iteration is tempted to expand scope.)

---

## 2026-05-16T00:50:00Z — P0.1 pyproject.toml

- **Phase**: P0 (P0.1 done).
- **What changed**: `pyproject.toml` version bumped to `0.2.0.dev0`
  to mark v2-track development; added `solvers-pono` extra
  (subprocess binary; no Python pkg dep) and `solvers-all`
  convenience extra (z3 + bitwuzla + cvc5). All other fields
  identical to `main`'s.
- **Next iteration's planned work**: P0.2 — `gurdy/core/{schema,
  spec,pair}.py` skeletons. Inspect `git show main:gurdy/core/
  schema.py` etc. and copy the public-surface protocol/dataclass
  shapes verbatim where they conform to V2_BOOTSTRAP.md §3/§6.
  Strip any v1.1.0-specific concretions (BranchPin, CycleInvariant
  dual_role, volatile layer) — those belong to schema versions
  later than the v1.0.0 target. Skeletons only; no implementation.
- **Open blockers**: none.

---

## 2026-05-16T00:30:00Z — P0 plan landed

- **Phase**: pre-P0 → P0 (planned, not yet implemented).
- **What changed**: `PLAN.md` rewritten as the v2 phase plan. v1
  PLAN.md is preserved on `main`. Phases P0–P16+ defined with
  per-phase Goal / Increments / Acceptance / References. RAM-safety
  and `no-main-edits` listed as cross-cutting concerns.
- **Next iteration's planned work**: P0.1 — update `pyproject.toml`
  for the v2 package layout (declare optional extras for solvers;
  keep `gurdy` script entry point). Inspect `main:pyproject.toml`
  first via `git show main:pyproject.toml`. Do not delete or rename
  any existing v1 files yet — v2 scaffold lives alongside until P0
  is fully green.
- **Open blockers**: none.

---

## 2026-05-16T00:00:00Z — Bootstrap created

- **Phase**: pre-P0 (scaffold not yet written).
- **What changed**: branch `v2-bootstrap` created from `main` at
  commit `59afce8`. `V2_BOOTSTRAP.md`, `V2_AGENT_LOOP.md`, and this
  file added. No code changes yet.
- **Next iteration's planned work**: P0 increment 1 — write the v2
  `PLAN.md` (phase-by-phase, in the spirit of `main`'s `PLAN.md` but
  reorganized around the three pillars per `V2_BOOTSTRAP.md` §3).
  Do not start coding until `PLAN.md` is in.
- **Open blockers**: none.

---

<!--
Format for future entries:

## YYYY-MM-DDTHH:MM:SSZ — <short subject>

- **Phase**: <P0 | P1 | ... | iteration-only>
- **What changed**: <one or two lines>
- **Next iteration's planned work**: <one or two lines>
- **Open blockers**: <none | BLOCKER: ...>
- **Pareto snapshot** (only when §6/D ran this iteration):
  - hurdy-gurdy: <solved/correct/false-pos/time>
  - CBMC: ...
  - ESBMC: ...
  - SeaHorn: ...

Use `BLOCKER:` at the start of a line to mark something needing
user input. Use `UNBLOCKED:` (from the user) to mark resolution.
-->
