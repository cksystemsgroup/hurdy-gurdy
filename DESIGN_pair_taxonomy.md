# Design note — a taxonomy of pairs (translation / compile / reasoning)

*Status: proposal (recorded 2026-06-05). This note fixes **vocabulary** and
the **classification axes** for the generalized view sketched in
[`DESIGN_generalized_pairs.md`](./DESIGN_generalized_pairs.md). It commits no
code; it exists so the names are settled before the Stage-1 refactor (extract
a `Hop` genus; see that note's §11 and the staging at the end here) lands. It
extends, and does not replace, [`PAIRING.md`](./PAIRING.md) §1 ("What a pair
is") and the trust-tier table of `DESIGN_generalized_pairs.md` §4.*

## 1. The one idea: classify a pair by its *output language*

`DESIGN_generalized_pairs.md` promotes a pair from `(source → reasoning)` to
a deterministic translation between **any two formal languages**, `L_in →
L_out`, composable into **chains**. Once that move is made, two questions
about a pair are no longer the same question, and conflating them is the
source of most naming confusion:

1. **What kind of language is `L_out`?** A representation you go on to *run or
   re-translate*, or a logic you *reason/solve in*?
2. **How predictable is the translation?** Can a reader derive the output
   bytes from a schema, or only reproduce them from a pin?

These are **orthogonal axes** (§6). This note names the first; the trust
tiers of `DESIGN_generalized_pairs.md` §4 already name the second. Keeping
them apart is the whole point.

## 2. The genus: **translation pair**

> A **translation pair** is one registered, deterministic edge `L_in → L_out`
> between two languages that each carry a formal semantics. It is the genus;
> everything below is a species of it.

This replaces the bare word "pair" as the umbrella term. The justification is
that *every* pair already **is** a translation — `PAIRING.md` §3 calls the
core deliverable the "Translation function," and Appendix A of
`DESIGN_generalized_pairs.md` names the top edge of the commuting square `T
(translate)`. "Translation pair" names what they have in common; the species
below name what distinguishes them.

(The resonance with **translation validation** — `DESIGN_generalized_pairs.md`
§4/§6, CompCert/Alive2 — is deliberate and welcome: a translation pair is
exactly the object that translation validation validates.)

## 3. The two species

Split the genus by the kind of `L_out`:

| Output language `L_out` is… | What you do with it | The pair is a… |
|---|---|---|
| another **representation / execution** target (RV64 ELF, WASM, LLVM IR, C, bytecode) | run it, or re-translate it onward | **compile pair** |
| a **reasoning language** (BTOR2, SMT-LIB, TPTP, CHC/Horn, DIMACS, a proof-assistant term language) | *solve / prove / decide* — a solver lives here | **reasoning pair** |

The dividing line is a single test:

> **Is there a mechanized solver/prover/decision procedure that consumes
> `L_out` directly?** If yes, the pair is a **reasoning pair** and `L_out` is
> a reasoning language. If `L_out` is merely another representation to be run
> or re-translated, the pair is a **compile pair**.

Notes:

- A **compile pair** carries no `lifter` and no `solvers`. Its value is a new
  representation, certified to preserve meaning (`reproducible` or, rarely,
  `transparent`/proven). `gurdy/hops/c_riscv` (`C → RV64 ELF`) is the first
  one; today it lives as loose functions, not a registered unit (Stage 1
  fixes that).
- A **reasoning pair** is today's `Pair` (`riscv-btor2`): it adds a spec
  vocabulary, a `lifter`, `solvers`, and interpreters. Its terminal position
  in a chain is where transporting stops and solving begins.
- "Compile" is used in the broad sense of *meaning-preserving translation to a
  lower/other representation*, **not** "emits machine code." A
  `Lagrangian → equations-of-motion` pair (§4) is a compile pair even though
  nothing is "compiled" in the CS sense.
- The retired term **transport pair** (from the brainstorm) is folded into
  **compile pair**. Reserve "transport"/"lowering" only if a future need
  arises to distinguish a compile pair that *descends* the abstraction ladder
  from one that re-represents *sideways or upward* (a decompiler's `asm → C`
  is a compile pair that goes *up*).

## 4. The input side is **field-blind**

`L_in` is currently called the *source language*, a word that leaks
"program." The membership rule is weaker and field-blind:

> A language is admissible as `L_in` iff it has a **formal semantics** — a
> definable meaning function. Executability is **not** required; programming
> languages are one family among many. Equivalently (Appendix A of
> `DESIGN_generalized_pairs.md`): `L_in` qualifies iff it *is* an institution
> (signatures, sentences, models, satisfaction).

Recommended term: **input language** (plain), or **subject language** when
stressing "the thing under study." Non-program input languages, by field:

| Field | Input language | Its formal semantics | Becomes a… |
|---|---|---|---|
| **Mathematics** | group presentations, polynomial systems, OpenMath / Content-MathML, term-rewriting systems | a group / variety / typed math object | **compile pair** to a canonical form or Gröbner basis; **reasoning pair** to SMT/ATP |
| | Bayesian networks / probabilistic graphical models | a factorized joint distribution | **reasoning pair** via weighted model counting → #SAT (a real chain into logic) |
| **Physics** | a **Lagrangian / Hamiltonian** | equations of motion via Euler–Lagrange / Hamilton (a *variational* semantics) | **transparent compile pair** — `L → EOM` is byte-deterministic given the variational schema |
| | **Feynman diagrams** | an amplitude integrand via the Feynman rules | **compile pair** (diagram → integrand), deterministic and schema-predictable |
| | quantum circuits (OpenQASM, Quipper) | a unitary / superoperator | **compile pair** to a matrix; **reasoning pair** to SMT/QBF — or to the **ZX-calculus**, itself a sound-and-complete graphical *reasoning language* |
| | Modelica / Simulink / bond graphs | hybrid / DAE dynamics | **compile pair** to an ODE/DAE system |
| | dimensional analysis / units | an abelian group over base dimensions | a small **decision pair** — dimension-checking is a decision procedure |
| **Chemistry** | **SMILES / SMARTS / InChI** | a labeled molecular graph | **compile pair** (SMILES → canonical InChI is deterministic canonicalization) |
| | **chemical reaction networks (CRNs)** | mass-action ODEs *or* a stochastic CTMC (Turing-complete) | **compile pair** to ODE; **reasoning pair** to SMT/model-checking for reachability |
| | SBML (systems biology) | a reaction-network ODE / flux model | **compile pair** to dynamics; lifts to verification |

Two of these double as evidence the taxonomy survives leaving CS:

- **`Lagrangian → EOM`** is a textbook **transparent** compile pair: given
  the variational schema, an LLM can predict the output equations
  byte-for-byte — the `PAIRING.md` §5 predictability invariant, in physics.
- **`CRN → ODE → SMT`** is a three-language chain whose determinism composes
  exactly as `C → ELF → BTOR2` does, and a divergence localizes to a hop
  (mass-action lowering vs. SMT encoding) — `DESIGN_generalized_pairs.md` §6
  error-localization, in chemistry.

This also strengthens the hub thesis (`DESIGN_generalized_pairs.md` §7):
SMT-LIB and #SAT/WMC become interlingua hubs that probability, chemistry, and
physics all route into — not just program front-ends.

## 5. What counts as a "reasoning language" — narrow vs. broad

A **reasoning pair**'s output carries a *mechanized derivation/decision
procedure*. There are two defensible scopes; pick deliberately.

- **Narrow (ship first).** A reasoning language is a **logic in the
  mathematical-logic sense** with an SMT/ATP/SAT/model-checker behind it:
  BTOR2, SMT-LIB, TPTP, CHC/Horn, DIMACS, proof-assistant term languages.
  Field inputs reach it *via chains* (`CRN → SMT`, `PGM → #SAT`,
  `Lagrangian → EOM → SMT`).
- **Broad (open later, demand-driven).** Also admit non-logic reasoning
  targets that nonetheless carry a mechanized derivation relation: ODE
  solvers, computer-algebra (Gröbner bases), the ZX-calculus rewrite system.
  The institution framing (Appendix A) supports this — each is an institution
  with its own satisfaction/derivation relation.

Recommendation: **scope `L_out` narrowly for now** ("reasoning language in
mathematical logic"), but design the solver-adapter interface (`SolverBackend`)
so the broad reading is a later *additive* step, taken only when a concrete
chain (a CRN or quantum pair) demands it. Do not build the broad machinery
speculatively (`PAIRING.md` §15).

A useful sub-distinction inside reasoning pairs, when wanted:

- **decision pair** — `L_out` lands in a *decidable* fragment (QF-BV, SAT,
  QBF); a solver *decides*.
- **deductive pair** — `L_out` targets a prover/ATP (CHC, TPTP, Lean/Coq
  terms) where the procedure is semi-decision or proof search.

## 6. The two axes are orthogonal (the crucial clarification)

`DESIGN_generalized_pairs.md` §3 splits pairs into *transparent* vs.
*opaque-but-reproducible*. That is **a different axis** from this note's
compile-vs-reasoning split. They cross freely:

| | **transparent** (schema → bytes) | **reproducible** (pin → bytes) |
|---|---|---|
| **compile pair** | `Lagrangian → EOM`; `SMILES → InChI` | `c-riscv` (`C → RV64 ELF`, gcc-pinned) |
| **reasoning pair** | `riscv-btor2` (today's pair) | a future `C →(clang)→ SMT-LIB` macro-hop |

- The **output-kind** axis (this note) answers *"do you run it or solve it?"*
  and determines whether the pair has a `lifter` + `solvers`.
- The **predictability/tier** axis (`DESIGN_generalized_pairs.md` §4) answers
  *"can you foresee the bytes or only replay them?"* and determines the trust
  computation.

Conflating them is why "pair" felt overloaded. A pair has **one cell in this
2×2** (plus `checked`/`trusted` as further tier values on the second axis).

## 7. Determinism across chains — the key concept ("determinism composes")

Determinism is the property the whole fabric rests on, and it must be stated
at the **chain** level, not just per hop. The companion law to "soundness
composes — and localizes" (`DESIGN_generalized_pairs.md` §6) is:

> **Determinism composes.** A chain is deterministic iff every hop is. The
> chain's output is a deterministic function of its input *because* each hop's
> output hash is a deterministic function of its input hash — so the
> content-addressed cache (`PAIRING.md` §2,
> keyed `(spec_hash, source_hash, schema_version)`) **extends across hops for
> free.** The chain cache exists *only* because determinism composes; one
> nondeterministic hop collapses it.

Make the following first-class rather than implicit:

- **Per-hop vs. end-to-end determinism.** Per-hop is the existing determinism
  contract (`PAIRING.md` §8: byte-identical artifact for fixed inputs).
  End-to-end is its conjunction across the route, and a leak **localizes to
  one hop** (the same localization the alignment oracle gives for soundness).
- **Two flavors, both genuinely deterministic, differing in legibility.**
  `transparent` = determinism you can *predict* (schema → bytes);
  `reproducible` = determinism you can only *replay* (pin → bytes). A chain
  mixing them is deterministic but **predictable only up to its first opaque
  hop** — surface this explicitly; never let "deterministic" silently imply
  "predictable."
- **Cache-key composition (mechanism).** Define a hop's output hash as
  `f(in_hash, hop_id, hop_version, params)`; a chain's output hash is the fold
  of these. The per-pair recompile-and-diff check (`PAIRING.md` §8) lifts to a
  **chain-level `recompile_and_diff(chain, input)`** (`gurdy/core/chain.py`).

Why it matters operationally: caching, the alignment oracle, multi-path
cross-checking (`DESIGN_generalized_pairs.md` §6), and the LLM-predictability
probe (§2 there) **all break the instant one hop in a chain is
nondeterministic.** Determinism is the load-bearing wall, not a nicety.

## 8. Trust and preservation also compose

Two further chain-level computations, parallel to determinism:

- **Trust = the meet (weakest hop).** A chain's tier is the weakest hop's
  tier — *unless a verifier hop re-establishes it*
  (`DESIGN_generalized_pairs.md` §4). Now *computed* as `Route.trust`
  (Stage 4) over the assurance ranking **transparent > checked > reproducible >
  trusted** (`Tier.trust_rank`): transparent is schema-auditable, checked is
  validated against its input every run, reproducible assures only determinism,
  trusted assures nothing. Verifier-hop re-establishment is not yet modelled —
  the CBMC differential in `gurdy/hops/c_riscv/verify.py` is a `checked`-tier
  verifier hop in spirit; registering it as one (so a checked hop lifts a
  chain's trust) is the next step.
- **Loss = the union of discards.** *Landed (Stage 4):* each hop declares a
  **preservation contract** — `Preservation(keeps, discards, note)`, a
  generalization of the projection's observable set — and `Route.discards`
  computes a chain's total loss as the union of its hops' `discards`, making
  `DESIGN_generalized_pairs.md` §10's "lossiness compounds" explicit and
  inspectable (surfaced by `gurdy preservation`). Labels are free-form and
  pair-local: no shared cross-field ontology is imposed — the two declared
  fields (`riscv-btor2`/`c-riscv` and `smiles-formula`) use different
  vocabularies on purpose. `keeps` is reported per hop but not composed across
  hops, since that would need the shared vocabulary we avoid.

## 9. The consolidated lexicon

| Concept | Term | One-line gloss |
|---|---|---|
| the thing under study | **input language** (or **subject language**) | any language with a formal semantics — not just programs (§4) |
| a registered deterministic edge `L_in → L_out` | **translation pair** (genus) | replaces bare "pair" |
| species: `L_out` is a representation/execution target | **compile pair** | no `lifter`/`solvers`; value is a certified new representation |
| species: `L_out` is a reasoning language | **reasoning pair** | today's `Pair`; has `lifter` + `solvers` |
| reasoning pair into a decidable fragment | **decision pair** | QF-BV / SAT / QBF |
| reasoning pair into a prover/ATP | **deductive pair** | CHC / TPTP / Lean / Coq |
| a composition of pairs | **chain** | squares pasted on a shared edge (Appendix A) |
| the load-bearing property | **chain determinism** / "**determinism composes**" | deterministic iff every hop is; leaks localize (§7) |
| predictability axis (orthogonal) | **transparent / reproducible / checked / trusted** | the trust tiers (`DESIGN_generalized_pairs.md` §4) |

The shape to remember: **compile until you can land; a reasoning pair is
where you land; the whole journey is trustworthy only because determinism —
like soundness and trust — composes hop by hop.**

## 10. What this commits, and what it defers

**Commits (vocabulary + axes only):**

- "Translation pair" as genus; "compile pair" / "reasoning pair" as species,
  divided by the solver test (§3).
- "Input language" is field-blind; the §4 examples are illustrative, not a
  worklist.
- The output-kind axis is orthogonal to the predictability/tier axis (§6).
- "Determinism composes" as the named chain-level law (§7).

**Defers (to a concrete consumer, per `PAIRING.md` §15 and
`DESIGN_generalized_pairs.md`'s demand-driven discipline):**

- The narrow→broad widening of "reasoning language" (§5) — until a CRN or
  quantum chain needs it.
- The `preservation` contract's concrete *type* (§8) — **landed** (Stage 4),
  now that the second field (Stage 6) exists: `Preservation(keeps, discards,
  note)`, designed against both `riscv-btor2`/`c-riscv` and `smiles-formula`
  and declared on all three hops, with `Route.discards` composing a chain's
  loss. Free-form pair-local labels; no shared ontology imposed.
- Further `L_in`/`L_out` beyond the current graph
  (`{c, rv64-elf, btor2, smiles, molecular-formula}`) — the §4 table is a map
  of the territory, not a build plan. Each new pair must still earn its place
  (a reasoning pair with the irreducible-six, `PAIRING.md` §3, and a benchmark;
  a compile pair with a schema or a toolchain pin).

## 11. How the code grows into this (staging)

This note is the naming layer under `DESIGN_generalized_pairs.md` §11's
staged plan. Recap, with this taxonomy attached (✅ landed · ◑ partial · ◻ planned):

1. ✅ **Stage 1 — extract the genus** (`gurdy/core/hop.py`). A `Hop` type;
   `Pair` redefined as the *reasoning-pair* species of it; `c-riscv`
   registered as a *compile pair* in one unified registry. Every hop tagged
   with `in_lang`, `out_lang`, and `tier`.
2. ✅ **Stage 2 — `Language` registry + `routes(L_in, L_out)`**
   (`gurdy/core/language.py`, `gurdy/core/route.py`). The registry is now a
   graph; `routes()` enumerates simple-path chains (it enumerates, it does not
   choose); `gurdy languages` / `gurdy routes` expose it on the CLI. The §4
   field languages plug in here as cheap descriptors.
3. ✅ **Stage 3 — `Chain.run` over the graph** (`gurdy/core/chain.py`). The
   generic runner sequences a route's hops, threading output + per-hop
   provenance; `gurdy/chains/c_to_btor2.py` is now a thin wrapper that drives
   it. Per-hop translate signatures stay distinct (Stage 1); the runner adapts
   each behind `run(prev) -> StepOutcome`. Transitive *provenance* is generic;
   transitive *source-map* composition stays chain-specific until a second
   chain justifies it.
4. ✅ **Stage 4 — chain trust + determinism + preservation**
   (`gurdy/core/{hop,route}.py`). `tier` is a first-class `Hop` field
   (Stage 1); `Route.trust` (weakest-hop meet), `Route.is_deterministic`,
   `Route.predictable_prefix`, and a generic `recompile_and_diff` land
   (`gurdy routes`). With the second field in hand (Stage 6), the
   `preservation` contract also lands: `Preservation(keeps, discards, note)`
   is a `Hop` field declared on all three hops, `Route.discards` unions a
   chain's loss, and `gurdy preservation` surfaces it.
5. ✅ **Stage 5 — a generic, localizing chain alignment oracle in core**
   (`gurdy/core/interp/chain_align.py`). `align_chain` pastes per-hop
   alignment squares (reusing `align_traces`), localizing a divergence to
   (hop, step, label) and recording non-alignable opaque hops as *skipped*
   with a reason. `ChainResult.align()` wires the C→ELF→BTOR2 chain through it
   (one aligned square; the `c-riscv` compile hop skipped). Multi-square
   composition is exercised by synthetic tests; the first real multi-aligned
   chain arrives with Stage 6.
6. ✅ **Stage 6 — a non-CS field pair** (`gurdy/hops/smiles_formula/`):
   `smiles -> molecular-formula`, a *transparent* compile pair in chemistry.
   SMILES is a non-programming language with formal semantics (a molecular
   graph); the implicit-hydrogen + Hill-notation rules make its output
   schema-predictable. This is the second registered pair — the field-blindness
   witness `PAIRING.md` §15 asks for, and the second data point that unblocks
   the deferred `preservation` contract (it keeps the atom multiset, discards
   connectivity).

**RAM discipline (standing constraint).** A chain runner holds several large
artifacts live (ELF + BTOR2 + traces). `Chain.run` must process one instance
fully through the route then release; never materialize a whole corpus' hop
outputs at once; cap corpus parallelism.

**What not to do.** No O(k²) language matrix (hubs + routing); no hidden
adaptive IR (every hop stays a named, contracted edge — the
`DESIGN_generalized_pairs.md` §5 amendment); no growing `Language` into a full
institution implementation (keep it a descriptor); no promoting
`preservation` to a grand ontology until two fields agree.
