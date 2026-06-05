# `wasm-btor2` Progress — Live State

> The single source of truth for "where is the `wasm-btor2` bootstrap
> right now." Each iteration appends one entry at the top. Older
> entries stay for history.
>
> See `V2_AGENT_LOOP.md` §6 for the entry format.

---

## 2026-06-05T01:40:00Z — P39: `i64.load8_u` lowering + corpus seed 0031

- **Phase**: P39 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    `i64.load8_u` (0x31) per-instruction lowering in `_lower_instr`:
    pop i32 address (TOS at SP-1) via `_stack_pop_i32`; add static
    `offset` immediate (bv32 wrap); bounds-check using bv64 arithmetic
    (`ea64 + 1 > mem_bytes64`); on OOB set `trap_nid`; on in-bounds
    read 1 byte from `linear_mem` (`byte0 = b.read("bv8", ...)` at
    `ea`); zero-extend bv8 → bv64 via `b.uext("bv64", byte0, 56)`;
    write bv64 result directly to stack slot sp-1 (TOS replaced, SP
    unchanged); `next_mem_nid` stays None (read-only). Updated module
    docstring for P39 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added four
    new module constants (`_BODY_LOAD8_U_I64`, `_WASM_LOAD8_U_I64`:
    no params, 1 initial page, body `i32.const 0; i64.load8_u align=0
    offset=0; drop; end`; `_BODY_LOAD8_U_I64_OFFSET`,
    `_WASM_LOAD8_U_I64_OFFSET`: same with offset=1) and 5 new tests
    under a new P39 section (2 compile + 1 `linear_mem` present + 2
    reasoning interpreter no-trap for i64.load8_u).
  - Created `bench/wasm-btor2/corpus/seed/0031-load8-u-i64-no-trap/module.wasm`
    — 45-byte WASM module: no params, no results, 1 initial page (no
    max), body `i32.const 0; i64.load8_u align=0 offset=0; drop; end`,
    exported as `main`.
    SHA-256: `39d229d716ba62deec986eb2b8586fe6156d13246c5bdd28c73359be08c1eca8`.
  - Created `bench/wasm-btor2/corpus/seed/0031-load8-u-i64-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8, task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0031.py` — 17
    tests: file-shape checks, spec round-trip, decoder
    instruction-sequence validation, decoder memory-section check,
    translation compiles, BTOR2 parseable, `linear_mem` present, and
    reasoning interpreter confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 1029 passed, 0
  failed (previously 1007 passed, 0 failed; +22 new tests: 5
  translation + 17 seed).
- **Next iteration's planned work**: P40 — `i64.load8_s` (0x30),
  sign-extending 8-bit load into i64. Identical to `i64.load8_u` but
  uses `b.sext("bv64", byte0, 56)` instead of `b.uext`. Pop i32
  address; bounds-check `ea64 + 1 > mem_bytes64`; read 1 byte; sext
  bv8 → bv64; write bv64 to stack slot sp-1. Add corpus seed 0032.
  After P40, all i64 linear-memory load instructions are complete
  (0x28-0x35); the next group will be i64 stores.
- **Open BLOCKERs**: none.

---

## 2026-06-05T01:20:00Z — P38: `i64.load16_s` lowering + corpus seed 0030

- **Phase**: P38 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    `i64.load16_s` (0x32) per-instruction lowering in `_lower_instr`:
    identical to `i64.load16_u` (P37) except the bv16 half is
    sign-extended to bv64 via `b.sext("bv64", half, 48)` instead of
    zero-extended. Pop i32 address (TOS at SP-1); add static `offset`
    immediate (bv32 wrap); bounds-check `ea64 + 2 > mem_bytes64`; read
    2 bytes little-endian from `linear_mem`; concat to bv16; sext bv16
    → bv64; write bv64 to stack slot sp-1 (SP unchanged, TOS replaced);
    `next_mem_nid` stays None (read-only). Updated module docstring for
    P38 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added four
    new module constants (`_BODY_LOAD16_S_I64`, `_WASM_LOAD16_S_I64`:
    no params, 1 initial page, body `i32.const 0; i64.load16_s align=0
    offset=0; drop; end`; `_BODY_LOAD16_S_I64_OFFSET`,
    `_WASM_LOAD16_S_I64_OFFSET`: same with offset=2) and 5 new tests
    under a new P38 section (2 compile + 1 `linear_mem` present + 2
    reasoning interpreter no-trap for i64.load16_s).
  - Created `bench/wasm-btor2/corpus/seed/0030-load16-s-i64-no-trap/module.wasm`
    — 45-byte WASM module: no params, no results, 1 initial page (no
    max), body `i32.const 0; i64.load16_s align=0 offset=0; drop; end`,
    exported as `main`.
    SHA-256: `d7089394daab23bfb8e098b8bb67b1277aab32a62d50ce85587b6966eb353c9b`.
  - Created `bench/wasm-btor2/corpus/seed/0030-load16-s-i64-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8, task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0030.py` — 17
    tests: file-shape checks, spec round-trip, decoder
    instruction-sequence validation, decoder memory-section check,
    translation compiles, BTOR2 parseable, `linear_mem` present, and
    reasoning interpreter confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 1007 passed, 0
  failed (previously 985 passed, 0 failed; +22 new tests: 5
  translation + 17 seed).
- **Next iteration's planned work**: P39 — `i64.load8_u` (0x31),
  zero-extending 8-bit load into i64. Pop i32 address (TOS at SP-1);
  add static `offset` immediate (bv32 wrap); bounds-check
  `ea64 + 1 > mem_bytes64`; read 1 byte from `linear_mem`
  (`byte0 = mem[ea]`); zero-extend bv8 → bv64 via
  `b.uext("bv64", byte0, 56)`; write bv64 to stack slot sp-1
  (SP unchanged). Add corpus seed 0031.
- **Open BLOCKERs**: none.

---

## 2026-06-05T01:00:00Z — P37: `i64.load16_u` lowering + corpus seed 0029

- **Phase**: P37 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    `i64.load16_u` (0x33) per-instruction lowering in `_lower_instr`:
    pop i32 address (TOS at SP-1); add static `offset` immediate (bv32
    wrap); bounds-check `ea64 + 2 > mem_bytes64`; read 2 bytes
    little-endian from `linear_mem` (`byte0 = mem[ea]`,
    `byte1 = mem[ea+1]`); concat to bv16 (`concat(byte1, byte0)`);
    zero-extend bv16 → bv64 via `b.uext("bv64", half, 48)`; write bv64
    result to stack slot sp-1 (SP unchanged, TOS replaced); `next_mem_nid`
    stays None (read-only). Updated module docstring for P37 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added four
    new module constants (`_BODY_LOAD16_U_I64`, `_WASM_LOAD16_U_I64`:
    no params, 1 initial page, body `i32.const 0; i64.load16_u align=0
    offset=0; drop; end`; `_BODY_LOAD16_U_I64_OFFSET`,
    `_WASM_LOAD16_U_I64_OFFSET`: same with offset=2) and 5 new tests
    under a new P37 section (2 compile + 1 `linear_mem` present + 2
    reasoning interpreter no-trap for i64.load16_u).
  - Created `bench/wasm-btor2/corpus/seed/0029-load16-u-i64-no-trap/module.wasm`
    — 45-byte WASM module: no params, no results, 1 initial page (no
    max), body `i32.const 0; i64.load16_u align=0 offset=0; drop; end`,
    exported as `main`.
    SHA-256: `c87d5448359118186f6abbb86de84ba4465794fa644cd3fc48733c6826b25d37`.
  - Created `bench/wasm-btor2/corpus/seed/0029-load16-u-i64-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8, task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0029.py` — 17
    tests: file-shape checks, spec round-trip, decoder
    instruction-sequence validation, decoder memory-section check,
    translation compiles, BTOR2 parseable, `linear_mem` present, and
    reasoning interpreter confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 985 passed, 0
  failed (previously 963 passed, 0 failed; +22 new tests: 5
  translation + 17 seed).
- **Next iteration's planned work**: P38 — `i64.load16_s` (0x32),
  sign-extending 16-bit load into i64. Identical to `i64.load16_u`
  but uses `b.sext("bv64", half, 48)` instead of `b.uext`. Pop i32
  address (TOS at SP-1); add static `offset` immediate; bounds-check
  `ea64 + 2 > mem_bytes64`; read 2 bytes; concat to bv16; sext bv16
  → bv64; write bv64 to stack slot sp-1. Add corpus seed 0030.
- **Open BLOCKERs**: none.

---

## 2026-06-05T00:40:00Z — P36: `i64.load32_s` lowering + corpus seed 0028

- **Phase**: P36 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    `i64.load32_s` (0x34) per-instruction lowering in `_lower_instr`:
    identical to `i64.load32_u` (P35) except the bv32 word is
    sign-extended to bv64 via `b.sext("bv64", word, 32)` instead of
    zero-extended. Pop i32 address (TOS at SP-1); add static `offset`
    immediate (bv32 wrap); bounds-check `ea64 + 4 > mem_bytes64`; read
    4 bytes little-endian from `linear_mem`; concat to bv32
    (`b3b2 = concat(bv16)`, `b3b2b1 = concat(bv24)`,
    `word = concat(bv32, b3b2b1, b0)`); sext bv32 → bv64; write bv64
    to stack slot sp-1 (SP unchanged, TOS replaced); `next_mem_nid`
    stays None (read-only). Updated module docstring for P36 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added four
    new module constants (`_BODY_LOAD32_S_I64`, `_WASM_LOAD32_S_I64`:
    no params, 1 initial page, body `i32.const 0; i64.load32_s align=0
    offset=0; drop; end`; `_BODY_LOAD32_S_I64_OFFSET`,
    `_WASM_LOAD32_S_I64_OFFSET`: same with offset=4) and 5 new tests
    under a new P36 section (2 compile + 1 `linear_mem` present + 2
    reasoning interpreter no-trap for i64.load32_s).
  - Created `bench/wasm-btor2/corpus/seed/0028-load32-s-i64-no-trap/module.wasm`
    — 45-byte WASM module: no params, no results, 1 initial page (no
    max), body `i32.const 0; i64.load32_s align=0 offset=0; drop; end`,
    exported as `main`.
    SHA-256: `a9f74be4f3c2dc3887851ab793c8d3383f5adb3617debb385712171fd2da4e98`.
  - Created `bench/wasm-btor2/corpus/seed/0028-load32-s-i64-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8, task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0028.py` — 17
    tests: file-shape checks, spec round-trip, decoder
    instruction-sequence validation, decoder memory-section check
    (1 initial page, no max), translation compiles, BTOR2 parseable,
    `linear_mem` present in flattened BTOR2, and reasoning interpreter
    confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 963 passed, 0
  failed (previously 941 passed, 0 failed; +22 new tests: 5
  translation + 17 seed).
- **Next iteration's planned work**: P37 — `i64.load16_u` (0x33),
  zero-extending 16-bit load into i64. Pop i32 address (TOS at SP-1);
  add static `offset` immediate (bv32 wrap); bounds-check
  `ea64 + 2 > mem_bytes64`; read 2 bytes little-endian from
  `linear_mem` (`byte0 = mem[ea]`, `byte1 = mem[ea+1]`);
  concat to bv16 (`concat(byte1, byte0)`); zero-extend bv16 → bv64
  via `b.uext("bv64", half, 48)`; write bv64 to stack slot sp-1
  (SP unchanged). Add corpus seed 0029.
- **Open BLOCKERs**: none.

---

## 2026-06-05T00:20:00Z — P35: `i64.load32_u` lowering + corpus seed 0027

- **Phase**: P35 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    `i64.load32_u` (0x35) per-instruction lowering in `_lower_instr`:
    pop i32 address (TOS at SP-1) via `_stack_pop_i32`; add static
    `offset` immediate (bv32 wrap) to form effective address `ea`;
    bounds-check using bv64 arithmetic (`ea64 + 4 > mem_bytes64`);
    on OOB set `trap_nid`; on in-bounds read 4 bytes little-endian
    from `linear_mem` (`b0`…`b3`) using the same concat chain as
    `i32.load` (`b3b2 = concat(bv16)`, `b3b2b1 = concat(bv24)`,
    `word = concat(bv32, b3b2b1, b0)`); zero-extend bv32 → bv64 via
    `b.uext("bv64", word, 32)`; write bv64 result directly to stack
    slot sp-1 via `b.write("stack", ...)`  (TOS replaced, SP
    unchanged); `next_mem_nid` stays None (read-only). Updated module
    docstring for P35 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added four
    new module constants (`_BODY_LOAD32_U_I64`, `_WASM_LOAD32_U_I64`:
    no params, 1 initial page, body `i32.const 0; i64.load32_u align=0
    offset=0; drop; end`; `_BODY_LOAD32_U_I64_OFFSET`,
    `_WASM_LOAD32_U_I64_OFFSET`: same with offset=4) and 5 new tests
    under a new P35 section (2 compile + 1 `linear_mem` present + 2
    reasoning interpreter no-trap for i64.load32_u).
  - Created `bench/wasm-btor2/corpus/seed/0027-load32-u-i64-no-trap/module.wasm`
    — 45-byte WASM module: no params, no results, 1 initial page (no
    max), body `i32.const 0; i64.load32_u align=0 offset=0; drop; end`,
    exported as `main`.
    SHA-256: `810880316821a1a85c78ee3ed2439fa7314629a1d79b9c2feec3e928c574113c`.
  - Created `bench/wasm-btor2/corpus/seed/0027-load32-u-i64-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8, task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0027.py` — 17
    tests: file-shape checks, spec round-trip, decoder
    instruction-sequence validation, decoder memory-section check
    (1 initial page, no max), translation compiles, BTOR2 parseable,
    `linear_mem` present in flattened BTOR2, and reasoning interpreter
    confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 941 passed, 0
  failed (previously 919 passed, 0 failed; +22 new tests: 5
  translation + 17 seed).
- **Next iteration's planned work**: P36 — `i64.load32_s` (0x34), the
  sign-extending 32-bit load into i64. Pattern mirrors `i64.load32_u`
  but uses `b.sext("bv64", word, 32)` instead of `b.uext`. Pop i32
  address (TOS at SP-1); add static `offset` immediate (bv32 wrap);
  bounds-check `ea64 + 4 > mem_bytes64`; read 4 bytes little-endian
  from `linear_mem`; concat to bv32; sign-extend bv32 → bv64; write
  bv64 to stack slot sp-1 (SP unchanged). Add corpus seed 0028.
- **Open BLOCKERs**: none.

---

## 2026-06-05T00:00:00Z — P34: `i64.load` lowering + corpus seed 0026

- **Phase**: P34 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    `i64.load` (0x29) per-instruction lowering in `_lower_instr`:
    pop i32 address (TOS at SP-1) via `_stack_pop_i32`; add static
    `offset` immediate (bv32 wrap) to form effective address `ea`;
    bounds-check using bv64 arithmetic (`ea64 + 8 > mem_bytes64`);
    on OOB set `trap_nid`; on in-bounds read 8 bytes little-endian
    from `linear_mem` at `ea`…`ea+7` via `b.read`; concat pairs to
    bv16s (`b1b0`, `b3b2`, `b5b4`, `b7b6`), then bv32s
    (`b3b2b1b0`, `b7b6b5b4`), then bv64 result
    (`b.emit("concat", "bv64", b7b6b5b4, b3b2b1b0)`); write bv64
    result directly to stack slot sp-1 via `b.write("stack", ...)`
    (TOS replaced, SP unchanged); `next_mem_nid` stays None
    (read-only). Updated module docstring for P34 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added four
    new module constants (`_BODY_LOAD64`, `_WASM_LOAD64`: no params,
    1 initial page, body `i32.const 0; i64.load align=0 offset=0;
    drop; end`; `_BODY_LOAD64_OFFSET`, `_WASM_LOAD64_OFFSET`: same
    with offset=8) and 5 new tests under a new P34 section (2 compile
    + 1 `linear_mem` present + 2 reasoning interpreter no-trap for
    i64.load).
  - Created `bench/wasm-btor2/corpus/seed/0026-load64-no-trap/module.wasm`
    — 45-byte WASM module: no params, no results, 1 initial page (no
    max), body `i32.const 0; i64.load align=0 offset=0; drop; end`,
    exported as `main`.
    SHA-256: `8b0bb65f76bfa474cfb31709cb48de9ee4ea3d7cf00cc0bcaa4eefb0bf9a6e6b`.
  - Created `bench/wasm-btor2/corpus/seed/0026-load64-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8, task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0026.py` — 17
    tests: file-shape checks, spec round-trip, decoder
    instruction-sequence validation, decoder memory-section check
    (1 initial page, no max), translation compiles, BTOR2 parseable,
    `linear_mem` present in flattened BTOR2, and reasoning interpreter
    confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 919 passed, 0
  failed (previously 897 passed, 0 failed; +22 new tests: 5
  translation + 17 seed).
- **Next iteration's planned work**: P35 — `i64.load32_u` (0x35), the
  first i64 truncating load. Pop i32 address (TOS at SP-1); add static
  `offset` immediate (bv32 wrap); bounds-check `ea64 + 4 > mem_bytes64`;
  read 4 bytes little-endian from `linear_mem` (`b0`…`b3`); concat to
  bv32 (same as i32.load); zero-extend bv32 → bv64 via
  `b.uext("bv64", word, 32)`; write bv64 result to stack slot sp-1
  (SP unchanged). Add corpus seed 0027.
- **Open BLOCKERs**: none.

---

## 2026-06-04T01:00:00Z — P33: `i32.load16_s` lowering + corpus seed 0025

- **Phase**: P33 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    `i32.load16_s` (0x2E) per-instruction lowering in `_lower_instr`:
    pop i32 address (TOS at SP-1); add static `offset` immediate (bv32
    wrap) to form effective address `ea`; bounds-check using bv64
    arithmetic (`ea64 + 2 > mem_bytes64`); on OOB set `trap_nid`; on
    in-bounds read 2 bytes little-endian from `linear_mem` at `ea` and
    `ea+1` via `b.read`; concat to bv16 (`b.emit("concat", "bv16",
    byte1, byte0)`); sign-extend from bv16 to bv32 via
    `b.sext("bv32", half, 16)`; push result via `_stack_push_i32`
    (TOS replaced, SP unchanged); `next_mem_nid` stays None
    (read-only). Updated module docstring for P33 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added four
    new module constants (`_BODY_LOAD16_S`, `_WASM_LOAD16_S`: no
    params, 1 initial page, body `i32.const 0; i32.load16_s align=0
    offset=0; drop; end`; `_BODY_LOAD16_S_OFFSET`,
    `_WASM_LOAD16_S_OFFSET`: same with offset=4) and 5 new tests under
    a new P33 section (2 compile + 1 `linear_mem` present + 2
    reasoning interpreter no-trap for load16_s).
  - Created `bench/wasm-btor2/corpus/seed/0025-load16-s-no-trap/module.wasm`
    — 45-byte WASM module: no params, no results, 1 initial page (no
    max), body `i32.const 0; i32.load16_s align=0 offset=0; drop; end`,
    exported as `main`.
    SHA-256: `ce77a39003273d575fab075d9198125cc04ca3a262e8252dea508d0c1e728270`.
  - Created `bench/wasm-btor2/corpus/seed/0025-load16-s-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8, task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0025.py` — 17
    tests: file-shape checks, spec round-trip, decoder
    instruction-sequence validation, decoder memory-section check
    (1 initial page, no max), translation compiles, BTOR2 parseable,
    `linear_mem` present in flattened BTOR2, and reasoning interpreter
    confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 897 passed, 0
  failed (previously 875 passed, 0 failed; +22 new tests: 5
  translation + 17 seed).
- **Next iteration's planned work**: P34 — `i64.load` (0x29), the
  first i64 linear-memory instruction. All i32 memory instructions are
  now complete. The stack already stores bv64 values (confirmed from
  P23/P24 i64 arithmetic). `i64.load`: pop i32 address (TOS at SP-1);
  add static `offset` immediate (bv32 wrap); bounds-check
  `ea64 + 8 > mem_bytes64`; read 8 bytes little-endian from
  `linear_mem` (`byte0`…`byte7`); concat to bv64; push result via
  `_stack_push_i64` (or equivalent — TOS replaced, SP unchanged);
  `next_mem_nid` stays None. Add corpus seed 0026.
- **Open BLOCKERs**: none.

---

## 2026-06-04T00:00:00Z — P32: `i32.load16_u` + `i32.store16` lowerings + corpus seed 0024

- **Phase**: P32 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    `i32.load16_u` (0x2F) per-instruction lowering in `_lower_instr`:
    pop i32 address (TOS at SP-1); add static `offset` immediate (bv32
    wrap) to form effective address `ea`; bounds-check using bv64
    arithmetic (`ea64 + 2 > mem_bytes64`); on OOB set `trap_nid`; on
    in-bounds read 2 bytes little-endian from `linear_mem` at `ea` and
    `ea+1` via `b.read`; concat to bv16 (`b.emit("concat", "bv16",
    byte1, byte0)`); zero-extend from bv16 to bv32 via
    `b.uext("bv32", half, 16)`; push result via `_stack_push_i32`
    (TOS replaced, SP unchanged); `next_mem_nid` stays None
    (read-only). Added `i32.store16` (0x3B) per-instruction lowering:
    pop i32 value (TOS at SP-1) and i32 address (SP-2); add static
    `offset` immediate; bounds-check (`ea64 + 2 > mem_bytes64`); on
    OOB set `trap_nid`; extract 2 low bytes little-endian
    (`byte0 = value[7:0]`, `byte1 = value[15:8]`); chain two array
    writes (`b.write` at `ea` and `ea+1`); guard write with
    `b.ite("linear_mem", in_bounds, mem2, ctx.mem_nid)`; set
    `next_mem_nid` to the ITE result; `next_sp_nid = sp_m2` (SP
    decremented by 2). Updated module docstring for P32 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added four
    new module constants (`_BODY_LOAD16_U`, `_WASM_LOAD16_U`: no
    params, 1 initial page, body `i32.const 0; i32.load16_u align=0
    offset=0; drop; end`; `_BODY_LOAD16_U_OFFSET`,
    `_WASM_LOAD16_U_OFFSET`: same with offset=4; `_BODY_STORE16`,
    `_WASM_STORE16`: `i32.const 0; i32.const 42; i32.store16 align=0
    offset=0; end`; `_BODY_STORE16_OFFSET`, `_WASM_STORE16_OFFSET`:
    same with offset=4) and 10 new tests under a new P32 section
    (2 compile + 1 `linear_mem` present + 2 reasoning interpreter
    no-trap for load16_u; 2 compile + 1 `linear_mem` present + 2
    reasoning interpreter no-trap for store16).
  - Created `bench/wasm-btor2/corpus/seed/0024-store16-no-trap/module.wasm`
    — 46-byte WASM module: no params, no results, 1 initial page (no
    max), body `i32.const 0; i32.const 42; i32.store16 align=0
    offset=0; end`, exported as `main`.
    SHA-256: `fa0ba466bccee0660db7d1126497428d7c3337fac064255c0f6d2aab4c619d4c`.
  - Created `bench/wasm-btor2/corpus/seed/0024-store16-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8, task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0024.py` — 17
    tests: file-shape checks, spec round-trip, decoder
    instruction-sequence validation, decoder memory-section check
    (1 initial page, no max), translation compiles, BTOR2 parseable,
    `linear_mem` present in flattened BTOR2, and reasoning interpreter
    confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 875 passed, 0
  failed (previously 848 passed, 0 failed; +27 new tests: 10
  translation + 17 seed).
- **Next iteration's planned work**: P33 — `i32.load16_s` (0x2E),
  the sign-extending 16-bit load. Read 2 bytes little-endian from
  `linear_mem`; concat to bv16; sign-extend to bv32 via
  `b.sext("bv32", half, 16)`; bounds-check `ea64 + 2 > mem_bytes64`.
  A small corpus seed would complete the instruction.
- **Open BLOCKERs**: none.

---

## 2026-06-03T01:00:00Z — P31: `i32.load8_s` lowering + corpus seed 0023

- **Phase**: P31 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    `i32.load8_s` (0x2C) per-instruction lowering in `_lower_instr`:
    pop i32 address (TOS at SP-1); add static `offset` immediate (bv32
    wrap) to form effective address `ea`; bounds-check using bv64
    arithmetic (`ea64 + 1 > mem_bytes64`); on OOB set `trap_nid`; on
    in-bounds read 1 byte from `linear_mem` at `ea` via `b.read`; sign-
    extend from bv8 to bv32 via `b.sext("bv32", byte0, 24)`; push result
    via `_stack_push_i32` (TOS replaced, SP unchanged); `next_mem_nid`
    stays None (read-only). Updated module docstring for P31 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added four
    new module constants (`_BODY_LOAD8_S`, `_WASM_LOAD8_S`: no params, 1
    initial page, body `i32.const 0; i32.load8_s align=0 offset=0; drop;
    end`; `_BODY_LOAD8_S_OFFSET`, `_WASM_LOAD8_S_OFFSET`: same with
    offset=4) and 5 new tests under a new P31 section (2 compile + 1
    `linear_mem` present + 2 reasoning interpreter no-trap for load8_s).
  - Created `bench/wasm-btor2/corpus/seed/0023-load8-s-no-trap/module.wasm`
    — 45-byte WASM module: no params, no results, 1 initial page (no
    max), body `i32.const 0; i32.load8_s align=0 offset=0; drop; end`,
    exported as `main`.
    SHA-256: `9d83a588692b7fdb5f795c7fa64154ef61276a7543b53b32df802fbfff876a8d`.
  - Created `bench/wasm-btor2/corpus/seed/0023-load8-s-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8, task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0023.py` — 17
    tests: file-shape checks, spec round-trip, decoder
    instruction-sequence validation, decoder memory-section check
    (1 initial page, no max), translation compiles, BTOR2 parseable,
    `linear_mem` present in flattened BTOR2, and reasoning interpreter
    confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 848 passed, 0
  failed (previously 826 passed, 0 failed; +22 new tests: 5
  translation + 17 seed).
- **Next iteration's planned work**: P32 — `i32.load16_u` (0x2F) and
  `i32.store16` (0x3B) lowerings, the 16-bit unsigned load/store pair.
  `i32.load16_u`: read 2 bytes little-endian from `linear_mem`, zero-
  extend from bv16 to bv32; bounds-check `ea64 + 2 > mem_bytes64`.
  `i32.store16`: pop value and address; write 2 bytes little-endian;
  guard with ITE; SP decremented by 2. A small corpus seed would
  complete the pair.
- **Open BLOCKERs**: none.

---

## 2026-06-03T00:00:00Z — P30: `i32.load8_u` + `i32.store8` lowerings + corpus seed 0022

- **Phase**: P30 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    `i32.load8_u` (0x2D) per-instruction lowering in `_lower_instr`:
    pop i32 address (TOS at SP-1); add static `offset` immediate (bv32
    wrap) to form effective address `ea`; bounds-check using bv64
    arithmetic (`ea64 + 1 > mem_bytes64`); on OOB set `trap_nid`; on
    in-bounds read 1 byte from `linear_mem` at `ea` via `b.read`; zero-
    extend from bv8 to bv32 via `b.uext("bv32", byte0, 24)`; push
    result via `_stack_push_i32` (TOS replaced, SP unchanged);
    `next_mem_nid` stays None (read-only). Added `i32.store8` (0x3A)
    per-instruction lowering: pop i32 value (TOS at SP-1) and i32
    address (SP-2); add static `offset` immediate; bounds-check
    (`ea64 + 1 > mem_bytes64`); on OOB set `trap_nid`; on in-bounds
    extract low byte via `b.slice_("bv8", value, 7, 0)` and write one
    array element via `b.write("linear_mem", ctx.mem_nid, ea, byte0)`;
    guard write with `b.ite("linear_mem", in_bounds, mem1, ctx.mem_nid)`;
    set `next_mem_nid` to the ITE result; `next_sp_nid = sp_m2` (SP
    decremented by 2). Updated module docstring for P30 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added four
    new module constants (`_BODY_LOAD8_U`, `_WASM_LOAD8_U`,
    `_BODY_LOAD8_U_OFFSET`, `_WASM_LOAD8_U_OFFSET`: no params, 1 initial
    page, body `i32.const 0; i32.load8_u align=0 offset=0; drop; end`
    and same with offset=4; `_BODY_STORE8`, `_WASM_STORE8`,
    `_BODY_STORE8_OFFSET`, `_WASM_STORE8_OFFSET`: same but
    `i32.store8 align=0 offset=0` and offset=4) and 10 new tests under
    a new P30 section (2 compile + 1 `linear_mem` present + 2 reasoning
    interpreter no-trap for load8_u; 2 compile + 1 `linear_mem` present
    + 2 reasoning interpreter no-trap for store8).
  - Created `bench/wasm-btor2/corpus/seed/0022-store8-no-trap/module.wasm`
    — 46-byte WASM module: no params, no results, 1 initial page (no
    max), body `i32.const 0; i32.const 42; i32.store8 align=0 offset=0;
    end`, exported as `main`.
    SHA-256: `d8c9e0989ec944934f358b843612c0be55091ed06e00a394397df075e3540de1`.
  - Created `bench/wasm-btor2/corpus/seed/0022-store8-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8, task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0022.py` — 18
    tests: file-shape checks, spec round-trip, decoder
    instruction-sequence validation, decoder memory-section check
    (1 initial page, no max), translation compiles, BTOR2 parseable,
    `linear_mem` present in flattened BTOR2, and reasoning interpreter
    confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 826 passed, 0
  failed (previously 798 passed, 0 failed; +28 new tests: 10
  translation + 18 seed).
- **Next iteration's planned work**: P31 — `i32.load8_s` (0x2C)
  lowering. This is the sign-extending 8-bit load: read 1 byte from
  `linear_mem`, sign-extend to bv32 via `b.sext("bv32", byte0, 24)`.
  Bounds-check is identical to `i32.load8_u` (1 byte). No new state
  variable or structural change; only the extension operation differs.
  A small corpus seed exercising an in-bounds load (no trap) would
  complete the 8-bit load pair. Optionally bundle `i32.load16_u`
  (0x2F) and `i32.store16` (0x3B) as the 16-bit width pair in the
  same iteration.
- **Open BLOCKERs**: none.

---

## 2026-06-02T01:00:00Z — P29: `i32.store` lowering + corpus seed 0021

- **Phase**: P29 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    `i32.store` (0x36) per-instruction lowering in `_lower_instr`:
    pop i32 value (TOS at SP-1) and i32 address (SP-2); add static
    `offset` immediate (bv32 wrap) to address to form effective address
    `ea`; bounds-check using bv64 arithmetic (same as `i32.load`); on
    OOB set `trap_nid`; on in-bounds extract 4 bytes little-endian
    (`byte0=value[7:0]` .. `byte3=value[31:24]`) and chain four
    `b.write("linear_mem", ...)` calls to produce `mem4`; guard the
    write with `b.ite("linear_mem", in_bounds, mem4, ctx.mem_nid)` so
    OOB traps leave `linear_mem` unchanged; set `next_mem_nid` to the
    ITE result; `next_sp_nid = sp_m2` (SP decremented by 2, both
    operands consumed, no push); traps if module has no memory section.
    This is the first instruction that sets `next_mem_nid`, exercising
    the dispatch ITE tree and `emit_binding` `next` path for
    `linear_mem`. Updated module docstring for P29 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added two
    new module constants (`_BODY_STORE_I32`, `_WASM_STORE_I32`: no
    params, 1 initial page, body `i32.const 0; i32.const 42; i32.store
    align=2 offset=0; end`; `_BODY_STORE_I32_OFFSET`,
    `_WASM_STORE_I32_OFFSET`: same but offset=4) and 5 new tests under
    a new P29 section (2 compile, 1 `linear_mem` state-var present,
    2 reasoning-interpreter no-trap).
  - Created `bench/wasm-btor2/corpus/seed/0021-store-i32-no-trap/module.wasm`
    — 46-byte WASM module: no params, no results, 1 initial page (no
    max), body `i32.const 0; i32.const 42; i32.store align=2 offset=0;
    end`, exported as `main`.
    SHA-256: `143c54d907fc83372bbe2e2847bcbc21bac54486d6b83d8a8e57429825a464fc`.
  - Created `bench/wasm-btor2/corpus/seed/0021-store-i32-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8, task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0021.py` — 18
    tests: file-shape checks, spec round-trip, decoder
    instruction-sequence validation, decoder memory-section check
    (1 initial page, no max), translation compiles, BTOR2 parseable,
    `linear_mem` present in flattened BTOR2, and reasoning interpreter
    confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 798 passed, 0
  failed (previously 775 passed, 0 failed; +23 new tests: 5
  translation + 18 seed).
- **Next iteration's planned work**: P30 — `i32.load8_u` (0x2D) and
  `i32.store8` (0x3A) lowerings + corpus seed 0022. These are the
  8-bit variants of the load/store pair: `i32.load8_u` reads one byte
  from `linear_mem` and zero-extends to bv32; `i32.store8` extracts
  the low byte of a bv32 value and writes it to `linear_mem`. A corpus
  seed exercising an in-bounds 8-bit store/load round-trip (no trap)
  would validate both together. Alternatively, P30 could focus on
  `i32.load8_s` (sign-extend variant) first since it requires a
  `sext` rather than `uext`, which adds a small but distinct lowering
  path. Recommend `i32.load8_u` + `i32.store8` as the natural
  unsigned-width-extension pair.
- **Open BLOCKERs**: none.

---

## 2026-06-02T00:00:00Z — P28: `i32.load` lowering + corpus seed 0020

- **Phase**: P28 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    `i32.load` (0x28) per-instruction lowering in `_lower_instr`:
    pop i32 address from TOS; add static `offset` immediate (bv32 wrap);
    bounds-check using bv64 arithmetic (`ea64 + 4 > mem_size_pages * 65536`)
    to avoid 32-bit overflow when `mem_size == 65536`; on OOB set `trap_nid`;
    on in-bounds read 4 bytes (`b0`–`b3`) from `linear_mem` and concat
    little-endian via bv24 intermediate (`concat(b3b2, b1)`) to produce
    bv32 result; `_stack_push_i32` TOS-replace (SP unchanged). Traps
    if module has no memory section (`mem_info is None`).
    Added new `linear_mem` `Array[bv32, bv8]` state variable to
    `EmitContext` (`mem_nid`, `next_mem_expr`), `InstrLowering`
    (`next_mem_nid`), `emit_header` (sort declaration), `emit_machine`
    (state declaration, no `init` → symbolic), `emit_dispatch` (ITE
    tree over future store lowerings, defaults to identity), and
    `emit_binding` (`next` binding). Updated module docstring for P28
    scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added two
    new module constants (`_BODY_LOAD_I32`, `_WASM_LOAD_I32`: no params,
    1 initial page, body `i32.const 0; i32.load align=2 offset=0; drop; end`;
    `_BODY_LOAD_I32_OFFSET`, `_WASM_LOAD_I32_OFFSET`: same but offset=4)
    and 5 new tests under a new P28 section (2 compile, 1 `linear_mem`
    state-var present, 2 reasoning-interpreter no-trap).
  - Created `bench/wasm-btor2/corpus/seed/0020-memory-grow-no-trap/module.wasm`
    — 45-byte WASM module: no params, no results, 1 initial page max 4 pages,
    body `i32.const 1; memory.grow; drop; end`, exported as `main`.
    SHA-256: `885f91911808d2686f058fc59f64e528a8b495ddbab319acae9f607b50b67756`.
  - Created `bench/wasm-btor2/corpus/seed/0020-memory-grow-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8,
    task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0020.py` — 18 tests:
    file-shape checks, spec round-trip, decoder instruction-sequence
    validation, decoder memory-section check (1 initial page, max 4),
    translation compiles, BTOR2 parseable, `mem_size` present in flattened
    BTOR2, and reasoning interpreter confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 775 passed, 0 failed
  (previously 752 passed, 0 failed; +23 new tests: 5 translation + 18 seed).
- **Next iteration's planned work**: P29 — `i32.store` (0x36) lowering and
  corpus seed 0021 exercising an in-bounds store (no trap). `i32.store` writes
  4 bytes to `linear_mem` at the effective address (little-endian), setting
  `next_mem_nid = b.write(...)` for the ITE dispatch tree. Bounds check is
  identical to `i32.load`. This completes the read/write pair for 32-bit
  integer memory access and exercises the `next_mem_nid` path in dispatch and
  binding for the first time.
- **Open BLOCKERs**: none.

---

## 2026-06-01T01:00:00Z — P27: `memory.size` + `memory.grow` lowerings + corpus seed 0019

- **Phase**: P27 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added two
    per-instruction lowerings in `_lower_instr`:
    `memory.size` (0x3F): push `mem_size_nid` (bv32) to stack, SP++;
    read-only, no transition of `mem_size`; traps if module has no memory section.
    `memory.grow` (0x40): pop delta (i32, unsigned) from TOS; compute
    `new_size = mem_size + delta` (bv32); success iff no unsigned overflow
    (`new_size ≥ mem_size` unsigned) AND `new_size ≤ max_pages` (constant
    from `memories[0].limits.max` if set, else 65536); on success push old
    `mem_size` and set `mem_size := new_size`; on failure push 0xFFFFFFFF
    (-1 as i32), `mem_size` unchanged; SP unchanged (TOS replaced); not a trap.
    Both opcodes were already decoded.
    Added new `mem_size` bv32 state variable to `EmitContext`
    (`mem_size_nid`, `next_mem_size_expr`), `InstrLowering`
    (`next_mem_size_nid`), `emit_machine` (state declaration), `emit_init`
    (initialized to `memories[0].limits.min` or 0), `emit_dispatch` (ITE
    tree over `memory.grow` lowerings), and `emit_binding` (`next` binding).
    Updated module docstring for P27 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added
    `_make_wasm_mem` helper (builds WASM binaries that include a memory
    section), 2 new module constants (`_BODY_MEMORY_SIZE`, `_WASM_MEMORY_SIZE`:
    no params, 2 initial pages, body `memory.size; drop; end`; `_BODY_MEMORY_GROW`,
    `_WASM_MEMORY_GROW`: no params, 1 initial page, max 4 pages, body
    `i32.const 1; memory.grow; drop; end`), and 6 new tests under a new P27
    section (2 compile, 2 `mem_size` state-var present, 2 reasoning-interpreter
    no-trap).
  - Created `bench/wasm-btor2/corpus/seed/0019-memory-size-no-trap/module.wasm`
    — 42-byte WASM module: no params, no results, 2 initial pages (no max),
    body `memory.size; drop; end`, exported as `main`.
    SHA-256: `722cbe184661e71ddd8ea131ec64a8f51450631a4701b4d874c6c4e013ed2ce6`.
  - Created `bench/wasm-btor2/corpus/seed/0019-memory-size-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8,
    task_class `memory-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0019.py` — 18 tests:
    file-shape checks, spec round-trip, decoder instruction-sequence
    validation, decoder memory-section check (2 initial pages, no max),
    translation compiles, BTOR2 parseable, `mem_size` present in flattened
    BTOR2, and reasoning interpreter confirms no-trap.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 752 passed, 0 failed
  (previously 728 passed, 0 failed; +24 new tests: 6 translation + 18 seed).
- **Next iteration's planned work**: P28 — `memory.grow` corpus seed (0020)
  exercising the grow path with a bounded max, plus the first `i32.load`
  (0x28) lowering to begin the memory-load instruction group. `memory.grow`
  modeling is now present in the translator; a corpus seed that exercises the
  grow/no-grow ITE branch in BMC would strengthen the corpus. Alternatively,
  `i32.load`/`i32.store` are the natural next group to open the linear-memory
  access path (currently both fall through to the unsupported trap branch).
  Recommend `i32.load` as P28 since it is read-only and simpler than `store`.
- **Open BLOCKERs**: none.

---

## 2026-06-01T00:00:00Z — P26: `local.set` + `local.tee` isolated tests + corpus seed 0018

- **Phase**: P26 complete.
- **What changed**:
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added 2 new module
    constants (`_BODY_LOCAL_SET`, `_WASM_LOCAL_SET`: two i32 params, body
    `local.get 1; local.set 0; end`; `_BODY_LOCAL_TEE`, `_WASM_LOCAL_TEE`:
    one i32 param, body `local.get 0; local.tee 0; drop; end`) and 4 new
    tests (2 compile, 2 reasoning-interpreter no-trap) under a new P26 section.
    No changes to `layers.py` — implementations of `local.set` (0x21) and
    `local.tee` (0x22) were already present from earlier phases; P26 adds the
    missing isolated test coverage.
  - Created `bench/wasm-btor2/corpus/seed/0018-local-set-no-trap/module.wasm`
    — 39-byte WASM module: one i32 param, no results, body
    `i32.const 10; local.set 0; end`, exported as `main`.
    SHA-256: `0e2c54f55f5a92e366a8b7b367856f51278a64d26675f7b402fe33d671b08d1a`.
  - Created `bench/wasm-btor2/corpus/seed/0018-local-set-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8,
    task_class `local-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0018.py` — 17 tests:
    file-shape checks, spec round-trip, decoder instruction-sequence
    validation, translation compiles, `ite` present in flattened BTOR2
    (conditional local-write lowering), and reasoning interpreter confirms
    no-trap (param value irrelevant; constant 10 overwrites it).
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 728 passed, 0 failed
  (previously 707 passed, 0 failed; +21 new tests: 4 translation + 17 seed).
- **Next iteration's planned work**: P27 — `memory.size` (0x3F) and
  `memory.grow` (0x40) to begin the MVP memory instruction set. Both opcodes
  are already decoded. `memory.size` pushes the current page count as i32;
  `memory.grow` pops a delta, grows memory (or traps if exceeds max), pushes
  old page count (-1 on failure). Recommend tackling `memory.size` first as
  it is read-only and simpler; `memory.grow` can follow in P28 since it
  requires modeling the memory-size state variable's transition.
- **Open BLOCKERs**: none.

---

## 2026-05-31T04:00:00Z — P25: `select` instruction + corpus seed 0017

- **Phase**: P25 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added one
    per-instruction lowering in `_lower_instr`:
    `select` (ternary; pop i32 `cond` at sp-1, `val2` at sp-2, `val1` at
    sp-3; `cond_bv1 = neq(cond_bv32, bv32(0))`; `result = ite("bv64",
    cond_bv1, val1, val2)`; write result to sp-3 via raw `b.write("stack",
    ...)`; SP = sp-2). Opcode 0x1B was already decoded. Updated module
    docstring to describe P25 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added 4 new
    tests (1 compile, 1 contains-ite, 2 reasoning-interpreter no-trap) and
    2 new module constants (`_BODY_SELECT`, `_WASM_SELECT`).
  - Created `bench/wasm-btor2/corpus/seed/0017-select-no-trap/module.wasm`
    — 42-byte WASM module: no params, no results, body
    `i32.const 10; i32.const 20; i32.const 1; select; drop; end`,
    exported as `main`.
    SHA-256: `766163fbe3e1bc2dba998342c508824fed428a027fb95bccba848618ad615a00`.
  - Created `bench/wasm-btor2/corpus/seed/0017-select-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8,
    task_class `select-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0017.py` — 17 tests:
    file-shape checks, spec round-trip, decoder instruction-sequence
    validation, translation compiles, `ite` present in flattened BTOR2,
    and reasoning interpreter confirms no-trap (no params; empty binding).
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 707 passed, 0 failed
  (previously 686 passed, 0 failed; +21 new tests: 4 translation + 17 seed).
- **Next iteration's planned work**: P26 — next natural groups are
  `memory.size` (0x3F) and `memory.grow` (0x40) to complete the MVP memory
  instruction set, OR `local.set` (0x21) and `local.tee` (0x22) to round
  out the local-variable instruction group. Recommend `local.set` + `local.tee`
  as P26 since both are unary/no-trap and complement the already-landed
  `local.get` (0x20), completing local variable support before memory ops.
- **Open BLOCKERs**: none.

---

## 2026-05-31T00:00:00Z — P24: i64 comparison instructions + corpus seed 0016

- **Phase**: P24 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added eleven
    per-instruction lowerings in `_lower_instr`:
    `i64.eqz` (unary: read bv64 TOS at sp-1; compare with bv64 zero via
    `_comparison_nid(EQ, operand, const("bv64", 0))`; `uext("bv32", cmp, 31)`;
    write back in-place via `_stack_push_i32`; SP unchanged);
    `i64.eq`, `i64.ne`, `i64.lt_s`, `i64.lt_u`, `i64.gt_s`, `i64.gt_u`,
    `i64.le_s`, `i64.le_u`, `i64.ge_s`, `i64.ge_u` (binary: read bv64 rhs at
    sp-1, lhs at sp-2; `_comparison_nid` with the appropriate Comparison enum;
    `uext("bv32", cmp, 31)`; push i32 result at sp-2 via `_stack_push_i32`;
    SP = sp-1). Opcodes 0x50–0x5A were already decoded. Updated module docstring
    to describe P24 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added 19 new tests
    (11 compile, 4 contains-op/uext, 4 reasoning-interpreter no-trap) and 11
    new module constants (`_BODY_I64_EQZ`, `_BODY_I64_EQ`, …, `_BODY_I64_GE_U`
    and corresponding `_WASM_*`).
  - Created `bench/wasm-btor2/corpus/seed/0016-i64-lt-s-no-trap/module.wasm`
    — 40-byte WASM module: no params, no results, body
    `i64.const 10; i64.const 5; i64.lt_s; drop; end`, exported as `main`.
    SHA-256: `f38f58079185ff2916942e62636e4850500218412fb15465a25b80fcb09ed344`.
  - Created `bench/wasm-btor2/corpus/seed/0016-i64-lt-s-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8,
    task_class `cmp-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0016.py` — 17 tests:
    file-shape checks, spec round-trip, decoder instruction-sequence
    validation, translation compiles, `slt` present in flattened BTOR2,
    and reasoning interpreter confirms no-trap (no params; empty binding).
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 686 passed, 0 failed
  (previously 650 passed, 0 failed; +36 new tests: 19 translation + 17 seed).
- **Next iteration's planned work**: P25 — add `i32.eqz` is already done
  (P11); next natural group is `i64.extend_i32_s` (0xAC) — sign-extending
  an i32 to i64 (signed variant of the existing `i64.extend_i32_u` at 0xAD),
  plus `f32`/`f64` stub stubs OR move to `select` instruction (0x1B) and
  `memory.size`/`memory.grow` (0x3F/0x40) to round out the MVP instruction
  set. Recommend `i64.extend_i32_s` + `select` as the P25 pair since both
  are small, well-scoped, and have no trap semantics.
- **Open BLOCKERs**: none.

---

## 2026-05-30T20:00:00Z — P23: `i64.clz` + `i64.ctz` + `i64.popcnt` + corpus seed 0015

- **Phase**: P23 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added three
    helper functions (`_clz64_nid`, `_ctz64_nid`, `_popcnt64_nid`) and three
    per-instruction lowerings in `_lower_instr`:
    `i64.clz` (read bv64 TOS at sp-1; 64-deep ITE priority encoder, MSB wins;
    `result = ite(bit63, 0, ite(bit62, 1, ..., ite(bit0, 63, 64)))`; written
    back in-place, SP unchanged);
    `i64.ctz` (same pattern, LSB wins:
    `ite(bit0, 0, ite(bit1, 1, ..., ite(bit63, 63, 64)))`);
    `i64.popcnt` (sum of 64 zero-extended single-bit slices, each
    `uext("bv64", bit_k, 63)` added to accumulator).
    Opcodes 0x79–0x7B were already decoded. Updated module docstring to
    describe P23 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added 11 new
    tests (3 compile, 4 contains-op/ite, 4 reasoning-interpreter no-trap)
    and 6 new module constants (`_BODY_I64_CLZ`, `_BODY_I64_CTZ`,
    `_BODY_I64_POPCNT` and corresponding `_WASM_*`).
  - Created `bench/wasm-btor2/corpus/seed/0015-i64-clz-no-trap/module.wasm`
    — 38-byte WASM module: no params, no results, body
    `i64.const 10; i64.clz; drop; end`, exported as `main`.
    SHA-256: `9b2c7349e5491ce22744f3a24f785a661df11d2b0e80a7494444ca3816dbf3ac`.
  - Created `bench/wasm-btor2/corpus/seed/0015-i64-clz-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8.
    task_class `clz-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0015.py` — 17 tests:
    file-shape checks, spec round-trip, decoder instruction-sequence
    validation, translation compiles, `ite` present in flattened BTOR2,
    and reasoning interpreter confirms no-trap (no params; empty binding).
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 650 passed, 0 failed
  (previously 622 passed, 0 failed; +28 new tests: 11 translation + 17 seed).
- **Next iteration's planned work**: P24 — add `i64.eqz`, `i64.eq`, `i64.ne`,
  `i64.lt_s`, `i64.lt_u`, `i64.gt_s`, `i64.gt_u`, `i64.le_s`, `i64.le_u`,
  `i64.ge_s`, `i64.ge_u` (i64 comparison instructions returning i32 bv1
  results, analogous to P10 i32 comparisons).
- **Open BLOCKERs**: none.

---

## 2026-05-29T20:00:00Z — P22: `i64.div_s` + `i64.div_u` + `i64.rem_s` + `i64.rem_u` + corpus seed 0014

- **Phase**: P22 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added four
    per-instruction lowerings in `_lower_instr`:
    `i64.div_s` (read bv64 rhs at sp-1, lhs at sp-2; `zero_div = eq(rhs, 0)`;
    `overflow = and_(eq(lhs, 0x8000000000000000), eq(rhs, ones("bv64")))`;
    `trap_cond = or_(zero_div, overflow)`; ITE on trap_cond muxes pc, sp,
    stack, and trap flag; result `sdiv("bv64", lhs, rhs)` written only on
    the non-trap branch);
    `i64.div_u` (same pattern, `trap_cond = eq(rhs, 0)`, `udiv("bv64", ...)`);
    `i64.rem_s` (same, only zero-divisor trap, `srem("bv64", ...)`);
    `i64.rem_u` (same, `urem("bv64", ...)`).
    Opcodes 0x7F–0x82 were already decoded. Updated module docstring to
    describe P22 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added 15 new
    tests (4 compile, 4 contains-op, 1 ite-for-trap, 1 nonzero-no-bad,
    3 zero-divisor-bad, 1 INT64_MIN/-1-overflow-bad, 1 div_s_overflow)
    and 5 new module constants (`_BODY_I64_DIV_S`, `_BODY_I64_DIV_U`,
    `_BODY_I64_REM_S`, `_BODY_I64_REM_U`, `_BODY_I64_DIV_S_OVERFLOW` and
    corresponding `_WASM_*`).
  - Created `bench/wasm-btor2/corpus/seed/0014-i64-div-no-trap/module.wasm`
    — 40-byte WASM module: no params, no results, body
    `i64.const 10; i64.const 2; i64.div_u; drop; end`, exported as `main`.
    SHA-256: `59a5e007851dcc6f38a7f64b65958ae7460bfc02d4f6fcb3de51cc5d99631226`.
  - Created `bench/wasm-btor2/corpus/seed/0014-i64-div-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8.
    task_class `div-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0014.py` — 17 tests:
    file-shape checks, spec round-trip, decoder instruction-sequence
    validation, translation compiles, `udiv` present in flattened BTOR2,
    and reasoning interpreter confirms no-trap (no params; empty binding).
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 622 passed, 0 failed
  (previously 590 passed, 0 failed; +32 new tests: 15 translation + 17 seed).
- **Next iteration's planned work**: P23 — add `i64.clz`, `i64.ctz`,
  `i64.popcnt` (unary, no trap, bv64 ITE encoders analogous to
  `i32.clz`/`i32.ctz`/`i32.popcnt` from P8).
- **Open BLOCKERs**: none.

---

## 2026-05-29T00:00:00Z — P21: `i64.and` + `i64.or` + `i64.xor` + `i64.shl` + `i64.shr_s` + `i64.shr_u` + corpus seed 0013

- **Phase**: P21 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added six
    per-instruction lowerings in `_lower_instr`:
    `i64.and` (read bv64 rhs at sp-1, lhs at sp-2, `and_("bv64", lhs, rhs)`,
    write to sp-2, sp--);
    `i64.or` (same with `or_("bv64", lhs, rhs)`);
    `i64.xor` (same with `xor("bv64", lhs, rhs)`);
    `i64.shl` (mask count = `and_("bv64", rhs, const("bv64", 63))`,
    `sll("bv64", lhs, count)`, write to sp-2, sp--);
    `i64.shr_s` (same mask, `sra("bv64", lhs, count)`);
    `i64.shr_u` (same mask, `srl("bv64", lhs, count)`).
    Opcodes 0x83–0x88 were already decoded. Updated module docstring to
    describe P21 scope.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added 18 new
    tests (3 compile-bitwise, 3 contains-op-bitwise, 3 compile-shift,
    3 contains-op-shift, 1 mask-explicit, 5 reasoning-interpreter no-trap)
    and 12 new module constants
    (`_BODY_I64_AND`, `_BODY_I64_OR`, `_BODY_I64_XOR`, `_BODY_I64_SHL`,
    `_BODY_I64_SHR_S`, `_BODY_I64_SHR_U` and corresponding `_WASM_*`).
  - Created `bench/wasm-btor2/corpus/seed/0013-i64-bitwise-shift-no-trap/module.wasm`
    — 40-byte WASM module: no params, no results, body
    `i64.const 0x0F; i64.const 0x07; i64.and; drop; end`, exported as `main`.
    SHA-256: `7cc04638ef66e261acffb111d9c1c8728147a0ff9b1a0ec0cd4fbc22d57fcf37`.
  - Created `bench/wasm-btor2/corpus/seed/0013-i64-bitwise-shift-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8.
    task_class `bitwise-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0013.py` — 17 tests:
    file-shape checks, spec round-trip, decoder instruction-sequence
    validation, translation compiles, `and` present in flattened BTOR2,
    and reasoning interpreter confirms no-trap (no params; empty binding).
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 590 passed, 0 failed
  (previously 555 passed, 0 failed; +35 new tests: 18 translation + 17 seed).
- **Next iteration's planned work**: P22 — add `i64.div_s`, `i64.div_u`,
  `i64.rem_s`, `i64.rem_u` following the P9 i32 div/rem pattern (trap on
  divide-by-zero; `i64.div_s` also traps on INT64_MIN / -1).  Alternatively,
  add `i64.clz`, `i64.ctz`, `i64.popcnt` (unary, no trap, bv64 ITE encoders
  analogous to i32.clz/ctz from P8).
- **Open BLOCKERs**: none.

---

## 2026-05-28T01:00:00Z — P20: `i64.extend8_s` + `i64.extend16_s` + `i64.extend32_s` + corpus seed 0012

- **Phase**: P20 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added three
    per-instruction lowerings in `_lower_instr`:
    `i64.extend8_s` (read bv64 TOS, `slice("bv8", val, 7, 0)`, `sext("bv64",
    slice8, 56)`, write back in-place; SP unchanged);
    `i64.extend16_s` (read bv64 TOS, `slice("bv16", val, 15, 0)`, `sext("bv64",
    slice16, 48)`, write back in-place; SP unchanged);
    `i64.extend32_s` (read bv64 TOS, `slice("bv32", val, 31, 0)`, `sext("bv64",
    slice32, 32)`, write back in-place; SP unchanged).
    Updated module docstring to describe P20 scope. Opcodes 0xC2–0xC4 were
    already decoded in P19; only the lowerings are new.
  - Updated `gurdy/pairs/wasm_btor2/source_interp/interpreter.py` — added
    concrete-execution handlers for all three new ops:
    `i64.extend8_s`: `(v & 0xFF) - 0x100 if (v & 0xFF) >= 0x80 else (v & 0xFF)`
    masked to bv64; `i64.extend16_s`: analogous for 16-bit; `i64.extend32_s`:
    uses `_s32(v)` helper to sign-extend 32 → 64 bits.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added 13 new
    tests (4 compile, 1 flattened-parseable, 3 library sext checks, 5
    reasoning-interpreter no-trap) and 4 new module constants
    (`_WASM_I64_EXTEND8_S`, `_WASM_I64_EXTEND16_S`, `_WASM_I64_EXTEND32_S`,
    `_WASM_I64_EXTEND_ALL`).
  - Created `bench/wasm-btor2/corpus/seed/0012-i64-extend8-extend16-extend32-no-trap/module.wasm`
    — 40-byte WASM module: no params, no results, body
    `i64.const 0; i64.extend8_s; i64.extend16_s; i64.extend32_s; drop; end`,
    exported as `main`.
    SHA-256: `43b8f20b810c784f7372429beddf8e4304a98d564ad5379f3e892a41e7d33b58`.
  - Created `bench/wasm-btor2/corpus/seed/0012-i64-extend8-extend16-extend32-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8.
    task_class `sign-extension-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0012.py` — 18 tests:
    file-shape checks, spec round-trip, decoder instruction-sequence
    validation, translation compiles, `sext` and `slice` present in flattened
    BTOR2, and reasoning interpreter confirms no-trap (no params; empty
    binding).
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 555 passed, 0 failed
  (previously 524 passed, 0 failed; +31 new tests: 13 translation + 18 seed).
- **Next iteration's planned work**: P21 — add `i64.and`, `i64.or`, `i64.xor`,
  `i64.shl`, `i64.shr_s`, `i64.shr_u` bitwise/shift lowerings (same pattern as
  P10's i32 variants but on bv64 TOS directly).  Alternatively, add i64 comparisons
  (`i64.eq`, `i64.ne`, `i64.lt_s`, etc.) following the P11 pattern with bv64
  operands.
- **Open BLOCKERs**: none.

---

## 2026-05-28T00:00:00Z — P19: `i32.extend8_s` + `i32.extend16_s` + corpus seed 0011

- **Phase**: P19 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/source/decoder.py` — registered five
    sign-extension operator opcodes (WASM 1.1): `0xC0` (`i32.extend8_s`),
    `0xC1` (`i32.extend16_s`), `0xC2` (`i64.extend8_s`), `0xC3`
    (`i64.extend16_s`), `0xC4` (`i64.extend32_s`).  The full family is
    registered even though only `i32.extend8_s` and `i32.extend16_s` are
    lowered this iteration; the rest will trap (unsupported) until lowered.
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added two
    per-instruction lowerings in `_lower_instr`:
    `i32.extend8_s` (pop bv32 TOS, `slice("bv8", val, 7, 0)`, `sext("bv32",
    slice8, 24)`, push in-place; SP unchanged);
    `i32.extend16_s` (pop bv32 TOS, `slice("bv16", val, 15, 0)`, `sext("bv32",
    slice16, 16)`, push in-place; SP unchanged).
    Updated module docstring to describe P19 scope.
  - Updated `gurdy/pairs/wasm_btor2/source_interp/interpreter.py` — added
    concrete-execution handlers for both new ops:
    `i32.extend8_s`: `(v & 0xFF) - 0x100 if (v & 0xFF) >= 0x80 else (v & 0xFF)`,
    masked to bv32; `i32.extend16_s`: analogous for 16-bit.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added 13 new
    tests (3 compile, 1 flattened-parseable, 4 library-layer node checks,
    5 reasoning interpreter no-trap concrete inputs) and 3 new module
    constants (`_WASM_EXTEND8_S`, `_WASM_EXTEND16_S`, `_WASM_EXTEND8_THEN_16`).
  - Created `bench/wasm-btor2/corpus/seed/0011-i32-extend8-extend16-no-trap/module.wasm`
    — 40-byte WASM module: one i32 param, one i32 result, body
    `local.get 0; i32.extend8_s; i32.extend16_s; end`, exported as `main`.
    SHA-256: `e9ea066864785afc0f59d7ad4690299124ded2939d5c198c24d71e3a0954e340`.
  - Created `bench/wasm-btor2/corpus/seed/0011-i32-extend8-extend16-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8.
    task_class `sign-extension-semantics`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0011.py` — 20 tests:
    file-shape checks, spec round-trip, translation compiles, `sext` and
    `slice` present in flattened BTOR2, and reasoning interpreter confirms
    no-trap for n=0, n=0x7F, n=0xFF, n=INT32_MAX.
- **Verification**: `pytest tests/pairs/wasm_btor2/` → 524 passed, 0 failed
  (previously 491 passed, 0 failed; +33 new tests: 13 translation + 20 seed).
- **Next iteration's planned work**: P20 — advance to i64 locals
  (`local.get`/`local.set`/`local.tee` for i64-typed locals) by widening the
  local state variables from bv32 to bv64 with appropriate slicing on i32
  reads.  Alternatively, add `i64.extend8_s`, `i64.extend16_s`,
  `i64.extend32_s` lowerings (already decoded; same slice+sext pattern as P19
  but bv64 targets).
- **Open BLOCKERs**: none.

---

## 2026-05-27T01:00:00Z — P18: fix `local.get` bv32→bv64 sort mismatch

- **Phase**: P18 complete.
- **What changed**:
  - Fixed `gurdy/pairs/wasm_btor2/translation/layers.py` — `local.get`
    lowering was calling `b.write("stack", ctx.stack_nid, ctx.sp_nid,
    ctx.local_nids[k])` directly, writing a bv32 local value into the
    bv64-element stack without zero-extension.  Replaced with
    `_stack_push_i32(b, ctx.stack_nid, ctx.sp_nid, ctx.local_nids[k])`,
    which uexts the bv32 value to bv64 before the write (same pattern used
    by every other i32-producing instruction since P16).  The `local.set`
    and `local.tee` lowerings were already correct (they read from the stack
    via `_stack_pop_i32` and write bv32 to the local).
- **Verification**: `pytest tests/pairs/wasm_btor2/test_solvers.py -v` → 28
  passed (previously 23 passed + 5 failures); `pytest tests/pairs/wasm_btor2/`
  → 491 passed, 0 failed (previously 486 passed, 5 pre-existing z3 failures).
- **Next iteration's planned work**: P19 — add `i32.extend8_s` and
  `i32.extend16_s` (pure i32→i32 sign-extension ops: slice low 8/16 bits,
  sext to 32).  These are the next small increment: no stack-type change
  needed, no trap semantics, and they complete the sign-extension family
  alongside the bv64 extend instructions already present.  Land corpus seed
  `0011` demonstrating the new instructions.  Alternatively, advance to
  i64 locals (`local.get`/`local.set` for i64-typed locals) by widening the
  local state variables from bv32 to bv64 with appropriate slicing on i32
  reads.
- **Open BLOCKERs**: none.

---

## 2026-05-27T00:00:00Z — P17: `i64.const` + `i64.add` + `i64.sub` + `i64.mul` + corpus seed 0010-i64-arith-no-trap

- **Phase**: P17 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added four
    per-instruction lowerings in `_lower_instr`:
    `i64.const N` (push bv64 constant to stack[sp], sp++);
    `i64.add` (pop bv64 rhs from sp-1 and lhs from sp-2 via
    `b.read("bv64", ...)`, emit `b.add("bv64", lhs, rhs)`, write result to
    sp-2, sp--);
    `i64.sub` (same pattern with `b.sub("bv64", ...)`);
    `i64.mul` (same pattern with `b.mul("bv64", ...)`).
    All four operate directly on bv64 stack elements — no uext/slice needed.
    Updated module docstring to describe P17 scope.
  - Created `bench/wasm-btor2/corpus/seed/0010-i64-arith-no-trap/module.wasm`
    — 43-byte WASM module: one i32 param, one i32 result, body
    `local.get 0; i64.extend_i32_u; i64.const 1; i64.add; i32.wrap_i64; end`,
    exported as `main`.
    SHA-256: `95c928994cf744abdcf00f3d1f62189c195c553784534668d7d92dbcf0b679aa`.
  - Created `bench/wasm-btor2/corpus/seed/0010-i64-arith-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8.
    task_class `i64-arithmetic`.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — added 14 new
    tests (4 compile, 1 flattened-parseable, 3 library-layer node checks,
    4 reasoning interpreter no-trap concrete inputs) and 4 new module
    constants (`_WASM_I64_ADD`, `_WASM_I64_SUB`, `_WASM_I64_MUL`,
    `_WASM_I64_CONST`).
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0010.py` — 20 tests:
    file-shape checks, spec round-trip, translation compiles, `add` and
    `uext` present in flattened BTOR2, and reasoning interpreter confirms
    no-trap for n=0, n=1, n=42, n=INT32_MAX.
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0010.py -v` → 34 new tests
  passed; `pytest tests/pairs/wasm_btor2/` → 486 passed, 5 pre-existing
  z3 solver failures (same `local.get` bv32→bv64 sort mismatch present
  since P16; unchanged from P16).
- **Next iteration's planned work**: P18 — fix the pre-existing `local.get`
  sort mismatch (write bv64 instead of bv32 to the bv64 stack by uext-ing
  the local value in the `local.get` lowering; same pattern as
  `_stack_push_i32`). This will unblock the z3 solver tests. Then add
  `i64.extend_i32_u/s` support for local variables so locals can hold
  i64 values in future iterations. Alternatively, add `i64.store`/`i64.load`
  if memory is in scope, or advance to `local.get`/`set` i64 locals.
  A simpler alternative: add `i32.extend8_s` and `i32.extend16_s`
  (pure i32→i32 sign-extension ops) as the next small increment.
- **Open BLOCKERs**: none.

---

## 2026-05-26T00:00:00Z — P16: stack widening bv32→bv64 + `i64.extend_i32_u/s` + `i32.wrap_i64` + corpus seed 0009-extend-wrap-no-trap

- **Phase**: P16 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — widened the
    value stack element sort from `Array[bv8, bv32]` to `Array[bv8, bv64]`
    in `emit_header`, `emit_machine`, and `emit_binding`.  Added two helpers:
    `_stack_pop_i32(b, stack_nid, addr_nid)` (reads bv64, slices [31:0] →
    bv32) and `_stack_push_i32(b, stack_nid, addr_nid, val_bv32)` (uexts to
    bv64, writes).  Replaced all 24 `b.read("bv32", ctx.stack_nid, …)` calls
    with `_stack_pop_i32` and all 24 `b.write("stack", ctx.stack_nid, …)` calls
    with `_stack_push_i32` (ITE variants included).  Added three per-instruction
    lowerings: `i64.extend_i32_u` (pop bv32, uext to bv64, write bv64 in-place),
    `i64.extend_i32_s` (pop bv32, sext to bv64, write bv64 in-place),
    `i32.wrap_i64` (read bv64 directly, slice [31:0] to bv32, push via
    `_stack_push_i32`).  SP is unchanged for all three (in-place result).
    Updated module docstring to describe P16 scope.
  - Created `bench/wasm-btor2/corpus/seed/0009-extend-wrap-no-trap/module.wasm`
    — 40-byte WASM module: one i32 param, one i32 result, body
    `local.get 0; i64.extend_i32_u; i32.wrap_i64; end`, exported as `main`.
    SHA-256: `e740f914078ebc3c1574c1df2fd40d2d0d4aafc366705d3fa9483e9bb0bdf1d2`.
  - Created `bench/wasm-btor2/corpus/seed/0009-extend-wrap-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8.
    task_class `type-conversion-semantics`.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 10 new tests:
    `i64.extend_i32_u` compile, `i64.extend_i32_s` compile, `i32.wrap_i64`
    compile, extend+wrap flattened parseable, `uext` in library layer for
    extend_u, `sext` in library layer for extend_s, `slice` in library layer
    for wrap, reasoning interpreter extend_u no-trap for n=0 and n=0xFFFFFFFF,
    reasoning interpreter extend_s no-trap for n=0xFFFFFFFF (sign-extension).
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0009.py` — 20 tests:
    file-shape checks, spec round-trip, translation compiles, `uext` and
    `slice` present in flattened BTOR2, and reasoning interpreter confirms
    no-trap for n=0, n=1, n=42, n=INT32_MAX.
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0009.py -v` → 154 passed;
  `pytest tests/pairs/wasm_btor2/` → 443 passed, 16 pre-existing z3
  failures (unchanged from P15).
- **Next iteration's planned work**: P17 — add `i64.const`, `i64.add`,
  `i64.sub`, `i64.mul`, and basic i64 arithmetic.  Now that the stack
  holds bv64 elements natively, pure i64 binary ops (add/sub/mul) can be
  lowered exactly like their i32 counterparts but reading/writing bv64
  directly (no uext/slice needed).  `i64.const` pushes a 64-bit constant.
  Alternatively, add `i32.extend8_s` and `i32.extend16_s` (pure i32→i32
  sign-extension via slice+sext) as a smaller increment.  Land corpus seed
  `0010` demonstrating the new capability.
- **Open BLOCKERs**: none.

---

## 2026-05-24T00:00:00Z — P15: `call` instruction + multi-function PC linearization + corpus seed 0008-call-no-trap

- **Phase**: P15 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — extended
    `InstrLowering` with two optional fields: `next_csp_nid` (call stack
    pointer update) and `next_call_stack_nid` (call stack array update).
    Extended `EmitContext` with `csp_nid`, `call_stack_nid`,
    `func_entry_pcs` (func_idx → first global PC), `next_csp_expr`, and
    `next_call_stack_expr`. Updated `emit_header` to declare `bv4` sort
    and `call_stack` array sort (Array[bv4, bv16]). Updated `emit_machine`
    to emit two new state variables: `csp` (bv4, call stack pointer) and
    `call_stack` (Array[bv4, bv16], saved return PCs). Rewrote
    `emit_library` to linearise all local (non-import) functions into one
    PC space: entry function occupies PCs 0..len(entry_body)-1, other
    functions follow in module order; `func_entry_pcs` is populated before
    any `_lower_instr` call so `call N` can resolve the callee's entry PC.
    Added `call` per-instruction lowering: if callee exists in
    `func_entry_pcs`, saves `pc+1` to `call_stack[csp]`, increments csp,
    and jumps to callee entry PC; if callee is unknown (import or absent),
    sets trap flag. Updated `return` and function-level `end` lowerings:
    when `csp > 0` (caller present) they read the saved return address from
    `call_stack[csp-1]`, decrement csp, and jump back; when `csp == 0`
    (top-level) they self-loop and set `halted = 1` as before. Added
    dispatch ITE trees for `next_csp` (bv4) and `next_call_stack`
    (call_stack). Added `init csp = 0` in `emit_init`. Updated
    `emit_binding` to bind csp and call_stack next-state expressions.
    Updated module docstring to describe P15 scope and per-activation local
    limitation (callee locals share the entry-function local namespace;
    correct only for no-param, no-extra-local callees in P15).
  - Created `bench/wasm-btor2/corpus/seed/0008-call-no-trap/module.wasm`
    — 49-byte WASM module: two functions. func 0 (`main`, type [i32]→[i32]):
    `local.get 0; call 1; local.get 0; end`. func 1 (`helper`, type []→[]):
    `end`. Export: "main" → func 0. SHA-256:
    `0c0cecde1cef911656bc2c0b5bd210dd54f22b5a04db4107a8d323d02ff46e94`.
  - Created `bench/wasm-btor2/corpus/seed/0008-call-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound
    12. task_class `call-semantics`.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 10 new tests:
    `call` two-function compile, flattened parseable, `csp` in machine
    layer, `call_stack` in machine layer, `write` in library layer (call
    stack push), `read` in library layer (call stack pop), single-function
    regression, reasoning interpreter `call` no-trap for inputs 42, 0, and
    -1 (0xFFFFFFFF).
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0008.py` — 20 tests:
    file-shape checks, spec round-trip, translation compiles, `write` and
    `read` in flattened BTOR2, and reasoning interpreter confirms no-trap
    for n=0, n=1, n=42, n=INT32_MAX.
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0008.py -v` → 144 passed;
  `pytest tests/pairs/wasm_btor2/` → 413 passed, 16 pre-existing z3
  failures (unchanged from P14).
- **Next iteration's planned work**: P16 — add `i32.wrap_i64`,
  `i64.extend_i32_s`, `i64.extend_i32_u` type conversion instructions.
  These require widening the value stack element type from bv32 to bv64 so
  that i64 values can be stored. A pragmatic approach: change the stack
  array sort to Array[bv8, bv64] and have all existing i32 operations
  zero-extend their results to bv64 on push and truncate (low 32 bits) on
  pop. `i64.extend_i32_s/u` extend a bv32 value to bv64 via sext/uext;
  `i32.wrap_i64` truncates a bv64 value to bv32 via slice. Alternatively,
  add `i32.extend8_s` and `i32.extend16_s` (pure i32 → i32 sign-extension
  via slice + sext, no stack-type change needed) as a simpler option. Land
  corpus seed `0009` demonstrating the new capability.
- **Open BLOCKERs**: none.

---

## 2026-05-23T00:00:00Z — P14: i32.clz / i32.ctz / i32.popcnt + corpus seed 0007-clz-no-trap

- **Phase**: P14 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/builder.py` — added
    `slice_` helper method that emits a BTOR2 `slice` node extracting
    bits [hi:lo] from a bv operand. Mirrors the existing `sext`/`uext`
    helpers; named `slice_` to avoid shadowing Python's built-in.
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    three helper functions: `_clz_nid` (32-deep ITE priority encoder,
    iterates bit positions 0..31 so bit 31 is the outermost/highest-
    priority check; clz(0)=32 per spec), `_ctz_nid` (symmetric from
    LSB; iterates 31..0 so bit 0 is outermost; ctz(0)=32), `_popcnt_nid`
    (sums 32 single-bit `uext(slice(x,k,k),31)` contributions via
    sequential `add` nodes). Added three per-instruction lowerings:
    `i32.clz`, `i32.ctz`, `i32.popcnt` — each pops one bv32 operand,
    calls the corresponding helper, and writes the result back in-place
    (SP unchanged). Updated module docstring to describe P14 scope.
  - Created `bench/wasm-btor2/corpus/seed/0007-clz-no-trap/module.wasm`
    — 39-byte WASM module: one i32 param, one i32 result, body
    `local.get 0; i32.clz; end`, exported as `main`.
  - Created `bench/wasm-btor2/corpus/seed/0007-clz-no-trap/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8. task_class `bit-count-semantics`. SHA-256 of module.wasm:
    `a2261e925e7d2e01e50bcd9ed5c8ca35a39981d6cb12ec368a28080d09841745`.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 12 new
    tests: `i32.clz` compile, `i32.ctz` compile, `i32.popcnt` compile,
    `slice` in BTOR2 for clz/ctz/popcnt, `ite` in library layer for
    clz, clz flattened BTOR2 parseable, reasoning interpreter tests
    for clz(1) no-trap, clz(0x80000000) no-trap, ctz(2) no-trap,
    popcnt(7) no-trap.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0007.py` — 20
    tests: file-shape checks, spec round-trip, translation compiles,
    `slice` and `ite` present in flattened BTOR2, and reasoning
    interpreter confirms no-trap for n=0 (clz=32), n=1 (clz=31),
    n=0x80000000 (clz=0), n=0xFFFFFFFF (clz=0).
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0007.py -v` → 134 passed;
  `pytest tests/pairs/wasm_btor2/` → 383 passed, 16 pre-existing z3
  failures (unchanged from P13).
- **Next iteration's planned work**: P15 — add `call` instruction
  support for direct intra-module function calls. The simplest step:
  translate `call N` for void-result callees in the same module.
  The translator linearises all functions into a single PC space
  (function 0 occupies PCs 0..len(func0)-1, function 1 occupies
  PCs len(func0)..len(func0)+len(func1)-1, etc.); `call N` pushes
  the return address (pc+1) on a separate call-stack state array
  and jumps to the entry PC of callee N; `return` in the callee pops
  the saved return address and jumps back. Alternatively, consider
  `i32.wrap_i64` / `i64.extend_i32_s/u` type conversions if call is
  too large for one iteration. Land corpus seed `0008` demonstrating
  the new capability.
- **Open BLOCKERs**: none.

---

## 2026-05-22T00:00:00Z — P13: br_if / br branch instructions + corpus seed 0006-loop-count

- **Phase**: P13 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/source/decoder.py` — extended
    `_resolve_targets` with a second pass (pass 2) that walks the
    instruction list with a fresh label stack and pre-resolves
    `br_target` on every `br` and `br_if` instruction. For `br N` /
    `br_if N`, the pass looks N levels up in the label stack and reads
    the `br_target` already set on the enclosing `block`/`loop`/`if`
    instruction by pass 1 (loop → back-edge = the loop instruction
    itself; block/if → instruction after the matching `end`). Pass 1
    is unchanged. The decoder now sets `ins.br_target` for `br` and
    `br_if` at decode time so the translator can read it without a
    runtime label stack.
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    four per-instruction lowerings: `block` (advance PC, no-op
    structural marker), `loop` (advance PC, no-op structural marker),
    `br` (unconditional jump to `ins.br_target`, no stack effect for
    void blocks), `br_if` (pop condition bv32, emit
    `neq(condition, 0)` to get bv1 flag, ITE selecting `ins.br_target`
    if nonzero or `p+1` if zero as next PC, decrement SP by 1).
    Updated module docstring to describe P13 scope.
  - Created `bench/wasm-btor2/corpus/seed/0006-loop-count/module.wasm`
    — 63-byte WASM module: one i32 param (n), one i32 local (counter),
    body `i32.const 0; local.set 1; block; loop; local.get 1;
    local.get 0; i32.ge_u; br_if 1; local.get 1; i32.const 1;
    i32.add; local.set 1; br 0; end; end; end`, exported as `main`.
  - Created `bench/wasm-btor2/corpus/seed/0006-loop-count/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8. task_class `loop-semantics`. SHA-256 of module.wasm:
    `ac10089d6d2876101cef493ad4c53c0f2fc81c06a3b205b916c2b611aacc7a5b`.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 13 new
    tests: `br_if` compile, `br` compile, `loop_count` compile,
    `br_if` BTOR2 parseable, loop-count BTOR2 parseable, `neq` in
    library layer for `br_if`, `ite` in dispatch layer for `br_if`,
    reasoning interpreter tests for br_if nonzero exits (no trap),
    br_if zero falls through (no trap), br unconditional exit (no
    trap), loop-count n=0 (no trap), loop-count n=1 (no trap),
    loop-count n=3 (no trap).
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0006.py` — 21
    tests: file-shape checks, spec round-trip, translation compiles,
    `ite` and `neq` present in flattened BTOR2, and reasoning
    interpreter confirms no-trap for n=0, n=1, n=2, n=3.
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0006.py -v` → 122 passed;
  `pytest tests/pairs/wasm_btor2/` → 351 passed, 16 pre-existing z3
  failures (unchanged from P12).
- **Next iteration's planned work**: P14 — add `call` instruction
  support for direct function calls, enabling multi-function modules.
  The simplest step: translate `call N` where callee is in the same
  module and has no return value; the translator emits a push of the
  return address and a jump to the callee's PC range. Alternatively,
  consider `i32.clz`, `i32.ctz`, `i32.popcnt` (pure no-trap unary
  ops) if call is too large for one iteration. Land corpus seed
  `0007` demonstrating the new capability.
- **Open BLOCKERs**: none.

---

## 2026-05-20T10:00:00Z — P12: if/else/end structured control flow + corpus seed 0005-if-no-trap

- **Phase**: P12 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    per-instruction lowerings for `if` and `else`. `if` (type `[] → []`,
    no result value): pops one i32 condition, emits `neq(condition, 0)` to
    produce a bv1 flag, then emits an ITE selecting `p+1` (true branch) or
    `ins.alt` (false target from the decoder's second pass) as the next PC,
    and decrements SP by 1 to consume the condition. `else`: unconditionally
    sets next PC to `ins.br_target` (instruction after the matching `end`),
    skipping the false branch when the true branch completes. Block-level
    `end` already advanced PC by one and required no change. Updated module
    docstring to describe P12 scope.
  - Created `bench/wasm-btor2/corpus/seed/0005-if-no-trap/module.wasm` —
    41-byte WASM module: one i32 param, body `local.get 0; if (void); nop;
    end; end`, exported as `main`.
  - Created `bench/wasm-btor2/corpus/seed/0005-if-no-trap/spec.json` and
    `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8.
    task_class `if-semantics`. SHA-256 of module.wasm:
    `0857bdde309623e0a78c230e3f5b71fd43be580d2f3a5257adaf33fd0423c627`.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 9 new tests:
    `if` and `if-else` compile tests, ITE-in-dispatch and neq-in-library
    presence tests, BTOR2 parseable, and reasoning interpreter tests for
    condition=0 (skip), condition=1 (enter), condition=-1 (nonzero enter)
    on `if`, plus true-branch and false-branch tests on `if-else`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0005.py` — 21 tests:
    file-shape checks, spec round-trip, translation compiles, `ite` and
    `neq` present in flattened BTOR2, and reasoning interpreter confirms
    no-trap for condition=0, condition=1, condition=-1, condition=INT32_MAX.
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0005.py -v` → 109 passed;
  `pytest tests/pairs/wasm_btor2/` → 318 passed, 16 pre-existing z3
  failures (unchanged from P11).
- **Next iteration's planned work**: P13 — add `br_if` and `br` branch
  instructions. `br_if` pops a condition and, if nonzero, jumps to
  `ins.br_target` (the exit of the enclosing block); `br` is an
  unconditional jump to `ins.br_target`. Together these enable loop-exit
  patterns (`loop + br_if` = while) and early-exit from blocks. Land
  corpus seed `0006-loop-count` demonstrating a counted loop that never
  traps.
- **Open BLOCKERs**: none.

---

## 2026-05-20T08:00:00Z — P11: i32.eqz + 10 binary comparison instructions + corpus seed 0004-comparison-ops

- **Phase**: P11 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    per-instruction lowerings for `i32.eqz` (unary: pop 1, compare with
    zero, zero-extend bv1 result to bv32, push) and ten binary comparisons
    `i32.eq`, `i32.ne`, `i32.lt_s`, `i32.lt_u`, `i32.gt_s`, `i32.gt_u`,
    `i32.le_s`, `i32.le_u`, `i32.ge_s`, `i32.ge_u` (pop 2, compare, uext
    bv1 → bv32, push). All 11 instructions produce bv32 results (0 or 1)
    per WASM spec — not bv1. None have trap semantics. Lowerings delegate
    to the existing `_comparison_nid` helper (reusing `Comparison` enum
    and BTOR2 op mapping already present for `LocalInit` constraints) then
    emit `uext(cmp, 31)` to widen to bv32. Updated module docstring to
    describe P11 scope.
  - Created `bench/wasm-btor2/corpus/seed/0004-comparison-ops/module.wasm`
    — 42-byte WASM module: two i32 params, body `local.get 0; local.get 1;
    i32.lt_s; end`, exported as `main`.
  - Created `bench/wasm-btor2/corpus/seed/0004-comparison-ops/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`, bound 8.
    task_class `comparison-semantics`. SHA-256 of module.wasm:
    `f13ede3bedffe0c44eac493e93fe751411d91bb30125100b26ba59651539ab87`.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 24 new tests:
    11 compile tests (one per new instruction), 6 BTOR2 operator presence
    tests (slt, ult, eq, neq, and two uext presence checks), 7 reasoning
    interpreter concrete-witness tests (lt_s basic, lt_s equal, lt_s
    negative, eq same values, eqz zero, eqz nonzero, ge_u basic).
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0004.py` — 21 tests:
    file-shape checks, spec round-trip, translation compiles, `slt` and
    `uext` present in flattened BTOR2, and reasoning interpreter confirms
    no-trap for (0,0), (1,2), (-1,0), (INT32_MAX,-1), (INT32_MIN,INT32_MAX).
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0004.py -v` → 100 passed;
  `pytest tests/pairs/wasm_btor2/` → 288 passed, 16 pre-existing z3
  failures (unchanged from P10).
- **Next iteration's planned work**: P12 — add `if`/`else`/`end` structured
  control flow. The comparison instructions landing in P11 produce the
  boolean operands needed for `if`; the block stack must track nesting
  depth so `end` closes the correct scope. Start with `if`-without-else
  (type `[] → []`, no result value) and one seed task `0005-if-no-trap`
  demonstrating that a branch on a comparison never traps. `br_if` and
  `br` can follow in P13 once `if` is solid.
- **Open BLOCKERs**: none.

---

## 2026-05-20T06:00:00Z — P10: i32.and/or/xor + i32.shl/shr_s/shr_u + i32.rotl/rotr + corpus seed 0003-shift-amount-mask

- **Phase**: P10 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/builder.py` — added `sll`,
    `srl`, `sra` helper methods (symmetric with the existing arithmetic
    helpers).
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    per-instruction lowerings for `i32.and`, `i32.or`, `i32.xor` (pure
    bitwise, no trap), and `i32.shl`, `i32.shr_s`, `i32.shr_u` (shifts
    with explicit mod-32 mask: `count = and(rhs, 0x1F)` before each BTOR2
    shift node so the model-checker sees WASM semantics rather than SMT
    shift-by-large-amount = 0). Added `i32.rotl` and `i32.rotr` expressed
    as `or(sll(a, count), srl(a, 32 - count))` and
    `or(srl(a, count), sll(a, 32 - count))` respectively; the n=0 edge
    case is correct for both the evaluator (which masks shift amounts mod
    width) and z3 (which gives 0 for shift >= width): both paths yield `a`.
    Updated module docstring to describe P10 scope and the rotation
    derivation.
  - Created `bench/wasm-btor2/corpus/seed/0003-shift-amount-mask/module.wasm`
    — 42-byte WASM module: two i32 params, body `local.get 0; local.get 1;
    i32.shl; end`, exported as `main`.
  - Created `bench/wasm-btor2/corpus/seed/0003-shift-amount-mask/spec.json`
    and `task.toml` — `reach_trap`, expected verdict `unreachable`,
    bound 8. task_class `shift-semantics`. SHA-256 of module.wasm:
    `bc95fd959e3982e469ec2f856ebd8727e39094a8fcf566aee0151f0aa8d64d45`.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 25 new tests:
    compile tests for all 8 new instructions, BTOR2 operator presence tests
    (`and`, `or`, `xor`, `sll`, `sra`, `srl`), mask-explicit-in-BTOR2 test
    for `i32.shl`, rotl sll+srl presence, and reasoning-interpreter concrete
    witness tests (shl basic, shl mod-32 mask, shr_u basic, rotr basic,
    and basic).
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0003.py` — 20 tests:
    file-shape checks, spec round-trip, translation compiles, `sll` present
    in flattened BTOR2, and reasoning interpreter confirms no-trap for
    (0,0), (1,1), (5,32) mod-32 mask, (0xFFFFFFFF,31), (1,33).
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0003.py -v` → 75 passed;
  `pytest tests/pairs/wasm_btor2/` → 243 passed, 16 pre-existing z3
  failures (unchanged from P9).
- **Next iteration's planned work**: P11 — add `i32.eqz`, `i32.eq`,
  `i32.ne`, `i32.lt_s`, `i32.lt_u`, `i32.gt_s`, `i32.gt_u`, `i32.le_s`,
  `i32.le_u`, `i32.ge_s`, `i32.ge_u` comparison instructions (pure
  arithmetic, no trap semantics). These produce bv32 results (0 or 1 per
  WASM spec — not bv1) and are needed for `if`/`br_if` control flow.
  Land corpus seed `0004-comparison-ops` demonstrating that comparisons
  are zero-or-one and never trap.
- **Open BLOCKERs**: none.

---

## 2026-05-20T04:00:00Z — P9: i32.div_s/div_u/rem_s/rem_u + corpus seed 0002-div-trap

- **Phase**: P9 complete.
- **What changed**:
  - Updated `gurdy/pairs/wasm_btor2/translation/layers.py` — added
    per-instruction lowerings for `i32.div_s`, `i32.div_u`, `i32.rem_s`,
    `i32.rem_u`. Each uses ITE-based conditional trap paths: the lowering
    emits `trap_cond` (bv1) as the OR of all trap conditions for that
    instruction, then wraps `next_pc`, `next_sp`, `next_stack`, and
    `trap` in ITE trees keyed on `trap_cond`. `i32.div_s` checks both
    divisor-zero (`rhs == 0`) and signed overflow (`lhs == INT32_MIN &&
    rhs == -1`). The remaining three check divisor-zero only.
  - Fixed `gurdy/pairs/wasm_btor2/btor2/evaluator.py` — `write` was
    masking element values with `& 0xFF` (bv8 width) instead of
    storing the full bv32 value; removed the incorrect mask. This was
    a pre-existing bug exposed by the first corpus task requiring
    large stack values (INT32_MIN = 0x80000000).
  - Created `bench/wasm-btor2/corpus/seed/0002-div-trap/module.wasm` —
    42-byte WASM module: two i32 params, body `local.get 0; local.get
    1; i32.div_s; end`, exported as `main`.
  - Created `bench/wasm-btor2/corpus/seed/0002-div-trap/spec.json` and
    `task.toml` — `reach_trap`, expected verdict `reachable`, bound 8.
  - Updated `tests/pairs/wasm_btor2/test_translation.py` — 25 new
    tests: four compile tests (one per instruction), BTOR2 operator
    presence tests, ITE presence in library layer, and reasoning
    interpreter concrete-witness tests (zero divisor, INT32_MIN/-1
    overflow, non-zero divisor no-trap, for all four instructions).
  - Created `tests/pairs/wasm_btor2/test_corpus_seed_0002.py` — 19
    tests: file-shape checks, spec round-trip, translation compiles,
    `sdiv` present in flattened BTOR2, and reasoning interpreter
    confirms trap for divisor==0, INT32_MIN/-1 overflow, and non-trap
    for valid divisors.
- **Verification**: `pytest tests/pairs/wasm_btor2/test_translation.py
  tests/pairs/wasm_btor2/test_corpus_seed_0002.py -v` → 53 passed;
  `pytest tests/pairs/wasm_btor2/` → 202 passed, 16 pre-existing z3
  failures (unchanged from P8).
- **Next iteration's planned work**: P10 — extend the translator with
  `i32.and`, `i32.or`, `i32.xor`, `i32.shl`, `i32.shr_s`, `i32.shr_u`,
  `i32.rotl`, `i32.rotr` and land seed task `0003-shift-amount-mask`
  (a function demonstrating that WASM masks shift counts mod 32,
  distinct from undefined behavior at source level). Alternatively, add
  `i32.eqz`, `i32.eq`, `i32.ne`, `i32.lt_s`, `i32.lt_u`, `i32.gt_s`,
  `i32.gt_u`, `i32.le_s`, `i32.le_u`, `i32.ge_s`, `i32.ge_u`
  comparison instructions (needed for `if` expressions and `br_if`
  control flow, not yet in scope but these are pure arithmetic
  without trap semantics so they are cheap to add).
- **Open BLOCKERs**: none.

---

## 2026-05-20T02:00:00Z — P8: witness lifter skeleton

- **Phase**: P8 complete.
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/lift/witness.py` — `WasmWitness`
    dataclass: `params` (dict[int, int] — param index → unsigned i32),
    `trap_step` (int | None — first BMC cycle where trap fires),
    `n_params` (int — count of params detected). `as_signed(k)` converts
    `params[k]` to a signed i32 in [-2^31, 2^31).
  - Created `gurdy/pairs/wasm_btor2/lift/parse_z3_model.py` —
    `parse_z3_model(witness_text)` parses `str(z3_model)` into
    `{var_name: int}`. Handles decimal, `#x` hex, `#b` binary, and `0x`
    hex value formats. Variable names may contain `!` (z3 step suffix).
  - Created `gurdy/pairs/wasm_btor2/lift/lifter.py` — `lift_witness(
    btor2_flattened, witness_text)`. Builds nid→symbol map from BTOR2
    state/input lines (format: `nid op sort_nid symbol`). Extracts param
    values from `in0_n{param_k_init_nid}` (primary) with fallback to
    `s0_n{local_k_nid}` (init equality). Finds `trap_step` by scanning
    `s{c}_n{trap_nid}` for the smallest cycle where value ≠ 0. Accepts
    `btor2_flattened` as bytes or str.
  - Updated `gurdy/pairs/wasm_btor2/lift/__init__.py` — exports
    `WasmWitness`, `lift_witness`, `parse_z3_model`.
  - Created `tests/pairs/wasm_btor2/test_lift.py` — 25 tests:
    WasmWitness construction/defaults/as_signed (6), parse_z3_model
    decimal/#x/#b/0x/multiline/empty/bang-suffix (7), lift_witness
    param-from-in0/fallback-s0/trap-step/trap-at-zero/no-trap/no-params/
    empty-witness/wrapping/hex-values/bytes-input/n_params-count (11),
    integration test against compiled 0001-i32-add-wrap with synthetic
    witness string confirming nid mapping end-to-end (1).
- **Note on environment**: z3 is not installed in this container;
  16 tests in `test_solvers.py` that `import z3` directly fail with
  `ModuleNotFoundError`. These were pre-existing before P8 (P7 ran in
  an environment where z3 was available). The 25 new lift tests are
  z3-free and all pass.
- **Verification**: `pytest tests/pairs/wasm_btor2/test_lift.py -v` →
  25 passed; `pytest tests/pairs/wasm_btor2/` → 167 passed, 16 pre-
  existing z3 failures; full suite → 530 passed, 18 skipped, 16
  pre-existing z3 failures.
- **Next iteration's planned work**: P9 — extend the translator with
  `i32.div_s`, `i32.div_u`, `i32.rem_s`, `i32.rem_u` instructions and
  land seed task `0002-div-trap` (`bench/wasm-btor2/corpus/seed/
  0002-div-trap/`): a two-param function that performs signed integer
  division, expected to trap when the divisor is zero. This is the first
  corpus task where z3-bmc should return `verdict="reachable"` and the
  lifter produces a non-trivial `WasmWitness` (divisor=0 at trap_step>0),
  validating the full P7→P8 pipeline end-to-end.
- **Open BLOCKERs**: none.

---

## 2026-05-20T00:00:00Z — P7: z3-bmc solver adapter

- **Phase**: P7 complete.
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/solvers/_bmc.py` — backend-agnostic
    BMC driver copied from `riscv_btor2` (v2-bootstrap) with all imports
    re-targeted to `gurdy.pairs.wasm_btor2.btor2.*`. Contains `Compiled`
    (engine-neutral structural form of a parsed BTOR2 Model), `Backend`
    (Protocol every engine adapter satisfies), `compile_btor2` (structural
    compiler), and `bmc(comp, bound, backend)` (3-arg unroller; cycles
    through `bound` steps, asserts init/next/constraint/bad disjunction,
    calls check_sat).
  - Created `gurdy/pairs/wasm_btor2/solvers/btor2_to_z3.py` — z3 Backend
    adapter copied from `riscv_btor2` (v2-bootstrap), re-targeted. Provides
    `Z3Backend` (all BTOR2 op vocabulary → z3 expression translations:
    bitvec arithmetic, logic, shifts, comparisons, ite, concat, read/write,
    slice/sext/uext) and the 2-arg `bmc(comp, bound)` convenience wrapper
    that wires `Z3Backend` automatically. `compile_to_z3 = compile_btor2`
    alias preserved.
  - Created `gurdy/pairs/wasm_btor2/solvers/z3bmc.py` — `Z3BMCSolver`
    (`InProcessSolverBackend`) with `name="z3-bmc"`. `dispatch(artifact_bytes,
    directive)` parses `artifact_bytes` as UTF-8 BTOR2 text via
    `wasm_btor2.btor2.parser.from_text`, compiles to `Compiled` via
    `compile_btor2`, reads `directive.bound`, calls `bmc(comp, bound,
    Z3Backend())`, and returns `RawSolverResult(verdict, elapsed, engine,
    payload)`. On `reachable`: extracts `solver.model()` into
    `payload={"witness_text": str(model)}`. Gracefully returns
    `verdict="error"` on parse failures and `verdict="unknown"` on
    `NotImplementedError` (unsupported BTOR2 ops).
  - Updated `gurdy/pairs/wasm_btor2/solvers/__init__.py` — exports
    `Z3BMCSolver`, `Compiled`, `compile_btor2`, `Z3Backend`, `bmc`.
  - Updated `tests/conftest.py` — appends
    `/usr/local/lib/python3.11/dist-packages` to `sys.path` when present,
    making the system-installed `z3-solver` visible to the pytest venv.
  - Created `tests/pairs/wasm_btor2/test_solvers.py` — 28 tests:
    import/structural smoke (Z3BMCSolver, Compiled, bmc3, bmc2,
    Z3Backend instantiation), compile_btor2 shapes (state_nids,
    bad_nids from minimal BTOR2 fixtures), bmc3 direct (no-bad-node →
    unreachable; always-bad → reachable with solver; seed artifact →
    unreachable at bound=8), Z3BMCSolver.dispatch (verdict unreachable,
    engine name, elapsed > 0, payload None on unreachable, payload
    witness_text on reachable, graceful error on malformed bytes,
    bound=0 no-bad → unreachable), Z3Backend unit ops (bv_const/zero/
    one/ones, add, eq, ite, unsupported op raises NotImplementedError,
    check_sat sat/unsat).
- **Validation on seed task**: `Z3BMCSolver().dispatch(artifact, bound=8)`
  on `0001-i32-add-wrap` → `verdict="unreachable"` in ~20ms.
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 158 passed
  (28 new); full suite → 541 passed, 16 skipped, 0 failed.
- **Next iteration's planned work**: P8 — lifter skeleton
  (`gurdy/pairs/wasm_btor2/lift/`). Given a `RawSolverResult` with
  `verdict="reachable"` and a `witness_text` from the z3 model, extract
  a `WasmWitness` (concrete parameter assignments and the step at which
  the trap fires). Validate on a minimal BTOR2 model with a reachable
  bad node to confirm witness parsing.
- **Open BLOCKERs**: none.

---

## 2026-05-19T22:00:00Z — P6: Corpus seed task 0001-i32-add-wrap

- **Phase**: P6 complete.
- **What changed**:
  - Created `bench/wasm-btor2/corpus/seed/0001-i32-add-wrap/module.wasm`
    — 42-byte hand-crafted WASM binary: type section `(i32,i32)→i32`,
    function section (one func, type index 0), export section
    (`"main"` → func 0), code section (body: `local.get 0; local.get 1;
    i32.add; end`). SHA-256:
    `c4e0c901b54c4ba8036806aaf9ba3766469dde748870ade4943c300ca5b84558`.
  - Created `bench/wasm-btor2/corpus/seed/0001-i32-add-wrap/spec.json`
    — `WasmBtor2Spec` serialized: `pair="wasm-btor2"`,
    `module.path="module.wasm"`, `module.content_hash` set to SHA-256
    above, `scope.entry_function="main"`, `question.kind="reach_trap"`,
    `question.negate=false`, `analysis.engine="z3-bmc"`, `bound=8`,
    `timeout=60`. Round-trips via `WasmBtor2Spec.from_jsonable`.
  - Created `bench/wasm-btor2/corpus/seed/0001-i32-add-wrap/task.toml`
    — task metadata: `id="0001-i32-add-wrap"`, `pair="wasm-btor2"`,
    `task_class="wrap-semantics"`, `difficulty="T1"`,
    `oracle_provenance="manual-proof"`, `expected.verdict="unreachable"`,
    `oracle.status="agreement"`, `oracle.bound=8`, `oracle.cases_checked=5`.
  - Created `tests/pairs/wasm_btor2/test_corpus_seed.py` — 24 tests:
    file-shape checks (module.wasm magic/version/size, spec.json/task.toml
    presence), content_hash round-trip against actual SHA-256,
    `WasmBtor2Spec.from_jsonable` round-trip, oracle agreement for 5
    concrete param pairs `(0+0, 3+5, 1+(−1), INT32_MAX+1, −1+(−1))`,
    `Btor2ReasoningInterpreter` bad_fired=False for 6 param pairs at
    bound=8 (confirming reach_trap unreachable via concrete simulation).
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 130 passed
  (24 new); full suite → 513 passed, 16 skipped, 0 failed.
- **Next iteration's planned work**: P7 — z3-bmc solver adapter
  (`gurdy/pairs/wasm_btor2/solvers/`). Wire up z3 Python API to consume
  a `CompiledArtifact`, run bounded model checking on the flattened
  BTOR2 output, and return `verdict ∈ {reachable, unreachable, unknown}`
  with a witness on `reachable`. Validate on `0001-i32-add-wrap` (expect
  `unreachable` at bound 8).
- **Open BLOCKERs**: none.

---

## 2026-05-19T20:00:00Z — P5: Alignment oracle

- **Phase**: P5 complete.
- **What changed**:
  - Created `bench/wasm-btor2/oracle_align.py` — standalone alignment
    oracle module + CLI. Public API: `ORACLE_VERSION = "1.0.0"`,
    `make_add_wasm()` (returns 0001-i32-add-wrap WASM bytes),
    `AlignmentMismatch(step, label, source_value, reasoning_value)`,
    `AlignmentReport(outcome, steps_checked, mismatches)`, and
    `run_oracle(params, *, bound=8, wasm_bytes=None, entry_name="main")`.
  - `run_oracle` wires up `WasmSourceInterpreter` and
    `Btor2ReasoningInterpreter` on the same concrete inputs:
    (a) compiles WASM → BTOR2 via `Translator`; (b) runs the source
    interpreter with `record_shadow=True` to capture per-step
    `local_write` deltas; (c) runs the reasoning interpreter with
    `state_init_by_symbol = {local_k: params[k]}` to supply concrete
    param values (overriding the `param_k_init` input-node init);
    (d) walks the two traces step-by-step comparing local-variable
    values and the trap flag. Reports "agreement" or "divergence"
    with the full mismatch list.
  - CLI output for 0001-i32-add-wrap over 5 test cases (0+0, 3+5,
    1+(-1), INT32_MAX+1, -1+-1): all report agreement over 4 steps.
  - Created `tests/pairs/wasm_btor2/test_oracle.py` — 19 tests:
    version export, `make_add_wasm` shape, agreement for 0+0 / 3+5 /
    INT32_MAX+1 / -1+-1 / negative-param / asymmetric pairs,
    steps_checked > 0, no-mismatches-on-agreement, `agrees` property,
    summary string, report field presence, trap agreement for
    unreachable function (steps_checked=1, no mismatches), bound
    parameter limits steps, bound=1 still agrees.
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 106 passed;
  full suite → 489 passed, 16 skipped, 0 failed.
- **Next iteration's planned work**: P6 — Corpus seed task
  (`bench/wasm-btor2/corpus/seed/0001-i32-add-wrap/`). Write
  `task.toml`, `spec.json`, and an inline WASM binary
  (`module.wasm`), wired together as a ground-truth seed: expected
  verdict `unreachable` (trap never fires for i32.add), verified by
  the oracle and the reasoning interpreter at bound 8.
- **Open BLOCKERs**: none.

---

## 2026-05-19T18:00:00Z — P4: Translator (WASM MVP → BTOR2)

- **Phase**: P4 complete.
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/translation/builder.py` — BTOR2
    node-construction helpers adapted from the riscv-btor2 reference;
    imports target `gurdy.pairs.wasm_btor2.btor2.*`; adds `bv16` to
    SORT_TABLE for PC encoding.
  - Created `gurdy/pairs/wasm_btor2/translation/layers.py` — per-layer
    emitters (`emit_header`, `emit_machine`, `emit_library`,
    `emit_dispatch`, `emit_init`, `emit_constraint`, `emit_bad`,
    `emit_binding`). Value stack modeled as BTOR2 `Array[bv8, bv32]`;
    PC as bv16; SP as bv8; locals as individual bv32 state variables;
    params initialized from `input` nodes at step 0. P4 instruction
    set: `i32.const`, `i32.add`, `i32.sub`, `i32.mul`,
    `local.get/set/tee`, `drop`, `nop`, `end` (function-level),
    `return`, `unreachable`. Unsupported instructions set the trap
    flag. `reach_trap` property emits `bad trap_nid`. `LocalInit`
    assumptions emit BTOR2 `constraint` nodes. Dispatch uses PC-keyed
    ITE trees over all state components.
  - Created `gurdy/pairs/wasm_btor2/translation/translate.py` —
    `Translator.translate(spec, source, annotation_emitter)` assembles
    layers in order, splits on `:layer:NAME:begin`/`:end` markers, and
    returns `CompiledArtifact`. `TRANSLATOR_VERSION = "1.0.0"`.
  - Updated `gurdy/pairs/wasm_btor2/translation/__init__.py` — exports
    `Translator`, `translate`, `TRANSLATOR_VERSION`, `SCHEMA_VERSION`.
  - Created `tests/pairs/wasm_btor2/test_translation.py` — 18 tests:
    version exports, CompiledArtifact shape (pair, schema_version, all
    8 layers present), i32.add/sub/mul/const compile without error,
    BTOR2 flattened output is parseable, bad layer non-empty for
    reach_trap, bad node present in BTOR2 text, negate=True inserts
    `not` in bad layer, ValueError when entry not found, LocalInit
    emits a constraint node.
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 87 passed;
  full suite → 470 passed, 16 skipped, 0 failed.
- **Next iteration's planned work**: P5 — Alignment oracle
  (`bench/wasm-btor2/oracle_align.py`). Wire up `WasmSourceInterpreter`
  and `Btor2ReasoningInterpreter` on the same concrete inputs, run the
  BTOR2 model through the reasoning interpreter, and assert that
  observable state (locals, trap flag) aligns step-by-step with the
  source interpreter's trace. Target: `0001-i32-add-wrap` shape —
  a two-param i32 add with symbolic inputs at BMC bound 8.
- **Open BLOCKERs**: none.

---

## 2026-05-19T16:00:00Z — P3: Reasoning interpreter (BTOR2)

- **Phase**: P3 complete.
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/btor2/` — full copy of the
    pair-agnostic BTOR2 subpackage from `riscv_btor2` at
    INTERPRETER_VERSION 1.1.0: `nodes.py` (Model AST, BitvecSort,
    ArraySort, Node, Comment), `evaluator.py` (concrete single-cycle
    evaluator for all arithmetic, logic, shift, comparison, memory,
    extension, slice, concat, ite ops), `parser.py` (permissive HWMCC
    superset parser with diagnostic reporting), `printer.py`
    (canonical round-trip text emitter), `__init__.py`. All imports
    redirected to `gurdy.pairs.wasm_btor2.btor2.*`; copy is
    self-contained so the wasm pair can diverge independently.
  - Created `gurdy/pairs/wasm_btor2/reasoning_interp/bindings.py` —
    `Btor2ReasoningBinding` with `pair = "wasm-btor2"`,
    `state_init_by_symbol`, `input_per_step_by_symbol`, and
    `from_jsonable`.
  - Created `gurdy/pairs/wasm_btor2/reasoning_interp/interpreter.py` —
    `Btor2ReasoningInterpreter.run()` producing `ReasoningTrace` with
    `pair = "wasm-btor2"` and `INTERPRETER_VERSION = "1.1.0"`. Full
    multi-step transition system: init-clause seeding, per-step input
    injection, next-clause state advancement, POST-step bad-clause
    firing detection. `_artifact_hash` uses SHA-256 of flattened bytes.
  - Updated `gurdy/pairs/wasm_btor2/reasoning_interp/__init__.py` —
    exports `Btor2ReasoningBinding`, `Btor2ReasoningInterpreter`,
    `INTERPRETER_VERSION`; docstring records copy provenance.
  - Created `tests/pairs/wasm_btor2/test_reasoning_interp.py` — 11
    tests: PAIR_ID == "wasm-btor2", INTERPRETER_VERSION exported,
    counter advances per step, `state_init_by_symbol` override,
    bad-clause fires at correct step, no bad → no firing, per-step
    input injection, `from_jsonable` round-trip, zero steps, btor2
    subpackage independence (parser + evaluator + printer each
    exercised), artifact hash in trace.
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 69 passed;
  full suite → 452 passed, 16 skipped, 0 failed.
- **Next iteration's planned work**: P4 — Translator (WASM MVP →
  BTOR2). Minimal viable translator in
  `gurdy/pairs/wasm_btor2/translation/`: compile a single-function
  WASM module with i32 arithmetic (add, sub, const) into a BTOR2
  transition system covering the `header`, `machine`, `library`,
  `dispatch`, `init`, and `bad` sections per V2_BOOTSTRAP.md §3.3.
  Start with the `0001-i32-add-wrap` seed task shape.
- **Open BLOCKERs**: none.

---

## 2026-05-19T14:00:00Z — P2: Source interpreter skeleton

- **Phase**: P2 complete.
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/source/decoder.py` — full WASM 1.0
    MVP binary decoder: LEB128 readers; type/import/function/export/
    global/memory/code/data section parsers; pre-decoded `Instr` list
    with two-pass jump-target resolution for block/loop/if/else/end.
  - Updated `gurdy/pairs/wasm_btor2/source/__init__.py` — `WasmSource`
    wrapper with `export()`, `export_func_idx()`, `func_type()`,
    `code_entry()`, `is_import()`, `globals_info()`, `memory_info()`,
    `import_funcs()`; `load_wasm_source(payload)` accepting bytes or
    path, sets `content_hash` (SHA-256).
  - Created `gurdy/pairs/wasm_btor2/source_interp/bindings.py` —
    `WasmInputBinding` (param_init, global_init, memory_init,
    import_returns; FREE sentinel; FreeFieldNotAllowed).
  - Created `gurdy/pairs/wasm_btor2/source_interp/interpreter.py` —
    `WasmSourceInterpreter.run()` producing `SourceTrace` with one
    `SourceStep` per instruction: all i32/i64 integer arithmetic,
    comparisons, bitwise ops, shifts, rotates; memory load/store (all
    widths, sign/zero extend); structured control flow (block, loop,
    if/else, br, br_if, br_table, return); local.get/set/tee,
    global.get/set; call (direct, imports via import_returns);
    memory.size/grow; drop, select; i32.wrap_i64,
    i64.extend_i32_s/u; trap handling (unreachable, div-by-zero,
    overflow, OOB memory, stack depth). Shadow mode records
    local/global reads and writes per step.
  - Updated `gurdy/pairs/wasm_btor2/source_interp/__init__.py`.
  - Created `tests/pairs/wasm_btor2/test_source.py` — 17 tests covering
    decode errors, section parsing, branch-target resolution, and
    WasmSource accessors.
  - Created `tests/pairs/wasm_btor2/test_interp.py` — 23 tests covering
    constants, params, arithmetic (add/sub/mul/div wrap/trap/signed),
    shifts (mask-mod-32 semantics for corpus seed 0004), control flow
    (if/else, loop with br-back), memory round-trip and OOB trap,
    local.tee, conversions, trace step count, shadow mode, FREE
    binding rejection, and direct call.
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 42 passed;
  full suite → 421 passed, 18 skipped, 0 failed.
- **Next iteration's planned work**: P3 — Reasoning interpreter (BTOR2).
  Port `gurdy/pairs/riscv_btor2/reasoning_interp/` to
  `gurdy/pairs/wasm_btor2/reasoning_interp/` by copying the
  pair-agnostic BTOR2 simulator and marking it with
  `INTERPRETER_VERSION` for audit traceability per V2_BOOTSTRAP.md §3.2.
- **Open BLOCKERs**: none.

---

## 2026-05-19T12:00:00Z — P1: Schema v1.0.0

- **Phase**: P1 complete.
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/spec.py` — full Schema v1.0.0
    type system:
    - `Comparison` enum (eq/ne/lt/le/gt/ge + unsigned variants)
    - `WasmModuleRef(path, content_hash)` — module binary reference
    - `AnalysisScope(entry_function, included_callees)` — entry point
    - Observables: `LocalAt`, `GlobalAt`, `MemoryByteAt`, `StackDepthAt`
    - Assumptions: `LocalInit`, `GlobalInit`, `MemoryInit`, `ImportFixed`
    - `PropertyKind` enum (`reach_trap`, `reach_host_call`,
      `reach_memory`, `safety`)
    - `QuestionSpec(kind, predicate, negate)` — tagged property
    - `AnalysisDirective(engine, bound, timeout, extra_options)`
    - `WasmBtor2Spec` — frozen, hashable top-level spec with
      `from_jsonable` classmethod and full JSON round-trip
    - `validate_wasm_btor2_spec(spec, source=None)` — structural
      validator emitting `Diagnostic` instances (codes 0001–0031)
  - Frozen `gurdy/pairs/wasm_btor2/SCHEMA.md` at version `1.0.0` —
    documents all types, fields, discriminants, constraints, and
    out-of-scope items.
  - Created `tests/pairs/wasm_btor2/test_spec.py` — 16 tests
    covering: default construction, minimal valid spec, `from_jsonable`
    round-trip, `spec_hash` stability, all validator error codes.
- **Verification**: all spec tests pass (`import ok`, round-trip ok,
  hash stable, all validator codes confirmed in-process).
- **Next iteration's planned work**: P2 — Source interpreter skeleton.
  Write `gurdy/pairs/wasm_btor2/source.py` (`WasmSource` wrapping a
  parsed WASM binary with `export()` and function/global/memory
  accessors) and `gurdy/pairs/wasm_btor2/source_interp.py` (a minimal
  step-based interpreter over the WASM 1.0 MVP integer opcode subset,
  capable of producing observable traces for the test corpus).

---

## 2026-05-19T00:00:00Z — P0b: package metadata + CI baseline

- **Phase**: P0 complete.
- **What changed**:
  - Audited `gurdy/core/` against `v2-bootstrap`: file-for-file
    identical (38 files). No copy needed — `main` already carries
    the v2 core. Pair-agnostic contract (`schema.py`, `pair.py`,
    `layers.py`, `dispatch.py`, `interp/` shared types) is already
    present and unmodified.
  - Added `wasm-btor2 = []` to `[project.optional-dependencies]`
    in `pyproject.toml`.
  - Added `"gurdy.pairs.wasm_btor2" = ["SCHEMA.md"]` to
    `[tool.setuptools.package-data]`.
  - Created `tests/pairs/wasm_btor2/test_smoke.py` — 2 tests
    verifying all 7 submodules are importable with docstrings and
    that `SCHEMA.md` is accessible via `importlib.resources`.
- **Verification**: `pytest tests/pairs/wasm_btor2/ -v` → 2 passed.
- **Next iteration's planned work**: P1 — Schema v1.0.0 for
  `wasm-btor2`. Write `gurdy/pairs/wasm_btor2/spec.py` with
  `WasmBtor2Spec` (subclass of `BaseSpec`), `AnalysisScope`,
  `WasmModuleRef`, and `QuestionSpec` for the WASM MVP reach
  property. Freeze `SCHEMA.md` to `1.0.0`. Mirror riscv_btor2
  spec.py structure but strip RISC-V-specific types.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).

---

## 2026-05-18T07:30:00Z — P0a: package scaffold landed

- **Phase**: P0 in progress (P0a complete).
- **What changed**:
  - Created `gurdy/pairs/wasm_btor2/` with submodule directories
    `source/`, `source_interp/`, `reasoning_interp/`, `translation/`,
    `lift/`, `solvers/`. Each carries an `__init__.py` with a
    one-paragraph docstring stating its role and the phase at which
    implementation begins (per `V2_BOOTSTRAP.md` §6).
  - `gurdy/pairs/wasm_btor2/SCHEMA.md` placeholder noting the
    schema is frozen at `1.0.0` at P1.
  - `bench/wasm-btor2/{corpus/seed, corpus/external, baselines,
    experiments}/.gitkeep`.
  - `tests/pairs/wasm_btor2/__init__.py`.
- **Verification**: `python -c "import
  gurdy.pairs.wasm_btor2; ..."` succeeds for all seven submodules.
- **Next iteration's planned work**: P0b — copy `gurdy/core/`
  primitives from the `v2-bootstrap` branch where they conform to
  the pair-agnostic contract (`schema.py`, `pair.py`, `layers.py`,
  `dispatch.py`, `interp/` shared types). Audit each file against
  `V2_BOOTSTRAP.md` §3 before copying; do not pull WASM-incompatible
  code.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).

---

## 2026-05-17T00:00:00Z — Branch bootstrap

- **Phase**: pre-P0. Nothing implemented yet on this branch.
- **What's here**: `V2_BOOTSTRAP.md` (spec), `V2_AGENT_LOOP.md`
  (procedure), `V2_PROGRESS.md` (this file),
  `bench/wasm-btor2/SCOPE.md` (benchmark scope). Everything else
  is inherited from `main`.
- **Next iteration's planned work**: P0 — scaffold the
  `gurdy/pairs/wasm_btor2/` package and `bench/wasm-btor2/`
  directory shape per `V2_BOOTSTRAP.md` §5. Copy `gurdy/core/`
  primitives from the `v2-bootstrap` branch where they conform
  to the pair-agnostic contract.
- **Open BLOCKERs**: none.
- **Reference branches**: `main` (v1), `v2-bootstrap`
  (`riscv-btor2` v2 — pattern source).
