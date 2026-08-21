# Potential — what owning every implementation is actually worth

The founding argument for generating everything was trust: what is
ours can be gated. That argument undersells the position. The deeper
observation is this: **in a pipeline of existing tools, every tool
boundary is simultaneously a trust boundary and an information
boundary, and nobody gets to choose where any of them go.** At each
handoff the artifact must be believed (trust), everything the tool
knew that the interchange format cannot say is lost (information),
and optimization stops at the box's wall (performance). Implementing
everything ourselves decouples the three: trust boundaries sit only
at judges, information flows end to end, and optimization crosses
every seam. The channels of [`KERNEL.md`](./KERNEL.md) are the
machinery of that decoupling; everything below is a corollary,
ordered roughly by how far it reaches.

## 1. Tools become measuring instruments

A solver we generate can emit *any observable of its own search* as
trust-inert profiling — the ledger's pilot already collected exact
witness counts from a BDD search as a free by-product, something no
wrapped engine can be asked for. Three escalations:

- **Blame maps.** Conflict statistics, hardest clauses, and budget
  attribution inside the solver can be pulled *backwards through the
  correspondence* to the source line that caused them, because the
  translator keeps the correspondence instead of discarding it at a
  format boundary. "This question is open because of this loop" is a
  sentence no pipeline of black boxes can utter; here it rides the
  same `Λ` machinery evidence already rides.
- **Counterfactual profiling.** Every heuristic is ours, so the same
  search can be rerun with one decision toggled and the cost
  attributed to the design choice — controlled experiments on the
  reasoning process itself. Existing tools expose a flag surface;
  ours expose their entire source as the experimental variable.
- **Stipulation sensitivity.** Semantics is also ours, so judges can
  be rerun under a deliberately mutated semantics — the gate's mutant
  discipline pointed at science instead of admission — asking whether
  a safety proof survives a change to, say, the shift-saturation
  rule. How much a verdict depends on contested corners of a language
  specification becomes a measured quantity. This requires owning the
  interpreter; no fixed tool can offer it.

## 2. Tools become conjectures

With wrapped engines, the player's repertoire is invocation
selection. With generated engines, a tool is a falsifiable,
improvable, replaceable object inside the loop: the registry is a
population under measurable fitness — the ledger — with trust held
invariant by the gate. Two consequences:

- **Open-ended repertoire.** An abstraction-refinement loop, a
  decision procedure for the one arithmetic pattern blocking a
  family, a domain-specific static analysis: each is a
  generation-plus-gate afternoon, not a tool-integration project. The
  set of available reasoning styles is bounded by what can be judged,
  not by what has been packaged.
- **The strategic bet, stated plainly.** The skeptic asks whether
  generated solvers can beat decades of tuning. Not at CDCL, on its
  own terrain, soon — and that is the wrong frame. The moat around
  existing tools is engineering effort, and LLM generation is
  precisely a machine for converting published ideas into engineering
  effort: the system imports ideas, never binaries, and every
  algorithm in the literature is a regeneration target. The design is
  long on implementation becoming cheap and short on trust by
  reputation; as the implementation-cost curve collapses, the
  bottleneck moves to judging, which is exactly what the kernel
  industrializes. The performance claim shifts accordingly, from the
  component to the pipeline: end-to-end bits per second on a corpus,
  where the cross-boundary moves of §3 are available here and
  structurally unavailable to any chain of black boxes.

## 3. Boundaries become optimization seams

- **Promises over `hint`.** The translator knows things — this state
  is the program counter, these inputs are one-hot, this machine
  encodes a CFG — that interchange formats cannot say and a wrapped
  solver could not safely believe. Here a promise rides the `hint`
  channel, the search exploits it, and a wrong promise costs
  performance, never soundness, because evidence still faces judges
  on arrival. Whole-toolchain co-design at zero trust cost: elsewhere
  exploiting producer structure means trusting the producer; the
  arrival checks make structure free to exploit.
- **The Futamura ladder.** Per-program specialization is already
  lawful; push it. The C interpreter specialized on a program *is*
  that program compiled (first projection); specializing the
  specializer on the interpreter yields a compiler (second
  projection). The C→RISC-V leg of the first campaign can be
  *derived from the C interpreter* rather than written fresh — the
  translator generated out of the very artifact that will judge it,
  with the square still checked per program, so no new trust enters.
  Interpreters as the single semantic source from which translators,
  compilers, and abstract interpreters (abstract the transfer
  functions; direction `over`) are systematically derived is a
  research program in itself, and it is only coherent because
  everything is source in one language.
- **Cross-question amortization.** Wrapped solvers restart from zero
  every invocation. Uniform evidence schemas make certificates a
  shared currency: an IC3 invariant strengthens a k-induction
  elsewhere; a fact proved once about a machine joins a lemma library
  re-discharged — check time, not search time — wherever it applies;
  search state cached across the questions sharing one machine rides
  as a hint. Incrementality at the level of the map, not the process.
- **Fixing the ledger's own first finding.** The pilot's honest
  weakness was the instrument: a simulator near forty samples per
  second caps every surprisal bound at twelve to sixteen bits. Own
  the sampler and the fix is the accelerator seam: a RISC-V
  interpreter accelerated to native speed is simultaneously
  *reasoning directly on executable code* and a sampler at a hundred
  million steps per second — surprisal bounds that bite at thirty or
  forty bits, on every play, for free. The instrument improves
  through exactly the seam the constitution already licenses.

## 4. Semantics becomes writable — and printable

Fragment-exactness inverts the usual completeness economics: existing
tools must implement full standards and then quietly disagree about
them — verdicts that differ because the tools embody different C's.
Our interpreter *is* the semantics: stipulated, printable, a few
hundred lines, grown demand-driven with each growth gated. A dispute
about what a program means becomes a diff against a short reference,
not archaeology in a solver's internals. Beyond exactness,
writability opens moves fixed tools cannot make: nonstandard
interpreters — abstract, symbolic, interval, taint — enter as
languages whose soundness polarity is the pair's direction; and
product languages (code and model in lock-step, divergence as
refusal) remain the deepest use, possible only when both interpreters
are ours to compose.

## 5. The trusted base becomes an object of science

Judges are a printable list, so the base itself can be improved with
the platform's own methods: independently generated interpreters for
one language cross-checked — corroboration applied to the base;
judge minimization as the standing honesty metric; the kernel's Lean
obligations as the endgame. The terminal state is worth naming: the
complete trust story of a verification result — judges, kernel,
anchors — fits in a paper's appendix and is auditable by one person
in one afternoon, and every result re-derives bit-identically a
decade later because nothing depends on a binary, a license, or a
version. No wrapped stack, however excellent, can make either claim.

## 6. What is given up, and the resolution

Two things, honestly. **Semantic archaeology**: floating point, the
ISO C corner cases, weak memory — domains where the hard artifact is
the semantics itself and existing tools embody person-centuries of
excavation. And the **raw search gap** on deep, unstructured
instances, which the ledger will report without mercy; the response
is to fight where structure and specialization dominate, not to
pretend. The resolution for both is the rule now in KERNEL.md §6:
**oracles, not organs**. Existing tools may testify from outside at
admission time — an oracle's output enters as anchors with recorded
provenance, corroborating a judge the way a benchmark label does —
and never enter the trusted base, never run inside a play. The fifth
generation's spine set the precedent with the compiler that never
entered; the rule inherits the world's hard-won semantics as
testimony at the gate, never as organs in the body.

## 7. The campaign order this suggests

Nothing above needs new constitution — that is the test that the
design is right. For the first campaign (C, RISC-V, BTOR2):

1. **RISC-V interpreter early, accelerated immediately** — execution
   engine, fast sampler, and ledger instrument in one artifact.
2. **C→RISC-V attempted as a derived translator** (Futamura on the C
   interpreter), a hand-generated one as fallback; compiler hops with
   `keeps = {bad}` lawful from the start.
3. **Translator promises over `hint` into the BMC search** — the
   first co-design experiment, measured in the ledger's currency.
4. **Blame maps** as the first new instrument once
   correspondence-carrying pairs exist.

Each is an ordinary registry entry through the ordinary gate — which
is the whole point.
