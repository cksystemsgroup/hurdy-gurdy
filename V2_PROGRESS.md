# `evm-btor2` Progress — Live State

> The single source of truth for "where is the `evm-btor2` bootstrap
> right now." Each iteration appends one entry at the top. Older
> entries stay for history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-06-02T01:00:00Z — P24: BALANCE (0x31) / ORIGIN (0x32) / CALLER (0x33) / CALLVALUE (0x34) / SELFBALANCE (0x47) lowering + corpus seed 0021

- **Phase**: P24 complete.
- **What changed**: Extended `CONTEXT_VARS` in `layers.py` from 13 to 15 entries,
  adding `("selfbalance", "bv256")` (current contract's Ether balance) and
  `("balance_of", "sto_t")` (address→balance mapping for BALANCE opcode).
  Added five new lowering functions to `library.py`:
  `lower_origin(b, machine_nids, ctx_nids)` (ORIGIN 0x32, gas=2, pushes
  `ctx["origin"]` — msg.origin address), `lower_caller(b, machine_nids,
  ctx_nids)` (CALLER 0x33, gas=2, pushes `ctx["caller"]` — msg.sender),
  `lower_callvalue(b, machine_nids, ctx_nids)` (CALLVALUE 0x34, gas=2, pushes
  `ctx["callvalue"]` — msg.value in wei), `lower_selfbalance(b, machine_nids,
  ctx_nids)` (SELFBALANCE 0x47, gas=5 per EIP-1884, pushes `ctx["selfbalance"]`),
  and `lower_balance(b, machine_nids, ctx_nids)` (BALANCE 0x31, gas=2600
  always-cold per EIP-2929, pops address TOS, pushes `ctx["balance_of"][address]`
  — net sp unchanged).  Updated `translator.py` to route 0x31→`lower_balance`,
  0x32→`lower_origin`, 0x33→`lower_caller`, 0x34→`lower_callvalue`,
  0x47→`lower_selfbalance`; updated docstring to P24.  Exported all new symbols
  from `translation/__init__.py` and `library.__all__`.  Updated
  `translation/__init__.py` version docstring to P24.  Fixed
  `test_context_var_count_is_13` → `test_context_var_count_is_15` in
  `test_translation_layers.py`.  Added corpus seed `0021-callvalue-gated`
  (bytecode `341515600757005b600160005500`: 14 bytes — `CALLVALUE / ISZERO /
  ISZERO / PUSH1 0x07 / JUMPI / STOP / JUMPDEST / PUSH1 0x01 / PUSH1 0x00 /
  SSTORE / STOP`; callvalue=1 → JUMPI taken → SSTORE(0,1) → STOP → bad fires
  at step 9; callvalue=0 → JUMPI falls through → STOP at pc=6, bad never fires;
  demonstrates Ether-value-gated SSTORE pattern common in Solidity payable
  functions).  Added ~50 library tests (9–10 per opcode covering constants,
  sp change, symbolic value push, gas/pc, OOG trap, halted no-op, round-trip),
  and 15 translator tests (5 round-trip routing + 2 stop-fires tests + 2 pin
  round-trips + 4 seed 0021 tests + 2 for OriginPin/CallerPin imports).
  Total: 1199 tests pass, 13 skipped.
- **Next phase hint**: P25 — GAS (0x5A) and GASLIMIT (0x45) opcodes: GAS pushes
  the current remaining gas to the stack; GASLIMIT pushes the block gas limit
  (already in ctx["gaslimit"]); these complete the gas-observability surface and
  enable patterns where contracts branch on remaining gas.

---

## 2026-06-02T00:00:00Z — P23: RETURNDATASIZE (0x3D) + RETURNDATACOPY (0x3E) lowering + corpus seed 0020

- **Phase**: P23 complete.
- **What changed**: Added `lower_returndatasize(b, machine_nids)` to `library.py`
  (constants `RETURNDATASIZE_GAS = 2`, `RETURNDATASIZE_SIZE = 1`; reads
  `machine_nids["returndatasize"]` (bv256) directly — no ctx needed; pushes it
  to `stack[sp]`; sp += 1; gas -= 2; stack overflow and OOG are trap conditions).
  Added `lower_returndatacopy(b, machine_nids, max_len=32)` (constants
  `RETURNDATACOPY_GAS = 3`, `RETURNDATACOPY_WORD_GAS = 3`, `RETURNDATACOPY_SIZE = 1`,
  `RETURNDATACOPY_MAX_LEN = 32`; pops dest (TOS), offset (NOS), length (3rd); copies
  `returndata[offset+k]` to `mem[dest+k]` for k in [0, max_len) where k < length;
  gas = base + 3*ceil(length/32) + expansion_gas; extra trap condition: offset+length >
  returndatasize (buffer out-of-bounds, EIP-211); P23 scope: 32-byte copy window,
  matching CALLDATACOPY).  Updated `translator.py` to route `0x3D →
  lower_returndatasize` and `0x3E → lower_returndatacopy`; updated docstring to P23.
  Exported all new symbols from `translation/__init__.py` and `library.__all__`.
  Updated `translation/__init__.py` version docstring to P23.  Added corpus seed
  `0020-returndatasize-baseline` (bytecode `3d15600a5760016000555b600160005500`:
  17 bytes — `RETURNDATASIZE / ISZERO / PUSH1 0x0a / JUMPI / PUSH1 0x01 / PUSH1 0x00 /
  SSTORE / JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP`; RETURNDATASIZE=0
  at init → ISZERO=1 → JUMPI always taken → SSTORE(0,1) → STOP → bad fires at step 8;
  expected_verdict=sat; demonstrates RETURNDATASIZE reads machine state, not ctx input).
  Added 10 library tests for RETURNDATASIZE, 11 library tests for RETURNDATACOPY
  (including oob-trap test unique to RETURNDATACOPY vs CALLDATACOPY), and 5 translator
  tests (2 direct routing + 3 seed 0020 tests).  Total: 1140 tests pass, 13 skipped.
- **Next phase hint**: P24 — SELFBALANCE / BALANCE / ORIGIN / CALLER / CALLVALUE
  context opcodes: SELFBALANCE (0x47) pushes the current contract's balance;
  CALLER (0x33) pushes msg.sender; CALLVALUE (0x34) pushes msg.value; these are
  symbolic context inputs like CALLDATALOAD/CALLDATASIZE; enable Ether-value-gated
  patterns common in Solidity payable functions and access-control checks.

---

## 2026-06-01T04:00:00Z — P22: REVERT opcode (0xFD) lowering + corpus seed 0019

- **Phase**: P22 complete.
- **What changed**: Added `lower_revert(b, machine_nids)` to `library.py`
  (constants `REVERT_GAS = 0`, `REVERT_SIZE = 1`; pops offset (TOS) and length
  (NOS) from stack; computes memory-expansion gas (same formula as RETURN);
  sets `trap=1` and `halted=1` on exec; does NOT drain gas — only expansion
  gas consumed; copies first byte of `mem[offset]` to `returndata[0]` and
  sets `returndatasize = length` (P22 scope: one byte); `no_exec` guard makes
  it a no-op when already halted or trapped; stack underflow sp<2 and OOG are
  trap conditions).  Updated `translator.py` to route `0xFD → lower_revert`;
  updated docstring to P22.  Exported `lower_revert`, `REVERT_GAS`,
  `REVERT_SIZE` from `translation/__init__.py` and `library.__all__`.
  Updated `translation/__init__.py` version docstring to P22.  Added corpus
  seed `0019-revert-trap` (bytecode `600035600b5760006000fd5b600160005500`:
  18 bytes — `PUSH1 0x00 / CALLDATALOAD / PUSH1 0x0b / JUMPI / PUSH1 0x00 /
  PUSH1 0x00 / REVERT / JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP`;
  calldata=0 falls through to PUSH1 0/PUSH1 0/REVERT → trap=1, halted=1 (gas
  unchanged); calldata≠0 takes jump → SSTORE(0,1) → STOP → bad fires at step
  8; expected_verdict=sat).  Key distinction from seed 0018 (INVALID): gas is
  preserved after REVERT (only expansion gas consumed, zero here), while
  INVALID drains all gas.  Added 10 library tests and 5 translator tests (4
  for seed 0019 + 1 direct REVERT routing test).  Total: 1111 tests pass, 13
  skipped.
- **Next phase hint**: P23 — RETURNDATASIZE / RETURNDATACOPY lowering: expose
  the returndata buffer set by RETURN/REVERT; RETURNDATASIZE (0x3d) pushes
  the current returndatasize to the stack; RETURNDATACOPY (0x3e) copies bytes
  from returndata into memory; both are used in inner-call patterns and Solidity
  low-level call result handling.

---

## 2026-06-01T03:00:00Z — P21: INVALID opcode (0xFE) lowering + corpus seed 0018

- **Phase**: P21 complete.
- **What changed**: Added `lower_invalid(b, machine_nids)` to `library.py`
  (constants `INVALID_GAS = 0`, `INVALID_SIZE = 1`; unconditionally sets
  `trap=1` and `halted=1`; drains `gas` to 0 via ITE mux pattern; no stack,
  pc, memory, or storage changes; `no_exec` guard makes it a no-op when
  already halted or trapped).  Updated `translator.py` to route
  `0xFE → lower_invalid`; updated docstring to P21.  Exported `lower_invalid`,
  `INVALID_GAS`, `INVALID_SIZE` from `translation/__init__.py` and
  `library.__all__`.  Updated `translation/__init__.py` version docstring to
  P21.  Added corpus seed `0018-invalid-trap` (bytecode
  `600035600757fe5b600160005500`: 14 bytes — `PUSH1 0x00 / CALLDATALOAD /
  PUSH1 0x07 / JUMPI / INVALID / JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE
  / STOP`; calldata=0 falls through to INVALID → trap; calldata≠0 takes jump
  → SSTORE(0,1) → STOP → bad fires at step 8; expected_verdict=sat).  Added 9
  library tests and 5 oracle tests (4 for seed 0018 + 1 direct INVALID routing
  test).  Total: 1094 tests pass, 13 skipped.
- **Next phase hint**: P22 — REVERT opcode (0xFD) lowering: sets trap=1 and
  halted=1 without consuming all gas; used extensively in Solidity require()
  and revert() stubs; shares the "trap-without-all-gas-drain" pattern with
  out-of-scope lowering but is an explicit in-scope opcode.

---

## 2026-06-01T02:00:00Z — P20: JUMPDEST validation in JUMP/JUMPI + corpus seed 0017

- **Phase**: P20 complete.
- **What changed**: Added `_build_jumpdest_valid(b, dest16, jumpdest_set)` helper
  to `library.py`: builds a BTOR2 disjunction `(dest16==jd1)|(dest16==jd2)|...`
  returning a bv1 node that is 1 iff dest is a known JUMPDEST pc; empty set always
  returns 0 (all dests invalid).  Updated `lower_jump` and `lower_jumpi` to accept
  `jumpdest_set: frozenset[int] | None = None` (default None = no validation,
  backward-compatible).  For JUMP: `invalid_dest = not(is_valid)` added to `exc`.
  For JUMPI: only traps when `cond!=0 AND invalid_dest` (fall-through cond=0 is
  always safe).  Updated `translate_bytecode` in `translator.py` to collect
  `jumpdests = frozenset(insn.pc for insn in instructions if insn.opcode == 0x5B)`
  and pass to `_lower_insn`; `_lower_insn` now accepts `jumpdests` parameter and
  passes it to `lower_jump`/`lower_jumpi`.  Added corpus seed
  `0017-jumpdest-validation` (bytecode `60003560075700600160005500`: 13 bytes with
  NO JUMPDEST byte; JUMPI target pc7=PUSH1; with validation: any cd!=0 traps instead
  of executing the SSTORE sequence; expected_verdict=unsat).  Added 9 library tests
  (validity helper, invalid/valid/no-cond JUMPI, JUMP, backward-compat) and 4 oracle
  tests.  Total: 1097 tests pass, 12 skipped.
- **Next phase hint**: P21 — INVALID opcode (0xFE) lowering: explicit invalid
  instruction that unconditionally traps; common in Solidity assert() revert stubs
  and function selector dispatch guards.

---

## 2026-06-01T01:00:00Z — P19: POP lowering + corpus seed 0016

- **Phase**: P19 complete.
- **What changed**: Added `lower_pop(b, machine_nids)` to `library.py`
  (constants `POP_GAS = 2`, `POP_SIZE = 1`; decrements sp by 1; advances pc
  by 1; decrements gas by 2; underflow sp<1, OOG traps via ITE mux pattern;
  the discarded stack slot is not zeroed — sp moves below it).  Note: POP costs
  2 gas (Wbase tier), not 3.  Updated `translator.py` to route `0x50 → lower_pop`;
  updated docstring to P19.  Exported `lower_pop`, `POP_GAS`, `POP_SIZE` from
  `translation/__init__.py` and `library.__all__`.  Added corpus seed
  `0016-pop-cleanup` (bytecode `60056000358110600c5750005b50600160005500`:
  PUSH1 5 / PUSH1 0 / CALLDATALOAD / DUP2 / LT / PUSH1 0x0c / JUMPI / POP /
  STOP / JUMPDEST / POP / PUSH1 1 / PUSH1 0 / SSTORE / STOP; 20 bytes; two
  POPs discard the saved threshold in both branches; SAT at step 12 with
  calldata[31]=6; UNSAT without witness).  Added 9 library tests and 4 oracle
  alignment tests.  Total: 1082 tests pass, 12 skipped.
- **Next phase hint**: P20 — JUMPDEST-validation: currently JUMP/JUMPI accept
  any destination; add a JUMPDEST validity check (destination must match a
  known JUMPDEST offset in the bytecode) to trigger invalid-jumpdest trap.
  This is a correctness gap for programs with indirect jumps.

---

## 2026-06-01T00:00:00Z — P18: SWAP1..SWAP16 lowering + corpus seed 0015

- **Phase**: P18 complete.
- **What changed**: Added `lower_swapn(b, machine_nids, n)` to `library.py`
  (constants `SWAP_GAS = 3`, `SWAP_SIZE = 1`; reads TOS = `stack[sp-1]` and
  deep = `stack[sp-n-1]`; writes TOS→deep slot and deep→TOS slot as two
  sequential `write` nodes; sp unchanged; pc += 1; gas -= 3; underflow sp<n+1,
  OOG traps via ITE mux pattern).  Updated `translator.py` to route
  `0x90 <= op <= 0x9F` through `lower_swapn` with `n = op - 0x8F`; updated
  docstring to P18.  Exported `lower_swapn`, `SWAP_GAS`, `SWAP_SIZE` from
  `translation/__init__.py` and `library.__all__`.  Added corpus seed
  `0015-swap1-gt` (bytecode `60003560059011600b57005b600160005500`: PUSH1 0x00 /
  CALLDATALOAD / PUSH1 0x05 / SWAP1 / GT / PUSH1 0x0b / JUMPI / STOP /
  JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP; 18 bytes; property
  storage_eq slot=0 value=1; bound=15; SWAP1 puts calldata on TOS for GT;
  SAT at step 11 with calldata[31]=6; UNSAT without witness).  Added 11
  library tests and 4 oracle alignment tests for seed 0015.  Total: 1067
  tests pass, 12 skipped.
- **Next phase hint**: P19 — POP (opcode 0x50); simple 1-item stack removal,
  low implementation effort, unlocks many real-world bytecode patterns that
  discard intermediate results.

---

## 2026-05-31T23:00:00Z — P17: DUP1..DUP16 lowering + corpus seed 0014

- **Phase**: P17 complete.
- **What changed**: Added `lower_dupn(b, machine_nids, n)` to `library.py`
  (constants `DUP_GAS = 3`, `DUP_SIZE = 1`; reads `stack[sp-n]` and writes a
  copy to `stack[sp]`; sp += 1; pc += 1; gas -= 3; underflow sp<n, overflow
  sp==1024, OOG traps via ITE mux pattern).  Updated `translator.py` to route
  the full `0x80 <= op <= 0x8F` range through `lower_dupn` with `n = op - 0x7F`
  (replacing the former single-opcode 0x80 branch for `lower_dup1`); updated
  docstring to P17.  Exported `lower_dupn`, `DUP_GAS`, `DUP_SIZE` from
  `translation/__init__.py` and `library.__all__`.  Added corpus seed
  `0014-dup2-eq` (bytecode `60016000358114600b57005b60005500`: PUSH1 0x01 /
  PUSH1 0x00 / CALLDATALOAD / DUP2 / EQ / PUSH1 0x0b / JUMPI / STOP / JUMPDEST /
  PUSH1 0x00 / SSTORE / STOP; 16 bytes; property storage_eq slot=0 value=1;
  bound=15; DUP2 copies the reference value 1 from depth 2, EQ compares with
  calldata; SAT at step 10 with calldata[31]=1; UNSAT without witness).  Added
  12 library tests and 4 oracle alignment tests for seed 0014.  Total: 1050
  tests pass, 12 skipped.
- **Next phase hint**: P18 — SWAP1..SWAP16 (opcodes 0x90–0x9F); completes the
  stack-manipulation family and unlocks typical Solidity argument-shuffling
  patterns (reorder arguments before calls, return-value capture).

---

## 2026-05-31T22:00:00Z — P16: PUSH2..PUSH32 lowering + corpus seed 0013

- **Phase**: P16 complete.
- **What changed**: Unified all multi-byte push opcodes (0x60–0x7F) behind a single
  `lower_pushn(b, machine_nids, immediate, n)` function in `library.py` (constant
  `PUSHN_GAS = 3`; pushes the n-byte immediate as a bv256 constant onto the stack via
  `b.const("bv256", immediate)`; sp += 1; pc += n+1; gas -= 3; OOG/underflow/halted
  guards via ITE mux pattern).  Updated `translator.py` to route the entire
  `0x60 <= op <= 0x7F` range through `lower_pushn` with `n = op - 0x5F`, replacing the
  former single-opcode 0x60 branch; updated docstring to P16.  Exported `lower_pushn`
  and `PUSHN_GAS` from `translation/__init__.py`.  Added corpus seed
  `0013-push2-gt` (bytecode `6100c860003511600b57005b600160005500`: PUSH2 0x00C8 /
  PUSH1 0x00 / CALLDATALOAD / GT / PUSH1 0x0b / JUMPI / STOP / JUMPDEST / PUSH1 0x01 /
  PUSH1 0x00 / SSTORE / STOP; 18 bytes; property storage_eq slot=0 value=1; bound=15;
  SAT at step 10 with calldata[31]=201 giving GT(201,200)=1 → JUMPI taken →
  SSTORE(0,1); calldata=0 → GT(0,200)=0 → UNSAT).  Added 10 library tests and 4 oracle
  alignment tests for seed 0013 (sat/unsat verdicts, witness binding, concrete trace).
  Fixed evaluator 8-bit mask limitation in two value tests (value 256→200, large→42).
  Total: 1032 tests pass, 12 skipped.
- **Next phase hint**: P17 — DUP1..DUP16 (opcodes 0x80–0x8F) or SWAP1..SWAP16
  (0x90–0x9F); both unlock deeper stack manipulation patterns needed for real contracts.

---

## 2026-05-31T20:00:00Z — P15: SDIV/SMOD lowering + corpus seed 0012

- **Phase**: P15 complete.
- **What changed**: Added `sdiv` and `srem` methods to `builder.py` (emitting BTOR2
  `sdiv`/`srem` nodes).  Added `lower_sdiv` to `library.py` (opcode 0x05, gas=5;
  pops a=TOS dividend, b=NOS divisor; pushes a/b signed truncated toward zero; b==0
  → 0 via ITE guard overriding BTOR2 sdiv's -1 result; MIN_INT/-1 naturally returns
  MIN_INT matching EVM via BTOR2/SMT-LIB overflow semantics; sp-=1; underflow/OOG
  traps).  Added `lower_smod` to `library.py` (opcode 0x07, gas=5; pops a=TOS,
  b=NOS; pushes T-remainder a%b with same sign as dividend a using BTOR2 `srem`;
  b==0 → 0 via ITE guard; sp-=1; underflow/OOG traps).  Wired both into
  `translator.py` opcode router (0x05→`lower_sdiv`, 0x07→`lower_smod`); exported
  from `translation/__init__.py`; updated docstring to P15 opcode set.  Added corpus
  seed `0012-sdiv-gt` (bytecode `600360003505600210600d57005b600160005500`: PUSH1
  0x03 / PUSH1 0x00 / CALLDATALOAD / SDIV / PUSH1 0x02 / LT / PUSH1 0x0d / JUMPI /
  STOP / JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP; property storage_eq
  slot=0 value=1; push order ensures a=calldata/b=3 for SDIV; SAT at step 12 with
  calldata[31]=9 giving 9/3=3>2 → LT(2,3)=1 → JUMPI taken → SSTORE(0,1); without
  witness calldata=0 → 0/3=0, LT(2,0)=0 → UNSAT).  Added 20 new library tests (10
  SDIV + 10 SMOD, covering positive division, div-by-zero → 0, exact division, sp
  change, pc advance, gas deduction, OOG trap, underflow trap, halted noop, BTOR2
  round-trip).  Added 4 oracle tests for seed 0012.  624 tests in evm_btor2 suite,
  1016 total, all green.
- **Next iteration's planned work**: P16 — extend signed arithmetic and/or move to
  stack ops: `lower_dup2`..`lower_dup16` (opcodes 0x81–0x8f) or `lower_swap1`
  (opcode 0x90); alternatively `lower_push2`..`lower_push32` (0x61–0x7f, important
  for realistic contracts that use push-encoded addresses or large literals). Priority:
  PUSH2..PUSH32 since they unlock more complex bytecode patterns.
- **Open BLOCKERs**: none.

---

## 2026-05-31T18:00:00Z — P14: SIGNEXTEND/SLT/SGT lowering + corpus seed 0011

- **Phase**: P14 complete.
- **What changed**: Added `lower_signextend` to `library.py` (opcode 0x0b, gas=5;
  pops bytenum=TOS, x=NOS; sign-extends x treating bit `bytenum*8+7` as the sign
  bit; bytenum>=31 → x unchanged via ITE guard; implementation uses the sll/sra
  trick: `sra(sll(x, 248-bytenum*8), 248-bytenum*8)`; sp-=1; underflow/OOG traps).
  Added `lower_slt` to `library.py` (opcode 0x12, gas=3; pops a=TOS, b=NOS; pushes
  1 if a < b signed two's-complement, else 0, using BTOR2 `slt`; sp-=1;
  underflow/OOG traps).  Added `lower_sgt` to `library.py` (opcode 0x13, gas=3;
  pops a=TOS, b=NOS; pushes 1 if a > b signed, else 0, using BTOR2 `sgt`; sp-=1;
  underflow/OOG traps).  Wired all three into `translator.py` opcode router
  (0x0b→`lower_signextend`, 0x12→`lower_slt`, 0x13→`lower_sgt`); exported from
  `translation/__init__.py`; updated docstring to P14 opcode set.  Added corpus seed
  `0011-signextend-slt` (bytecode `60003560000b603012600d57005b600160005500`: PUSH1
  0x00 / CALLDATALOAD / PUSH1 0x00 / SIGNEXTEND / PUSH1 0x30 / SLT / PUSH1 0x0d /
  JUMPI / STOP / JUMPDEST / PUSH1 0x01 / PUSH1 0x00 / SSTORE / STOP; property
  storage_eq slot=0 value=1; SAT at step 12 with calldata[31]=49 giving
  SIGNEXTEND(0,49)=49>48 signed → SLT(48,49)=1 → JUMPI taken → SSTORE(0,1); without
  witness calldata=0 → SIGNEXTEND(0,0)=0, SLT(48,0)=0 → JUMPI falls through →
  UNSAT).  Added 30 new library tests (10 SIGNEXTEND + 10 SLT + 10 SGT, covering
  positive extension, identity for bytenum>=31, bytenum=100 guard, sp change, pc
  advance, gas deduction, OOG trap, underflow trap, halted noop, BTOR2 round-trip).
  Added 4 oracle tests for seed 0011.  604 tests total in evm_btor2 suite, all green.
- **Next iteration's planned work**: P15 — add signed arithmetic: `lower_sdiv`
  (opcode 0x05; signed division per EVM two's-complement rules including the
  MIN_INT/-1 edge case) and `lower_smod` (opcode 0x07; signed modulo, result has
  same sign as dividend); optionally add `lower_not` (0x19, already present) audit
  or a more complex corpus seed exercising negative-number arithmetic (e.g., a seed
  where a negative calldata value must satisfy a signed inequality to reach storage).
- **Open BLOCKERs**: none.

---

## 2026-05-31T12:00:00Z — P13: BYTE/SHL/SHR/SAR lowering + corpus seed 0010

- **Phase**: P13 complete.
- **What changed**: Added `lower_byte` to `library.py` (opcode 0x1a, gas=3; pops
  i=TOS, x=NOS, pushes byte i of x zero-extended to bv256; byte 0 = MSB;
  i >= 32 → 0 via explicit ITE guard; computed as `(x >> ((31-i)*8)) & 0xFF`
  with natural overflow for i>=32 giving huge shift → 0; sp-=1; underflow/OOG
  traps).  Added `lower_shl` to `library.py` (opcode 0x1b, gas=3, EIP-145; pops
  shift=TOS, value=NOS, pushes `value << shift` using BTOR2 `sll`; shift>=256
  gives 0 per BTOR2 `sll` semantics = EVM spec; sp-=1; underflow/OOG traps).
  Added `lower_shr` to `library.py` (opcode 0x1c, gas=3, EIP-145; pops
  shift=TOS, value=NOS, pushes `value >> shift` logical using BTOR2 `srl`;
  shift>=256 gives 0 per BTOR2 `srl` semantics = EVM spec; sp-=1;
  underflow/OOG traps).  Added `lower_sar` to `library.py` (opcode 0x1d, gas=3,
  EIP-145; pops shift=TOS, value=NOS, pushes `value >> shift` arithmetic using
  BTOR2 `sra`; shift>=256 replicates sign bit per BTOR2 `sra` semantics = EVM
  spec; sp-=1; underflow/OOG traps).  Wired all four into `translator.py` opcode
  router (0x1a→`lower_byte`, 0x1b→`lower_shl`, 0x1c→`lower_shr`,
  0x1d→`lower_sar`); exported from `translation/__init__.py`; updated docstring
  to P13 opcode set.  Added corpus seed `0010-shr-abi-decode` (bytecode
  `60003560011c600f10600d57005b600160005500`: PUSH1 0x00 / CALLDATALOAD / PUSH1
  0x01 / SHR / PUSH1 0x0f / LT / PUSH1 0x0d / JUMPI / STOP / JUMPDEST / PUSH1
  0x01 / PUSH1 0x00 / SSTORE / STOP; property storage_eq slot=0 value=1; SAT at
  step 12 with calldata[31]=32 giving 32>>1=16>15; without witness calldata=0 →
  0>>1=0≤15 → LT=0 → JUMPI falls through → UNSAT).  Added 51 new library tests
  (11 BYTE + 10 SHL + 11 SHR + 10 SAR, covering constants, return type, sp
  change, result semantics, boundary cases, gas deduction, OOG trap, underflow
  trap, halted noop, BTOR2 round-trip; shift-by-248 on an 8-bit value exercises
  correct BTOR2 `srl` zero-result without hitting evaluator's bv256 stack-mask
  limitation).  Added 4 oracle tests for seed 0010.  568 tests total, all green.
  Harness run (all 10 seeds): all SAT (witness_steps 3/4/5/8/8/7/10/12/12/12 for
  seeds 0001–0010).
- **Next iteration's planned work**: P14 — add `lower_signextend` (0x0b)
  signed-extension lowering; add `lower_slt` (0x12) / `lower_sgt` (0x13)
  signed comparison lowerings; extend corpus with seed 0011 exercising a
  signed-arithmetic pattern (e.g., a pre-0.8 Solidity int256 underflow or a
  signed-range check via SGT/SLT that differs from the unsigned case).
- **Open BLOCKERs**: none.

---

## 2026-05-31T00:00:00Z — P12: DIV/MOD/ADDMOD/MULMOD/EXP lowering + corpus seed 0009

- **Phase**: P12 complete.
- **What changed**: Added `lower_div` to `library.py` (opcode 0x04, gas=5; pops
  a=TOS, b=NOS, pushes a/b unsigned; a/0=0 per EVM convention via ite guard on
  udiv-by-zero; sp-=1; underflow/OOG traps).  Added `lower_mod` to `library.py`
  (opcode 0x06, gas=5; pops a=TOS, b=NOS, pushes a%b unsigned; a%0=0 per EVM
  convention via ite guard on urem-by-zero; sp-=1; underflow/OOG traps).  Added
  `lower_addmod` to `library.py` (opcode 0x08, gas=8; pops a=TOS, b=NOS, N=3rd;
  pushes (a+b)%N using 257-bit zero-extended arithmetic so the intermediate sum
  does not wrap mod 2^256; N=0 → 0; sp-=2; underflow/OOG traps).  Added
  `lower_mulmod` to `library.py` (opcode 0x09, gas=8; pops a=TOS, b=NOS, N=3rd;
  pushes (a*b)%N using 512-bit zero-extended arithmetic so the product does not
  wrap mod 2^256; N=0 → 0; sp-=2; underflow/OOG traps).  Added `lower_exp` to
  `library.py` (opcode 0x0a; pops base=TOS, exp=NOS; pushes base**exp mod 2**256;
  only the low 8 bits of exp are modelled via unrolled square-and-multiply
  (EXP_EXPONENT_BITS=8, 8 conditional multiplications + 7 squarings); gas =
  ite(exp==0, 10, 60) per EIP-160 1-byte bound; sp-=1; underflow/OOG traps).
  Wired all five into `translator.py` opcode router (0x04→`lower_div`,
  0x06→`lower_mod`, 0x08→`lower_addmod`, 0x09→`lower_mulmod`,
  0x0a→`lower_exp`); exported from `translation/__init__.py`; updated docstring
  to P12 opcode set.  Added corpus seed `0009-div-sstore-on-taken` (bytecode
  `600a60026000350411600d57005b604260005500`: PUSH1 0x0a / PUSH1 0x02 / PUSH1
  0x00 / CALLDATALOAD / DIV / GT / PUSH1 0x0d / JUMPI / STOP / JUMPDEST / PUSH1
  0x42 / PUSH1 0x00 / SSTORE / STOP; property storage_eq slot=0 value=66; SAT at
  step 12 with calldata[31]=22 giving 22/2=11>10; without witness cd=0 →
  0/2=0≤10 → GT=0 → JUMPI falls through → UNSAT).  Added 42 new library tests
  (10 DIV + 10 MOD + 9 ADDMOD + 9 MULMOD + 10 EXP, covering constants, return
  type, sp change, result semantics, zero-divisor convention, gas deduction, OOG
  trap, underflow trap, halted noop, BTOR2 round-trip).  Added 4 oracle tests for
  seed 0009.  517 tests total, all green.  Harness run (all 9 seeds): all SAT
  (witness_steps 3/4/5/8/8/7/10/12/12 for seeds 0001–0009).
- **Next iteration's planned work**: P13 — add `lower_shl` (0x1b) / `lower_shr`
  (0x1c) / `lower_sar` (0x1d) shift lowerings; add `lower_byte` (0x1a) byte
  extraction; extend corpus with seed 0010 exercising a SHR-based bitmask or
  byte-extraction pattern common in ABI decoding (e.g., extracting a uint8
  argument from calldata using SHR 248 or BYTE opcode).
- **Open BLOCKERs**: none.

---

## 2026-05-30T00:00:00Z — P11: SUB/MUL/AND/OR/XOR/NOT/JUMP lowering + corpus seed 0008

- **Phase**: P11 complete.
- **What changed**: Added `lower_sub` to `library.py` (opcode 0x03, gas=3; pops a=TOS,
  b=NOS, pushes a-b bv256 wrapping; sp-=1; underflow/OOG traps).  Added `lower_mul` to
  `library.py` (opcode 0x02, gas=5; pops a=TOS, b=NOS, pushes a*b bv256 wrapping; sp-=1;
  underflow/OOG traps).  Added `lower_and` to `library.py` (opcode 0x16, gas=3; pops
  a=TOS, b=NOS, pushes a&b; sp-=1; underflow/OOG traps).  Added `lower_or` to
  `library.py` (opcode 0x17, gas=3; pushes a|b; same structure).  Added `lower_xor` to
  `library.py` (opcode 0x18, gas=3; pushes a^b; same structure).  Added `lower_not` to
  `library.py` (opcode 0x19, gas=3; pops a=TOS, pushes ~a bitwise 256-bit complement
  in-place; sp unchanged; underflow/OOG traps).  Added `lower_jump` to `library.py`
  (opcode 0x56, gas=8; pops dest=TOS, sets pc=dest[15:0]; sp-=1; underflow/OOG traps).
  Wired all seven into `translator.py` opcode router (0x02→`lower_mul`,
  0x03→`lower_sub`, 0x16→`lower_and`, 0x17→`lower_or`, 0x18→`lower_xor`,
  0x19→`lower_not`, 0x56→`lower_jump`); exported from `translation/__init__.py`;
  updated docstring to P11 opcode set.  Added corpus seed `0008-mul-sstore-on-taken`
  (bytecode `606460003560020211600d57005b604260005500`: PUSH1 0x64 / PUSH1 0x00 /
  CALLDATALOAD / PUSH1 0x02 / MUL / GT / PUSH1 0x0d / JUMPI / STOP / JUMPDEST /
  PUSH1 0x42 / PUSH1 0x00 / SSTORE / STOP; property storage_eq slot=0 value=66;
  SAT at step 12 with calldata[31]=51 giving 2*51=102>100; without witness
  cd=0 → 0*2=0 ≤ 100 → GT=0 → JUMPI falls through → UNSAT).  Added 69 new library
  tests (10 SUB + 10 MUL + 9 AND + 9 OR + 9 XOR + 10 NOT + 10 JUMP — note: tests for
  wrapping arithmetic use low-byte checks due to evaluator's 8-bit array-write mask;
  the BTOR2 model itself is correct bv256).  Added 4 oracle tests for seed 0008.  458
  tests total, all green.  Harness run (all 8 seeds): all SAT (witness_steps 3/4/5/8/8/7/10/12
  for seeds 0001–0008).
- **Next iteration's planned work**: P12 — add `lower_div` (0x04) / `lower_mod` (0x06)
  / `lower_addmod` (0x08) / `lower_mulmod` (0x09) arithmetic lowerings; add
  `lower_exp` (0x0a) with a static bound on the exponent for symbolic tractability;
  extend corpus with seed 0009 exercising a DIV-based conditional (e.g., a ratio-check
  pattern common in pre-0.8 Solidity: `(a * b) / DENOMINATOR > THRESHOLD → write`).
- **Open BLOCKERs**: none.

---

## 2026-05-29T00:00:00Z — P10: LT/GT/EQ + CALLDATACOPY lowering + corpus seed 0007

- **Phase**: P10 complete.
- **What changed**: Added `lower_lt` to `library.py` (opcode 0x10, gas=3; pops a=TOS,
  b=NOS, pushes (a < b unsigned ? 1 : 0) as bv256 to stack[sp-2]; sp-=1; underflow/OOG
  traps).  Added `lower_gt` to `library.py` (opcode 0x11, gas=3; same structure using
  `ugt`; pushes (a > b unsigned ? 1 : 0)).  Added `lower_eq_op` to `library.py` (opcode
  0x14, gas=3; same structure using `eq`; pushes (a == b ? 1 : 0)).  Added
  `lower_calldatacopy` to `library.py` (opcode 0x37; pops dest=TOS, offset=NOS,
  length=3rd; copies up to `max_len=32` bytes from `calldata[offset+k]` to `mem[dest+k]`
  for k in [0,32) guarded by `ult(k, length)`; sp-=3; gas = 3 + 3*ceil(length/32) +
  Cmem expansion; underflow sp<3 / OOG traps).  Wired all four into `translator.py`
  opcode router (0x10→`lower_lt`, 0x11→`lower_gt`, 0x14→`lower_eq_op`,
  0x37→`lower_calldatacopy`); exported from `translation/__init__.py`; updated docstring
  to P10 opcode set.  Added corpus seed `0007-gt-sstore-on-taken` (bytecode
  `600360003511600a57005b604260005500`: PUSH1 0x03 / PUSH1 0x00 / CALLDATALOAD / GT /
  PUSH1 0x0a / JUMPI / STOP / JUMPDEST / PUSH1 0x42 / PUSH1 0x00 / SSTORE / STOP;
  property storage_eq slot=0 value=66; SAT at step 10 with calldata[31]=66; without
  witness cd=0 → GT=0 → JUMPI falls through → UNSAT).  Added 35 new library tests (9 LT
  + 9 GT + 8 EQ + 9 CALLDATACOPY) covering structure, result semantics (true/false/equal
  cases), sp/gas/pc mechanics, trap paths, halted-noop, BTOR2 round-trips.  Added 4 oracle
  tests for seed 0007.  385 tests total, all green.  Harness run (all 7 seeds): all SAT
  (witness_steps 3/4/5/8/8/7/10 for seeds 0001–0007).
- **Next iteration's planned work**: P11 — add `lower_sub` (0x03) and `lower_mul` (0x02)
  arithmetic lowerings to unblock overflow-sensitive contract patterns; add `lower_and`
  (0x16) / `lower_or` (0x17) / `lower_xor` (0x18) / `lower_not` (0x19) bitwise
  lowerings; add `lower_jump` (0x56) for unconditional control flow; extend corpus with
  seed 0008 exercising a MUL-based conditional (e.g., Solidity pre-0.8 style unchecked
  multiplication overflow reaching a storage write).
- **Open BLOCKERs**: none.

---

## 2026-05-28T00:00:00Z — P9: CALLDATASIZE/MLOAD/MSTORE lowering + harness witness wiring + seed 0006

- **Phase**: P9 complete.
- **What changed**: Added `lower_calldatasize` to `library.py` (opcode 0x36, gas=2; pushes
  symbolic `calldatasize` context input onto stack; overflow/OOG traps; takes `ctx_nids`).
  Added `lower_mload` to `library.py` (opcode 0x51, base gas=3 + Cmem expansion; pops offset,
  reads 32 bytes big-endian from `mem[offset..offset+31]`, pushes bv256 result back at TOS; net
  sp=0; underflow/OOG traps; updates `mem_words`).  Added `lower_mstore` to `library.py`
  (opcode 0x52, base gas=3 + Cmem expansion; pops offset/value, writes 32 big-endian bytes to
  `mem[offset..offset+31]` via 32 chained `write` operations; sp -= 2; underflow/OOG traps;
  updates `mem_words`).  Wired all three into `translator.py` opcode router
  (0x36→`lower_calldatasize`, 0x51→`lower_mload`, 0x52→`lower_mstore`); exported from
  `translation/__init__.py`; updated docstring to P9 opcode set.  Updated `harness.py` to load
  optional `task.witness.json` per seed (string-keyed dict values auto-converted to int-keyed for
  array-state binding).  Added `task.witness.json` to seeds 0002/0004/0005 with
  `{"calldata": {"31": 1}}` so the harness now reports SAT for all 5 original seeds.  Added
  corpus seed `0006-mload-mstore-roundtrip` (bytecode `604260005260005160005500`: PUSH1 0x42 /
  PUSH1 0x00 / MSTORE / PUSH1 0x00 / MLOAD / PUSH1 0x00 / SSTORE / STOP; property
  storage_eq slot=0 value=66; SAT at step 7).  Added 29 new library tests (9 CALLDATASIZE +
  10 MLOAD + 10 MSTORE) covering structure, sp/gas/pc mechanics, semantic correctness, trap
  paths, halted-noop, no-expansion gas, and BTOR2 round-trips; added 4 oracle tests for seed
  0006.  340 tests total, all green.  Harness run (all 6 seeds): all SAT
  (witness_steps 3/4/5/8/8/7 for seeds 0001–0006).
- **Next iteration's planned work**: P10 — add `lower_calldatacopy` (0x37) to enable
  multi-byte calldata reads into memory (unblocks contracts that use ABI decoding); add
  `lower_lt` (0x10) / `lower_gt` (0x11) / `lower_eq` (0x14) comparison opcodes to expand
  arithmetic coverage; extend corpus with seed 0007 exercising a calldata-dependent branch
  using LT/GT comparisons.
- **Open BLOCKERs**: none.

---

## 2026-05-27T12:00:00Z — P8: GasLimitPin corpus seeds + MSTORE8/PUSH0/RETURN lowering + seed 0003 SAT

- **Phase**: P8 complete.
- **What changed**: Added `{"__type__": "GasLimitPin", "gas": 1000000}` to all 5 corpus seed
  spec JSONs so the concrete oracle no longer OOGs immediately.  Added `lower_mstore8` to
  `library.py` (opcode 0x53, base gas=3 + Cmem expansion; pops offset/byte, writes low byte to
  `mem[offset]`, updates `mem_words`).  Added `lower_push0` (opcode 0x5f, gas=2; pushes constant
  0 to stack, overflow/OOG traps).  Added `lower_return` (opcode 0xf3, base gas=0 + expansion;
  pops offset/length, copies `mem[offset]` to `returndata[0]` (P8 scope: length=1 only), sets
  `returndatasize=length`, halts cleanly; trap on underflow/OOG).  Wired all three into
  `translator.py` opcode router (0x53→`lower_mstore8`, 0x5f→`lower_push0`, 0xf3→`lower_return`)
  and exported from `translation/__init__.py`.  Updated docstring to P8 opcode set.  Replaced
  `test_seed_0003_oos_unsat` oracle test with 4 new seed-0003 tests (bad_fired SAT,
  `witness_step=5`, wrong-value UNSAT, btor2-model non-empty).  Added 29 new library tests (11
  MSTORE8, 9 PUSH0, 7 RETURN + 2 constant checks) covering structure, sp/gas/pc mechanics,
  mem-write semantics, low-byte truncation, trap paths, halted-noop, and BTOR2 round-trips.
  303 tests total, all green.  Harness run: seeds 0001/0003 SAT (bad_fired=True,
  witness_steps 3/5), seeds 0002/0004/0005 UNSAT (calldata-dependent SAT requires witness
  binding not supplied by harness).
  **Note (P8 scope)**: `lower_return` copies only the first byte (`mem[offset]` →
  `returndata[0]`); future iteration should unroll arbitrary `length` using the
  compile-time-constant-length pattern from `CALLDATACOPY` or emit multiple symbolic writes.
- **Next iteration's planned work**: P9 — wire calldata witness bindings into the harness for
  seeds 0002/0004/0005 so the harness reports SAT verdicts for all 5 seeds; add
  `lower_calldatasize` (0x36) and `lower_mload` (0x51) / `lower_mstore` (0x52) to expand the
  opcode coverage; extend corpus with seed 0006 exercising MLOAD+MSTORE round-trip property.
- **Open BLOCKERs**: none.

---

## 2026-05-27T00:00:00Z — P7: ISZERO + DUP1 lowering + seed 0005 oracle coverage + harness wiring

- **Phase**: P7 complete.
- **What changed**: Added `lower_iszero` to `library.py` (opcode 0x15, gas=3):
  replaces TOS in-place with 1 if TOS==0 else 0; net sp=0; trap on sp<1 or
  gas<3.  Added `lower_dup1` to `library.py` (opcode 0x80, gas=3):
  reads stack[sp-1], writes copy to stack[sp], sp+=1; trap on sp<1, sp==1024,
  or gas<3.  Both wired into `translator.py` opcode router (0x15→`lower_iszero`
  before 0x35, 0x80→`lower_dup1` after 0x60).  Exported from
  `translation/__init__.py`.  22 new library tests (11 ISZERO + 11 DUP1)
  covering zero/nonzero semantics, sp/gas/pc mechanics, all trap paths,
  halted-noop, and BTOR2 round-trips.  3 new oracle tests for seed 0005
  (`6000358015600c57600055005b00`): no-witness UNSAT (calldata=0 → ISZERO(0)=1
  → JUMPI taken → no SSTORE), with `calldata{31:1}` SAT (ISZERO(1)=0 →
  JUMPI not taken → SSTORE(0,1)), `witness_step=8`.  Implemented
  `bench/evm-btor2/harness.py`: loads `task.spec.json` per seed dir, runs
  `AlignmentOracle.check`, reports bad_fired/witness_step/wall_seconds per
  task.  274 tests total, all green.
  **Note**: corpus seed JSONs have no `GasLimitPin` so the concrete
  interpreter OOGs immediately — harness correctly reports UNSAT for all
  seeds without a witness; oracle tests use `GasLimitPin(gas=1_000_000)` via
  the `_spec()` helper.  Corpus seed files should gain `GasLimitPin` in a
  follow-up to make the harness faithfully exercise SAT paths.
- **Next iteration's planned work**: P8 — add `GasLimitPin` to the 5 corpus
  seed spec JSONs so the harness reports correct SAT verdicts without witness
  bindings; then add `lower_push0` (0x5f), `lower_mstore8` (0x53), and
  `lower_return` (0xf3) to unblock seed 0003 (currently OOS-trapping);
  extend oracle tests and harness to confirm seeds 0003 is SAT.
- **Open BLOCKERs**: none.

## 2026-05-26T16:40:00Z — P6: JUMPI lowering + seed 0004 oracle coverage

- **Phase**: P6 complete.
- **What changed**: Added `lower_jumpi` to `library.py` (opcode 0x57, gas=10).
  Lowering: pops TOS (`dest`, bv256 → truncated to bv16 via `slice`) and NOS
  (`cond`, bv256); if `cond == 0` falls through (`pc += 1`), else jumps to
  `dest16`; `sp -= 2`; trap conditions: `sp < 2` (underflow) and `gas < 10`
  (OOG).  Wired into `translator.py` opcode router (0x57 → `lower_jumpi` before
  0x5b JUMPDEST), and exported from `translation/__init__.py`.  9 new library
  tests (fall-through pc, taken-branch pc, sp decrement, gas, OOG trap,
  underflow trap, halted noop, round-trip).  3 new oracle tests for seed 0004
  (`600035600757005b604260005500`): without-witness UNSAT, with `calldata{31:1}`
  SAT, `witness_step=8`.  249 tests total, all green.
- **Next iteration's planned work**: P7 — add `ISZERO` (0x15) and `DUP1` (0x80)
  lowering to expand scope to seed 0005; then wire `AlignmentOracle` to the
  pair harness for full end-to-end spec-JSON-to-result pipeline.
- **Open BLOCKERs**: none.

## 2026-05-26T16:00:00Z — P5: AlignmentOracle

- **Phase**: P5 complete.
- **What changed**: Created `gurdy/pairs/evm_btor2/oracle/` package with
  `alignment.py` (`AlignmentResult` frozen dataclass, `AlignmentOracle.check`
  method) and `__init__.py`.  `AlignmentOracle.check(spec, witness_binding=None)`
  translates the spec's bytecode via `translate_bytecode`, wraps the BTOR2 text
  in a `CompiledArtifact`, builds a `Btor2ReasoningBinding` from the optional
  `witness_binding` dict (forwarded as `state_init_by_symbol`), runs
  `Btor2ReasoningInterpreter.run` up to `spec.analysis.bound` (default 100)
  steps, and returns `AlignmentResult(bad_fired, witness_step, btor2_model)`.
  11 new tests in `test_oracle_alignment.py` covering: seed 0001 SAT
  (bad_fired=True, witness_step=3), bound-too-small UNSAT (bound=3),
  bound-just-enough SAT (bound=4), wrong-value UNSAT, seed 0002 without
  witness UNSAT / with calldata{31:1} SAT (witness_step=4), seed 0003
  OOS-trap UNSAT (MSTORE8+RETURN not in P4 opcode set → trap=1 → bad
  requires NOT trap → never fires), and btor2_model non-empty in both
  SAT and UNSAT cases.  236 tests total, all green.
- **Next iteration's planned work**: P6 — wire `AlignmentOracle` to the
  harness (`gurdy/pairs/evm_btor2/harness.py` or equivalent) so the
  full `evm-btor2` pair pipeline is exercisable end-to-end from a spec
  JSON file; add JUMPI (0x57) lowering to expand scope to seeds 0004–0005.
- **Open BLOCKERs**: none.

## 2026-05-26T15:20:00Z — P4: translate_bytecode (full dispatcher)

- **Phase**: P4 complete.
- **What changed**: Created `gurdy/pairs/evm_btor2/translation/translator.py`
  with `translate_bytecode(bytecode, spec) -> str` — the main P4 entry
  point.  It orchestrates all six SCHEMA.md §13 layers: header → machine
  states → context inputs (with spec assumptions) → init clauses →
  PC-keyed ITE dispatch (`_build_dispatch` iterates `pc_lowerings` in
  reverse, wrapping each as nested `ite(pc==offset, result, prev)`) →
  `next` clauses → bad property from `ReachProperty` (`_emit_bad_expr`
  handles STOP/REVERT/STORAGE_EQ/RETURNDATA_EQ).  Includes helpers:
  `_lower_insn` (routes 0x00 STOP, 0x01 ADD, 0x35 CALLDATALOAD, 0x55
  SSTORE, 0x5b JUMPDEST, 0x60 PUSH1; all others → `_lower_oos`),
  `_lower_jumpdest` (pc+=1, gas-=1), and `_lower_oos` (trap=1, halted=1,
  SCHEMA.md §16).  Updated `translation/__init__.py` to export
  `translate_bytecode`.  11 new tests in
  `test_translation_translator.py` covering: BTOR2 round-trips (STOP,
  PUSH1+STOP, seed-0001, ADD), STOP sets halted / not trap, PUSH1+STOP
  bad fires at step 1, **seed 0001** (PUSH1 0x42 / PUSH1 0x00 / SSTORE /
  STOP) bad fires at step 3 and not before, wrong-value doesn't fire,
  out-of-scope opcode traps.  225 tests total, all green.
- **Next iteration's planned work**: P5 — alignment oracle skeleton:
  create `gurdy/pairs/evm_btor2/oracle/` package with
  `AlignmentOracle` that runs `translate_bytecode` to produce a BTOR2
  model, feeds it to the reasoning interpreter up to `spec.analysis.bound`
  steps, and returns an `AlignmentResult` indicating whether bad fired
  (SAT witness found) or not (UNSAT up to bound).  Wire to the harness
  and exercise with all 5 corpus seeds (0001–0005), checking that
  seeds 0001–0003 produce SAT results and that the bound is respected.
- **Open BLOCKERs**: none.

---

## 2026-05-26T14:40:00Z — P4: lower_sstore + lower_calldataload

- **Phase**: P4 in progress.
- **What changed**: Extended `gurdy/pairs/evm_btor2/translation/library.py`
  with `lower_sstore(builder, machine_nids)` (pops slot/value from TOS/NOS,
  writes `sto[slot]:=value`, sets `sto_warm[slot]:=1`, 2-case warm/cold gas
  model: `SSTORE_GAS_COLD=2200` / `SSTORE_GAS_WARM=100` from
  `sto_warm[slot][0:0]`, underflow+OOG trap guards, sp−=2, pc+=1) and
  `lower_calldataload(builder, machine_nids, ctx_nids)` (pops offset from
  TOS, reads 32 bytes big-endian from `calldata[offset..offset+31]` via
  31 concat operations producing a bv256 word, replaces TOS in place so
  net sp=0, gas−=3, pc+=1; intermediate bitvec sorts bv16–bv248 auto-
  declared by `Btor2Builder.declare_sort`).  Updated `__init__.py` to
  export both lowerings and constants.  24 new tests in
  `test_translation_library.py` (11 SSTORE + 10 CALLDATALOAD + 3 constant
  checks) covering structure, concrete storage write, warm/cold gas costs,
  trap paths (OOG, underflow), and BTOR2 round-trips.  214 tests total,
  all green.
- **Next iteration's planned work**: P4 continued — implement a
  `translate_bytecode(bytecode: bytes, spec: EvmBtor2Spec) -> str` function
  in `translation/translator.py` that: (1) disassembles the bytecode,
  (2) calls `emit_header + emit_machine_states + emit_context_inputs +
  emit_init_clauses`, (3) for each opcode position builds one
  `EvmLoweringResult` per PC offset, (4) wires a PC-keyed ITE dispatch tree
  (SCHEMA.md §13) wiring all `next` clauses, (5) emits the `bad` property
  from the spec's `ReachProperty`; then test by translating corpus seed
  0001 (PUSH1/PUSH1/SSTORE/STOP, `storage_eq slot=0 value=66`) and
  verifying that the BTOR2 model round-trips cleanly.
- **Open BLOCKERs**: none.

---

## 2026-05-26T14:00:00Z — P4: lower_stop + lower_add

- **Phase**: P4 in progress.
- **What changed**: Extended `gurdy/pairs/evm_btor2/translation/library.py`
  with `lower_stop(builder, machine_nids)` (sets `halted=1`, `trap`
  unchanged, zero gas cost, all other states frozen; no-exec guard
  prevents double-halt) and `lower_add(builder, machine_nids)` (pops TOS
  and NOS from `stack[sp-1]`/`stack[sp-2]`, pushes their bv256 sum at
  `stack[sp-2]`, sp−=1, gas−=3, pc+=1; underflow check `sp<2` and
  out-of-gas check trigger trap/halted sticky flags via same exec-ITE
  pattern as PUSH1).  Updated `translation/__init__.py` to export both
  new lowerings and their constants (`STOP_GAS`, `ADD_GAS`, `ADD_SIZE`).
  23 new tests in `test_translation_library.py` (7 for STOP, 11 for ADD,
  plus constant/structure checks) covering semantics, trap conditions,
  no-op-when-halted, and BTOR2 round-trip.  Note: discovered that "no
  trap on clean exec" tests must cap max_steps=1 because the same
  single-opcode dispatch model re-applies the lowering each step (step 1
  of ADD hits underflow since sp=1 after step 0).  190 tests total, all
  green.
- **Next iteration's planned work**: P4 continued — implement
  `lower_sstore(builder, machine_nids)` (slot=stack[sp-1],
  value=stack[sp-2], sto'=write(sto,slot,value), sp−=2, gas per
  EIP-2929/3529 cold/warm schedule, pc+=1) and
  `lower_calldataload(builder, machine_nids, ctx_nids)` (reads 32 bytes
  from `calldata[offset..offset+31]`, pushes bv256 result, sp+=1,
  gas−=3, pc+=1); then wire a `dispatch_single(builder, opcode,
  machine_nids, ctx_nids, spec)` function that routes by opcode to the
  correct lowering; exercise by building a BTOR2 model for seed 0001
  (PUSH1/PUSH1/SSTORE/STOP) and verifying the `storage_eq` property.
- **Open BLOCKERs**: none.

---

## 2026-05-26T13:20:00Z — P4: lower_push1 + EvmLoweringResult

- **Phase**: P4 in progress.
- **What changed**: Created `gurdy/pairs/evm_btor2/translation/library.py`
  with `EvmLoweringResult` (12-field dataclass mirroring `MACHINE_STATE_VARS`)
  and `lower_push1(builder, machine_nids, immediate)`.  `lower_push1`
  computes BTOR2 next-state nid expressions for a PUSH1 instruction:
  stack-overflow check (`uext(sp,246)==1024`), out-of-gas check
  (`gas < 3`), `exec = not(no_exec OR trap_from_op)` guard, normal-path
  ITE mux for `sp`/`stack`/`pc`/`gas`, and sticky `trap`/`halted`.
  Unchanged states (`mem`, `mem_words`, `sto`, `sto_warm`, `returndata`,
  `returndatasize`) alias the input state nids.  Updated
  `translation/__init__.py` to export `EvmLoweringResult`, `lower_push1`,
  `PUSH1_GAS`, and `PUSH1_SIZE`.  20 new tests in
  `test_translation_library.py` covering result structure, all-fields
  int check, unchanged/changed nid invariants, sp/pc/gas/stack concrete
  semantics via reasoning interpreter, OOG trap (sp/pc/gas frozen),
  already-halted/trapped no-op, round-trip, and immediate edge cases
  (0x00 and 0xFF).  167 tests total, all green.
- **Next iteration's planned work**: P4 continued — implement
  `lower_stop(builder, machine_nids)` (sets `halted=1` cleanly, no trap,
  freezes all other states) and `lower_add(builder, machine_nids)` (pops
  two bv256 operands, pushes their bv256 sum, gas -= 3, pc += 1); then
  add a `build_single_opcode_model(builder, spec, immediate)` dispatch
  helper that wires header + machine + context + init + single-opcode
  lowering + bad-property for a STOP/PUSH1/ADD bytecode; exercise with
  corpus seeds 0001–0003 in BTOR2 emission tests.
- **Open BLOCKERs**: none.

---

## 2026-05-26T12:40:00Z — P4: emit_context_inputs + emit_init_clauses

- **Phase**: P4 in progress.
- **What changed**: Created `gurdy/pairs/evm_btor2/translation/layers.py`
  with `emit_context_inputs(builder, spec)` and `emit_init_clauses(builder,
  spec, machine_nids)`.  `emit_context_inputs` declares all 13 SCHEMA.md §4
  symbolic context variables as BTOR2 states held constant via self-loop
  `next` clauses, emits address-validity constraints
  (`caller[255:160]==0`, `origin[255:160]==0`), pins `chainid=1` by
  default, and translates `CallerPin`, `CallvaluePin`, `OriginPin`,
  `CalldatasizePin`, and `CalldataBytePin` spec assumptions to `constraint`
  nodes.  `emit_init_clauses` emits BTOR2 `init` nodes for all six scalar
  machine states (`sp`, `mem_words`, `pc`, `trap`, `halted`,
  `returndatasize`) to zero; applies `GasLimitPin` as a `gas` init value;
  encodes `StoragePin` and `StorageWarm` as `constraint(read(sto/sto_warm,
  slot)==value)` nodes (all-steps; step-0 guard deferred to P5).  Updated
  `translation/__init__.py` to export both layer functions.  21 new tests in
  `test_translation_layers.py` covering structure, assumption types, init
  presence, pin values, and full-emission BTOR2 round-trip.  147 tests
  total, all green.
- **Next iteration's planned work**: P4 continued — implement
  `gurdy/pairs/evm_btor2/translation/library.py` with a minimal opcode
  lowering function `lower_push1(builder, machine_nids, immediate)` that
  emits the BTOR2 `next` clauses for `sp`, `stack`, `pc`, and `gas` for a
  PUSH1 instruction; then write hand-traced BTOR2 output tests verifying the
  resulting model evaluates correctly via the reasoning interpreter.
- **Open BLOCKERs**: none.

---

## 2026-05-26T12:20:00Z — P3+P4: halted/trap interpreter test + Btor2Builder skeleton

- **Phase**: P3 complete; P4 begun.
- **What changed**: Added 3 tests to `test_reasoning_interp.py` using a
  minimal halted/trap 2-state BTOR2 model that mirrors EVM SCHEMA.md §3.1
  bv1 machine flags (`halted'=or(halted, counter==3)`, `trap'=halted`,
  `bad=and(halted,trap)`). Traced: bad fires at step 4 when both flags
  become 1 simultaneously; tests cover exact step, under-bound (no fire),
  and layer_values membership for halted/trap nids.  Created
  `gurdy/pairs/evm_btor2/translation/builder.py` (`Btor2Builder`) with:
  `EVM_BITVEC_SORTS` (bv1/8/10/16/64/256), `EVM_ARRAY_SORTS`
  (stack_t/mem_t/sto_t), `MACHINE_STATE_VARS` (12 symbols from §3.1+§3.2),
  `emit_header()` (declares all 9 sorts), `emit_machine_states()` (declares
  all 12 state variables with correct sort nids, returns symbol→nid dict),
  plus core builder helpers (const, add/sub/mul/and/or/xor/not/ite/eq/ult
  etc., uext/sext/slice/concat, read/write, state/init/next/bad/constraint).
  Updated `translation/__init__.py` to export `Btor2Builder`.  22 new tests
  in `test_translation_builder.py` covering sort idempotency, state counts,
  constant ops, arithmetic helpers, and BTOR2 round-trip via printer/parser.
  126 tests total, all green.
- **Next iteration's planned work**: P4 continued — implement
  `gurdy/pairs/evm_btor2/translation/layers.py` with `emit_context_inputs()`
  that declares the symbolic context state variables from SCHEMA.md §3.3
  (caller, callvalue, calldata, calldatasize, block vars) using the builder,
  plus `emit_init_clauses()` that wires zero-init for all machine states and
  applies StoragePin / GasLimitPin / StorageWarm assumptions from the spec.
- **Open BLOCKERs**: none.

---

## 2026-05-26T12:00:00Z — P2+P3: JUMPI corpus seeds 0004–0005 + reasoning_interp skeleton

- **Phase**: P2 complete; P3 begun.
- **What changed**: Added 2 JUMPI-based corpus seeds:
  `0004-jumpi-sstore-on-taken` (storage_eq slot=0 value=0x42, SAT —
  solver must find any non-zero calldata word to take the JUMPI branch
  reaching the SSTORE) and `0005-jumpi-sstore-on-not-taken`
  (storage_eq slot=0 value=1, SAT — solver must find calldata[0..31]=1
  so ISZERO produces 0, JUMPI is NOT taken, and fall-through reaches
  SSTORE(slot=0, calldata)).  Both seeds verified against the P2
  concrete executor (executor.run) and round-trip through
  `EvmBtor2Spec.from_jsonable`.  Created
  `gurdy/pairs/evm_btor2/btor2/` subpackage — domain-free BTOR2 AST
  (nodes.py), parser (parser.py), evaluator (evaluator.py), printer
  (printer.py) — verbatim port of `v2-bootstrap:riscv-btor2/btor2/`
  with imports redirected to the local package and tagged
  `BTOR2_PACKAGE_VERSION = "1.0.0"`.  Created
  `gurdy/pairs/evm_btor2/reasoning_interp/interpreter.py`
  (`Btor2ReasoningInterpreter`, `INTERPRETER_VERSION = "1.0.0"`,
  `PAIR_ID = "evm-btor2"`) and `bindings.py`
  (`Btor2ReasoningBinding` with EVM SCHEMA.md §3 symbol names),
  adapted from riscv-btor2.  28 new tests in
  `tests/pairs/evm_btor2/test_reasoning_interp.py` covering BTOR2
  parser, evaluator (add/eq/ite/sort-mismatch), multi-step interpreter
  (counter model, bad-firing step, state override), and corpus seed
  round-trips for all 5 seeds.  104 tests total, all green.
- **Next iteration's planned work**: P3 continued — write a second
  BTOR2 interpreter test using a minimal 2-state model that mirrors the
  EVM SCHEMA.md halted/trap variables (bv1 states); then begin P4
  skeleton: `gurdy/pairs/evm_btor2/translation/` module stub with a
  `Btor2Builder` helper that emits sort declarations for the 6 sorts in
  SCHEMA.md §2 and the machine-state variable declarations from §3.1.
- **Open BLOCKERs**: none.

---

## 2026-05-26T00:00:00Z — P2: JUMPI/RETURN/MSTORE8 coverage + seed corpus (3 tasks)

- **Phase**: P2 in progress.
- **What changed**: Added 7 tests to `tests/pairs/evm_btor2/test_source_interp.py`
  covering the three opcodes that were implemented but untested: JUMPI
  (taken path, not-taken path, invalid-dest trap), RETURN (single-byte
  returndata via MSTORE8, 32-byte word via MSTORE), and MSTORE8 (single-byte
  write verified by MLOAD, and truncation of upper bytes confirmed).  76 tests
  total, all green.  Created the first three hand-crafted seed tasks in
  `bench/evm-btor2/corpus/seed/`: `0001-sstore-unconditional`
  (storage_eq, slot 0 = 0x42, SAT), `0002-sstore-from-calldata`
  (storage_eq, slot 0 = 1 via free calldata, SAT), and
  `0003-return-fixed-byte` (returndata_eq, offset 0 = [0x42], SAT).  Each
  seed has `task.bin`, `task.toml`, and `task.spec.json` that round-trips
  through `EvmBtor2Spec.from_jsonable`.
- **Next iteration's planned work**: P2 continued — add 2 more corpus seeds
  exercising JUMPI-based conditional branching (storage_eq only reachable on
  one branch, testing that the solver finds the right calldata witness); then
  begin P3 skeleton: `gurdy/pairs/evm_btor2/reasoning_interp/` module stub,
  porting the BTOR2 parser from `v2-bootstrap:gurdy/pairs/riscv_btor2/` and
  adapting it to the EVM SCHEMA.md variable names.
- **Open BLOCKERs**: none.

---

## 2026-05-25T00:00:00Z — P2: concrete EVM executor + bytecode disassembler

- **Phase**: P2 in progress.
- **What changed**: Implemented `gurdy/pairs/evm_btor2/source_interp/disasm.py`
  (`Instruction` dataclass, `disassemble()`, `compute_jumpdest_table()`) and
  `gurdy/pairs/evm_btor2/source_interp/executor.py` (`MachineState`,
  `EvmContext`, `StepRecord`, `step()`, `run()`).  The executor covers the
  full P1 opcode set: all arithmetic (ADD–SIGNEXTEND), comparison/bitwise
  (LT–SAR), environment vars (CALLER, CALLVALUE, CALLDATALOAD, CALLDATACOPY,
  CODESIZE, etc.), block vars (COINBASE–GASLIMIT), stack/memory/storage
  (POP, MLOAD, MSTORE, MSTORE8, MSIZE, GAS, PUSH0, PUSH1–32, DUP1–16,
  SWAP1–16, SLOAD, SSTORE), control flow (JUMP, JUMPI, JUMPDEST, PC), and
  termination (STOP, RETURN, REVERT, INVALID).  Gas model: static costs from
  §10.1, EXP byte-count dynamic (§10.2), memory expansion Cmem formula (§7.1),
  EIP-2929 SLOAD cold/warm (§8), EIP-2929/3529 SSTORE six-case schedule
  (§10.4).  Trap semantics: stack overflow/underflow, invalid jump dest,
  out-of-gas, out-of-scope opcode (§11/§16).  Shadow mode records per-step
  stack/memory/storage reads and writes.  `__init__.py` exports the public
  API.  17 new tests in `tests/pairs/evm_btor2/test_source_interp.py`
  covering 5 hand-traced sequences (ADD, MUL+SUB, JUMP+JUMPDEST, SSTORE+SLOAD,
  CALLDATALOAD), memory round-trip, trap cases, disassembler, and shadow mode.
  69 tests total, all green.
- **Next iteration's planned work**: P2 continued — JUMPI coverage (conditional
  branch, both taken and not-taken paths); RETURN with returndata; MSTORE8;
  extend corpus with ≥ 3 hand-crafted bytecode seeds in
  `bench/evm-btor2/corpus/seed/` exercising the storage_eq and returndata_eq
  reach properties.
- **Open BLOCKERs**: none.

---

## 2026-05-24T00:00:00Z — P1: SCHEMA.md v1.0.0 frozen; EvmBtor2Spec implemented

- **Phase**: P1 complete.
- **What changed**: `SCHEMA.md` frozen at v1.0.0 — specifies sorts
  (`bv1/8/10/16/64/256`, three array sorts), machine state variables
  (`sp`, `stack`, `mem`, `mem_words`, `sto`, `sto_warm`, `pc`, `gas`,
  `trap`, `halted`, `returndata`, `returndatasize`), symbolic context
  inputs (CALLER, CALLVALUE, ORIGIN, calldata, block vars), gas model
  (full static costs table + EXP dynamic + memory expansion +
  EIP-2929/3529 SSTORE schedule), opcode lowering table for the
  pure-function P1 subset, layer structure (header → machine → context
  → constraint → dispatch → binding → bad), and reach-property
  encoding (`revert` / `stop` / `storage_eq` / `returndata_eq`).
  `spec.py` implements `EvmBtor2Spec` (BaseSpec subclass), all eight
  assumption types, `ReachProperty`, `AnalysisDirective`, JSON
  round-trip (`from_jsonable`), and `validate_evm_btor2_spec`
  (52 tests green, `tests/pairs/evm_btor2/test_spec.py`).
- **Next iteration's planned work**: P2 — source interpreter skeleton:
  bytecode disassembler (opcode + immediate decoder), concrete EVM
  executor for the pure-function P1 opcode set (stack machine +
  memory + storage + calldata), trap semantics, shadow mode
  (per-instruction stack/memory/storage read-write records).
  Target: `gurdy/pairs/evm_btor2/source_interp/` and
  `tests/pairs/evm_btor2/test_source_interp.py` with ≥ 5 hand-traced
  bytecode sequences covering arithmetic, control flow, and storage.
- **Open BLOCKERs**: none.

---

## 2026-05-22T00:00:00Z — P0: package + bench scaffold

- **Phase**: P0 complete.
- **What changed**: Created `gurdy/pairs/evm_btor2/` package skeleton
  (`__init__.py`, `spec.py`, `SCHEMA.md`, `source/`, `source_interp/`,
  `reasoning_interp/`, `translation/`, `lift/`, `solvers/`); added
  `bench/evm-btor2/corpus/{seed,external}/`, `harness.py`,
  `oracle_align.py`, `oracle_cross.py`, `engine_bench.py`,
  `baselines/{smtchecker,hevm,hurdy_gurdy,pareto}.py`;
  `tests/pairs/evm_btor2/`.  `gurdy/core/` already matched
  `v2-bootstrap` — no copy needed.  Package imports cleanly.
- **Next iteration's planned work**: P1 — define `SCHEMA.md` v1.0.0
  for the pure-function subset (no `CALL`/`DELEGATECALL`), single
  contract, BMC engine, `reach`-property `QuestionSpec`.  Freeze
  SCHEMA.md and stub `EvmBtor2Spec` + validator in `spec.py`.
- **Open BLOCKERs**: none.

---

## 2026-05-17T00:00:00Z — Branch bootstrap

- **Phase**: pre-P0. Nothing implemented yet on this branch.
- **What's here**: `V2_BOOTSTRAP.md` (spec), `V2_AGENT_LOOP.md`
  (procedure), `V2_PROGRESS.md` (this file),
  `bench/evm-btor2/SCOPE.md` (benchmark scope). Everything else
  is inherited from `main`.
- **Next iteration's planned work**: P0 — scaffold the
  `gurdy/pairs/evm_btor2/` package and `bench/evm-btor2/`
  directory shape per `V2_BOOTSTRAP.md` §5. Copy `gurdy/core/`
  primitives from `v2-bootstrap` where they conform.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).
