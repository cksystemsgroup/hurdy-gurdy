# `ebpf-btor2` benchmark scope

This is the §9.1 instantiation of [BENCHMARKING.md](../../BENCHMARKING.md)
for the `ebpf-btor2` pair.

## 1. Source language and dialect

- **Spec**: eBPF instruction set as defined by Linux kernel
  documentation (`Documentation/bpf/instruction-set.rst`) and the
  IETF draft (`draft-ietf-bpf-isa`).
- **Subset in scope (P1 schema v1.0.0)**:
  - **ALU64 + ALU32**: add, sub, mul, div, mod, or, and, lsh, rsh,
    neg, xor, mov, arsh, end (byte-swap).
  - **Branches**: ja, jeq, jgt, jge, jne, jsgt, jsge, jlt, jle,
    jslt, jsle (immediate + register operands).
  - **Exit**.
  - **Load immediate (lddw)** and inline immediate ops.
  - **Load/store** (B/H/W/DW, signed and unsigned variants).
  - **Stack model** (`r10`-relative addressing).
  - **Call** (BPF_CALL): in-program subroutine calls only at P1;
    helper calls are P9.
- **Out of scope at P1**:
  - Helper calls (`BPF_CALL` with `imm = helper_id`) — P9.
  - Map access (via helpers) — P11.
  - Packet / context memory — P10.
  - Tail calls — P12.
  - Spin locks (`bpf_spin_lock`) — defer.
  - Kfuncs, dynptr, iterators — defer.
  - JIT-emitted machine code (only the source eBPF semantics
    matter for verification; JIT correctness is a separate
    Serval-eBPF problem).
- **Source artifact**: a `.bpf.o` ELF (an LLVM-emitted eBPF
  object) plus an `AnalysisScope(entry_section, included_subprogs)`.
  CO-RE relocations are pre-resolved at the bytecode level
  (treat post-relocation bytecode as the source); BTF is optional
  annotation only.

## 2. Reasoning language and solver inventory

- **Reasoning language**: BTOR2, schema version `1.0.0`. Layered
  shape with eBPF-specific machine:
  - **Registers**: `r0`–`r9` as `bv64` state. `r10` modeled as a
    fixed constant (stack top).
  - **Stack**: `Array bv12 bv8` (4096-byte address space wrap;
    actual stack is 512 B but the address space allows
    out-of-bounds detection).
  - **PC**: `bv32` (instruction index).
  - **Exit flag**: `bv1`; on exit, `r0` carries the return value.
  - **Helper-call counter**: `bv32`; tracks calls for spec-pinned
    upper bounds.

- **Solver inventory** (target):

| Engine        | Backend          | Role |
|---------------|------------------|------|
| `z3-bmc`      | z3 4.16.0        | BMC; default. |
| `z3-spacer`   | z3 4.16.0        | Inductive (Horn). Important for unbounded loops the kernel verifier rejects. |
| `bitwuzla`    | 0.9.0+           | BMC alternative; bitvector-strong. |
| `cvc5`        | 1.3.3+           | BMC alternative; second-vendor cross-check. |
| `pono`        | 2.0.0-beta+      | Subprocess BMC + k-induction. |

## 3. Property language

A `QuestionSpec` for `ebpf-btor2` targets one of:

- **`safety(register_bound)`** — does `r0` (or any reg) stay
  within a declared range at every step? (Inductive engines.)
- **`safety(stack_in_bounds)`** — does every stack access stay
  within `[r10 - 512, r10)`?
- **`safety(map_access_valid)`** — does every map access satisfy
  the map's declared key/value bounds? (P11+.)
- **`reach(register_value)`** — does `r0` ever equal a target
  value within `bound` instructions?
- **`reach(helper_arg)`** — does a helper get invoked with a
  specific argument matching a predicate?

Witness format: a sequence of `(packet_byte_assignment,
map_value_assignment, helper_return_assignment, step_index)`
pairs naming the `Free` cells.

## 4. Corpus structure

```
bench/ebpf-btor2/corpus/
  seed/
    0001-alu-add-bound/
      task.toml         # ground truth, expected
      task.bpf.o        # compiled object
      task.c            # source (for review)
      task.spec.json    # QuestionSpec
    0002-loop-bounded-trip-count/
    ...
  kernel_rejects/         # the headline class
    0050-bounded-loop-too-deep/
      task.bpf.o
      task.c
      task.kernel-log   # verifier log showing rejection
      task.spec.json
      task.notes.md     # why this program is actually safe
    ...
  external/               # streamed from Cilium/Falco/Pixie
    cilium-NNN/
    ...
```

Seed tasks pin each schema feature. The `kernel_rejects/`
subdirectory is the main wedge corpus: programs the in-kernel
verifier rejects (verifier log captured) but are
demonstrably safe (notes capture the proof obligation).

## 5. SOTA baselines

- **In-kernel verifier** — load programs via `bpf(BPF_PROG_LOAD)`
  using a test-only program type (e.g.,
  `BPF_PROG_TYPE_SOCKET_FILTER`) and capture the verifier verdict.
  Adapter must **skip-with-note** if `CAP_BPF` unavailable.
- **Prevail** — research tool; install via its repo.
  Skip-with-note if unavailable.
- **Serval-eBPF** — Rosette-based; closest thesis competitor.
  Best-effort install; skip-with-note.

Each baseline gets one adapter under `bench/ebpf-btor2/baselines/`.

## 6. The wedge class to chase

**Completeness wedges, not soundness wedges.** Each wedge is a
program where:

1. The Linux in-kernel verifier **rejects** the program
   (`bpf(BPF_PROG_LOAD)` returns `-EACCES` with a "verifier
   rejected" log).
2. The program is **demonstrably safe** under the relevant
   property (bounded register values, stack-in-bounds, valid map
   access).
3. Hurdy-gurdy + an SMT solver **proves the property** within
   the time/RAM caps.

Candidate wedge classes from public discussion:

- **Bounded loops with high trip counts** — verifier gives up
  past 1M instructions; LLM-pinned loop bound + BMC succeeds.
- **Pointer arithmetic with multi-source pointers** — verifier
  conservatively rejects; bv arithmetic handles it.
- **Map-key-from-packet** — verifier loses precision on keys
  derived from packet data; BMC tracks the key range.
- **Helper return-value bounds** — verifier uses signature-only
  return type; spec-pinned return-range tightens the bound.
- **Stack accesses with computed offsets** — verifier rejects
  unless offset is constant; BMC handles symbolic offsets with
  range constraints.

## 7. Out-of-scope properties

- **Performance bounds** (instruction count, JIT code size) —
  out of scope until the verifier instruction-counting mechanism
  is modeled.
- **Concurrent safety** — eBPF is single-program at a time; no
  inter-program properties.
- **Probabilistic helper outputs** (`bpf_get_prandom_u32`) — the
  output range is pinned by spec; cryptographic-strength
  reasoning out of scope.
- **Tail-call chains** (multi-program graphs) — single program
  at P1.
