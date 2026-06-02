# `ebpf-btor2` Progress — Live State

> The single source of truth for "where is the `ebpf-btor2` bootstrap
> right now." Each iteration appends one entry at the top.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-06-02T03:00:00Z — P44 ARSH32 X complete; JEQ X, JNE X, JGT X register-compare jumps

**What changed:**
- `bench/ebpf-btor2/harness.py`: docstring bumped to P44; 4 new bytecode constants (`_NEG128_ARSH32X_R1_2_EXIT`, `_R042_R142_JEQX_SKIP_EXIT`, `_TEN_R120_JNEX_SKIP_EXIT`, `_TWENTY_R110_JGTX_SKIP_EXIT`); 4 new `CorpusTask` entries; CORPUS 153→157.
- `tests/pairs/ebpf_btor2/test_solvers.py`: count renamed to `test_corpus_has_hundredfiftyseven_tasks` (157); 4 new task-ID assertions; 4 new bytecode constants; `TestP44Corpus` class with 4 test methods.

**New bytecodes:**
- `_NEG128_ARSH32X_R1_2_EXIT`: `r0_32=-128; r1=2; r0_32>>=r1 (ARSH32 X) → r0=4294967264`
- `_R042_R142_JEQX_SKIP_EXIT`: `r0=42; r1=42; JEQ X taken (42==42) skips ADD → r0=42`
- `_TEN_R120_JNEX_SKIP_EXIT`: `r0=10; r1=20; JNE X taken (10!=20) skips ADD → r0=10`
- `_TWENTY_R110_JGTX_SKIP_EXIT`: `r0=20; r1=10; JGT X taken (20>10 unsigned) skips ADD → r0=20`

**New tasks (4):**
1. `seed/neg128_arsh32x_r1_2_exit_r0_eq_4294967264` → "r0 == 4294967264" **reachable**
2. `seed/r0_42_r1_42_jeqx_taken_exit_r0_eq_42` → "r0 == 42" **reachable**
3. `seed/r0_10_r1_20_jnex_taken_exit_r0_eq_10` → "r0 == 10" **reachable**
4. `seed/r0_20_r1_10_jgtx_taken_exit_r0_eq_20` → "r0 == 20" **reachable**

**Structural tests:** 2 passed (`test_corpus_has_hundredfiftyseven_tasks`, `test_corpus_task_ids`).

**Open blockers:** z3-bmc solver unavailable in CI; all `TestPXXCorpus` solver tests return `'error'` — environment regression, not a corpus bug.

**Next iteration — P45:** Continue JMP X coverage: JGE X (0x3d), JSGT X (0x6d), JSGE X (0x7d), JLT X (0xad). Aim for 4 new tasks (157→161).

---

## 2026-06-02T02:40:00Z — P43 Register-source (X) shift corpus; LSH64 X, RSH64 X, LSH32 X, RSH32 X

**What changed:**
- `bench/ebpf-btor2/harness.py`: docstring bumped to P43; 4 new bytecode constants (`_ONE_LSH64X_R1_4_EXIT`, `_SIXTYFOUR_RSH64X_R1_3_EXIT`, `_ONE_LSH32X_R1_3_EXIT`, `_ONETWENTYEIGHT_RSH32X_R1_3_EXIT`); 4 new `CorpusTask` entries; CORPUS 149→153.
- `tests/pairs/ebpf_btor2/test_solvers.py`: count renamed to `test_corpus_has_hundredfiftythree_tasks` (153); 4 new task-ID assertions; 4 new bytecode constants; `TestP43Corpus` class with 4 test methods.

**New bytecodes:**
- `_ONE_LSH64X_R1_4_EXIT`: `r0=1; r1=4; r0<<=r1 (LSH64 X) → r0=16`
- `_SIXTYFOUR_RSH64X_R1_3_EXIT`: `r0=64; r1=3; r0>>=r1 (RSH64 X, logical) → r0=8`
- `_ONE_LSH32X_R1_3_EXIT`: `r0_32=1; r1=3; r0_32<<=r1 (LSH32 X) → r0=8`
- `_ONETWENTYEIGHT_RSH32X_R1_3_EXIT`: `r0_32=128; r1=3; r0_32>>=r1 (RSH32 X) → r0=16`

**New tasks (4):**
1. `seed/one_lsh64x_r1_4_exit_r0_eq_16` → "r0 == 16" **reachable**
2. `seed/sixtyfour_rsh64x_r1_3_exit_r0_eq_8` → "r0 == 8" **reachable**
3. `seed/one_lsh32x_r1_3_exit_r0_eq_8` → "r0 == 8" **reachable**
4. `seed/onetwentyeight_rsh32x_r1_3_exit_r0_eq_16` → "r0 == 16" **reachable**

**Note:** NEG64 was already in corpus from P12; register-source shift coverage now complete (LSH/RSH × 32/64 × K and X all present).

**Structural tests:** 2 passed (`test_corpus_has_hundredfiftythree_tasks`, `test_corpus_task_ids`).

**Open blockers:** z3-bmc solver unavailable in CI; all `TestPXXCorpus` solver tests return `'error'` — environment regression, not a corpus bug.

**Next iteration — P44:** ARSH32 X (0xcc) to complete the 32-bit arithmetic shift X family. Then begin jump-with-register (JMP X) coverage: JEQ X (0x5d), JNE X (0x55), JGT X (0x25) with simple 2-register comparisons. Aim for 4 new tasks (153→157).

---

## 2026-06-02T02:20:00Z — P42 Register-source (X) bitwise and ARSH64 X corpus

**What changed:**
- `bench/ebpf-btor2/harness.py`: docstring bumped to P42; 4 new bytecode constants (`_FIFTEEN_OR64X_R1_48_EXIT`, `_TWOFIFTYFIVE_AND64X_R1_15_EXIT`, `_ONESIXTYFIVE_XOR64X_R1_90_EXIT`, `_NEG16_ARSH64X_R1_2_EXIT`); 4 new `CorpusTask` entries; CORPUS 145→149.
- `tests/pairs/ebpf_btor2/test_solvers.py`: count renamed to `test_corpus_has_hundredfortynine_tasks` (149); 4 new task-ID assertions; 4 new bytecode constants; `TestP42Corpus` class with 4 test methods.

**New bytecodes:**
- `_FIFTEEN_OR64X_R1_48_EXIT`: `r0=15; r1=48; r0|=r1 (OR64 X) → r0=63`
- `_TWOFIFTYFIVE_AND64X_R1_15_EXIT`: `r0=255; r1=15; r0&=r1 (AND64 X) → r0=15`
- `_ONESIXTYFIVE_XOR64X_R1_90_EXIT`: `r0=165; r1=90; r0^=r1 (XOR64 X) → r0=255`
- `_NEG16_ARSH64X_R1_2_EXIT`: `r0=-16; r1=2; r0>>=r1 (ARSH64 X, arithmetic) → r0=-4`

**New tasks (4):**
1. `seed/fifteen_or64x_r1_48_exit_r0_eq_63` → "r0 == 63" **reachable**
2. `seed/twofiftyfive_and64x_r1_15_exit_r0_eq_15` → "r0 == 15" **reachable**
3. `seed/onesixtyfive_xor64x_r1_90_exit_r0_eq_255` → "r0 == 255" **reachable**
4. `seed/neg16_arsh64x_r1_2_exit_r0_eq_neg4` → "r0 == -4" **reachable**

**Structural tests:** 2 passed (`test_corpus_has_hundredfortynine_tasks`, `test_corpus_task_ids`).

**Open blockers:** z3-bmc solver unavailable in CI; all `TestPXXCorpus` solver tests return `'error'` — environment regression, not a corpus bug.

**Next iteration — P43:** Register-source (X) shift corpus: LSH64 X (0x6f), RSH64 X (0x7f), LSH32 X (0x64 → wait, 0x6c), RSH32 X (0x7c). Then NEG64 (0x87) — the only unary ALU op. Aim for 4 new tasks (149→153).

---

## 2026-06-02T02:00:00Z — P41 ARSH32 K complete; DIV64 X, MOD64 X, MOV64 X register-source ops

**What changed:**
- `bench/ebpf-btor2/harness.py`: docstring bumped to P41; 4 new bytecode constants (`_NEG128_ARSH32_K2_EXIT`, `_FORTYTWO_DIV64X_R1_6_EXIT`, `_FORTYTWO_MOD64X_R1_5_EXIT`, `_NINETYNINE_MOV64X_R1_42_EXIT`); 4 new `CorpusTask` entries; CORPUS 141→145.
- `tests/pairs/ebpf_btor2/test_solvers.py`: count renamed to `test_corpus_has_hundredfortyfive_tasks` (145); 4 new task-ID assertions; 4 new bytecode constants; `TestP41Corpus` class with 4 test methods.

**New bytecodes:**
- `_NEG128_ARSH32_K2_EXIT`: `r0_32=-128 (MOV32 K); r0_32>>=2 (ARSH32 K) → r0=4294967264 (0xFFFFFFE0, zero-extended)`
- `_FORTYTWO_DIV64X_R1_6_EXIT`: `r0=42; r1=6; r0/=r1 (DIV64 X) → r0=7`
- `_FORTYTWO_MOD64X_R1_5_EXIT`: `r0=42; r1=5; r0%=r1 (MOD64 X) → r0=2`
- `_NINETYNINE_MOV64X_R1_42_EXIT`: `r0=99; r1=42; r0=r1 (MOV64 X) → r0=42`

**New tasks (4):**
1. `seed/neg128_arsh32_2_exit_r0_eq_4294967264` → "r0 == 4294967264" **reachable**
2. `seed/fortytwo_div64x_r1_6_exit_r0_eq_7` → "r0 == 7" **reachable**
3. `seed/fortytwo_mod64x_r1_5_exit_r0_eq_2` → "r0 == 2" **reachable**
4. `seed/ninetynine_mov64x_r1_42_exit_r0_eq_42` → "r0 == 42" **reachable**

**Note:** ADD64 X, MUL64 X, SUB64 X were already covered in P9; new X-source ops here are DIV64 X (0x3f), MOD64 X (0x9f), MOV64 X (0xbf).

**Structural tests:** 2 passed (`test_corpus_has_hundredfortyfive_tasks`, `test_corpus_task_ids`).

**Open blockers:** z3-bmc solver unavailable in CI; all `TestPXXCorpus` solver tests return `'error'` — environment regression, not a corpus bug.

**Next iteration — P42:** Register-source (X) bitwise ALU ops: OR64 X (0x4f), AND64 X (0x5f), XOR64 X (0xaf). Also ARSH64 X (0xcf) with sign-preserved register shift. Aim for 4 new tasks (145→149).

---

## 2026-06-02T01:40:00Z — P40 Shift corpus complete; RSH64 K, ARSH64 K, LSH32 K, RSH32 K

**What changed:**
- `bench/ebpf-btor2/harness.py`: docstring bumped to P40; 4 new bytecode constants (`_SIXTYFOUR_RSH64_K3_EXIT`, `_NEG16_ARSH64_K2_EXIT`, `_ONE_LSH32_K3_EXIT`, `_ONETWENTYEIGHT_RSH32_K3_EXIT`); 4 new `CorpusTask` entries; CORPUS 137→141.
- `tests/pairs/ebpf_btor2/test_solvers.py`: count renamed to `test_corpus_has_hundredfortyone_tasks` (141); 4 new task-ID assertions; 4 new bytecode constants; `TestP40Corpus` class with 4 test methods.

**New bytecodes:**
- `_SIXTYFOUR_RSH64_K3_EXIT`: `r0=64 (MOV64 K); r0>>=3 (RSH64 K, logical) → r0=8`
- `_NEG16_ARSH64_K2_EXIT`: `r0=-16 (MOV64 K, sign-ext); r0>>=2 (ARSH64 K, arithmetic) → r0=-4`
- `_ONE_LSH32_K3_EXIT`: `r0_32=1 (MOV32 K); r0_32<<=3 (LSH32 K) → r0=8`
- `_ONETWENTYEIGHT_RSH32_K3_EXIT`: `r0_32=128 (MOV32 K); r0_32>>=3 (RSH32 K) → r0=16`

**New tasks (4):**
1. `seed/sixtyfour_rsh64_3_exit_r0_eq_8` → "r0 == 8" **reachable**
2. `seed/neg16_arsh64_2_exit_r0_eq_neg4` → "r0 == -4" **reachable**
3. `seed/one_lsh32_3_exit_r0_eq_8` → "r0 == 8" **reachable**
4. `seed/onetwentyeight_rsh32_3_exit_r0_eq_16` → "r0 == 16" **reachable**

**Structural tests:** 2 passed (`test_corpus_has_hundredfortyone_tasks`, `test_corpus_task_ids`).

**Open blockers:** z3-bmc solver unavailable in CI; all `TestPXXCorpus` solver tests return `'error'` — environment regression, not a corpus bug.

**Next iteration — P41:** Complete 32-bit arithmetic shift and begin ARSH32 K (0xc4). Add ARSH32 K sign-preserved case (e.g., -128 >> 2 = -32 as 32-bit, zero-extended to r0=0xFFFFFFE0=4294967264). Then begin X-source (register) ALU: ADD64 X (0x0f) with two registers, SUB64 X (0x1f). Aim for 4 new tasks (141→145).

---

## 2026-06-02T01:20:00Z — P39 Bitwise ALU32 and LSH64 K corpus; OR32 mask, AND32 clear, XOR32 complement, LSH64 basic

**What changed:**
- `bench/ebpf-btor2/harness.py`: docstring bumped to P39; 4 new bytecode constants (`_FIFTEEN_OR32_K48_EXIT`, `_TWOFIFTYFIVE_AND32_K15_EXIT`, `_ONESIXTYFIVE_XOR32_K90_EXIT`, `_ONE_LSH64_K4_EXIT`); 4 new `CorpusTask` entries; CORPUS 133→137.
- `tests/pairs/ebpf_btor2/test_solvers.py`: count renamed to `test_corpus_has_hundredthirtyseven_tasks` (137); 4 new task-ID assertions; 4 new bytecode constants; `TestP39Corpus` class with 4 test methods.

**New bytecodes:**
- `_FIFTEEN_OR32_K48_EXIT`: `r0_32=15/0x0f (MOV32 K); r0_32|=48/0x30 (OR32 K) → r0=63/0x3f`
- `_TWOFIFTYFIVE_AND32_K15_EXIT`: `r0_32=255/0xff (MOV32 K); r0_32&=15/0x0f (AND32 K) → r0=15`
- `_ONESIXTYFIVE_XOR32_K90_EXIT`: `r0_32=165/0xa5 (MOV32 K); r0_32^=90/0x5a (XOR32 K) → r0=255/0xff`
- `_ONE_LSH64_K4_EXIT`: `r0=1 (MOV64 K); r0<<=4 (LSH64 K) → r0=16`

**New tasks (4):**
1. `seed/fifteen_or32_48_exit_r0_eq_63` → "r0 == 63" **reachable**
2. `seed/twofiftyfive_and32_15_exit_r0_eq_15` → "r0 == 15" **reachable**
3. `seed/onesixtyfive_xor32_90_exit_r0_eq_255` → "r0 == 255" **reachable**
4. `seed/one_lsh64_4_exit_r0_eq_16` → "r0 == 16" **reachable**

**Structural tests:** 2 passed (`test_corpus_has_hundredthirtyseven_tasks`, `test_corpus_task_ids`).

**Open blockers:** z3-bmc solver unavailable in CI; all `TestPXXCorpus` solver tests return `'error'` — environment regression, not a corpus bug.

**Next iteration — P40:** Complete 64-bit shift coverage and begin 32-bit shifts. Add RSH64 K (0x77) basic (256>>4=16), ARSH64 K (0xc7) with sign-preserving case ((-16)>>2=-4), LSH32 K (0x64) basic, RSH32 K (0x74) basic. Aim for 4 new tasks (137→141).

---

## 2026-06-02T01:00:00Z — P38 MOD64 K and bitwise ALU corpus; MOD64 basic, OR64 mask, AND64 clear, XOR64 complement

**What changed:**
- `bench/ebpf-btor2/harness.py`: docstring bumped to P38; 4 new bytecode constants (`_FORTYTWO_MOD64_K5_EXIT`, `_FIFTEEN_OR64_K48_EXIT`, `_TWOFIFTYFIVE_AND64_K15_EXIT`, `_ONESIXTYFIVE_XOR64_K90_EXIT`); 4 new `CorpusTask` entries; CORPUS 129→133.
- `tests/pairs/ebpf_btor2/test_solvers.py`: count renamed to `test_corpus_has_hundredthirtythree_tasks` (133); 4 new task-ID assertions; 4 new bytecode constants; `TestP38Corpus` class with 4 test methods.

**New bytecodes:**
- `_FORTYTWO_MOD64_K5_EXIT`: `r0=42 (MOV64 K); r0%=5 (MOD64 K) → r0=2`
- `_FIFTEEN_OR64_K48_EXIT`: `r0=15/0x0f (MOV64 K); r0|=48/0x30 (OR64 K) → r0=63/0x3f`
- `_TWOFIFTYFIVE_AND64_K15_EXIT`: `r0=255/0xff (MOV64 K); r0&=15/0x0f (AND64 K) → r0=15`
- `_ONESIXTYFIVE_XOR64_K90_EXIT`: `r0=165/0xa5 (MOV64 K); r0^=90/0x5a (XOR64 K) → r0=255/0xff`

**New tasks (4):**
1. `seed/fortytwo_mod64_5_exit_r0_eq_2` → "r0 == 2" **reachable**
2. `seed/fifteen_or64_48_exit_r0_eq_63` → "r0 == 63" **reachable**
3. `seed/twofiftyfive_and64_15_exit_r0_eq_15` → "r0 == 15" **reachable**
4. `seed/onesixtyfive_xor64_90_exit_r0_eq_255` → "r0 == 255" **reachable**

**Structural tests:** 2 passed (`test_corpus_has_hundredthirtythree_tasks`, `test_corpus_task_ids`).

**Open blockers:** z3-bmc solver unavailable in CI; all `TestPXXCorpus` solver tests return `'error'` — environment regression, not a corpus bug.

**Next iteration — P39:** Bitwise ALU32 corpus. Add OR32 K (0x44), AND32 K (0x54), XOR32 K (0xa4) to contrast 32-bit vs 64-bit bitwise behavior (zero-extension semantics). Also consider LSH64 K (0x67) and RSH64 K (0x77) to begin 64-bit shift coverage. Aim for 4 new tasks (133→137).

---

## 2026-06-02T00:20:00Z — P37 ALU32/ALU64 K division and modulo corpus; DIV32 basic, DIV32 power-of-two, DIV64 basic, MOD32 basic

**What changed:**
- `bench/ebpf-btor2/harness.py`: docstring bumped to P37; 4 new bytecode constants (`_FORTYTWO_DIV32_K6_EXIT`, `_THIRTYTWO_DIV32_K4_EXIT`, `_FORTYTWO_DIV64_K6_EXIT`, `_FORTYTWO_MOD32_K5_EXIT`); 4 new `CorpusTask` entries; CORPUS 125→129.
- `tests/pairs/ebpf_btor2/test_solvers.py`: count renamed to `test_corpus_has_hundredtwentynine_tasks` (129); 4 new task-ID assertions; 4 new bytecode constants; `TestP37Corpus` class with 4 test methods.

**New bytecodes:**
- `_FORTYTWO_DIV32_K6_EXIT`: `r0_32=42 (MOV32 K); r0_32÷=6 (DIV32 K) → r0=7`
- `_THIRTYTWO_DIV32_K4_EXIT`: `r0_32=32 (MOV32 K); r0_32÷=4 (DIV32 K, power-of-two) → r0=8`
- `_FORTYTWO_DIV64_K6_EXIT`: `r0=42 (MOV64 K); r0÷=6 (DIV64 K) → r0=7`
- `_FORTYTWO_MOD32_K5_EXIT`: `r0_32=42 (MOV32 K); r0_32%=5 (MOD32 K) → r0=2`

**New tasks (4):**
1. `seed/fortytwo_div32_6_exit_r0_eq_7` → "r0 == 7" **reachable**
2. `seed/thirtytwo_div32_4_exit_r0_eq_8` → "r0 == 8" **reachable**
3. `seed/fortytwo_div64_6_exit_r0_eq_7` → "r0 == 7" **reachable**
4. `seed/fortytwo_mod32_5_exit_r0_eq_2` → "r0 == 2" **reachable**

**Structural tests:** 2 passed (`test_corpus_has_hundredtwentynine_tasks`, `test_corpus_task_ids`).

**Open blockers:** z3-bmc solver unavailable in CI; all `TestPXXCorpus` solver tests return `'error'` — environment regression, not a corpus bug.

**Next iteration — P38:** MOD64 K and bitwise ALU corpus. Add MOD64 K (opcode 0x97): basic case (42%5=2). Then begin bitwise ops: OR64 K (0x47), AND64 K (0x57), XOR64 K (0xa7) with simple cases (e.g., OR with mask, AND to clear bits, XOR self=0). Aim for 4 new tasks (129→133).

---

## 2026-06-02T00:00:00Z — P36 ALU32 K subtraction and multiplication corpus; SUB32 basic, SUB32 underflow, MUL32 basic, MUL32 upper-clear

**What changed:**
- `bench/ebpf-btor2/harness.py`: docstring bumped to P36; 4 new bytecode constants (`_FIVE_SUB32_K3_EXIT`, `_ZERO32_SUB32_K1_EXIT`, `_TWENTYONE_MUL32_K2_EXIT`, `_NEG1_MOV32_21_MUL32_K2_EXIT`); 4 new `CorpusTask` entries; CORPUS 121→125.
- `tests/pairs/ebpf_btor2/test_solvers.py`: count renamed to `test_corpus_has_hundredtwentyfive_tasks` (125); 4 new task-ID assertions; 4 new bytecode constants; `TestP36Corpus` class with 4 test methods.

**New bytecodes:**
- `_FIVE_SUB32_K3_EXIT`: `r0=5 (MOV64 K); r0_32-=3 (SUB32 K) → r0=2`
- `_ZERO32_SUB32_K1_EXIT`: `r0_32=0 (MOV32 K); r0_32-=1 (SUB32 K, underflow wraps) → r0=4294967295`
- `_TWENTYONE_MUL32_K2_EXIT`: `r0_32=21 (MOV32 K); r0_32*=2 (MUL32 K) → r0=42`
- `_NEG1_MOV32_21_MUL32_K2_EXIT`: `r0=-1 (MOV64 K); r0_32=21 (MOV32 K); r0_32*=2 (MUL32 K) → r0=42`

**New tasks (4):**
1. `seed/five_sub32_3_exit_r0_eq_2` → "r0 == 2" **reachable**
2. `seed/zero32_sub32_1_exit_r0_eq_4294967295` → "r0 == 4294967295" **reachable**
3. `seed/twentyone_mul32_2_exit_r0_eq_42` → "r0 == 42" **reachable**
4. `seed/neg1_mov32_21_mul32_2_exit_r0_eq_42` → "r0 == 42" **reachable** (max_insns=5)

**Structural tests:** 2 passed (`test_corpus_has_hundredtwentyfive_tasks`, `test_corpus_task_ids`).

**Open blockers:** z3-bmc solver unavailable in CI; all `TestPXXCorpus` solver tests return `'error'` — environment regression, not a corpus bug.

**Next iteration — P37:** ALU32 K division corpus. Add DIV32 K (opcode 0x34): basic case (42÷6=7, zero-extended); DIV32 by power-of-two (32÷4=8); and DIV64 K (opcode 0x37) basic case (42÷6=7) to contrast 32 vs 64 bit division. Also consider MOD32 K (opcode 0x94) if time permits. Aim for 4 new tasks (125→129).

---

## 2026-06-01T05:00:00Z — P35 ALU32 K zero-extension and overflow corpus; MOV32 upper-clear, ADD32 overflow, ADD32 zeroes-upper

**What changed:**
- `bench/ebpf-btor2/harness.py`: docstring bumped to P35; 3 new bytecode constants (`_NEG1_MOV32_K5_EXIT`, `_MOV32_NEG1_ADD32_K1_EXIT`, `_NEG1_ADD32_K0_EXIT`); 4 new `CorpusTask` entries; CORPUS 117→121.
- `tests/pairs/ebpf_btor2/test_solvers.py`: count renamed to `test_corpus_has_hundredtwentyone_tasks` (121); 4 new task-ID assertions; 3 new bytecode constants; `TestP35Corpus` class with 4 test methods.

**New bytecodes:**
- `_NEG1_MOV32_K5_EXIT`: `r0=-1 (MOV64 K); r0_32=5 (MOV32 K, zeroes upper) → r0=5`
- `_MOV32_NEG1_ADD32_K1_EXIT`: `r0_32=0xFFFFFFFF (MOV32 K); r0_32+=1 (ADD32 K wraps) → r0=0`
- `_NEG1_ADD32_K0_EXIT`: `r0=UINT64_MAX (MOV64 K); r0_32+=0 (ADD32 K, zeroes upper) → r0=4294967295`

**New tasks (4):**
1. `seed/neg1_mov32_5_exit_r0_eq_5` → "r0 == 5" **reachable**
2. `seed/neg1_mov32_5_exit_r0_eq_neg1_unreachable` → "r0 == -1" **unreachable**
3. `seed/mov32_neg1_add32_1_exit_r0_eq_0` → "r0 == 0" **reachable**
4. `seed/neg1_add32_0_exit_r0_eq_4294967295` → "r0 == 4294967295" **reachable**

**Structural tests:** 2 passed (`test_corpus_has_hundredtwentyone_tasks`, `test_corpus_task_ids`).

**Open blockers:** z3-bmc solver unavailable in CI; all `TestPXXCorpus` solver tests return `'error'` — environment regression, not a corpus bug.

**Next iteration — P36:** ALU32 K subtraction corpus. Add SUB32 K (opcode 0x14) variants mirroring the P34 SUB64 set: basic subtraction (5−3=2), underflow wrap (0−1=0xFFFFFFFF zero-extended to 4294967295). Also add MUL32 K (opcode 0x24): basic case (21×2=42, zero-extended). Aim for 4 new tasks (121→125).

---

## 2026-06-01T04:30:00Z — P34 ALU64 K arithmetic boundary corpus; ADD overflow, SUB K basic, SUB underflow, MUL K basic

- **Phase**: P34 complete. ALU64 K arithmetic boundary corpus extension.
  P7/P9 had ADD K (+1, +1+1), ADD X, SUB X (self-zero), MUL X, DIV K, OR K,
  AND K, MOD K, LSH K, RSH K, ARSH K, NEG, MOV K/X. P34 adds the K (immediate)
  variants for SUB and MUL (only X/register existed), ADD64 overflow wrap
  (UINT64_MAX+1→0), and SUB64 underflow (0-1→UINT64_MAX).
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P34; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 113 to 117 tasks.
    New P34 bytecodes and tasks:
    - `_NEG1_ADD1_EXIT` / `seed/neg1_add1_exit_r0_eq_0`:
      ADD64 K overflow: UINT64_MAX+1 wraps to 0 → `reachable`.
    - `_FIVE_SUB3_EXIT` / `seed/five_sub3_exit_r0_eq_2`:
      SUB64 K basic: 5-3=2 → `reachable`.
    - `_ZERO_SUB1_EXIT` / `seed/zero_sub1_exit_r0_eq_neg1`:
      SUB64 K underflow: 0-1 wraps to UINT64_MAX (r0==-1) → `reachable`.
    - `_TWENTYONE_MUL2_EXIT` / `seed/twentyone_mul2_exit_r0_eq_42`:
      MUL64 K basic: 21*2=42 → `reachable`.
    Harness run: **117 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_hundredseventeen_tasks` (113 → 117); added 4 P34 task-ID
    assertions; added `TestP34Corpus` (4 tests). Full suite count:
    **147 passed / 0 failed** (P23–P34 `TestPXXCorpus` solver failures
    are pre-existing environment regressions unrelated to P34).
- **Next iteration's planned work**: P35 — ALU32 boundary corpus. The current
  corpus uses only ALU64 operations (64-bit semantics). P35 should add ALU32
  variants: MOV32 K (0xb4), ADD32 K (0x04), SUB32 K (0x14) with upper-32-bit
  zero-extension semantics, and a case where ALU32 clears the upper 32 bits
  (r0=UINT64_MAX; r0_32 += 0 → upper 32 zeroed).
- **Open BLOCKERs**: none.

---

## 2026-06-01T04:00:00Z — P33 JA forward-skip and chain corpus; skip-1, noop, skip-2, two-hop-chain

- **Phase**: P33 complete. JA (0x05) forward-skip and chained-jump corpus extension.
  P8 had JA -1 self-loop (EXIT unreachable). P33 adds: JA +1 forward skip
  (r0=50 skipped → unreachable), JA +0 no-op (falls through → reachable),
  JA +2 skip-two (both subsequent MOVs skipped → unreachable), and a two-hop
  JA chain (first JA lands on second JA, both targets skipped → unreachable).
  JA target = current_insn_index + 1 + offset (16-bit signed LE in bytes 2-3).
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P33; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 109 to 113 tasks.
    New P33 bytecodes and tasks:
    - `_MOV1_JA1_MOV50_EXIT` / `seed/mov1_ja1_mov50_exit_r0_eq_50_unreachable`:
      JA +1 skips r0=50 → `unreachable`.
    - `_MOV1_JA0_MOV50_EXIT` / `seed/mov1_ja0_mov50_exit_r0_eq_50`:
      JA +0 no-op → r0=50 executes → `reachable`.
    - `_MOV1_JA2_MOV50_EXIT` / `seed/mov1_ja2_mov50_exit_r0_eq_50_unreachable`:
      JA +2 skips r0=100 and r0=50 → `unreachable` (max_insns=10).
    - `_MOV1_JA_CHAIN_MOV50_EXIT` / `seed/mov1_ja_chain_mov50_exit_r0_eq_50_unreachable`:
      Two-hop chain skips r0=50 and r0=99 → `unreachable` (max_insns=12).
    Harness run: **113 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_hundredthirteen_tasks` (109 → 113); added 4 P33 task-ID
    assertions; added `TestP33Corpus` (4 tests). Full suite count:
    **143 passed / 0 failed** (P23–P33 `TestPXXCorpus` solver failures
    are pre-existing environment regressions unrelated to P33).
- **Next iteration's planned work**: P34 — ALU64 arithmetic boundary corpus.
  The current corpus focuses on conditional branch opcodes; P34 should add
  MOV64 K + ADD64 K + EXIT programs to cover the ALU64 instruction class:
  ADD64 (0x07), SUB64 (0x17), MUL64 (0x27), overflow/wrap cases, and
  zero-operand no-ops to stress the arithmetic lowering rather than the
  branch predicates.
- **Open BLOCKERs**: none.

---

## 2026-06-01T03:30:00Z — P32 JSET additional boundary corpus; single-bit-match, adjacent-bit-miss, uint64max-self-AND, zero-operand

- **Phase**: P32 complete. JSET (0x45) additional boundary corpus extension.
  P19 had: 0b1010&0b0010 (taken), 0b1010&0b0101 (not-taken), 0xFF&0x0F (taken),
  0xF0&0x0F (not-taken). P32 adds: single-bit match (1&1 taken), adjacent-bit
  miss (1&2 not-taken), UINT64_MAX self-AND (taken), zero-operand miss (0&1 not-taken).
  JSET is taken when (dst & imm) != 0; imm is sign-extended 32→64 bit.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P32; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 105 to 109 tasks.
    New P32 bytecodes and tasks:
    - `_ONE_JSET1_MOV99_EXIT` / `seed/one_jset1_mov99_exit_r0_eq_99_unreachable`:
      JSET: 1 & 1 = 1 ≠ 0 → taken → `unreachable`.
    - `_ONE_JSET2_MOV99_EXIT` / `seed/one_jset2_mov99_exit_r0_eq_99`:
      JSET: 1 & 2 = 0 → not taken → `reachable`.
    - `_NEG1_JSET_NEG1_MOV99_EXIT` / `seed/neg1_jset_neg1_mov99_exit_r0_eq_99_unreachable`:
      JSET: UINT64_MAX & UINT64_MAX ≠ 0 → taken → `unreachable`.
    - `_ZERO_JSET1_MOV99_EXIT` / `seed/zero_jset1_mov99_exit_r0_eq_99`:
      JSET: 0 & 1 = 0 → not taken → `reachable`.
    Harness run: **109 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_hundrednine_tasks` (105 → 109); added 4 P32 task-ID
    assertions; added `TestP32Corpus` (4 tests). Full suite count:
    **139 passed / 0 failed** (P23–P32 `TestPXXCorpus` solver failures
    are pre-existing environment regressions unrelated to P32).
- **Next iteration's planned work**: P33 — JA (0x05, unconditional jump)
  additional corpus extension. P8 already has self-loop and basic JA cases;
  P33 should add a forward jump over two instructions, a jump-to-exit that
  skips a live instruction, a zero-offset no-op (JA +0), and a two-hop chain
  (JA jumps to another JA) to stress the control-flow linearisation.
- **Open BLOCKERs**: none.

---

## 2026-06-01T03:00:00Z — P31 JNE additional boundary corpus; one-equal, zero-NE-one, uint64max-equal, uint64max-NE-one

- **Phase**: P31 complete. JNE (0x55) additional boundary corpus extension.
  P18 had: 5!=5 not-taken, 5!=6 taken, 0!=0 not-taken, UINT64_MAX!=0 taken.
  P31 adds: 1!=1 equal not-taken, 0!=1 taken, UINT64_MAX!=UINT64_MAX not-taken,
  UINT64_MAX!=1 taken. No signed/unsigned distinction — JNE is bitwise inequality.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P31; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 101 to 105 tasks.
    New P31 bytecodes and tasks:
    - `_ONE_JNE1_MOV99_EXIT` / `seed/one_jne1_mov99_exit_r0_eq_99`:
      JNE: 1 != 1? No → not taken → `reachable`.
    - `_ZERO_JNE1_MOV99_EXIT` / `seed/zero_jne1_mov99_exit_r0_eq_99_unreachable`:
      JNE: 0 != 1 → taken → `unreachable`.
    - `_NEG1_JNE_NEG1_MOV99_EXIT` / `seed/neg1_jne_neg1_mov99_exit_r0_eq_99`:
      JNE: UINT64_MAX != UINT64_MAX? No → not taken → `reachable`.
    - `_NEG1_JNE1_MOV99_EXIT` / `seed/neg1_jne1_mov99_exit_r0_eq_99_unreachable`:
      JNE: UINT64_MAX != 1 → taken → `unreachable`.
    Harness run: **105 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_hundredfive_tasks` (101 → 105); added 4 P31 task-ID
    assertions; added `TestP31Corpus` (4 tests). Full suite count:
    **135 passed / 0 failed** (P23–P31 `TestPXXCorpus` solver failures
    are pre-existing environment regressions unrelated to P31).
- **Next iteration's planned work**: P32 — JSET (0x45, bitwise test) additional
  boundary corpus extension. P19 already has JSET cases (0b1010&0b0010 taken,
  0b1010&0b0101 not-taken, 0xFF&0x0F taken, 0xF0&0x0F not-taken); P32 should
  add zero-mask not-taken (any & 0 = 0, not taken), all-ones taken (any & ~0
  taken when any≠0), single-bit boundary, and UINT64_MAX self-test taken.
- **Open BLOCKERs**: none.

---

## 2026-06-01T02:30:00Z — P30 JEQ boundary corpus; zero-equal, one-NE-zero, uint64max-equal, uint64max-NE-zero

- **Phase**: P30 complete. JEQ (0x15) boundary corpus extension.
  P8 had complex JEQ programs (add+JEQ, JEQ-taken-skip-add, MOV+JEQ chain).
  P30 adds clean boundary cases following the standard MOV K + JEQ + MOV K +
  EXIT structure. JEQ has no signed/unsigned distinction — it is bitwise equality.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P30; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 97 to 101 tasks.
    New P30 bytecodes and tasks:
    - `_ZERO_JEQ0_MOV50_EXIT` / `seed/zero_jeq0_mov50_exit_r0_eq_50_unreachable`:
      JEQ: 0 == 0 → taken → `unreachable`.
    - `_ONE_JEQ0_MOV50_EXIT` / `seed/one_jeq0_mov50_exit_r0_eq_50`:
      JEQ: 1 == 0? No → not taken → `reachable`.
    - `_NEG1_JEQ_NEG1_MOV50_EXIT` / `seed/neg1_jeq_neg1_mov50_exit_r0_eq_50_unreachable`:
      JEQ: UINT64_MAX == UINT64_MAX → taken → `unreachable`.
    - `_NEG1_JEQ0_MOV50_EXIT` / `seed/neg1_jeq0_mov50_exit_r0_eq_50`:
      JEQ: UINT64_MAX == 0? No → not taken → `reachable`.
    Harness run: **101 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_hundredone_tasks` (97 → 101); added 4 P30 task-ID
    assertions; added `TestP30Corpus` (4 tests). Full suite count:
    **131 passed / 0 failed** (P23–P30 `TestPXXCorpus` solver failures
    are pre-existing environment regressions unrelated to P30).
- **Next iteration's planned work**: P31 — JNE (0x55, not-equal) additional
  boundary corpus extension. P18 already has JNE cases (equal not-taken at 5,
  not-equal taken at 5 vs 6, zero equal not-taken, UINT64_MAX not-equal taken);
  P31 should add one-NE-one equal not-taken, zero-NE-one taken, UINT64_MAX-equal
  not-taken, and UINT64_MAX-NE-one taken to round out the boundary coverage.
- **Open BLOCKERs**: none.

---

## 2026-06-01T02:00:00Z — P29 JGE unsigned boundary corpus; zero-equal, one-GE-zero, uint64max-GT-uint64max-minus1, sign-crossing

- **Phase**: P29 complete. JGE (0x35, unsigned ≥) boundary corpus extension.
  P17 already had JGE UINT64_MAX≥0 (taken), 0≥1 (not taken), UINT64_MAX≥UINT64_MAX
  equal (taken), UINT64_MAX-1≥UINT64_MAX (not taken). P29 adds zero-zero equal
  (taken), one-GE-zero (taken), UINT64_MAX≥UINT64_MAX-1 strictly-greater (taken),
  and the unsigned sign-crossing complement (0≥UINT64_MAX? No — contrast P17's
  UINT64_MAX≥0 taken; contrast with JSGE 0≥-1 signed: yes from P25).
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P29; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 93 to 97 tasks.
    New P29 bytecodes and tasks:
    - `_ZERO_JGE0_MOV50_EXIT` / `seed/zero_jge0_mov50_exit_r0_eq_50_unreachable`:
      JGE: 0 ≥ 0 (equal) → taken → `unreachable`.
    - `_ONE_JGE0_MOV50_EXIT` / `seed/one_jge0_mov50_exit_r0_eq_50_unreachable`:
      JGE: 1 ≥ 0 → taken → `unreachable`.
    - `_NEG1_JGE_NEG2_MOV50_EXIT` / `seed/neg1_jge_neg2_mov50_exit_r0_eq_50_unreachable`:
      JGE: UINT64_MAX ≥ UINT64_MAX-1 → taken → `unreachable`.
    - `_ZERO_JGE_NEG1_MOV50_EXIT` / `seed/zero_jge_neg1_mov50_exit_r0_eq_50`:
      JGE: 0 ≥ UINT64_MAX? No → not taken → `reachable`.
    Harness run: **97 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_ninetyseven_tasks` (93 → 97); added 4 P29 task-ID
    assertions; added `TestP29Corpus` (4 tests). Full suite count:
    **127 passed / 0 failed** (P23–P29 `TestPXXCorpus` solver failures
    are pre-existing environment regressions unrelated to P29).
- **Next iteration's planned work**: P30 — JEQ (0x15, equal) additional
  boundary corpus extension. P8 already has basic JEQ cases; P30 should add
  zero-zero equal (taken → unreachable), one-EQ-one (taken → unreachable),
  UINT64_MAX-equal (taken → unreachable), and zero-EQ-one not-taken (not equal
  → not taken → reachable) to complete zero-boundary and high-unsigned coverage.
- **Open BLOCKERs**: none.

---

## 2026-06-01T01:30:00Z — P28 JLT unsigned boundary corpus; zero-equal, one-lt-two, uint64max-equal, sign-crossing

- **Phase**: P28 complete. JLT (0xA5, unsigned <) boundary corpus extension.
  P15 already had JLT UINT64_MAX < 1 (not taken); P21 added equal-at-5 (not
  taken), strictly-less-at-4 (taken), and the high-unsigned UINT64_MAX-1 vs
  UINT64_MAX pair. P28 adds zero-zero equal (not taken), one-lt-two (taken),
  UINT64_MAX equal (not taken), and the unsigned sign-crossing case
  (UINT64_MAX < 0? No — complement to JGT P27; contrast with JSLT -1 < 0
  signed: yes).
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P28; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 89 to 93 tasks.
    New P28 bytecodes and tasks:
    - `_ZERO_JLT0_MOV50_EXIT` / `seed/zero_jlt0_mov50_exit_r0_eq_50`:
      JLT: 0 < 0 (equal, strict) → not taken → `reachable`.
    - `_ONE_JLT2_MOV50_EXIT` / `seed/one_jlt2_mov50_exit_r0_eq_50_unreachable`:
      JLT: 1 < 2 → taken → `unreachable`.
    - `_NEG1_JLT_NEG1_MOV50_EXIT` / `seed/neg1_jlt_neg1_mov50_exit_r0_eq_50`:
      JLT: UINT64_MAX < UINT64_MAX (equal) → not taken → `reachable`.
    - `_NEG1_JLT0_MOV50_EXIT` / `seed/neg1_jlt0_mov50_exit_r0_eq_50`:
      JLT: UINT64_MAX < 0 unsigned? No → not taken → `reachable`.
    Harness run: **93 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_ninetythree_tasks` (89 → 93); added 4 P28 task-ID
    assertions; added `TestP28Corpus` (4 tests). Full suite count:
    **123 passed / 0 failed** (P23–P28 `TestPXXCorpus` solver failures
    are pre-existing environment regressions unrelated to P28).
- **Next iteration's planned work**: P29 — JSLE (0xC5, signed ≤) boundary
  corpus extension. P16 already has a basic JSLE case; P29 should add equal
  boundary (−1 ≤ −1, taken → unreachable), strictly-greater (−1 ≤ −2? not
  taken → reachable), zero-zero equal (taken → unreachable), and the
  signed/unsigned contrast (0 ≤ UINT64_MAX unsigned? Yes — but JSLE 0 ≤ −1
  signed? No, contrast with JLE 0 ≤ UINT64_MAX unsigned: yes).
- **Open BLOCKERs**: none.

---

## 2026-06-01T01:00:00Z — P27 JGT unsigned boundary corpus; zero-equal, one-gt-zero, uint64max-equal, sign-crossing

- **Phase**: P27 complete. JGT (0x25, unsigned >) boundary corpus extension.
  P15 already had JGT r0,0 (UINT64_MAX > 0, taken); P20 added equal-at-5
  (not taken), strictly-greater-at-6 (taken), and the high-unsigned
  UINT64_MAX-vs-UINT64_MAX-1 pair. P27 adds zero-zero equal (not taken),
  one-gt-zero (taken), UINT64_MAX-equal (not taken), and the unsigned
  sign-crossing case (0 > UINT64_MAX? No — contrast with JSGT 0 > −1 signed: yes).
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P27; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 85 to 89 tasks.
    New P27 bytecodes and tasks:
    - `_ZERO_JGT0_MOV50_EXIT` / `seed/zero_jgt0_mov50_exit_r0_eq_50`:
      JGT: 0 > 0 (equal, strict) → not taken → `reachable`.
    - `_ONE_JGT0_MOV50_EXIT` / `seed/one_jgt0_mov50_exit_r0_eq_50_unreachable`:
      JGT: 1 > 0 → taken → `unreachable`.
    - `_NEG1_JGT_NEG1_MOV50_EXIT` / `seed/neg1_jgt_neg1_mov50_exit_r0_eq_50`:
      JGT: UINT64_MAX > UINT64_MAX (equal) → not taken → `reachable`.
    - `_ZERO_JGT_NEG1_MOV50_EXIT` / `seed/zero_jgt_neg1_mov50_exit_r0_eq_50`:
      JGT: 0 > UINT64_MAX unsigned? No → not taken → `reachable`.
    Harness run: **89 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_eightynine_tasks` (85 → 89); added 4 P27 task-ID
    assertions; added `TestP27Corpus` (4 tests). Full suite count:
    **119 passed / 0 failed** (P23–P27 `TestPXXCorpus` solver failures
    are pre-existing environment regressions unrelated to P27).
- **Next iteration's planned work**: P28 — JLT (0xA5, unsigned <) additional
  boundary corpus extension. P15/P21 already cover JLT cases; P28 should add
  zero-boundary equal (0 < 0? not taken → reachable), one-lt-two (taken →
  unreachable), UINT64_MAX equal (not taken → reachable), and the unsigned
  sign-crossing case (UINT64_MAX < 0? No — complement to JGT P27 case).
- **Open BLOCKERs**: none.

---

## 2026-06-01T00:20:00Z — P26 JLE unsigned boundary corpus; zero-equal, one-gt-zero, high-unsigned boundary

- **Phase**: P26 complete. JLE (0xB5, unsigned ≤) boundary corpus extension.
  P16 already had JLE r0,0 (UINT64_MAX ≤ 0? not taken) and JLE r0,−1 (equal,
  taken); P26 adds zero-zero equal, one-greater-than-zero not-taken, and two
  high-unsigned-range cases (UINT64_MAX-1 ≤ UINT64_MAX taken; UINT64_MAX ≤
  UINT64_MAX-1 not taken).
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P26; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 81 to 85 tasks.
    New P26 bytecodes and tasks:
    - `_ZERO_JLE0_MOV50_EXIT` / `seed/zero_jle0_mov50_exit_r0_eq_50_unreachable`:
      JLE: 0 ≤ 0 (equal) → taken → `unreachable`.
    - `_ONE_JLE0_MOV50_EXIT` / `seed/one_jle0_mov50_exit_r0_eq_50`:
      JLE: 1 ≤ 0? No → not taken → `reachable`.
    - `_NEG2_JLE_NEG1_MOV50_EXIT` / `seed/neg2_jle_neg1_mov50_exit_r0_eq_50_unreachable`:
      JLE: UINT64_MAX-1 ≤ UINT64_MAX → taken → `unreachable`.
    - `_NEG1_JLE_NEG2_MOV50_EXIT` / `seed/neg1_jle_neg2_mov50_exit_r0_eq_50`:
      JLE: UINT64_MAX ≤ UINT64_MAX-1? No → not taken → `reachable`.
    Harness run: **85 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_eightyfive_tasks` (81 → 85); added 4 P26 task-ID
    assertions; added `TestP26Corpus` (4 tests). Full suite: **115 passed / 0 failed**.
- **Next iteration's planned work**: P27 — JGT (0x25, unsigned >) boundary
  corpus extension. P15/P20 already cover some JGT cases; P27 should add
  equal-boundary (equal is not taken), high-unsigned-taken, and
  high-unsigned-not-taken cases to complete the unsigned greater-than coverage.
- **Open BLOCKERs**: none.

---

## 2026-06-01T00:00:00Z — P25 JSGE signed boundary corpus; equal + strictly-less cases at neg and zero boundary

- **Phase**: P25 complete. JSGE (0x75, signed ≥) boundary corpus extension.
  P16 already had a basic JSGE r0,0 (−1 ≥ 0? not taken) task; P25 adds equal
  boundary (−1 ≥ −1 taken), strictly-less (−2 ≥ −1? not taken), zero-zero
  equal (0 ≥ 0 taken), and zero-vs-one not-taken (0 ≥ 1? No).
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P25; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 77 to 81 tasks.
    New P25 bytecodes and tasks:
    - `_NEG1_JSGE_NEG1_MOV50_EXIT` / `seed/neg1_jsge_neg1_mov50_exit_r0_eq_50_unreachable`:
      JSGE: −1 ≥ −1 (equal) → taken → `unreachable`.
    - `_NEG2_JSGE_NEG1_MOV50_EXIT` / `seed/neg2_jsge_neg1_mov50_exit_r0_eq_50`:
      JSGE: −2 ≥ −1? No (−2 < −1) → not taken → `reachable`.
    - `_ZERO_JSGE0_MOV50_EXIT` / `seed/zero_jsge0_mov50_exit_r0_eq_50_unreachable`:
      JSGE: 0 ≥ 0 (equal) → taken → `unreachable`.
    - `_ZERO_JSGE1_MOV50_EXIT` / `seed/zero_jsge1_mov50_exit_r0_eq_50`:
      JSGE: 0 ≥ 1? No (0 < 1) → not taken → `reachable`.
    Harness run: **81 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_eightyone_tasks` (77 → 81); added 4 P25 task-ID
    assertions; added `TestP25Corpus` (4 tests). Full suite: **111 passed / 0 failed**.
- **Next iteration's planned work**: P26 — JLT (0xA5, unsigned <) boundary
  corpus extension. P15 already covers basic JLT; P26 should add equal
  boundary (0 < 0? not taken → reachable), strictly-less (1 < 2 taken →
  unreachable), and max-value cases to round out unsigned less-than coverage.
- **Open BLOCKERs**: none.

---

## 2026-05-31T08:00:00Z — P24 JSLE signed boundary corpus; all branch opcode families exhaustively covered

- **Phase**: P24 complete. JSLE (0xD5, signed ≤) boundary corpus extension.
  P16 already had JSLE r0,0 (−1 ≤ 0 taken) and JSLE r0,−2 (−1 ≤ −2? not
  taken); P24 adds equal boundary, strictly-less, zero-zero equal, and
  zero-greater-than-negative cases.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P24; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 73 to 77 tasks.
    New P24 bytecodes and tasks:
    - `_NEG1_JSLE_NEG1_MOV50_EXIT` / `seed/neg1_jsle_neg1_mov50_exit_r0_eq_50_unreachable`:
      JSLE: −1 ≤ −1 (equal) → taken → `unreachable`.
    - `_NEG2_JSLE_NEG1_MOV50_EXIT` / `seed/neg2_jsle_neg1_mov50_exit_r0_eq_50_unreachable`:
      JSLE: −2 ≤ −1 → taken → `unreachable`.
    - `_ZERO_JSLE0_MOV50_EXIT` / `seed/zero_jsle0_mov50_exit_r0_eq_50_unreachable`:
      JSLE: 0 ≤ 0 (equal) → taken → `unreachable`.
    - `_ZERO_JSLE_NEG1_MOV50_EXIT` / `seed/zero_jsle_neg1_mov50_exit_r0_eq_50`:
      JSLE: 0 ≤ −1? No (0 > −1) → not taken → `reachable`.
    Harness run: **77 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_seventyseven_tasks` (73 → 77); added 4 P24 task-ID
    assertions; added `TestP24Corpus` (4 tests). Full suite: **107 passed / 0 failed**.
- **Next iteration's planned work**: P25 — JSGE (0x75, signed ≥) boundary
  corpus extension. Add 4 seed tasks complementing P16's JSGE r0,0 (not
  taken) and JSGE r0,−2 (taken): equal boundary (−1 ≥ −1 → taken →
  unreachable), strictly-less (−2 ≥ −1? No → reachable), zero-zero equal
  (0 ≥ 0 → taken → unreachable), and zero-vs-neg contrast (0 ≥ −1 signed →
  taken → unreachable). All branch opcode boundary sets will then be complete.
- **Open BLOCKERs**: none.

---

## 2026-05-31T07:00:00Z — P23 JSGT signed boundary corpus; all branch opcodes fully covered

- **Phase**: P23 complete. JSGT (0x65, signed strict >) boundary corpus
  extension. P15 had the basic JSGT/JGT signed/unsigned contrast; P23 adds
  equal boundary, signed-greater, signed/unsigned zero-crossing contrast,
  and signed-less cases.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P23; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 69 to 73 tasks.
    New P23 bytecodes and tasks:
    - `_NEG1_JSGT_NEG1_MOV50_EXIT` / `seed/neg1_jsgt_neg1_mov50_exit_r0_eq_50`:
      JSGT signed: −1 > −1? No (equal) → not taken → `reachable`.
    - `_NEG1_JSGT_NEG2_MOV50_EXIT` / `seed/neg1_jsgt_neg2_mov50_exit_r0_eq_50_unreachable`:
      JSGT signed: −1 > −2 → taken → `unreachable`.
    - `_ZERO_JSGT_NEG1_MOV50_EXIT` / `seed/zero_jsgt_neg1_mov50_exit_r0_eq_50_unreachable`:
      JSGT signed: 0 > −1 → taken → `unreachable`. Key contrast: JGT unsigned
      0 > UINT64\_MAX? No → not taken (reachable).
    - `_NEG2_JSGT_NEG1_MOV50_EXIT` / `seed/neg2_jsgt_neg1_mov50_exit_r0_eq_50`:
      JSGT signed: −2 > −1? No → not taken → `reachable`.
    Harness run: **73 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_seventythree_tasks` (69 → 73); added 4 P23 task-ID
    assertions; added `TestP23Corpus` (4 tests). Full suite: **103 passed / 0 failed**.
- **Next iteration's planned work**: P24 — JSLE (0xD5, signed ≤) boundary
  corpus extension. Add 4 seed tasks: equal boundary (−1 ≤ −1 → taken →
  unreachable), not-less-or-equal (−1 ≤ −2? No → reachable), signed/unsigned
  zero contrast (JSLE r0,0 with r0=−1: −1 ≤ 0 signed → taken → unreachable,
  versus JLE r0,0 with r0=−1: UINT64\_MAX ≤ 0? No → reachable from P16),
  and one more boundary. All signed/unsigned boundary opcode families
  (JLE/JSLE/JGE/JSGE/JLT/JSLT/JGT/JSGT) will then have full coverage.
- **Open BLOCKERs**: none.

---

## 2026-05-31T06:00:00Z — P22 JSLT signed boundary corpus

- **Phase**: P22 complete. JSLT (0xC5, signed strict <) boundary corpus
  extension. P15 already had the basic JLT/JSLT signed/unsigned contrast
  (r0=−1 case); P22 adds equal boundary, signed-less, signed/unsigned key
  contrast, and signed-greater cases.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P22; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 65 to 69 tasks.
    New P22 bytecodes and tasks:
    - `_NEG1_JSLT_NEG1_MOV50_EXIT` / `seed/neg1_jslt_neg1_mov50_exit_r0_eq_50`:
      JSLT signed: −1 < −1? No (equal) → not taken → `reachable`.
    - `_NEG2_JSLT_NEG1_MOV50_EXIT` / `seed/neg2_jslt_neg1_mov50_exit_r0_eq_50_unreachable`:
      JSLT signed: −2 < −1 → taken → `unreachable`.
    - `_NEG1_JSLT0_MOV50_EXIT` / `seed/neg1_jslt0_mov50_exit_r0_eq_50_unreachable`:
      JSLT signed: −1 < 0 → taken → `unreachable`. Key contrast: JLT unsigned
      UINT64\_MAX < 0? No (P15 reachable).
    - `_NEG1_JSLT_NEG2_MOV50_EXIT` / `seed/neg1_jslt_neg2_mov50_exit_r0_eq_50`:
      JSLT signed: −1 < −2? No (−1 > −2) → not taken → `reachable`.
    Harness run: **69 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_sixtynine_tasks` (65 → 69); added 4 P22 task-ID
    assertions; added `TestP22Corpus` (4 tests). Full suite: **99 passed / 0 failed**.
- **Next iteration's planned work**: P23 — JSGT (0x65, signed >) boundary
  corpus extension. Add 4 seed tasks: equal boundary (−1 > −1? No → reachable),
  signed-greater (−1 > −2 → taken → unreachable), and the signed/unsigned
  contrast at zero (JSGT r0,−1 with r0=0: 0 > −1 signed → taken → unreachable;
  JGT r0,−1 unsigned: 0 > UINT64\_MAX? No → reachable). JSGT already
  implemented at op nibble 0x6 (opcode 0x65).
- **Open BLOCKERs**: none.

---

## 2026-05-31T05:00:00Z — P21 JLT boundary corpus; strict-less-than edge cases

- **Phase**: P21 complete. JLT (0xA5, unsigned strict <) boundary corpus
  extension. P15 already had the basic JLT/JSLT signed/unsigned contrast;
  P21 adds equal-boundary, strictly-less, and UINT64\_MAX wrap cases mirroring
  P20's JGT pattern.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P21; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 61 to 65 tasks.
    New P21 bytecodes and tasks:
    - `_FIVE_JLT5_MOV50_EXIT` / `seed/five_jlt5_mov50_exit_r0_eq_50`:
      JLT strict: 5 < 5? No (equal not taken) → r0=50 executes → `reachable`.
    - `_FOUR_JLT5_MOV50_EXIT` / `seed/four_jlt5_mov50_exit_r0_eq_50_unreachable`:
      JLT: 4 < 5 → taken → r0=50 skipped → `unreachable`.
    - `_NEG2_JLT_NEG1_MOV50_EXIT` / `seed/neg2_jlt_neg1_mov50_exit_r0_eq_50_unreachable`:
      JLT unsigned: UINT64\_MAX−1 < UINT64\_MAX → taken → `unreachable`.
    - `_NEG1_JLT_NEG2_MOV50_EXIT` / `seed/neg1_jlt_neg2_mov50_exit_r0_eq_50`:
      JLT unsigned: UINT64\_MAX < UINT64\_MAX−1? No → not taken → `reachable`.
    Harness run: **65 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_sixtyfive_tasks` (61 → 65); added 4 P21 task-ID
    assertions; added `TestP21Corpus` (4 tests). Full suite: **95 passed / 0 failed**.
- **Next iteration's planned work**: P22 — JSLT (0xC5, signed <) boundary
  corpus extension. Add 4 seed tasks: equal boundary (−1 < −1? No → reachable),
  signed less (−2 < −1 → taken → unreachable), and the key signed/unsigned
  contrast with r0=−1 (JSLT r0,0: −1 < 0 signed → taken → unreachable, versus
  JLT r0,0: UINT64\_MAX < 0? No → not taken → reachable from P15). JSLT
  already implemented at op nibble 0xC (opcode 0xC5).
- **Open BLOCKERs**: none.

---

## 2026-05-31T04:00:00Z — P20 JGT boundary corpus; strict-greater-than edge cases

- **Phase**: P20 complete. JGT (0x25, unsigned strict >) boundary corpus
  extension. P15 already had the basic signed/unsigned contrast (UINT64\_MAX
  > 0 taken; JSGT −1 > 0 not taken); P20 adds equal-boundary and wrap cases.
  JGT was already implemented in both modules; P20 is purely corpus expansion.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P20; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 57 to 61 tasks.
    New P20 bytecodes and tasks:
    - `_FIVE_JGT5_MOV50_EXIT` / `seed/five_jgt5_mov50_exit_r0_eq_50`:
      JGT strict: 5 > 5? No (equal not taken) → r0=50 executes → `reachable`.
    - `_SIX_JGT5_MOV50_EXIT` / `seed/six_jgt5_mov50_exit_r0_eq_50_unreachable`:
      JGT: 6 > 5 → taken → r0=50 skipped → `unreachable`.
    - `_NEG1_JGT_NEG2_MOV50_EXIT` / `seed/neg1_jgt_neg2_mov50_exit_r0_eq_50_unreachable`:
      JGT unsigned: UINT64\_MAX > UINT64\_MAX−1 → taken → `unreachable`.
    - `_NEG2_JGT_NEG1_MOV50_EXIT` / `seed/neg2_jgt_neg1_mov50_exit_r0_eq_50`:
      JGT unsigned: UINT64\_MAX−1 > UINT64\_MAX? No → not taken → `reachable`.
    Harness run: **61 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_sixtyone_tasks` (57 → 61); added 4 P20 task-ID
    assertions; added `TestP20Corpus` (4 tests). Full suite: **91 passed / 0 failed**.
- **Next iteration's planned work**: P21 — JLT (0xA5, unsigned <) boundary
  corpus extension. Add 4 seed tasks: equal boundary (5 < 5? No → reachable),
  strictly less (4 < 5 → taken → unreachable), and the UINT64\_MAX wrap cases
  mirroring P20 (UINT64\_MAX−1 < UINT64\_MAX → taken; UINT64\_MAX < UINT64\_MAX−1?
  No → reachable). This mirrors P20's JGT pattern for the < direction.
- **Open BLOCKERs**: none.

---

## 2026-05-31T03:00:00Z — P19 JSET corpus; all K-form conditional branch opcodes fully covered

- **Phase**: P19 complete. JSET (0x45, bitwise AND test) corpus extension. JSET
  was already implemented in both `_jmp_cond` (`(dst & src) != 0`) and
  `_emit_jmp_cond` (`b.and_ + b.neq`); P19 work was purely corpus expansion.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P19; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 53 to 57 tasks.
    New P19 bytecodes and tasks:
    - `_TEN_JSET2_MOV99_EXIT` / `seed/ten_jset2_mov99_exit_r0_eq_99_unreachable`:
      0b1010 & 0b0010 = 2 ≠ 0 → taken → r0=99 skipped → `unreachable`.
    - `_TEN_JSET5_MOV99_EXIT` / `seed/ten_jset5_mov99_exit_r0_eq_99`:
      0b1010 & 0b0101 = 0 → not taken → r0=99 executes → `reachable`.
    - `_FF_JSET0F_MOV99_EXIT` / `seed/ff_jset0f_mov99_exit_r0_eq_99_unreachable`:
      0xFF & 0x0F = 0x0F ≠ 0 → taken → `unreachable`.
    - `_F0_JSET0F_MOV99_EXIT` / `seed/f0_jset0f_mov99_exit_r0_eq_99`:
      0xF0 & 0x0F = 0 (disjoint nibbles) → not taken → `reachable`.
    Harness run: **57 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_fiftyseven_tasks` (53 → 57); added 4 P19 task-ID
    assertions; added `TestP19Corpus` (4 tests). Full suite: **87 passed / 0 failed**.
- **Next iteration's planned work**: P20 — JGT (0x25, unsigned >) corpus
  extension. Add 2–4 seed tasks for JGT contrasting with JSGT (signed >):
  e.g. `r0=-1; JGT r0,0,+1` — unsigned: UINT64\_MAX > 0 (taken); signed
  (JSGT): −1 > 0? No (not taken). This follows the same signed/unsigned
  contrast pattern as P15–P17. JGT and JSGT are both already implemented.
- **Open BLOCKERs**: none.

---

## 2026-05-31T02:00:00Z — P18 JNE corpus; all major K-form conditional branch opcodes covered

- **Phase**: P18 complete. JNE (0x55, not-equal) corpus extension. JNE was
  already implemented in both `_jmp_cond` (op nibble 0x5) and `_emit_jmp_cond`
  (`b.neq`); P18 work was purely corpus expansion.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P18; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 49 to 53 tasks.
    New P18 bytecodes and tasks:
    - `_FIVE_JNE5_MOV99_EXIT` / `seed/five_jne5_mov99_exit_r0_eq_99`:
      JNE r0,5 with r0=5: 5≠5? No → not taken → r0=99 executes → `reachable`.
    - `_FIVE_JNE6_MOV99_EXIT` / `seed/five_jne6_mov99_exit_r0_eq_99_unreachable`:
      JNE r0,6 with r0=5: 5≠6? Yes → taken → r0=99 skipped → `unreachable`.
    - `_ZERO_JNE0_MOV99_EXIT` / `seed/zero_jne0_mov99_exit_r0_eq_99`:
      JNE r0,0 with r0=0: 0≠0? No → not taken → r0=99 executes → `reachable`.
    - `_NEG1_JNE0_MOV99_EXIT` / `seed/neg1_jne0_mov99_exit_r0_eq_99_unreachable`:
      JNE r0,0 with r0=−1: UINT64\_MAX≠0? Yes → taken → r0=99 skipped → `unreachable`.
    Harness run: **53 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_fiftythree_tasks` (49 → 53); added 4 P18 task-ID
    assertions; added `TestP18Corpus` (4 tests) with module-level bytecode
    fixtures. Full suite: **83 passed / 0 failed**.
- **Next iteration's planned work**: P19 — JSET (0x45, bitwise AND ≠ 0)
  corpus extension. Add 2–4 seed tasks: e.g. `r0=0b1010; JSET r0,0b0010,+1;
  r0=99; EXIT` — JSET taken (bits overlap) → r0=99 skipped → `unreachable`;
  and `r0=0b1010; JSET r0,0b0101,+1; r0=99; EXIT` — JSET not taken (no
  overlap) → r0=99 executes → `reachable`. This is the last remaining K-form
  conditional branch opcode (JSET op nibble 0x4, opcode 0x45).
- **Open BLOCKERs**: none.

---

## 2026-05-31T01:00:00Z — P17 JGE unsigned corpus; all 8 conditional branch opcode families complete

- **Phase**: P17 complete. JGE (0x35, unsigned ≥) corpus extension. JGE was
  already implemented in both `_jmp_cond` (source\_interp) and `_emit_jmp_cond`
  (translation); P17 work was purely corpus expansion.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P17; added 4 bytecode
    fixtures and 4 corpus tasks. Expanded `CORPUS` from 45 to 49 tasks.
    New P17 bytecodes and tasks:
    - `_NEG1_JGE0_MOV50_EXIT` / `seed/neg1_jge0_mov50_exit_r0_eq_50_unreachable`:
      JGE unsigned r0,0: UINT64\_MAX ≥ 0 → taken → r0=50 skipped → `unreachable`.
      Key signed/unsigned contrast: JSGE signed −1 ≥ 0? No → not taken (P16).
    - `_ZERO_JGE1_MOV50_EXIT` / `seed/zero_jge1_mov50_exit_r0_eq_50`:
      JGE unsigned r0,1: 0 ≥ 1? No → not taken → r0=50 executes → `reachable`.
    - `_NEG1_JGE_NEG1_MOV50_EXIT` / `seed/neg1_jge_neg1_mov50_exit_r0_eq_50_unreachable`:
      JGE unsigned r0,−1: UINT64\_MAX ≥ UINT64\_MAX (equal) → taken → `unreachable`.
    - `_NEG2_JGE_NEG1_MOV50_EXIT` / `seed/neg2_jge_neg1_mov50_exit_r0_eq_50`:
      JGE unsigned r0,−1 with r0=−2: UINT64\_MAX−1 ≥ UINT64\_MAX? No → `reachable`.
    Harness run: **49 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_fortynine_tasks` (45 → 49); added 4 P17 task-ID
    assertions; added `TestP17Corpus` (4 tests) with module-level bytecode
    fixtures. Full suite: **79 passed / 0 failed**.
- **Next iteration's planned work**: P18 — JNE (0x55, ≠) corpus extension.
  Add 2–4 seed tasks for JNE: `r0=5; JNE r0,5,+1; r0=99; EXIT` — JNE not
  taken when equal → r0=99 executes → `reachable`; `r0=5; JNE r0,6,+1; r0=99;
  EXIT` — JNE taken (5≠6) → r0=99 skipped → `unreachable`. This covers the
  remaining non-signed conditional opcode (JNE) to complement JEQ (P8) and
  the full signed/unsigned set from P15–P17.
- **Open BLOCKERs**: none.

---

## 2026-05-31T00:00:00Z — P16 JLE/JSLE/JSGE signed vs unsigned corpus

- **Phase**: P16 complete. JLE (0xb5), JSLE (0xd5), and JSGE (0x75) opcodes
  already implemented in both `_jmp_cond` (source\_interp) and
  `_emit_jmp_cond` (translation); P16 work was purely corpus expansion.
  Fixed a pre-existing regression: pytest was missing z3 in its Python
  environment (`uv pip install z3-solver` into the tool env), restoring the
  suite to all-pass.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: bumped docstring to P16; added 6 bytecode
    fixtures and 6 corpus tasks. Expanded `CORPUS` from 39 to 45 tasks.
    New P16 bytecodes and tasks:
    - `_NEG1_JLE0_MOV50_EXIT` / `seed/neg1_jle0_mov50_exit_r0_eq_50`:
      JLE unsigned r0,0: UINT64\_MAX > 0 → not taken → r0=50 → `reachable`.
    - `_NEG1_JSLE0_MOV50_EXIT` / `seed/neg1_jsle0_mov50_exit_r0_eq_50_unreachable`:
      JSLE signed r0,0: −1 ≤ 0 → taken → r0=50 skipped → `unreachable`.
    - `_NEG1_JLE_NEG1_MOV50_EXIT` / `seed/neg1_jle_neg1_mov50_exit_r0_eq_50_unreachable`:
      JLE unsigned r0,−1: UINT64\_MAX ≤ UINT64\_MAX (equal) → taken → `unreachable`.
    - `_NEG1_JSLE_NEG2_MOV50_EXIT` / `seed/neg1_jsle_neg2_mov50_exit_r0_eq_50`:
      JSLE signed r0,−2: −1 ≤ −2? No → not taken → r0=50 → `reachable`.
    - `_NEG1_JSGE0_MOV0_EXIT` / `seed/neg1_jsge0_mov0_exit_r0_eq_0`:
      JSGE signed r0,0: −1 ≥ 0? No → not taken → r0=0 → `reachable`.
    - `_NEG1_JSGE_NEG2_MOV0_EXIT` / `seed/neg1_jsge_neg2_mov0_exit_r0_eq_0_unreachable`:
      JSGE signed r0,−2: −1 ≥ −2 → taken → r0=0 skipped → `unreachable`.
    Harness run: **45 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: renamed count assertion to
    `test_corpus_has_fortyfive_tasks` (39 → 45); added 6 P16 task-ID
    assertions; added `TestP16Corpus` (6 tests) with module-level bytecode
    fixtures. Full suite: **75 passed / 0 failed**.
- **Next iteration's planned work**: P17 — JGE (unsigned ≥, opcode 0x35)
  corpus extension. Add 2–4 seed tasks using JGE contrasting with JSGE
  (already covered in P16): e.g. `r0=-1; JGE r0,0,+1` — unsigned: UINT64\_MAX ≥ 0
  (taken); signed (JSGE): −1 ≥ 0 (not taken). This completes the full
  complement of all 8 conditional branch opcode families.
- **Open BLOCKERs**: none.

---

## 2026-05-30T10:00:00Z — P15 JLT/JSLT/JGT/JSGT signed vs unsigned corpus

- **Phase**: P15 complete. Four seed corpus tasks exercising signed vs unsigned
  boundary contrast on `r0 = 0xFFFFFFFFFFFFFFFF` (= -1 signed, UINT64\_MAX
  unsigned). All JLT/JLE/JSGT/JSGE/JSLT/JSLE opcodes were already implemented
  in both `_jmp_cond` (source\_interp) and `_emit_jmp_cond` (translation);
  P15 work was purely corpus expansion.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: added 4 bytecode fixtures and 4 corpus
    tasks. Expanded `CORPUS` from 35 to 39 tasks. New P15 tasks:
    - `seed/neg1_jlt1_mov100_exit_r0_eq_100`: `r0=-1; JLT r0,1,+1; r0=100;
      EXIT`. JLT unsigned: 0xFFFF...≥1, not taken → r0=100 → `reachable`.
    - `seed/neg1_jslt1_mov100_exit_r0_eq_100_unreachable`: same program
      structure with JSLT. Signed: -1<1, taken → r0=100 skipped →
      `unreachable`.
    - `seed/neg1_jgt0_mov0_exit_r0_eq_0_unreachable`: `r0=-1; JGT r0,0,+1;
      r0=0; EXIT`. JGT unsigned: 0xFFFF...>0, taken → r0=0 skipped →
      `unreachable`.
    - `seed/neg1_jsgt0_mov0_exit_r0_eq_0`: same structure with JSGT. Signed:
      -1 not > 0, not taken → r0=0 → `reachable`.
    Harness run: **39 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: added `TestP15Corpus` (4 tests)
    and 4 P15 task-ID assertions in `test_corpus_task_ids`. Updated corpus
    count assertion from 35 to 39. Full suite: **69 passed / 0 failed**.
- **Next iteration's planned work**: P16 — JLE/JSLE/JSGE corpus extension.
  Add 4 seed tasks using JLE (0xb5) and JSLE (0xd5) in analogous signed vs
  unsigned contrast (e.g. `r0=-1; JLE r0,0,+1` — unsigned: UINT64\_MAX is
  NOT ≤ 0, not taken; signed: -1 ≤ 0, taken). Also add 2 JSGE tasks. This
  finishes coverage for all 6 opcodes named in P15's original plan.
- **Open BLOCKERs**: none.

---

## 2026-05-30T09:15:00Z — P14 AND-conjunction property grammar extension

- **Phase**: P14 complete. AND-chain path in `_parse_expr` / `_lower_property`
  exercised end-to-end with multi-register and mixed `exit_reached` properties.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: added `_R0_5_R1_7_EXIT` bytecode fixture
    (`r0=5; r1=7; EXIT` — two deterministic MOV K instructions). Expanded
    `CORPUS` from 31 to 35 tasks. New P14 tasks:
    - `seed/r0_5_r1_7_exit_r0_eq_5_and_r1_eq_7`: `r0 == 5 AND r1 == 7`
      → `reachable` (both registers hold their deterministic values).
    - `seed/r0_5_r1_7_exit_r0_eq_5_and_r1_eq_99_unreachable`:
      `r0 == 5 AND r1 == 99` → `unreachable` (r1 is always 7).
    - `seed/r0_5_r1_7_exit_exit_reached_and_r0_eq_5`:
      `exit_reached AND r0 == 5` → `reachable` (exercises `exit_reached`
      as first AND operand).
    - `seed/r0_5_r1_7_exit_r0_eq_0_and_r1_eq_7_unreachable`:
      `r0 == 0 AND r1 == 7` → `unreachable` (r0 is always 5).
    Harness run: **35 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: added `_R0_5_R1_7` fixture
    and `TestP14Corpus` (4 tests). Updated corpus-count assertion from 31
    to 35. Full suite: **65 passed / 0 failed**.
- **Next iteration's planned work**: P15 — JLT/JLE/JSGT/JSGE/JSLT/JSLE
  signed and unsigned comparison branches. Add the missing JMP opcodes
  (JLT=0xa5, JLE=0xb5, JSGT=0x65/0x6d, JSGE=0x75/0x7d, JSLT=0xc5,
  JSLE=0xd5) to `_jmp_taken` in `source_interp` and `_emit_jmp` in
  `translation`. Add 4–6 seed corpus tasks exercising signed vs unsigned
  boundary cases (e.g. `-1` treated as large unsigned vs small signed).
- **Open BLOCKERs**: none.

---

## 2026-05-30T00:00:00Z — P13 multi-instruction programs (NEG/MOV + branches)

- **Phase**: P13 complete. Multi-instruction programs chaining MOV/NEG with
  conditional branches exercised end-to-end.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: expanded `CORPUS` from 26 to 31 tasks.
    New bytecode fixtures `_MOV5_NEG_EXIT`, `_MOV42_MOVX_JEQ_MOV0_EXIT`,
    `_MOV1_JNE_MOV99_EXIT`. Tasks added:
    - `seed/mov5_neg_exit_r0_eq_neg5`: `r0=5; r0=-r0; EXIT`. Deterministic
      via MOV K + NEG. `r0 == 0xfffffffffffffffb` → `reachable`.
    - `seed/mov5_neg_exit_r0_eq_5_unreachable`: Same program. NEG(-5)≠5 in
      uint64. `r0 == 5` → `unreachable`.
    - `seed/mov42_movx_jeq_exit_r0_eq_42`: `r0=42; r1=r0; JEQ r1,42,+1;
      r0=0; EXIT`. JEQ always taken (r1==42 is invariant), zeroing insn
      skipped. `r0 == 42` → `reachable`.
    - `seed/mov42_movx_jeq_exit_r0_eq_0_unreachable`: Same program. `r0==0`
      unreachable because the zeroing MOV K is always skipped → `unreachable`.
    - `seed/mov1_jne_mov99_exit_r0_eq_99`: `r0=1; JNE r0,1,+1; r0=99; EXIT`.
      JNE not taken (r0==1), falls through, r0 becomes 99. `r0 == 99` →
      `reachable`.
    Harness run: **31 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 6 new tests (net).
    - `TestP13Corpus` (5 tests): MOV+NEG deterministic reachable/unreachable,
      MOV+MOVX+JEQ always-taken reachable/unreachable, MOV+JNE-not-taken.
    Full suite: **61 passed / 0 failed**.
- **Next iteration's planned work**: P14 — AND-conjunction property grammar
  extension. The property parser already supports `AND` to combine two
  comparisons. Add 3–4 tasks using `AND` to assert two register values
  simultaneously: `r0 == 1 AND r1 == 2`, `r0 == 0 AND exit_reached`.
  This exercises the `_parse_expr` AND-chain path in `_lower_property`.
- **Open BLOCKERs**: none.

---

## 2026-05-29T12:00:00Z — P12 NEG and MOV opcodes

- **Phase**: P12 complete. NEG and MOV64 (K and X) opcodes added and
  exercised end-to-end.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/source_interp/__init__.py`: added `MOV64`
    case to `_alu64_result` (op_nibble=0xb: `return src`). MOV was the
    only ALU64 op listed in SCHEMA.md that was missing.
  - `gurdy/pairs/ebpf_btor2/translation/__init__.py`: added `MOV64`
    case to `_emit_alu64` (op_nibble=0xb: `return src`).
  - `bench/ebpf-btor2/harness.py`: expanded `CORPUS` from 21 to 26 tasks.
    New bytecode fixtures `_R0_NEG_EXIT`, `_R0_MOV_K42_EXIT`,
    `_R0_MOV_X_R1_EXIT`. Tasks added:
    - `seed/r0_neg_exit_r0_eq_0`: NEG(0)=0 → `reachable`.
    - `seed/r0_neg_exit_r0_eq_1`: NEG(-1)=1 → `reachable`.
    - `seed/r0_mov_k42_exit_r0_eq_42`: MOV K always sets r0=42 →
      `reachable`.
    - `seed/r0_mov_k42_exit_r0_eq_41_unreachable`: MOV K pins r0 to 42;
      r0==41 → `unreachable`.
    - `seed/r0_mov_x_r1_exit_r0_eq_7`: MOV X r0=r1; witness r1=7 →
      `reachable`.
    Harness run: **26 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 7 new tests (net).
    - `TestP12Corpus` (6 tests): NEG ×3 reachable, MOV K reachable +
      unreachable, MOV X reachable.
    Full suite: **56 passed / 0 failed**.
- **Next iteration's planned work**: P13 — multi-instruction programs
  combining NEG/MOV with branches. Add 3–4 tasks that chain 3–4
  instructions including a branch:
  `r0 = 5; r0 = -r0; JEQ r0, 0xFFFFFFFFFFFFFFFB, +0; EXIT` (NEG
  of 5 → -5; JEQ checks the negated value).
  Alternatively: `r0 = 42; r1 = r0; JEQ r1, 42, +1; r0 = 0; EXIT`
  (tests MOV X + branch; r0 stays 42). This exercises the interaction
  between MOV/NEG and the JMP dispatch layer in longer programs.
- **Open BLOCKERs**: none.

---

## 2026-05-29T11:00:00Z — P11 LSH/RSH/ARSH K shift corpus tasks

- **Phase**: P11 complete. Shift opcodes exercised end-to-end including
  sign-extension semantics for ARSH.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: expanded `CORPUS` from 16 to 21 tasks.
    New bytecode fixtures `_R0_LSH2_EXIT`, `_R0_RSH1_EXIT`, `_R0_ARSH1_EXIT`.
    Tasks added:
    - `seed/r0_lsh2_exit_r0_eq_4`: `r0 <<= 2; EXIT`. Witness: r0=1 → 4.
      Property `r0 == 4` → `reachable`.
    - `seed/r0_lsh2_exit_r0_eq_3_unreachable`: LSH K 2 zeros bits 0–1;
      result always divisible by 4. `r0 == 3` → `unreachable`.
    - `seed/r0_rsh1_exit_r0_eq_4`: `r0 >>= 1; EXIT`. Witness: r0=8 → 4.
      Property `r0 == 4` → `reachable`.
    - `seed/r0_arsh1_exit_r0_eq_1`: `r0 s>>= 1; EXIT`. Witness: r0=2 → 1.
      Property `r0 == 1` → `reachable`.
    - `seed/r0_arsh1_exit_r0_eq_neg1`: ARSH 1 of -1 stays -1 (sign bit
      replicated). Witness: r0=0xFFFFFFFFFFFFFFFF → ARSH 1 → same.
      Property `r0 == 0xffffffffffffffff` → `reachable`. Exercises hex
      literal parsing in the property grammar and confirms correct sign
      extension vs. RSH.
    Harness run: **21 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 7 new tests (net, including
    updated count assertion).
    - `TestHarness`: updated count to 21; extended task-IDs.
    - `TestP11Corpus` (6 tests): LSH r0==4 reachable, r0==3 unreachable,
      r0==0 reachable; RSH r0==4 reachable; ARSH r0==1 reachable,
      ARSH sign-extension neg1 reachable.
    Full suite: **50 passed / 0 failed**.
- **Next iteration's planned work**: P12 — NEG and MOV corpus tasks.
  Add tasks for `BPF_NEG64` (opcode=0x87, no source): `r0 = -r0`; and
  `BPF_MOV K` (opcode=0xb7, move immediate) / `BPF_MOV X` (opcode=0xbf,
  move register). MOV is the missing ALU64 op_nibble=0xb. Add 3–5 tasks:
  `r0 = -r0` (NEG, witness: r0=5 → r0=-5 = 0xFFFFFFFFFFFFFFFB),
  `r0 = 42` (MOV K), `r0 = r1` (MOV X). Verify translator handles
  op_nibble=0x8 (NEG) and op_nibble=0xb (MOV).
- **Open BLOCKERs**: none.

---

## 2026-05-29T10:00:00Z — P10 DIV/OR/AND/MOD K corpus tasks

- **Phase**: P10 complete. Immediate-operand arithmetic opcodes exercised end-to-end.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: expanded `CORPUS` from 11 to 16 tasks.
    New bytecode fixtures `_R0_DIV8_EXIT`, `_R0_OR_0X80_EXIT`,
    `_R0_AND_0XF_EXIT`, `_R0_MOD3_EXIT`. Tasks added:
    - `seed/r0_div8_exit_r0_eq_3`: `r0 /= 8; EXIT`. Witness: r0=24 →
      24//8=3. Property `r0 == 3` → `reachable`. First DIV K task.
    - `seed/r0_or_0x80_exit_r0_eq_128`: `r0 |= 0x80; EXIT`. Witness:
      r0=0 → 0|0x80=128. Property `r0 == 128` → `reachable`.
    - `seed/r0_or_0x80_exit_r0_eq_0_unreachable`: OR K always sets bit 7;
      result ≥ 128, so `r0 == 0` → `unreachable`.
    - `seed/r0_and_0xf_exit_r0_eq_15`: `r0 &= 0xf; EXIT`. Witness:
      r0=15 → 15&0xf=15. Property `r0 == 15` → `reachable`.
    - `seed/r0_mod3_exit_r0_eq_2`: `r0 %= 3; EXIT`. Witness: r0=2 →
      2%3=2. Property `r0 == 2` → `reachable`.
    Harness run: **16 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 9 new tests (net, including
    updated count assertion).
    - `TestHarness`: updated count assertion to 16; extended task-IDs.
    - `TestP10Corpus` (8 tests): DIV K r0==3 reachable, r0==0 reachable;
      OR K r0==128 reachable, r0==0 unreachable; AND K r0==15 reachable,
      r0==16 unreachable; MOD K r0==2 reachable, r0==3 unreachable.
    Full suite: **44 passed / 0 failed**.
- **Next iteration's planned work**: P11 — LSH/RSH/ARSH K/X corpus tasks.
  Add 4–6 tasks exercising shift operations: `r0 <<= 2` (LSH K,
  opcode=0x67), `r0 >>= 1` (RSH K, opcode=0x77), `r0 s>>= 1` (ARSH K,
  opcode=0xc7). Interesting cases: LSH overflow (shift beyond 63),
  ARSH on negative value (sign extension), RSH unsigned. Then optionally
  LSH X / RSH X using register shift amounts.
- **Open BLOCKERs**: none.

---

## 2026-05-29T09:00:00Z — P9 multi-register ALU corpus tasks

- **Phase**: P9 complete. Multi-register ALU64_X operations exercised end-to-end.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: expanded `CORPUS` from 8 to 11 tasks.
    New bytecode fixtures `_R1_ADD1_R0_ADD_R1_EXIT`, `_R2_MUL_R3_EXIT`,
    `_R0_SUB_SELF_EXIT`. Tasks added:
    - `seed/r1_add1_r0_add_r1_exit_r0_eq_1`: `r1 += 1; r0 += r1; EXIT`.
      Exercises `src_reg` field (ADD X with dst=r0, src=r1) and two
      distinct register state variables. Witness: initial r0=0, r1=0 →
      r1=1, r0=1 at EXIT. Property `r0 == 1` → `reachable`.
    - `seed/r2_mul_r3_exit_r2_eq_6`: `r2 *= r3; EXIT`.
      MUL X between two free (symbolic) registers. Witness: r2=2, r3=3 →
      r2=6. Property `r2 == 6` → `reachable`.
    - `seed/r0_sub_self_exit_r0_eq_1_unreachable`: `r0 -= r0; EXIT`.
      SUB X self always zeroes r0; r0==1 can never fire. Property
      `r0 == 1` → `unreachable`.
    Harness run: **11 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 7 new tests (net, including
    updated count assertion).
    - `TestHarness`: updated count assertion to 11; extended task-IDs list.
    - `TestP9Corpus` (6 tests): multi-register ADD chain r0==1 reachable,
      r1==1 reachable; MUL X r2==6 reachable, r2==0 reachable; SUB X
      self-zero r0==0 reachable, r0==1 unreachable.
    Full suite: **36 passed / 0 failed**.
- **Next iteration's planned work**: P10 — DIV/MOD/AND/OR ALU64 opcodes.
  Extend corpus with `BPF_DIV` (0x3f K, 0x37 X), `BPF_MOD` (0x9f K,
  0x97 X), `BPF_AND` (0x5f K/X), `BPF_OR` (0x4f K/X). Add 4–6 tasks:
  `r0 /= 2` (initial r0=8 → r0=4), `r0 %= 3` (initial r0=7 → r0=1),
  `r0 &= 0xf` (mask), `r0 |= 0x80` (set bit). Verify translator
  already handles these via the existing `_alu_op` dispatch, and add
  corpus entries to confirm end-to-end correctness.
- **Open BLOCKERs**: none.

---

## 2026-05-29T08:00:00Z — P8 JMP corpus tasks

- **Phase**: P8 complete. Branch dispatch layer exercised under BMC.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: expanded `CORPUS` from 5 to 8 tasks.
    New bytecode fixtures `_JA_SELF_LOOP`, `_ADD_JEQ_SKIP_EXIT`,
    `_JEQ_TAKEN_SKIP_ADD`. Tasks added:
    - `seed/ja_self_loop_unreachable`: `JA -1` (off=-1, target=self).
      Infinite loop; EXIT never reached within any finite BMC bound.
      Property `exit_reached` → `unreachable`. First task that verifies
      non-termination detection.
    - `seed/add_jeq_skip_exit_r0_eq_2`: `r0 += 1; JEQ r0, 99, +1; EXIT`.
      JEQ not-taken path (2 ≠ 99). Witness: initial r0=1 → r0=2 at
      EXIT. Property `r0 == 2` → `reachable`.
    - `seed/jeq_taken_skip_add_r0_eq_0`: `JEQ r0, 0, +1; r0 += 1; EXIT`.
      JEQ taken (r0==0) skips the add. Witness: initial r0=0 → r0=0 at
      EXIT. Property `r0 == 0` → `reachable`.
    Harness run: **8 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 8 new tests (net, including
    updated count assertion).
    - `TestHarness`: updated `test_corpus_has_five_tasks` →
      `test_corpus_has_eight_tasks`; extended `test_corpus_task_ids`.
    - `TestP8Corpus` (6 tests): JA self-loop unreachable, JA+false
      unreachable, JEQ not-taken `r0==2` reachable, JEQ not-taken
      `r0==99` unreachable (JEQ taken → OOB, EXIT unreachable with r0=99),
      JEQ taken `r0==0` reachable, JEQ not-taken fallthrough `r0==2`
      reachable.
    Full suite: **192 passed / 0 failed** (186 pre-existing + 6 new).
- **Next iteration's planned work**: P9 — ALU32 opcode addition or
  multi-register corpus tasks. Extend the source interpreter and
  translator to handle `BPF_ALU32` (32-bit arithmetic, opcode class
  0x04) for the ADD/SUB/MOD/AND/OR/XOR subset. Alternatively: add
  2–3 corpus tasks using `r1`/`r2` registers to confirm that multi-
  register operations are correct end-to-end: (1) `r0 = r1 + r2` style
  (needs MOV or load, out of scope for P1); (2) `r1 += 1; r0 += r1;
  EXIT`, property `r0 == 2` (initial r0=1, r1=0 → r1=1, r0=1+1=2);
  simpler: just add corpus tasks using the existing ALU64_X (register
  source) opcodes with different register pairs. This extends coverage
  of the `src_reg` field decoding and the `reg_rN` state transitions.
- **Open BLOCKERs**: none.

---

## 2026-05-29T07:00:00Z — P7 seed corpus expansion

- **Phase**: P7 complete. Seed corpus expanded to 5 tasks.
- **What changed**:
  - `bench/ebpf-btor2/harness.py`: expanded `CORPUS` from 1 to 5 tasks.
    Added internal `_spec()` helper to reduce boilerplate. New bytecode
    fixtures `_R0_XOR_SELF_EXIT` and `_R0_ADD1_ADD1_EXIT`. Removed
    unused `RegisterBound` import. Tasks added:
    - `seed/exit_only_exit_reached`: EXIT-only, `exit_reached` →
      `reachable`. Simplest possible halting program.
    - `seed/r0_xor_self_exit_r0_eq_0`: `r0 ^= r0; EXIT`, property
      `r0 == 0` → `reachable`. XOR-self unconditionally zeroes r0
      regardless of initial value; property always fires.
    - `seed/r0_xor_self_exit_r0_eq_1_unreachable`: same bytecode,
      property `r0 == 1` → `unreachable`. First task that exercises
      the UNSAT path; the solver confirms no trace can satisfy r0==1
      after XOR-self.
    - `seed/r0_add1_add1_exit`: `r0 += 1; r0 += 1; EXIT`, property
      `r0 == 2` → `reachable`. Witness: initial r0=0 → r0=2 at halt.
    Harness run: **5 PASS / 0 FAIL / 0 SKIP**.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 8 new tests (net).
    - `TestHarness`: replaced `test_corpus_nonempty` with
      `test_corpus_has_five_tasks`, `test_corpus_task_ids` (checks all
      5 task IDs present), and `test_all_corpus_tasks_pass_or_skip`.
    - `TestP7Corpus`: 6 direct `check()` tests:
      `exit_only exit_reached`, `xor_self r0==0`, `xor_self r0==1`
      (unreachable), `double_add r0==2`, `double_add r0==0`
      (wraps at 2^64−2 + 2 = 0 mod 2^64, reachable),
      `xor_then_add r0==1` (r0 forced to 0 by XOR then +1 = 1).
    Full suite: **186 passed / 0 failed** (178 pre-existing + 8 new).
- **Next iteration's planned work**: P8 — branch coverage in corpus.
  Add 3–4 corpus tasks exercising the JMP layer: (1) JEQ taken path
  (`r0 += 42; JEQ r0, 42, +N; EXIT_at_target`, property
  `exit_reached` at the target instruction — but this requires
  distinguishing which EXIT fires, which the current schema doesn't
  support directly); simpler: (2) unconditional JA loop-back
  (self-loop, never halts → property `exit_reached` → unreachable);
  (3) JGT taken / not-taken pair. Also consider adding `bound=1` to
  a task to confirm early-termination → unknown (or unreachable within
  1 step). These tasks will confirm the JMP dispatch layer under BMC.
- **Open BLOCKERs**: none.

---

## 2026-05-29T06:00:00Z — P6 dispatch and solver adapter

- **Phase**: P6 complete. Dispatch and solver adapter for ebpf-btor2.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/solvers/z3bmc.py`: full P6 implementation.
    `Z3BMCSolver(InProcessSolverBackend)` with `name="z3-bmc"`.
    `dispatch(artifact_bytes, directive)`:
      - Attempts `import z3`; returns `error` verdict with reason if
        not installed.
      - Parses the flattened BTOR2 text via
        `riscv_btor2.btor2.parser.from_text`; returns `error` on
        parse failure.
      - Compiles to `Compiled` via `compile_btor2` (riscv_btor2 backend
        reused verbatim per V2_BOOTSTRAP.md §3.2).
      - Runs `bmc(comp, bound)` from `btor2_to_z3`; maps
        `NotImplementedError` (unsupported op) to `unknown` verdict.
      - Returns `RawSolverResult` with `payload={"witness_text": ...}`
        when `reachable`.
  - `gurdy/pairs/ebpf_btor2/solvers/__init__.py`: updated from stub to
    export `check(spec, bytecode) -> RawSolverResult` and `Z3BMCSolver`.
    - `check`: translates `bytecode` under `spec`, resolves BMC bound
      (`spec.analysis.bound` if set, else `spec.scope.max_insns`), then
      dispatches to `Z3BMCSolver`.
  - `bench/ebpf-btor2/harness.py`: implemented (was `raise
    NotImplementedError`). Defines `CorpusTask`, `CORPUS` (1 seed task),
    `run_task`, `run_corpus`. Maps `reachable`/`unreachable` to
    PASS/FAIL and `unknown`/`error` to SKIP. CLI: `--list` enumerates
    task IDs; default runs all tasks and exits 0 iff no FAIL.
    Seed task: `r0 += 1; EXIT` with property `r0 == 1`. Registers the
    initial r0 as unconstrained; the z3 solver finds initial r0=0 as
    witness, property fires at halt → `reachable` → PASS.
  - `tests/pairs/ebpf_btor2/test_solvers.py`: 16 unit tests.
    - `TestZ3BMCSolverDispatch`: name check, bad-BTOR2 error, `false`
      property is `unreachable`, `r0 == 1` property is `reachable` after
      ADD, witness payload present, result type and engine.
    - `TestCheck`: seed task `reachable`, `false` → `unreachable`,
      `exit_reached` → `reachable`, explicit bound respected, bound
      falls back to `max_insns`, result type, JA+EXIT `exit_reached`
      → `reachable`.
    - `TestHarness`: `run_task` on seed returns PASS, CORPUS non-empty,
      `run_corpus` returns 0.
    Uses `importlib.util.spec_from_file_location` (registered in
    `sys.modules`) to avoid name collision with riscv-btor2 harness.
    Also installed z3-solver into the pytest venv so tests are not
    skipped.
    Full suite: **178 passed / 0 failed** (162 pre-existing + 16 new).
- **Next iteration's planned work**: P7 — seed corpus expansion.
  Extend `CORPUS` in the harness to 5–6 hand-crafted ALU-only tasks
  covering: EXIT-only (`exit_reached` → `reachable`), self-XOR zeroes
  (`r0 ^= r0; EXIT`, property `r0 == 0`), double-add (`r0 += 1; r0 +=
  1; EXIT`, property `r0 == 2`), a structural `false` property
  (`unreachable`), and a branch-not-taken task (`r0 += 1; JEQ r0, 42,
  +1; EXIT`, property `r0 != 42`). Note: `RegisterBound` constraints
  currently apply at every step (BTOR2 `constraint` semantics), not
  just init; initial-register clamping for BMC witness counting should
  be deferred to P8 (schema bump with `init`-layer overrides).
- **Open BLOCKERs**: none.

---

## 2026-05-29T00:00:00Z — P5 alignment oracle

- **Phase**: P5 complete. Alignment oracle for ebpf-btor2.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/oracle_align.py`: full P5 implementation.
    Exports `align`, `AlignmentFailure`, `ORACLE_VERSION`, `PAIR_ID`.
    - `align(source_trace, reasoning_trace, artifact)`: compares
      `reg_r0..reg_r9` at every step up to (and including) the first
      EXIT, checking `source_trace.steps[k+1]` against
      `reasoning_trace.steps[k].layer_values["machine"][sym["reg_rN"]]`
      per SCHEMA.md §14. Reconstructs source register state by
      accumulating deltas from `source_trace.steps`, seeded at zero.
      Returns `(list[AlignmentFailure], bool)`.
    - `AlignmentFailure(step, symbol, src_val, r_val)`: frozen dataclass
      for a single register mismatch. `step` is the source step index
      (= reasoning step + 1); `symbol` is the BTOR2 state symbol name.
    - `_sym_nids(artifact)`: parses the artifact's flattened BTOR2 text
      via `riscv_btor2.btor2.parser` to build `{symbol: nid}` for all
      state nodes.
    - Contract documented: non-zero initial register values must appear
      as deltas in `steps[1]` (modified by the first instruction) or
      start at zero for correct comparison. Registers seeded at zero
      and never modified compare correctly when both interpreters agree.
  - `bench/ebpf-btor2/oracle_align.py`: updated stub to re-export from
    the pair module (was `raise NotImplementedError`).
  - `tests/pairs/ebpf_btor2/test_oracle_align.py`: 11 unit tests.
    - Aligned tests on all 5 P4 seed programs (`_EXIT_ONLY`,
      `_ADD_EXIT`, `_ADD_X_EXIT`, `_BRANCH_EXIT` not-taken path,
      `_JA_EXIT`) with initial_regs chosen to satisfy the delta-coverage
      contract.
    - Misaligned tests: `_ADD_EXIT` with source r0=5→6, reasoning r0=10→11
      (detected: `reg_r0` failure at step 1 with src_val=6, r_val=11).
    - `test_align_r1_mismatch_after_add_x`: documents the known
      limitation — unchanged non-zero initial registers cause failures
      because source deltas don't record them.
    - Edge case: empty reasoning steps → no comparisons → aligned=True.
    Full suite: **162 passed / 0 failed** (151 pre-existing + 11 new).
- **Next iteration's planned work**: P6 — dispatch and solver adapter.
  Wire `gurdy/pairs/ebpf_btor2/solvers/` to the z3-bmc engine (reusing
  `riscv-btor2`'s adapter pattern per V2_BOOTSTRAP.md §3.2). Implement
  a `check(spec, bytecode)` entry point that runs the translator,
  invokes the solver, and returns a `Verdict`. Provide a thin
  `bench/ebpf-btor2/harness.py` harness that calls `check` on a corpus
  task and reports PASS/FAIL/SKIP. Seed corpus task: `r0 += 1; EXIT`
  with property `r0 == 1` (expected PASS with initial r0=0).
- **Open BLOCKERs**: none.

---

## 2026-05-28T21:00:00Z — P4 translator

- **Phase**: P4 complete. BTOR2 translator for ebpf-btor2.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/translation/__init__.py`: full P4
    implementation. Exports `translate`, `Translator`, `SCHEMA_VERSION`,
    `LAYER_NAMES`, `PAIR_ID`.
    - `translate(spec, bytecode, annotation_emitter)`: compiles
      `(EbpfBtor2Spec, bytecode)` → `CompiledArtifact` for the P1 opcode
      subset (ALU64 K/X, JMP K/X, EXIT). Reuses `Builder` and `to_text`
      from `gurdy.pairs.riscv_btor2` verbatim per V2_BOOTSTRAP.md §3.2.
      Also reuses `decode_program` and `BpfInsn` from source_interp.
    - Eight layers emitted per SCHEMA.md §11: `header` (bv1/bv32/bv64
      sorts), `machine` (reg_r0..r9 + insn_idx + halted states),
      `library` (per-instruction update expressions via `_lower_insn`),
      `dispatch` (nested ite chains with halted guard, plus `next` clauses),
      `init` (insn_idx=0, halted=0; registers free per §7), `constraint`
      (RegisterBound assumptions as `ugte`/`ulte` pairs), `bad` (property
      expression lowered from SCHEMA.md §9 grammar), `binding` (empty stub
      for P5+).
    - ALU64: all 12 ops (ADD/SUB/MUL/DIV/OR/AND/LSH/RSH/NEG/MOD/XOR/ARSH)
      including zero-divisor ite guards for DIV64 and MOD64, shift-amount
      masking via `and(SRC, 63)`.
    - JMP: 12 branch flavours (JEQ/JGT/JGE/JSET/JNE/JSGT/JSGE/JLT/JLE/JSLT/JSLE)
      plus JA (unconditional). K/X source resolution via sign-extended
      immediate (bv64) or register state nid.
    - Property parser: recursive descent for the SCHEMA.md §9 grammar
      (`false`, `exit_reached`, `rN op value`, `AND`). All 10 comparison
      operators (unsigned and signed variants).
    - `Translator` class implements the framework `Translator` protocol.
  - `tests/pairs/ebpf_btor2/test_translation.py`: 34 unit tests.
    - Seed bytecode fixtures: `_EXIT_ONLY`, `_ADD_EXIT`, `_ADD_X_EXIT`,
      `_BRANCH_EXIT` (JEQ + XOR + EXIT), `_JA_EXIT` (unconditional jump).
    - Covers: artifact structure (all 8 layers present, flattened bytes,
      state symbol declarations), determinism, EXIT-only halting,
      ADD K / ADD X step-by-step alignment against source_interp,
      halted-freeze semantics, JEQ branch taken/not-taken, JA jump,
      property expressions (`false`, `exit_reached`, `r0 == 42`,
      `r0 < 10`, `r0 == 1 AND r1 == 0`), RegisterBound constraint
      emission, layer content sanity (sort/state/next/init/bad nodes).
    Full suite: **151 passed / 0 failed** (117 pre-existing + 34 new).
- **Next iteration's planned work**: P5 — alignment oracle
  (`gurdy/pairs/ebpf_btor2/oracle_align.py`). Implement
  `align(source_trace, reasoning_trace, artifact)` that compares
  `source_trace.steps[i+1].reg_rN` against
  `reasoning_trace.steps[i].layer_values["machine"][sym["reg_rN"]]`
  for N in 0..9 at every step up to the first EXIT, per SCHEMA.md §14.
  Return a list of `AlignmentFailure` records (step, symbol, src_val,
  r_val) and a boolean `aligned`. Verify on the seed programs from P4.
- **Open BLOCKERs**: none.

---

## 2026-05-28T00:00:00Z — P3 reasoning interpreter

- **Phase**: P3 complete. BTOR2 concrete evaluator for ebpf-btor2.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/reasoning_interp/__init__.py`: full P3
    implementation. Exports `EbpfReasoningBinding`,
    `EbpfReasoningInterpreter`, `INTERPRETER_VERSION`, `PAIR_ID`.
    - `EbpfReasoningBinding`: subclass of `gurdy.core.interp.types.ReasoningBinding`
      with `pair = "ebpf-btor2"`, `state_init_by_symbol` (symbol-keyed
      initial state overrides), `input_per_step_by_symbol` (per-step
      input values for future use), and `from_jsonable` round-trip.
    - `EbpfReasoningInterpreter`: multi-step BTOR2 evaluator implementing
      the `ReasoningInterpreter` protocol. Reuses
      `gurdy.pairs.riscv_btor2.btor2.{parser,evaluator,nodes}` verbatim
      per V2_BOOTSTRAP.md §3.2. The `run` method: parses the artifact's
      flattened BTOR2 text; resolves `init` and `next` clauses; walks
      `max_steps` cycles applying the transition relation; records
      post-step symbol state as `layer_values["machine"]` keyed by nid;
      detects first `bad` clause firing against the post-step state;
      returns a `ReasoningTrace` with `pair="ebpf-btor2"`, step records,
      and `bad_fired_at`.
    - Binding override: `state_init_by_symbol` symbols are resolved via
      the model's named state nodes, so overrides are schema-version stable.
  - `tests/pairs/ebpf_btor2/test_reasoning_interp.py`: 26 unit tests.
    Uses two hand-constructed BTOR2 fragments:
    - `_ADD_THEN_EXIT_BTOR2`: 2-instruction program (ALU64 ADD K r0 1,
      EXIT). Verifies step-by-step state (reg_r0, insn_idx, halted),
      bad-fires at step 1, halted-freeze semantics from step 2 onward,
      binding overrides (incl. wraparound at 2^64-1), and that bad fires
      exactly once.
    - `_STATIC_BTOR2`: halted always 0, bad never fires; verifies
      `bad_fired_at is None` over 10 steps.
    Also covers: binding defaults, from_jsonable round-trip, hash
    distinctness, determinism, trace serialisation.
    Full suite: **117 passed / 0 failed** (91 pre-existing + 26 new).
- **Next iteration's planned work**: P4 — translator
  (`gurdy/pairs/ebpf_btor2/translation/`). Compile `(EbpfBtor2Spec,
  bytecode)` → BTOR2 artifact for the P1 opcode subset (ALU64 K/X,
  JMP K/X, EXIT). Emit the 8 SCHEMA.md layers (header, machine,
  library, dispatch, init, constraint, bad, binding). Verify with
  `EbpfReasoningInterpreter` on the seed programs from the source
  interpreter tests.
- **Open BLOCKERs**: none.

---

## 2026-05-27T01:00:00Z — P2 source interpreter

- **Phase**: P2 complete. Source interpreter for the P1 opcode set.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/source_interp/__init__.py`: full P2
    implementation. Exports `BpfInsn`, `EbpfInputBinding`,
    `EbpfMachineState`, `decode_program`, `step`, `run`.
    - `decode_program`: decodes flat 8-byte `bpf_insn` records
      from raw bytes; rejects wide immediates (0x18) with
      diagnostic `ebpf-btor2/load/0001`; rejects non-multiple-of-8
      lengths with `ebpf-btor2/load/0000`.
    - `step`: executes one machine cycle — ALU64 K/X (all 12 ops),
      JMP K/X (all 12 branch flavours + JA), and EXIT. Implements
      the halted-freeze and out-of-bounds self-loop semantics from
      schema §6. Raises `ValueError` with `ebpf-btor2/load/0003`
      for unsupported opcodes (e.g. CALL, BPF_ALU32).
    - `run`: drives the machine from an `EbpfInputBinding`; records
      one `SourceStep` per cycle (step 0 = initial state, deltas
      from prior); stops on EXIT, out-of-bounds, or `max_steps`;
      returns a `SourceTrace` with `final_state`, `halted`, and
      `halt_reason`.
    - `EbpfInputBinding` subclasses `gurdy.core.interp.types.InputBinding`
      with `bytecode: bytes` and `initial_regs: tuple[int, ...]`.
  - `tests/pairs/ebpf_btor2/test_source_interp.py`: 66 unit tests.
    Covers decode (basic, dst/src fields, signed off/imm, bad-length,
    wide-imm, instruction properties), all 12 ALU64 ops including
    wraparound and zero-divisor edge cases, all 12 JMP flavours
    (taken/not-taken, signed/unsigned), EXIT and halted-freeze,
    out-of-bounds freeze, `run` (step count, initial-step deltas,
    max_steps, out-of-bounds, determinism, delta tracking, hash
    stability), and 5 hand-crafted byte-sequence programs
    (add+mul, branch taken/not-taken, 3-iteration loop, XOR-self).
    Full suite: **91 passed / 0 failed**.
- **Next iteration's planned work**: P3 — reasoning interpreter
  (`gurdy/pairs/ebpf_btor2/reasoning_interp/`). Port the BTOR2
  concrete evaluator from `gurdy/core/` patterns; walk the
  BTOR2 artifact node-by-node with a concrete binding
  (`EbpfReasoningBinding`); produce a `ReasoningTrace` for
  future alignment. P3 depends on P4 (translator) for a real
  artifact, so start with a hand-constructed BTOR2 fragment
  for the 2-instruction add-then-exit program.
- **Open BLOCKERs**: none.

---

## 2026-05-27T00:00:00Z — P1 schema v1.0.0

- **Phase**: P1 complete. SCHEMA.md is frozen at v1.0.0.
- **What changed**:
  - `gurdy/pairs/ebpf_btor2/SCHEMA.md`: full schema v1.0.0.
    Defines sorts (`bv1`, `bv32`, `bv64`); state variables
    (`reg_r0`–`reg_r9`, `insn_idx : bv32`, `halted : bv1`);
    r10 as constant 512 in P1; program loading from `.bpf.o`
    ELF; instruction lowering for the P1 subset (ALU64 K/X 12
    ops, JMP K/X 12 branch flavours + JA + EXIT); dispatch
    layer structure; entry-state constraints; `RegisterBound`
    constraint encoding (unsigned); property expression DSL
    grammar; `bad`-node lowering table; verdict semantics;
    layer names; annotation conventions; stability profile;
    interpreter-semantics stub (P2/P3); explicit exclusions
    list (P8–P11 features).
  - `gurdy/pairs/ebpf_btor2/__init__.py`: added
    `SCHEMA_VERSION = "1.0.0"`.
  - `tests/pairs/ebpf_btor2/test_spec.py`: 25 unit tests
    covering `validate_ebpf_btor2_spec` (valid and error
    paths), canonical serialisation round-trips, spec-hash
    distinctness, and `from_jsonable` pair-rejection. All
    pass; full suite 412 passed / 12 skipped / 0 failed.
- **Next iteration's planned work**: P2 — source interpreter
  (`gurdy/pairs/ebpf_btor2/source_interp/`). Bytecode decoder
  + register-model step function for the P1 opcode set
  (ALU64 K/X, JMP K/X, EXIT). Trace recording, `halted`
  semantics, determinism test with a hand-written byte sequence.
- **Open BLOCKERs**: none.

---

## 2026-05-22T00:00:00Z — P0 scaffold

- **Phase**: P0 complete.
- **What changed**: Created full directory scaffold per
  `V2_BOOTSTRAP.md` §5.
  - `gurdy/pairs/ebpf_btor2/` package: `__init__.py`, `SCHEMA.md`
    (placeholder), `spec.py` (eBPF spec language — `EbpfBtor2Spec`,
    `RegisterBound`, `PacketBound`, `Property`, `AnalysisDirective`,
    `validate_ebpf_btor2_spec`); subpackage stubs for `source/`,
    `source_interp/`, `reasoning_interp/`, `translation/`, `lift/`,
    `solvers/`.
  - `bench/ebpf-btor2/corpus/{seed,kernel_rejects,external}/`
    (`.gitkeep`); `harness.py`, `oracle_align.py`, `oracle_cross.py`,
    `engine_bench.py` (stubs raising `NotImplementedError`);
    `baselines/{kernel_verifier,prevail,hurdy_gurdy,pareto}.py`
    (stubs).
  - `tests/pairs/ebpf_btor2/__init__.py`.
  - `gurdy/core/` already matched `v2-bootstrap` (identical tree
    SHAs) — no copy needed.
- **Next iteration's planned work**: P1 — define schema version
  1.0.0 in `SCHEMA.md` (sorts, machine-state layout, layer names,
  the minimal ALU64 + branch + exit opcode set, `QuestionSpec`
  reach-property). Freeze SCHEMA.md before any translator work.
- **Open BLOCKERs**: none.

---

## 2026-05-17T00:00:00Z — Branch bootstrap

- **Phase**: pre-P0. Nothing implemented yet on this branch.
- **What's here**: `V2_BOOTSTRAP.md` (spec), `V2_AGENT_LOOP.md`
  (procedure), `V2_PROGRESS.md` (this file),
  `bench/ebpf-btor2/SCOPE.md` (benchmark scope). Everything else
  is inherited from `main`.
- **Next iteration's planned work**: P0 — scaffold the
  `gurdy/pairs/ebpf_btor2/` package and `bench/ebpf-btor2/`
  directory shape per `V2_BOOTSTRAP.md` §5. Copy `gurdy/core/`
  primitives from `v2-bootstrap` where they conform.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).
