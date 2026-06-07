# `wasm-btor2` Schema

Schema-pinned translation contract for the `wasm-btor2` pair.

> **Status**: frozen at version `1.0.0` (P1, 2026-05-19).

## 1. Versioning

- `1.0.0` (P1): WASM 1.0 MVP, integer-only seed corpus, BMC engine,
  reach-property `QuestionSpec`. Current version.
- Minor bumps: additive features (float opcodes, multi-module,
  additional observable/assumption kinds).
- Major bumps: breaking property-shape changes (e.g. changing
  `QuestionSpec.kind` discriminant values).

Every minor/major bump requires all prior corpus tasks to still align
under the new schema; that is a hard invariant.

## 2. Top-level structure

A `WasmBtor2Spec` is serialised as:

```json
{
  "pair": "wasm-btor2",
  "fields": {
    "module":      { ... },
    "scope":       { ... },
    "observables": [ ... ],
    "assumptions": [ ... ],
    "question":    { ... },
    "analysis":    { ... }
  }
}
```

### 2.1 `module`

```json
{ "path": "<path-to-.wasm>", "content_hash": "<sha256-hex-or-null>" }
```

`path` must be non-empty. `content_hash` is optional (SHA-256 hex
digest for cache validation).

### 2.2 `scope`

```json
{ "entry_function": "<export-name>", "included_callees": ["<name>", ...] }
```

`entry_function` must be non-empty and must be an export of kind
`func` in the module. `included_callees` lists additional exported
functions inlined into the dispatch table; all other callees are
self-looped (see `V2_BOOTSTRAP.md` §3.3).

## 3. Observables

Each observable object carries `"__type__"` and its fields.

| `__type__`      | Fields                              | Description                                      |
|-----------------|-------------------------------------|--------------------------------------------------|
| `LocalAt`       | `func_idx`, `local_idx`, `step`     | Local variable value at a given execution step   |
| `GlobalAt`      | `global_idx`, `step`                | Mutable global value at a given step             |
| `MemoryByteAt`  | `address`, `step`                   | Single byte of linear memory at a given step     |
| `StackDepthAt`  | `step`                              | Operand stack depth at a given step              |

All indices are 0-based. `step` is the 0-indexed BMC cycle number.
`func_idx` counts imports first (matching the WASM binary function
section). `global_idx` counts imports first.

## 4. Assumptions

Each assumption object carries `"__type__"` and its fields. `op` is
one of `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `ltu`, `leu`, `gtu`,
`geu` (signed unless the `u` suffix).

| `__type__`    | Fields                                           | Description                                        |
|---------------|--------------------------------------------------|----------------------------------------------------|
| `LocalInit`   | `func_idx`, `local_idx`, `op`, `value`           | Constraint on a local at step 0                    |
| `GlobalInit`  | `global_idx`, `op`, `value`                      | Constraint on a mutable global's initial value     |
| `MemoryInit`  | `address`, `width`, `op`, `value`                | Constraint on initial memory at `address`          |
| `ImportFixed` | `import_module`, `import_name`, `value`          | Pin a host-import's return value to a constant     |

`MemoryInit.width` must be 1, 2, 4, or 8 (bytes). The comparison is
applied to the little-endian integer value at that address.

`ImportFixed` overrides the `Free` host-import binding used during
translation, fixing the single-value return to `value`. Multi-value
returns are deferred to a future schema bump.

## 5. Property

```json
{
  "kind":      "<kind-string>",
  "predicate": "<opaque-string>",
  "negate":    false
}
```

| `kind`            | Meaning                                                           |
|-------------------|-------------------------------------------------------------------|
| `reach_trap`      | Module traps within `bound` steps (P1 focus, predicate unused)   |
| `reach_host_call` | Host import invoked with args matching `predicate`               |
| `reach_memory`    | Linear memory or a global satisfies `predicate` at some step     |
| `safety`          | Invariant expressed in `predicate` holds at every step (k-ind.)  |

`predicate` is an opaque string parsed by the translator. It is the
empty string for `reach_trap`. `negate` flips the polarity (e.g. for
synthesis or complement-reachability).

## 6. Analysis directive

```json
{
  "engine":        "z3-bmc",
  "bound":         null,
  "timeout":       null,
  "extra_options": {}
}
```

`engine` defaults to `"z3-bmc"`. `bound` is the BMC step limit
(non-negative integer or null for engine default). `timeout` is a
positive float in seconds or null. `extra_options` is a flat
string→string map of engine-specific flags.

## 7. Layered BTOR2 artifact

The translator emits BTOR2 in the layered shape established by
`riscv-btor2` (header / machine / library / dispatch / init /
constraint / bad / binding). Layer linking is handled by
`gurdy/core/layers.py`.

## 8. Out of scope at v1.0.0

Per `bench/wasm-btor2/SCOPE.md` §1: SIMD, threads, reference types
beyond funcref, tail calls, exception handling, GC, component model,
multi-value returns from host imports. Each is a candidate for a
future minor schema bump.
