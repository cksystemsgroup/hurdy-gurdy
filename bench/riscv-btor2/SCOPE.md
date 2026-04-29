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
  exclusions per `SCHEMA.md` §13.
- **Source artifact**: a single statically-linked RV64 ELF, plus an
  `AnalysisScope(entry_function, included_callees)`. DWARF is
  optional and only used in annotations.

## 2. Reasoning language and solver inventory

- **Reasoning language**: BTOR2, schema version `1.0.0`.
- **Solver inventory** (from `christophkirsch/hurdy-gurdy-bench:2530ee8`,
  digest `sha256:8bae13f23a36…`):

| Engine        | Backend version | BENCHMARKING.md role |
|---------------|-----------------|----------------------|
| `z3-bmc`      | z3 4.16.0       | BMC; default engine in `AnalysisDirective` |
| `z3-spacer`   | z3 4.16.0       | Inductive (Horn / fixedpoint). v1 limitation: spec routes through BMC unless inductive reasoning is explicitly required, in which case it returns `unknown` with a structured reason. |
| `bitwuzla`    | 0.9.0           | BMC alternative; bitvector-strong |
| `cvc5`        | 1.3.3           | BMC alternative; second-vendor cross-check for §3 condition C's "two unrelated tools" criterion when used as oracle |
| `pono`        | commit `59c5cb88` (`v2.0.0-beta.1-52-g59c5cb8`) | Subprocess BMC via vendored smt-switch; alternative engine with different bug surface |

Image hash is the §7 pinning artifact; bumping any version is a new
experiment and a new image tag.

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

RISC-V binaries do not have a direct source-level verifier analogue
of CBMC/ESBMC, so condition D is **omitted** for this pair. The
plausible substitute would be a symbolic execution tool (angr,
manticore) operating on the binary, but those are themselves
"reasoning over the binary" rather than over a higher-level source —
they don't isolate a different value layer. We document the omission
per BENCHMARKING.md §9.4 rather than misrepresenting it.

If the corpus eventually includes tasks whose ELF was produced from
known C source under `-O0`, condition D could be added by running
CBMC against the C — that becomes a separate corpus tier and is out
of scope for v1.

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
