# Pair — `sail-btor2`  ·  SAIL → BTOR2

*Status: **registered** (not yet built).*

Lower a Sail object — the RISC-V model applied to a program — into a BTOR2
transition system. Composed after `riscv-sail`, this completes the
**indirect** RISC-V→BTOR2 route, whose output is cross-checked against the
direct `riscv-btor2` translator at BTOR2 ([`PATHS.md`](../../PATHS.md)
§4–5). Where `riscv-btor2` encodes RISC-V into BTOR2 by hand from the spec,
this route derives the same target from the Sail model — independence is the
value.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source language.** Sail —
  [`languages/sail`](../../languages/sail/README.md).
- **Target language.** BTOR2 —
  [`languages/btor2`](../../languages/btor2/README.md).
- **Translator `T`.** A lowering from the Sail object's state and transition
  relation to a BTOR2 transition system (state variables for the model's
  architectural state, init / next / constraint / bad). The lowering is
  governed by a written specification of how Sail constructs map to
  word-level BTOR2; deterministic and, to the extent the mapping is
  rule-for-rule, schema-predictable.
- **Source interpreter.** The **shared** Sail interpreter
  ([`languages/sail`](../../languages/sail/README.md)) — reused. (Built by
  whichever Sail pair lands first.)
- **Target interpreter.** The **shared** BTOR2 interpreter
  ([`languages/btor2`](../../languages/btor2/README.md)) — reused.
- **Target-to-source interpreter `L`.** Decodes a BTOR2 witness into a Sail
  behavior — the per-step architectural state and the reached bad state —
  which `riscv-sail`'s `L` then carries up to RISC-V (and `c-riscv`'s `L` to
  C). Pair-owned.

## Translator detail

State which fragment of Sail is lowered (the subset the RISC-V model
exercises in scope) and how each construct becomes BTOR2. Pin the Sail
model/version consistently with `riscv-sail`. The encoding choices should be
documented well enough that the BTOR2 output is auditable against the Sail
semantics.

## Projection `π`

The Sail model's architectural observables mapped onto BTOR2 state
variables — kept **projection-compatible** with the direct route so that, at
BTOR2, the two routes' behaviors are compared on the same observable space
([`languages/sail`](../../languages/sail/README.md),
[`pairs/riscv-btor2`](../riscv-btor2/README.md)).

## Fidelity target + evidence

- **Declared: `checked`.** Evidence: the commuting-square oracle walks the
  shared Sail interpreter's trace against `L(I_btor2(T(p)))` under `π` on a
  corpus.
- **Toward `proved`.** As with `riscv-btor2`, ship re-checkable certificates
  for questions discharged by induction/k-induction/DRAT to lift those
  answers to `proved`.
- **Branch corroboration.** The composed route
  `riscv-sail` → `sail-btor2` is cross-checked against `riscv-btor2` at
  BTOR2; agreement raises the effective fidelity of both
  ([`PATHS.md`](../../PATHS.md) §4).

## Soundness story

Direct commuting-square check against the shared Sail interpreter, plus the
native-vs-bridged BTOR2 check available via
[`btor2-smtlib`](../btor2-smtlib/README.md), plus the branch against the
direct RISC-V→BTOR2 route. Three independent angles on the same target
([`PAIRING.md`](../../PAIRING.md) §6).

## Notes for the implementing agent

- Reuse both shared interpreters (Sail and BTOR2); add no private BTOR2 core.
- Coordinate `π` with `riscv-btor2` — comparing the two routes at BTOR2 is
  the reason this pair exists.
- Document the Sail→BTOR2 mapping enough to audit it against the Sail
  semantics, not just against test outputs.
