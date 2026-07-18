# Solvers and witness verification

Some target languages are **reasoning languages**: a mechanized decision
procedure consumes them directly (BTOR2 model checkers, SMT solvers). A
pair into such a language can do more than *run a model* — it can ask
whether a `bad` is reachable for **any** input, or whether a property holds
for **all** inputs. This document is the shared contract for that extra
capability: how reasoning languages **decide** questions and how those
decisions are **verified**.

It complements [`ARCHITECTURE.md`](./ARCHITECTURE.md) (the single-pair
model) and [`ROUTES.md`](./ROUTES.md) (composition). Like an interpreter, the
machinery here is **owned by a language and shared by every pair that
targets it** — it is not a per-pair component.

## 1. Three roles, two sides of the determinism line

A reasoning language carries three distinct executors. Keeping them
separate is the whole point of this document.

| Role | Question | Output | Determinism |
|------|----------|--------|-------------|
| **interpreter** `I_t` | run *this one* model | a trace | **deterministic** (meaning-preserving core) |
| **solver** | is there *any* model? does it hold for *all*? | a verdict, maybe a witness, maybe a certificate | **oracle — not** internally deterministic |
| **witness checker** | is this claimed witness/proof actually valid? | valid / invalid / unsupported | **deterministic** (and ideally *verified*) |

The line through the middle is the key architectural commitment:

> **Producers are the quarantined oracle; interpreters and checkers are the
> deterministic, pinned core.** A solver is the one component the platform
> admits may be non-deterministic. Nothing it says is believed until the
> deterministic core — the interpreter (for a model) or an independent
> checker (for a proof) — re-validates it.

This is how reasoning languages live inside the determinism invariant of
[`ARCHITECTURE.md`](./ARCHITECTURE.md) §4 without pretending a solver's
internal search is reproducible.

## 2. Ownership and sharing

Solvers and checkers attach to the **language**, exactly as interpreters do
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §6):

- A reasoning language registers a **solver inventory** and a **checker
  inventory** under `languages/<language>/`. `languages/btor2/` owns the
  BTOR2 model checkers and their certificate checkers; `languages/smtlib/`
  owns the SMT solvers and their proof checkers.
- **Shared by every pair that targets the language.** `riscv-btor2` and
  `sail-btor2` dispatch to the *same* BTOR2 solver inventory; they ship no
  private adapters.
- **First touch wires it; later touches reuse it.** The first pair into a
  reasoning language contributes its solver and checker inventories;
  subsequent pairs import them.
- **A shared inventory is a shared contract.** Adding, removing, or
  re-pinning a solver or checker is a versioned event that re-validates
  every dependent pair's results, never a quiet per-pair edit
  ([`AGENTS.md`](./AGENTS.md) §3).
- **Growth is designed, not ad hoc.** How the books come to *demand* a
  missing engine, and the admission gate a candidate — including a
  synthesized one — must clear before an inventory believes it, is
  [`SYNTHESIS.md`](./SYNTHESIS.md).

### 2.1 The solver brief

An engine enters an inventory the way a pair enters the registry:
through a one-page contract a human stands behind
([`AGENTS.md`](./AGENTS.md) §1, extended to solvers). A **solver
brief** ([`gurdy/solvers/brief.py`](./gurdy/solvers/brief.py))
declares:

- the **language** it attaches to and the **shapes** it decides —
  tokens of the §9 taxonomy, honest against the atlas;
- the **budget schema** — declared limits, never an undeclared
  hardcoded timeout;
- the **certificate obligation**, per shape × verdict: the witness
  kind emitted and the deterministic-side checker that re-validates
  it (§5) — or the explicit `uncheckable`, which caps that claim's
  contribution at corroboration (`checked`), never certification
  (`proved`). Every declared shape carries a stated obligation: the
  silent `unsupported` escape hatch is closed.
- the **lineage** — the codebase ancestry, the unit of independence
  accounting. Corroboration counts only agreement across *disjoint
  declared lineages* (`solvers/proved.py`): boolector and bitwuzla
  agreeing is one codebase family, honestly `reproducible`, never
  `checked`. A synthesized engine's lineage includes the reference
  semantics and any solver corpus it was synthesized from — a
  teacher and its student can never corroborate each other.
- the **intended design**, in a sentence — the human's field.

The registered briefs cover every shipped engine, retroactively under
the contract they always implicitly had; amending the table is a
versioned admission event (§2), and a *candidate* engine's brief is
recommended by the `native-procedure` demand that cites it
([`SYNTHESIS.md`](./SYNTHESIS.md) §3) and admitted through the solver
gate ([`tools/solver_gate.py`](./tools/solver_gate.py),
[`SYNTHESIS.md`](./SYNTHESIS.md) §5).

## 3. The `SolverBackend` contract (produce)

One thin, uniform protocol across BTOR2 model checkers and SMT solvers, so
the player sees a single shape regardless of engine:

```text
decide(artifact, directive) -> Result

  directive : { engine,            # which registered solver
                bound,             # unrolling depth k, where applicable
                limits,            # wall-time, memory (always set)
                seed }             # for reproducible pinning

  Result    : { verdict,
                model?,            # present on reachable/sat
                certificate?,      # present when the engine emits one
                provenance }

  verdict   ∈ { reachable,        # sat — a model exists
                unreachable,      # unsat / holds-for-all
                unknown,          # gave up (incompleteness)
                resource-out }    # hit a time/memory limit

  model     : a concrete INPUT BINDING — not a full trace (see §4)
  certificate : a re-checkable proof object (see §5)
  provenance  : { solver id, version digest, flags, seed, limits, stats }
```

Rules:

- **Thin adapters.** A backend pins its binary **by digest**, enforces the
  time/memory limits, and normalizes output into `Result`. It reimplements
  nothing.
- **Enumerate, don't choose.** The framework lists the registered solvers
  for a language and dispatches the one `directive.engine` names. It does
  **not** pick the engine, set the budget, or race a portfolio — the player
  does, exactly as it chooses a route ([`ROUTES.md`](./ROUTES.md) §6). Running
  several engines and comparing is a player-composed cross-check (§7).
- **`unknown` and `resource-out` are first-class verdicts**, not errors.
  Decidability and budgets are real; the player decides what to do with
  them.
- **Provenance is mandatory.** A verdict is only as reproducible as the pin
  recorded with it.

## 4. Witnesses seed the deterministic core — they don't bypass it

A solver returns a `model` that is a **concrete input binding**, never a
trusted trace. The deterministic core regrows and validates the rest:

```text
solver.decide ─▶ model (a binding)
                   │
                   ▼
        I_t replays it  ─▶ target trace ─▶ L lifts ─▶ source behavior ─▶ check π
        (deterministic)                    (pair-owned)                  (the square)
```

So a `reachable` answer is believed **only after** the deterministic
interpreter reproduces it and the pair's projection `π`
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §3) holds. The solver's internal
non-determinism cannot affect soundness: it only *proposes* the binding;
the deterministic core *disposes*. (For BTOR2 this replay is a
`btorsim`-style simulation of the solver's `.wit` witness — and that
simulator simply **is** the shared BTOR2 interpreter `I_t`.)

This is the crucial economy: **positive-side witness verification is
already the commuting square's replay-and-project check.** No new machinery
is needed to validate a counterexample — only to validate a *proof* (§5).

The same replay carries one extra meaning on a route with a
**directional** hop ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §3): there a
`reachable` may be an artifact of the over-approximation, and the replay is
what tells — success certifies it at the source exactly as above, while a
replay *failure* is a **spurious counterexample**, the player's signal to
refine the abstraction rather than a soundness bug. `unreachable` verdicts
transfer across `over` hops on the strength of the direction alone
([`ROUTES.md`](./ROUTES.md) §3).

## 5. The `WitnessChecker` contract (verify)

A witness or certificate is only as trustworthy as the **independent**
checker that re-validates it. The checker is a shared language capability,
distinct from the producing solver:

```text
check(claim, witness) -> { result,        # valid | invalid | unsupported
                           checker_provenance,
                           tcb }           # the trusted computing base (§6)
```

It dispatches by witness kind:

| Verdict it backs | Witness / certificate | How `check` validates it |
|---|---|---|
| `reachable` | a model / `.wit` trace | **re-execute** it: §4 replay through `I_t` + `L`, check `π`. Deterministic, cheap, **always available.** |
| `unreachable` (transition systems) | an **inductive invariant** | re-discharge `init ⇒ I`, `I ∧ trans ⇒ I'`, `I ⇒ ¬bad` — three queries to a **different** registered `SolverBackend`. |
| `unreachable` (bounded / k) | a **k-induction certificate** | re-discharge BASE + STEP on an independent engine. |
| `unsat` (bit-blasted) | a **DRAT / LRAT** proof | a dedicated, ideally *verified*, proof checker. |
| `unsat` (SMT) | an **Alethe / LFSC** proof | the corresponding proof checker / proof-assistant reconstruction. |

Two consequences worth stating outright:

- **Most checking reuses what already exists.** Model validation reuses the
  interpreter; invariant / k-induction re-checking reuses the
  `SolverBackend` interface with a *different* engine. Only the dedicated
  proof-format checkers (drat-trim / lrat-check / `cake_lpr`; Carcara /
  LFSC) are genuinely new — thin, pinned adapters.
- **Independence is the whole value.** A checker must be a *different
  codebase* from the producing solver (z3 produces, cvc5/Carcara checks;
  one model checker produces an invariant, another engine re-discharges it).
  A solver that "checks itself" verifies nothing.

Checkers, unlike solvers, live on the **deterministic side**: their
verdict (valid/invalid) must be reproducible and the binary pinned. The
strongest checkers are themselves *formally verified* (e.g. `cake_lpr`), or
are a proof-assistant kernel.

## 6. Fidelity, and the trusted computing base

Solvers and checkers map directly onto the fidelity tiers of
[`ARCHITECTURE.md`](./ARCHITECTURE.md) §7:

| Evidence | Fidelity of the answer |
|---|---|
| one pinned solver, verdict recorded with provenance | `reproducible` |
| ≥2 independent solvers (or native-vs-bridged, §7) agree | `checked` |
| the witness is re-validated by an **independent checker** (§5) | `proved` |

`proved` is **not a single point** — its strength is the checker's
pedigree, and every `proved` result must record its **trusted computing
base**:

```text
   re-checked by an        verified checker          reconstructed in a
   independent solver  <   (e.g. cake_lpr)      <    proof-assistant kernel
   TCB = {that solver,     TCB = {verified         TCB = {kernel,
          replay I_t,             checker,                 replay I_t,
          parser}                 replay I_t, parser}      parser}
```

State which one you did. Do not let `proved` drift from "an independent
solver agreed" up to "a kernel checked it" — they are different TCBs and
different claims.

## 7. Three layers of cross-check

Corroboration stacks at three points along a route, each localizing a defect
to a narrower place:

1. **Translate-step branch** — two routes to the same target
   (`riscv-btor2` vs `riscv-sail` → `sail-btor2`) cross-checked
   ([`ROUTES.md`](./ROUTES.md) §4). A mismatch is a *translator* bug.
2. **Solve-step branch** — the same artifact decided two ways: a **native**
   BTOR2 model checker vs **bridged** through `btor2-smtlib` to an SMT
   solver. Verdicts must agree; a mismatch is a *translator-or-solver* bug.
   This is the general form of the `btor2-smtlib` "native vs bridged"
   check. For the bounded-unreachable half, `NativeBtor2Checker.decide_bounded`
   reads btormc's clean `-kmax` exhaustion (exit 0, empty output — guarded so
   a parse error can never read as unreachable, and — because the signal is
   silence — trusted only from a binary that first answers `sat` on a
   trivially reachable canary, the §5 negative-control rule applied to an
   exhaustion signal) as "no counterexample within
   k", the same bounded claim the bridge's `unsat` makes; combined with a
   translate-step branch this yields a corroborating pair whose stacks are
   fully disjoint after the head (the paper's disjoint-decision block).
3. **Proof-step check** — the surviving verdict's witness re-validated by an
   independent checker (§5). A failure means the *solver lied*.

A high-confidence answer is one corroborated at all three: reached by two
translations, decided by two engines, and carrying a re-checked proof.

## 8. What the framework provides vs. what a pair declares

**Framework / language layer provides** this document's machinery as
framework capability — protocols, shared inventories, pinning and
limits, the normalized `Result`, the dispatch surface. The single
source is [`FRAMEWORK.md`](./FRAMEWORK.md) §2.

**A reasoning pair declares** ([`PAIRING.md`](./PAIRING.md)): which shared
solvers it dispatches to; the **model/witness shape** its target-to-source
interpreter `L` consumes (§4); the **certificate kinds** it can emit and
which shared checker validates each; and — for any `proved` claim — the
**checker and TCB** behind it (§6). It implements no solver or checker of
its own beyond what the language shares.

## 9. Question shapes

A **shape** is the logical form of a question's condition `φ` together
with its asking mode — the coordinate the shape obstacle checks
([`POTENTIAL.md`](./POTENTIAL.md) §1; `why_not` obstacle 3). Shapes are
declared per reasoning language as `question_shapes` on the registry's
`Language` ([`gurdy/core/registry.py`](./gurdy/core/registry.py)) and
matched by exact token: the route report and `why_not` compare `φ`'s
shape string against the destination's declared tuple. A language that
declares nothing reads **undeclared** — unknown, never false.

The declared vocabulary, today:

| token | mode | the claim | discharged by | checked by |
|-------|------|-----------|---------------|------------|
| `reachability` | existential | some input reaches `φ` | `reachable` + witness (native); `sat` + model (SMT) | witness replay through `I_t` (§4); model evaluation, then source replay |
| `bounded-unreachability` | universal, within the declared bound `k` | no input reaches `φ` within `k` | clean `-kmax` exhaustion, canary-controlled (native, §7); `unsat` (bridged) | `corroborate_unreach` replay (§5); multi-engine corroboration and the certificate chain (§5–6) |

Four rules keep the vocabulary honest:

1. **A declaration is a claim with obligations.** Declaring a token
   asserts that the language's shared solver inventory decides that
   shape — and, per verdict, names the witness kind and the shared
   checker that validates it (§5). A shape×verdict combination with no
   checker must be declared uncheckable, and caps the assurance an
   answer through it can carry ([`SYNTHESIS.md`](./SYNTHESIS.md) §4).
2. **Tokens are one shared vocabulary.** The same string makes the
   same claim on every language. The authoritative chart of tokens
   beyond the declared ones is the fragment atlas
   ([`gurdy/core/atlas.py`](./gurdy/core/atlas.py)): per shape, the
   setting in which it is decidable, the native procedure family, and
   the known crossing into a shape an existing hub already decides.
   A shape the atlas does not know reads `uncharted`, never a guess.
3. **Adding a token is a versioned admission event** (§2's shared
   contract): it widens answerability at obstacle 3 for every pair
   into the language, and it rides the ratchet — never a quiet edit.
4. **Undeclared is not undecidable.** A blocked shape lands on the
   books located by the atlas, and most close by a known crossing —
   an endo-pair on an existing hub (liveness-to-safety,
   self-composition, monitor weaving; [`POTENTIAL.md`](./POTENTIAL.md)
   §4) — before any new procedure is worth designing
   ([`SYNTHESIS.md`](./SYNTHESIS.md) §3).

## 10. Current inventories

Authoritative lists live in the language briefs; summarized here.

- **BTOR2** ([`languages/btor2`](./languages/btor2/README.md)) —
  *solvers:* BtorMC, Pono (reachability / k-induction; AVR is a named
  future layer);
  *witnesses:* BTOR2 `.wit` (validated by `I_t` replay), inductive
  invariants, k-induction certificates;
  *checkers:* `I_t` replay (`.wit` on the reachable side;
  `corroborate_unreach` — full-bound replay, sampled inputs — as the
  bounded-unreachable corroboration), independent-engine re-discharge,
  `certifaiger`-style certificate checking.
- **SMT-LIB** ([`languages/smtlib`](./languages/smtlib/README.md), scope
  `QF_ABV` / `QF_BV` / `QF_LIA`) —
  *solvers:* Z3, Bitwuzla, Boolector, cvc5, Yices2;
  *witnesses:* models (validated by evaluation), Alethe / LFSC proofs,
  DRAT/LRAT for bit-blasted unsat;
  *checkers:* model evaluation, Carcara (Alethe), LFSC, `cake_lpr`
  (verified LRAT), optional proof-assistant reconstruction.

See [`REGISTRY.md`](./REGISTRY.md) for the per-language solver/checker
tables.
