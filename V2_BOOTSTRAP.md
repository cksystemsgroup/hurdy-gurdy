# Hurdy-Gurdy — `aarch64-btor2` Pair Bootstrap

> Self-contained brief for a long-running autonomous agent. The agent's
> job is to build the `aarch64-btor2` pair from scratch on the
> `aarch64-btor2-bootstrap` branch, following this spec, until the pair
> beats established C/C++ → AArch64 verification tools on standard
> benchmarks.
>
> A fresh Claude Code session should be able to pick up purely from
> this file + `V2_AGENT_LOOP.md` + `V2_PROGRESS.md`. The reference
> `riscv-btor2` pair lives on branch `v2-bootstrap`; this pair is the
> closest port of riscv-btor2 to a second ISA.

## 1. Thesis

Hurdy-gurdy is a **question compiler**: it deterministically translates
`(QuestionSpec, source program)` into a reasoning artifact for an
external solver, then lifts the verdict back to source-level facts.
*The framework does no reasoning; the LLM does.*

This pair's **wedge thesis** is the same shape as `riscv-btor2`'s,
applied to a second ISA:

- **C declares behavior undefined; AArch64 defines it.** Signed
  integer overflow, divide-by-zero (yields 0 on AArch64 SDIV/UDIV
  rather than trapping like RV64M; but `AArch64` `SDIV INT_MIN, -1`
  still yields `INT_MIN`), shift-amount masking (AArch64 `LSL/LSR`
  mask shift count mod 32/64), `mul` overflow truncation.
- The CBMC false-positive class observed on RV64
  (`riscv-btor2/baselines/INITIAL_FINDINGS.md` §13) is expected to
  reproduce on AArch64 because the *C side* of the gap is identical
  — what changes is which ISA defines the behavior, not whether the
  source verifier sees it.

Two strategic reasons this pair is worth building:

1. **Demonstrates ISA-portability** of the translator architecture.
   "Works on >1 ISA" is a credibility ratchet for the v2 thesis.
2. **Bigger industrial install base** than RV64 (mobile, server,
   embedded, Apple silicon). Even if the *novel* wins are
   incremental, the *audience* is larger.

Acknowledge up-front: this pair is incremental science compared to
`wasm-btor2` and `evm-btor2`. It's the right second pair if the goal
is ISA portability proof and broader adoption; not the right second
pair if the goal is new wedge classes.

The three pillars, load-bearing from commit zero:

1. **Source interpreter** (`source_interp/`) — a concrete executor
   of AArch64 (ARMv8-A user mode) at the same fidelity the translator
   claims.
2. **Reasoning interpreter** (`reasoning_interp/`) — BTOR2 simulator
   + witness replayer. Reusable from `v2-bootstrap`.
3. **Translator** (`translation/`) — the deterministic compiler from
   AArch64 ELF + scope to BTOR2.

## 2. Why this can outperform SOTA

The relevant SOTA is the same as for `riscv-btor2` because the
C-source side is identical:

- **CBMC / ESBMC** — direct C BMC.
- **SeaHorn** — LLVM IR Horn clauses.
- **Symbiotic** — slicing + multi-engine.
- **KLEE / angr** — symbolic execution (angr has decent AArch64
  support).
- **Pono (native)** — BTOR2 BMC/k-ind from a hand-written front
  end.

AArch64-specific competitors:

- **CBMC on AArch64-targeted source** — same tool, same UB
  conservatism.
- **Sail-ARM** + tools built on it (Islaris, Cerberus) — formal
  ARMv8-A semantics; verification tooling research-grade.

Hurdy-gurdy's edge claims, same as RV64:

1. **C-UB-but-AArch64-defined wedges**: signed overflow, shift
   masking, mul truncation. Expected 5/5 reproduction of the
   RV64 pattern on lifted-to-AArch64 versions of the seed corpus.
2. **LLM-curated scope** + **multi-engine portfolio**.
3. **CEGAR in spec space**.

## 3. Foundation reuse plan

Maximize reuse from `v2-bootstrap`:

- `gurdy/core/` — copy verbatim.
- `gurdy/pairs/riscv_btor2/reasoning_interp/` — copy as
  `gurdy/pairs/aarch64_btor2/reasoning_interp/`.
- `gurdy/pairs/riscv_btor2/lift/` — copy and adapt witness
  fingerprints for the AArch64 register set.
- `gurdy/pairs/riscv_btor2/solvers/` — copy verbatim; the BTOR2
  output shape is engine-agnostic.
- `gurdy/pairs/riscv_btor2/translation/builder.py` and the layered
  artifact format — copy; only the **library** layer (per-instruction
  lowerings) and **machine** layer (register file shape) are
  ISA-specific.

The translator's layered architecture (header / machine / library /
dispatch / init / constraint / bad / binding) was designed precisely
to make per-ISA reuse cheap. This pair should validate that design
choice; if reuse turns out painful, that is a design BLOCKER for the
v2 architecture, not for this pair specifically.

## 4. The three pillars in detail

### 4.1 Source interpreter (`gurdy/pairs/aarch64_btor2/source_interp/`)

A concrete executor of AArch64 user mode at the same fidelity the
translator claims.

Required capabilities:

- **Run**: `(elf, scope, inputs) → trace`.
- **Bindings**: `Free` sentinel for uninstantiated inputs.
- **Shadow mode**: per-instruction read/write records.
- **Determinism**.
- **No solver dependency**.

Subset at P1: integer base ISA + LDR/STR + branches. Defer:

- F/D floating point (NEON/SVE) — separate large opcode surface.
- Atomics (LDXR/STXR, LSE) — concurrency outside scope.
- SVE (variable-length vectors) — defer.
- Privileged mode (EL1+), system registers — out of scope.
- Pointer authentication (PAC) — out of scope.
- BTI (Branch Target Identification) — out of scope.

### 4.2 Reasoning interpreter (`gurdy/pairs/aarch64_btor2/reasoning_interp/`)

A concrete executor of BTOR2. **Copy verbatim from
`gurdy/pairs/riscv_btor2/reasoning_interp/`**.

### 4.3 Translator (`gurdy/pairs/aarch64_btor2/translation/`)

The `(spec, elf) → btor2_model` compiler.

Topology mirrors `riscv-btor2`:

- **header**: BTOR2 sort declarations.
- **machine**: state — `x0`–`x30` (general-purpose 64-bit), `sp`,
  `pc`, NZCV (`bv4` or four `bv1` flags), trap flag. Memory as
  `Array bv64 bv8`.
- **library**: per-instruction lowering for AArch64 base ISA. ~90
  integer/control/memory opcodes at P1.
- **dispatch**: PC-keyed ITE.
- **init**: initial state from spec.
- **constraint**: invariants.
- **bad**: property under investigation.
- **binding**: next clauses wiring states to dispatch.

Schema version begins at `1.0.0`.

## 5. The interpreter-alignment correctness oracle

Same shape as `riscv-btor2`:

```
trace_src  = source_interp.run(elf, scope, inputs, record_shadow=True)
artifact   = translator.compile(spec, elf, scope)
verdict, witness = dispatch(artifact, spec.engine)

if verdict == "reachable":
    trace_rsn = reasoning_interp.replay(artifact, witness)
    assert align(trace_src_with_same_inputs, trace_rsn).ok
elif verdict in {"unreachable", "proved"}:
    trace_src_concrete = source_interp.run(elf, scope, zero_inputs)
    assert not violates_property(trace_src_concrete, spec.property)
```

`bench/aarch64-btor2/oracle_align.py`.

## 6. Repo scaffold

```
gurdy/
  pairs/
    aarch64_btor2/
      SCHEMA.md
      __init__.py
      spec.py
      source/                  # AArch64 ELF loader, insn decoder
      source_interp/           # AArch64 concrete executor + shadow
      reasoning_interp/        # BTOR2 simulator (copied)
      translation/             # the translator
      lift/                    # witness → source-level facts
      solvers/                 # engine adapters (copied)
bench/
  aarch64-btor2/
    SCOPE.md
    corpus/
      seed/                    # AArch64 versions of the riscv-btor2 wedge seeds
      svcomp_slice/            # SV-COMP subset compiled to AArch64
    harness.py
    oracle_align.py
    oracle_cross.py
    engine_bench.py
    baselines/
      cbmc.py
      hurdy_gurdy.py
      pareto.py
tests/
  pairs/aarch64_btor2/
V2_BOOTSTRAP.md                # this file
V2_AGENT_LOOP.md
V2_PROGRESS.md
```

## 7. Phase plan (the agent owns and extends this)

Compressed relative to `riscv-btor2` because of maximum reuse.

- **P0 — Scaffold & contracts**: directory layout above; copy
  `gurdy/core/`, `reasoning_interp/`, `solvers/`, dispatch
  infrastructure from `v2-bootstrap`.
- **P1 — Schema v1.0.0 for `aarch64-btor2`**: minimal viable —
  AArch64 base integer ISA only; single-function entry; BMC
  engine; reach-property `QuestionSpec`. SCHEMA.md frozen.
- **P2 — Source interpreter (AArch64 base)**: ELF loader,
  instruction decoder, integer + branch + load/store opcodes,
  observable model.
- **P3 — Reasoning interpreter**: copied; verify pair-agnostic
  contract holds.
- **P4 — Translator (AArch64 base → BTOR2)**: minimum viable.
- **P5 — Alignment oracle**.
- **P6 — Dispatch & solver adapter**: z3-bmc + bitwuzla + cvc5 +
  pono (copied adapters).
- **P7 — Seed corpus + harness**: port the `riscv-btor2`
  wedge-seed tasks (0115–0121) to AArch64. The C source is
  identical; recompile with an AArch64 toolchain.
- **P8 — Wedge reproduction measurement**: run hurdy-gurdy on
  the ported wedges, run CBMC on the same C source. The
  expected outcome is **5/5 wedge reproduction**, replicating
  the `riscv-btor2` headline. If any wedge fails to reproduce,
  that is the iteration's diagnostic (translator gap, schema
  gap, or genuine AArch64-vs-RV64 semantics divergence).
- **P9 — Shadow mode + `FREE` sentinel**.
- **P10 — Multi-engine cross oracle**.
- **P11 — SV-COMP slice ingestion**: stream + AArch64
  cross-compile.
- **P12 — k-induction + Spacer**.
- **P13 — SOTA baselines (additional)**: ESBMC, SeaHorn,
  Symbiotic, angr.
- **P14+ — Iteration**.

## 8. Concrete SOTA-comparison benchmark

**Initial target corpus**: the 5 wedge tasks from `riscv-btor2`
(0115 / 0116 / 0117 / 0118 / 0121) lifted to AArch64. Same C
source, AArch64 cross-compile.

**Headline metric**: reproduce the 5/5 wedge rate against CBMC.

**Stretch metric**: dominate the Pareto frontier on a 25-task
slice analogous to the v0.4 sweep.

## 9. Stop / escalation conditions

Same as `riscv-btor2`. Additionally:

- **If wedges don't reproduce on AArch64 after P8 measurement
  is clean**, that is a **soft BLOCKER** — the wedge thesis is
  ISA-specific in a way the v2 architecture did not anticipate.
  Write the diagnostic and stop; the user decides whether to
  continue.

## 10. What the agent is and is not authorized to do

**Authorized:**

- Create, edit, delete files on `aarch64-btor2-bootstrap`.
- Commit and push to `aarch64-btor2-bootstrap` on origin.
- Install Python packages into `.venv-aarch64/`.
- Run tests, run the harness on ≤ 5 corpus tasks per iteration.
- Spawn subprocesses with bounded timeout / memory caps.
- Use a pinned AArch64 cross-toolchain (`aarch64-linux-gnu-gcc`)
  via `apt install` in this session's environment — or via a
  pinned Docker image documented in `bench/aarch64-btor2/Dockerfile`.
- Use `qemu-aarch64-static` for source-interpreter golden
  traces (run the same ELF; compare interpreter output to QEMU
  output). QEMU is the *external* oracle for the source
  interpreter, analogous to how RV64 source-interp tests use
  Spike or similar.

**Not authorized:**

- Touching `main`, `v2-bootstrap`, or any other pair's branch.
- Force-pushing, history rewrite.
- Cloning the ARM Architecture Reference Manual or any
  large reference corpora.
- Running anything in parallel beyond `-j 2`.

## 11. Relationship to `main` and `v2-bootstrap`

`main` is v1 reference. `v2-bootstrap` is the `riscv-btor2` v2
line. This branch is the **second-ISA port** that validates the
v2 pair-architecture's portability claim. Maximize reuse;
*every* divergence from the `riscv-btor2` shape should have a
justification noted in the relevant `SCHEMA.md` section or
`PLAN.md` entry.

Do not modify `riscv-btor2` from this branch.
