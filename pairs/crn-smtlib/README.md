# Pair — `crn-smtlib`  ·  CRN → SMT-LIB

*Status: **registered** (not yet built). Ported from v2 — the non-CS pair.*

Translate a chemical reaction network, under discrete-population
(Petri-net) semantics, into SMT-LIB (`QF_LIA`) for **bounded reachability**,
decided by an SMT solver. This is the second reasoning hub (SMT-LIB
alongside BTOR2) and the evidence the architecture is **field-blind**: the
source language is chemistry, not code.

## Components ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2)

- **Source.** CRN — [`languages/crn`](../../languages/crn/README.md).
- **Target.** SMT-LIB — [`languages/smtlib`](../../languages/smtlib/README.md).
- **Translator `T`.** A schema-determined unrolling of the Petri-net
  semantics to a step bound `k`: integer population variables per species
  per step, reaction-firing constraints from the stoichiometry, and a
  reachability `bad`. `k` is a caller parameter, not a heuristic.
  Deterministic and **schema-predictable**.
- **Source interpreter.** The **shared** CRN interpreter
  ([`languages/crn`](../../languages/crn/README.md)) — reused; contributed
  by this pair if first.
- **Target interpreter.** SMT-LIB's deterministic model evaluator + text I/O
  ([`languages/smtlib`](../../languages/smtlib/README.md)) — reused.
- **Target-to-source interpreter `L`.** Decodes an SMT model into a CRN
  behavior — the firing sequence and per-step populations reaching the
  target marking. Pair-owned.

## Projection `π`

Per-step species populations and the reachability target — the CRN
interpreter's observables mapped onto the SMT-LIB integer variables.

## Fidelity target + evidence

- **`predicted`** — given the network, the bound `k`, and the schema, the
  SMT-LIB is determined byte-for-byte.
- The decision is verified by **model evaluation** (a `sat` firing sequence
  re-checked by the deterministic interpreter) and, for `unsat`, an
  independent SMT proof checker ([`SOLVERS.md`](../../SOLVERS.md) §5).

## Soundness story

Byte-prediction plus model validation: a `sat` model is replayed through the
CRN interpreter under `π` to confirm it actually reaches the target marking
([`PAIRING.md`](../../PAIRING.md) §6).

## Notes for the implementing agent

- The shared CRN interpreter implements the discrete Petri-net semantics;
  validate it against a PRISM/Maude oracle ([`languages/crn`](../../languages/crn/README.md)).
- Solvers/checkers are SMT-LIB's shared inventory; this pair wires none of
  its own ([`SOLVERS.md`](../../SOLVERS.md)).
