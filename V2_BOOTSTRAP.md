# Hurdy-Gurdy — `evm-btor2` Pair Bootstrap

> Self-contained brief for a long-running autonomous agent. The agent's
> job is to build the `evm-btor2` pair from scratch on the
> `evm-btor2-bootstrap` branch, following this spec, until the pair
> beats established Ethereum smart-contract verification tools on
> standard benchmarks.
>
> A fresh Claude Code session should be able to pick up purely from
> this file + `V2_AGENT_LOOP.md` + `V2_PROGRESS.md`, with no other
> conversation context. The reference `riscv-btor2` pair lives on
> branch `v2-bootstrap`; inspect it freely.

## 1. Thesis

Hurdy-gurdy is a **question compiler**: it deterministically translates
`(QuestionSpec, source program)` into a reasoning artifact for an
external solver, then lifts the verdict back to source-level facts.
*The framework does no reasoning; the LLM does.* See `README.md` and
`PLAN.md` on `main` for the full philosophy.

This pair's **wedge thesis**: EVM (Ethereum Virtual Machine) has
fully defined deterministic semantics — 256-bit modular arithmetic,
gas accounting, byte-addressed storage and memory, deterministic
ABI encoding. Verifiers that reason at the **Solidity** level
(SMTChecker, Certora's CVL-on-Solidity, Slither, Mythril-on-source)
suffer from Solidity↔EVM semantic gaps that bite in security
audits:

- **Pre-0.8 vs ≥ 0.8 overflow semantics** — same source, different
  EVM bytecode, different verification answer.
- **ABI encoding edges** — `bytes`, `string`, dynamic arrays
  encoded by the compiler in ways the source doesn't surface.
- **Storage packing** — multiple state variables co-located in one
  256-bit slot; source-level reasoning loses bit-precise aliasing.
- **`delegatecall` context** — caller's storage, callee's code;
  Solidity-level analysis cannot see the storage layout collision.
- **PUSH0 / EOF transitions** — newer EVM versions change opcode
  semantics in ways the Solidity AST does not encode.

Reasoning at the EVM bytecode level is the audit gold standard
precisely because the bytecode *is* the deployed artifact. Source
verifiers approximate; bytecode verifiers ground truth.

The three pillars, load-bearing from commit zero:

1. **Source interpreter** (`source_interp/`) — a concrete executor
   of EVM bytecode (stack machine + memory + storage + calldata +
   gas).
2. **Reasoning interpreter** (`reasoning_interp/`) — a concrete
   executor of BTOR2. Reusable from `v2-bootstrap`.
3. **Translator** (`translation/`) — the deterministic compiler
   from EVM bytecode + scope to BTOR2.

The translator's correctness contract is interpreter-trace
alignment.

## 2. Why this can outperform SOTA

Existing Ethereum smart-contract verification:

- **Solidity SMTChecker** — built into solc; operates on the
  Solidity IR (Yul / IR-experimental). Source-level, fast,
  conservative on bytecode semantics.
- **Certora Prover** — proprietary, CVL-on-Solidity. Industrial
  audit standard. Source-level with bytecode-aware hooks.
- **hevm** — Haskell-based symbolic EVM execution
  (Mooly Sagiv / a16z fork). Bytecode-level. Closest existing
  competitor on the *thesis*.
- **Mythril** — symbolic execution; bug-finding rather than proof.
- **Slither** — static analysis; pattern matching, no soundness.
- **KEVM (K framework)** — formal EVM semantics in K. Reference
  semantics; verification possible but tooling heavy.
- **Manticore-EVM** — symbolic execution; mature, slow.

Hurdy-gurdy's edge claims, to validate empirically:

1. **Bytecode-level reasoning catches Solidity↔EVM gap bugs
   that SMTChecker / Certora-on-source miss.** This is the
   direct analogue of the C-UB-RV64-defined wedge cluster.
2. **LLM-curated unrolling** — Solidity contracts often have
   loops with evident bounds the LLM can read.
3. **Multi-engine portfolio** — bitvector-strong solvers
   (bitwuzla) likely win on 256-bit arithmetic.
4. **Counterexample-guided refinement in spec space**, not in
   IR space — when a false positive surfaces, the LLM tightens
   the spec at the EVM level (e.g., constraining `CALLER` to
   a non-zero address).

## 3. The three pillars in detail

### 3.1 Source interpreter (`gurdy/pairs/evm_btor2/source_interp/`)

A concrete executor of EVM bytecode at the same fidelity the
translator claims.

Required capabilities:

- **Run**: `(bytecode, scope, calldata, world_state) → trace`.
- **Bindings**: `Free` sentinel for `CALLER`, `CALLVALUE`,
  `CALLDATA[i]`, `BLOCKHASH`, storage cells the spec does not pin,
  return values of external `CALL`s.
- **Shadow mode**: per-instruction records of stack, memory, and
  storage reads/writes.
- **Determinism**: same `(bytecode, scope, calldata, world)` →
  same trace.
- **Gas accounting**: full EIP-150/2929/3529 gas model. Spec may
  pin gas-limit or treat it as `Free`.
- **No solver dependency**.

Out of scope at day one (add later):
- **Precompiles** beyond identity / ecrecover (modeled as `Free`
  imports initially).
- **External `CALL` to other contracts** (modeled as
  uninterpreted function returning a `Free` value initially).
- **Block-level state** (blockhash, timestamp): `Free` initially.

### 3.2 Reasoning interpreter (`gurdy/pairs/evm_btor2/reasoning_interp/`)

A concrete executor of BTOR2. **Reuse the riscv-btor2
implementation verbatim** unless the EVM translator emits BTOR2
nodes the existing simulator doesn't handle. Tag the copy with
`INTERPRETER_VERSION` so divergence is auditable.

### 3.3 Translator (`gurdy/pairs/evm_btor2/translation/`)

The `(spec, bytecode) → btor2_model` compiler. Mechanical, pure,
deterministic.

Translator topology:

- **header**: BTOR2 sort declarations. `bv256` is the dominant
  sort for stack slots, storage values, arithmetic. `bv8` for
  memory and calldata. Array sorts for memory, storage, calldata.
- **machine**: state — operand stack (modeled as an array `bv8
  bv256` with explicit SP, or unrolled to fixed depth ≤ 1024 per
  spec), memory (`Array bv256 bv8`), storage (`Array bv256
  bv256`), PC, gas, trap flag, return-data buffer.
- **library**: per-opcode lowering. EVM has ~150 opcodes; each
  becomes a parameterized lowering.
- **dispatch**: PC-keyed ITE selecting which opcode lowering
  applies at each step.
- **init**: initial state from the spec — pinned storage cells,
  pinned calldata, code (immutable).
- **constraint**: spec assumptions (e.g., `CALLER != 0`, `msg.value
  == 0`).
- **bad**: property under investigation.
- **binding**: next clauses wiring states to dispatch.

Schema version begins at `1.0.0`.

## 4. The interpreter-alignment correctness oracle

For each task:

```
trace_src  = source_interp.run(bytecode, scope, calldata, world,
                                record_shadow=True)
artifact   = translator.compile(spec, bytecode, scope)
verdict, witness = dispatch(artifact, spec.engine)

if verdict == "reachable":
    trace_rsn = reasoning_interp.replay(artifact, witness)
    assert align(trace_src_with_same_inputs, trace_rsn).ok
elif verdict in {"unreachable", "proved"}:
    trace_src_concrete = source_interp.run(bytecode, scope,
                                            zero_calldata, world)
    assert not violates_property(trace_src_concrete, spec.property)
```

This is `bench/evm-btor2/oracle_align.py`. Primary correctness
oracle; `oracle_cross.py` is the secondary multi-engine oracle.

## 5. Repo scaffold (logical target)

```
gurdy/
  pairs/
    evm_btor2/
      SCHEMA.md
      __init__.py
      spec.py
      source/                  # bytecode disassembler, ABI helpers
      source_interp/           # EVM concrete executor + shadow
      reasoning_interp/        # BTOR2 simulator (reused)
      translation/             # the translator
      lift/                    # witness → source-level facts
      solvers/                 # engine adapters
bench/
  evm-btor2/
    SCOPE.md
    corpus/
      seed/                    # hand-crafted T0–T3
      external/                # curated contracts (verified-source
                               # mainnet bytecode samples)
    harness.py
    oracle_align.py
    oracle_cross.py
    engine_bench.py
    baselines/
      smtchecker.py
      hevm.py
      hurdy_gurdy.py
      pareto.py
tests/
  pairs/evm_btor2/
V2_BOOTSTRAP.md                # this file
V2_AGENT_LOOP.md
V2_PROGRESS.md
```

## 6. Phase plan (the agent owns and extends this)

- **P0 — Scaffold & contracts**: directory layout above; copy
  `gurdy/core/` from `v2-bootstrap`.
- **P1 — Schema v1.0.0**: minimal viable — pure functions
  (no `CALL`, no `DELEGATECALL`), single contract, BMC engine,
  reach-property `QuestionSpec`. Frankfurt / London EVM
  (PUSH0 available, EIP-3855). SCHEMA.md frozen.
- **P2 — Source interpreter (EVM, pure subset)**: bytecode
  disassembler; stack/memory/storage model; pure-arithmetic +
  control opcodes; trap semantics (stack overflow/underflow,
  OOG, invalid jumpdest). No `CALL` family yet.
- **P3 — Reasoning interpreter (BTOR2)**: port from
  `v2-bootstrap`.
- **P4 — Translator (EVM pure-subset → BTOR2)**: minimum viable.
- **P5 — Alignment oracle**: `bench/evm-btor2/oracle_align.py`.
- **P6 — Dispatch & solver adapter**: z3-bmc + bitwuzla. Bitwuzla
  likely critical: 256-bit arithmetic is its strongest suit.
- **P7 — Seed corpus + harness**: 5–10 hand-crafted tasks
  targeting the wedge class:
  - `0001-pre-0.8-overflow` — Solidity ≤ 0.7 `a + b` overflows
    silently; SMTChecker (with default config) over-approximates;
    bytecode shows the wrap.
  - `0002-storage-pack-aliasing` — two `uint128` packed into one
    slot; source-level may miss the aliasing on `sload`.
  - `0003-delegatecall-storage-collision` — caller storage
    layout != callee storage layout; bytecode-level catches.
  - `0004-abi-decode-malformed` — calldata shorter than
    expected; source-level often assumes well-formed.
  - `0005-push0-version-mismatch` — same Solidity source compiled
    with PUSH0-disabled vs enabled; different bytecode.
- **P8 — Shadow mode + `FREE` sentinel** for calldata / CALLER /
  external CALL returns.
- **P9 — Multi-engine cross oracle**: cvc5, pono adapters.
- **P10 — k-induction + Spacer**: enables `proved` verdicts.
- **P11 — `CALL` / `DELEGATECALL` / `STATICCALL` support**:
  initially as uninterpreted functions over storage / return data;
  later with controlled inlining via `included_callees`-equivalent.
- **P12 — External corpus**: stream from Etherscan verified-source
  contracts via the streaming recipe (`V2_AGENT_LOOP.md` §4) —
  never bulk-clone.
- **P13 — SOTA baselines**: SMTChecker, hevm, Manticore-EVM.
  Pareto table.
- **P14+ — Iteration**: Pareto-driven refinements.

## 7. Concrete SOTA-comparison benchmark

**Initial target corpus**: 20–30 hand-crafted contracts paired
with the Solidity source. Each has a property of the shape
`reach(revert)` or `reach(storage[X] == V)` and a ground-truth
answer hand-determined from the EVM semantics.

**Metrics per task**: `verdict ∈ {true, false, unknown, error}`,
`wall_seconds`, `peak_rss_mb`, `ground_truth`, `correct`,
`false_positive`.

**Pareto criterion**: hurdy-gurdy wins overall if there is no SOTA
tool with strictly better (correct, total_time) at the same or
lower false-positive rate.

## 8. Stop / escalation conditions

Same as `riscv-btor2`: pause and `BLOCKER:` on schema-break-≥-25%,
unlocalizable alignment failure recurrence, RAM cap risk, 10
iterations without Pareto progress, any destructive operation
needed.

## 9. What the agent is and is not authorized to do

**Authorized:**

- Create, edit, delete files on `evm-btor2-bootstrap`.
- Commit and push to `evm-btor2-bootstrap` on origin.
- Install Python packages into a local venv at `.venv-evm/`.
- Run tests, run the harness on ≤ 5 corpus tasks per iteration.
- Spawn subprocesses with bounded timeout (60s default) and memory
  caps (2 GiB).
- Fetch verified-source bytecode from Etherscan one contract at a
  time via the streaming recipe; never bulk-clone.

**Not authorized:**

- Touching `main`, `v2-bootstrap`, or any other pair's branch.
- Force-pushing, history rewrite, deleting branches.
- Installing solc globally; use a pinned local install per
  test.
- Running anything in parallel beyond `-j 2`.
- Cloning Etherscan mass-export archives.

## 10. Relationship to `main` and `v2-bootstrap`

`main` is v1 reference. `v2-bootstrap` is the `riscv-btor2` v2
line where the foundation patterns were established. This branch
**inherits the patterns** but builds an independent pair. Do not
modify `riscv-btor2` from this branch.
