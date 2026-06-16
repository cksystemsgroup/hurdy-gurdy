# hurdy-gurdy v3 — Roadmap

**Focus: generalize the reference oracle away from "Sail only."** Make a *formal
model* a first-class, **registered-by-humans, developed-by-agents** artifact —
symmetric to a pair — so that any pair can reference any registered model
(Sail, WasmCert, KEVM, …) as its semantics oracle. **Pair development comes
after** this architecture is in place.

## Goal

Today the only reference oracle is a hand-wired Sail-RISC-V group. The goal is
**architectural support for formal models that pairs use as reference**:

- A **model registry** (humans declare *what* model they want available) and a
  **model-build agent** (autonomously supplies *how*: vendor, pin, wire, realize)
  — exactly the register→implement→gate loop we already use for pairs.
- An **Oracle interface** that abstracts a formal model behind a capability set,
  so Sail is *one* backend among many, and a pair's fidelity ceiling is bounded
  by the *certified* capabilities of the model it references.

Only once models are a generalized, registry-driven substrate do we resume pair
development (the full C→RISC-V→BTOR2→SMT-LIB chain, AArch64, etc.) — now as
*consumers* of registered models. See §6.

## The symmetry (this is the whole idea)

| | **Model** (source semantics / reference) | **Pair** (hop / reasoning) |
|---|---|---|
| Registered by | a human (`registry/models/<id>.yaml`) | a human (`registry/<id>.yaml`) |
| Built by | a **model-build** agent (referential — *has* the model) | a **pair-build** agent (sandboxed — *blind* to the model) |
| Trust | referential (conformance to the formal semantics) | differential (independent procedures agree) |
| Certified by | the **model gate** (oracle conforms; capabilities honest) | the **pair gate** (F0–F4 battery) |
| Produces | an Oracle: `run`, optional proof-export, optional machine-model | a lowering `in_lang → out_lang` |
| One agent each | yes, sequential | yes, sequential (no intra-pair parallelism) |

Referential artifacts (models) are built **openly**; reasoning artifacts (pairs)
are built **blind** to the model and validated against it — that asymmetry is
what lets a pair *validate* a model rather than merely consume it.

---

## 1. Baseline

The `sail-riscv` group exists but is **hand-wired**: a vendored Sail model, an
emulator realization (`oracle.py`, shelling to `sail_riscv_sim` v0.12), and a
verified `btor2-machine` realization (GREEN for the RV64I/M ALU slice). The
orchestrator already distinguishes **machine-build** (Sail access) vs
**pair-build** (sandboxed) agents — but a model is not yet a *registered,
agent-developed* thing, and the oracle is Sail-specific.

This roadmap turns that one bespoke group into the **first instance of a
generalized, registered model** (dogfood the abstraction by reducing the
existing thing to it).

---

## 2. The Oracle interface (capabilities)

A registered model realizes an **Oracle** providing some subset of three
capabilities. The model gate certifies *which*, honestly:

| Capability | Method (sketch) | Unlocks for a referencing pair |
|---|---|---|
| **Executable conformance** | `run(program, binding) → projection` | F1_tested / F2_bounded (differential, sampled / bounded) |
| **Mechanized-proof export** | `reference_export()` → theorem-prover defs / a transcribable reference | F3_lowering (lemmas vs an exported reference) and F4_extracted where a proof chain exists |
| **Machine-model generation** | `machine_model()` → a verified BTOR2 machine | the `machine` reasoning path (instantiate-by-init) |

**A pair's fidelity ceiling = the certified capabilities of the model it
references.** Sail is the gold tier (all three). Others slot in lower and the
report says so — never faked.

| Model (backend) | Executable | Proof export | Machine-gen | Max pair fidelity |
|---|---|---|---|---|
| **Sail** (riscv, arm, …) | ✅ emulator | ✅ Isabelle/Rocq/Lean | ✅ (our generator) | F4 + machine path |
| **WasmCert** + Wasm ref-interp | ✅ ref interpreter | ✅ Isabelle/Coq | ❌ | F3 |
| **KEVM / Dafny-EVM** | ✅ K / Dafny runner | ⚠️ (K / Dafny) | ❌ | F2–F3 |
| **Solana eBPF semantics** | ✅ ref interpreter | ⚠️ | ❌ | F2 |

---

## 3. Phase A — the formal-model architecture (the focus)

Each item is small and independently reviewable. I drive the framework pieces;
each *model* (A8) is then one model-build agent.

- **A1 — Oracle protocol.** `gurdy/core/oracle.py`: the `run` / `reference_export`
  / `machine_model` protocol + a `capabilities` set. Make the current Sail
  emulator oracle implement it (no behavior change).
- **A2 — Model registration schema + registry.** `schemas/model_registration.schema.json`
  and `registry/models/<id>.yaml`, mirroring pair registration: `id`, `language`,
  upstream `source` (repo + pinned version), `oracle: { kind: sail | external }`,
  `target_capabilities`, `conformance_suite`, `agent: { playbook, budget }`.
- **A3 — Group = realization of a registration.** Refactor `semantics/<group>/
  GROUP.yaml` to be the *realization* side of a registered model; record the
  certified capability set per realization. **Retrofit `sail-riscv`** as the
  first `registry/models/` entry (dogfood).
- **A4 — Model-build agent + playbook.** `agents/playbook/BUILD_model_from_registration.md`,
  generalizing today's `BUILD_machine_from_sail.md`: vendor + pin upstream, build
  the executable emulator realization, wire the Oracle protocol, and build the
  machine realization **iff** the registration targets machine-gen and the
  backend supports it. Orchestrator plans one model-build agent per registered-
  but-unrealized model.
- **A5 — Model gate.** `gate/model/`: certify the oracle runs and conforms to the
  upstream's own test suite (or self-consistency), that declared capabilities are
  *backed* (no claiming machine-gen/proof-export you can't produce), and that the
  version is pinned. Publishes the **certified capability set**.
- **A6 — Fidelity-by-capability.** The pair gate reads a referenced model's
  certified capabilities and **caps** the achievable fidelity accordingly
  (recorded in the report). This is the load-bearing link between §2 and merge.
- **A7 — ISA-agnostic machine generator.** Make the machine-gen capability work
  beyond RV64 (parameterize decode fields / XLEN / regfile), so machine-gen is a
  *general* capability, not a RISC-V special case — the prerequisite for any
  second Sail model offering it.
- **A8 — Bring up the model roster** (one model-build agent each; see §4).

**Exit:** `sail-riscv` is a registered model certified through the model gate;
at least one **non-Sail** model (e.g. `wasmcert-wasm`) is registered and
certified at its honest capability ceiling; the pair gate caps fidelity by
certified capability. The substrate is general.

---

## 4. The model roster (registered models, one agent each)

| Model id | Language | Backend | Target capabilities | Agent |
|---|---|---|---|---|
| `sail-riscv` | rv64 | Sail (`riscv/sail-riscv`) | exec + proof + machine | retrofit / M‑sail-riscv |
| `sail-aarch64` | aarch64 | Sail (`rems-project/sail-arm`, ASL-derived) | exec + proof + machine | M‑sail-aarch64 |
| `wasmcert-wasm` | wasm | WasmCert (Isabelle/Coq) + Wasm ref-interp | exec + proof | M‑wasmcert |
| `kevm-evm` | evm | KEVM (K) or Dafny-EVM | exec (+proof ⚠️) | M‑kevm |
| `solana-ebpf` | ebpf | Solana eBPF formal semantics + ref-interp | exec | M‑ebpf |

Of v2's reasoning targets, only RISC-V and AArch64 have Sail models; the rest
(wasm/evm/ebpf) are exactly why the generalization matters — they enter as
**external**-oracle registrations.

---

## 5. Phase B — pair development (after Phase A)

Resume pairs as *consumers* of registered models. This is where the earlier plan
lives, deferred:

1. **Full RISC-V chain** — `c_riscv` (compile, F1), `btor2_smtlib` (bridge, F1),
   and `riscv_btor2` extended to **full RV64IMC** (memory + control flow, rotor/v2
   scope) referencing the certified `sail-riscv` model. The machine model also
   grows to the full subset (memory + symbolic next-PC + ecall/htif).
2. **AArch64 pair** — `aarch64_btor2` referencing `sail-aarch64`.
3. **wasm / evm / ebpf pairs** — referencing the external-oracle models, capped at
   their honest fidelity.

Deferred pair-level decisions (revisit when Phase B starts):
- **own-path control flow** — full rotor-style machine vs straight-line + machine
  delegation;
- **seed from v2** — port v2's hand-written (Sail-independent ⇒ audit-clean)
  lowerings as starting points.

---

## 6. Cross-cutting concerns & risks

- **Honest capability ceilings.** The whole design hinges on the model gate
  *refusing* to certify capabilities a backend can't back. A model that only
  runs (no proof export, no machine-gen) must cap its pairs at F2 — and say so.
- **External-oracle integration cost.** Wrapping KEVM (K), WasmCert (Isabelle/
  Coq + extraction), or the eBPF semantics behind one `run`/`reference_export`
  protocol is real work per backend; pin every upstream like the bench image
  pins solvers/Sail (BENCHMARKING.md §9.8).
- **Version pinning is core to model dev**, not an afterthought — reconcile the
  current Sail 0.12-binary / 0.18-model / `>=0.18` mismatch as part of A3.
- **Machine-gen generality (A7)** is the hard framework piece; the whole-machine
  equivalence proof (memory + symbolic next-PC ≡ the model) returns in Phase B.
- **RAM/compute.** One agent per model/pair, sequential within each; parallelize
  only across independent models/pairs. Heavy backends from the pinned image.

---

## 7. Sequencing

```
Phase A  (focus)  formal-model architecture
  A1 Oracle protocol        A2 model registry+schema     A3 group=realization (retrofit sail-riscv)
  A4 model-build agent      A5 model gate                A6 fidelity-by-capability
  A7 ISA-agnostic machine-gen
  A8 model roster: certify sail-riscv; register+build ≥1 non-Sail model (wasmcert-wasm),
     then sail-aarch64 / kevm-evm / solana-ebpf — one model-build agent each

Phase B  (after)  pair development as consumers of registered models
  full RISC-V chain (c_riscv, btor2_smtlib, riscv_btor2 full RV64IMC)  →  aarch64_btor2  →  wasm/evm/ebpf pairs
```

## 8. Open decisions (model architecture)

- **MA1 — registry layout:** `registry/models/<id>.yaml` (separate dir) vs a
  `kind: model|pair` discriminator in one registry.
- **MA2 — capability set:** the three in §2, or finer (e.g. split bounded vs
  unbounded executable conformance; concurrency/memory-model export)?
- **MA3 — machine-build vs model-build:** fold today's `machine-build` agent into
  a single `model-build` agent where machine-gen is just one targeted capability,
  vs keep them distinct.
- **MA4 — retrofit depth:** how far to reduce the existing bespoke `sail-riscv`
  group to the new registration before declaring A3 done.
- **MA5 — Sail version reconciliation** (0.12 / 0.18 / `>=0.18`), done as part of
  the retrofit.
