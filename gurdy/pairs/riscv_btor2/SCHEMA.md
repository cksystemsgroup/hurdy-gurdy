# `riscv-btor2` schema

This document is the contract between hurdy-gurdy and any consumer
(LLM or human) of the `riscv-btor2` pair's output. Every translation
choice this pair makes is recorded here. If the code disagrees with
this document, the code is wrong; if the schema is wrong, fix it and
bump the version.

The invariant: same `(QuestionSpec, RV64 ELF)` produces a byte-
identical BTOR2 reasoning artifact under this schema version.

## 1. Versioning

- **Schema version:** `1.1.0`.
- The schema version is recorded on every cached artifact and on
  every annotation-sidecar entry.
- A change that affects emitted bytes (different node ordering, new
  default, encoding tweak) bumps the *minor* component. An additive
  change that introduces a new layer is also a minor bump *iff*
  v(prev) specs produce byte-identical artifacts under v(new). A
  breaking change to the spec language or layer set bumps the *major*.

### Changelog

- **1.1.0** — Added §14 "Partial bindings and the question
  compiler": `Free` binding fields, `BranchPin`,
  `CycleInvariant.dual_role`, the `volatile` layer (between
  `constraint` and `bad`), term shadow on the source interpreter,
  memory-at-free-address handling. Specs that use none of this
  vocabulary compile to byte-identical artifacts under 1.1.0; a
  regression test pins this.
- **1.0.0** — Initial release: §§2–13.

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
translator and lifter. The interpreter version is `1.1.0` and is
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

## 14. Partial bindings and the question compiler

This section is the v1.1.0 contract. Both the translator increment
(`volatile` layer, `BranchPin`, `dual_role`) and the interpreter
increment (`record_shadow` mode) are implemented; `schema_version`
and `interpreter_version` are both `1.1.0`. A v1.0.0 spec — one
using no `Free` binding fields, no `BranchPin`, and no
`dual_role=True` — compiles to byte-identical output under 1.0.0
and 1.1.0; a regression test
(`tests/pairs/riscv_btor2/golden/test_v10_backcompat.py`) pins this.

### 14.1 The set-of-runs framing

A `QuestionSpec` describes a set of program runs. Init clauses,
cycle invariants, branch pins, and input bindings all narrow the
set; `bad` asks something about it. Whole-program BMC, symbolic
execution, concolic exploration, and concrete simulation are not
separate features — they are the same question compiler applied to
specs that pin different fractions of the runs:

| Pins in spec               | Set described                   | Cheapest discharger |
|---|---|---|
| init + cycle invariants    | wide (every consistent run)     | z3-bmc / spacer / bitwuzla / pono |
| + branch pins              | one path, inputs free           | z3-bmc on a path-shaped formula   |
| + branch pins + some input pins | one path, fewer inputs free | z3-bmc on a tighter formula       |
| + all input pins           | singleton                       | source interpreter (O(n))         |

Nothing here changes the contract for fully-symbolic or fully-pinned
specs. The new vocabulary in §§14.2–14.7 is the middle ground.

### 14.2 Free fields on `RiscvInputBinding`

A `RiscvInputBinding` field may be the sentinel `Free` instead of a
concrete value. A field is **pinned** iff it is a concrete value;
otherwise it is **free**.

| Field                       | `Free` legal? | Meaning |
|---|---|---|
| `register_init[N]`          | yes           | the N-th GPR's entry value is symbolic |
| `memory_init[addr]`         | yes           | the byte at `addr` at entry is symbolic |
| `pc`                        | no            | PC must be concrete; widen via `init` clauses if needed |
| `halted`                    | no            | boolean only |
| `havoc_per_step[i][r]`      | yes           | the per-step havoc value is symbolic |

The plain interpreter (today's `simulate`) raises
`FreeFieldNotAllowed` on encountering any free field. The
term-shadow interpreter (§14.6) accepts free fields.

`canonical_bytes()` distinguishes pinned-to-`V`, free, and absent.
The three produce three distinct `inputs_hash`es by design.

### 14.3 `BranchPin`

A new `Assumption` subtype:

```
BranchPin(step: int, taken: bool, pc: int)
```

- `step >= 0`: the cycle (0-indexed) the pin fires at.
- `taken`: which direction the branch went.
- `pc >= 0`: the PC of the branch instruction. **Required.** A
  step-indexed pin without a PC would force the encoding to
  identify "the branch at step S" globally, which the transition
  relation does not expose; `pc` lets the constraint name the
  specific dispatch arm whose branch condition is being pinned.

Lowering: into the `volatile` layer (§14.5). When any `BranchPin`
is present, the volatile layer declares an auxiliary step counter
state and emits one equality constraint per pin:

```
state step_count : bv64
init step_count = 0
next step_count = step_count + 1

# For each BranchPin(step=S, taken=D, pc=P):
constraint(
    (step_count != S) OR (pc_state != P) OR (branch_cond_at_P == D)
)
```

`branch_cond_at_P` is the BTOR2 sub-expression the library layer
already computes for the conditional at PC `P` (see §5, "Branches");
volatile references the existing nid via the dispatch arm rather
than re-emitting. `pc_state` is the `pc` state variable declared
in §3.

Soft no-op rules:

- If the program halts before step `S`, the antecedent is false at
  every cycle; the constraint holds vacuously.
- If at step `S` the executing PC is not `P` (the pin's `pc` was a
  mistake about which branch was being pinned), the antecedent is
  still false; the constraint holds vacuously.

A pin is *active* iff some trace reaches `step_count == S` with
`pc == P`. Only active pins constrain the search. This reflects
the pin's semantics — *"what we observed when we executed"* — not
*"what must be true."* Inconsistent pins don't fail the search;
they just don't constrain it.

`step_count` is `bv64`, sufficient for any realistic
`AnalysisDirective.bound`. Wrap-around is undefined and is not
reachable at v1.1.0 budgets.

### 14.4 Dual-role predicates and `paired_with_nid`

`CycleInvariant` gains a `dual_role: bool` field, default `False`.

- `dual_role=False`: existing semantics. One clause in `constraint`,
  role `assumption`.
- `dual_role=True`: two paired clauses, in one compilation pass:
  1. `constraint(P)` — assumed for downstream questions.
     Role `assumption`, layer `constraint`.
  2. `bad(¬P)` — checked for falsification on this question.
     Role `bad`, layer `volatile`.

Both annotation entries carry `paired_with_nid` pointing at the
other. The lifter consumes the link to phrase a witness as
*"assumed invariant ⟨P⟩ violated at step k by trace ⟨T⟩"* rather
than the generic "bad clause N fired."

A dual-role `CycleInvariant` is the full mechanism behind what the
deprecated `CandidateInvariant` directive was meant to provide.
A "ranking-function candidate" is a dual-role `CycleInvariant`
whose expression is the ranking-decrease predicate on back-edges.
There is no third vocabulary.

### 14.5 The `volatile` layer

A new layer named `volatile`, inserted between `constraint` and
`bad` in `LAYER_NAMES`:

```
("header", "machine", "library", "dispatch",
 "init", "constraint", "volatile", "bad",
 "binding", "havoc")
```

Contents:

- `BranchPin` lowerings: when at least one pin is present, the
  layer declares a `step_count : bv64` state with `init = 0` and
  `next = step_count + 1`, plus one `constraint` clause per pin
  (formula in §14.3).
- `dual_role=True` companion `bad` clauses.
- Synthesized memory-at-free-address pins from the term shadow
  (§14.7).

Stability profile addendum to §12:

| Layer       | Recompute when |
|---|---|
| `volatile`  | The `BranchPin` set, any `CycleInvariant.dual_role` flag, or the synthesized memory-pin set changes. |

The `constraint` layer's stability is *not* affected by anything in
`volatile`. This is the cache-isolation purpose of the new layer:
per-question churn lives here so the cheaper lower layers stay
content-stable across LLM iterations.

A spec that uses none of §§14.2–14.4 produces a `volatile` layer
whose body is its marker comment and nothing else; the rest of the
artifact is byte-identical to its v1.0.0 form.

### 14.6 Term shadow in the source interpreter

The source interpreter accepts an optional `record_shadow: bool`,
default `False`.

- `record_shadow=False`: byte-identical behavior to v1.0.0 on
  fully-pinned bindings. Free fields raise `FreeFieldNotAllowed`.
- `record_shadow=True`: the interpreter accepts free fields,
  concretizes each free cell to `0` for execution, and records
  per-instruction events on the trace.

Recorded events (v1.1.0):

- At every conditional branch:
  `BranchEvent(step, pc, mnemonic, taken)` — taken is recovered
  from the simulator's pre- and post-step PC plus the instruction's
  immediate; no parallel BTOR2 emission.
- At every load or store:
  `MemoryAccessEvent(step, pc, mnemonic, addr, kind, free_dependent)` —
  `addr` is the resolved concrete address; `kind ∈ {"load", "store"}`;
  `free_dependent` is currently always `False` (v1.1.0 does not
  taint-propagate; consumers conservatively treat every memory
  event as potentially free-dependent).
- The set of free fields:
  `free_fields = {register_init: [...], memory_init: [...]}`.

Events are exposed on the returned trace as
`SourceTrace.final_state["shadow"]` (a dict). They are not part of
`deltas`; predicates and `cross_check` do not consume them. They
are consumed by the pair-local helper `trace_to_branch_pins` to
synthesize follow-up specs from a recorded trace.

No parallel BTOR2-term emission. The volatile-layer lowering for a
`BranchPin` recovers the branch condition's BTOR2 term from the
existing `library.LoweringResult.branch_cond` (Phase 2 work),
indexed by the pin's `pc`. The shadow's role is to identify
*which* `(step, pc, taken)` triples and *which* memory addresses to
pin, not to emit BTOR2 in parallel. If a future use case demands
the symbolic expression of a free-dependent computation directly
(rather than reconstructing it through the library), that is a
v1.2.0+ extension.

The interpreter version is `1.1.0` (bumped with the shadow). A
trace produced with `record_shadow=False` under interpreter `1.1.0`
is byte-identical to the same trace under `1.0.0`.

### 14.7 Memory at a free address

When a load or store has an effective address that depends on a
free input field:

1. The concrete simulator resolves the address and performs the
   read/write as usual; the trace's `deltas` are unaffected.
2. The shadow records the access (per §14.6) **and** synthesizes a
   `BranchPin`-shaped constraint:
   `constraint(addr_term == resolved_value)`.
3. The synthesized pin is emitted into `volatile` of any spec built
   from this trace by `trace_to_branch_pins`.

Effect: a follow-up question built from the trace is constrained to
runs that resolve to the same address at the same step. Exploring a
different resolution requires the LLM to drop the pin — a deliberate
spec-level act, not an implicit framework choice.

This is the conservative option. Refusing free addresses outright
would forbid useful patterns; emitting an `ite` over a finite
resolved set shifts the work from the LLM to the framework and
inflates the artifact. Neither is supported at v1.1.0.

### 14.8 Soundness contract

Two properties; both testable.

1. **Free-fields-default-to-zero reproduces the plain simulator.**
   Let `B` be a binding with some cells set to `FREE`. Let
   `concretize(B)` replace every `FREE` cell with `0`. Then
   `simulate(source, concretize(B))` (plain interpreter) produces a
   `SourceTrace` byte-identical to
   `simulate(source, B, record_shadow=True)` with
   `final_state["shadow"]` stripped. (For v1.1.0 the shadow's
   default concretization is always `0`; a future version may let
   callers supply a different concretization map.)
2. **Branch events are BMC-feasible.** For every
   `BranchEvent(step, pc, taken)` recorded by the shadow, the
   BMC encoding of the same source under the corresponding
   `BranchPin(step, pc, taken)` is satisfiable up to step `step`.
   This holds by construction: the dispatch layer's branch
   condition at `pc` is the same BTOR2 term whether evaluated by
   the BMC solver under the spec's bindings or by the volatile
   layer's `BranchPin` constraint. (Memory events satisfy the
   analogous property: the synthesized memory-address pin is
   feasible at the recorded `addr`.)

Property 1 is enforced by the Phase 4 cross-check test
(`test_shadow_crosscheck.py`); property 2 follows from §14.3 + §5
and is spot-checked per branch instruction class.

A trace produced under v1.1.0 with `record_shadow=True` thus
describes a concrete RV64 run (under the all-zero concretization)
together with a `(step, pc, taken)`/`(step, pc, addr)` event log
that the pair-local helper `trace_to_branch_pins` converts into
`BranchPin` / memory-pin spec patches. A solver consuming those
pins as constraints is, by construction, searching exactly the
suffix of paths that share the recorded prefix.

## 15. What this schema deliberately does not do

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
