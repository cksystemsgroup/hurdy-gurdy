# `ebpf-btor2` schema — version 1.0.0

This document is the contract between hurdy-gurdy and any consumer
(LLM or human) of the `ebpf-btor2` pair's output. Every translation
choice this pair makes is recorded here. If the code disagrees with
this document, the code is wrong; if the schema is wrong, fix it and
bump the version.

The invariant: same `(QuestionSpec, eBPF bytecode)` produces a byte-
identical BTOR2 reasoning artifact under this schema version.

---

## 1. Versioning

- **Schema version:** `1.0.0`.
- The schema version is recorded on every cached artifact and on
  every annotation-sidecar entry.
- A change that affects emitted bytes (different node ordering, new
  default, encoding tweak) bumps the *minor* component. An additive
  change that introduces a new layer is also a minor bump *iff*
  v(prev) specs produce byte-identical artifacts under v(new). A
  breaking change to the spec language or layer set bumps the *major*.

### Changelog

- **1.0.0** — Initial release: this document, §§2–14.

### Phase-gated future bumps (planned, not yet in effect)

- **1.1.0** — P8: load/store + stack model. Adds `bv8`, `bv16`,
  `bv32` sorts; `stack` state (array `bv12 → bv8`); load/store
  lowerings; `r10` becomes real state.
- **1.2.0** — P9: helper-call model. Adds helper-call counter state;
  `bpf_map_lookup_elem` and friends as spec-parameterized abstract
  functions.
- **1.3.0** — P10: packet/context memory model. Adds `packet` state
  (array `bv32 → bv8`) and `packet_len` state.
- **1.4.0** — P11: map memory model. Per-map array states.

---

## 2. Sorts

The pair declares one universal `header` layer that emits all sorts.
Every cross-layer reference uses the symbolic export name.

| Symbolic name | Sort   | Width / args                         | Phase introduced |
|---------------|--------|--------------------------------------|-----------------|
| `bv1`         | bitvec | 1                                    | P1              |
| `bv32`        | bitvec | 32 (instruction index, narrow imm)   | P1              |
| `bv64`        | bitvec | 64 (registers; the dominant sort)    | P1              |

Sorts for narrowed loads (`bv8`, `bv16`) and memory arrays are
deferred to P8+. This schema version emits only the three sorts above.

---

## 3. State variables

Emitted once in the `machine` layer. Naming is fixed so linker
exports are predictable.

### Registers

- Ten mutable registers `r0`–`r9`, sort `bv64`.
- Symbolic export name pattern: `reg_r{N}` for `N` in `0..9`.
- `r10` is *not* declared as state. It is the read-only frame
  pointer. In P1 (no stack operations) every read of `r10` resolves
  to the constant `R10_BASE = 0x0000_0000_0000_0200` (decimal 512,
  the kernel eBPF stack size). P8 will promote `r10` to real state.
- Register `r0` is the function return-value register; it is
  otherwise treated identically to `r1`–`r9`.

### Instruction index

- Single `insn_idx` state, sort `bv32`.
- Symbolic export name: `insn_idx`.
- Represents the 0-based index of the *current* instruction (the
  instruction about to execute this cycle). Analogous to a program
  counter.
- Maximum value: `2^32 - 1`, far exceeding the kernel verifier's
  1 000 000-instruction limit. `bv32` is chosen for
  implementation convenience; P1 programs are small.

### Exit flag

- Single `halted` state, sort `bv1`.
- Symbolic export name: `halted`.
- Set to `1` on the cycle that executes `BPF_EXIT_INSN`. Once set,
  all state is frozen for every subsequent cycle.

### Inputs

- No auxiliary input states in P1. There are no helper calls, no
  packet reads, and no map lookups to model as non-deterministic
  inputs. Free register values at entry come from the `init` layer's
  lack of constraints, not from input states.

---

## 4. Program loading

- Source: a compiled `.bpf.o` ELF object. The `EbpfProgramRef`
  specifies the ELF section name (`prog_section`); the default is
  the first `SEC("…")` prog section found in the object.
- The prog section contains a flat sequence of 8-byte `bpf_insn`
  records in little-endian format. Instruction at index `i` occupies
  bytes `[8*i, 8*i + 8)`.
- Wide instructions (16-byte `BPF_LD | BPF_IMM | BPF_DW`, opcode
  `0x18`) are NOT in P1; the loader must reject any program
  containing them with diagnostic `ebpf-btor2/load/0001`.
- `content_hash` on `EbpfProgramRef` is the SHA-256 hex digest of
  the raw prog-section bytes. When present, the loader verifies it
  and raises `ebpf-btor2/load/0002` on mismatch.
- MAP descriptors, BTF, and CO-RE relocations are ignored at P1.
  Pre-relocate bytecode before passing it to the translator.

### Instruction encoding

```
Byte 0:  opcode = cls[2:0] | src_flag[3] | op_code[7:4]
Byte 1:  dst_reg[3:0] | src_reg[7:4]
Bytes 2–3:  signed 16-bit offset  (little-endian)
Bytes 4–7:  signed 32-bit immediate (little-endian)
```

Notation used throughout §5:
- `dst`: `dst_reg` field (0–9 for valid P1 programs).
- `src`: `src_reg` field.
- `off`: `off` field, sign-extended to 32 bits when added to
  `insn_idx`.
- `imm32`: `imm` field, a signed 32-bit integer.
- `imm64`: `sign_extend(imm32, 64)`, the sign-extended 64-bit form.
- `DST`: current value of `reg_r{dst}` (a `bv64` term).
- `SRC_K`: `bv64` constant equal to `imm64`.
- `SRC_X`: current value of `reg_r{src}` (a `bv64` term).
- `SRC`: `SRC_K` for BPF_K instructions; `SRC_X` for BPF_X.

---

## 5. Instruction lowering (P1 subset)

This section enumerates every supported instruction's BTOR2
fragment. Unsupported opcodes encountered during loading cause
diagnostic `ebpf-btor2/load/0003` and abort translation.

The state update for each instruction:
1. The listed `next` clause for `reg_r{dst}` (if the instruction
   writes a register).
2. `next insn_idx = …` as specified below.
3. `next halted = halted` — unchanged unless the instruction is
   `BPF_EXIT_INSN`.
4. All other `reg_r{N}` states satisfy `next reg_r{N} = reg_r{N}`
   (unchanged).

The halted-guard rule overrides everything: when `halted == 1` at
the start of a cycle, the dispatch layer freezes all state
regardless of `insn_idx`.

### ALU64 — BPF_ALU64 (class `0x07`)

Source flag: `BPF_K = 0` (immediate) or `BPF_X = 1` (register).

| Mnemonic   | op nibble | opcode (K) | opcode (X) | BTOR2 result `r` |
|------------|-----------|------------|------------|-------------------|
| `ADD64`    | `0x0`     | `0x07`     | `0x0f`     | `add(DST, SRC)` |
| `SUB64`    | `0x1`     | `0x17`     | `0x1f`     | `sub(DST, SRC)` |
| `MUL64`    | `0x2`     | `0x27`     | `0x2f`     | `mul(DST, SRC)` |
| `DIV64`    | `0x3`     | `0x37`     | `0x3f`     | `ite(SRC == 0, 0, udiv(DST, SRC))` |
| `OR64`     | `0x4`     | `0x47`     | `0x4f`     | `or(DST, SRC)` |
| `AND64`    | `0x5`     | `0x57`     | `0x5f`     | `and(DST, SRC)` |
| `LSH64`    | `0x6`     | `0x67`     | `0x6f`     | `sll(DST, and(SRC, 63))` |
| `RSH64`    | `0x7`     | `0x77`     | `0x7f`     | `srl(DST, and(SRC, 63))` |
| `NEG64`    | `0x8`     | `0x87`     | —          | `neg(DST)` (SRC ignored; only BPF_K variant) |
| `MOD64`    | `0x9`     | `0x97`     | `0x9f`     | `ite(SRC == 0, DST, urem(DST, SRC))` |
| `XOR64`    | `0xa`     | `0xa7`     | `0xaf`     | `xor(DST, SRC)` |
| `ARSH64`   | `0xc`     | `0xc7`     | `0xcf`     | `sra(DST, and(SRC, 63))` |

*Opcode encoding:* `opcode = op_nibble << 4 | src_flag << 3 | 0x07`.

State update:
- `next reg_r{dst} = r`
- `next insn_idx = insn_idx + 1`

Shift-amount masking: the BTOR2 shift operators require the shift
amount to fit in the operand width; the `and(SRC, 63)` ensures this
for `bv64`. This matches the Linux kernel verifier's definition.

Division/modulo by zero: the kernel eBPF verifier allows programs
where the divisor is provably non-zero; if a zero divisor is
possible at runtime, the kernel returns `0` (DIV) or the original
`DST` (MOD). The schema encodes both cases via `ite` to remain sound.

### Branches — BPF_JMP (class `0x05`)

For conditional branches the target instruction index is:
```
next insn_idx = ite(cond, insn_idx + 1 + sign_extend(off, 32),
                          insn_idx + 1)
```
All arithmetic on `insn_idx` is `bv32`. `off` is sign-extended from
16 to 32 bits before the addition.

For `JA` (unconditional):
```
next insn_idx = insn_idx + 1 + sign_extend(off, 32)
```

No register is written by any branch instruction.

For K-type sources, `SRC_K = sign_extend(imm32, 64)` (bv64 compare).

| Mnemonic | op nibble | opcode (K) | opcode (X) | Condition `cond` (bv64) |
|----------|-----------|------------|------------|--------------------------|
| `JA`     | `0x0`     | `0x05`     | —          | — (unconditional) |
| `JEQ`    | `0x1`     | `0x15`     | `0x1d`     | `eq(DST, SRC)` |
| `JGT`    | `0x2`     | `0x25`     | `0x2d`     | `ugt(DST, SRC)` |
| `JGE`    | `0x3`     | `0x35`     | `0x3d`     | `ugte(DST, SRC)` |
| `JSET`   | `0x4`     | `0x45`     | `0x4d`     | `neq(and(DST, SRC), 0)` |
| `JNE`    | `0x5`     | `0x55`     | `0x5d`     | `neq(DST, SRC)` |
| `JSGT`   | `0x6`     | `0x65`     | `0x6d`     | `sgt(DST, SRC)` |
| `JSGE`   | `0x7`     | `0x75`     | `0x7d`     | `sgte(DST, SRC)` |
| `JLT`    | `0xa`     | `0xa5`     | `0xad`     | `ult(DST, SRC)` |
| `JLE`    | `0xb`     | `0xb5`     | `0xbd`     | `ulte(DST, SRC)` |
| `JSLT`   | `0xc`     | `0xc5`     | `0xcd`     | `slt(DST, SRC)` |
| `JSLE`   | `0xd`     | `0xd5`     | `0xdd`     | `slte(DST, SRC)` |

*Opcode encoding:* `opcode = op_nibble << 4 | src_flag << 3 | 0x05`.

`CALL` (opcode `0x85`) is **not** in P1; encountering it aborts
with diagnostic `ebpf-btor2/load/0003`.

### Exit — BPF_EXIT_INSN

Opcode: `0x95`.

State update:
- `next halted = 1`
- `next insn_idx = insn_idx` (freeze)
- `next reg_r{N} = reg_r{N}` for all N in 0..9 (freeze)

The return value is `reg_r0` at the cycle `halted` transitions from
0 to 1.

---

## 6. Dispatch

The `dispatch` layer ties `insn_idx` values to per-instruction
lowerings from the `library` layer.

- One large nested `ite` expression keyed on `insn_idx`, ordered by
  ascending instruction index. Each arm matches one valid `insn_idx`
  and routes to the corresponding library lowering.
- Highest-priority arm: `if halted == 1 then freeze all state`.
  This arm is emitted first (innermost `ite`), before any opcode
  arm.
- For `insn_idx` values outside the analyzed instruction range (e.g.
  out-of-bounds jumps), the dispatch self-loops: all state frozen.
  The `bad` expression can detect this condition if the spec
  requires.
- Arm ordering is strictly ascending by instruction index
  (deterministic and reproducible). Re-ordering is not permitted.

---

## 7. Entry state

The `init` layer constrains the initial state:

- `insn_idx` at entry: `0` (always; the program starts at its first
  instruction).
- `halted` at entry: `0`.
- `reg_r0`–`reg_r9`: **free** at entry unless the spec supplies
  `RegisterBound` assumptions for those registers. Free registers
  have no `init` clause; their entry value is unconstrained in the
  BMC search.

`r10` is not state; it has no `init` clause. Its canonical value
for P1 is the constant `bv64(512)` wherever referenced.

---

## 8. Constraint encoding

`RegisterBound` assumptions are emitted into the `constraint` layer.
Each `RegisterBound(reg=N, value_lo=lo, value_hi=hi)` becomes two
BTOR2 `constraint` nodes:

```
constraint  ugte(reg_r{N}, bv64(lo))
constraint  ulte(reg_r{N}, bv64(hi))
```

Comparisons are *unsigned*. `value_lo` and `value_hi` are Python
`int` values in range `[0, 2^64 - 1]`; the schema does not support
negative bounds at P1. A `value_lo > value_hi` bound is rejected by
the spec validator with diagnostic `ebpf-btor2/spec/0021`.

Constraints hold at every cycle the solver explores (they are not
entry-only). For a `RegisterBound` that is intended only at entry,
combine with an explicit `insn_idx == 0` guard. P1 does not expose
this guard in the spec language; per-entry bounds are the only use
case so the distinction is deferred.

---

## 9. Property expression language and bad encoding

The `Property.expression` string is parsed by the translator and
lowered into the `bad` layer. The default `"false"` produces a
constant-false `bad` node (the property is unsatisfiable by
construction; useful as a scaffold before a real property is added).

### Grammar (P1)

```
expr   ::= "false"
         | "exit_reached"
         | reg_expr
         | expr "AND" expr
         | "(" expr ")"

reg_expr ::= "r" N op value

N      ::= "0" | "1" | … | "9"
op     ::= "==" | "!=" | "<" | "<=" | ">" | ">="
         | "s<" | "s<=" | "s>" | "s>="
value  ::= decimal | "0x" hexdigits     (64-bit unsigned constant)
```

Unqualified comparison operators (`<`, `<=`, `>`, `>=`) are
**unsigned** (`ult`, `ulte`, `ugt`, `ugte`). Operators prefixed with
`s` are **signed** (`slt`, `slte`, `sgt`, `sgte`). `==` and `!=`
are sign-agnostic bit-equality.

A `value` outside `[0, 2^64 - 1]` is a parse error.
`N` outside `[0, 9]` is a parse error (r10 is not state).

### Lowering to BTOR2 bad

| Expression | `bad` clause |
|---|---|
| `"false"` | constant `false` (1-bit zero) |
| `"exit_reached"` | `halted` |
| `"r{N} op value"` | `and(halted, op(reg_r{N}, bv64(value)))` |
| `"e1 AND e2"` | `and(lower(e1), lower(e2))` |

The outermost `bad` node is the `or` of all sub-expressions if the
top-level expression is a conjunction. In the common single-clause
case it is emitted directly.

Polarity: `bad = true` means the property is **violated** (the bad
state is reachable). `bad = false` means no violation was witnessed
at this bound.

---

## 10. Verdict semantics

| Verdict | Meaning |
|---|---|
| `reachable` | A finite trace satisfies all constraints and reaches `bad = 1`. The solver returns a witness in the raw payload. |
| `unreachable` | No trace within `scope.max_insns` cycles reaches `bad = 1`. Bounded; says nothing past the bound. |
| `proved` | Not applicable at P1 (BMC only). Reserved for P13 when k-induction / Spacer is added. |
| `unknown` | The solver gave up (timeout, memory, incomplete theory). |

`scope.max_insns` is the unrolling depth for BMC engines. The
artifact does not bake this in; the solver is invoked with the bound
via its own API.

---

## 11. Layer names

```python
LAYER_NAMES = (
    "header",      # sorts
    "machine",     # state declarations
    "library",     # per-opcode BTOR2 lowering fragments
    "dispatch",    # insn_idx-keyed ITE routing
    "init",        # entry-state constraints
    "constraint",  # cycle constraints from spec assumptions
    "bad",         # property violation expression
    "binding",     # concrete value overrides (for interpreter inputs)
)
```

The `volatile` layer (BranchPin support, dual-role invariants) is
not present at v1.0.0 and will be introduced in a future bump if
needed.

---

## 12. Annotation conventions

For every emitted BTOR2 node the annotation records:

- **role**: one of `sort`, `state`, `input`, `init`, `transition`,
  `constraint`, `bad`, `observable`, `assumption`, `dispatch`,
  `binding`, `expression`, `other`.
- **source mapping** (`EbpfSourceMapping`): `insn_idx` (the
  instruction index the node was emitted for), `opcode` (hex),
  `mnemonic` (decoded name e.g. `"ADD64_K"`), `prog_section` (ELF
  section of origin).
- **provenance**: schema version, spec hash.

The annotation layer is the contract between `compile` and
`introspect`. A change that removes or renames a role is a breaking
schema change requiring a major version bump.

---

## 13. Stability profile (cache behaviour)

| Layer        | Recompute when |
|---|---|
| `header`     | Schema version changes (never for a fixed version). |
| `machine`    | Never at P1; at P8+ when stack/packet/map are added. |
| `library`    | P1 opcode set is fixed; bumps with P8+ schema versions. |
| `dispatch`   | The set of analyzed instruction indices changes. |
| `init`       | Spec's `RegisterBound` assumptions or scope changes. |
| `constraint` | Spec's `RegisterBound` or `PacketBound` assumptions change. |
| `bad`        | Spec's `Property` expression or `ExitReached` observable changes. |
| `binding`    | Always re-emitted (cheap). |

Cache keys aggregate `(spec_hash, source_hash, schema_version)` plus
the engine name when artifact bytes vary by engine (they do not at
P1). The framework's content-addressed cache covers this
automatically.

---

## 14. Interpreter semantics (deferred to P2 and P3)

The pair will ship two concrete interpreters:

- **Source interpreter** (P2): eBPF bytecode executor. Step function
  mirrors §5 exactly; trace records per-step register deltas.
- **Reasoning interpreter** (P3): multi-step BTOR2 evaluator. Ported
  from `riscv-btor2`; the pair-specific projection function aligns
  source and reasoning traces.

Both interpreters record `schema_version` and
`interpreter_version` on every trace. The interpreter version starts
at `1.0.0` (aligned with schema) and bumps independently when only
interpreter code changes.

The alignment oracle (`oracle_align.py`) verifies:
```
source_trace.reg_r{N}[step] == reasoning_trace.machine["reg_r{N}"][step]
```
for N in 0..9, at every step up to the first EXIT.

This section will be replaced with full normative text in P2/P3.

---

## 15. What this schema deliberately does not do

These exclusions are stable for v1.0.0. Adding any of them requires
a schema version bump; partial or implicit support is not allowed.

- **32-bit ALU** (`BPF_ALU`, class `0x04`). Deferred.
- **32-bit branches** (`BPF_JMP32`, class `0x06`). Deferred.
- **Load / store** (`BPF_LD`, `BPF_LDX`, `BPF_ST`, `BPF_STX`).
  Deferred to P8.
- **Stack model.** `r10` is a constant at v1.0.0. P8 introduces
  the stack array (`bv12 → bv8`, 512 bytes) and real `r10` state.
- **Wide immediate** (`BPF_LD | BPF_IMM | BPF_DW`, opcode `0x18`).
  Deferred to P8 (loads a 64-bit immediate into a register).
- **Helper calls** (`BPF_CALL`, opcode `0x85`). Deferred to P9.
- **Packet / context memory.** Deferred to P10.
- **Map memory.** Deferred to P11.
- **Tail calls / subprograms.** Single flat function only. No
  `bpf_tail_call` or inter-subprog calls.
- **BTF type information.** Not used; pre-relocate bytecode before
  passing to the translator.
- **Multiple entry points.** A single prog section with a single
  entry at instruction index 0.
- **Live kernel attachment.** The kernel-verifier baseline loads
  programs with `BPF_PROG_LOAD` for verifier feedback only; it never
  attaches them to live hooks.
- **Negative `RegisterBound` values.** Bounds are unsigned 64-bit
  integers at P1.
