# Architecture

## The pair as a commuting square

A pair (hop) is the top edge `T` of a commuting square; correctness is the
square commuting up to a declared projection `π`:

```
   I_in(p)  ≡_π  L( I_out( T(p) ) )
```

`I_in` is the **source semantics** — the reference. Fidelity is measured
*against it*. This asymmetry drives everything below.

## Two epistemologies

| | Source edge | Reasoning edge |
|---|---|---|
| Role in the square | reference / oracle | engine / medium |
| Requirement | formal, executable semantics (Sail-grade) | precise semantics + a sound solver |
| Trusted by… | **referential** conformance to Sail | **differential** agreement of unrelated engines |
| Grouping | **correctness commons** (shared oracle, shared lemmas) | **mechanical commons** (shared solvers, witness format, chaining) |

A language needs **oracle-grade semantics to sit on a source edge**; it
needs only **precise semantics + a sound solver to sit on a reasoning
edge**. The obligation attaches to the *edge position*, not the language
(so `btor2` is a reasoning language in `riscv_btor2`, but a *source* in the
`btor2_smtlib` bridge, where its trust is differential decide-both-ways).

## Fidelity lattice (the merge gate, correctness only)

Strength-of-evidence that the round-trip conforms to the source oracle on `π`:

| Level | Evidence | Tier |
|---|---|---|
| **F0 Typed** | compiles; lift yields well-formed source facts; structural round-trip | — |
| **F1 Tested** | round-trip agrees with Sail on a generated instance suite | `checked` (per-run) |
| **F2 Bounded** | per program, `T(p)` ≡ Sail for all inputs up to bound k (SMT) | `checked` |
| **F3 Lowering** | per-instruction machine-checked QF_BV lemma vs Sail ⇒ programs faithful by composition (paste lemma) | `transparent` |
| **F4 Extracted** | translator proven/extracted against Sail end-to-end | `transparent` |

Chains compose by **meet** (a chain's fidelity is its weakest hop); a
verifier hop may re-establish a weaker hop at run time. **Fidelity gates
merge; reasoning-utility (benchmarks) is advisory metadata and never gates.**

## `differential_only` and the Sail sandbox

`oracle_access: differential_only` means the builder agent gets **no** Sail
access (source or behavior). It builds against an independent `dev_oracle`
(Spike) and the gate validates against Sail on an **agent-blind held-out
partition**. Because the lowering never saw Sail, a gate disagreement is a
genuine differential — informative about *both* the pair and Sail. (Other
regimes: `held_out_behavioral` — gate-mediated π-only queries on a training
partition; `guided` — may read Sail, earns no validator badge.)

## Two realizations of one semantics

The `sail-riscv` group holds two realizations of the same meaning:

| Realization | Form | Role |
|---|---|---|
| Sail emulator (`oracle.py`) | executable | the **reference** (sandboxed behind the gate) |
| BTOR2 machine model | transition system | the **model-checkable** form |

**Fidelity of the machine realization = it agrees with the reference** —
the whole-machine equivalence proven once by `tools/sail_btor2_machine`
(per-instruction F3 lemmas + a fetch/decode/control harness lemma). Pairs
that target btor2 may *instantiate* this verified model and inherit its
proof, rather than re-verifying per program.

## Two agent types

- **Machine-build agent** (*referential*): has Sail access; mirrors Sail
  into the BTOR2 machine and proves equivalence. Playbook:
  `agents/playbook/BUILD_machine_from_sail.md`.
- **Pair-build agent** (*independent, differential-only*): sandboxed from
  Sail **and** from the machine model during construction; builds against
  `dev_oracle`. Playbook: `agents/playbook/IMPLEMENT_pair_differential.md`.

The structural guarantee: the *trusted* machine model and the *validating*
pair lowerings are built by different agents under different access rules,
so a pair's Sail-validation power is never contaminated by the Sail-derived
machine — even though the merged pair may *use* that machine at runtime.

## Anti-gaming invariants (enforced by the gate, not policy)

1. `projection` (π) and `fidelity.target` are **pinned at registration**
   and byte-checked by the gate; the agent cannot weaken them.
2. The gate runs **its own code on a clean checkout** — the agent cannot
   influence the referee.
3. The **oracle is external and version-pinned** (Sail) — "correct" is
   defined outside both agent and gate.
4. **Independence audit**: no Sail source vendored, no machine-model crib,
   query log empty (or within the training partition).
