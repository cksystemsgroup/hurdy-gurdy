# Pairs

A **pair** is one registered edge `source → target` and the four
deterministic functions that realize it
([`ARCHITECTURE.md`](../ARCHITECTURE.md) §2). Each subdirectory here is one
pair's **registration brief** — the one-page specification a human writes
to trigger that pair's independent agent ([`AGENTS.md`](../AGENTS.md) §1),
and which the agent then fills out into the pair's full specification while
implementing it to the [`PAIRING.md`](../PAIRING.md) contract.

A pair's id is kebab-case `<source>-<target>` and is also its directory
name (`pairs/riscv-btor2/`).

## Brief template

Every brief states:

1. **Languages.** Source and target (both in [`languages/`](../languages/)
   or introduced here).
2. **Translator.** What `T` is — a pinned tool, a spec-derived mapping, a
   model-derived lowering — and what it deterministically produces.
3. **Source / target interpreters.** Which **shared** interpreters
   ([`languages/`](../languages/)) it reuses, and which it must
   **contribute** (the first pair over a language builds that language's
   interpreter).
4. **Target-to-source interpreter.** What `L` carries back (a solver
   witness, a target trace) and to what source-level behavior — the one
   interpreter-shaped component the pair owns.
5. **Projection `π`.** The observables agreement is checked on — the
   precise meaning of "faithful" for this pair.
6. **Fidelity target + evidence.** The tier to reach
   ([`ARCHITECTURE.md`](../ARCHITECTURE.md) §7) and the artifact that will
   establish it.
7. **Soundness story.** How the commuting square is shown to hold
   ([`PAIRING.md`](../PAIRING.md) §6).
8. **Status.** *registered* → *built*, plus blockers and lessons.

## The registered pairs

| Pair | Source → Target | Status |
|------|-----------------|--------|
| [`c-riscv`](./c-riscv/README.md)         | C → RISC-V      | registered |
| [`riscv-btor2`](./riscv-btor2/README.md) | RISC-V → BTOR2  | registered |
| [`btor2-smtlib`](./btor2-smtlib/README.md)| BTOR2 → SMT-LIB | registered |
| [`riscv-sail`](./riscv-sail/README.md)   | RISC-V → SAIL   | registered |
| [`sail-btor2`](./sail-btor2/README.md)   | SAIL → BTOR2    | registered |

The paths these induce — including the RISC-V→BTOR2 branch — are in
[`REGISTRY.md`](../REGISTRY.md) and [`PATHS.md`](../PATHS.md).
