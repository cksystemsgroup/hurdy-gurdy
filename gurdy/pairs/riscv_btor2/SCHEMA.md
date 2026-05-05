# `riscv-btor2` schema

This document is the contract between hurdy-gurdy and any consumer
(LLM or human) of the `riscv-btor2` pair's output. Every translation
choice this pair makes is recorded here. If the code disagrees with
this document, the code is wrong; if the schema is wrong, fix it and
bump the version.

The invariant: same `(QuestionSpec, RV64 ELF)` produces a byte-
identical BTOR2 reasoning artifact under this schema version.

## 1. Versioning

- **Schema version:** `1.0.0`.
- The schema version is recorded on every cached artifact and on
  every annotation-sidecar entry.
- A change that affects emitted bytes (different node ordering, new
  default, encoding tweak) bumps the *minor* component. A breaking
  change to the spec language or layer set bumps the *major*.

## 2. Sorts

The pair declares one universal `header` layer that emits all sorts.
Every cross-layer reference uses the symbolic export name, not a
numeric id, so sort-id renumbering during linking is invisible to
downstream layers.

| Symbolic name | Sort | Width / args |
|---|---|---|
| `bv1` | bitvec | 1 |
| `bv5` | bitvec | 5 (RVC compressed shift / register fields) |
| `bv6` | bitvec | 6 (RV64 shift amount) |
| `bv7` | bitvec | 7 |
| `bv8` | bitvec | 8 |
| `bv12` | bitvec | 12 (I- and S-type immediate) |
| `bv16` | bitvec | 16 |
| `bv20` | bitvec | 20 (U-type immediate) |
| `bv32` | bitvec | 32 |
| `bv64` | bitvec | 64 (XLEN; the dominant sort) |
| `mem` | array | index `bv64`, element `bv8` (byte-addressable, big-enough address space) |

XLEN is fixed at 64 bits in this pair. RV32 is a separate pair if it
ever ships. The memory sort is byte-granular and indexed by the full
64-bit address — sub-XLEN truncation is the consumer's job, not the
schema's.

## 3. State variables

Emitted once in the `machine` layer. State naming is fixed so that
linker exports are predictable.

### Registers

- 32 general-purpose registers `x0` through `x31`, sort `bv64`.
- Symbolic export name pattern: `reg_x{N}` for `N` in `0..31`.
- Register `x0` is *not* declared as state. Every read of `x0`
  resolves to the constant zero; every write to `x0` is dropped.
  This keeps the state vector minimal and matches RISC-V semantics.
- ABI aliases (`ra`, `sp`, ...) are *not* used as state names. The
  annotation records the ABI alias as a hint; the state name is the
  numeric one.

### Program counter

- Single `pc` state, sort `bv64`.
- Symbolic export name: `pc`.
- This pair models a single hart; multi-core is parameterized in the
  declaration layer but unused at v1 (see phase plan).

### Memory

- Single `mem` state, sort `mem` (byte array indexed by `bv64`).
- Symbolic export name: `mem`.
- Halfword, word, and doubleword loads/stores compose two, four, or
  eight `read`/`write` operations against this byte array. Endianness
  is little-endian (RISC-V convention).

### Inputs

- One free-input state `nondet` of sort `bv64` per question, used to
  back the result of unknown side effects (havoc'd register values,
  CSR reads, system calls). Each cycle introduces a fresh symbolic
  value.

## 4. ELF loading

- All `PT_LOAD` segments contribute their `filesz` bytes to memory's
  initial contents. Bytes between `filesz` and `memsz` (the BSS
  region) are initialized to zero.
- Bytes outside any `PT_LOAD` segment are *uninitialized*: the
  initial-state clauses leave them free, and any access to them is
  modelled with no constraint on the byte read. This is a deliberate
  modelling choice — the schema does not silently zero memory the
  binary doesn't claim.
- `e_entry` is recorded in the annotation but does not constrain the
  initial PC. The initial PC comes from the spec's analysis scope
  (typically the entry function's start address).

## 5. Instruction lowering

This section enumerates every supported instruction's BTOR2 fragment.
Operand identifiers (`rs1`, `rs2`, `rd`, `imm`) are decoded values.
RVC encodings are translated to their 32-bit equivalents (per phase
7's `expand_rvc`) before lowering — RVC is *not* given its own
schema entries.

Every entry follows the pattern:
- the BTOR2 expression computing the result `r`
- the register-file write: `next reg_x{rd} = r` (skipped when `rd ==
  0`, since `x0` has no state)
- the PC update: `next pc = pc + length` for sequential instructions;
  per-instruction otherwise.

Throughout: `xN` denotes the current value of `reg_x{N}` (or constant
zero for `x0`); `signed(e)` and `unsigned(e)` denote BTOR2 signed
vs unsigned operators (e.g. `slt` vs `ult`).

### LUI, AUIPC

- `LUI rd, imm`: `r = sign_extend(imm[31:12] << 12, 64)`. Implemented
  as a 64-bit constant.
- `AUIPC rd, imm`: `r = pc + sign_extend(imm[31:12] << 12, 64)`.

### Integer immediate (RV64I)

- `ADDI rd, rs1, imm12`: `r = x{rs1} + sign_extend(imm12, 64)`.
- `SLTI`: `r = ite(signed(x{rs1}) < signed(imm), 1, 0)`, zero-extended
  to 64.
- `SLTIU`: same with unsigned comparison; the 12-bit immediate is
  sign-extended to 64 first, then compared unsigned (RV64I rule).
- `XORI / ORI / ANDI`: bitwise; immediate sign-extended.
- `SLLI / SRLI / SRAI`: 6-bit shift amount on RV64. Logical / arithmetic
  shifts are the BTOR2 `sll` / `srl` / `sra`. Shift amount is masked
  to 6 bits before applying.

### Word-only immediate (RV64I)

- `ADDIW`: `r = sign_extend(low32(x{rs1} + sign_extend(imm12, 64)), 64)`.
- `SLLIW / SRLIW / SRAIW`: shift amount is 5 bits, mask before applying;
  result is `sign_extend(low32(...), 64)`.

### Register-register (RV64I)

- `ADD / SUB`: `r = x{rs1} ± x{rs2}`.
- `SLT / SLTU`: 64-bit signed/unsigned comparison, zero-extended.
- `XOR / OR / AND`: bitwise.
- `SLL / SRL / SRA`: 64-bit shifts; shift amount is `x{rs2}[5:0]`.

### Word-only register-register

- `ADDW / SUBW`: 32-bit op, sign-extended to 64.
- `SLLW / SRLW / SRAW`: shift amount is `x{rs2}[4:0]`.

### Branches

- `BEQ / BNE / BLT / BGE / BLTU / BGEU rs1, rs2, imm`:
  `next pc = ite(cond(x{rs1}, x{rs2}), pc + sign_extend(imm, 64), pc + length)`.
- Comparisons use the obvious BTOR2 operator (`eq`, `neq`, `slt`,
  `sge`, `ult`, `uge`).
- Branch targets are 2-byte aligned by encoding; no extra masking is
  applied.

### Loads and stores

- All addresses are computed as `addr = x{rs1} + sign_extend(imm, 64)`.
- Loads compose multiple `read`s of `mem`. Endianness is little-endian:
  the byte at `addr` becomes the LSB.
  - `LB`: 1 byte, sign-extended to 64.
  - `LBU`: 1 byte, zero-extended.
  - `LH / LHU`: 2 bytes.
  - `LW / LWU`: 4 bytes.
  - `LD`: 8 bytes (no extension needed).
- Stores compose multiple `write`s of the bottom bytes of `x{rs2}`
  to `mem`.
  - `SB`: low 8 bits.
  - `SH`: low 16 bits.
  - `SW`: low 32 bits.
  - `SD`: all 64 bits.
- Misaligned accesses are not specially handled at the schema level;
  they decompose into per-byte `read`/`write`s the same way. If a
  later spec parameter wants to flag misalignment, it can be added.

### Jumps

- `JAL rd, imm`: `r = pc + length`; `next pc = pc + sign_extend(imm, 64)`.
- `JALR rd, rs1, imm12`: `r = pc + length`; `next pc = (x{rs1} +
  sign_extend(imm12, 64)) & ~1`. The `~1` mask is mandated by the
  RISC-V spec.

### Multiply / divide (RV64M)

- `MUL`: low 64 bits of signed×signed product.
- `MULH / MULHSU / MULHU`: high 64 bits with the indicated signedness.
- `DIV / REM`: signed.
  - Division by zero returns: quotient `-1` (all-ones, 64-bit),
    remainder `x{rs1}`.
  - Signed overflow (`INT_MIN / -1`): quotient `INT_MIN`, remainder `0`.
- `DIVU / REMU`: unsigned.
  - Division by zero returns: quotient `2^64 - 1`, remainder `x{rs1}`.
- `MULW / DIVW / DIVUW / REMW / REMUW`: 32-bit op on the low halves;
  sign-extended to 64. Division-by-zero and overflow follow the same
  table on the 32-bit operands.

The divide-by-zero and overflow behaviours are encoded in BTOR2 via
explicit `ite` cases; the underlying `sdiv` / `udiv` / `srem` / `urem`
operators are wrapped accordingly.

### System / FENCE

- `FENCE / FENCE.I`: emitted as no-ops at the schema level (they are
  ordering primitives, not state-changing). Recorded with role
  `OTHER` in the annotation.
- `ECALL / EBREAK`: the schema treats these as transitions to a
  trap/exit state. The state vector adds a `halted` flag (one-bit)
  set on encountering one of these, and the dispatch layer keeps PC
  fixed once `halted` is true. Per-spec assumptions can override.
- `CSRR*`: CSR reads are modelled as fresh `nondet` values unless the
  spec adds an assumption pinning the CSR; CSR writes are dropped
  (no CSR state tracked at v1).

## 6. Dispatch

The `dispatch` layer ties PCs to the per-instruction lowering in the
`library` layer.

- The dispatch layer emits one large nested `ite` keyed on `pc`,
  ordered by ascending PC. Each arm matches one PC in the analyzed
  function set and routes to the corresponding library lowering.
- For PCs *outside* the analyzed set, the dispatch arm self-loops
  (`next pc = pc`) and freezes the register file (every register's
  `next` clause becomes itself). This makes "left the analyzed
  region" detectable by the bad expression and avoids unbounded
  exploration.
- The arm ordering is strictly ascending by PC (deterministic and
  reproducible). Re-ordering or compacting the table is not
  permitted.

## 7. Entry assumptions

These assumptions are added to the `init` and `constraint` layers by
default. Each can be overridden or relaxed via spec parameters.

- **`ra` (x1)** at entry: constrained to point *outside* the analyzed
  function set. Specifically, `ra ∈ excluded_pc_ranges` (a
  spec-supplied set). The default is the union of any non-analyzed
  `PT_LOAD` ranges plus a synthetic exit address `0xFFFF_FFFF_FFFF_FFFE`.
- **`sp` (x2)** at entry: free (no constraint). Specs that want
  alignment can add a `RegisterInit(register=2, op=eq, value=0)`
  modulo 16 — the schema does not assume one.
- **All other GPRs**: free unless the spec pins them via `RegisterInit`.
- **PC at entry**: constrained to the analyzed scope's entry PC.
- **Memory at entry**: bytes inside `PT_LOAD` are pinned via init
  clauses; bytes outside are free.

## 8. Constraint and bad encoding

- The `constraint` layer accumulates one BTOR2 `constraint` per
  spec-supplied invariant or assumption. The conjunction of all
  constraints must hold at every cycle the solver explores.
- Polarity convention: `bad` expressions are *true when the property
  is violated*. A `bad` of `false` is unreachable (proves the
  property); a `bad` of `true` is reachable (refutes the property).
- Multi-clause `bad` aggregates by `or`: the property is violated if
  any individual `bad` clause is.
- `LearnedFact` entries land in `constraint` with their provenance
  preserved in the annotation. The translator does not validate
  semantic applicability — the LLM is responsible for that.

## 9. Havoc semantics

- A spec's `havoc_registers` set replaces the `next` clause of each
  named register with `nondet`. The register's value at every cycle
  is independently free.
- Havoc never changes the *initial* value of a register; only its
  evolution. To free the entry value, drop the corresponding
  `RegisterInit`.
- Memory havoc is not supported at v1. If a spec needs it, the
  pattern would be: replace `mem`'s `next` with a fresh array input
  whose entries are constrained only at observed addresses. This
  encoding is documented here as a *future* schema feature; v1 will
  reject memory havoc with a structured diagnostic.

## 10. Verdict semantics

| Verdict | What it means |
|---|---|
| `reachable` | A finite trace satisfies all constraints and reaches the bad expression. The solver returns a witness in the raw payload. |
| `unreachable` | No trace within the spec's `bound` reaches a `bad`. *This is bounded model-checking only.* It says nothing about behaviour past the bound. |
| `proved` | A *bounded* invariant has been proved; a `proved` answer from a finite-state engine (BMC) is implicit "no trace within bound" and should be reported as `unreachable` instead. Engines that produce inductive invariants (Spacer / Pono) emit `proved` when they prove the property holds at all depths and return the invariant in the raw payload. |
| `unknown` | The solver gave up. The `reason` field on the raw result distinguishes timeout, memory exhaustion, incompleteness on the chosen theory, etc. |

The `bound` parameter:
- For BMC engines, `bound` is the number of cycles unrolled. The
  emitted artifact does not bake the bound in — it stays a
  parametric transition system. The solver is invoked with `bound`
  via its own configuration.
- For Spacer / Pono, `bound` is ignored; these engines explore until
  proof or counterexample.

The `havoc_registers` field of `AnalysisDirective`:
- Affects the artifact bytes (it determines which `next` clauses are
  replaced). Two directives with different `havoc_registers` produce
  different artifacts and different cache entries.

## 11. Annotation conventions

For every emitted node, the annotation records:

- **role**: one of `sort`, `state`, `input`, `init`, `transition`,
  `constraint`, `bad`, `observable`, `assumption`,
  `learned_invariant`, `dispatch`, `binding`, `havoc`, `expression`,
  `other`.
- **source mapping** (`RiscvSourceMapping`): `pc` (where the node
  came from in the binary), `dwarf_file`, `dwarf_line` (when DWARF
  is available), and `mnemonic` (for nodes inside an instruction's
  lowering).
- **provenance**: schema version, spec hash, optional learned-fact
  provenance.

This vocabulary is the contract between `compile` and `introspect`.

## 12. Stability profile (cache behaviour)

| Layer | Recompute when |
|---|---|
| `header` | Never; same bytes for every spec under this schema version. |
| `machine` | Core count changes (not exposed at v1). |
| `library` | ISA subset changes (RV64I+M+C is fixed at v1). |
| `dispatch` | The set of analyzed PCs changes. |
| `init` | Spec's entry assumptions, register/memory inits change. |
| `constraint` | Spec's assumptions or learned facts change. |
| `bad` | Spec's observables or property change. |
| `binding` | Always re-emitted (cheap). |
| `havoc` | `havoc_registers` set changes. |

Cache keys aggregate `(spec_hash, source_hash, schema_version)` plus
the engine name when artifact bytes vary by engine (they do not at
v1). The framework's content-addressed cache covers this
automatically.

## 13. Interpreter semantics

The pair ships two concrete interpreters — one source-side (RV64
simulator) and one reasoning-side (multi-step BTOR2 evaluator) —
which are first-class components of the pair alongside the
translator and lifter. The interpreter version is `1.0.0` and is
recorded on every emitted trace.

Interpretation is the third deterministic component (translation,
dispatch, lifting being the others). Same `(source, binding)` →
identical source trace; same `(artifact, binding)` → identical
reasoning trace.

### 13.1 Source interpreter

- **Architectural state**: 32 × 64-bit registers, byte-addressable
  64-bit memory, 64-bit PC, `halted` flag.
- **Step**: decodes the instruction at the current PC and applies the
  per-instruction lowering of `library.py`. Mirrors §5 exactly. A
  divergence between this simulator and the library lowering is a
  schema/library bug.
- **Halting**: ECALL/EBREAK set `halted=True` and freeze the PC; a
  PC in the spec's `excluded_pc_ranges` halts with reason
  `pc_in_excluded_range`; a PC outside loadable bytes halts with
  reason `fetch_failed`.
- **Trace recording**: the interpreter records *post-step* state in
  each step's `deltas` (PC, full register snapshot, memory changes,
  halted flag) and the source-level location (PC, mnemonic, disasm,
  optional DWARF file/line) in `location`.

### 13.2 Reasoning interpreter

- **Subset**: only the BTOR2 ops the library and translator emit;
  unknown ops raise `NotImplementedError`. Ill-formed BTOR2 (operand
  width mismatches) raises `SortMismatch`. Real solvers reject the
  same inputs.
- **Initial state**: each state nid is initialized from its `init`
  clause (if any), then overridden by the binding's
  `state_init_by_symbol` map. States without either default to zero.
- **Step**: evaluates every node with current state values and any
  per-step inputs, then computes new state values from each state's
  `next` clause. States without a `next` carry forward unchanged.
- **Trace recording**: each step's `layer_values["machine"]` records
  the *post-step* values keyed by state nid. Symbol→nid resolution
  uses the schema's pinned names (`pc`, `reg_x{1..31}`, `mem`,
  `halted`).
- **Bad firing**: `bad_fired_at` is the first step whose post-step
  state satisfies any `bad` clause. The check re-evaluates the
  artifact with the post-step bindings so the recorded state and the
  firing decision agree by construction.

### 13.3 Cross-check correspondence

The two traces are aligned step-by-step by the pair's projection
function. Per step, the projection checks:

| Field | Source | Reasoning |
|---|---|---|
| `pc` | `deltas.pc` | `machine[sym["pc"]]` |
| `reg_x{N}` (N=1..31) | `deltas.regs[N]` | `machine[sym["reg_x{N}"]]` |
| `halted` | `deltas.halted` | `machine[sym["halted"]]` |

`mem` (the BTOR2 memory array) is not compared field-by-field per
step because per-step array equality is expensive on long traces and
this pair's translation already pins memory semantics in §5; a
final-state check is sufficient (and is what `cross_check` exposes).

A divergence means the schema's promise — *same `(spec, source)` →
byte-identical artifact whose semantics match the simulator* — has
been broken on this concrete input. It is always a bug, never a
feature.

### 13.4 Interpreter version

The `interpreter_version` is bumped independently of
`schema_version`. A change to instruction semantics in the simulator
that mirrors a §5 change keeps `interpreter_version` aligned with
`schema_version`. A change that only restructures interpreter code
(packaging, performance, additional fields on traces) bumps the
*minor* component.

Cached traces include `interpreter_version` in their cache key, so
upgrading the interpreter invalidates affected traces.

## 14. What this schema deliberately does not do

- **Floating point.** RV64F/D are out of scope at v1. A future pair
  (or this pair's v2) can add them.
- **Atomics (A extension), vector (V), compressed-with-extensions
  beyond RVC.** Out of scope.
- **Privileged ISA.** Trap handling, supervisor mode, paging,
  interrupts — none of these are modelled; the property's scope is
  user-mode straight-line and branching code.
- **Calling convention enforcement.** The schema does not check that
  callees obey the System V RISC-V ABI. The analysis scope spec
  parameter selects which callees are inlined; everything else is
  treated as opaque (the dispatch self-loop).
- **Concurrency.** Single hart only.

These exclusions are stable. Adding any of them requires a schema
version bump; partial support is not allowed.
