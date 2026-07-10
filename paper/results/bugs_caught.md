# Bugs the square caught

Concrete defects found by hurdy-gurdy's cross-checking architecture — the
commuting-square oracle, the external differentials (sail_riscv_sim, CBMC,
pinned CPython), solver corroboration, branch cross-checks, witness replay,
determinism (twice-and-diff), and coverage probes — mined from the repository
history and docs.

**Method.** Searched `git log --all` (675 unique commits across `main`, `v2`,
`v3`, and tag `v2-final`) for fix-type subjects and bodies mentioning
divergence/mismatch/disagreement/surfaced/vacuous/latent/silently; read the
full commit bodies of every candidate (`git log --format=full -1`); grepped
`HANDOFF.md`, `pairs/*/README.md`, `ARCHITECTURE.md`, the v2 append-only log
(`git show v2-final:V2_PROGRESS.md`), and `tests/` for regression narratives.
For each incident the *catching mechanism* is taken from the primary record
(commit body or progress log), not inferred; where the record is ambiguous the
incident is marked accordingly. Incidents caught by ordinary unit tests during
development are excluded from the main list (one is noted at the end for
proportion).

A note on generations: `main` contains the full v1/v2 lineage plus the current
v3-root code; a few cited commits live only on branch `v3` (noted inline).
All SHAs below resolve in this repository.

---

## I1. riscv-btor2 translator emitted bv64-sorted `and/or/xor` over bv1 operands (malformed BTOR2)

- **Defect in:** `riscv-btor2` translator (`gurdy/pairs/riscv_btor2/translation/exprs.py:218`).
- **What:** The expression dispatcher hardcoded result sort `bv64` for
  `and/or/xor`. When the operands were bv1 predicates (e.g. the `bad` clause's
  AND over two `eq` results) the emitted BTOR2 was malformed:
  `90 and 4 87 89` — result sort bv64 with bv1 operands.
- **Caught by:** the **strict in-process BTOR2 evaluator** during the
  witness-replay / alignment walk (`replay_witness` + `oracle_align`), i.e. the
  square's reasoning-interpreter leg. The commit is explicit that "real
  solvers tolerate it; the in-process simulator rejects it. The strict
  evaluator catches it (this was its design intent)." Autonomy protocol
  escalated the fix to the user (translator emission changes were not
  autonomous-safe).
- **Localized to:** the specific emitted nid (the bad-clause AND), sort
  hardcoding at `exprs.py:218`; after the fix, `oracle_align` passed on the
  three previously-erroring tasks (0002, 0007, 0017).
- **Evidence:** commits `79ef208` (diagnosis + escalation), `2126126` (v2 fix
  after UNBLOCK), `2ad3ac2` (same fix on the v1 line); follow-up class audit
  `bad769f` found **one more latent instance** (`exprs.py:235`,
  `not_("bv1", …)` over a bv64 const — unreached in the corpus at the time).
  Narrative: `git show v2-final:V2_PROGRESS.md` (P1.3/P1.3a sections).

## I2. riscv-btor2 translator: LBU/LHU/LWU loads not zero-extended to bv64 (+ a z3-adapter slice bug)

- **Defect in:** (a) `riscv-btor2` translator (`translation/library.py`
  load path); (b) the `btor2_to_z3` solver adapter.
- **What:** (a) `_load_bytes_le` returns bv(8·n); the unsigned-load branches
  LBU/LHU/LWU never extended the bv8/bv16/bv32 result to bv64 (the signed
  branches did sign-extend), so the destination-register dispatch ITE mixed a
  bv8/16/32 then-arm with a bv64 else-arm — a genuine **zero-extension bug**.
  (b) `btor2_to_z3._eval_op` eagerly evaluated *every* argument after the
  result sort as a nid, but `slice`/`sext`/`uext` carry integer indices — a
  low-bit slice (`lo=0`) crashed with `KeyError: 'no builder for nid 0'`, and
  other small integers "would have silently looked up the wrong node".
- **Caught by:** the **solver leg of the square** during empirical validation
  of the riscv-btor2 corpus through the dispatcher: z3 rejected the malformed
  ITE with `Sorts (_ BitVec 8) and (_ BitVec 64) are incompatible` (tasks
  0005 LBU-after-SB, 0010 LBU-after-SH); the adapter bug crashed on tasks
  0003 (ADDIW) and 0006 (SLL). After the fix, all 18 corpus tasks dispatch to
  the expected verdict (was 14, with 4 crashes) and determinism is unchanged
  (18/18 byte-identical recompile).
- **Localized to:** named tasks and named lowering sites in the commit body.
- **Evidence:** commit `d733a5e` ("fix: z3-bmc lowering bugs surfaced by the
  riscv-btor2 corpus").

## I3. BTOR2 emitter: `init` value nid out-ranked the state nid — every stateful pair affected

- **Defect in:** the shared BTOR2 `Builder` (emitter used by riscv/sail/ebpf
  -btor2 — "every stateful pair").
- **What:** The Builder declared states before their constant init values, so
  emitted `init` lines had `nid(value) > nid(state)` — which "every conformant
  BTOR2 tool rejects but the z3 bridge tolerated". A wrong-encoding bug that a
  single lenient solver hid.
- **Caught by:** **solver corroboration** — wiring the second and third
  engines (pono, btormc) for the native-vs-bridged BTOR2 check made the
  latent malformation manifest as hard rejections. Fixed with a stable,
  idempotent renumbering pass (`btor2.model.canonicalize`); the reachable
  corpus then agreed on host btormc and the pinned pono. The same defect
  class had earlier been worked around at the adapter (bench line): pono
  v2.0.0 "rejects every hurdy-gurdy emitted model" for the same ordering
  reason, surfaced during certificate prototyping.
- **Localized to:** the init-emission ordering in the Builder; per-engine
  reject messages.
- **Evidence:** commit `c6ee5b8` (step 3), `HANDOFF.md` ("Wiring a real
  native checker surfaced a latent defect the z3 bridge tolerated");
  adapter-side precursors `9ee953c`, `d76d5f3` (v2 line).

## I4. wasm-btor2: `local.get` wrote a bv32 node into the bv64-element stack

- **Defect in:** `wasm-btor2` translator (stack write in the `local.get`
  lowering).
- **What:** `local.get` called `b.write()` directly with a bv32 local node
  into the bv64-element stack array instead of zero-extending via
  `_stack_push_i32()` (the pattern every other i32-producing instruction
  used) — a **sort mismatch / missing zero-extension**.
- **Caught by:** the **solver leg** — a z3 sort-mismatch exception at BMC
  time; 5 pre-existing z3 solver-test failures were all this one bug
  (491 passed / 0 failed after the fix).
- **Localized to:** the one stack-write call site.
- **Evidence:** commit `a3ae15e` ("wasm/P18: fix local.get bv32→bv64 sort
  mismatch in stack write").

## I5. evm-btor2 evaluator: array writes unconditionally masked with `& 0xFF` (bv256 stores truncated to 8 bits)

- **Defect in:** the EVM pair's BTOR2 **evaluator** (reasoning-side
  interpreter, `evaluator.py` `write` op).
- **What:** Every array store was masked to 8 bits regardless of element
  sort, silently truncating bv256-element stack writes — a wrong-width bug in
  the strict evaluator itself.
- **Caught by:** cross-checking while authoring the signed-comparison corpus
  seed (SGT signed-vs-unsigned semantics): the evaluator's replay disagreed
  with correct EVM semantics on the new seed. Notably, **three existing unit
  tests had been written *against the buggy behaviour*** and had to be
  corrected — the plain unit tests had codified the bug; widening the
  semantic surface exposed it. (The record does not name the exact failing
  check, so the mechanism attribution is *partial*; the defect and its
  unit-test blind spot are fully documented.)
- **Localized to:** the `write` op; element width now taken from
  `array_meta`.
- **Evidence:** commit `614e266` ("evm/p39: SGT signed-positive seed +
  evaluator write-mask bug fix").

## I6. Witness carry-back (lifter) silently zero-filled init-pinned registers

- **Defect in:** the v1 **lifter** (the carry-back `L` for BMC witnesses),
  `_initial_state_from_witness`.
- **What:** z3's BMC witness *omits* values for states pinned by BTOR2 `init`
  clauses (they are determined). The lifter's silent zero-fallback therefore
  misread the entry state of **every** RegisterInit-pinned task (0201 plus
  0020/0021/0023/0027/0030) — lifted traces showed entry registers as 0
  regardless of the spec's pins.
- **Caught by:** the **witness-replay / anchor-audit machinery**: a chain of
  witness-metadata mismatches across bench iterations 26→40 (audit_anchors
  disagreeing with the pinned `halted_step`, per-step register plumbing) that
  "ultimately uncovered this v1 lifter bug that's been silently misreading
  pinned tasks". Fix: resolve init clauses from the parsed BTOR2 model and
  merge them under the witness values.
- **Localized to:** step-0 registers of the lifted trace; verified on 0201
  (regs x5..x8 = 1,100,0,40 at step 0; bmc_step=96 within tolerance).
- **Evidence:** commit `8274a31`; narrative in
  `git show v2-final:V2_PROGRESS.md` (iter-40 section).

## I7. Bench oracle's source leg ignored RegisterInit pins — spurious FAIL (0200)

- **Defect in:** the bench framework oracle's source-side binding
  (`bench/riscv-btor2/oracle.py`, v2 tree).
- **What:** Same bug class as I6 on the *other* leg of the square: the oracle
  constructed a default (empty) `RiscvInputBinding`, so the source
  interpreter ran from all-zero registers although the spec pinned
  x5=3, x6=2, x7=7; `mul` produced 0·0=0 at step 1 and the property
  "violated" spuriously.
- **Caught by:** the **framework-oracle corpus run** — disagreement with the
  task's expected label (spurious FAIL on 0200); after the fix, zero FAILs on
  the full corpus.
- **Localized to:** step 1, the mul result observable.
- **Evidence:** commit `493fad5` (v2 line; also `3dcaf06`);
  `V2_PROGRESS.md` "Fix #1: 0200 oracle.py (same bug class as 0201)".

## I8. False negative: default BMC bound hid a step-93 violation (0201) — "bounded unreachable" conflated with "unreachable"

- **Defect in:** verdict semantics of the BMC path (lifter mapped "no
  violation within bound k=20/30" to "unreachable") plus the default bound.
- **What:** Task 0201 needs 93+ steps (40 iterations of `x5 *= 100` to bv64
  wraparound); at the default bound the pipeline reported **unreachable for a
  reachable-expected task — a silent soundness bug (false negative)**. The
  v2 retrospective explicitly grades the pre-fix state a soundness failure
  and the post-fix residue (anchor metadata mismatch) merely informational.
- **Caught by:** the **framework oracle vs. the corpus's expected label**
  (`test_bench_framework_oracle_reports_no_failures` flagged the
  misclassification).
- **Localized to:** the bound (30 → 128) and the unreachable-verdict mapping.
- **Evidence:** commits `3c63fa0` (diagnosis), `3dcaf06` (bound bump);
  `V2_PROGRESS.md` iter-26/32/35 retrospective sections.

## I9. The RISC-V ⟂ sail_riscv_sim differential was passing vacuously

- **Defect in:** the ISA-differential **harness itself** (a check-of-the-check).
- **What:** With no trace flag, `sail_riscv_sim` emits nothing, so
  `align([], [])` was trivially ok — the flagship external differential had
  been green without comparing anything.
- **Caught by:** discharging the formerly Docker-gated steps and inspecting
  what the check actually did; hardened by defaulting `--trace`, binding to
  the HTIF `tohost` symbol, **refusing an empty oracle stream**, and linking
  test ELFs at the model's base. Then "verified step-for-step over the
  slice."
- **Localized to:** the empty oracle stream (now a hard error).
- **Evidence:** commit `c6ee5b8` (steps 1–2), `HANDOFF.md`.

## I10. btormc witness path produced an empty witness that "replays to nothing"

- **Defect in:** the native-checker adapter / witness generation
  (btormc invocation + checker selection).
- **What:** The image's btormc 3.2.4 defaults `--trace-gen-full` off, so for
  a no-input system it emitted only `sat`/`b0` with no state lines — an empty
  witness; separately `find_native_checker()` could pick pono, whose witness
  is not the `.wit` format the parser expects.
- **Caught by:** the **in-image suite + witness replay** (the positive
  proved-side check): `test_btor2_witness::test_counter` failed inside the
  pinned image while passing on the host — an environment-differential catch
  of a build-dependent vacuity.
- **Localized to:** the two adapter gaps (flag default; checker selection).
- **Evidence:** commit `05140b0` ("Fix btormc witness generation (surfaced by
  the in-image suite)").

## I11. ELF header bytes fed to the translator broke the square on real gcc binaries

- **Defect in:** the shared RISC-V ELF loader's code-region bounds
  (`gurdy/languages/riscv/elf.py`), as consumed by the riscv-btor2
  translator's whole-region dispatch.
- **What:** Bounding the code region by PF_X *segments* included the mapped
  ELF header, so header bytes were decoded as instructions by the translator
  — "fine for the interpreter (it halts at ecall) but it **broke the
  riscv-btor2 square on real binaries**."
- **Caught by:** the **commuting-square oracle** the first time an arbitrary
  `riscv64-unknown-elf-gcc` binary (loop + branch) was pushed through the
  square (asymmetric failure of the two legs). Fixed with section-aware
  (`SHF_EXECINSTR` PROGBITS) bounds + symbol-aware entry.
- **Localized to:** the code-bounds computation (header region).
- **Evidence:** commit `1471141` ("Symbol/section-aware ELF code bounds: real
  gcc binaries through the square").

## I12. btor2-smtlib bridge silently dropped BTOR2 `constraint` lines — a soundness leak

- **Defect in:** the `btor2-smtlib` bridge translator (hub bridge).
- **What:** BTOR2 `constraint` directives were silently not asserted in the
  unrolled SMT-LIB encoding — an under-constrained encoding that could report
  spurious reachability (the commit calls it "a soundness leak"); `redxor`
  was additionally a hard-abort hole.
- **Caught by:** the **coverage probe**: building the spec-derived
  operator/sort/directive inventory (denominator) and pushing bridge coverage
  to 56/56 exposed the two holes ("Reaching it closed two holes").
- **Localized to:** the `constraint` directive (now asserted in every
  unrolled state) and the `redxor` lowering.
- **Evidence:** commit `60847ea` ("Build the shared SMT-LIB interpreter; give
  btor2-smtlib a 56/56 inventory").

## I13. Committed spec pinned the wrong trap PC (0303) — stale by one instruction

- **Defect in:** corpus task metadata (`0303-c-ptr-past-end` committed
  `spec.json`): the property pinned `eq(pc, 0x10054)` but a fresh
  pinned-toolchain compile of the task's own `task.c` puts `trap` at
  `0x10058` — the property targeted the wrong PC.
- **Caught by:** the **reproducible-compile discipline**: recompiling the
  task under the pinned toolchain and re-running the oracle end-to-end
  (`oracle.py` then reports expected=unreachable, check=holds). The same
  commit fixed a corpus guard that had been passing only due to
  sibling-built disk state.
- **Localized to:** the trap-PC constant in the spec.
- **Evidence:** commit `1a1b5a3` ("fix(bench): correct corpus guard to
  authored files; rebuild + fix 0303").

## I14. Human-authored ground truth off by 5: 0023 `halted_step` 17 → 22

- **Defect in:** corpus task metadata (`0023-stride-3-loop` `task.toml`):
  the shipped `halted_step = 17` was "an author's eyeball estimate"; the
  loop actually takes 7×3+1 = 22 transitions.
- **Caught by:** **agreement of the independent machine checks against the
  human label**: the BMC engine reports step 22 (witness `s22_*` keys) and
  the §9.10 oracle reports `violated@22` — both disagree with the shipped 17
  by 5, outside tolerance 3. Surfaced when a benchmark LLM read the loop
  correctly, answered 22, and was graded "witness-mismatch".
- **Localized to:** the anchor step; per-iteration arithmetic recorded in the
  task notes.
- **Evidence:** commit `7f4f04d` ("corpus: 0023-stride-3-loop halted_step
  17 → 22").

## I15. CBMC c-diff route disagreements: genuine C-UB vs RV64-defined divergences (and a CBMC false positive)

- **Defect in:** not hurdy-gurdy — real **semantic divergences between the
  C-source route and the lowered RV64 route**, plus a baseline false
  positive.
- **What:** On `0117-c-int-min-div-neg-one` (`INT_MIN / -1`, textbook signed
  overflow UB) CBMC reports *reachable* (false positive — UB treated
  conservatively) while the RV64 route reports *unreachable* (correct: `divw`
  returns INT_MIN as a defined sentinel); ground truth per task.toml is
  unreachable. On svcomp task 0277 the differential surfaces genuine C-UB
  (`1 << s` for s ≥ 32 and `n % 0`, both RV64-defined) as an
  expected-divergence. The c-diff machinery classifies every disagreement:
  UB-checks-fire ⇒ documented C-undefined-but-RISC-V-defined; a value
  disagreement with no UB ⇒ a fault localized to the compile hop.
- **Caught by:** the **CBMC c-diff branch cross-check** (two routes to the
  same question), with the UB-vs-fault classifier adjudicating.
- **Localized to:** the property-evaluation site of each task; per-task
  classification recorded.
- **Evidence:** commits `44b5894` (the 0117 wedge; also
  `INITIAL_FINDINGS.md` in the v2 tree), `47ff76f` (0277 and the 0115
  expected-divergence), `HANDOFF.md` §5, `pairs/c-riscv/README.md`.

## I16. The CBMC differential's dialect had drifted — svcomp verdicts were meaningless

- **Defect in:** the c-diff **harness** (trap-idiom rewrite in
  `to_cbmc_dialect`), a check-of-the-check.
- **What:** The rewrite matched only literal `if (cond) trap();`, missing the
  svcomp extractor's macro shim and `goto ERROR` idiom — "every svcomp task
  got a mis-rewritten dialect and a meaningless verdict"; CBMC's default
  unwinding assertion additionally produced spurious FAILED on `while(1)`
  tasks. Root cause of the silence: the bench emitter had drifted from the
  differential's dialect ("that drift is what hid this bug"); the fix makes
  the bench delegate to the hop's single dialect function.
- **Caught by:** validating the differential across both task families
  (spurious FAILED on 0275/0276; uninformative verdicts on svcomp shapes).
- **Localized to:** the dialect rewrite; validated per-task
  (agree/expected-divergence matrix in the commit body).
- **Evidence:** commit `47ff76f` ("c-riscv: fix the CBMC dialect for the
  svcomp task shape").

## I17. evm-btor2 JUMP/JUMPI: underflow-halt row diverged on `pc` — caught by step alignment during widening

- **Defect in:** the in-progress `evm-btor2` translator lowering of
  `JUMP`/`JUMPI` (control-flow widening round).
- **What:** Every existing opcode advances `pc := off+1` whenever *active*
  (even on an underflow halt); the first JUMP/JUMPI lowering wrote pc only on
  the non-underflow path, so the underflow-halt row **diverged on `pc`**
  between the source interpreter and the reasoning trace. Fixed as
  `next_pc := ite(active, ite(underflow, off+1, resolved), prev)`.
- **Caught by:** the **commuting-square step alignment** during development
  of the widening (recorded in the pair README's narrative of the round).
- **Localized to:** the `pc` observable on the halt-edge row.
- **Evidence:** `pairs/evm-btor2/README.md` (control-flow widening section,
  "otherwise the underflow-halt row diverged on `pc`"); commit `4482364`.

## I18. v3 gate defects: an unrun independence audit passed silently; exception-class aliasing crashed the gate

- **Defect in:** the v3 merge-gate machinery itself (branch `v3` only).
- **What:** (a) `merge_policy` blocked only on an audit that explicitly
  FAILED; an *unrun* audit (`None`) passed silently — "not run" treated as
  evidence of independence. (b) `_load_oracle()` re-exec'd the oracle module
  per call, minting fresh `SailUnavailable` classes, so an `except` clause
  silently missed the exception and the whole gate crashed on Sail-less
  runners only.
- **Caught by:** (a) design review of the gate contract; (b) **CI on a
  Sail-less runner** (an environment-diversity catch — local runs with Sail
  present never hit it).
- **Evidence:** commits `d607e01`, `f0700c4` (branch `v3`).

## I19. `check_drat` accepted every checker outcome — "NOT VERIFIED" contains "VERIFIED"

- **Defect in:** the `proved`-tier checker **adapter**
  (`gurdy/solvers/proved.py` `check_drat`), a check-of-the-check.
- **What:** The adapter tested `"VERIFIED" in output.upper()`; `drat-trim`
  reports failure as `s NOT VERIFIED`, which contains the substring — so
  every check, sound or bogus, returned True. Latent since the pipeline was
  written: on checker-less hosts the call raised `CheckerUnavailable` before
  parsing, and in-image positive tests used real certificates, which do
  verify — no execution path ever produced a should-fail parse until a
  negative control ran.
- **Caught by:** the **negative control** while validating the checker on
  the host (2026-07-02, installing pinned `drat-trim` @ `2e3b2dc`): a bogus
  refutation of a *satisfiable* CNF — for which no valid refutation exists —
  came back "verified". (First mutation attempts — flipping a literal
  mid-proof, an empty-clause-only proof against the propagation-refutable
  UNSAT instance — were themselves *legitimately* verified, a reminder that
  proof mutations are not sound negative controls; the satisfiable-formula
  control is.)
- **Localized to:** the status-line parse; fixed to match the exact
  `s VERIFIED` line, with the two controls added as permanent tests
  (`tests/test_proved.py::TestCheckerControls`).
- **Evidence:** the 2026-07-02 host-checker commit (fix + regression tests
  + `paper/results/data/proved.json` recording the controls).

---

## I20. riscv-sail dropped the program's initial memory — loads read 0 on the Sail route

- **Defect in:** the `riscv-sail` translator (`translate.py`): the emitted
  Sail object carried `words`/`entry`/`init_regs`/`property` but **not** the
  image's memory byte map.
- **What:** Loads from initialized addresses (any `.data`, or code bytes the
  program reads) returned the stored value in the RISC-V reference
  interpreter and `0` on the Sail route — accepted, silently wrong, and a
  latent cross-route disagreement for any solver question that loads from
  pre-initialized memory. Invisible to acceptance-only coverage (the probe
  *translates* fine) and to the existing branch questions (which only load
  what they first store).
- **Caught by:** the first run of the **conjoined coverage measurement**
  (Definition 4.6's covered∧faithful, run probe-by-probe through the new
  per-pair square): all seven load-family probes (LB/LH/LW/LD/LBU/LHU/LWU)
  diverged at step 0 on the loaded register.
- **Localized to:** the missing `mem` field; fixed by embedding the image's
  byte map in the Sail object (translator 0.1 → 0.2), with the load-family
  squares as regression tests (`tests/test_coverage.py`).
- **Evidence:** the 2026-07-03 conjoined-coverage commit;
  `results/data/capability.json` (`riscv-sail.conjoined` 96/96 after).

---

## I21. All three BTOR2 lowerings modeled off-code PC as *stuck*, not halted

- **Defect in:** the `riscv-btor2`, `sail-btor2` (RISC-V arm), and
  `ebpf-btor2` translators — the same semantic edge, independently wrong the
  same way in three LLM-written lowerings (a common-mode pattern worth
  naming: all three modeled only the instructions, not the fetch miss).
- **What:** Every reference interpreter treats a program counter that
  matches no instruction (run off the end, jump past the image) as a
  **halt**; the BTOR2 models left `halted` false and the machine stuck,
  so traces diverged on the `halted` observable one step after any taken
  jump whose target leaves the code. The `aarch64-btor2` lowering had the
  off-code halt from the start — the defect was in the three that didn't.
- **Caught by:** the first run of the **conjoined coverage measurement**:
  every taken-jump/taken-branch probe (JAL/BEQ/BGE/BGEU/C.J/C.BEQZ on
  RISC-V, all 21 taken-jump probes on eBPF) diverged at step 1 on `halted`.
- **Localized to:** the missing off-code transition; fixed with an
  exact-match `in_code` disjunction over the decoded instruction addresses
  (`riscv-btor2` 0.1 → 0.2, `sail-btor2` 0.2 → 0.3, `ebpf-btor2`
  0.4 → 0.5), taken-jump squares as regression tests.
- **Evidence:** the 2026-07-03 conjoined-coverage commit; branch agreement
  re-run green across all 12 questions after the fix.

---

## I22. The SD probe clobbered its own ECALL — an unrunnable probe counted as covered

- **Defect in:** the RV64IMC probe inventory itself (a check-of-the-check):
  `SD`'s probe stored 8 bytes at address 0, overwriting both its own
  encoding and the ECALL terminator at bytes 4–7.
- **What:** Under acceptance-only measurement the probe "covered" SD — the
  translator accepts it — but the *reference interpreter cannot even run
  it* (the clobbered ECALL decodes as `c.illegal`), so the faithfulness
  half of the conjunction was untestable for that construct and no square
  had ever executed on it. The narrower stores (SB/SH/SW) missed the
  terminator by width, hiding the pattern.
- **Caught by:** the first conjoined-coverage run (the square raised the
  interpreter's typed abort instead of aligning).
- **Localized to:** the probe program; store probes now write at offset 16,
  past the code (inventory moved to `gurdy/languages/riscv/inventory.py`).
- **Evidence:** the 2026-07-03 conjoined-coverage commit.

---

## I23. Degenerate probe operands: signedness and strictness invisible to the squares

- **Defect in:** the RV64IMC probe inventory again (a check-of-the-check,
  I22's sibling): ALU/compare/branch probes ran their construct on
  degenerate operands (`x0, x0` — all zeros), on which `slt` and `ult`
  agree, `srl` and `sra` agree, and equality-vs-strictness is moot.
- **What:** A systematically wrong translator that emits `sra` for `srl`
  (or confuses signed/unsigned compares) passes the entire conjoined
  probe suite: every probe's square commutes because the operands never
  exercise the difference. The suite's verdict "96/96 conjoined" was
  true but weaker than it reads — faithfulness *on the probes*, and the
  probes underdetermined the constructs.
- **Caught by:** the **fault-injection experiment** (escape-rate
  measurement): in round 1, both `srl->sra` mutants escaped all three
  gates; hardening the probes with mixed-sign operands (-5 vs 3) moved
  36 → 50 of the catches to the square layer but let `ult->ulte`
  (strictness) escape round 2 — equality-vs-strictness is observable
  only at *equal* operands. Round 3's probes run an equal-operand and a
  mixed-sign instance per construct; 0 of 55 mutants escape.
- **Localized to:** the probe operand choices; compare/branch probes now
  carry both operand classes (`gurdy/languages/riscv/inventory.py`,
  `_pcmp`/`_pcmpi`/`_pbr`).
- **Evidence:** the 2026-07-03 fault-injection commit;
  `results/data/escape.json` (round-3 rows); rounds 1-2 counts in the
  paper's escape-rate subsection.

## I24. Same-sign compare vectors: slice, benchmark, and differential all blind to SLT signedness

- **Defect in:** the compliance slice's arithmetic program (a
  check-of-the-check, I23's sibling one level up): its `SLT`/`SLTI` cases
  used same-sign operands, on which signed and unsigned comparison agree.
- **What:** In round 1 of the **common-mode (both-leg) fault-injection
  experiment** (2026-07-09), the `slt-as-sltu` misreading — injected into
  BOTH the reference interpreter and the riscv-btor2 translator — escaped
  every gate: the squares are structurally blind (both legs wrong
  identically), the authored branch questions exercise no compare, the
  benchmark's cross-route disagreement cannot fire when no derived value
  discriminates signedness, and the Sail differential's executed streams
  agree wherever operands are same-sign. The platform's first measured
  full-stack escape. (The five sibling misreadings were all caught outside
  the squares: four by cross-route disagreement at the benchmark, one
  — `and-as-or` — only by the external Sail differential.)
- **Caught by:** the common-mode experiment itself (the escape is the
  catch — an instrument-adequacy defect, not a translator defect).
- **Localized to:** the slice's compare vectors; fixed by adding
  mixed-sign and equal-operand `SLT` cases to `rv64ui-arith` (upstream
  `rv64ui-slt`'s vectors) — the ratchet's answer, after which round 2
  catches the mutant: the discriminating vectors surface in the executed
  stream, so the **Sail differential** fires at `rv64ui-arith` (step 49,
  x5); the benchmark's per-register value questions remain blind to it,
  a stated limitation of value sampling.
- **Evidence:** `results/data/common_mode_round1.json` (the escape),
  `results/data/common_mode.json` (round-2 catch), `tools/riscv_slice.py`.

---

## Honest negatives, blind spots, and disconfirmations

- **A shared misreading the square could not catch.** Both the RISC-V
  interpreter *and* the riscv-btor2 translator silently mis-decoded MUL
  (funct7=0x01) as ADD — since both legs agreed, the square was blind; the
  bug was found by manual audit during widening and both sides now hard-abort
  on unknown funct7 (commit `e215ff4`). The architecture's later answer to
  this class is *external* anchoring: `decode_vs_sail` validates the decoder
  against 610 real Sail-emitted words (0 divergences), and the independent
  RV64C decompressor is cross-checked construct-by-construct (`9f37f65`).
- **The architecture also disconfirms.** A 2026-06-06 session finding
  ("translator emits a slice whose sort width is the register width; pono
  rejects, bitwuzla accepts silently") was investigated and shown to be a
  stale-cache/misattribution artifact — no such bug existed; `Builder.slice`
  was hardened so the class cannot regress (commit `0aeeef4`).
- **Clean differential campaigns (no divergences found):** in-house
  RISC-V-vs-Sail fuzz, 300 seeded RV64IMC programs, 0 divergences
  (`c769f5e`); Csmith C differential (native gcc vs pinned cross-gcc +
  shared interpreter), 10-seed campaign, 0 mismatches (`b09b6a7`);
  riscv-tests slice 10/10 with riscv-diff ok (`c6ee5b8`); sail_cross
  reference validation, 463 cases, 0 divergences (v3 branch, `eacb7ed`
  lineage). The harnesses carry positive controls ("a corrupted own emission
  is caught", "catches a wrong shamt width"), so these greens are non-vacuous.
- **Caught by ordinary tests, not the architecture** (excluded from the table
  but counted for proportion): aarch64-btor2 translator registered as a plain
  function instead of the `Translator` protocol object — 9 z3-dependent tests
  failed once z3 4.16.0 appeared (`b6c4ee2`); assorted CI/adapter fixes
  (`bdf16c9`, `27e5e30`, `eff6cbd`, `dc07042`).

## Proportion

Across all refs the repository has **675 unique commits**; **116** mention
"fix" somewhere in the message. Filtering to commits whose *subject* is a
fix/correction and that touch runtime code (translators, interpreters, solver
adapters, oracle/bench harness — excluding docs and corpus data) leaves
roughly **21** fix commits; the incident list above accounts for the large
majority of the distinct defects behind them (I20–I24 postdate that mining
pass — they were caught by the conjoined-coverage measurement and the
fault-injection experiments added 2026-07-03/09). Of the 24 incidents recorded
here, **15 were caught by the architecture's cross-checks** (square/alignment,
solver leg or solver corroboration, witness replay/anchor audit, framework
oracle vs label, c-diff route disagreement, coverage probe, conjoined
coverage/square, reproducibility, in-image environment differential),
**7 were check-of-the-check repairs**
(I9, I16, I18, I19, I22, I23, I24 — the architecture auditing its own instruments,
mostly caught because a check was vacuous rather than weak or wrong), **1** was
caught by machine-vs-human-label disagreement (I14), and **1** is partially
attributed (I5). One known blind-spot instance (shared MUL/ADD misreading) was caught by
audit, not the square.

## Summary table

| # | Incident | Defect location | Caught by | Localized to | Evidence |
|---|----------|-----------------|-----------|--------------|----------|
| I1 | bv64 sort hardcoded for and/or/xor over bv1 | riscv-btor2 translator (exprs.py) | strict BTOR2 evaluator on witness replay / alignment walk (square) | emitted bad-clause AND nid; exprs.py:218 | 79ef208, 2126126, 2ad3ac2, bad769f |
| I2 | LBU/LHU/LWU missing zero-extension; z3 adapter mis-evals slice/sext/uext int args | riscv-btor2 translator (library.py); btor2_to_z3 adapter | solver leg: z3 sort rejection / crash on corpus dispatch | tasks 0003/0005/0006/0010; named lowering sites | d733a5e |
| I3 | init value nid out-ranks state nid (malformed BTOR2, z3-tolerated) | shared BTOR2 Builder (all stateful pairs) | solver corroboration (pono/btormc reject) | init emission ordering | c6ee5b8, HANDOFF.md; 9ee953c, d76d5f3 |
| I4 | local.get writes bv32 into bv64 stack | wasm-btor2 translator | solver leg: z3 sort-mismatch at BMC | local.get stack write | a3ae15e |
| I5 | array write masked with & 0xFF (bv256→8 bits) | evm-btor2 BTOR2 evaluator | cross-check while authoring signed-comparison seed (mechanism partially recorded); unit tests had codified the bug | evaluator write op | 614e266 |
| I6 | lifter zero-fills init-pinned registers omitted from z3 witness | witness carry-back L (v1 lifter) | anchor audit / witness-replay mismatch chain | step-0 registers; _initial_state_from_witness | 8274a31, V2_PROGRESS.md |
| I7 | oracle source leg ignores RegisterInit pins (spurious FAIL) | bench framework oracle (source binding) | framework oracle vs expected label | step 1 mul observable, task 0200 | 493fad5, 3dcaf06 |
| I8 | default BMC bound hides step-93 violation (false negative) | BMC verdict semantics + default bound | framework oracle vs expected label | task 0201, bound 30→128 | 3c63fa0, 3dcaf06, V2_PROGRESS.md |
| I9 | Sail differential vacuously green (empty traces align) | differential harness (check-of-check) | discharging gated steps; now refuses empty oracle stream | empty trace stream | c6ee5b8 |
| I10 | btormc emits empty witness; pono picked with wrong witness format | native-checker adapter / witness path | in-image suite + witness replay | --trace-gen-full default; checker selection | 05140b0 |
| I11 | ELF header bytes decoded as code | RISC-V ELF loader bounds (translator input) | commuting-square oracle on real gcc binary | code-region bounds | 1471141 |
| I12 | BTOR2 `constraint` silently dropped in SMT-LIB unrolling | btor2-smtlib bridge | coverage probe (56/56 inventory) | constraint directive; redxor | 60847ea |
| I13 | spec pins stale trap PC (one instruction off) | corpus spec.json (0303) | reproducible recompile + oracle re-run | trap PC constant | 1a1b5a3 |
| I14 | halted_step ground truth off by 5 | corpus task.toml (0023) | BMC engine + oracle agree against human label (bench sweep) | anchor step 17→22 | 7f4f04d |
| I15 | C-UB vs RV64 semantic divergences; CBMC false positive on 0117 | (real cross-route divergence; CBMC baseline) | CBMC c-diff route disagreement + UB classifier | property-evaluation site per task | 44b5894, 47ff76f, HANDOFF.md |
| I16 | c-diff dialect drift: meaningless svcomp verdicts, spurious FAILED | c-diff harness (check-of-check) | validating differential across task families | trap-idiom rewrite; unwinding assertions | 47ff76f |
| I17 | JUMP/JUMPI underflow-halt row diverged on pc | evm-btor2 translator (control-flow widening) | commuting-square step alignment during widening | pc observable on halt edge | pairs/evm-btor2/README.md, 4482364 |
| I18 | unrun independence audit passes; exception-class aliasing crashes gate | v3 merge-gate machinery | design review; CI on Sail-less runner | merge_policy; _load_oracle caching | d607e01, f0700c4 (branch v3) |
| I19 | check_drat matched substring VERIFIED — "s NOT VERIFIED" also accepted | proved-tier checker adapter (check-of-check) | negative control: bogus refutation of a satisfiable CNF | status-line parse in check_drat | 2026-07-02 host-checker commit; tests/test_proved.py TestCheckerControls |
| I20 | riscv-sail dropped initial memory — loads read 0 on the Sail route | riscv-sail translator | conjoined coverage (square per probe): 7 load probes diverge at step 0 | missing `mem` in the Sail object | 2026-07-03 conjoined-coverage commit; capability.json |
| I21 | off-code PC stuck-not-halted in three BTOR2 lowerings | riscv-btor2, sail-btor2 (RV arm), ebpf-btor2 | conjoined coverage: every taken-jump probe diverges on `halted` | missing fetch-miss→halt transition | 2026-07-03 conjoined-coverage commit; branch re-run green |
| I22 | SD probe self-clobbered its ECALL — unrunnable probe counted covered | RV64IMC probe inventory (check-of-check) | conjoined coverage: square hits typed interpreter abort | store-probe offsets; inventory now language-owned | 2026-07-03 conjoined-coverage commit |
| I23 | degenerate probe operands: srl/sra, slt/ult, strict/non-strict invisible to squares | RV64IMC probe inventory (check-of-check) | fault-injection experiment: srl→sra and ult→ulte mutants escaped all gates | probe operand classes (equal + mixed-sign per construct) | 2026-07-03 fault-injection commit; escape.json |
| I24 | same-sign compare vectors: slice + benchmark + Sail differential all blind to SLT signedness | compliance slice arith program (check-of-check) | common-mode experiment round 1: slt-as-sltu (both legs) escaped every gate | slice compare vectors (mixed-sign + equal SLT cases added) | common_mode_round1.json (escape); common_mode.json (round-2 catch) |
