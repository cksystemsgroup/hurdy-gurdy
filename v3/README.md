# hurdy-gurdy v3 — registry architecture (skeleton)

A clean-slate factoring of hurdy-gurdy as a **self-extending library of
verified translation pairs**, where humans declare *what* (register a
pair), autonomous LLM agents supply *how* (implement it on a branch), and
a formal-semantics-backed gate decides *whether* it is correct enough to
merge.

> **Status: skeleton (depth-i).** The architecture machinery, manifests,
> gate orchestration, route enumeration, and agent orchestrator are real
> and runnable end-to-end on the **F0 (typed) gate**. The semantic
> heavy-lifting — the actual translations, the Sail integration, the
> LLM-generated BTOR2 machine model, and the F1–F3 proofs — are typed
> **stubs** marked `TODO(agent)`, to be filled by the autonomous agents
> the orchestrator spawns. Nothing here imports or modifies the existing
> top-level repo; it lives entirely under `v3/`.

## The three example hops

```
   C ──[c_riscv]──▶ rv64-elf ──[riscv_btor2]──▶ btor2 ──[btor2_smtlib]──▶ smt-lib
   compile          (sail-riscv group)            reasoning                bridge
   differential-only  differential-only + machine-tool path   decide-both-ways
```

The worked route `C → rv64-elf → btor2 → smt-lib` (`gurdy/chains/c_to_smtlib.py`)
exercises all three hop kinds, the Sail source-semantics group, mixed-trust
meet-composition, and the two reasoning paths at the `riscv_btor2` node.

## The two epistemologies (see `ARCHITECTURE.md`)

- **Source edges** are trusted **referentially** — conformance to a formal
  semantics (Sail for rv64). This defines *correct*.
- **Reasoning edges** are trusted **differentially** — independent decision
  procedures (and the decide-both-ways bridge) must agree.

A pair lowering is built **`differential_only`**: the agent is sandboxed
from Sail and validates against an independent `dev_oracle` (Spike); the
gate then checks it against Sail on a **held-out** partition. That
independence is what lets a pair *validate* Sail, not just consume it.

## The generic `sail → btor2` machine tool

`tools/sail_btor2_machine/` is an **ISA-agnostic generator**: it turns a
Sail ISA model into a BTOR2 *machine model* (a universal CPU transition
system) whose whole-machine equivalence to Sail is proven **once**. A
program then "translates" by **initialization** (load memory + PC). This
verified model is published as a **realization** of the `sail-riscv`
semantics group, alongside the Sail emulator. A differential-only pair may
declare `machine_tool` to instantiate it as an **alternative reasoning
path** at runtime (and cross-check it against its own lowering) — but may
**not** use it during construction (that would break independence).

## Layout

| Path | Role |
|---|---|
| `gurdy/core/` | language graph, hops, routes, manifests, fidelity reports |
| `gurdy/hops/` | the three example hops (typed stubs) |
| `gurdy/chains/` | the worked `C→…→smt-lib` route |
| `tools/sail_btor2_machine/` | the generic Sail→BTOR2 machine generator + verifier |
| `semantics/sail-riscv/` | the source-semantics group: two realizations + IDF allowlist |
| `registry/` | the typed holes (human-authored manifests) |
| `gate/` | the independent referee: fidelity battery, sandbox, trust, merge policy |
| `agents/` | the orchestrator + playbooks for the two agent types |
| `schemas/` | JSON-Schema for manifests and reports |
| `ci/` | sample workflows (move to `.github/workflows/` on adoption) |

## Run it

```bash
cd v3
python cli.py routes c smt-lib        # enumerate routes over the hop graph
python cli.py plan                    # what the orchestrator would spawn
python cli.py gate riscv_btor2        # run the gate (F0 real; F1–F3/machine stubbed)
python cli.py chain                   # walk the worked C→…→smt-lib route
```
