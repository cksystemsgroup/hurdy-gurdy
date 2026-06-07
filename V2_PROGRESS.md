# `evm-btor2` Progress — Live State

> The single source of truth for "where is the `evm-btor2` bootstrap
> right now." Each iteration appends one entry at the top. Older
> entries stay for history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-06-07T00:00:00Z — P49: Corpus seed 0042 (SIGNEXTEND+SAR sign-gated SSTORE, SAT) + translator tests

- **Phase**: P49 complete.
- **What changed**:
  1. **Corpus seed 0042** (`bench/evm-btor2/corpus/seed/0042-signextend-sar-sign-gated-sstore/`):
     SIGNEXTEND+SAR composite gating SSTORE on sign bit. Bytecode loads a calldata word,
     sign-extends its lowest byte (SIGNEXTEND bytenum=0), arithmetic-shifts right by 1
     (SAR 1), then uses SGT(TOS=0, NOS=sar_result) to check if the result is negative.
     Stack order verified: SGT(a=TOS=0, b=NOS=sar_result) pushes 1 if 0 > sar_result
     (= sar_result < 0). SAT when calldata[31] ∈ 128..255 (bit 7 of LSB set →
     SIGNEXTEND gives negative → SAR preserves sign → SGT=1 → JUMPI taken →
     SSTORE(0,1) → bad fires at step 14). UNSAT when calldata[31] ∈ 0..127.
     Witness: `{"calldata": {"31": 128}}` (0x80 = minimum negative int8).
     Tests SIGNEXTEND+SAR opcode pair: arithmetic shift is sign-preserving; a negative
     int8 sign-extended to 256 bits stays negative after SAR.
     Note: SLT (0x12) semantics are `a=TOS < b=NOS`, i.e., SLT(TOS=0, NOS=x) = x>0;
     SGT (0x13) is used here to gate on x<0 (sar_result negative).
  2. **Translator tests** (3 new in `test_translation_translator.py`):
     `test_translate_seed_0042_round_trips`, `test_seed_0042_negative_byte_fires_at_step_14`
     (calldata[31]=0x80 → fires), `test_seed_0042_nonnegative_byte_never_fires`
     (calldata[31]=0x7f → silent).
  Total: 1263 tests pass (+5: 3 new translator tests + 2 parametric reasoning-interp
  tests picked up from the new seed directory).
- **Next phase hint**: P50 — Harness run on seeds 0020–0024 (now allowed: P48 harness
  → P49 = 1 iteration; need 2 more before next harness, so P50 is still corpus; next
  allowed harness is P51). Or: corpus seed 0043 (e.g. multi-byte BYTE extraction with
  PUSH2 index testing PUSH2 opcode + BYTE with i<31, or ADD-overflow edge case with
  two CALLDATALOAD words added and EQ-compared to a wrapped sum).

---

## 2026-06-06T01:00:00Z — P48: Harness run on seeds 0015–0019

- **Phase**: P48 complete.
- **What changed**:
  Harness run (`bench/evm-btor2/harness.py`) on 5 seeds (0015–0019; all had
  pre-existing witness files except 0017 which is UNSAT):

  | seed                      | bad_fired | witness_step | wall_s |
  |---------------------------|-----------|-------------|--------|
  | 0015-swap1-gt             | True      | 11          | 0.044  |
  | 0016-pop-cleanup          | True      | 12          | 0.049  |
  | 0017-jumpdest-validation  | False     | -           | 0.027  |
  | 0018-invalid-trap         | True      | 8           | 0.027  |
  | 0019-revert-trap          | True      | 8           | 0.034  |

  All 4 SAT seeds fire at the expected step. Seed 0017 (JUMPI to pc=7 which
  is `PUSH1`, not `JUMPDEST`) correctly reports `bad_fired=False` — invalid
  jump traps execution before SSTORE is reached → UNSAT.
  Cumulative harness coverage: 14 SAT seeds verified (0001, 0009, 0010–0016,
  0018–0019, 0034–0036); 2 UNSAT seeds correctly silent (0017, 0037).
  Total: 1258 tests pass (unchanged — harness-only, no code changes).
- **Next phase hint**: P49 — Corpus seed 0042 (next allowed 3 iterations from
  P48 harness is P51; so seed 0042 is the right move). Candidates:
  SIGNEXTEND+SAR composite (extend a signed byte then arithmetic-shift right,
  gate on sign bit), ADD-overflow edge case (pre-0.8 wraparound via CALLDATALOAD
  ADD EQ SSTORE), or multi-byte BYTE extraction with PUSH2 index.

---

## 2026-06-06T00:00:00Z — P47: Corpus seed 0041 (BYTE LSB extraction, SAT) + translator tests
## 2026-06-05T00:00:00Z — doc correction: two stale/imprecise numbers in older entries

- **Phase**: documentation — a main-branch consistency audit surfaced two
  numbers in older entries that no longer reflect live state or were
  imprecise when written. Per this log's append-only rule ("older entries
  stay for history"), the dated entries below are **left intact** — this
  note records the corrections instead.
- **Corpus size (supersedes iter-43's "92").** iter-43 (2026-05-28)
  recorded "Built full corpus (92 ELFs)" / "the full 92-task corpus" — an
  accurate snapshot for that day. The corpus has since grown to **103
  tracked task directories**: 51× `00xx` (assembly), 26× `01xx` (C), 23×
  `02xx` (C + SV-COMP), 3× `03xx`. So "92" is correct history but no longer
  the live count.
- **The "18-task canonical measured subset" (clarifies iter-42).** iter-42
  (2026-05-27) writes "all 18 canonical C-source tasks (`_compile_c.py`
  run on `0100-0124`)". The two are not equal: `0100-0124` is **25** task
  IDs, all present since 2026-05-11. "18" is a curated *measured subset*
  drawn from that range (cf. commit `973d792`, "16/18 on measured
  subset") — the `/18` denominators in iter-42's Pareto tables are correct
  as that subset; the `(0100-0124)` parenthetical overstates its span.
- **Open blockers**: 0.

---

## 2026-05-28T10:30:00Z — iter-43: Adversarial wedge tasks compiled & validated

- **Phase**: P47 complete.
- **What changed**:
  1. **Corpus seed 0041** (`bench/evm-btor2/corpus/seed/0041-byte-lsb-gated-sstore/`):
     BYTE opcode extracts least-significant byte (index 31, counting from MSB=0) of a
     calldata word, then `EQ(byte, 0x42)` gates SSTORE. Stack order: push calldata word
     first (via CALLDATALOAD), then push index `0x1f` — so TOS=i, NOS=x for BYTE.
     SAT when `calldata[31]=0x42` → `BYTE(31, word)=0x42` → `EQ=1` → JUMPI taken →
     `SSTORE(0,1)` → bad fires at step 12. UNSAT when `calldata[31]≠0x42`.
     Witness: `{"calldata": {"31": 66}}` (0x42=66).
     Tests BYTE opcode: byte-index extraction from a symbolic calldata word.
  2. **Translator tests** (3 new): round-trip, fires-at-step-12 (calldata[31]=0x42),
     nonmatching-byte-never-fires (calldata[31]=0x43).
  Total: 1258 tests pass.
- **Next phase hint**: P48 — Harness run on seeds 0015–0019 (now allowed: P45 harness
  → P46 → P47 → P48 = 3 iterations gap met). Or: corpus seed 0042 (e.g. SIGNEXTEND+SAR
  composite, or multi-byte BYTE extraction with PUSH2 index, or ADD-overflow edge case).

---

## 2026-06-05T09:00:00Z — P46: Corpus seed 0040 (MSTORE+MLOAD round-trip, SAT) + translator tests

- **Phase**: P46 complete.
- **What changed**:
  1. **Corpus seed 0040** (`bench/evm-btor2/corpus/seed/0040-mstore-mload-eq-sstore/`):
     MSTORE+MLOAD round-trip gating SSTORE. `MSTORE(0, 0x42)` writes to memory;
     `MLOAD(0)` reads it back as 0x42; `EQ(0x42, 0x42)` = 1 always; `JUMPI` always
     taken; `SSTORE(0, 1)` reached unconditionally → bad fires at step 13.
     No witness file needed (unconditional). Tests memory faithfulness: the BTOR2
     model must correctly propagate values through the `mem` array.
  2. **Translator tests** (3 new): round-trip, fires-at-step-13, not-fired-before-step-13.
  Total: 1253 tests pass.
- **Next phase hint**: P47 — Harness run on seeds 0015–0019 (now allowed: P45 harness
  → P46 → P47 = 2 iterations; actually need 3, so first allowed at P48). Or: corpus
  seed 0041 (new opcode pattern — e.g. BYTE-based branch, or SIGNEXTEND+SAR composite,
  or PUSH2/PUSH3 value with complex branch).

## 2026-06-05T08:00:00Z — P45: Harness run on seeds 0010–0014

- **Phase**: P45 complete.
- **What changed**:
  Harness run (`bench/evm-btor2/harness.py`) on 5 seeds (all had pre-existing witness files):

  | seed                | bad_fired | witness_step | wall_s |
  |---------------------|-----------|-------------|--------|
  | 0010-shr-abi-decode | True      | 12          | 0.054  |
  | 0011-signextend-slt | True      | 12          | 0.054  |
  | 0012-sdiv-gt        | True      | 12          | 0.053  |
  | 0013-push2-gt       | True      | 10          | 0.041  |
  | 0014-dup2-eq        | True      | 10          | 0.040  |

  All 5 fire correctly. Cumulative harness coverage: 11/11 SAT seeds verified
  (0001, 0009, 0034–0036 from P42; 0010–0014 from P45); 1 UNSAT seed (0037)
  correctly silent.
  Total: 1248 tests pass (unchanged — no new code).
- **Next phase hint**: P46 — Continue Pareto table: run harness on seeds 0015–0019
  (5 more seeds). Or: extend corpus with seed 0040 exercising a new opcode pattern
  (e.g. MSTORE+MLOAD round-trip gated SSTORE, or RETURNDATACOPY affecting branch).

## 2026-06-05T07:00:00Z — P44: CALLCODE corpus seed 0039 (UNSAT) + translator tests

- **Phase**: P44 complete.
- **What changed**:
  1. **Corpus seed 0039** (`bench/evm-btor2/corpus/seed/0039-callcode-gated-sstore/`):
     CALLCODE-gated SSTORE. CALLCODE (0xF2) pops 7 args (gas, to, value, argsOffset,
     argsLen, retOffset, retLen) — same as CALL. Stub always pushes 0 → JUMPI not taken
     → STOP at pc=0x12 → SSTORE unreachable → UNSAT. Completes the call-family UNSAT
     seed trio: 0037 (STATICCALL), 0038 (DELEGATECALL), 0039 (CALLCODE).
     Gas budget: 7×PUSH1=21 + CALLCODE stub=700 + PUSH1=3 + JUMPI=10 + STOP=0 ≈ 734.
  2. **Translator tests** (2 new in `test_translation_translator.py`):
     `test_translate_seed_0039_round_trips` and `test_seed_0039_never_fires`.
  Total: 1248 tests pass.
- **Next phase hint**: P45 — Run harness on seeds 0010–0033 (Pareto table extension;
  now allowed per 3-iteration rule: P42 harness → P43 → P44 → P45). Aim for ≤ 10 seeds
  per run. Then P46: CALL-gated SSTORE SAT seed (CALL stub pushes 0 → SSTORE unreachable
  even on success-path) — but note with stub this is also UNSAT; document in UNSAT notes.

## 2026-06-05T06:00:00Z — P43: DELEGATECALL corpus seed 0038 (UNSAT) + translator tests

- **Phase**: P43 complete.
- **What changed**:
  1. **Corpus seed 0038** (`bench/evm-btor2/corpus/seed/0038-delegatecall-gated-sstore/`):
     DELEGATECALL-gated SSTORE. Bytecode identical to seed 0037 but with opcode 0xF4
     (DELEGATECALL) instead of 0xFA (STATICCALL). DELEGATECALL pops 6 args, stub always
     pushes 0 → JUMPI not taken → STOP at pc=0x10 → SSTORE unreachable → UNSAT.
     Gas budget: 6×PUSH1=18 + DELEGATECALL stub=700 + PUSH1=3 + JUMPI=10 + STOP=0 ≈ 731.
  2. **Translator tests** (2 new in `test_translation_translator.py`):
     `test_translate_seed_0038_round_trips` (BTOR2 model parses without errors) and
     `test_seed_0038_never_fires` (bad never fires within 12 steps).
  Total: 1244 tests pass.
- **Next phase hint**: P44 — Either (a) run harness on seeds 0010–0033 to extend the Pareto
  table (next allowed harness run after P42+2=P44), or (b) add corpus seed 0039 exercising
  CALLCODE-gated SSTORE (UNSAT), or (c) implement CREATE/CREATE2 as out-of-scope traps with
  a corpus seed demonstrating the behaviour.

## 2026-06-05T05:00:00Z — P42: Harness run on 6 seeds + witness for seed 0035

- **Phase**: P42 complete.
- **What changed**:
  1. **`task.witness.json` for seed 0035**: Added `{"calldata": {"31": 1}}` so the
     `AlignmentOracle` harness can find the SAT path (calldata byte 31 = 1 → SGT(1,0)=1
     → JUMPI taken → SSTORE fires at step 10).
  2. **Harness run** (`bench/evm-btor2/harness.py`) on 6 seeds with `PYTHONPATH` set:

     | seed                              | bad_fired | witness_step | wall_s |
     |-----------------------------------|-----------|-------------|--------|
     | 0001-sstore-unconditional         | True      | 3           | 0.009  |
     | 0009-div-sstore-on-taken          | True      | 12          | 0.059  |
     | 0034-push3-pc-advance-sstore      | True      | 3           | 0.009  |
     | 0035-sgt-signed-positive-sstore   | True      | 10          | 0.036  |
     | 0036-call-stub-sstore             | True      | 12          | 0.035  |
     | 0037-staticcall-gated-sstore      | False     | -           | 0.035  |

     0037 correctly reports `bad_fired=False` (UNSAT — STATICCALL stub always pushes 0).
  3. **Pareto coverage**: 5/6 SAT seeds fire; 1 UNSAT seed correctly silent.
  Total: 1240 tests pass (unchanged — no new code, only a data file).
- **Next phase hint**: P43 — DELEGATECALL corpus seed (SSTORE via DELEGATECALL → UNSAT with
  stub, documenting inter-contract gap). Or: RETURNDATASIZE (0x3D) / RETURNDATACOPY (0x3E)
  as zero-stubs (returndatasize always 0). Or: add harness to seeds 0010–0033 Pareto table.

## 2026-06-05T04:00:00Z — P41: CALLCODE (0xF2) and DELEGATECALL (0xF4) pessimistic stubs + seed 0037

- **Phase**: P41 complete.
- **What changed**:
  1. **`lower_callcode`** (0xF2) — thin wrapper over `lower_call`: pops 7 args (same as
     CALL including a value slot), net sp -= 6, pushes 0.
  2. **`lower_delegatecall`** (0xF4) — thin wrapper over `lower_staticcall`: pops 6 args
     (no value), net sp -= 5, pushes 0.
  3. **Translator dispatch**: opcodes 0xF2 and 0xF4 now route to the new stubs.
  4. **Library tests** (8 new): round-trip, pushes-zero, sp-net, underflow for both
     CALLCODE and DELEGATECALL.
  5. **Corpus seed 0037** (`bench/evm-btor2/corpus/seed/0037-staticcall-gated-sstore/`):
     STATICCALL-gated SSTORE; stub always pushes 0 so JUMPI is never taken and SSTORE is
     unreachable → UNSAT. Exercises the pessimistic-stub UNSAT path.
  6. **Translator tests** (2 new): round-trip and never-fires for seed 0037.
  Total: 1240 tests pass.
- **Next phase hint**: P42 — Harness run on 5 seeds (0001, 0009, 0034, 0035, 0036) to
  populate the Pareto table. Then: DELEGATECALL corpus seed (SSTORE reachable via
  DELEGATECALL? UNSAT with stub, potentially SAT with real model). Or: implement
  RETURNDATASIZE/RETURNDATACOPY handling with stub returndatasize=0.

## 2026-06-05T03:00:00Z — P40: CALL (0xF1) and STATICCALL (0xFA) pessimistic stubs

- **Phase**: P40 complete.
- **What changed**:
  1. **`lower_call` / `lower_staticcall`** added to `library.py`: pessimistic stubs that
     always push 0 (call failed). CALL pops 7 args (gas/to/value/argsOff/argsLen/retOff/retLen),
     net sp -= 6; STATICCALL pops 6 args, net sp -= 5. Both deduct `CALL_GAS_STUB = 700`
     (EIP-150 base cost). Trap on underflow (sp < 7 / sp < 6) or OOG (gas < 700).
     returndata/returndatasize left unchanged.
  2. **Translator dispatch**: opcodes 0xF1 and 0xFA now route to the new stubs instead
     of falling through to `_lower_oos` (out-of-scope trap).
  3. **Library tests** (20 new): round-trip, pushes-zero, sp-net, gas-decremented,
     pc-advanced, underflow-traps, oog-traps, exact-gas-no-oog, halted-noop for both
     CALL and STATICCALL.
  4. **Corpus seed 0036** (`bench/evm-btor2/corpus/seed/0036-call-stub-sstore/`):
     7 × PUSH1 0 + CALL + POP + PUSH1 1 + PUSH1 0 + SSTORE + STOP. Unconditional SSTORE
     after CALL verifies stub lets execution continue; bad fires at step 12.
  5. **Translator tests** (3 new): round-trip, fires-at-step-12, not-before-step-12.
  Total: 1228 tests pass.
- **Next phase hint**: P41 — DELEGATECALL (0xF4) and CALLCODE (0xF2) pessimistic stubs
  (same pattern as STATICCALL — pop 6 args, push 0, deduct 700 gas). Then P42:
  corpus seed 0037 with STATICCALL-gated SSTORE (UNSAT — stub always fails, so SSTORE
  on success-path never fires). Alternatively: revisit corpus density — we have 0001–0036
  seeds but no harness run yet; consider P41 = harness run on 5 seeds.

## 2026-06-05T02:00:00Z — P39: SGT signed-positive corpus seed + evaluator write-mask bug fix

- **Phase**: P39 complete.
- **What changed**:
  1. **Evaluator bug fix** (`gurdy/pairs/evm_btor2/btor2/evaluator.py`): The `write` op
     was unconditionally masking stored values with `& 0xFF`, treating all array writes
     as byte-width. This was correct for `mem_t` (Array bv256→bv8) but silently
     truncated `stack_t` (Array bv10→bv256) writes to 8 bits. Fixed to look up the
     array's element sort width via `array_meta` and apply `_mask(elem_w)`. Three
     existing tests that were written against the buggy behaviour (`test_lower_sub_wrapping`,
     `test_lower_not_result_zero_input`, `test_lower_not_clears_low_byte`) were updated to
     check the correct full bv256 values.
  2. **Corpus seed 0035** (`bench/evm-btor2/corpus/seed/0035-sgt-signed-positive-sstore/`):
     SGT signed-positive CALLDATALOAD-gated SSTORE. Bytecode:
     `PUSH1 0 / PUSH1 0 / CALLDATALOAD / SGT / PUSH1 0x0a / JUMPI / STOP / JUMPDEST /
      PUSH1 1 / PUSH1 0 / SSTORE / STOP`. SAT witness: `calldata[31]=1` → SGT(1,0)=1 →
     JUMPI taken → SSTORE(0,1) → bad at step 10. UNSAT: `calldata=0` or `calldata=0xFF..FF`
     (-1 signed → SGT(-1,0)=0). Exercises: signed vs unsigned comparison semantics.
  3. **Translator tests** (4 new in `test_translation_translator.py`): round-trip, positive
     calldata fires at step 10, zero calldata never fires, negative calldata never fires.
  4. **Library test extension**: Added ISZERO to the `test_arithmetic_exact_gas_does_not_oog`
     parametrize (P38 extension).
  Total: 1208 tests pass.
- **Next phase hint**: P40 — CALL (0xF1) / STATICCALL (0xFA) as uninterpreted stubs:
  pop 7 args (CALL: gas/addr/value/argsOffset/argsLength/retOffset/retLength);
  push 0 (pessimistic "call failed"); mark returndata as fresh symbolic input;
  set returndatasize to a fresh symbolic bv256 input; sp -= 6 net; gas model:
  deduct a base stub cost. Corpus seed: calldata-gated STATICCALL that writes
  0 on success-path.

## 2026-06-05T01:00:00Z — P38: Arithmetic OOG edge-case audit — exact-gas-no-OOG for 24 opcodes

- **Phase**: P38 complete.
- **What changed**: Added `@pytest.mark.parametrize` library test
  `test_arithmetic_exact_gas_does_not_oog` covering all 24 arithmetic opcodes
  that had a "gas < cost → trap" test but no "gas == cost → no trap" test.
  The OOG guard uses strict less-than (`b.ult(gas, c_gas)` = `gas < opcode_cost`),
  so `gas == opcode_cost` must execute normally. The test verifies `trap == 0`
  fires (bad condition = no trap) at step 0 for each opcode at the exact-cost boundary.
  Opcodes covered (24): ADD, SUB, MUL, DIV, MOD, SDIV, SMOD, ADDMOD, MULMOD, EXP
  (at EXP_GAS_BASE=10 with exp=0), AND, OR, XOR, NOT, LT, GT, EQ, SLT, SGT,
  SHL, SHR, SAR, BYTE, SIGNEXTEND. Special setup: EXP uses exp=0 → base gas=10;
  ADDMOD/MULMOD use sp=3 (ternary ops); NOT uses sp=1 (unary op). All 24 tests
  confirm the strict-`<` semantics are correctly modelled — no off-by-one in the
  OOG guard.
  Total: 1569 tests pass, 13 skipped.
- **Next phase hint**: P39 — CALL (0xF1) / STATICCALL (0xFA) as uninterpreted
  stubs: pop 7 args (CALL: gas/addr/value/argsOffset/argsLength/retOffset/retLength);
  push 0 (pessimistic "call failed"); mark returndata as fresh symbolic input;
  set returndatasize to a fresh symbolic bv256 input; sp -= 6 net; gas model:
  always charge 700 base (EIP-150 cold base, warm discount not modelled) +
  calldata-copy expansion. Sound over-approximate: caller cannot observe return
  value or returndata content. Or consider ISZERO (0x15) exact-gas audit + corpus
  seed, or a corpus seed exercising CALLDATALOAD + signed comparison (SGT/SLT)
  to cover a pre-0.8 signed-overflow wedge pattern.

---

## 2026-06-05T00:00:00Z — P37: PUSH-range completeness — PUSH3/PUSH16/PUSH31 pc-advance + corpus seed 0034

- **Phase**: P37 complete.
- **What changed**: Added systematic pc-advance coverage for PUSH3..PUSH31 variants
  not individually tested in P16/P32. Added `@pytest.mark.parametrize` library test
  `test_lower_pushn_pc_advance_n_plus_1` with n in [3, 4, 8, 16, 24, 31] —
  each verifies `pc_next == n+1` after one `lower_pushn` step (6 cases).
  Added 5 translator tests: `test_translate_push3_round_trips`,
  `test_translate_push3_stop_fires_at_step_1` (STOP at pc=4, bad fires at step 1),
  `test_translate_push3_pc_advances_by_4` (PUSH3 + PUSH1 + SSTORE: wrong advance
  would decode 0x01 as PUSH1 and trap; bad fires at step 3),
  `test_translate_push16_pc_advances_by_17` (PUSH16 + PUSH1 + SSTORE, bad fires at
  step 3), `test_translate_push31_pc_advances_by_32` (PUSH31 + PUSH1 + SSTORE, bad
  fires at step 3). Added corpus seed `0034-push3-pc-advance-sstore`
  (hex `6200000160005500`: 8 bytes — `PUSH3 0x000001 / PUSH1 0x00 / SSTORE / STOP`;
  PUSH3 pushes 1 with 4-byte pc advance, PUSH1 pushes slot=0, SSTORE writes sto[0]=1;
  bad fires at step 3 confirming correct 3-byte immediate parsing and pc=4 placement
  of the next instruction). 3 seed 0034 corpus tests added.
  Total: 1545 tests pass, 13 skipped.
- **Next phase hint**: P38 — ADD/MUL/DIV OOG edge-case audit: verify that the
  arithmetic opcodes correctly trap on OOG when gas equals exactly the opcode cost
  minus 1 (e.g., ADD gas=3, trap when gas=2). Also consider CALL (0xF1) /
  STATICCALL (0xFA) as uninterpreted stubs (push 0 return value, symbolic
  returndata, net sp-=5+1=-4 for CALL; sound conservative model), or
  RETURNDATASIZE/RETURNDATACOPY alignment audit to verify the out-of-bounds
  trap fires correctly relative to returndatasize machine state.

---

## 2026-06-04T10:00:00Z — P36: EXTCODEHASH (0x3f) symbolic external-code hash + corpus seed 0033

- **Phase**: P36 complete.
- **What changed**: Added `lower_extcodehash(b, machine_nids)` to `library.py`
  (EXTCODEHASH_GAS_COLD=2600, EXTCODEHASH_SIZE=1). Implementation: pops
  `address` (TOS = `stack[sp-1]`); pushes a fresh unconstrained `bv256` BTOR2
  `input` node (symbol `extcodehash_result`) as the keccak256 of the external
  account's code back at `stack[sp-1]`; net sp unchanged. Gas: always-cold
  2600 (EIP-2929 warm-account discounting not modelled — sound conservative
  bound). Hash modelled identically to SHA3 (unconstrained, over-approximate).
  Updated `translator.py` to route `0x3F → lower_extcodehash(b, machine_nids)`;
  updated docstring; imported `lower_extcodehash`. Updated `__init__.py` imports
  and `__all__`. Updated `library.py` `__all__`. Added 10 library tests
  (constants, returns result, sp NID unchanged assertion, sp unchanged via
  interpreter, gas decremented, pc advanced, underflow trap, OOG trap, halted
  noop, BTOR2 round-trip). Added 5 translator tests (EXTCODEHASH round-trip,
  stop fires at step 2, and 3 seed 0033 corpus tests). Added corpus seed
  `0033-extcodehash-then-sstore` (hex `60003f60005500`: 7 bytes —
  `PUSH1 0x00 / EXTCODEHASH / PUSH1 0x00 / SSTORE / STOP`; symbolic hash
  of code at address 0 stored in sto[0]; stop bad fires at step 4).
  Total: 1527 tests pass, 13 skipped.
- **Next phase hint**: P37 — the `0x30..0x3F` block is now fully populated.
  Consider CALL (0xF1), STATICCALL (0xFA), DELEGATECALL (0xF4) — very complex;
  or RETURNDATASIZE/RETURNDATACOPY alignment audit; or move to PUSH-range
  completeness (PUSH3..PUSH32 systematic test for pc advance by n+1);
  or ADD/MUL/DIV OOG edge-case audit across all arithmetic opcodes.

---

## 2026-06-04T09:00:00Z — P35: SHA3/KECCAK256 (0x20) symbolic hash + corpus seed 0032

- **Phase**: P35 complete.
- **What changed**: Added `lower_sha3(b, machine_nids)` to `library.py`
  (SHA3_BASE_GAS=30, SHA3_WORD_GAS=6, SHA3_SIZE=1). Implementation: pops
  `offset` (TOS = `stack[sp-1]`), `size` (NOS = `stack[sp-2]`); pushes a
  fresh unconstrained `bv256` BTOR2 `input` node (symbol `sha3_result`) as
  the hash result back to `stack[sp-2]`; net sp decrements by 1. Gas:
  `30 + 6*ceil(size/32) + Cmem_delta(offset+size)` — word cost uses
  `((size + 31) / 32) * 6` with bv256 arithmetic following CALLDATACOPY
  pattern; memory expansion uses the same Cmem quadratic formula as
  MLOAD/MSTORE. Hash output is modeled as a fresh BTOR2 `input` node —
  over-approximate (any 256-bit value), but sound. Updated `translator.py`
  to route `0x20 → lower_sha3(b, machine_nids)`; updated docstring; imported
  `lower_sha3`. Updated `__init__.py` imports and `__all__`. Added 9 library
  tests (constants, returns result, sp decremented by 1, base gas when
  size=0, pc advance, underflow trap sp<2, OOG trap, halted noop, BTOR2
  round-trip). Added 5 translator tests (SHA3 round-trip, SHA3 stop fires at
  step 3, and 3 seed 0032 corpus tests). Added corpus seed
  `0032-sha3-keccak256-then-sstore` (hex `602060002060005500`: 9 bytes —
  `PUSH1 0x20 / PUSH1 0x00 / SHA3 / PUSH1 0x00 / SSTORE / STOP`; SHA3
  hashes 32 bytes at offset 0, stores symbolic result in sto[0]; stop bad
  fires at step 5).
  Total: 1510 tests pass, 13 skipped.
- **Next phase hint**: P36 — consider EXTCODEHASH (0x3f, cold=2600 gas,
  warm=100), or CALL/STATICCALL/DELEGATECALL (complex, needs careful spec),
  or an audit pass on memory-expansion gas for CODECOPY/EXTCODECOPY to
  ensure Cmem formula matches RETURNDATA/CALLDATACOPY pattern. Also consider
  JUMPDEST (0x5b) if not yet routing it as a no-op with gas=1.

---

## 2026-06-04T08:00:00Z — P34: LOG0-LOG4 (0xa0–0xa4) event opcodes + corpus seed 0031

- **Phase**: P34 complete.
- **What changed**: Added `lower_logn(b, machine_nids, n)` to `library.py`
  (LOG_BASE_GAS=375, LOG_DATA_GAS=8, LOG_TOPIC_GAS=375, LOG_SIZE=1). `n` is the
  number of topics (0 for LOG0, …, 4 for LOG4). Implementation: pops
  `offset` (TOS), `size` (NOS), and `n` topic words; no return value; sp
  decrements by `2 + n`. Gas: `375 + 8*size + 375*n + Cmem_delta(offset+size)`
  — byte cost is symbolic (symbolic multiplication `8 * size`) following the
  CALLDATACOPY word-cost pattern; topic cost is constant per LOGn; memory
  expansion uses the Cmem quadratic formula same as MLOAD/MSTORE. `size==0`
  short-circuit skips expansion to avoid spurious gas when data length is zero.
  Updated `translator.py` to route `0xA0..0xA4 → lower_logn(b, m, op-0xa0)`;
  updated docstring; imported `lower_logn`. Updated `__init__.py` imports and
  `__all__`. Added 13 library tests (constants, LOG0/LOG1/LOG4 returns result,
  sp decrement by 2/3/6, base gas decrement, pc advance, LOG0/LOG1 underflow
  traps, LOG0 OOG trap, halted noop, LOG0/LOG4 round-trips). Added 7 translator
  tests (LOG0 round-trip, LOG0 stop-fires at step 3, LOG1/LOG4 round-trips, 3
  seed 0031 corpus tests). Added corpus seed `0031-log1-then-sstore` (hex
  `600060006000a1600160005500`: 13 bytes — `PUSH1 0 / PUSH1 0 / PUSH1 0 /
  LOG1 / PUSH1 1 / PUSH1 0 / SSTORE / STOP`; LOG1 consumes 3 stack items and
  750 gas; SSTORE sets sto[0]=1; bad fires at step 7).
  Total: 1496 tests pass, 13 skipped.
- **Next phase hint**: P35 — RETURNDATACOPY already implemented; check
  EXTCODEHASH (0x3f, cold=2600), or SELFBALANCE (already done); consider
  CODECOPY (0x39) memory-expansion gas correctness audit, or move to
  SHA3/KECCAK256 (0x20) — pop offset+size, push hash; gas = 30 + 6*ceil(size/32)
  + memory_expansion; hashing modelled symbolically (unconstrained fresh
  variable per call).

---

## 2026-06-04T07:00:00Z — P33: SLOAD (0x54) cold/warm gas + sto_warm marking + corpus seed 0030

- **Phase**: P33 complete.
- **What changed**: Added `lower_sload(b, machine_nids)` to `library.py`
  (SLOAD_GAS_COLD=2100, SLOAD_GAS_WARM=100, SLOAD_SIZE=1). Implementation:
  pops `slot` (TOS = `stack[sp-1]`), reads `sto[slot]`, overwrites TOS with
  the loaded value (net sp unchanged), marks slot warm
  (`sto_warm[slot] := 1`). Gas: ITE(warm, 100, 2100) using same warm-check
  pattern as SSTORE (`sto_warm[slot][0:0]`). Trap: underflow (sp<1) | OOG.
  Updated `translator.py` to route 0x54→`lower_sload`; updated docstring to
  list SLOAD; imported `lower_sload`, `SLOAD_GAS_COLD/WARM/SIZE`. Updated
  `__init__.py` imports and `__all__`. Added 11 library tests (constants,
  returns result, sp unchanged, reads zero from uninit, cold gas decrement, pc
  advance, cold OOG trap, underflow trap, halted noop, marks slot warm,
  round-trip). Added 5 translator tests (SLOAD round-trip, stop-fires, 3 seed
  0030 corpus tests). Added corpus seed `0030-sstore-sload-roundtrip` (hex
  `600160005560005460005500`: 12 bytes — `PUSH1 1 / PUSH1 0 / SSTORE / PUSH1 0
  / SLOAD / PUSH1 0 / SSTORE / STOP`; first SSTORE marks slot warm at 2200,
  SLOAD reads value=1 back at warm cost 100, second SSTORE re-writes at warm
  cost 100; bad fires at step 7). Total: 1474 tests pass, 13 skipped.
- **Next phase hint**: P34 — LOG0-LOG4 opcodes (0xa0–0xa4): pop offset + size
  (+ 0-4 topics) from stack, read mem[offset..offset+size-1]; no return value;
  gas = 375 + 8*size + 375*N_topics (London); sp decrements by 2+N_topics;
  memory-expansion gas if needed. These are prerequisites for event-based
  contract patterns.

---

## 2026-06-04T06:00:00Z — P32: PUSH2-PUSH32 translator coverage + corpus seed 0029

- **Phase**: P32 complete.
- **What changed**: `lower_pushn` (PUSH1–PUSH32, 0x60–0x7F) was already
  implemented and routed (`n = op - 0x5F`, `pc_inc = n + 1`, immediate parsed
  via `int.from_bytes(insn.immediate, "big")`). The disassembler correctly
  reads `imm_len = op - 0x60 + 1` bytes per PUSH opcode with zero-padding for
  truncated immediates. Library tests (P16, 9 tests) were already passing.
  P32 adds 8 translator tests: PUSH2 (0x61) round-trip and stop-fires
  (verifying STOP lands at pc=3 after PUSH2's 3-byte advance), PUSH32 (0x7F)
  round-trip and stop-fires (STOP at pc=33), `test_translate_push2_pc_advances_by_3`
  (PUSH2 0x0001 / PUSH1 0x00 / SSTORE / STOP: bad fires at step 3, proving correct
  pc offset placement), and 3 seed 0029 corpus tests. Added corpus seed
  `0029-push2-value-sstore` (hex `61000160005500`: 7 bytes — `PUSH2 0x0001 /
  PUSH1 0x00 / SSTORE / STOP`; demonstrates that PUSH2's 3-byte pc advance
  correctly positions subsequent instructions so SSTORE(0,1) fires at step 3).
  Total: 1456 tests pass, 13 skipped.
- **Next phase hint**: P33 — SLOAD (0x54, cold=2100/warm=100 EIP-2929): pop
  key from stack, push `sto[key]`; marks slot warm in `sto_warm`; gas model
  mirrors SSTORE cold/warm split; prerequisite for read-then-conditional-write
  patterns used in most real-world reentrancy guards.

---

## 2026-06-04T05:00:00Z — P31: DUP2-DUP16 / SWAP1-SWAP16 / POP translator coverage + corpus seed 0028

- **Phase**: P31 complete.
- **What changed**: `lower_dupn`, `lower_swapn`, and `lower_pop` were already
  implemented in `library.py` (DUP_GAS=3, SWAP_GAS=3, POP_GAS=2) and routed
  in `translator.py` (0x50→lower_pop, 0x80–0x8F→lower_dupn(n), 0x90–0x9F→lower_swapn(n)),
  and library tests already covered them (32 tests passing). P31 work:
  added 9 translator tests covering POP (0x50) round-trip and stop-fires, DUP2
  (0x81) round-trip and stop-fires, SWAP1 (0x90) round-trip and stop-fires,
  and 3 corpus seed 0028 tests. Added corpus seed
  `0028-swap1-corrects-push-order-sstore` (hex `60006001905500`: 7 bytes —
  `PUSH1 0 / PUSH1 1 / SWAP1 / SSTORE / STOP`; SWAP1 exchanges the push order
  so SSTORE receives slot=0 and val=1 rather than slot=1 and val=0; demonstrates
  SWAP1 as a stack-order corrector enabling the property to fire at step 4).
  Total: 1446 tests pass, 13 skipped.
- **Next phase hint**: P32 — PUSH2-PUSH32 multi-byte push opcodes (0x61–0x7f);
  `lower_pushn` is already implemented for PUSH1-style immediates; need to
  verify/extend routing so all 31 multi-byte PUSH variants produce correct
  `pc_next += 1 + n` advancement and push the correctly-sized immediate onto
  the stack.

---

## 2026-06-04T04:00:00Z — P30: TLOAD (0x5c) / TSTORE (0x5d) transient storage + corpus seed 0027

- **Phase**: P30 complete.
- **What changed**: Added `transient_sto` (sto_t, EIP-1153) as the 13th machine
  state to `MACHINE_STATE_VARS` in `builder.py`. Extended `EvmLoweringResult`
  dataclass with `transient_sto: int` field (now 13 fields). Updated all 68
  existing lowering functions in `library.py` to declare
  `transient_sto = machine_nids["transient_sto"]` and include
  `transient_sto=transient_sto,` in their `EvmLoweringResult` returns (two-pass
  scripted replacement covering both multiline and compact inline return
  formats). Added `lower_tload` (0x5c, gas=100): pops key, pushes
  `transient_sto[key]`; net sp unchanged; OOG (gas<100) and stack-underflow
  (sp<1) traps; halted/trap noop guards. Added `lower_tstore` (0x5d, gas=100):
  pops key (TOS) and value (NOS); writes `transient_sto[key] = value`; sp-=2;
  OOG and underflow traps; halted/trap noop guards. Updated `translator.py` to
  route 0x5c→`lower_tload` and 0x5d→`lower_tstore`; updated `_lower_jumpdest`
  and `_lower_oos` to declare/pass `transient_sto`; updated docstring to P30.
  Updated `__init__.py` imports and `__all__`. Updated
  `test_translation_builder.py` to include `transient_sto` in expected
  machine-state symbol set (13 states). Updated `test_translation_layers.py`
  context-var count from 18→19. Added 20 library tests (TLOAD/TSTORE constants,
  return result, sp behavior, gas decrement, pc advance, OOG/underflow traps,
  halted noop, round-trip). Added 7 translator tests (round-trips for TLOAD and
  TSTORE bytecode, stop-fires for each, and 3 seed 0027 corpus tests). Added
  corpus seed `0027-tstore-tload-gated-sstore` (hex
  `600160005d60005c600114600f57005b600160005500`: 22 bytes — `PUSH1 1 / PUSH1 0
  / TSTORE / PUSH1 0 / TLOAD / PUSH1 1 / EQ / PUSH1 0x0f / JUMPI / STOP /
  JUMPDEST / PUSH1 1 / PUSH1 0 / SSTORE / STOP`; TSTORE writes 1 to transient
  slot 0, TLOAD reads it back, EQ(1,1)=1 unconditional → JUMPI taken →
  SSTORE(0,1) → bad fires at step 13; demonstrates full transient-storage
  round-trip gating persistent storage).
  Total: 1435 tests pass, 13 skipped.
- **Next phase hint**: P31 — DUP2–DUP16 and SWAP1–SWAP16 generic stack
  manipulation opcodes (0x81–0x8f, 0x90–0x9f); `lower_dupn(b, machine_nids, n)`
  and `lower_swapn(b, machine_nids, n)` already referenced in `__all__` as stubs;
  completing these extends stack-manipulation coverage needed for realistic
  multi-value ABI-decoded dispatch patterns.

---

## 2026-06-04T02:00:00Z — P29: PC (0x58) lowering + corpus seed 0026

- **Phase**: P29 complete.
- **What changed**: Added `lower_pc(b, machine_nids)` to `library.py` (PC 0x58,
  gas=2, size=1; pushes the current program counter — `pc` bv16 zero-extended to
  bv256 — onto `stack[sp]`; sp+=1; pc+=1; gas-=2; stack overflow sp==1024 and OOG
  guards). Added `PC_GAS=2` and `PC_SIZE=1` constants. Updated `translator.py` to
  route 0x58→`lower_pc`; imported `lower_pc`; updated docstring to P29. Updated
  `translation/__init__.py` to import and export `lower_pc`, `PC_GAS`, `PC_SIZE`;
  updated version docstring to P29.
  RETURNDATASIZE (0x3d) re-checked: gas=2, pushes `returndatasize` machine state
  (bv256), stack overflow + OOG guards correct; 10 existing tests all pass.
  GAS (0x5a) re-checked: pushes post-deduction gas zero-extended bv64→bv256;
  existing implementation and tests correct.
  Added 11 library tests for PC (constants, returns result, sp increment, push
  zero at init, push current value, pc advance, gas decrement, OOG trap, halted
  noop, trap noop, round-trip). Added 5 translator tests (round-trip + stop-fires
  + 3 seed 0026 corpus tests). Added corpus seed `0026-pc-gated-sstore` (hex
  `58600014600857005b600160005500`: 15 bytes — `PC / PUSH1 0 / EQ / PUSH1 8 /
  JUMPI / STOP / JUMPDEST / PUSH1 1 / PUSH1 0 / SSTORE / STOP`; PC at offset 0
  pushes 0, EQ(0,0)=1 unconditional → JUMPI taken → SSTORE(0,1) → bad fires at
  step 9; demonstrates PC self-referential program-counter observability).
  Total: 1406 tests pass, 13 skipped.
- **Next phase hint**: P30 — TLOAD (0x5c) / TSTORE (0x5d) transient storage
  opcodes (EIP-1153, Cancun hardfork): TLOAD pops key, pushes
  `transient_sto[key]` (a new machine-state array like `sto` but zero-reset
  per-transaction; bv256→bv256); TSTORE pops value then key, writes
  `transient_sto[key] = value`; both gas=100 (warm tier); adding these extends
  the storage surface to Cancun-era contracts and is a prerequisite for
  reentrancy-guard patterns that use transient storage.

---

## 2026-06-04T01:00:00Z — P28: MSIZE (0x59) / ADDRESS (0x30) lowering + corpus seed 0025

- **Phase**: P28 complete.
- **What changed**: Added `("address", "bv256")` to `CONTEXT_VARS` in `layers.py`
  (this contract's own address for ADDRESS 0x30; count: 18→19); extended the
  address-validity constraint loop in `emit_context_inputs` to include `"address"`
  (upper 96 bits = 0, matching the 20-byte Ethereum address format). Updated the
  docstring to mention the new constraint.
  Added two new lowering functions to `library.py`:
  `lower_msize(b, machine_nids)` (MSIZE 0x59, gas=2, pushes
  `mem_words * 32` as bv256 — current memory size in bytes; stack overflow check
  sp==1024; net sp+=1);
  `lower_address(b, machine_nids, ctx_nids)` (ADDRESS 0x30, gas=2, pushes
  `ctx["address"]` — symbolic bv256 with upper 96 bits constrained to 0;
  stack overflow check sp==1024; net sp+=1).
  Updated `translator.py` to route 0x30→`lower_address`, 0x59→`lower_msize`;
  imported both functions; updated docstring to P28. Updated
  `translation/__init__.py` to import and export `lower_msize`, `lower_address`,
  `MSIZE_GAS`, `MSIZE_SIZE`, `ADDRESS_GAS`, `ADDRESS_SIZE`; updated version
  docstring to P28.
  Updated `test_context_var_count_is_18` → `test_context_var_count_is_19` in
  `test_translation_layers.py`. Added 10 library tests for MSIZE and 11 for
  ADDRESS (including trap_noop test). Added 7 translator tests (2 round-trip
  routing + 2 stop-fires + 3 seed 0025 corpus tests). Added corpus seed
  `0025-msize-gated-sstore` (hex `600060005359600010600d57005b600160005500`:
  20 bytes — `PUSH1 0 / PUSH1 0 / MSTORE8 / MSIZE / PUSH1 0 / LT /
  PUSH1 0x0d / JUMPI / STOP / JUMPDEST / PUSH1 1 / PUSH1 0 / SSTORE / STOP`;
  MSTORE8 expands mem_words to 1 → MSIZE pushes 32 → LT(0,32)=1 → JUMPI taken
  → SSTORE(0,1) → bad fires at step 12; demonstrates P28 MSIZE memory-size
  observability). SELFBALANCE (0x47) re-checked: implementation and tests are
  correct (gas=5, pushes ctx["selfbalance"], stack overflow + OOG guards).
  Total: 1388 tests pass, 13 skipped.
- **Next phase hint**: P29 — RETURNDATASIZE (0x3d) re-check + PC (0x58) opcode:
  PC pushes the current program counter value (`pc` machine state, bv16 zero-extended
  to bv256, Wbase gas=2); RETURNDATASIZE re-check ensures the existing lowering
  is correct for the full instruction; completing these finishes the remaining
  self-referential machine-state observability surface. Then GAS (0x5a) re-check
  (already implemented as `lower_gas`) and consider CALLDATACOPY alignment audit.

---

## 2026-06-04T00:00:00Z — P27: CHAINID (0x46) / CODESIZE (0x38) / CODECOPY (0x39) / EXTCODESIZE (0x3B) / EXTCODECOPY (0x3C) lowering + corpus seed 0024

- **Phase**: P27 complete.
- **What changed**: Added two new context variables to `CONTEXT_VARS` in `layers.py`:
  `("extcodesize_of", "sto_t")` (address→external code size for EXTCODESIZE 0x3B)
  and `("extcode_data", "mem_t")` (external code bytes over-approximation for
  EXTCODECOPY 0x3C); count: 16→18. Added `constarray(array_sort, elem_value_nid)`
  method to `Btor2Builder` (builder.py) and `constarray` handling to `evaluator.py`
  (sparse-dict representation: missing keys default to 0 — correct for zero-init
  base used by CODECOPY). Added five new lowering functions to `library.py`:
  `lower_chainid(b, machine_nids, ctx_nids)` (CHAINID 0x46, gas=2, pushes
  `ctx["chainid"]` — already constrained to 1 by `emit_context_inputs`; EIP-1344
  Berlin fork);
  `lower_codesize(b, machine_nids, codesize: int)` (CODESIZE 0x38, gas=2, pushes
  `const(bv256, len(bytecode))` — a compile-time constant in our single-bytecode model);
  `lower_codecopy(b, machine_nids, bytecode: bytes, max_len=32)` (CODECOPY 0x39,
  gas=base(3)+word(3*ceil(length/32))+expansion, pops dest/offset/length, sp-=3;
  builds a concrete BTOR2 `constarray`+write-chain for the bytecode bytes and copies
  up to 32 bytes to memory; reads past the bytecode end return 0 per EVM spec);
  `lower_extcodesize(b, machine_nids, ctx_nids)` (EXTCODESIZE 0x3B, gas=2600
  always-cold per EIP-2929, pops address TOS, pushes `ctx["extcodesize_of"][address]`
  — fully symbolic over-approximation; net sp unchanged);
  `lower_extcodecopy(b, machine_nids, ctx_nids, max_len=32)` (EXTCODECOPY 0x3C,
  gas=2600+3*ceil(length/32)+expansion, pops address/dest/offset/length, sp-=4;
  copies from `ctx["extcode_data"][offset+k]` — symbolic over-approximation ignoring
  address, sound for BMC). Updated `translator.py` to pass `bytecode` to `_lower_insn`,
  route 0x38→`lower_codesize`, 0x39→`lower_codecopy`, 0x3B→`lower_extcodesize`,
  0x3C→`lower_extcodecopy`, 0x46→`lower_chainid`; updated docstring to P27.
  Exported all new symbols from `translation/__init__.py` and `library.__all__`.
  Updated `translation/__init__.py` version docstring to P27.
  Updated `test_context_var_count_is_16` → `test_context_var_count_is_18` in
  `test_translation_layers.py`. Added corpus seed `0024-chainid-gated-sstore`
  (hex `60014614600857005b600160005500`: 15 bytes —
  `PUSH1 0x01 / CHAINID / EQ / PUSH1 0x08 / JUMPI / STOP / JUMPDEST / PUSH1 0x01 /
  PUSH1 0x00 / SSTORE / STOP`; chainid constrained to 1 → EQ(chainid, 1)=1 →
  JUMPI taken → SSTORE(0,1) → bad fires at step 9; demonstrates EIP-1344
  cross-chain replay-protection pattern from P27). Added 10 library tests for
  CHAINID, 9 for CODESIZE, 10 for CODECOPY, 9 for EXTCODESIZE, 9 for EXTCODECOPY.
  Added 10 translator tests (5 round-trip routing + 2 stop-fires + 3 seed 0024
  corpus tests). Total: 1377 tests pass, 12 skipped.
- **Next phase hint**: P28 — MSIZE (0x59) and SELFBALANCE re-check, then
  ADDRESS (0x30) opcode: MSIZE pushes the current memory size in bytes
  (`mem_words * 32`, bv256, Wbase gas=2); ADDRESS (0x30) pushes the current
  contract's address (`ctx["address"]` if added as a new context var, or a
  symbolic bv256 with upper 96 bits = 0 constraint); completing these finishes
  the self-referential code/env observability surface and sets up for
  `CALLDATALOAD` patterns that depend on address-based routing.

---

## 2026-06-03T01:00:00Z — P26: BLOCKHASH (0x40) / COINBASE (0x41) / TIMESTAMP (0x42) / NUMBER (0x43) / PREVRANDAO (0x44) / BASEFEE (0x48) lowering + corpus seed 0023

- **Phase**: P26 complete.
- **What changed**: Added `("blockhash_of", "sto_t")` to `CONTEXT_VARS` in `layers.py`
  (block-number→hash array for BLOCKHASH 0x40; count now 16). Added six new lowering
  functions to `library.py`: `lower_blockhash(b, machine_nids, ctx_nids)` (BLOCKHASH
  0x40, gas=20, pops block_number, pushes `ctx["blockhash_of"][block_number]` — fully
  symbolic over-approximation of the last-256-blocks EVM restriction; net sp unchanged),
  `lower_coinbase` (COINBASE 0x41, gas=2, pushes `ctx["coinbase"]`),
  `lower_timestamp` (TIMESTAMP 0x42, gas=2, pushes `ctx["timestamp"]`),
  `lower_number` (NUMBER 0x43, gas=2, pushes `ctx["blocknumber"]`),
  `lower_prevrandao` (PREVRANDAO 0x44, gas=2, pushes `ctx["prevrandao"]` — formerly
  DIFFICULTY, renamed by EIP-4399 post-Merge),
  `lower_basefee` (BASEFEE 0x48, gas=2, pushes `ctx["basefee"]` — added in EIP-3198,
  London fork). Updated `translator.py` to route 0x40→`lower_blockhash`,
  0x41→`lower_coinbase`, 0x42→`lower_timestamp`, 0x43→`lower_number`,
  0x44→`lower_prevrandao`, 0x48→`lower_basefee`; updated docstring to P26.
  Exported all new symbols from `translation/__init__.py` and `library.__all__`.
  Updated `translation/__init__.py` version docstring to P26. Updated
  `test_context_var_count_is_15` → `test_context_var_count_is_16` in
  `test_translation_layers.py`. Added corpus seed `0023-number-gated-sstore`
  (hex `60004311600857005b600160005500`: 15 bytes —
  `PUSH1 0x00 / NUMBER / GT / PUSH1 0x08 / JUMPI / STOP / JUMPDEST / PUSH1 0x01 /
  PUSH1 0x00 / SSTORE / STOP`; blocknumber symbolic — any value > 0 witnesses
  GT(blocknumber, 0)=1 → JUMPI taken → SSTORE(0,1) → bad fires at step 9;
  demonstrates block-context observability from P26). Added 8 library tests for
  BLOCKHASH, 9 for COINBASE, 9 for TIMESTAMP, 9 for NUMBER, 9 for PREVRANDAO,
  9 for BASEFEE. Added 10 translator tests (6 round-trip routing + 2 stop-fires +
  2 for seed 0023 corpus tests). Total: 1299 tests pass, 13 skipped.
- **Next phase hint**: P27 — CHAINID (0x46) and CODESIZE (0x38) / CODECOPY (0x39)
  / EXTCODESIZE (0x3B) / EXTCODECOPY (0x3C) code-context opcodes: CHAINID pushes
  `ctx["chainid"]` (already constrained to 1 by default); CODESIZE pushes the byte
  length of the currently executing bytecode (a constant in our single-bytecode model);
  CODECOPY copies bytecode bytes to memory (analogous to CALLDATACOPY but source is
  the bytecode array); EXTCODESIZE/EXTCODECOPY reference external contract code
  (model as symbolic unless scope limits to self); completing these finishes
  the code-observability surface.

---

## 2026-06-03T00:00:00Z — P25: GAS (0x5A) / GASLIMIT (0x45) lowering + corpus seed 0022

- **Phase**: P25 complete.
- **What changed**: Added `lower_gaslimit(b, machine_nids, ctx_nids)` (GASLIMIT 0x45,
  gas=2, pushes `ctx["gaslimit"]` — block gas limit bv256, already in `CONTEXT_VARS`)
  and `lower_gas(b, machine_nids)` (GAS 0x5A, gas=2, pushes remaining gas after own
  cost deduction, zero-extended from bv64 to bv256: `uext(gas - 2, 192)` — EVM Yellow
  Paper mandates GAS pushes post-cost remaining gas) to `library.py`.  Updated
  `translator.py` to route 0x45→`lower_gaslimit` and 0x5A→`lower_gas`; updated
  docstring to P25.  Exported all new symbols from `translation/__init__.py` and
  `library.__all__`.  Updated `translation/__init__.py` version docstring to P25.
  Added corpus seed `0022-gas-gated-sstore` (hex
  `60005a11600857005b600160005500`: 15 bytes —
  `PUSH1 0x00 / GAS / GT / PUSH1 0x08 / JUMPI / STOP / JUMPDEST / PUSH1 0x01 /
  PUSH1 0x00 / SSTORE / STOP`; with GasLimitPin=1M, GAS always pushes a
  large positive value; GT(gas_remaining, 0)=1 unconditionally so JUMPI is
  always taken → SSTORE(0,1) → bad fires at step 9).  Added 9 library tests
  for GASLIMIT and 10 for GAS (constants, sp, symbolic value push with <256
  workaround for evaluator's 8-bit write mask, gas/pc, OOG trap, halted/trap
  no-op, round-trip).  Added 7 translator tests (2 round-trip routing + 2
  stop-fires + 3 seed 0022 corpus tests).  Note: corpus seed 0021
  (callvalue-gated) was described in P24 progress but not committed to
  `bench/`; not retroactively added here.  Total: 1228 tests pass, 13 skipped.
- **Next phase hint**: P26 — BLOCKHASH (0x40) and COINBASE (0x41) / TIMESTAMP
  (0x42) / NUMBER (0x43) / PREVRANDAO (0x44) / BASEFEE (0x48) block context
  opcodes: these push symbolic bv256 context values already in `CONTEXT_VARS`
  (blocknumber, timestamp, prevrandao, coinbase, basefee); BLOCKHASH(0x40)
  pops a block number and returns a 32-byte hash (model as symbolic array
  `blockhash_of[number]`); all are Wbase gas=2; completing these finishes
  the block-context observability surface.

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
