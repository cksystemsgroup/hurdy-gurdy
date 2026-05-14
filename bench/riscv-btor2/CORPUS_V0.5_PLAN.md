# Corpus v0.5 plan — SV-COMP slice (pilot)

This plan covers the v0.5 corpus expansion described in
`EXTERNAL_BENCHMARKS_SURVEY.md` §"Recommended sequencing", step 1
(SV-COMP slice). v0.5 lands as **two stages**: a 10-task **pilot**
(this commit) and, conditional on the pilot's outcome, an 80–100
task **full slice** in a follow-up.

The pilot's purpose is to validate the rewriter end-to-end on a
mix of zero-nondet and entry-only-nondet tasks, *not* to grow the
benchmark's measurement weight. Numbers from the pilot should not
appear in §7-grade reporting; they are infrastructure validation.

## Provenance

External corpus: <https://github.com/sosy-lab/sv-benchmarks>
vendored as a git submodule at
`bench/riscv-btor2/external/sv-benchmarks/`, pinned to commit
`2e1723fde6aa65a250dcb677efa45edaa4b6b631` (master tip at the time
this pilot landed).

Sparse-checkout configuration (re-apply after a fresh
`git submodule update --init`, since sparse-checkout state isn't
committed):

```bash
git -C bench/riscv-btor2/external/sv-benchmarks sparse-checkout init --cone
git -C bench/riscv-btor2/external/sv-benchmarks sparse-checkout set \
    c/properties \
    c/loops c/bitvector c/bitvector-regression \
    c/loop-invariants c/loop-acceleration \
    c/ntdrivers-simplified c/locks
```

Per-task provenance is recorded in `task.toml` under
`[svcomp_extract]`: the SV-COMP source path, the sv-benchmarks
commit sha, the extractor version, and the SV-COMP `.yml` data
model. Each task directory also vendors `original.c` and
`original.yml` (the unrewritten SV-COMP source) so a reviewer can
diff the rewrite without leaving the bench tree.

## Defaults adopted (the four Q1–Q4 from the survey)

1. **`reach_error` → `trap`: source rewrite via macro.** The
   shim header pre-pended to every `task.c` defines
   `#define reach_error() trap()`, plus parallel macros for
   `abort()` and `__VERIFIER_assert(c)`. A linker `--defsym` alias
   was rejected because the SV-COMP source ships
   `void reach_error() { __assert_fail(...) }` *bodies* that would
   conflict with the alias; macros sidestep the redefinition
   issue.
2. **Optimization level: pinned to `-O0` for the pilot.** Matches
   what most SV-COMP authors test against and isolates rewriter
   bugs from optimizer-induced surprise. A future stage may sweep
   `-O0 / -O2` per the existing `010X-c-loopsum-oN` family.
3. **Nondet handling: entry-only.** A task is accepted only if all
   `__VERIFIER_nondet_*` calls appear in `main`'s prelude — i.e.,
   before the first control-flow keyword (`if/while/for/...`).
   Each such call becomes a positional argument to a renamed
   `task_main(<args>)`, threaded from `_start` through register
   declarations on `a0..aN` (uninitialized at entry, hence
   BMC-symbolic in the bench's encoding). Tasks with nondets
   inside loops or branches (e.g., `while
   (__VERIFIER_nondet_int())`) are rejected from the pilot.
4. **External corpus: vendored as a submodule.** The submodule
   keeps the bench small and re-pullable; sparse-checkout keeps
   the on-disk surface under 5 MB.

## The 10 tasks

| ID                                | Source                                        | Nondet | Bench expected | Engine       |
|-----------------------------------|-----------------------------------------------|--------|----------------|--------------|
| `0250-svcomp-implicit-uns-conv-1` | `c/bitvector-regression/implicitunsignedconversion-1.c` | 0 | reachable    | z3-bmc       |
| `0251-svcomp-implicit-uns-conv-2` | `c/bitvector-regression/implicitunsignedconversion-2.c` | 0 | unreachable  | z3-bmc       |
| `0252-svcomp-integer-promo-2`     | `c/bitvector-regression/integerpromotion-2.c` | 0      | unreachable    | z3-bmc       |
| `0253-svcomp-integer-promo-3`     | `c/bitvector-regression/integerpromotion-3.c` | 0      | reachable      | z3-bmc       |
| `0254-svcomp-signext-1`           | `c/bitvector-regression/signextension-1.c`    | 0      | reachable      | z3-bmc       |
| `0255-svcomp-signext-2`           | `c/bitvector-regression/signextension-2.c`    | 0      | unreachable    | z3-bmc       |
| `0256-svcomp-signext2-1`          | `c/bitvector-regression/signextension2-1.c`   | 0      | unreachable    | z3-bmc       |
| `0257-svcomp-signext2-2`          | `c/bitvector-regression/signextension2-2.c`   | 0      | reachable      | z3-bmc       |
| `0258-svcomp-count-up-down-1`     | `c/loops/count_up_down-1.c`                   | 1 (uint) | unreachable | bitwuzla     |
| `0259-svcomp-count-up-down-2`     | `c/loops/count_up_down-2.c`                   | 1 (uint) | reachable   | bitwuzla     |

Selection criteria: small (≤ 30 LoC), no stack arrays (sp is
uninitialized at the bench's `_start`), no FP, no malloc, no
`__VERIFIER_assume`. The 8 bitvector-regression tasks exercise C's
implicit conversion / sign-extension surface — exactly the
lowering-sensitive territory `EXTERNAL_BENCHMARKS_SURVEY.md` §1
calls out as the highest-value claim for the pair. The 2
count_up_down tasks add coverage for entry-only nondet plus a
bounded loop. The recommended 3+3+3+1 split across BitVectors /
Loops / NoOverflows / ControlFlow was deferred: the
`ntdrivers-simplified/` and `locks/` ControlFlow tasks all run to
hundreds of LoC with double-digit nondet counts (rejected by Q3),
and the `NoOverflows-Other.set` overlap with bitvector is already
covered by the lowering-sensitive picks.

`0258`/`0259` are pinned to **bitwuzla** (not the default
`z3-bmc`) because z3 timed out at bound 60–80 on the symbolic-`n`
bounded loop; bitwuzla converges in seconds. Engine selection per
task is recorded in `spec.json`'s `analysis.engine`.

## Pipeline

The full pipeline for one task:

```bash
# 1. rewrite + vendor
python bench/riscv-btor2/corpus/_svcomp_extract.py \
    --sv-bench-root bench/riscv-btor2/external/sv-benchmarks \
    --pick c/bitvector-regression/integerpromotion-2.c \
    --task-id 0252-svcomp-integer-promo-2 \
    --bound 60

# 2. compile + sidecars + spec.json
python bench/riscv-btor2/corpus/_compile_c.py \
    bench/riscv-btor2/corpus/0252-svcomp-integer-promo-2

# 3. validate
PYTHONPATH=. python bench/riscv-btor2/oracle.py            --task 0252
PYTHONPATH=. python bench/riscv-btor2/framework_oracle.py  --task 0252
PYTHONPATH=. python bench/riscv-btor2/oracle_cross.py      --task 0252
```

Each per-task `task.toml` already records the spec for
`included_callees`: `["task_main", "trap"]`. Tasks for which gcc
emits additional local functions (e.g., a non-inlined
`__VERIFIER_assert`) need that name added; the macro-based shim
prevents this case for the pilot.

## Pilot acceptance — outcome

| Oracle                                                     | Pass | Skip / Fail | Notes                                             |
|------------------------------------------------------------|------|-------------|---------------------------------------------------|
| `oracle.py` (concrete-trace)                               | 10/10 | 0          | Zero-input concrete reaches expected verdict.     |
| `framework_oracle.py` (z3-bmc / bitwuzla single-engine)    | 10/10 | 0          | Per-task engine pin recorded in spec.json.        |
| `oracle_cross.py` (multi-engine agreement)                 | 10/10 | pono/cvc5 unavailable locally | Engines that agree match expected; "unavailable" engines do not contribute to disagreement count. |
| `condition_d_reference.py` (CBMC cross-oracle)             | 0/10 | 10           | **Deferred.** `_emit_cbmc.py` does not yet rewrite the SV-COMP-vendored shape (`task_main` body, macro-expanded `reach_error()`); CBMC fails with "no body for callee trap". This is a `_emit_cbmc.py` follow-up, not a corpus issue. |

`check_determinism.py` confirms each cell produces the same
verdict across repeated invocations.

`oracle_cross` exits with `failures=0 mismatches=0` on the
locally-available engines (`z3-bmc`, `z3-spacer`, `bitwuzla`).
`pono` and `cvc5` report `error` rows because the local
environment doesn't have them installed; the bench Docker image
does, and the production `oracle_cross.py` runs in that image.
The pilot's signal is that the engines that *did* run agreed on
every task.

## Scope explicitly NOT in the pilot

- **80–100 tasks.** Out of scope; the pilot's success unblocks
  the full slice but doesn't ship it.
- **`_emit_cbmc.py` for SV-COMP shape.** Required for condition D
  coverage. Likely a small extension: detect the SV-COMP shim
  signature (the four `#define` macros), rewrite `reach_error()`
  → `__CPROVER_assert(0, ...)`, drop the `task_main` indirection.
  Tracked as a follow-up.
- **`__VERIFIER_assume`.** Not in any pilot pick; the rewriter
  rejects tasks that use it.
- **In-loop nondet.** `loop-invariants/even.c`-style tasks
  (`while (__VERIFIER_nondet_int())`) are rejected. The full
  slice will likely need a different rewriter strategy
  (per-iteration havoc via memory or a `nondet` input that
  changes each step).
- **`-O2 / -O3` sweep.** Not in the pilot. The existing
  `010X-c-*-oN` convention can be replicated for SV-COMP picks
  in a follow-up if the lowering-sensitive story benefits.
- **Multi-property tasks.** The pilot maps only the
  `unreach-call` property. SV-COMP `.yml`s carry `no-overflow`,
  `termination`, etc.; those are ignored.

## Open questions for the full slice

- **Compiler pin.** v0.4 already has the riscv64-unknown-elf-gcc
  version dependency open as a question; the SV-COMP scale-up
  amplifies it. Pinning a specific gcc version (or recording
  which version produced each ELF) becomes a §9.6-style
  artifact.
- **Selection criteria as a §9.2 artifact.** SV-COMP has > 20,000
  C tasks; the bench will only run a curated slice. The criteria
  used to pick (LoC, nondet count, no-arrays, etc.) become part
  of the pre-registration record so the slice is reproducible.
- **Engine selection per task.** The pilot showed that some
  symbolic-input loops are out of z3-bmc's range and need
  bitwuzla; at full slice scale, the `engine_bench.py`
  per-task pin discipline (already in v0.4) is necessary.

## Files added by the pilot

- `bench/riscv-btor2/external/sv-benchmarks/` — git submodule
- `bench/riscv-btor2/corpus/_svcomp_extract.py` — rewriter
- `bench/riscv-btor2/corpus/0250-svcomp-implicit-uns-conv-1/` — first vendored task
- (... 9 more under `0251-…` through `0259-…`)
- `bench/riscv-btor2/CORPUS_V0.5_PLAN.md` — this file
