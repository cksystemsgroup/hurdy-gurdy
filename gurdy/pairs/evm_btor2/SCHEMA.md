# `evm-btor2` schema

This document is the contract between hurdy-gurdy and any consumer
(LLM or human) of the `evm-btor2` pair's output. Every translation
choice this pair makes is recorded here. If the code disagrees with
this document, the code is wrong; if the schema is wrong, fix it and
bump the version.

The invariant: same `(QuestionSpec, EVM bytecode)` produces a byte-
identical BTOR2 reasoning artifact under this schema version.

---

## 1. Versioning

- **Schema version:** `1.0.0`.
- **Frozen:** P1. No changes without a version bump.
- The schema version is recorded on every cached artifact.
- A change that affects emitted bytes bumps the *minor* component.
  A breaking change to the spec language bumps the *major*.

### Changelog

- **1.0.0** — Initial release: §§2–16. Pure-function EVM subset,
  single contract, BMC engine, `reach` property class.

### EVM baseline

This schema targets **London EVM** (EIP-1559, EIP-3198 BASEFEE,
EIP-3529 refund cap) with the **Shanghai** PUSH0 opcode (EIP-3855)
available. Later EVM versions are out of scope until §16 is lifted.

The `evm_version` field in `AnalysisScope` records which EVM version
the bytecode was compiled for; the translator uses it to gate opcode
availability (e.g., PUSH0 only on ≥ Shanghai).

---

## 2. Sorts

The translator declares all sorts in the `header` layer. Every cross-
layer reference uses the symbolic export name, not a raw numeric id.

| Symbolic name | Sort    | Width / args                                   |
|---------------|---------|------------------------------------------------|
| `bv1`         | bitvec  | 1 (boolean flags)                              |
| `bv8`         | bitvec  | 8 (memory / calldata byte element)             |
| `bv10`        | bitvec  | 10 (stack pointer; max 1024 = 0x400)           |
| `bv16`        | bitvec  | 16 (program counter; max bytecode 24 576 B)    |
| `bv64`        | bitvec  | 64 (gas; max ~30 M per block, fits in 64 bits) |
| `bv256`       | bitvec  | 256 (dominant sort: words, arithmetic, addrs)  |
| `stack_t`     | array   | index `bv10`, element `bv256`                  |
| `mem_t`       | array   | index `bv256`, element `bv8`                   |
| `sto_t`       | array   | index `bv256`, element `bv256`                 |

`bv256` is the EVM word. All stack operations, arithmetic, storage
reads/writes, and address values use `bv256`. Byte-granular memory
and calldata use `bv8` element arrays indexed by `bv256` byte offset.

---

## 3. State variables

Declared in the `machine` layer. Names are fixed; renaming requires a
version bump.

### 3.1 Execution state

| Name             | Sort      | Init                  | Meaning                               |
|------------------|-----------|-----------------------|---------------------------------------|
| `sp`             | `bv10`    | `0`                   | stack pointer; depth = value          |
| `stack`          | `stack_t` | all-zero              | operand stack; top = `stack[sp−1]`    |
| `mem`            | `mem_t`   | all-zero              | EVM memory (byte-addressed)           |
| `mem_words`      | `bv256`   | `0`                   | memory high-water mark in 32-B words  |
| `sto`            | `sto_t`   | per spec              | persistent storage                    |
| `pc`             | `bv16`    | `0`                   | program counter                       |
| `gas`            | `bv64`    | per spec              | gas remaining                         |
| `trap`           | `bv1`     | `0`                   | 1 = abnormal termination              |
| `halted`         | `bv1`     | `0`                   | 1 = execution finished (any reason)   |
| `returndata`     | `mem_t`   | all-zero              | output buffer (RETURN writes here)    |
| `returndatasize` | `bv256`   | `0`                   | byte length of valid return data      |

### 3.2 Warm-slot tracking (storage access sets — EIP-2929)

A single state variable:

| Name         | Sort      | Init     | Meaning                               |
|--------------|-----------|----------|---------------------------------------|
| `sto_warm`   | `sto_t`   | per spec | `sto_warm[s] == 1` iff slot `s` warm  |

Element sort is `bv256` but only the low bit is meaningful (0 = cold,
1 = warm). The translator coerces reads: `warm = sto_warm[s][0:0]`.

The spec may pre-warm slots via `StorageWarm` assumptions. All slots
accessed by a SLOAD or SSTORE become warm for subsequent accesses in
the same call.

---

## 4. Symbolic context (free inputs)

Declared in the `context` layer. These are symbolic state variables
initialized at step 0 and held constant across all steps (they model
per-invocation inputs, not per-step).

| Name          | Sort    | Default   | Meaning                          |
|---------------|---------|-----------|----------------------------------|
| `caller`      | `bv256` | free      | `CALLER` / msg.sender            |
| `callvalue`   | `bv256` | free      | `CALLVALUE` / msg.value (wei)    |
| `origin`      | `bv256` | free      | `ORIGIN` / tx.origin             |
| `gasprice`    | `bv256` | free      | `GASPRICE`                       |
| `calldata`    | `mem_t` | free      | immutable per-call input bytes   |
| `calldatasize`| `bv256` | free      | byte length of calldata          |
| `blocknumber` | `bv256` | free      | `NUMBER`                         |
| `timestamp`   | `bv256` | free      | `TIMESTAMP`                      |
| `prevrandao`  | `bv256` | free      | `DIFFICULTY` / `PREVRANDAO`      |
| `gaslimit`    | `bv256` | free      | `GASLIMIT`                       |
| `coinbase`    | `bv256` | free      | `COINBASE`                       |
| `basefee`     | `bv256` | free      | `BASEFEE` (EIP-3198)             |
| `chainid`     | `bv256` | `1`       | `CHAINID` (mainnet default)      |

**Address constraints**: `caller` and `origin` are valid 20-byte
Ethereum addresses. The translator automatically emits:

```
constraint: caller[255:160] == 0
constraint: origin[255:160] == 0
```

`calldata[i]` for `i >= calldatasize` is treated as `0` by
`CALLDATALOAD` (per Yellow Paper): the translator enforces this with:

```
constraint: for all i in bv256: (i >= calldatasize) => (calldata[i] == 0)
```

---

## 5. Bytecode model

- The deployed bytecode is **immutable** — a byte-constant array in
  the BTOR2 model. It is not a state variable; it is encoded as a
  sequence of constants in the `header` layer.
- Symbolic name: `code[i]` for byte index `i` (a `bv8` constant).
- `CODESIZE` returns `len(bytecode)` as a `bv256` constant.

### 5.1 JUMPDEST table

The translator precomputes the set of valid JUMPDEST positions by
scanning the bytecode once (skipping PUSH argument bytes). This
produces a boolean array:

```
jumpdest_valid: Array bv16 bv1
```

initialized at every position: `jumpdest_valid[i] = 1` iff byte `i`
is a `JUMPDEST` (0x5b) opcode and not a PUSH argument. This constant
array is declared in the `header` layer.

`JUMP` and `JUMPI` look up `jumpdest_valid[target]` and set
`trap = 1` if the result is `0`.

---

## 6. Stack model

The EVM operand stack holds up to 1024 items. Each item is `bv256`.

- `sp` is the number of items currently on the stack (0 = empty).
- `stack[sp−1]` is the top of stack (TOS).
- `stack[0]` is the oldest element.

**Overflow**: pushing when `sp == 1024` sets `trap = 1; halted = 1`.
The stack and PC are not updated.

**Underflow**: popping when `sp == 0` sets `trap = 1; halted = 1`.

These checks fire before the opcode's other side effects. Once `trap`
or `halted` is set, the dispatch loop holds the state constant for all
subsequent steps (no further opcode lowerings fire).

### 6.1 Stack pointer arithmetic

Stack pointer values are `bv10`. The translator extends to `bv256` for
arithmetic comparisons with 1024:

```
sp_full  = zext(sp, 246)          ; bv256
overflow = (sp_full == 1024) AND <PUSH-class opcode>
underflow = (sp_full == 0)    AND <POP-class opcode>
trap_next = trap OR overflow OR underflow
```

---

## 7. Memory model

EVM memory is a byte array, zero-initialized per invocation. Size
expands in 32-byte words. The cost of expansion is charged in gas.

- State: `mem: mem_t`, `mem_words: bv256` (high-water mark in words).
- `MLOAD(offset)`: reads 32 bytes from `mem[offset..offset+31]`
  (big-endian assembly into `bv256`). Updates `mem_words` if
  `ceil((offset + 32) / 32) > mem_words`.
- `MSTORE(offset, value)`: writes 32 bytes to `mem[offset..offset+31]`
  (big-endian split from `bv256`). Updates `mem_words`.
- `MSTORE8(offset, byte)`: writes 1 byte to `mem[offset]`.
  Updates `mem_words` if `ceil((offset + 1) / 32) > mem_words`.
- `MSIZE`: returns `mem_words * 32` (zero-padded to `bv256`).
- `CALLDATACOPY(dest, src, len)`, `CODECOPY(dest, src, len)`: loop
  unrolled to `len` byte writes. P1 spec: `len` must be a compile-time
  constant (PUSH immediate) for the translator to unroll; dynamic
  length → BLOCKER.

### 7.1 Memory expansion gas

```
Cmem(n) = floor(n * n / 512) + 3 * n    ; n = mem_words
delta_gas_mem = Cmem(new_mem_words) − Cmem(old_mem_words)
```

Computed in `bv256` arithmetic. If `gas < delta_gas_mem` the
translator sets `trap = 1; halted = 1` before performing the access.

---

## 8. Storage model

EVM storage is a 256→256 mapping, persistent across calls (but only
within one call in this pair's scope).

- State: `sto: sto_t` — initial values per `StoragePin` assumptions,
  all other slots initialized to `0`.
- `SLOAD(slot)`: reads `sto[slot]`. Gas: 2 100 (cold) or 100 (warm).
  Sets `sto_warm[slot] = 1`.
- `SSTORE(slot, value)`: writes `sto[slot] := value`. Gas: EIP-2929
  schedule (§10.4). Sets `sto_warm[slot] = 1`.

---

## 9. Calldata model

Calldata is the per-invocation input byte array. It is immutable.

- Context: `calldata: mem_t`, `calldatasize: bv256`.
- `CALLDATALOAD(offset)`: reads `calldata[offset..offset+31]`
  (big-endian into `bv256`). Bytes past `calldatasize` are zero (per
  Yellow Paper). Gas: 3.
- `CALLDATASIZE`: returns `calldatasize`. Gas: 2.
- `CALLDATACOPY(dest, src, len)`: copies `len` bytes from
  `calldata[src..]` to `mem[dest..]`. Bytes past `calldatasize`
  are zero. Gas: 3 + 3 * ceil(len / 32) + memory expansion.
  P1 restriction: `len` must be a compile-time constant.

---

## 10. Gas model

### 10.1 Fixed opcode costs (London)

All values are in gas units. Dynamic costs (memory expansion,
SLOAD/SSTORE EIP-2929, EXP byte count) are listed separately.

| Opcode group                                     | Cost |
|--------------------------------------------------|------|
| ADD, SUB, LT, GT, SLT, SGT, EQ, ISZERO          | 3    |
| AND, OR, XOR, NOT, BYTE, SHL, SHR, SAR           | 3    |
| MUL, DIV, SDIV, MOD, SMOD, SIGNEXTEND            | 5    |
| ADDMOD, MULMOD                                   | 8    |
| EXP (base cost; see §10.2)                       | 10   |
| KECCAK256 (base; P2+)                            | 30   |
| ADDRESS, ORIGIN, CALLER, CALLVALUE               | 2    |
| CALLDATALOAD, CALLDATASIZE                       | 3/2  |
| CODESIZE, GASPRICE                               | 2    |
| COINBASE, TIMESTAMP, NUMBER, DIFFICULTY/PREVRANDAO, GASLIMIT | 2 |
| CHAINID, BASEFEE                                 | 2    |
| MLOAD, MSTORE, MSTORE8 (+ expansion)            | 3    |
| MSIZE                                            | 2    |
| SLOAD cold/warm (EIP-2929)                       | 2100/100 |
| JUMP                                             | 8    |
| JUMPI                                            | 10   |
| JUMPDEST                                         | 1    |
| POP                                              | 2    |
| PUSH0                                            | 2    |
| PUSH1–PUSH32                                     | 3    |
| DUP1–DUP16                                       | 3    |
| SWAP1–SWAP16                                     | 3    |
| PC                                               | 2    |
| GAS                                              | 2    |
| STOP, RETURN, REVERT                             | 0    |
| INVALID                                          | 0 (all remaining gas consumed) |

### 10.2 EXP dynamic cost

`EXP(base, exp)` costs `10 + 50 * byte_length(exp)` where
`byte_length(n)` is the number of bytes needed to represent `n`
(= 0 for `n == 0`). In BTOR2: the translator emits a chain of
comparisons on the `bv256` exponent to determine byte length, then
multiplies by 50.

### 10.3 Gas check ordering

For every opcode:

1. Compute static gas cost (+ dynamic component where applicable).
2. If `gas < cost`: set `trap = 1; halted = 1`. No state update.
3. Otherwise: `gas := gas − cost`. Perform the opcode's state update.

### 10.4 SSTORE gas (EIP-2929 + EIP-3529)

| Condition                                              | Cost  | Refund |
|--------------------------------------------------------|-------|--------|
| Slot cold, new == current                              | 2 200 | 0      |
| Slot cold, new != current, current == original        | 20 000| see below |
| Slot cold, new != current, current != original        | 2 200 | see below |
| Slot warm, new == current                             | 100   | 0      |
| Slot warm, new != current, current == original        | 2 900 | see below |
| Slot warm, new != current, current != original        | 100   | see below |

Refund schedule (EIP-3529 cap at `gas_used / 5`):

- If `new == original AND original != 0`: refund 4 800.
- If `new == 0 AND original != 0`: refund 4 800.

P1 simplification: SSTORE refund accounting is omitted. Refunds are
tracked in state but not applied to final gas. The spec field
`engine="z3-bmc"` treats gas as over-approximated anyway.

---

## 11. Trap and halt semantics

| Event                            | Effect                              |
|----------------------------------|-------------------------------------|
| Stack overflow (push at depth 1024) | `trap=1; halted=1`               |
| Stack underflow (pop at depth 0) | `trap=1; halted=1`                 |
| Invalid jump destination         | `trap=1; halted=1`                 |
| Out-of-gas                       | `trap=1; halted=1`                 |
| INVALID (0xFE)                   | `trap=1; halted=1`                 |
| REVERT                           | `trap=1; halted=1`                 |
| STOP                             | `trap=0; halted=1`                 |
| RETURN                           | `trap=0; halted=1; returndata set` |
| Out-of-scope opcode (§16)        | `trap=1; halted=1`                 |

Once `halted = 1`, the dispatch selects a no-op lowering for all
subsequent steps: all next-state values equal current values. This
keeps the BTOR2 model well-formed at any bound.

---

## 12. Opcode lowering table (P1 scope)

All opcodes listed here are **fully implemented** in P1. All others
hit the out-of-scope lowering (§16).

### 12.1 Arithmetic

| Opcode      | Bytecode | Stack effect         | Notes                            |
|-------------|----------|----------------------|----------------------------------|
| STOP        | 0x00     | –                    | halt=1, trap=0                   |
| ADD         | 0x01     | (a,b) → a+b          | bv256 add (wraps mod 2^256)      |
| MUL         | 0x02     | (a,b) → a*b          | wraps                            |
| SUB         | 0x03     | (a,b) → a-b          | wraps                            |
| DIV         | 0x04     | (a,b) → a/b          | unsigned; b==0 → 0               |
| SDIV        | 0x05     | (a,b) → a/b          | signed; b==0 → 0; overflow (min_int/-1) → min_int |
| MOD         | 0x06     | (a,b) → a%b          | unsigned; b==0 → 0               |
| SMOD        | 0x07     | (a,b) → a%b          | signed; b==0 → 0; sign of a      |
| ADDMOD      | 0x08     | (a,b,N) → (a+b)%N    | N==0 → 0; no overflow in sum     |
| MULMOD      | 0x09     | (a,b,N) → (a*b)%N    | N==0 → 0; exact multiply         |
| EXP         | 0x0a     | (a,b) → a^b          | see §10.2 for gas                |
| SIGNEXTEND  | 0x0b     | (b,x) → sign_ext     | b >= 31 → x unchanged            |

### 12.2 Comparison and bitwise

| Opcode   | Bytecode | Stack effect    | Notes                              |
|----------|---------|-----------------|------------------------------------|
| LT       | 0x10    | (a,b) → a<b     | unsigned; result 0 or 1            |
| GT       | 0x11    | (a,b) → a>b     | unsigned                           |
| SLT      | 0x12    | (a,b) → a<b     | signed (2's complement)            |
| SGT      | 0x13    | (a,b) → a>b     | signed                             |
| EQ       | 0x14    | (a,b) → a==b    |                                    |
| ISZERO   | 0x15    | (a) → a==0      |                                    |
| AND      | 0x16    | (a,b) → a&b     |                                    |
| OR       | 0x17    | (a,b) → a\|b    |                                    |
| XOR      | 0x18    | (a,b) → a^b     |                                    |
| NOT      | 0x19    | (a) → ~a        | bitwise complement                 |
| BYTE     | 0x1a    | (i,x) → byte_i  | i >= 32 → 0; byte 0 = MSB         |
| SHL      | 0x1b    | (shift,x) → x<<shift | logical; shift>=256 → 0       |
| SHR      | 0x1c    | (shift,x) → x>>shift | logical; shift>=256 → 0       |
| SAR      | 0x1d    | (shift,x) → x>>shift | arithmetic; shift>=256 → 0 or -1 |

### 12.3 Environment

| Opcode        | Bytecode | Stack effect       | Notes                           |
|---------------|----------|--------------------|---------------------------------|
| ADDRESS       | 0x30     | → this_address     | P1: free symbolic `bv256`       |
| ORIGIN        | 0x32     | → origin           | context var                     |
| CALLER        | 0x33     | → caller           | context var                     |
| CALLVALUE     | 0x34     | → callvalue        | context var                     |
| CALLDATALOAD  | 0x35     | (i) → calldata[i..i+31] | big-endian 32B read; past end → 0 |
| CALLDATASIZE  | 0x36     | → calldatasize     | context var                     |
| CALLDATACOPY  | 0x37     | (dest,src,len)     | P1: len must be PUSH-immediate constant |
| CODESIZE      | 0x38     | → len(bytecode)    | constant                        |
| CODECOPY      | 0x39     | (dest,src,len)     | P1: len constant only           |
| GASPRICE      | 0x3a     | → gasprice         | context var                     |
| RETURNDATASIZE| 0x3d     | → returndatasize   | 0 at entry (pure call)          |
| RETURNDATACOPY| 0x3e     | (dest,src,len)     | P2+                             |
| BASEFEE       | 0x48     | → basefee          | context var (EIP-3198)          |
| CHAINID       | 0x46     | → chainid          | context var (EIP-1344)          |

### 12.4 Block

| Opcode      | Bytecode | Stack effect  |
|-------------|----------|---------------|
| BLOCKHASH   | 0x40     | (n) → free `bv256` (uninterpreted for any n) |
| COINBASE    | 0x41     | → coinbase    |
| TIMESTAMP   | 0x42     | → timestamp   |
| NUMBER      | 0x43     | → blocknumber |
| DIFFICULTY  | 0x44     | → prevrandao  |
| GASLIMIT    | 0x45     | → gaslimit    |

### 12.5 Stack, memory, storage

| Opcode      | Bytecode    | Stack effect           | Notes                        |
|-------------|-------------|------------------------|------------------------------|
| POP         | 0x50        | (a) →                  |                              |
| MLOAD       | 0x51        | (off) → mem[off..off+31] | big-endian; expands mem    |
| MSTORE      | 0x52        | (off,v) →              | big-endian; expands mem      |
| MSTORE8     | 0x53        | (off,b) →              | stores low byte              |
| SLOAD       | 0x54        | (slot) → sto[slot]     | EIP-2929 gas                 |
| SSTORE      | 0x55        | (slot,val) →           | EIP-2929/3529 gas; §10.4     |
| MSIZE       | 0x59        | → mem_words * 32       |                              |
| GAS         | 0x5a        | → gas (after this opcode's cost) | gas remaining       |
| PUSH0       | 0x5f        | → 0                    | EIP-3855; Shanghai+          |
| PUSH1..PUSH32 | 0x60..0x7f | → immediate bv256     | immediate bytes follow PC    |
| DUP1..DUP16 | 0x80..0x8f | stack[sp-N] → top      |                              |
| SWAP1..SWAP16 | 0x90..0x9f | swap top with stack[sp-1-N] |                       |

### 12.6 Control flow

| Opcode    | Bytecode | Stack effect      | Notes                                     |
|-----------|----------|-------------------|-------------------------------------------|
| JUMP      | 0x56     | (dest) →          | jumpdest_valid[dest] or trap              |
| JUMPI     | 0x57     | (dest,cond) →     | jump if cond!=0; jumpdest_valid check     |
| JUMPDEST  | 0x5b     | –                 | no-op; marks valid jump target            |
| PC        | 0x58     | → pc              | value of PC *before* this instruction     |

### 12.7 Termination

| Opcode   | Bytecode | Stack effect    | Notes                                         |
|----------|----------|-----------------|-----------------------------------------------|
| STOP     | 0x00     | –               | halted=1, trap=0                              |
| RETURN   | 0xf3     | (off,len) →     | halted=1, trap=0; copies mem[off..off+len] to returndata |
| REVERT   | 0xfd     | (off,len) →     | halted=1, trap=1; copies mem to returndata    |
| INVALID  | 0xfe     | –               | halted=1, trap=1; consumes all gas            |

---

## 13. Layer structure

The translator emits layers in this fixed order. The linker concatenates
them into a single BTOR2 file, renumbering node IDs monotonically.

| Layer index | Name          | Content                                                   |
|-------------|---------------|-----------------------------------------------------------|
| 0           | `header`      | Sort declarations; `jumpdest_valid` constant; bytecode constants |
| 1           | `machine`     | State variable declarations + init (§3)                   |
| 2           | `context`     | Symbolic context inputs (§4); address range constraints   |
| 3           | `constraint`  | Spec-pinned assumptions (CallerPin, StoragePin, …)        |
| 4           | `dispatch`    | PC-keyed ITE tree selecting per-opcode lowering           |
| 5           | `binding`     | `next` clauses wiring each state variable to dispatch outputs |
| 6           | `bad`         | The negated property (see §14)                            |

Each layer exports a dict of symbolic names → BTOR2 node IDs. Layers
reference exports from earlier layers by name; the linker resolves
them. This indirection means layer order never changes emitted bytes
(except for ID renumbering, which is deterministic).

### 13.1 Dispatch structure

The `dispatch` layer is the core of the translator. For each unique
PC value `p` that appears in the bytecode, the translator emits the
corresponding opcode lowering (§12). The top-level dispatch is:

```
if halted:
    no_op_lowering()
else if pc == p0:
    lowering_0()
else if pc == p1:
    lowering_1()
...
else:
    out_of_scope_lowering()   ; trap=1, halted=1
```

Lowerings are emitted as pure combinational terms (no new `state`
nodes inside dispatch). Each lowering produces a full set of
`next_*` values for every state variable.

---

## 14. Property encoding

### 14.1 Reach properties

All P1 properties are `reach` properties: "does there exist an
execution trace of ≤ `bound` opcode steps where the specified
condition holds at the moment of termination?"

`bad` fires when:

```
bad = halted == 1 AND <reach_condition>
```

The solver searches for a satisfying assignment (counterexample = a
concrete trace reaching the bad state).

### 14.2 Reach conditions by kind

| `ReachKind`       | `bad` expression                                      |
|-------------------|-------------------------------------------------------|
| `revert`          | `trap == 1`                                           |
| `stop`            | `trap == 0`                                           |
| `storage_eq`      | `trap == 0 AND sto[slot] == value`                    |
| `returndata_eq`   | `trap == 0 AND returndata[off..off+len] == data_bytes` |

For `returndata_eq`, the translator emits one equality per byte:
`AND_{i=0}^{len-1}(returndata[off+i] == data[i])`.

### 14.3 Negation

To ask "is it impossible that storage[slot] == value at termination?"
— i.e., to prove absence — the translator emits the same `bad` node.
If the solver returns `unsat`, the absence is proved up to `bound`.

---

## 15. Spec vocabulary

This section is normative for `spec.py` (§ `EvmBtor2Spec`).

### 15.1 `BytecodeRef`

```
hex:           str           lowercase hex, no 0x prefix; must be even length
content_hash:  str | None    keccak256 of the decoded bytes, hex (optional)
```

### 15.2 `AnalysisScope`

```
evm_version:   EvmVersion    "london" | "paris" | "shanghai" | "cancun"
```

Default: `"london"`. Note: PUSH0 (0x5f) is only available on ≥ Shanghai.
The translator rejects PUSH0 in bytecode for `evm_version < "shanghai"`.

### 15.3 Assumptions

| Class              | Fields                              | BTOR2 effect                         |
|--------------------|-------------------------------------|--------------------------------------|
| `CallerPin`        | `address: int` (160-bit)            | `constraint: caller == address`      |
| `CallvaluePin`     | `value: int` (256-bit)              | `constraint: callvalue == value`     |
| `OriginPin`        | `address: int` (160-bit)            | `constraint: origin == address`      |
| `CalldatasizePin`  | `size: int` (≥ 0, < 2^256)         | `constraint: calldatasize == size`   |
| `CalldataBytePin`  | `offset: int`, `value: int (0..255)` | `constraint: calldata[offset] == value` |
| `StoragePin`       | `slot: int`, `value: int`           | `init: sto[slot] = value`            |
| `StorageWarm`      | `slot: int`                         | `init: sto_warm[slot] = 1`           |
| `GasLimitPin`      | `gas: int` (≥ 0, ≤ 2^64−1)         | `init: gas = value`                  |

`StoragePin` sets the *initial* storage value (before any SSTORE in
this call). Multiple pins on different slots are all applied.

### 15.4 `ReachProperty`

```
kind:   ReachKind  "revert" | "stop" | "storage_eq" | "returndata_eq"
slot:   int        required for storage_eq
value:  int        required for storage_eq
offset: int        required for returndata_eq
data:   tuple[int] required for returndata_eq; each int is 0..255
```

### 15.5 `AnalysisDirective`

```
engine:  str        "z3-bmc" (P1)
bound:   int | None max BMC steps; None → translator default (100)
timeout: int | None seconds per solver call; None → solver default
```

---

## 16. Out of scope (P2+)

The following opcodes/features set `trap=1; halted=1` if encountered
in P1 bytecode (out-of-scope lowering):

- `CALL` (0xf1), `CALLCODE` (0xf2), `DELEGATECALL` (0xf4),
  `STATICCALL` (0xfa) — P11.
- `CREATE` (0xf0), `CREATE2` (0xf5) — P11.
- `SELFDESTRUCT` (0xff) — P11.
- `LOG0`–`LOG4` (0xa0–0xa4) — P10 (observability).
- `KECCAK256` (0x20) — P2 (needs hash model or uninterpreted function).
- `EXTCODESIZE` (0x3b), `EXTCODECOPY` (0x3c), `EXTCODEHASH` (0x3f) — P11.
- `BALANCE` (0x31), `SELFBALANCE` (0x47) — P11.
- `RETURNDATACOPY` (0x3e) — P3 (return data model extension).
- `PUSH` / `COPY` with dynamic length argument — P3.

The out-of-scope lowering emits a clear signal in the annotation
sidecar so the LLM can detect it and propose a scope extension.
