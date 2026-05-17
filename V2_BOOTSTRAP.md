# Hurdy-Gurdy — `ebpf-btor2` Pair Bootstrap

> Self-contained brief for a long-running autonomous agent. The agent's
> job is to build the `ebpf-btor2` pair from scratch on the
> `ebpf-btor2-bootstrap` branch, following this spec, until the pair
> beats the Linux in-kernel verifier (and other eBPF verification
> tools) on a class of well-defined safety properties.
>
> A fresh Claude Code session should be able to pick up purely from
> this file + `V2_AGENT_LOOP.md` + `V2_PROGRESS.md`. The reference
> `riscv-btor2` pair lives on branch `v2-bootstrap`.

## 1. Thesis

Hurdy-gurdy is a **question compiler**: it deterministically translates
`(QuestionSpec, source program)` into a reasoning artifact for an
external solver, then lifts the verdict back to source-level facts.
*The framework does no reasoning; the LLM does.*

This pair's **wedge thesis is different from the others**. eBPF
has well-formalized semantics (Prevail formal model, Serval-eBPF
in Coq), and the Linux kernel ships its own in-kernel verifier.
The wedge here is **completeness, not soundness**:

> The in-kernel eBPF verifier is famously **conservative**: it
> rejects valid programs that a precise BMC could prove safe.
> Industrial users (Cilium, Falco, Pixie, Katran) routinely
> wrestle with verifier rejections of demonstrably-correct code
> (bounded loops past the cBPF era, complex pointer arithmetic
> with provable bounds, helper-call preconditions the verifier
> can't reason through).

Hurdy-gurdy's claim: a precise, ISA-grade eBPF-to-BTOR2 translator
plus an SMT solver can **prove safe** programs the in-kernel
verifier **rejects** — closing false-negative gaps the verifier's
designed-for-speed heuristics leave open.

Symmetric thesis to soundness wedges, equally fundable: false
negatives in a gate-keeper verifier mean valid programs cannot
ship.

The three pillars, load-bearing from commit zero:

1. **Source interpreter** (`source_interp/`) — a concrete executor
   of eBPF bytecode (11 registers, 512-byte stack, packet/map
   memory, helper calls).
2. **Reasoning interpreter** (`reasoning_interp/`) — a concrete
   executor of BTOR2. Reusable from `v2-bootstrap`.
3. **Translator** (`translation/`) — the deterministic compiler
   from eBPF bytecode + scope to BTOR2.

The translator's correctness contract is interpreter-trace
alignment.

## 2. Why this can outperform SOTA

Existing eBPF verification:

- **Linux in-kernel verifier** — fast, conservative, rejects
  valid programs. The de facto gate. Reference for the wedge.
- **Prevail** (Microsoft Research, USENIX ATC 2019) — abstract
  interpretation; more precise than the in-kernel verifier
  on numeric domains, less so on pointers. Single research tool.
- **Serval-eBPF** (UW, OSDI 2020) — symbolic execution +
  Rosette. Bytecode-level. Strong on JIT correctness; the
  closest existing thesis competitor.
- **BPFContract** — pre/post conditions; user-supplied
  invariants.
- **Crucible-eBPF** — Galois research; symbolic execution.

Hurdy-gurdy's edge claims:

1. **Programs rejected by the in-kernel verifier as
   "unbounded" are proved safe by hurdy-gurdy** when an LLM
   reads the source and pins the loop bound. The verifier
   gives up at 1M instructions; BMC at the right bound
   succeeds in seconds.
2. **Helper-call preconditions** — verifier conservatively
   models helpers via type signatures alone. Hurdy-gurdy
   models the relevant helpers' return-value ranges
   precisely (per spec) and proves bounds the verifier
   cannot.
3. **Pointer-arithmetic safety** — verifier rejects valid
   pointer arithmetic involving multiple bases; BMC with
   bv arithmetic handles it.
4. **Map access patterns** — verifier rejects valid map
   accesses whose key is derived from packet data; BMC
   tracks the key's range precisely.

## 3. The three pillars in detail

### 3.1 Source interpreter (`gurdy/pairs/ebpf_btor2/source_interp/`)

A concrete executor of eBPF at the same fidelity the translator
claims.

Required capabilities:

- **Run**: `(insns, scope, packet, maps) → trace`.
- **Bindings**: `Free` sentinel for packet bytes, map contents,
  helper return values not pinned by the spec.
- **Shadow mode**: per-instruction records of register / stack /
  packet / map reads and writes.
- **Determinism**.
- **No solver dependency**.

Registers: `r0`–`r10`, all 64-bit. `r10` is read-only stack
pointer, points to a 512-byte stack frame.

Out of scope at day one (add with schema bumps):
- **JIT-specific behavior** (only the bytecode interpreter
  semantics matter for verification).
- **Multi-program tail calls** — at most one tail call depth
  initially.
- **Spinlocks, kfuncs, dynptr** — defer.
- **CO-RE relocations** — pre-resolved at the bytecode level
  (treat relocated bytecode as the source).

### 3.2 Reasoning interpreter (`gurdy/pairs/ebpf_btor2/reasoning_interp/`)

A concrete executor of BTOR2. **Reuse the riscv-btor2
implementation verbatim**.

### 3.3 Translator (`gurdy/pairs/ebpf_btor2/translation/`)

The `(spec, insns) → btor2_model` compiler.

Translator topology:

- **header**: sorts. `bv64` for registers and most data,
  `bv8`/`bv16`/`bv32` for narrowed loads, array sorts for
  stack/packet/map memory.
- **machine**: state — `r0`–`r9` as `bv64`, stack as
  `Array bv12 bv8` (4 KiB max for the stack — eBPF has 512 B
  but address-space-coding-wise the array can be larger to
  encompass stack-relative addressing into helpers), packet as
  `Array bv32 bv8` with bounds, maps as `Array bv64 bv64` per
  map (or per-key-type), helper-call counter, PC, exit flag.
- **library**: per-opcode lowering. eBPF has ~100 opcodes
  (ALU/ALU64, branch, load/store, call, exit). Each becomes a
  parameterized lowering.
- **dispatch**: PC-keyed ITE.
- **init**: initial state — `r1 = context_pointer`,
  `r10 = stack_top`, packet metadata pinned.
- **constraint**: spec assumptions (e.g.,
  `packet_size >= MIN_HEADER`, `map_value_size == 8`).
- **bad**: property under investigation.

Schema version begins at `1.0.0`.

## 4. The interpreter-alignment correctness oracle

For each task:

```
trace_src  = source_interp.run(insns, scope, packet, maps,
                                record_shadow=True)
artifact   = translator.compile(spec, insns, scope)
verdict, witness = dispatch(artifact, spec.engine)

if verdict == "reachable":
    trace_rsn = reasoning_interp.replay(artifact, witness)
    assert align(trace_src_with_same_inputs, trace_rsn).ok
elif verdict in {"unreachable", "proved"}:
    trace_src_concrete = source_interp.run(insns, scope,
                                            zero_packet, empty_maps)
    assert not violates_property(trace_src_concrete, spec.property)
```

`bench/ebpf-btor2/oracle_align.py`.

## 5. Repo scaffold

```
gurdy/
  pairs/
    ebpf_btor2/
      SCHEMA.md
      __init__.py
      spec.py
      source/                  # eBPF object loader (.bpf.o), insn decoder
      source_interp/           # eBPF concrete executor + shadow
      reasoning_interp/        # BTOR2 simulator (reused)
      translation/             # the translator
      lift/                    # witness → source-level facts
      solvers/                 # engine adapters
bench/
  ebpf-btor2/
    SCOPE.md
    corpus/
      seed/                    # hand-crafted T0–T3
      kernel_rejects/          # programs the in-kernel verifier rejects
      external/                # curated programs from Cilium/Falco/Pixie
    harness.py
    oracle_align.py
    oracle_cross.py
    engine_bench.py
    baselines/
      kernel_verifier.py
      prevail.py
      hurdy_gurdy.py
      pareto.py
tests/
  pairs/ebpf_btor2/
V2_BOOTSTRAP.md                # this file
V2_AGENT_LOOP.md
V2_PROGRESS.md
```

## 6. Phase plan (the agent owns and extends this)

- **P0 — Scaffold & contracts**: directory layout; copy
  `gurdy/core/` from `v2-bootstrap`.
- **P1 — Schema v1.0.0**: minimal viable — ALU64 + branches +
  exit only, no loads/stores, no helpers, no maps. BMC engine,
  reach-property `QuestionSpec`. SCHEMA.md frozen.
- **P2 — Source interpreter (ALU + branch + exit subset)**:
  bytecode decoder; register model; trap semantics.
- **P3 — Reasoning interpreter (BTOR2)**: port from
  `v2-bootstrap`.
- **P4 — Translator (ALU subset → BTOR2)**: minimum viable.
- **P5 — Alignment oracle**.
- **P6 — Dispatch & solver adapter**: z3-bmc + bitwuzla.
- **P7 — Seed corpus + harness**: 5–10 hand-crafted ALU-only
  tasks proving simple register-value bounds.
- **P8 — Load/store + stack model**: schema bump 1.0.0 → 1.1.0.
- **P9 — Helper call model**: schema bump. Helpers as
  spec-parameterized abstract functions with declared return
  ranges. Initially: `bpf_map_lookup_elem`,
  `bpf_get_prandom_u32`, `bpf_ktime_get_ns`,
  `bpf_skb_load_bytes`.
- **P10 — Packet / context memory model**: schema bump.
- **P11 — Map memory model**: schema bump. Each map type
  (HASH, ARRAY, PERCPU_ARRAY) gets its own BTOR2 array shape.
- **P12 — Kernel-verifier-rejects corpus**: hand-curated
  programs the in-kernel verifier rejects but are demonstrably
  safe. Sourced from upstream LKML discussions, Cilium issue
  tracker, etc. Streaming recipe (`V2_AGENT_LOOP.md` §4).
- **P13 — k-induction + Spacer**: `proved` verdicts for
  unbounded-loop programs where an inductive invariant exists.
- **P14 — SOTA baselines**: in-kernel verifier (run programs
  via `bpf(BPF_PROG_LOAD)` and capture verifier log), Prevail,
  Serval-eBPF (best-effort).
- **P15+ — Iteration**.

## 7. Concrete SOTA-comparison benchmark

**Initial target corpus**: 20–30 hand-crafted eBPF programs
plus a curated set of "verifier reject" programs from public
sources.

The headline metric is **(verifier reject) ∧ (hurdy-gurdy
proves safe) ∧ (program is actually safe)** — a wedge in the
completeness column.

**Metrics per task**: `verdict ∈ {true, false, unknown, error}`,
`wall_seconds`, `peak_rss_mb`, `ground_truth`, `correct`,
`false_positive`, `kernel_verdict ∈ {accept, reject, error}`.

**Pareto criterion**: hurdy-gurdy wins overall on the
completeness axis if it proves safe ≥ K programs the kernel
verifier rejects, where K is the seed corpus size, and produces
no false positives on the accepted-and-safe set.

## 8. Stop / escalation conditions

Same as other pairs: pause and `BLOCKER:` on schema-break-≥-25%,
unlocalizable alignment failure recurrence, RAM cap risk, 10
iterations without Pareto progress, any destructive operation
needed.

## 9. What the agent is and is not authorized to do

**Authorized:**

- Create, edit, delete files on `ebpf-btor2-bootstrap`.
- Commit and push to `ebpf-btor2-bootstrap` on origin.
- Install Python packages into `.venv-ebpf/`.
- Run tests, run the harness on ≤ 5 corpus tasks per iteration.
- Spawn subprocesses with bounded timeout / memory caps.
- **Load eBPF programs into the kernel verifier as a
  measurement**, but only via `bpf(BPF_PROG_LOAD)` with the
  program type marked test-only (e.g., `BPF_PROG_TYPE_SOCKET_FILTER`),
  and only when the harness explicitly invokes the baseline
  adapter. **Never auto-attach** programs to a hook (tracepoint,
  XDP, etc.).

**Not authorized:**

- Touching `main`, `v2-bootstrap`, or any other pair's branch.
- Force-pushing, history rewrite.
- Running eBPF programs that attach to live kernel hooks.
- Loading eBPF programs with `CAP_BPF` privileges this session
  does not have; skip-with-note instead.
- Cloning kernel sources in full; use the streaming recipe for
  per-file fetches.

## 10. Relationship to `main` and `v2-bootstrap`

`main` is v1 reference. `v2-bootstrap` is the `riscv-btor2` v2
line. This branch inherits patterns but builds an independent
pair. Do not modify `riscv-btor2` from this branch.

## 11. Note on environment

The remote execution environment may or may not have kernel
eBPF loading available (`CAP_BPF`, recent kernel). The
`baselines/kernel_verifier.py` adapter must **skip-with-note**
when loading fails, not error the loop. Wedge measurements that
require the kernel verdict can be deferred to a session with
kernel access.
