# Benchmarks — coverage, and how triviality is caught

A pair (or a route) can satisfy the letter of its contract while gutting the
substance: translate only `add`/`addi`, pass a commuting-square check on the
five inputs it chose, and declare victory. This document is the contract
that prevents that. It introduces **coverage** as the second axis alongside
**fidelity** ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §7), defines how both
are measured against yardsticks the implementer does **not** choose, and
specifies per-pair and per-route benchmarking with reasonable size caps.

It is a cross-cutting contract, peer to [`SOLVERS.md`](./SOLVERS.md) and
[`ROUTES.md`](./ROUTES.md).

## 1. Two axes, conjoined — the anti-triviality move

- **Fidelity** answers *is what you translated faithful?* (the commuting
  square + the tiers, [`ARCHITECTURE.md`](./ARCHITECTURE.md) §7).
- **Coverage** answers *how much of the language did you actually translate?*

Each axis alone is gameable, in opposite directions:

| Gamed by… | Defeated by |
|-----------|-------------|
| **triviality** — a tiny fragment, vacuously faithful | requiring **coverage** against an external yardstick |
| **unsoundness** — broad but wrong | requiring **fidelity** (the square) on everything counted |

So the platform reports them **conjoined per construct**: a construct counts
only when it is **covered *and* faithful**. The headline number for a pair is
*"constructs that are both covered and faithful, out of the language's
total."* You cannot inflate coverage with unsound lowerings, nor call a
faithful-but-tiny pair done.

## 2. Coverage is measured against a yardstick you don't choose

Two yardsticks, increasing in strength:

1. **Construct coverage (universal, spec-derived).** The denominator is the
   *enumerable inventory* of the language taken from its specification — the
   RISC-V opcode list, the Wasm instruction set, the SMT-LIB operators, the
   C grammar's node kinds. Handled ÷ total. The agent cannot shrink the
   denominator; it comes from the spec. Required of **every** pair, including
   reasoning targets (operator coverage of the interpreter).
2. **Benchmark coverage (external, optional-but-default).** The fraction of a
   **public benchmark suite** the pair can load, translate, and — where the
   suite carries labels — answer correctly. The suite is fixed externally
   (§4).

## 3. The honest-failure rule (what makes coverage measurable)

- **No silent unsoundness → typed abort.** An unsupported construct MUST
  hard-abort at load/translate time with `unsupported: <named construct>` —
  never silently dropped, no-op'd, or mis-lowered. This turns a suite run
  into an itemized **`unsupported` histogram** (which constructs blocked how
  many tasks) instead of a green check hiding the gap.
- **Rejection tests.** Suites of inputs that *should* be rejected (invalid
  Wasm, kernel-rejected eBPF) verify the pair aborts correctly — coverage of
  the *boundary*, not just of valid inputs.
- **Fuzz / mutation (defeats a cherry-picked corpus).** Beyond a fixed
  suite, a generator the agent has never seen — Csmith, `riscv-torture`,
  `wasm-smith` — produces fresh programs, differential-checked against the
  formal-model oracle ([`REGISTRY.md`](./REGISTRY.md) "Formal models"). A
  fixed suite can be overfit; a generator cannot. *Built:* an in-house
  **RISC-V ⟂ Sail differential fuzzer** (`tools/riscv_fuzz.py`,
  `tests/test_fuzz_differential.py`) — seeded random RV64IMC programs whose
  traces must agree across the two independent realizations (and whose
  reachability must agree across both branch routes); this needs no external
  oracle. The external-generator axis is now seeded too: a **Csmith differential
  for `c-riscv`** (`tools/csmith_fuzz.py`, gated/in-image) compiles a random
  UB-free C program native vs through the pinned riscv toolchain (a no-libc
  shim, run on the interp, the CRC checksum read from memory) and requires the
  checksums to agree — validated on a Csmith-config slice the pure-Python interp
  can run. `riscv-torture` (against `sail_riscv_sim`) remains pending its
  `sbt`/`scala` tooling ([`DOCKER.md`](./DOCKER.md)).

## 4. Public benchmarks

Where a public suite exists, wiring it is the default; its absence must be
justified in the brief (construct coverage still applies). A suite serves
three roles at once:

- **Coverage meter** — the `unsupported` rate and histogram (§3).
- **External differential oracle** — where the suite is labeled (verdicts,
  golden states), answers are checked against an oracle the agent didn't
  write — a correctness signal independent of the self-graded square.
- **Adversarial breadth** — real suites exercise constructs the agent would
  never have tested.

Candidate suites (these are also what the *formal models* validate against,
so wiring them aligns our interpreter with the model's own oracle):

| Source | Public suite(s) | Labels? |
|--------|-----------------|---------|
| C | **SV-COMP** (`sv-benchmarks`); GCC/LLVM torture; Csmith (fuzz) | verdicts |
| RISC-V | **riscv-tests**, **riscv-arch-test** (compliance), **riscv-torture** (fuzz) | golden state |
| AArch64 | Arm **Architecture Compliance Kit** (validated `sail-arm`) | golden state |
| WebAssembly | the **official Wasm spec tests** (`.wast`) | expected results |
| eBPF | Linux kernel **BPF selftests** + verifier reject cases | partial |
| EVM | **`ethereum/tests`** (state / VM tests; used by KEVM) | post-state |
| CRN | BioModels / SBML model sets; PRISM/STORM case studies | partial |
| SMILES | ChEMBL / PubChem subsets; RDKit test molecules | canonical form |
| Python | CPython test suite (subset) | expected results |
| *(targets)* BTOR2 / SMT-LIB | **HWMCC** / **SMT-LIB (SMT-COMP)** libraries | verdicts |

**Ingestion — hybrid, always pinned.** Small, license-clean compliance
suites enter as **pinned git submodules** (and may be vendored into the dev
image, [`DOCKER.md`](./DOCKER.md)); large suites (SV-COMP) are
**streamed-with-pin** — one task fetched at a time from a pinned
snapshot/commit, never bulk-copied. Either way the suite's snapshot identity
is recorded in every result's provenance, exactly as the image digest is
([`DOCKER.md`](./DOCKER.md)). Streaming respects the RAM discipline: process
one instance fully, then release; cap corpus parallelism.

## 5. Per-pair benchmarking

What a pair reports, and the gate it must pass:

- **Metrics:** construct coverage; benchmark coverage (load + translate +,
  where labeled, answer); the `unsupported` histogram; per-construct fidelity
  (the square holds on what's counted).
- **Floors by language class.** A minimum below which a pair may not be
  called `built` at all: a machine ISA must fully cover its declared base ISA
  (plus the extensions it declares); a finite reasoning bridge
  (`btor2-smtlib`) must cover 100 % of the operator set (it is small and
  spec-enumerable); a high-level pair must clear a declared benchmark
  pass-rate.
- **The coverage ratchet.** Coverage may only go up; a change that raises the
  `unsupported` count or drops the benchmark pass-rate fails CI.
- **Status vocabulary (honest partial).** `registered` → `partial
  (<coverage>)` → `built`. Stopping early yields an honest
  `partial (62 % RV64I, 0 % M/C)` — a legitimate, visible terminal state, not
  a false `built`. The [`PAIRING.md`](./PAIRING.md) §8 done-gate requires
  meeting the brief's coverage target on the external yardstick, with the
  histogram attached.

## 6. Route benchmarking

A route benchmark validates that pairs **compose** ([`ROUTES.md`](./ROUTES.md)) —
the only way to catch bugs invisible per-hop: projection mismatches between
hops, carry-back that doesn't ground at the origin, source-map/provenance
threading errors, and cumulative loss that destroys meaning. **No new
corpus:** a route is driven by its **origin** language's suite (SV-COMP drives
`C→RISC-V→BTOR2→SMT-LIB`).

- **Composed metrics** (the [`ROUTES.md`](./ROUTES.md) laws, now measured):
  end-to-end coverage (= the min across hops — surfaces the weakest hop),
  end-to-end fidelity / verdict accuracy, **determinism** (end-to-end
  recompile-and-diff), and **loss** (does the answer still mean something at
  the origin).
- **Headline metric: branch agreement.** Where two routes reach the same
  target from the same origin (`riscv-btor2` vs `riscv-sail`→`sail-btor2`;
  likewise AArch64), run both on the same task and require agreement, with
  disagreements **localized to a hop/step**. This needs no labels (agreement
  self-corroborates) and is how a branch *earns* its raised fidelity
  ([`ROUTES.md`](./ROUTES.md) §4) — measured, not asserted.

### Reasonable caps (seven dimensions, pinned and declared)

Routes multiply combinatorially and a route runner holds several large
artifacts live at once, so cap every dimension:

1. **Route length** — only routes ≤ *k* hops.
2. **Route count** — a curated set (the spine, both arms of each branch, one
   representative per hub front-end), not all routes.
3. **Tasks per route** — a small *fixed slice* of the origin suite, not the
   whole suite.
4. **Program size** — max instructions / AST nodes per task.
5. **Unrolling bound `k`** — small; `unknown` / `resource-out` beyond it are
   **first-class, not failures** ([`SOLVERS.md`](./SOLVERS.md)). Report the
   *reached-verdict rate* alongside accuracy so caps neither masquerade as
   passes nor as failures.
6. **Wall-time / memory per hop** — tighter for longer routes (cost compounds).
7. **Parallelism** — one task fully through the route, then release.

Two rules keep caps honest:

- **Small ≠ easy.** The capped slice is curated for *diversity within the
  budget* — it must include the hard cases (UB/wedge tasks, loops,
  branch-sensitive inputs), externally chosen and pinned, so a route can't
  pass by routing only trivial tasks.
- **Capped results are labeled as capped** — "branch agreement on a 50-task
  SV-COMP slice, k≤20, 60 s/hop" — never implied as full-suite. The caps are
  part of the result's provenance, like the suite snapshot and image digest.

## 7. The route-grader agent (triggered on merge)

Per-pair agents own one edge and are independent ([`AGENTS.md`](./AGENTS.md));
composition is not their job. Route benchmarking is run by a dedicated
**route-grader agent**:

- **Trigger: merge.** When a pair is merged (built or advanced), the
  route-grader is triggered. It benchmarks the capped routes the merged pair
  participates in, computes the composed metrics and branch agreement (§6),
  and updates each route's status in [`REGISTRY.md`](./REGISTRY.md).
- **Externalized "done."** The route-grader — not the implementing agent —
  computes route status; a pair does not grade the compositions it sits in.
- **Composition ratchet (regression gate).** A merge that breaks a route the
  pair participates in, raises a route's `unsupported` rate, or drops a
  branch's agreement rate **fails** — the merge is a regression. This is the
  route-level analogue of the per-pair ratchet (§5).
- **Cadence.** On-merge of a composing pair (and optionally nightly on the
  capped slices). Lower cadence than per-pair coverage, because it is the
  expensive, combinatorial check — which is exactly why the caps (§6) are
  mandatory.

## 8. What the framework provides vs. what a pair declares

**Framework / grader layer provides:** the construct-inventory extractor
(spec → denominator); the pinned-suite ingestion (submodule + streamed,
§4); the coverage and `unsupported`-histogram computation; the per-pair and
per-route harnesses; the ratchets; and the **route-grader agent** with its
merge trigger (§7). (All framework deliverables —
[`FRAMEWORK.md`](./FRAMEWORK.md) §2.)

**A pair declares** ([`PAIRING.md`](./PAIRING.md)): its in-scope construct
set and coverage **target** (set by the human in the brief,
[`AGENTS.md`](./AGENTS.md) §1 — *not* shrinkable by the agent); the public
suite it wires (or a justification for none); the typed `unsupported` aborts
(§3); and its honest `partial`/`built` status backed by the measured
coverage. It implements no grader of its own.
