# Proving — how the books would come to demand a mechanical proof

This document says how the platform would come to *demand* the
`proved` tier from a pair designer — instead of merely accepting it
when offered, which is all the contract does today. The finding it
writes up: the architecture has the slots already cut — the tier and
its obligation, the checker stack, the brief currency, the
protected-field mechanism — and what is missing is demand-side
machinery, not checking machinery. It is a design document in the
sense of [`FRONTIER-PLAN.md`](./FRONTIER-PLAN.md): everything below
is named work, not landed code.

## 1. The gap, stated exactly

The `proved` tier is real but **answer-level**. The wired pipeline
([`gurdy/solvers/proved.py`](./gurdy/solvers/proved.py)) certifies
that the emitted formula is unsat — DRAT elaborated to LRAT,
re-validated by `cake_lpr`, the formally verified checker, with
negative controls ([`SCALING.md`](./SCALING.md) §9's I19 discipline).
What no artifact certifies is the **translation**: that the formula
*means* what the source meant. [`SCALING.md`](./SCALING.md) §11 names
this residual itself — "`proved`-encoding faithfulness — that a
universal claim's CNF means what it says is itself a translation
needing a square."

And nothing *demands* the tier:

- no pair ships a translation-level certificate; three pairs carry
  `checked` → `proved` as a registered fidelity target and the bridge
  claims `predicted` / `proved` ([`REGISTRY.md`](./REGISTRY.md)), all
  as aspiration with no enforcement point;
- the books have no proof-shaped generation target — the trust arm
  names only `declare-provenance` and `independent-pair`
  ([`gurdy/core/trust.py`](./gurdy/core/trust.py)), even while
  hinting at the missing instrument ("certificates at the terminal
  are the other instrument");
- the gate protects the projection and the coverage floors
  ([`SCALING.md`](./SCALING.md) §12.1), but not the fidelity floor.

## 2. What the platform already supplies

Four slots exist today and are load-bearing for everything below:

- **The tier, with a real obligation.**
  [`PAIRING.md`](./PAIRING.md) §1/§4 and
  [`ARCHITECTURE.md`](./ARCHITECTURE.md) §7: a `proved` pair ships a
  certificate an independent checker re-verifies — a refinement proof
  or a translation-validation certificate — stating exactly what it
  proves, and recording its checker and trusted computing base.
- **The checker stack.** The bit-blast → DRAT → LRAT →
  verified-checker chain is live with positive and negative controls
  ([`REGISTRY.md`](./REGISTRY.md), framework row), and the pedigree
  ladder is already graded ([`SOLVERS.md`](./SOLVERS.md) §6:
  independent re-discharge < verified checker < proof-assistant
  kernel).
- **The proof-gate discipline, in-repo.**
  [`paper/mechanization/`](./paper/mechanization/README.md) is the
  precedent: pinned `lean-toolchain`, no mathlib, zero `sorry`s, an
  axiom audit printed at every build. A demanded per-pair proof
  inherits exactly this gate.
- **The brief currency.** The fidelity target is already a brief
  field; `checked` → `proved` is already how a registration states
  the intent. Demanding a proof is a floor on an existing field, not
  a new vocabulary.

## 3. The demand: a `certify-pair` target kind

The trust obstacle ([`POTENTIAL.md`](./POTENTIAL.md) §1, fifth in the
walk) should be able to name a third instrument. **`certify-pair`**:
upgrade a named pair's grade to `proved` on a named fragment, by a
named species (§5). It fires when the asker's assurance floor is
unmet and no independent branch corroborates past — the same failure
that today names `independent-pair` — and the books should show
*both* targets, priced against each other: the anchor census says
whether a genuinely independent second route even exists to build;
the ledger's cost side says what a certificate costs against a new
front-end. Two honest instruments for one failure; the evidence
decides, the platform never chooses.

The frontier currency is ready for it. A frontier pair's required
contract already joins the highest cited floor
([`FRONTIER-PLAN.md`](./FRONTIER-PLAN.md) §1.6), so a demand whose
*only* gap is assurance — connectivity, loss, shape, and cost all
clear — is precisely a proof demand: same signature identity, same
evidence payload, same compounding across benchmarks.

## 4. The obligation: the fidelity floor as a protected field

Registration briefs fix protected fields the builder cannot shrink —
projection, coverage floors, direction policy — and the gate
diff-rejects edits to them ([`SCALING.md`](./SCALING.md) §12.1). Add
the **fidelity floor**: `proved`, with the named checker and TCB.
Enforced at `built`, not at merge — the thin-slice path
([`PAIRING.md`](./PAIRING.md) §1) stays: a `partial` pair widens
under `checked`, and the proof gates the `built` promotion, exactly
as §8 of the pairing contract gates it today. A scoped registration
mandate ([`FRONTIER.md`](./FRONTIER.md) §4.2) extends the same way:
the mandate fixes the floor for its region, and a mandate-registered
brief inherits it.

## 5. Two admissible species, two gates

- **Per-run translation validation** — the tractable species, and
  the better architectural fit. The translator stays untrusted; each
  translation ships a certificate; a deterministic, pinned,
  **independent** checker validates it. This is the same seam that
  quarantines `decide` ([`SOLVERS.md`](./SOLVERS.md) §1): certificate
  *production* may use an oracle, certificate *checking* may not.
  Scope is per-instance and per-construct, so it composes with
  partiality — no vacuous-`proved` risk beyond what the per-construct
  coverage conjunction ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §7)
  already guards. Negative controls are mandatory: a corrupted
  certificate must fail, exact success-line parse, the I19
  discipline unchanged.
- **Once-and-for-all refinement proof** — feasible where a
  mechanized semantics already exists, which in this registry means
  **along Sail**. Gated exactly like
  [`paper/mechanization/`](./paper/mechanization/README.md) — pinned
  toolchain, `lake build`, zero `sorry`s, axiom audit — with
  [`SCALING.md`](./SCALING.md) §10 retry caps and escalation, since
  an LLM builder that cannot close a proof must surface, not spin.

## 6. Why the demand stays selective

The asymmetry (paper Thm 4.8; `existential_self_certifying` in the
mechanization) already gives existential answers away free: every
`reachable` is carried back and replayed through the shared source
interpreter, so a proof buys nothing there. `proved` purchases
assurance in exactly one corner — **universal verdicts flowing
through hops no independent branch corroborates**. A blanket proof
requirement on every pair would spend proof cost where replay
already gives the guarantee, and would tax the loop's throughput
([`FRONTIER.md`](./FRONTIER.md) §3: the loop must run faster than a
human's hands). So the demand is floor-driven, like every other
obstacle: the books ask for a proof when an asker's floor is unmet
and the trust advisor finds no cheaper instrument — never as an
admission tax on pair designers at large.

## 7. The first inhabitant

A translation-validation certificate for `btor2-smtlib`'s
`proved`-tier encoding: per unrolled step, the emitted constraint is
checked equivalent to the BTOR2 transition relation by an
independent engine, the equivalence discharged through the
already-validated DRAT → LRAT → `cake_lpr` chain. That closes
[`SCALING.md`](./SCALING.md) §11's own stated residual with
infrastructure already validated on the host, and gives
`certify-pair` its first discharge — the pattern
([`SYNTHESIS.md`](./SYNTHESIS.md) set the precedent) being that a
new demand kind lands together with one inhabitant that proves the
gate real.

*Status (2026-07-18): nothing above is landed — no `certify-pair`
target, no fidelity-floor enforcement, no pair-level certificate.
This document is the named future work.*
