# Language — CRN (chemical reaction network)

A chemical reaction network: a set of species and reactions transforming
reactant multisets into product multisets. The platform's **non-CS source
language** and the evidence that the architecture is field-blind
([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §1) — the source is chemistry,
not code. Source of `crn-smtlib`.

## Formal semantics (source of truth)

A CRN has a precise, textbook formal semantics in two flavors:

- **Discrete / Petri-net.** A marking is a species-population vector; a
  reaction fires when its reactants are present, updating populations by its
  stoichiometry. This is exactly a Petri net, and it is the semantics
  `crn-smtlib` encodes for **bounded reachability**.
- **Stochastic / CTMC.** Under mass-action kinetics, the same network
  defines a continuous-time Markov chain over population states.

The discrete reading is what makes a `predicted` translation
to SMT-LIB possible: given the network and a step bound, the arithmetic
constraints are determined.

## Formal model — no Sail (not an ISA); a mathematical semantics

CRNs are not an ISA, so there is no Sail model — but none is needed: the
Petri-net/CTMC semantics *is* the formal model. It is mechanized and
checkable in **PRISM** / **STORM** (probabilistic / CTMC model checking)
and **Maude** (the Petri-net rewriting semantics). These serve as external
oracles for the shared interpreter.

## Shared interpreter

**Role: source.** A deterministic executor of the discrete (Petri-net)
semantics: given an initial marking and a firing schedule/bound, produce the
post-step population states ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5).
Observables are species populations per step. Validate against a PRISM/Maude
oracle. Shared by every CRN pair.

## Public benchmarks

Coverage anchor ([`BENCHMARKS.md`](../../BENCHMARKS.md) §4): curated CRN /
**SBML** model sets (e.g. the **BioModels** database) and the **PRISM/STORM**
CRN case studies, pinned. Labels are partial, so coverage leans on construct
coverage plus model-evaluation of `sat` witnesses.

## Pairs over this language

- [`crn-smtlib`](../../pairs/crn-smtlib/README.md) — source.
