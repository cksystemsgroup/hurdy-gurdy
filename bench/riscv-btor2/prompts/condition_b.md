# Condition B — pair-equipped

You have everything Condition A has, plus:

- The `{{PAIR_ID}}` pair's tool surface (see the `tools` parameter
  on this request). The four tools are:
  - `compile(spec_json)` — translates a `RiscvBtor2Spec` to BTOR2,
    returning a content-addressed `artifact_id` plus diagnostics.
  - `dispatch(artifact_id, directive)` — runs the named solver
    against the artifact. `directive` is an `AnalysisDirective`
    (`engine`, `bound`, `timeout`, `havoc_registers`, `extra_options`).
    Returns a `RawSolverResult` (`verdict`, `elapsed`, `payload`,
    `reason`).
  - `lift(artifact_id, raw_result)` — translates a raw solver
    output back to source-level steps and (for `proved` verdicts)
    a lifted invariant. Returns a `LiftedResult` whose `trace`
    field has the per-cycle (pc, mnemonic, regs) you need to fill
    in the witness JSON.
  - `introspect(spec_json)` — runs the spec validator without
    compiling. Use this when you suspect your spec is malformed.

- The pair's schema document at `{{SCHEMA_URL}}`. Read it for the
  state-variable naming, lowering rules, and verdict semantics.

- A starter spec.json (below). The `binary.path`, `scope`, and
  default `analysis` are filled in; the **`property` and any
  task-specific assumptions are left for you to fill in** based on
  the question above. Do not invent fields the pair does not declare;
  if a question shape is not encodable in this spec language, emit
  `unknown` with reason `"coverage gap"`.

```json
{{STARTER_SPEC_JSON}}
```

## Property expression DSL (READ THIS BEFORE CONSTRUCTING A SPEC)

Spec fields like `property.expression` are **strings**, not
Python or C. The full grammar is enumerated in
`gurdy/pairs/riscv_btor2/translation/exprs.py`; the supported
forms are:

| Atom | Meaning |
|---|---|
| `pc` | the current program counter (bv64) |
| `true` / `false` | literal booleans (bv1) |
| `42`, `-7`, `0xDEADBEEF` | integer literals (bv64 constants) |
| `reg(N)` | current value of register N, 0 ≤ N < 32 |
| `mem(addr, width)` | memory at `addr` over `width` bytes (1, 2, 4, or 8) |
| `const(value)` | explicit bv64 constant (use when an integer literal would be ambiguous) |

| Operator | Returns | Notes |
|---|---|---|
| `eq(a, b)`, `neq(a, b)` | bv1 | use `neq` -- there is no `ne` |
| `lt(a, b)`, `le(a, b)`, `gt(a, b)`, `ge(a, b)` | bv1 | **signed** comparison |
| `ltu(a, b)`, `leu(a, b)`, `gtu(a, b)`, `geu(a, b)` | bv1 | **unsigned** comparison |
| `and(a, b)`, `or(a, b)`, `xor(a, b)`, `not(a)` | matches input width | bitwise; on bv1 results these double as logical and / or / xor / not |
| `add(a, b)`, `sub(a, b)` | bv64 | wraps mod 2⁶⁴ |

There is no `==`, no `!=`, no `<`, no `>`, no `&&`, no `||`.
Python and C operators are not in the grammar and will be
rejected by the parser.

Property objects must have exactly **two** fields:

```json
{ "expression": "<DSL string>", "negate": false }
```

There is no `affinity` field, no `reach` field, no
`assertion` field. `negate: true` flips the bad expression's
polarity (rare; only set this if you are encoding the negation
of the SCHEMA-defined `bad` polarity from §8).

Concrete worked example. To express the question "after the
program halts at PC 0x10008, can register x10 hold the value
12?", the property is:

```json
{
  "expression": "and(eq(pc, const(0x10008)), eq(reg(10), const(12)))",
  "negate": false
}
```

A two-clause example with a memory observation: "at PC
0x10010, can the byte at address 0x20100 equal 0x42 AND
register x6 be unsigned-greater-than-or-equal-to 100?":

```json
{
  "expression": "and(and(eq(pc, const(0x10010)), eq(mem(0x20100, 1), const(0x42))), geu(reg(6), const(100)))",
  "negate": false
}
```

If you need a property the grammar doesn't support, emit
`unknown` with reason `"coverage gap"` rather than improvising
operator names.

## Workflow guidance (non-binding)

A typical successful B-condition session looks like:

1. Read `SCHEMA.md` if you have not already.
2. Translate the natural-language question into a `Property.expression`
   (and any `CycleInvariant`s).
3. Call `introspect` to confirm the spec is well-formed.
4. Call `compile` to get an `artifact_id`.
5. Call `dispatch` with the default engine. If the result is
   `unknown` due to bound exhaustion or timeout, increase `bound`
   and re-dispatch; if it's `unknown` due to engine incompleteness,
   try a different engine.
6. If the result is `reachable`, call `lift` to get the source-level
   trace and read off the witness fingerprint (bad_pc, anchor cycle,
   register values).
7. Emit the final answer JSON.

You may deviate from this; the grading is on the final answer, not
the path.

## What this pair will not do

The schema deliberately excludes floating point, atomics, vector,
privileged ISA, CSR-write effects, concurrency, and memory havoc
(see `SCHEMA.md` §13). If the question requires any of these, the
correct verdict is `unknown` with reason `"coverage gap"`.
