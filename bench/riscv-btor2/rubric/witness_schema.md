# Witness schema

Two halves of one contract:

1. **Author side.** What goes in `task.toml`'s `[witness]` table when
   `expected.verdict == "reachable"`.
2. **LLM side.** The JSON shape the LLM under condition B must emit
   so `matcher.py` can grade it.

The schema is grounded in the pair's existing `LiftedResult` / `WitnessTrace`
/ `LiftedStep` types (`gurdy/pairs/riscv_btor2/lift/witness.py`); we don't
invent new fields.

## Author side: `task.toml [witness]`

```toml
[witness]
# REQUIRED: the PC of the trace step at which `bad` is satisfied. The
# matcher walks the LLM's lifted trace looking for a step with this
# pc; if no step matches, the witness fails regardless of register
# values. This is the anchor that makes "right verdict, wrong witness"
# distinguishable from a genuine pass (BENCHMARKING.md §4.5).
bad_pc = 65550

# OPTIONAL: the cycle number at which the bad step occurs. Useful
# when the same pc is visited multiple times. If specified without
# `halted_step_tolerance`, must match exactly.
halted_step = 18
halted_step_tolerance = 0          # |observed - expected| ≤ tolerance

[witness.final_regs]
# OPTIONAL. Required GPR values at the bad step. Keys are integers
# 0..31 (the numeric register name; SCHEMA.md §3 doesn't use ABI
# names as state names, neither do we). Every listed register must
# match the observed value bit-for-bit. Registers NOT listed are
# free — the LLM may report any value for them.
10 = 42
5 = 8
6 = 8

[witness.executed_pcs]
# OPTIONAL. Every PC in this list must appear at least once in the
# observed trace's step list. Useful for tasks where the diagnostic
# is "the LLM must have noticed that PC P was executed before the
# bad step", e.g., a specific store that taints memory.
# = [65540, 65548]

[witness.memory]
# OPTIONAL. Required values for memory cells at the bad step.
# Each entry: address (key) → { width, value }.
# Width is in bytes (1/2/4/8). Value is interpreted as a width-byte
# little-endian integer to match SCHEMA.md §5's load semantics.
# 65536 = { width = 4, value = 0x06300013 }
```

### What "matches" means, precisely

- **`bad_pc`**: there must exist *at least one* step `s` in the LLM's
  lifted trace with `s.pc == bad_pc`. The first such step is taken as
  the witness anchor; subsequent register/memory checks are read from
  that anchor's state.
- **`halted_step`**: the chosen anchor step's `cycle` must be within
  `halted_step_tolerance` of `halted_step`.
- **`final_regs[N]`**: at the anchor step, register `N`'s observed
  value must equal the listed value (modulo 2⁶⁴; both sides are
  reduced to `uint64` before comparison).
- **`executed_pcs`**: every PC in the list appears in the *full* trace
  (not necessarily before the anchor; the order isn't checked).
- **`memory[A] = { width, value }`**: at the anchor step, the bytes
  at address `A` for `width` bytes, interpreted little-endian, equal
  `value`.

Fields the author *did not* list are free. A more demanding task
lists more fields.

### `proved` and `unknown` verdicts

These tasks omit the `[witness]` table entirely. `matcher.py` errors
at validation time if a `reachable` task lacks `[witness]` or if a
non-`reachable` task carries one. Pre-registration catches the
mistake.

## LLM side: required output JSON

The condition B/C prompt template (§9.3) instructs the LLM to emit
*exactly* this JSON:

```json
{
  "verdict":    "reachable",
  "confidence": 0.92,
  "reason":     "free-form 1-2 sentences",
  "witness": {
    "bad_pc":      65550,
    "anchor_step": 18,
    "final_regs":  { "10": 42, "5": 8, "6": 8, "0": 0 },
    "executed_pcs": [65536, 65538, 65540, 65542, 65540, 65542, 65540, 65542, 65540, 65542, 65540, 65542, 65540, 65542, 65540, 65542, 65540, 65542, 65546, 65550]
  },
  "lift": null
}
```

- `witness.bad_pc` and `witness.anchor_step` are scalars matching the
  author-side `bad_pc` and `halted_step`.
- `witness.final_regs` is a JSON object with *string* keys (JSON
  doesn't allow integer keys); the matcher converts.
- `witness.executed_pcs` is the full trace's PC list, in order — the
  matcher only checks set-membership, but ordering is recorded for
  any later post-mortem.
- `lift` is required only for T4 tasks; otherwise `null`.

Fields the LLM emits but the schema doesn't reference are ignored.
Missing required fields cause a fail with a structured reason.

## Why this shape

- **Scalar `bad_pc`** as the anchor avoids the "two coincidentally
  matching states" problem (BENCHMARKING.md §4.5).
- **Numeric register keys** match `SCHEMA.md` §3's state naming and
  the pair's `RegisterAt(register, pc)` observable.
- **No "trace length" check.** Trace length depends on the engine and
  the encoding; grading on it would penalise valid alternatives.
- **No "register x18 must be free" check.** The schema only states
  required equalities. Negative constraints ("x18 is unconstrained")
  belong in the spec's assumptions, not the witness fingerprint.
