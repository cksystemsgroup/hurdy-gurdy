# Languages

A **language** is admissible in hurdy-gurdy iff it carries a **formal
semantics** — a definable meaning function over its programs
([`ARCHITECTURE.md`](../ARCHITECTURE.md) §1). Each registered language has
a brief here that records two things:

1. **Its formal semantics** — the authoritative source of truth for what
   the language *means* (a standard, a specification, a model). Every pair
   over the language is judged against this, not against any
   implementation.
2. **Its shared interpreter contract** — the deterministic executor that
   produces a *behavior* (a trace of post-step observable states), written
   **once** and reused by **every** pair that touches the language
   ([`ARCHITECTURE.md`](../ARCHITECTURE.md) §§5–6).

A language interpreter follows the conventions in
[`ARCHITECTURE.md`](../ARCHITECTURE.md) §5: post-step state, named
projectable observables, and strict determinism. It is owned by the
language; a change to it is a versioned event that re-validates every
dependent pair ([`AGENTS.md`](../AGENTS.md) §3).

> Note. The *target-to-source* interpreter is **not** here — it is
> pair-specific and lives with the pair ([`pairs/`](../pairs/)), because
> the correspondence it encodes is particular to one source→target
> combination.

Registered languages: [`c`](./c/README.md), [`riscv`](./riscv/README.md),
[`aarch64`](./aarch64/README.md), [`wasm`](./wasm/README.md),
[`ebpf`](./ebpf/README.md), [`evm`](./evm/README.md),
[`btor2`](./btor2/README.md), [`smtlib`](./smtlib/README.md),
[`sail`](./sail/README.md), [`crn`](./crn/README.md),
[`smiles`](./smiles/README.md),
[`molecular-formula`](./molecular-formula/README.md),
[`python`](./python/README.md). The sharing graph and the formal model
behind each source language are in [`REGISTRY.md`](../REGISTRY.md).
