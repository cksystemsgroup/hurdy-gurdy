# `riscv-btor2` benchmark scope

This is the §9.1 instantiation of [BENCHMARKING.md](../../BENCHMARKING.md)
for the `riscv-btor2` pair. It defines what the benchmark covers and,
just as importantly, what it does not. Every later artifact (corpus,
prompts, rubric) inherits these boundaries.

## 1. Source language and dialect

- **ISA**: RV64I + M extension + C compressed (RV64IMC). XLEN is 64.
- **Mode**: user-mode only. Straight-line and branching code; calls
  to `included_callees` are inlined per the spec's `AnalysisScope`.
- **Out of scope**: F/D (floating point), A (atomics), V (vector),
  privileged ISA (trap handlers, supervisor mode, paging, interrupts,
  CSR-driven control flow), multi-hart concurrency. These are stable
  exclusions per `SCHEMA.md` §15.
- **Multi-function programs are in scope** via `included_callees`.
  `_start` calls a callee `f`; the spec's
  `scope.included_callees=("f",)` adds `f`'s PCs to the analyzed
  set so the dispatch ITE walks through `f`. Callees not listed
  produce a self-loop at their entry PC (`SCHEMA.md` §6) — the
  control-flow boundary for "left the analyzed region". Calling
  conventions are not enforced; the linkage register is whatever
  the assembly source uses (typically `x1`/`ra`, but the seed
  task `0027-nested-call` uses `x6` for an inner call to avoid
  clobbering an outer return address). Multi-function corpus tasks
  (the T3 family) exercise the LLM's choice of which callees to
  include in scope.
- **Source artifact**: a single statically-linked RV64 ELF, plus an
  `AnalysisScope(entry_function, included_callees)`. DWARF is
  optional and only used in annotations.

## 2. Reasoning language and solver inventory

- **Reasoning language**: BTOR2, schema version `1.1.0`
  (v1.1.0 adds `BranchPin`, `CycleInvariant.dual_role`, and the
  `volatile` layer — see `gurdy/pairs/riscv_btor2/SCHEMA.md` §14).
- **Solver inventory** (pinned bench image — canonical tag + digest in
  [`DOCKERHUB.md`](../../DOCKERHUB.md)):

| Engine        | Backend version | BENCHMARKING.md role |
|---------------|-----------------|----------------------|
| `z3-bmc`      | z3 4.16.0       | BMC; default engine in `AnalysisDirective` |
| `z3-spacer`   | z3 4.16.0       | Inductive (Horn / fixedpoint). Encodes the BTOR2 transition system as Horn clauses and lets Spacer discover an inductive invariant. Emits `proved` when the property holds at all depths (strictly stronger than BMC's bounded `unreachable`), `reachable` when a counterexample exists, `unknown` on timeout. |
| `bitwuzla`    | 0.9.1           | BMC alternative; bitvector-strong. Pinned by v0.3 corpus tasks `0050-deep-mul-chain` and `0051-large-bound-loop-bitwuzla` where engine perf records 6–13× speedup over `z3-bmc`. Also a §4.5 cross-solver oracle column in `oracle_cross.py`. |
| `cvc5`        | 1.3.4           | BMC alternative; second-vendor cross-check for §3 condition C's "two unrelated tools" criterion. The §4.5 cross-solver oracle column in `oracle_cross.py`. |
| `pono`        | `v2.0.0` (commit `c81aa36`) | Subprocess BMC via vendored smt-switch; also exposes k-induction (`extra_options.engine=ind`) so it can emit `proved` and serve as the inductive cross-check for `z3-spacer` in `oracle_cross.py`. |

Image hash is the §7 pinning artifact; bumping any version is a new
experiment and a new image tag.

The §9.12 multi-engine cross oracle (`oracle_cross.py`) is what
makes bitwuzla / cvc5 / pono load-bearing rather than merely
"installed": every corpus task is dispatched under every compatible
engine, and the agreement matrix is the §4.5 oracle. BMC tasks run
on z3-bmc + bitwuzla + cvc5 + pono; inductive tasks run on z3-spacer
+ pono-ind. Locally, engines whose bindings/binaries are absent
return `error` and surface as `CROSS-SKIPPED`; inside the bench
image all four return verdicts.

## 3. Question taxonomy exercised

The benchmark exercises every `Observable`, `Assumption`, and
`Property` shape the pair currently supports.

### Observables (from `gurdy/pairs/riscv_btor2/spec.py`)

| Shape | Encodes |
|---|---|
| `RegisterAt(register, pc)` | "what is the value of `xN` when execution reaches PC P" |
| `MemoryAt(address, width, pc)` | "what is the value at memory address A (1/2/4/8 bytes) at PC P" |
| `PCAtStep(step)` | "what PC is executed at step S" |
| `Executed(pc)` | "is PC P ever executed within the bound" |

### Assumptions

| Shape | Encodes |
|---|---|
| `RegisterInit(register, op, value)` | constrain entry value of a GPR (`eq`/`ne`/`lt`/…/`geu`) |
| `MemoryInit(address, width, op, value)` | constrain an initial memory cell |
| `CycleInvariant(expression)` | symbolic predicate that must hold every cycle |

### Property

- `Property(expression, negate=False)`: a `bad` clause in the pair's
  expression DSL (parsed by the translator). `negate=True` flips
  polarity for synthesis-style tasks.

### Analysis directive

- `AnalysisDirective(engine, bound, timeout, havoc_registers, extra_options)`.
- `havoc_registers ⊆ {0..31}` replaces a register's `next` clause with
  fresh `nondet`. Memory havoc is rejected at v1 (see §4 below).

### Verdicts

`reachable` / `unreachable` / `proved` / `unknown`. Per `SCHEMA.md` §10:
BMC engines return `unreachable` (not `proved`) when no trace within
`bound` reaches a `bad`; only Pono/Spacer can emit `proved`.

## 4. Lowering-sensitive criterion (BENCHMARKING.md §4.3)

A task is **lowering-sensitive** when answering it correctly requires
appealing to semantics the source language (RV64 binary mnemonics)
*hides* but the BTOR2 lowering *makes explicit*. A reasonable RISC-V
programmer reading the source could plausibly get it wrong; the
translation forces the right answer.

A non-trivial fraction (≥ 20% of the corpus, per §4.3) must satisfy
this. Three motivating examples:

1. **Word-only sign extension** — `ADDIW`, `ADDW`, `SLLIW`, etc. compute
   on the low 32 bits and *sign-extend the result to 64*. A reader who
   thinks of these as "32-bit ops" may not realise `x{rd}` ends up
   negative when bit 31 of the result is 1. The BTOR2 lowering makes
   this explicit (`sign_extend(low32(...), 64)` per `SCHEMA.md` §5).

2. **DIV-by-zero produces sentinel values, not a trap** — `DIV` returns
   quotient `-1` and remainder `x{rs1}`; `DIVU` returns `2^64 - 1` and
   `x{rs1}`; signed `INT_MIN / -1` returns `INT_MIN`. C programmers
   used to SIGFPE may reason as if the program halts; BTOR2 encodes
   the actual sentinel-returning ITE.

3. **Memory bytes outside `PT_LOAD` are *uninitialized*, not zero** —
   the schema deliberately does not silently zero unmapped bytes
   (`SCHEMA.md` §4). A reader who expects calloc-like behaviour will
   miss tasks that hinge on a load returning an arbitrary value.

Other lowering-sensitive surfaces (not exhaustive):

- Shift-amount masking to 5/6 bits.
- JALR's mandated `~1` mask on the next-PC.
- Misalignment decomposing to per-byte loads/stores rather than trapping.
- Endianness of multi-byte loads/stores (little-endian).
- `ECALL`/`EBREAK` setting `halted` and freezing the PC, instead of an
  OS-level transition.
- Register `x0` reading as zero and silently dropping writes.

The instantiation is responsible for tagging each corpus task with a
`lowering_sensitive: bool` based on these criteria.

## 5. Question shapes the pair *cannot* encode

These are the coverage gaps. Tasks whose natural framing requires one
of these are recorded as **coverage gaps** (BENCHMARKING.md §4.1) and
contribute to the coverage-gap rate metric.

- **Floating point** — no F/D. Properties about `fadd`, NaN propagation,
  rounding modes, etc.
- **Atomic / memory-ordering** — no A. Properties about `lr`/`sc`,
  acquire/release ordering.
- **Vector** — no V. Properties about `vadd.vv`, masking, `vlen`.
- **Privileged ISA** — no trap handlers, no `sret`/`mret`, no
  page-table walks, no interrupt delivery. Properties about which
  trap fires or how an exception unwinds.
- **CSR-write effects** — CSR writes are dropped at v1; CSR reads
  return fresh `nondet`. Properties whose answer depends on a
  programmed `mtvec`, `satp`, `fcsr`, etc. cannot be encoded.
- **Concurrency** — single hart. Properties about cross-hart races or
  shared memory.
- **Memory havoc** — v1 rejects `havoc` of memory cells with a
  structured diagnostic. Tasks whose natural framing is "assume memory
  changes arbitrarily between cycles" cannot be encoded.
- **ABI / calling-convention conformance** — the schema does not check
  callee/caller-saved register obligations.
- **Inductive properties beyond bound** — BMC engines (`z3-bmc`,
  `bitwuzla`, `cvc5`, `pono`) say nothing about behaviour past `bound`.
  Pono and Spacer can in principle emit `proved`; in v1 Spacer routes
  back to BMC unless inductive reasoning is explicitly required, so
  unbounded-correctness tasks usually report `unknown`.
- **Liveness / termination** — only safety properties (`bad`
  expressions). Tasks of the form "does the program eventually reach
  P" are not directly encodable; the bounded approximation
  ("does it reach P within `bound`") is what `Executed` captures.

## 6. Source-level baseline (condition D)

For the *original* hand-written assembly corpus (0001-0049),
RISC-V binaries do not have a direct source-level verifier analogue
of CBMC / ESBMC, so condition D is **omitted** there. The plausible
substitute would be a symbolic execution tool (angr, manticore)
operating on the binary, but those are themselves "reasoning over
the binary" rather than over a higher-level source — they don't
isolate a different value layer.

For the v0.4 **C-derived** corpus (0100+, see CORPUS_V0.4_PLAN.md),
condition D is now *available* via CBMC, and the bench has shipped
a §3.D smoke test that demonstrates exactly the value claim
BENCHMARKING.md §3.D promises:

> The strongest case for a pair is a task class on which D answers
> `unknown` or wrong and B answers correctly — typically the
> lowering-sensitive subset.

### v0.4 condition D smoke result (`condition_d_reference.py`)

The reference CBMC oracle runs `cbmc task.cbmc.c --unwind <bound>`
on every C task and compares CBMC's verdict to the bench's
pre-registered `expected_verdict`. Across the 25 v0.4 C tasks:

| | Count |
|---|---:|
| CBMC PASS (CBMC verdict matches bench `expected_verdict`) | 20 |
| CBMC FAIL (CBMC disagrees with the bench's correct verdict) | 5 |

The 5 FAILs are **every single lowering-sensitive task whose
question turns on a UB-vs-RV64-defined-behavior gap**:

- 0115-c-int-overflow (`INT_MAX + 1` — UB vs RV64 wraparound)
- 0116-c-divu-sentinel (divuw by zero — UB vs RV64 sentinel)
- 0117-c-int-min-div-neg-one (signed `INT_MIN / -1` — UB vs RV64 sentinel)
- 0118-c-shift-amount-mask (`x << 64` — UB vs RV64 6-bit mask)
- 0121-c-mulw-truncation (`int*int` overflow — UB vs RV64 MULW low-32)

CBMC's stdout shows that on each of these, the failing property
is the C-standard's `arithmetic overflow` / `division by zero`
check — *not* the rewritten `__CPROVER_assert(!(cond))` that the
bench's question maps to. CBMC is correctly enforcing the C
language standard's "this is UB → cannot certify"; the bench is
correctly verifying RV64's well-defined behavior on the same
construct. The pair adds value over CBMC by accepting "UB in C
but well-defined on the actual target."

The other lowering-sensitive C tasks (0119, 0120, 0122) do not
hinge on UB and CBMC handles them correctly. The lowering-
sensitive flag is broader than "CBMC misses it" — it marks any
RV64 surface a C reader might miss, regardless of whether
CBMC also misses it.

This result is the strongest single argument for the pair's
distinctive value the bench has produced to date, and it lands
without any LLM in the loop. The CBMC oracle is at
`bench/riscv-btor2/condition_d_reference.py`; the rewriter is
at `bench/riscv-btor2/corpus/_emit_cbmc.py`.

### Wiring status (LLM-D-mode)

Both the reference oracle and the LLM-facing tool surface for D
are **operational**: `tool_cbmc` in `harness.py`,
`prompts/condition_d.md`, `prompts/tools_d.json`, MCP `mode="D"`,
and `run_matrix --conditions D` are all wired and exercised by
the v0.4 sweep — see `runs/v0.4/_full_D/manifest.json` and
`runs/v0.4/results.md`. The infrastructure mirrors condition C's
path (`mode="C"` in `mcp_server.py`).

### Status of condition C (BENCHMARKING.md §3.C)

Condition C is **operational**: the LLM-facing tool surface
(`prompts/tools_c.json` declaring `solve(engine, input_language,
input_text, options)`), the prompt (`prompts/condition_c.md`), the
harness route (`harness.py:tool_solve`), the MCP server (`mode="C"`
in `mcp_server.py`), and the run-matrix flag (`--conditions C`)
are all wired.

The `solve` tool exposes four engines whose CLI binaries the bench
Docker image installs at the version pins above:

- **z3** consuming SMT-LIB2 (general-purpose default).
- **bitwuzla** consuming SMT-LIB2 (bitvector-strong; matches the
  6–13× speedup the in-process bitwuzla shows on BMC tasks).
- **cvc5** consuming SMT-LIB2 (natural second-vendor cross-check).
- **pono** consuming BTOR2 (BTOR2 BMC).

The (bitwuzla, btor2) combination is *not* exposed: bitwuzla's CLI
does not handle the BTOR2 model-checking extensions
(state/init/next/bad). BTOR2 BMC under bitwuzla is reachable only
via the in-process Python bindings (used by the pair, not
condition C); BTOR2 BMC under condition C is pono-only.

The path is end-to-end smoke-tested by
`bench/riscv-btor2/condition_c_reference.py`: hand-written
SMT-LIB encodings of representative corpus tasks dispatched
through `tool_solve` against every locally-available SMT-LIB
engine (`z3` / `bitwuzla` / `cvc5`); each engine's verdict must
match the corpus oracle. The v0.1.2 / v0.2 published runs do
*not* include condition C transcripts; the path back to a
§3.C-grade publication is to run
`python bench/riscv-btor2/run_matrix.py --conditions C ...`
against an LLM slot, not to build the infrastructure (which is
already there).

## 7. Per-pair difficulty hints (BENCHMARKING.md §4.2)

Sketches only — the corpus document instantiates these.

- **T1**: trivially decidable at `bound ≤ 8` with default engine
  (`z3-bmc`). Examples: register-flag toggles, single-call leaf
  functions returning a constant.
- **T2**: requires a non-default directive — larger `bound`,
  `bitwuzla` instead of `z3-bmc`, or a `havoc_registers` set to
  drop sub-callee detail.
- **T3**: requires decomposition. The natural approach proves a loop
  invariant or callee post-condition as a separate question and
  injects it as a `LearnedFact` in a follow-up.
- **T4**: requires source-level interpretation of the witness via
  `lift` — e.g., explaining *which mnemonic at which PC* caused the
  refutation, not just that one exists.

## 8. Open questions (resolve before §9.2 corpus)

- **Toolchain for synthesizing tasks.** Options: hand-written assembly
  (precise but slow), `riscv64-unknown-elf-gcc -O0` from C (fast but
  drifts with compiler version — needs pinning in the bench image).
  Probably both.
- **Witness fingerprint format.** §4.5 wants `witness_shape` recorded
  in advance. Sketch: `(bad_pc, halted_step, observable_state_at_bad)`
  serialized canonically.
- **Whether to count `unknown` as a coverage gap.** §5 grades
  `unknown` separately, but a pair that always says `unknown` on its
  T2 tier is not effective. Probably split: `unknown-by-design`
  (timeout, beyond bound) vs `unknown-by-coverage-gap` (pair couldn't
  encode).

These are choices the §9.2 corpus author makes; flagged here so they
don't get re-litigated downstream.
