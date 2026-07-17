# Interface — the LLM-facing surface

This is how a **player** — an LLM, or a human — connects to and drives
hurdy-gurdy. The platform is mechanism; the player supplies the reasoning.
The interface is the player's *entire* contact surface, and it is built to
one rule:

> **The platform translates, interprets, carries back, cross-checks,
> decides, and checks — mechanically and deterministically. It never
> decides *what* to ask, *which* route to take, *which* solver to run, or
> *how much* fidelity to buy.** Those are the player's calls. The platform
> *enumerates* faithful, deterministic options and reports exactly what each
> result means; the player chooses and composes.

Everything below is pair- and route-**generic**: the same tools serve every
registered pair ([`pairs/`](./pairs/)) and every route through the registry
graph ([`ROUTES.md`](./ROUTES.md)). The pair or route is a parameter, not a
different API.

## 1. Shape and delivery

The surface is a small set of tools, delivered as an **MCP server**
(`gurdy mcp` — stdio JSON-RPC, zero dependencies, shipped) and mirrored
by a `gurdy` **CLI** (same operations, same names). The MCP surface is
the **use plane plus demand recording**, never the evolution plane
([`ARCHITECTURE.md`](./ARCHITECTURE.md) §0): no tool registers a pair,
touches a protected field, or reaches the ratchet — the graph never
grows through a session. Every tool:

- takes and returns **structured, content-addressed** values;
- is **deterministic** — same inputs → byte-identical output — **with the
  single exception of `decide`**, the solver oracle ([`SOLVERS.md`](./SOLVERS.md) §1);
- carries **provenance** on its result: the versions and pins involved, the
  declared **fidelity** of the route, and — for a checked answer — the
  trusted computing base.

Because results are content-addressed, re-asking an identical question is
cheap and returns identical bytes; the cache extends across a whole route
([`ROUTES.md`](./ROUTES.md) §2).

## 2. The tools

Three families. The middle family is exactly the edges of the commuting
square ([`ARCHITECTURE.md`](./ARCHITECTURE.md) §3); the last is the
reasoning contract ([`SOLVERS.md`](./SOLVERS.md)).

### A. Discovery (read-only)

| Tool | Returns |
|------|---------|
| `languages()` | registered languages, their formal-semantics reference, and the interpreters/solvers/checkers they own |
| `pairs()` | registered pairs: source→target, declared fidelity, direction, status |
| `routes(from, to)` | every route between two languages, each with its **composed** determinism, fidelity, direction, and loss, and whether it is part of a **branch**; endo-hops (abstraction pairs) enumerate **opt-in** ([`ROUTES.md`](./ROUTES.md)). The annotated form (`route_report`) adds, per route: weakest-link assurance, question **feasibility** (observables vs. the head projection, shape vs. the target's declared solver shapes), the **measured cost profile** from the host-local opt-in ledger (`GURDY_LEDGER`; `unmeasured` is the honest default), and **Pareto-dominance marks** (dominated routes are marked, never hidden; dominance only between fully measured routes). Advisory annotations only — the platform still never chooses |
| `describe(topic)` | spec-on-demand: a pair's translation specification, a language's semantics, a layer or observable. The surface that makes a `predicted` pair predictable |
| `solvers(language)` / `checkers(language)` | the reasoning inventories for a reasoning language |
| `why_not(source, observables, shape, verdict?, floor?, program?, origin?, suite?)` | the answerability diagnosis ([`POTENTIAL.md`](./POTENTIAL.md) §1–2 as a call, `gurdy why-not`): walks the **five obstacles** of [`POTENTIAL.md`](./POTENTIAL.md) §1 in order and returns the first failure as a machine-readable **demand record** naming the generation target (a missing pair, a wider projection on a named pair, a missing reasoning language, or a reduction), with a draft brief stub for pair-shaped targets. A question about a program already in a reasoning language carries its zero-hop **native route** (no translation debt). When the ledger is configured the demand is **recorded** (question verbatim, origin-tagged, suite-tagged when asked from a benchmark — [`FRONTIER.md`](./FRONTIER.md) §1.1) — the books behind `recommendations`. Advisory; **registration stays a human act** ([`AGENTS.md`](./AGENTS.md) §1) |
| `recommendations()` | the books' demand side aggregated per generation target (`gurdy recommendations`): distinct questions unlocked (dedup by question identity), the obstacle each target removes (the one demand taxonomy), per-origin counts (organic vs campaign, displayed apart), first/last seen. Sorted by evidence volume — volume is not a verdict; a brief cites the records behind its row and the human decides ([`AGENTS.md`](./AGENTS.md) §1) |
| `suggest_reduction(system, bads?)` | the abstraction dial's advisor for the BTOR2 hub (`gurdy suggest-reduction`; [`languages/btor2`](./languages/btor2/README.md)): the question's cone of influence, the **free havoc set** (zero precision loss — an executable, negative-controlled claim), the farthest-first refinement ladder for `btor2-havoc`, and observed interval seeds for `btor2-interval` (candidates its lax square corroborates or refutes). Advisory parameters only — passed to `translate(params)` by the player, or ignored |
| `trust_options(source, target, floor?)` | the trust view (`gurdy trust-options`; pure and read-only — `why_not` owns the demand recording): per-route assurance, **branch independence** over the pairs' declared `semantic_artifact`s with the shared suffix removed (a shared artifact is never independent; undeclared is *unknown*, never silently independent), the anchor census, and — when the floor is unmet — the honest option set: run an existing independent branch, generate a route from a **new** artifact, or **saturation** (further same-anchor routes add count, not trust — [`POTENTIAL.md`](./POTENTIAL.md) §5). Advisory; grades stay declared and protected |

### B. The square (operate a pair or a whole route)

`route` is a single pair or a route; the platform threads provenance and the
composed target-to-source mapping along a route so answers land at the
*original* source.

| Tool | Square edge | Does |
|------|-------------|------|
| `translate(route, source, params)` | `T` | source program → target artifact (+ annotation + provenance). Deterministic. |
| `interpret_source(route, binding)` | `I_s` | run the source on a concrete binding → source trace |
| `interpret_target(artifact, binding)` | `I_t` | step the target on a concrete binding → target trace |
| `carry_back(artifact, witness)` | `L` | carry a target witness or trace back to a source-level behavior |
| `cross_check(route, binding)` | `≡_π` | does the square commute on the declared observables? (A directional hop is checked along its witness embedding — [`ARCHITECTURE.md`](./ARCHITECTURE.md) §3.) Localizes a divergence to a step and an observable. For a branch, compares the two routes' results. |

### C. Reasoning (reasoning-language targets only)

| Tool | Role | Does |
|------|------|------|
| `decide(artifact, directive)` | solver (oracle) | decide a question over *all* inputs → `Result{verdict, model?, certificate?, provenance}` ([`SOLVERS.md`](./SOLVERS.md) §3). The one non-deterministic tool. |
| `check_witness(claim, witness)` | checker | independently re-validate a witness/certificate → `valid | invalid | unsupported`, with the TCB ([`SOLVERS.md`](./SOLVERS.md) §5) |

A solver's `model` is an **input binding**, not a trusted trace: feed it to
`interpret_target` to regrow the trace and to `carry_back` to ground it at
the source — that replay *is* the positive-side witness check
([`SOLVERS.md`](./SOLVERS.md) §4).

## 3. What the player composes (and the platform does not)

The tools are primitives. These patterns live entirely in the player's
logic — the platform supplies no policy for any of them:

- **Route / branch choice.** `routes(...)` reports the options and their
  composed fidelity; the player decides which to run, and whether to spend a
  branch's extra cost for cross-checked corroboration ([`ROUTES.md`](./ROUTES.md) §4).
- **Portfolios.** Calling `decide` with several engines and comparing is a
  player-built portfolio; the platform never races solvers.
- **CEGAR / refinement.** Re-`translate` with refined `params` or a tighter
  `directive` in a loop the player drives.
- **Proof-carrying answers.** After an `unreachable`/`unsat` verdict, request
  the certificate and `check_witness` it; choose the checker pedigree (and
  thus the `proved` strength / TCB) the question warrants.
- **Fact transfer.** Carrying a fact learned on one route to another along a
  shared language is the player's move, made meaningful by the route graph.

Mirror of [`README.md`](./README.md) "Using hurdy-gurdy": no
deciding what to verify, no solver/budget choice, no automatic refinement,
no portfolio racing, no cross-question fact validation — and the advisory
reads (§2A) do not change this: they annotate, diagnose, and account;
choosing remains the player's, and registering remains the human's.

## 4. A question, end to end

A question is a `(route, source, params, directive)`. A representative loop
over `C → RISC-V → BTOR2 → SMT-LIB` ([`REGISTRY.md`](./REGISTRY.md)):

1. **Discover.** `routes("c", "smtlib")` → the route above, plus the Sail
   branch reaching BTOR2; note their composed fidelity (a `reproducible`
   compiler head, re-established downstream).
2. **Translate.** `translate(route, c_source, params)` → the SMT-LIB
   artifact, with provenance for every hop and a composed map back to C
   `file:line`.
3. **Decide.** `decide(artifact, directive)` → a verdict.
4. **On `reachable`:** `carry_back(artifact, model)` (via
   `interpret_target`) → a concrete execution grounded at the **C source
   line**; `cross_check` confirms the route didn't misrepresent the program.
5. **On `unreachable`:** request the certificate and `check_witness` it with
   an independent checker → a `proved` answer with a stated TCB.
6. **Corroborate (optional).** Run the **branch** (`riscv-sail` →
   `sail-btor2`) and the **native vs. bridged** decision, and require
   agreement — the three cross-check layers of [`SOLVERS.md`](./SOLVERS.md) §7.

Every step is deterministic except `decide`, and every result says exactly
what it means — which is the whole point of the surface.

## 5. Honest limits, surfaced not hidden

`unknown`, `resource-out` (a solver gave up or hit a budget), and
`unsupported` (no checker for a witness kind) are **first-class results**,
returned with provenance — never swallowed or papered over. A divergence
from `cross_check` is reported at a step and an observable. The interface's
job is to tell the player the truth about each outcome, including when the
truth is "I don't know."
