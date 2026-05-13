# External C/C++ code-reasoning benchmarks — fit survey

This document surveys publicly-available C/C++ benchmarks used in the
program-verification, static-analysis, and code-reasoning communities,
and assesses each one's fit for hurdy-gurdy's `riscv-btor2` pair.
It is research output, not a corpus plan; concrete adoption goes through
a `CORPUS_V0.x_PLAN.md`.

The frame:

- **What we measure.** BENCHMARKING.md §2 — an *LLM-plus-pair system*
  on `(source, question, expected_verdict, witness_shape)` tasks under
  conditions A/B/C (±D, ±E).
- **What encodes.** SCOPE.md §3 — `Observable` (`RegisterAt`,
  `MemoryAt`, `PCAtStep`, `Executed`), `Assumption` (`RegisterInit`,
  `MemoryInit`, `CycleInvariant`), `Property` (single `bad` expression,
  optionally negated). Verdicts are
  `reachable`/`unreachable`/`proved`/`unknown`.
- **What doesn't encode.** SCOPE.md §5 — floats (F/D), atomics (A),
  vector (V), privileged ISA, CSR-driven control flow, concurrency,
  memory havoc, liveness/termination, unbounded inductive properties
  outside Spacer/Pono.
- **What's especially valuable.** SCOPE.md §4 — lowering-sensitive
  tasks where C semantics (UB) differs from RV64 defined behavior.
  v0.4 §3.D smoke confirmed CBMC fails on exactly this subset; the
  pair's distinctive value is concentrated there.
- **What's already in place.** v0.4's `_compile_c.py` compiles `task.c`
  to RV64 ELF and auto-generates `spec.json` from the `trap()` /
  `ebreak` convention. External C benchmarks adopt by conforming to
  that convention (or by a small rewriter).

## Tier 1 — high fit, high-volume, reusable infrastructure

### SV-COMP / `sv-benchmarks` (sosy-lab)

The 15th SV-COMP runs in 2026; the benchmark repository has ~20,000
tagged C verification tasks with machine-readable `.yml` task files
declaring `expected_verdict: true|false` and the property to check.
Categories that map cleanly onto the pair's encodable surface:

| SV-COMP category           | Maps to hurdy-gurdy            | Notes                                                                                  |
|----------------------------|--------------------------------|----------------------------------------------------------------------------------------|
| `ReachSafety-Loops`        | `Executed(reach_error_pc)`     | Reachability of `reach_error()` — the bench's `trap()` pattern, 1:1.                   |
| `ReachSafety-BitVectors`   | same + bitvector reasoning     | Highest direct fit — exercises BV theory the pair already uses.                        |
| `ReachSafety-ControlFlow`  | same                           | Branch-heavy reachability; tests dispatch ITE walking.                                 |
| `ReachSafety-ECA`          | same                           | Event-condition-action; large state spaces, good T2/T3 stress.                         |
| `ReachSafety-Arrays`       | same                           | Memory-as-array — the pair's natural shape.                                            |
| `NoOverflowSafety`         | `MemoryAt`/arithmetic property | **Lowering-sensitive gold mine** — C's UB on signed overflow vs RV64's defined wrap.   |
| `ReachSafety-Sequentialized` | same                         | Originally concurrent, mechanically sequentialized for single-hart analyzers.          |

**Out of scope (skip):**
- `ReachSafety-Floats`, `ReachSafety-Heap` (rich malloc patterns blow the pair's no-allocator assumption), `ConcurrencySafety-*`, `Termination-*`, `MemSafety-*` (most use rich pointer/aliasing that doesn't map to RV64 bytes), `SoftwareSystems-*` (Linux drivers — too large).
- `ReachSafety-Recursive` is encodable in principle but the pair's `included_callees` inlining of unbounded recursion will hit bounds quickly.

**Adaptation cost.** Three pieces:
1. SV-COMP tasks call `__VERIFIER_nondet_int()` etc. — these become
   `RegisterInit(..., op="any")`-style symbolic inputs or
   `havoc_registers` entries in the spec.
2. `reach_error()` is renamed `trap()` (or its PC is resolved by
   symbol).
3. Stdlib calls (`abort`, `__assert_fail`) need a freestanding shim.
   Most tasks in `ReachSafety-BitVectors` and `NoOverflowSafety` are
   self-contained and need only the entry-point fixup.

**Oracle.** SV-COMP `.yml` files carry `expected_verdict: true|false`
established by a decade of cross-tool agreement — §4.5 mechanism #2
out of the box.

**Why this is the obvious first target.** Volume, established ground
truth, machine-readable metadata, well-defined categories that match
the spec vocabulary. A curated 100-task slice (≈15 per category) gets
T1–T4 coverage at compiler-emitted code densities the hand-written
corpus can't reach.

### NIST Juliet C/C++ Test Suite (SARD)

64,099 test cases over ~118 CWEs, each one a small synthetic program
with a "bad" variant (flaw present) and a paired "good" variant (flaw
fixed). Public domain, machine-readable metadata, *ground-truth
provenance baked in*.

**The CWEs that map onto the pair's lowering-sensitive criterion:**

| CWE | Description                              | Maps to                                               |
|-----|------------------------------------------|-------------------------------------------------------|
| 190 | Integer Overflow or Wraparound           | 0115-c-int-overflow generalized. Direct fit.          |
| 191 | Integer Underflow                        | Same as 190; signed/unsigned cross-checks.            |
| 369 | Divide by Zero                           | 0116-c-divu-sentinel / 0117-c-int-min-div-neg-one.    |
| 682 | Incorrect Calculation                    | Catch-all numerical; many lowering-sensitive cases.   |
| 197 | Numeric Truncation Error                 | 0121-c-mulw-truncation generalized.                   |
| 195 | Signed-to-Unsigned Conversion            | 0122-c-signed-vs-unsigned-cmp generalized.            |
| 196 | Unsigned-to-Signed Conversion            | Same family.                                          |
| 839 | Numeric Range Comparison Without Min     | Bound-sensitive comparisons; T2 class.                |

**Out of scope:** CWE-121/122 (stack/heap buffer overflows in their
Juliet form rely on libc and dynamic allocation), CWE-415/416
(double-free/use-after-free — requires heap modeling), most CWEs in
the 200s (info exposure, requires I/O), all CWE-3xx (concurrency).

**Adaptation cost.** Higher than SV-COMP. Juliet test cases are
authored as `omitgood`/`omitbad`-conditioned executables linked
against a libc-style runner. Each candidate task needs:
1. Strip the runner main, keep the `bad`/`good` function body.
2. Insert the `_start` entry and `trap()` semantics.
3. Auto-generate the spec by symbol resolution.

A `_juliet_extract.py` rewriter is the right shape, modeled on the
existing `_compile_c.py`. Per-CWE bulk extraction is plausible.

**Oracle.** §4.5 mechanism #4 (property-by-construction): Juliet's
`bad` vs `good` partition *is* the oracle. The bench's
`expected_verdict` falls out for free.

**Value.** Juliet is the strongest single source for §3.D-failing /
§3.B-passing lowering-sensitive tasks at scale. The v0.4 condition D
smoke already showed CBMC `unknown`/wrong on the exact UB-vs-RV64
gap; Juliet's CWE-190/191/369/197 buckets are hundreds of variants of
that same gap.

### CBMC regression suite (`diffblue/cbmc` `regression/`)

The CBMC source tree ships a multi-thousand-test regression set, each
test case a tiny C program with a CBMC invocation and an expected
verdict (VERIFICATION SUCCESSFUL / FAILED). Categories are
folder-organized (`cbmc/`, `cbmc-cover/`, `cbmc-c++/`, ...).

**Fit.** Excellent for the bench's condition D cross-reference and for
sanity-checking the bench's own corpus: every task that exists in
CBMC regression and compiles to RV64 gives a free §4.5 mechanism #2
agreement column. The condition D reference (`condition_d_reference.py`)
already invokes CBMC on the bench's C tasks; widening the input set
to CBMC's own regression tasks is a natural extension.

**Adaptation cost.** Low for the smoke subset (CBMC regression tasks
that are self-contained, no preprocessor wrangling). Medium for
anything that depends on CBMC's `__CPROVER_*` builtins — those need
to be lowered to the bench's spec vocabulary by hand.

**Value.** Less about scale, more about **cross-tool oracle hygiene**:
"CBMC and hurdy-gurdy agree on a 200-task shared subset" is a
defensible §4.5 column that strengthens every other claim. Also
exercises the *opposite* direction of the v0.4 result: tasks where
CBMC is right and the pair must agree, complementing the v0.4 tasks
where CBMC is wrong-on-UB and the pair is right.

## Tier 2 — useful, more adaptation work

### DARPA Cyber Grand Challenge (Trail of Bits `cb-multios` port)

~200 small C/C++ programs, each with one or more *seeded
vulnerabilities* and a *proof-of-vulnerability* input that triggers
the bug. Originally for binary-level fuzzing/SAST competition.

**Fit.** Programs are small (target: human-comprehensible C with
seeded bugs), have *executable witnesses* (PoV inputs) which match
§4.5 mechanism #3 directly, and were *designed to be reasoned about
at the binary level* — closer to the pair's natural surface than
high-level C.

**Adaptation cost.** Higher than SV-COMP. Programs use a CGC-specific
syscall interface (`receive`/`transmit`/`allocate`) that needs to be
stubbed for freestanding RV64. Trail of Bits' port (cb-multios)
already has a libc-translation layer; that needs to be re-targeted
to no-libc.

**Value.** Real-shaped binaries (input-driven control flow, not
toy `_start` stubs) with witnesses. A 20-task slice would give the
bench a class of T4-grade lift tasks the hand-corpus can't easily
synthesize.

### Toyota ITC Benchmark (SAMATE 104)

1,276 small static-analysis test cases over nine categories:
static memory, dynamic memory, stack-related, numerical, resource
management, pointer-related, concurrency, inappropriate code,
miscellaneous. Half planted-defect, half clean. Originally for SAST
tool evaluation.

**Fit.** The *numerical*, *static memory*, and *stack-related*
categories map naturally onto the spec vocabulary. Smaller volume
than Juliet but better balanced — Juliet over-represents control/data
flow variants of the same defect; Toyota ITC diversifies the defect
shapes.

**Out of scope:** concurrency, dynamic memory (most of it),
resource management (file/socket).

**Adaptation cost.** Same shape as Juliet — strip the runner, keep the
defect body, fix entry, resolve trap PC. Slightly easier because the
test cases are smaller on average.

### Code2Inv benchmark

133 small C loop programs from a deep-learning-for-invariants paper.
Each has a precondition, a loop, and a post-condition; the verification
task is to infer a loop invariant strong enough to prove the
post-condition.

**Fit.** Maps to the pair's T3 tier (decomposition: prove the loop
invariant as a separate question, inject as `LearnedFact`). Also
maps to `z3-spacer`'s strength — these are the canonical inductive
tasks Spacer is built for.

**Adaptation cost.** Low — small programs, well-formed, easy to
compile. Mostly needs an `_invariant_to_cycleinvariant.py` rewriter
to express the program's invariant as a `CycleInvariant` assumption.

**Value.** Targeted T3 stress + a defensible Spacer-tier benchmark.
Pairs well with §9.12's `oracle_cross.py` (`z3-spacer` vs `pono-ind`
agreement on inductive tasks).

### HWMCC BTOR2 benchmark archive

The Hardware Model Checking Competition publishes ~500 BTOR2 models
per year (word-level track). Not C/C++, but BTOR2 directly.

**Fit for the *pair*: none.** These aren't translated *from* a source
language; they're hand-authored hardware models. Condition A is
meaningless.

**Fit for the *solver layer*: high.** §3 condition C ("same solver,
hand-written encoding") becomes more defensible if `tool_solve` is
known to handle a large BTOR2 corpus correctly. The bench's
`engine_bench.py` could be re-run over HWMCC's BTOR2 set to
characterize the solver inventory's behavior, independent of the
translation. This is solver-side hygiene, not corpus material.

## Tier 3 — relevant adjacent, mostly out of fit

### CompCert test suite

The CompCert verified C compiler ships a regression suite. Programs
are well-formed, well-defined (no UB by design — they're the *good*
cases). Useful as a sanity-check substrate but lacks the
"violation"/"safe" partition that the bench needs.

### SV-COMP `MemSafety-*`

Memory-safety tasks rely on rich pointer/aliasing modeling that the
pair doesn't currently encode (memory is byte-addressed, no separation
logic, no shape analysis). Coverage gap — log as `MemSafety` cannot
be encoded, contributes to the coverage-gap-rate metric.

### SV-COMP `Termination-*`

Liveness isn't expressible (SCOPE.md §5). Coverage gap by design.

## Non-fits — research-adjacent but wrong shape

### CoRe (2025 static-analysis benchmark)

12,553 LLM tasks on dataflow / control-dependency / information-flow
*questions* in C/C++/Java. The questions are *about* the program, not
*on* the program — they're more like "which line is data-dependent
on this one" than "does this assertion hold." The pair's spec
vocabulary doesn't express dataflow-classification questions; the
LLM-with-pair workflow is solver-dispatch, not pattern-recognition.
Treat as orthogonal.

### VerifyThis / VerifyThisBench

End-to-end formal-proof challenge problems (Java/Dafny/Coq targets,
some C). The verification artifact is a proof, not a solver verdict.
Doesn't fit the BMC/inductive workflow.

### CRUXEval-X, LiveCodeBench, SecRepoBench

Code generation / completion benchmarks, not reasoning over a fixed
program. Different problem class.

### CSmith / YARPGen (random C generators)

Generators, not benchmarks. Useful as *fuzzers* for the
translator/lifter (does the pair survive arbitrary valid C?) but
provide no oracle for the question side. Would need to be paired
with a reference verifier (CBMC) to establish expected verdicts —
which means CBMC's verdict becomes ground truth, which means the
benchmark can only measure agreement with CBMC, not advantage over
it. Self-defeating for the bench's purpose.

## Recommended sequencing

A v0.5 corpus expansion that produces, in order:

1. **SV-COMP slice — ~80–100 tasks** across `ReachSafety-BitVectors`,
   `ReachSafety-ControlFlow`, `ReachSafety-Loops`, `NoOverflowSafety`.
   Writes one rewriter (`_svcomp_extract.py`) that handles
   `__VERIFIER_nondet_*` and `reach_error`. Inherits SV-COMP's
   pre-registered verdicts. Doubles the corpus and triples its
   T2/T3 difficulty mass without growing the lowering-sensitive
   fraction (these are mostly *not* lowering-sensitive — they
   measure raw BMC capacity on compiler-emitted code).

2. **Juliet UB slice — ~50 tasks** across CWE-190 / -191 / -369 / -197 /
   -195. Writes `_juliet_extract.py`. Doubles the
   lowering-sensitive subset and gives the §3.D-fails / §3.B-passes
   story far more weight than v0.4's 5 hand-authored examples.

3. **CBMC regression cross-oracle — ~200 tasks (no LLM)**. Drop into
   `condition_d_reference.py`-equivalent infrastructure. Produces
   the agreement matrix that strengthens every §4.5 column.

4. **(optional, later) Code2Inv slice — ~20 tasks** for Spacer
   T3 stress.

Each slice is independently shippable; (1) and (2) are the
high-leverage ones, (3) is hygiene, (4) is targeted.

## Open questions

- **Compiler pinning.** SV-COMP and Juliet programs need a pinned
  `riscv64-unknown-elf-gcc` (CORPUS_V0.4_PLAN.md §"Open questions"
  flagged this already). External programs amplify the issue — many
  SV-COMP tasks were authored against `gcc -O0`-shaped output and
  may behave differently under `-O2`.
- **Spec auto-generation for general C.** v0.4's
  `_compile_c.py` assumes the `trap()` convention. Adopting SV-COMP
  tasks requires teaching the auto-generator to recognize
  `reach_error()` (or to insert a `trap` alias at link time). Both
  approaches work; choosing one is a v0.5 plan item.
- **Volume discipline.** SV-COMP and Juliet between them have
  >80,000 tasks; the bench cannot run them all under §3 conditions
  (cost-per-cell × 5 runs × 2+ LLMs × 4 conditions). A curated slice
  with documented selection criteria is the only viable shape; the
  selection criteria become a §9.2 artifact.

---

Sources:

- [SV-COMP — sosy-lab/sv-benchmarks](https://github.com/sosy-lab/sv-benchmarks)
- [SV-COMP 2026 (Zenodo)](https://zenodo.org/records/18650775)
- [NIST SAMATE / SARD](https://samate.nist.gov/SARD/)
- [Juliet C/C++ 1.3 (SARD)](https://samate.nist.gov/SARD/test-suites/112)
- [CBMC (diffblue/cbmc)](https://www.cprover.org/cbmc/)
- [ESBMC (esbmc/esbmc)](https://github.com/esbmc/esbmc)
- [DARPA CGC port (trailofbits/cb-multios)](https://github.com/trailofbits/cb-multios)
- [Toyota ITC Benchmarks (regehr/itc-benchmarks)](https://github.com/regehr/itc-benchmarks)
- [Code2Inv (PL-ML/code2inv)](https://github.com/PL-ML/code2inv)
- [HWMCC'25](https://hwmcc.github.io/2025/)
- [Btor2 (Niemetz, Preiner, Wolf, Biere — CAV'18)](https://fmv.jku.at/papers/NiemetzPreinerWolfBiere-CAV18.pdf)
- [SeaHorn](https://seahorn.github.io/)
- [CoRe (arXiv 2507.05269)](https://arxiv.org/abs/2507.05269)
- [VerifyThisBench (researchgate)](https://www.researchgate.net/publication/392104908_VerifyThisBench_Generating_Code_Specifications_and_Proofs_All_at_Once)
- [Frama-C on CGC corpus bugs](https://frama-c.com/2019/02/26/Finding-unexpected-bugs-in-the-DARPA-CGC-corpus.html)
