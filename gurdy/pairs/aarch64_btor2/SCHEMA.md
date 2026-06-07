# `aarch64-btor2` schema

This document is the contract between hurdy-gurdy and any consumer
(LLM or human) of the `aarch64-btor2` pair's output. Every
translation choice this pair makes is recorded here. If the code
disagrees with this document, the code is wrong; if the schema is
wrong, fix it and bump the version.

The invariant: same `(QuestionSpec, AArch64 ELF)` produces a byte-
identical BTOR2 reasoning artifact under this schema version.

**Divergences from `riscv-btor2`**: this schema documents AArch64-
vs-RV64 semantic differences inline as `⚡ AArch64 divergence:` notes
so readers can audit each ISA-portability assumption directly.

## 1. Versioning

- **Schema version:** `1.0.0`.
- The schema version is recorded on every cached artifact and on
  every annotation-sidecar entry.
- A change that affects emitted bytes bumps the *minor* component.
  A breaking change to the spec language or layer set bumps the
  *major*.

### Changelog

- **1.0.0** — Initial release: §§2–15.

## 2. Sorts

The pair declares one universal `header` layer that emits all sorts.
Every cross-layer reference uses the symbolic export name, not a
numeric id.

| Symbolic name | Sort | Width / args | Notes |
|---|---|---|---|
| `bv1` | bitvec | 1 | flag bits |
| `bv4` | bitvec | 4 | NZCV packed |
| `bv5` | bitvec | 5 | W-register shift amount (mod 32) |
| `bv6` | bitvec | 6 | X-register shift amount (mod 64) |
| `bv8` | bitvec | 8 | byte |
| `bv16` | bitvec | 16 | halfword |
| `bv32` | bitvec | 32 | word (W-register width) |
| `bv33` | bitvec | 33 | 32-bit arithmetic with carry |
| `bv64` | bitvec | 64 | doubleword; the dominant sort |
| `bv65` | bitvec | 65 | 64-bit arithmetic with carry |
| `mem` | array | index `bv64`, element `bv8` | byte-addressable |

The 33-bit and 65-bit sorts exist only to compute carry/borrow in
flag-setting instructions (§5.2); they appear in no state variable
and are not part of any public cross-layer export name.

## 3. State variables

Emitted once in the `machine` layer.

### Registers

- 31 general-purpose registers `x0` through `x30`, sort `bv64`.
  Export name pattern: `reg_x{N}` for `N` in `0..30`.
- **Register 31 (XZR / WSR / SP) is context-sensitive** and is *not*
  declared as a single state:
  - In data-processing instructions (arithmetic, logical, shifts,
    moves, multiply, divide, bitfield, conditional select), register
    31 denotes the **zero register** (XZR/WSR). Reads return the
    constant 0; writes are discarded. No `reg_x31` state is declared.
  - In load/store base-address fields and stack-pointer–explicit
    instructions (MOV SP, ...; ADD SP, SP, ...; etc.), register 31
    denotes **SP** (the stack pointer state below).
  - The library layer resolves the context at decode time; no
    ambiguity is left for the BTOR2 consumer.
- ABI aliases (`fp`, `lr`, `sp`) are *not* used as state names.
  The annotation records the ABI alias as a hint.

⚡ **AArch64 divergence (register file shape):** RV64 has 32 GPRs
  (x0–x31) with x0 always zero. AArch64 has 31 GPRs (x0–x30) plus
  a context-sensitive register 31 that may be XZR or SP depending on
  the instruction encoding field. The SP is a separate named state;
  x0 is a real, writable register.

### Stack pointer

- Single `sp` state, sort `bv64`. Export name: `sp`.
- SP is distinct from the GPR file. Its initial value is free unless
  the spec pins it via `SPInit`.
- SP is updated by explicit SP-targeting instructions (MOVZ SP, ...;
  ADD SP, SP, imm; SUB SP, SP, imm; LDR/STR pre/post-indexed, etc.).

### Program counter

- Single `pc` state, sort `bv64`. Export name: `pc`.
- All AArch64 instructions are 4 bytes (A64 fixed-width encoding);
  sequential PC advance is always `pc + 4`.

### Condition flags

- Single `nzcv` state, sort `bv4`. Export name: `nzcv`.
- Bit layout: bit 3 = N (negative), bit 2 = Z (zero), bit 1 = C
  (carry), bit 0 = V (overflow). This matches the PSTATE flag field
  ordering in the ARMv8-A architecture reference.
- Only **flag-setting** instruction variants update `nzcv`. All
  non-flag-setting variants leave `nzcv` unchanged:
  `next nzcv = nzcv`.
- At entry, `nzcv` is free unless the spec provides `NZCVInit`.

⚡ **AArch64 divergence (flags):** RV64 has no flag register; branches
  compare two register operands directly. AArch64 separates compare
  (flag-setting instruction) from conditional branch (reads NZCV).
  The `nzcv` state is unique to this pair.

### Memory

- Single `mem` state, sort `mem` (byte array indexed by `bv64`).
  Export name: `mem`.
- Byte ordering: **little-endian** (standard AArch64 user-mode Linux
  convention; BE8 is outside scope).
- Halfword, word, and doubleword loads/stores compose 2, 4, or 8
  `read`/`write` operations against the byte array.

### Halted flag

- Single `halted` state, sort `bv1`. Export name: `halted`.
- Set to 1 by `SVC`, `BRK`, or a PC that exits the analyzed set.
  Once set, PC and registers are frozen (every `next` clause
  becomes an identity on the current value).

### Inputs

- One free-input state `nondet` of sort `bv64` per question. Each
  cycle introduces a fresh symbolic value, used to model unknown
  side effects (havoc'd register values, SVC results, etc.).

## 4. ELF loading

- All `PT_LOAD` segments contribute their `filesz` bytes to the
  initial memory contents. Bytes in `[filesz, memsz)` (BSS) are
  initialized to zero.
- Bytes outside any `PT_LOAD` segment are uninitialized: the initial-
  state clauses leave them free.
- `e_entry` is recorded in the annotation but does not constrain the
  initial PC. The initial PC comes from the spec's analysis scope.

## 5. Instruction lowering

This section enumerates every supported instruction's BTOR2 fragment.
AArch64 uses a fixed 32-bit encoding (A64); there are no compressed
or variable-length forms.

All 64-bit register reads return the current value of `reg_x{N}` (or
`sp` when the field addresses register 31 in an SP context, or the
constant 0 when the field addresses register 31 in an XZR context).
32-bit operands are the low 32 bits of the corresponding X-register,
extracted via `slice`.

Every instruction entry follows the pattern:

- The BTOR2 expression computing the result.
- The register-file write (`next reg_x{Rd} = result`; discarded if
  Rd = 31 in XZR context).
- The SP write (`next sp = result`; only when Rd = 31 in SP context).
- The NZCV write (only for flag-setting variants).
- The PC update (`next pc = pc + 4` for sequential; per-instruction
  otherwise).

### 5.1 Immediate data processing

Immediate operands are decoded values; the encoder's shift / bitmask
encoding is transparent to the schema.

**ADD / ADDS (immediate, 64-bit)**

- `r = xN + imm` where `imm = imm12 << {0 | 12}` (decoded).
- `next reg_x{Rd} = r` (or `next sp = r` if Rd = 31 in SP context).
- **ADDS only**: updates NZCV (§5.2).
- `next pc = pc + 4`.

**SUB / SUBS (immediate, 64-bit)**

- `r = xN - imm` (decoded as above).
- `next reg_x{Rd} = r` (or `next sp = r`).
- **SUBS only**: updates NZCV (§5.2). CMP is an alias for SUBS with
  Rd = XZR (write discarded).
- `next pc = pc + 4`.

**AND / ANDS / ORR / EOR (immediate, 64-bit)**

- Bitmask immediate decoded to a 64-bit pattern `mask`.
- `r = xN & mask` / `xN | mask` / `xN ^ mask`.
- `next reg_x{Rd} = r`.
- **ANDS only**: updates NZCV with N = r[63], Z = (r == 0), C = 0,
  V = 0. TST is an alias for ANDS with Rd = XZR.
- `next pc = pc + 4`.

**Move wide (MOVZ, MOVK, MOVN)**

- `MOVZ`: `r = imm16 << shift` where shift ∈ {0, 16, 32, 48}.
  All other bits zero.
- `MOVK`: `r = (xN & ~(0xFFFF << shift)) | (imm16 << shift)`.
  Keeps all bits of `xN` except the 16-bit field at `shift`.
- `MOVN`: `r = ~(imm16 << shift)`.
- `next reg_x{Rd} = r`.
- `next pc = pc + 4`.

**PC-relative address formation (ADR, ADRP)**

- `ADR`: `r = pc + sign_extend(imm21, 64)`.
- `ADRP`: `r = (pc & ~0xFFF) + sign_extend(imm21 << 12, 64)`.
  The low 12 bits of pc are zeroed before adding the page offset.
- `next reg_x{Rd} = r`.
- `next pc = pc + 4`.

### 5.2 Flag update semantics (ADDS / SUBS / ANDS)

Flag-setting instructions compute NZCV from the 64-bit result `r`
and (for ADDS/SUBS) a 65-bit intermediate:

**ADDS / CMN (add-like):** let `lhs = xN`, `rhs = operand`.

```
sum65 = zero_extend(lhs, 65) + zero_extend(rhs, 65)
r     = sum65[63:0]       ; 64-bit result
N     = r[63]
Z     = (r == 0)          ; bv1, 1 if all-zero
C     = sum65[64]         ; unsigned carry out
V     = (lhs[63] == rhs[63]) AND (r[63] != lhs[63])
next nzcv = concat(N, Z, C, V)   ; bv4
```

**SUBS / CMP (subtract-like):** let `lhs = xN`, `rhs = operand`.

AArch64 subtraction is computed as `lhs + NOT(rhs) + 1`; carry has
the inverted borrow semantics (C = 1 means no borrow = unsigned
lhs >= rhs).

```
rhs_inv = NOT(rhs)
sum65   = zero_extend(lhs, 65) + zero_extend(rhs_inv, 65) + 1
r       = sum65[63:0]
N       = r[63]
Z       = (r == 0)
C       = sum65[64]       ; 1 iff lhs >= rhs (unsigned)
V       = (lhs[63] != rhs[63]) AND (r[63] != lhs[63])
next nzcv = concat(N, Z, C, V)
```

⚡ **AArch64 divergence (carry polarity):** AArch64 SUB carry = 1
  means "no borrow" (unsigned ≥). This is the ARM traditional carry
  convention, opposite to x86 but consistent with ARMv8-A. BTOR2
  consumers must not assume x86 carry polarity.

**ANDS / TST (logical):** N = r[63], Z = (r == 0), C = 0, V = 0.

```
next nzcv = concat(r[63], (r == 0), bv1(0), bv1(0))
```

**32-bit flag-setting variants (ADDS Wd, ...):**
Compute using 33-bit intermediates (same formula on the 32-bit
operands), then zero-extend `r` to 64 bits before storing. NZCV
flags reflect the 32-bit result: N = r[31], Z = (r[31:0] == 0),
C = sum33[32], V from 32-bit sign bits.

### 5.3 Conditional branch conditions

All conditional branches and conditional select instructions use one
of the standard A64 condition codes, evaluated on `nzcv`:

```
N = nzcv[3]   Z = nzcv[2]   C = nzcv[1]   V = nzcv[0]
```

| Condition | Mnemonic | BTOR2 predicate |
|---|---|---|
| EQ | Equal | Z |
| NE | Not equal | ¬Z |
| CS / HS | Carry set / unsigned ≥ | C |
| CC / LO | Carry clear / unsigned < | ¬C |
| MI | Minus / negative | N |
| PL | Plus / positive or zero | ¬N |
| VS | Overflow | V |
| VC | No overflow | ¬V |
| HI | Unsigned higher | C ∧ ¬Z |
| LS | Unsigned lower or same | ¬C ∨ Z |
| GE | Signed ≥ | N ↔ V (BTOR2: `eq N V`) |
| LT | Signed < | N ⊕ V (BTOR2: `ne N V`) |
| GT | Signed > | ¬Z ∧ (N ↔ V) |
| LE | Signed ≤ | Z ∨ (N ⊕ V) |
| AL | Always | true |

All predicates are BTOR2 `bv1` expressions; `B.cond` extends them
with `ite(cond, pc + offset, pc + 4)`.

### 5.4 Register-register data processing (shifted register)

Applies to ADD, ADDS, SUB, SUBS, AND, ANDS, ORR, EOR, BIC, BICS,
ORN, EON. Shift variants: LSL, LSR, ASR (and ROR for logical ops).

- `shifted_rhs = apply_shift(xM, shift_type, shift_amount_field[5:0])`.
  For 64-bit forms: shift amount = `xM_shift[5:0]`. For 32-bit W
  forms: `[4:0]`.
- The arithmetic / logical operation applies to the shifted operand.
- BIC = AND NOT; ORN = OR NOT; EON = EOR NOT.
- NEG = SUB with lhs = XZR = 0. NEGS updates NZCV.
- Flag update for *S variants: same §5.2 rules.

### 5.5 Extended register data processing

ADD, ADDS, SUB, SUBS accept an extended-register operand encoding
that zero- or sign-extends a sub-word slice of xM then optionally
shifts left 0–4 bits:

```
ext_rhs = extend_and_shift(xM, ext_type, left_shift)
```

where `ext_type ∈ {UXTB, UXTH, UXTW, UXTX, SXTB, SXTH, SXTW, SXTX}`
and `left_shift ∈ 0..4`. The extend is the sign- or zero-extension
(as indicated by U/S prefix) of the low 8/16/32/64 bits of xM,
followed by a logical left shift. Result fed to the same arithmetic
unit as §5.4.

### 5.6 Shift and rotate instructions

**LSL, LSR, ASR, ROR (register operand, 64-bit)**

- `amount = xM[5:0]` (6-bit mask). BTOR2 uses `slice xM 5 0`.
- `r = sll / srl / sra / ror` applied to xN with `amount`.
- `next reg_x{Rd} = r`. `next pc = pc + 4`.

**LSL, LSR, ASR (immediate, 64-bit)**

- `amount ∈ 0..63` embedded in SBFM/UBFM encoding.
- Lowered as UBFM (LSL immediate), UBFM (LSR immediate), or SBFM
  (ASR immediate). See §5.7 (bitfield).

**ROR (immediate, EXTR)**

- `EXTR Xd, Xn, Xm, #imm`: `r = (concat(xN, xM))[imm+63 : imm]`.
  Slices a 64-bit window from the 128-bit pair `{xN, xM}` starting
  at bit `imm`.

⚡ **AArch64 divergence (shift semantics):** RV64 shift amount masking
  is identical (mod 64 for 64-bit, mod 32 for 32-bit). No semantic
  divergence for shift count masking.

**32-bit shift forms (W registers)**

- Shift amount = `xM[4:0]`. Result 32-bit, zero-extended to 64 bits.

⚡ **AArch64 divergence (W-register zero extension):** RV64 word
  instructions (ADDW, SUBW, SLLW, etc.) **sign-extend** the 32-bit
  result to 64 bits. AArch64 W-register instructions **zero-extend**
  the 32-bit result to 64 bits. This is a fundamental semantic
  difference affecting any translation that maps RV64 word ops to
  AArch64 W-register ops.

### 5.7 Bitfield instructions

**UBFM (Unsigned Bitfield Move)**: extracts a bitfield and
zero-extends. Aliases: UBFX, UBFIZ, LSL (imm), LSR (imm), UXTB,
UXTH, UXTW.

**SBFM (Signed Bitfield Move)**: extracts a bitfield and
sign-extends. Aliases: SBFX, SBFIZ, ASR (imm), SXTB, SXTH, SXTW.

**BFM (Bitfield Move)**: inserts a bitfield into a destination,
keeping other bits. Aliases: BFI, BFXIL.

Lowering uses BTOR2 `slice` and `concat` / `sext` / `uext`
operations. The schema does not reproduce the complex `immr`/`imms`
decoding here; the library layer decodes it and emits the
corresponding slice/extend chain.

### 5.8 Multiply and divide

**MUL Xd, Xn, Xm** (alias MADD Xd, Xn, Xm, XZR)

- `r = mul(xN, xM)` — BTOR2 `mul` (64-bit, low 64 of 128-bit
  product). Export name: `mul xN xM`.

**MADD Xd, Xn, Xm, Xa** / **MSUB Xd, Xn, Xm, Xa**

- `r = xA + xN * xM` / `xA - xN * xM`.
- Lowered as `add xA (mul xN xM)` / `sub xA (mul xN xM)`.

**SMULH Xd, Xn, Xm** / **UMULH Xd, Xn, Xm**

- High 64 bits of signed / unsigned 128-bit product.
- BTOR2: `slice (smul_128(xN, xM)) 127 64` where `smul_128` is
  `sext xN 128 * sext xM 128`; `umulh` analogously with `uext`.

**SMULL Xd, Wn, Wm** (alias SMADDL Xd, Wn, Wm, XZR)

- Sign-extend each 32-bit W operand to 64 bits, then multiply:
  `r = sext(xN[31:0], 64) * sext(xM[31:0], 64)`. Result is 64 bits.

**UMULL Xd, Wn, Wm** (alias UMADDL)

- Zero-extend each 32-bit W operand to 64 bits, then multiply.

**SMADDL / SMSUBL / UMADDL / UMSUBL**: accumulate variants of the
above.

**SDIV Xd, Xn, Xm** (64-bit signed divide)

```
if xM == 0:       r = 0
elif xN == INT_MIN AND xM == -1:  r = INT_MIN
else:             r = sdiv(xN, xM)   ; BTOR2 sdiv
```

Encoded in BTOR2 via nested `ite`:

```
ite (eq xM 0)
    0
    (ite (and (eq xN INT_MIN) (eq xM -1))
         INT_MIN
         (sdiv xN xM))
```

⚡ **AArch64 divergence (SDIV div-by-zero):** AArch64 `SDIV` returns
  **0** when the divisor is zero. RV64 `DIV` returns **-1** (all
  ones). Any wedge that relies on the div-by-zero return value must
  be ported with the correct constant.

⚡ **AArch64 divergence (SDIV overflow):** Both AArch64 and RV64 return
  `INT_MIN` for `INT_MIN / -1` (no trap). Behavior identical.

**UDIV Xd, Xn, Xm** (64-bit unsigned divide)

```
ite (eq xM 0)
    0
    (udiv xN xM)
```

⚡ **AArch64 divergence (UDIV div-by-zero):** AArch64 `UDIV` returns
  **0** when the divisor is zero. RV64 `DIVU` returns **2^64 - 1**.

**32-bit W-register variants (SDIV Wd, UDIV Wd)**

- Same ite structure on 32-bit operands. INT_MIN = 0x80000000.
- Result zero-extended to 64 bits.

⚡ **AArch64 divergence (W-register divide):** RV64 `DIVW` / `DIVUW`
  sign-extend the 32-bit result to 64. AArch64 SDIV/UDIV on
  W-registers zero-extend. The div-by-zero behavior (→ 0) is the
  same for both 32-bit and 64-bit AArch64 variants.

**No MULW analogue**: AArch64 has no exact equivalent to RV64's
`MULW` (multiply then sign-extend lower 32 bits). The closest forms
are SMULL (sign-extend inputs, 64-bit result) and MUL on W-registers
(zero-extend result). The translator must not assume RV64 MULW
semantics apply to any AArch64 instruction.

### 5.9 Branches

**B label** (unconditional)

- `next pc = pc + sign_extend(imm26 << 2, 64)`.

**BL label** (branch with link)

- `next reg_x30 = pc + 4`.
- `next pc = pc + sign_extend(imm26 << 2, 64)`.
- x30 is the AArch64 link register (LR).

⚡ **AArch64 divergence (link register):** AArch64 uses x30 as the
  link register; RV64 uses x1 (ra). Entry assumptions and the
  dispatch self-loop use x30 accordingly (§7).

**BR Xn** (branch to register)

- `next pc = xN`.

**BLR Xn** (branch with link to register)

- `next reg_x30 = pc + 4`.
- `next pc = xN`.

**RET {Xn}** (return; default Xn = x30)

- `next pc = xN` (or `x30` if omitted).
- Lowered identically to `BR Xn`.

**B.cond label** (conditional branch)

- `cond_val = evaluate_condition(cond, nzcv)` (§5.3), a `bv1` predicate.
- `next pc = ite(cond_val, pc + sign_extend(imm19 << 2, 64), pc + 4)`.

**CBZ / CBNZ Xn, label** (compare and branch)

- `CBZ`: `next pc = ite(eq xN 0, target, pc + 4)`.
- `CBNZ`: `next pc = ite(ne xN 0, target, pc + 4)`.
- No flag update; these do not go through NZCV.

**TBZ / TBNZ Xn, #bit, label** (test bit and branch)

- `TBZ`: `next pc = ite(eq (slice xN bit bit) 0, target, pc + 4)`.
- `TBNZ`: `next pc = ite(ne (slice xN bit bit) 0, target, pc + 4)`.

### 5.10 Loads and stores

All addresses are computed from the addressing mode (§5.11).

**64-bit loads (LDR Xt)**

- Compose 8 byte reads from `mem`. `r = concat(mem[addr+7], ..., mem[addr])` (little-endian).
- `next reg_x{Rt} = r`.

**32-bit loads**

- `LDR Wt`: 4 bytes, zero-extend to 64 bits.
- `LDRSW Xt`: 4 bytes, sign-extend to 64 bits.

⚡ **AArch64 divergence (LDR Wt zero-extends):** The 32-bit load
  `LDR Wt` zero-extends to 64. RV64 `LW` sign-extends; RV64 `LWU`
  zero-extends. The sign-extending form is `LDRSW`, not `LDR Wt`.

**8-bit loads**

- `LDRB Wt`: 1 byte, zero-extend to 64.
- `LDRSB Xt`: 1 byte, sign-extend to 64.
- `LDRSB Wt`: 1 byte, sign-extend to 32, zero-extend to 64.

**16-bit loads**

- `LDRH Wt`: 2 bytes, zero-extend to 64.
- `LDRSH Xt`: 2 bytes, sign-extend to 64.
- `LDRSH Wt`: 2 bytes, sign-extend to 32, zero-extend to 64.

**64-bit stores (STR Xt)**

- Decompose 8 byte writes: `next mem = write(write(...write(mem, addr, r[7:0])..., addr+7, r[63:56]))`.

**32-bit stores (STR Wt)**

- Store low 32 bits of `xN` (= `reg_x{N}[31:0]`): 4 byte writes.

**8-bit and 16-bit stores (STRB, STRH)**

- Store low 8 / 16 bits of `xN`: 1 / 2 byte writes.

**Load pair (LDP Xt1, Xt2, [base, imm])**

- Two consecutive 64-bit loads at `addr` and `addr + 8`.
- `next reg_x{Rt1} = mem[addr..addr+7]`.
- `next reg_x{Rt2} = mem[addr+8..addr+15]`.

**Store pair (STP Xt1, Xt2, [base, imm])**

- Two consecutive 64-bit stores.

**LDP / STP 32-bit forms**: pairs of W-register loads/stores,
zero-extending on load. `imm` in the pair encoding is scaled by 4.

### 5.11 Addressing modes

AArch64 supports several addressing modes. The translator decodes
and computes the effective address `addr` before lowering:

| Mode | Syntax | Effective address | SP update |
|---|---|---|---|
| Base register | `[Rn]` | `xN` (or `sp` if Rn=31) | none |
| Base + imm offset | `[Rn, #imm]` | `xN + imm` | none |
| Base + register | `[Rn, Rm, extend shift]` | `xN + extend(xM) << shift` | none |
| Pre-indexed | `[Rn, #imm]!` | `xN + imm` | `next Rn = xN + imm` |
| Post-indexed | `[Rn], #imm` | `xN` | `next Rn = xN + imm` |
| Literal (LDR) | `[pc, #imm]` | `pc + imm` | none |

Pre- and post-indexed modes emit a writeback `next` clause for Rn
in addition to the load/store `next mem` clause.

Misaligned accesses are not specially handled; they decompose into
per-byte `read`/`write` operations the same way. A later spec
parameter can flag misalignment if needed.

### 5.12 Conditional select and set

**CSEL Xd, Xn, Xm, cond**

- `r = ite(cond_val, xN, xM)`.

**CSINC Xd, Xn, Xm, cond**

- `r = ite(cond_val, xN, add xM 1)`.
- Aliases: CINC (Xm = Xn, cond inverted), CSET (Xn = XZR, Xm = XZR).

**CSINV Xd, Xn, Xm, cond**

- `r = ite(cond_val, xN, not xM)`.
- Aliases: CINV, CSETM.

**CSNEG Xd, Xn, Xm, cond**

- `r = ite(cond_val, xN, neg xM)`.
- Alias: CNEG.

All conditional select instructions leave NZCV unchanged.

### 5.13 Compare instructions (flag-setting only)

- **CMP Xn, operand**: alias for `SUBS XZR, Xn, operand`. Updates
  NZCV per §5.2; write to XZR discarded.
- **CMN Xn, operand**: alias for `ADDS XZR, Xn, operand`. Updates
  NZCV.
- **TST Xn, operand**: alias for `ANDS XZR, Xn, operand`. Updates
  NZCV.

### 5.14 System and barrier instructions

- **SVC #imm**: supervisor call. Sets `halted = 1`. PC frozen.
  The result of the system call is modelled as a fresh `nondet`
  value injected into the relevant register (typically x0) at the
  *next* cycle when `halted = 0`. At v1.0.0, the schema treats SVC
  as a hard halt; post-SVC continuation requires a spec continuation
  parameter (deferred).
- **BRK #imm**: breakpoint. Sets `halted = 1`. Same treatment as SVC.
- **NOP**: no-op. PC advances by 4; nothing else changes.
- **HINT #imm** (NOP, YIELD, WFE, WFI, SEV, SEVL, PACDZA, etc.):
  treated as NOP at the schema level unless a future spec parameter
  enables specific semantics.
- **DSB, DMB, ISB**: data/instruction barrier. Treated as NOP
  (ordering primitives, not state-mutating). Recorded as role `OTHER`
  in the annotation.

## 6. Dispatch

The `dispatch` layer ties PCs to the per-instruction lowering in the
`library` layer.

- One large nested `ite` keyed on `pc`, ordered by ascending PC.
- Each arm matches one PC in the analyzed function set.
- PCs outside the analyzed set: the dispatch arm self-loops
  (`next pc = pc`) and freezes all registers, SP, and NZCV
  (every `next` becomes identity). This makes "left the analyzed
  region" detectable by the `bad` expression.
- Arm ordering: strictly ascending by PC (deterministic).

## 7. Entry assumptions

Added to `init` and `constraint` layers by default; each can be
overridden via spec parameters.

- **`x30` (link register / LR)** at entry: constrained to point
  *outside* the analyzed function set. Default: union of non-analyzed
  `PT_LOAD` ranges plus synthetic exit address `0xFFFF_FFFF_FFFF_FFFE`.

⚡ **AArch64 divergence (link register):** The entry-LR assumption
  applies to x30 here, vs x1 (ra) in `riscv-btor2`.

- **`sp`** at entry: free (no constraint by default). Specs that
  require 16-byte alignment can add `SPInit(op=eq_mod, value=0,
  modulus=16)`.
- **All GPRs x0–x29**: free unless the spec pins them via
  `RegisterInit`. x30 follows the LR assumption above.
- **`nzcv`** at entry: free unless the spec provides `NZCVInit`.
- **PC at entry**: constrained to the analyzed scope's entry PC.
- **Memory at entry**: bytes inside `PT_LOAD` are pinned; bytes
  outside are free.

## 8. Constraint and bad encoding

- The `constraint` layer accumulates one BTOR2 `constraint` per
  spec-supplied invariant or assumption.
- `bad` expressions are *true when the property is violated*.
- Multi-clause `bad` aggregates by `or`.
- `LearnedFact` entries land in `constraint` with provenance in the
  annotation.

## 9. Havoc semantics

- `havoc_registers` replaces the `next` clause of each named GPR
  index (0–30) or `sp` with `nondet`. Register values are
  independently free at every cycle.
- Havoc never changes the *initial* value.
- Memory havoc is not supported at v1.0.0.

## 10. Verdict semantics

| Verdict | Meaning |
|---|---|
| `reachable` | A finite trace satisfies all constraints and reaches the bad expression. Witness in raw payload. |
| `unreachable` | No trace within `bound` reaches a `bad`. BMC only. |
| `proved` | Inductive invariant from Spacer/Pono proves the property at all depths. |
| `unknown` | Solver gave up. `reason` field distinguishes timeout, OOM, incompleteness. |

The `bound` parameter sets the BMC cycle count. For Spacer/Pono,
`bound` is ignored.

## 11. Annotation conventions

For every emitted node:

- **role**: `sort`, `state`, `input`, `init`, `transition`,
  `constraint`, `bad`, `observable`, `assumption`,
  `learned_invariant`, `dispatch`, `binding`, `havoc`,
  `expression`, `other`.
- **source mapping** (`Aarch64SourceMapping`): `pc` (origin PC in
  binary), `dwarf_file`, `dwarf_line` (when DWARF available),
  `mnemonic` (for nodes inside an instruction's lowering).
- **provenance**: schema version, spec hash, optional learned-fact
  provenance.

## 12. Stability profile (cache behaviour)

| Layer | Recompute when |
|---|---|
| `header` | Never under this schema version. |
| `machine` | Core count changes (unused at v1). |
| `library` | ISA subset changes (AArch64 A64 base integer is fixed at v1). |
| `dispatch` | The set of analyzed PCs changes. |
| `init` | Spec's entry assumptions, register / memory inits change. |
| `constraint` | Spec's assumptions or learned facts change. |
| `bad` | Spec's observables or property change. |
| `binding` | Always re-emitted (cheap). |
| `havoc` | `havoc_registers` set changes. |

Cache keys: `(spec_hash, source_hash, schema_version, engine_name)`.

## 13. Interpreter semantics

The pair ships two concrete interpreters — one source-side (AArch64
simulator) and one reasoning-side (multi-step BTOR2 evaluator) — both
first-class components alongside the translator and lifter.

### 13.1 Source interpreter

- **Architectural state**: 31 × 64-bit registers (x0–x30), 64-bit SP,
  64-bit PC, 4-bit NZCV, 1-bit `halted`, byte-addressable 64-bit
  memory.
- **Step**: decodes the 32-bit A64 instruction at the current PC and
  applies the per-instruction lowering from §5. A divergence between
  the simulator and the library lowering is always a bug.
- **R31 context resolution**: the interpreter resolves register 31
  identically to the library — XZR (constant 0) in data-processing
  contexts, SP in memory/stack contexts.
- **Halting**: `SVC` / `BRK` set `halted = 1` and freeze PC. A PC
  in `excluded_pc_ranges` halts with reason `pc_in_excluded_range`.
  A PC outside loadable bytes halts with reason `fetch_failed`.
- **Trace recording**: post-step state in each step's `deltas`
  (PC, full register snapshot including x0–x30 and SP, NZCV, memory
  changes, halted flag) and source location (PC, mnemonic, disasm,
  optional DWARF file/line) in `location`.

### 13.2 Reasoning interpreter

- Same BTOR2 op subset as `riscv-btor2`. Unknown ops raise
  `NotImplementedError`. Ill-formed widths raise `SortMismatch`.
- **Symbol names**: `pc`, `reg_x{0..30}`, `sp`, `nzcv`, `halted`.

### 13.3 Cross-check correspondence

Per-step projection:

| Field | Source | Reasoning |
|---|---|---|
| `pc` | `deltas.pc` | `machine[sym["pc"]]` |
| `reg_x{N}` (N=0..30) | `deltas.regs[N]` | `machine[sym["reg_x{N}"]]` |
| `sp` | `deltas.sp` | `machine[sym["sp"]]` |
| `nzcv` | `deltas.nzcv` | `machine[sym["nzcv"]]` |
| `halted` | `deltas.halted` | `machine[sym["halted"]]` |

`mem` is not compared per-step; a final-state check suffices.

### 13.4 Interpreter version

`interpreter_version` is bumped independently of `schema_version`.
Cached traces include `interpreter_version` in their cache key.

## 14. AArch64-vs-RV64 semantics divergence summary

For auditors and future ISA-portability analysis:

| Semantic aspect | RV64 (`riscv-btor2`) | AArch64 (`aarch64-btor2`) |
|---|---|---|
| GPR count | 32 (x0 always-zero) | 31 (x0–x30 writable) + XZR/SP |
| Link register | x1 (ra) | x30 (lr) |
| Condition flags | None (compare-and-branch) | NZCV 4-bit state |
| Branch style | Register compare + branch | Flag-setting + B.cond |
| `DIV` / `SDIV` div-by-zero | Returns −1 | Returns 0 |
| `DIVU` / `UDIV` div-by-zero | Returns 2^64 − 1 | Returns 0 |
| `DIVW` / 32-bit signed div overflow | Sign-extends result to 64 | Zero-extends result to 64 |
| `ADDW` / 32-bit add | Sign-extends result to 64 | Zero-extends result to 64 |
| Word op result extension | Sign | Zero |
| `MULW` equivalent | MULW (sign-extend lower 32 to 64) | None; SMULL sign-extends *inputs* |
| Carry convention (SUB) | Borrow (C=1 = borrow) | No-borrow (C=1 = no borrow) |
| Instruction width | Variable (16 or 32 bits; RVC) | Fixed 32 bits (A64) |
| Memory endianness | Little-endian | Little-endian |

This table is the primary artifact for the C-UB-but-ISA-defined
wedge analysis. The five divide-by-zero and word-extension rows are
where the wedge behaviour differs between the two ISAs; any
C-source task that relies on these semantics requires an
AArch64-specific ground truth derivation, not a port of the RV64
one.

## 15. What this schema deliberately does not do

- **Floating point.** NEON, SVE, FP (F, D, H scalar) are out of scope
  at v1.0.0.
- **Atomics.** LDXR/STXR, LSE atomic extensions — concurrency is
  out of scope.
- **SVE (Scalable Vector Extension).** Variable-length vectors.
- **Privileged mode.** EL1+, system registers, trap handling, paging,
  interrupts.
- **Pointer Authentication (PAC).** All PAC instructions treated as
  NOP.
- **Branch Target Identification (BTI).** Treated as NOP.
- **Calling convention enforcement.** Not checked; scope spec
  parameter controls which callees are inlined.
- **Concurrency.** Single execution thread only.
- **Big-endian memory.** BE8 is outside scope.

These exclusions are stable. Adding any of them requires a schema
version bump; partial support is not permitted.
