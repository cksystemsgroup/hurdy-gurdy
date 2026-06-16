# hurdy-gurdy v3 — Roadmap

From the current depth-i slice to a full **C → RISC-V → BTOR2 → SMT-LIB** chain,
a second Sail-backed ISA (AArch64), and — eventually — source-semantics groups
that are **not** backed by Sail at all (WasmCert, KEVM, …).

## Goals

1. **Full RISC-V chain.** `main` runs `C → rv64-elf → btor2 → smt-lib` over the
   *full* RV64IMC user-mode ISA (memory + control flow), as the selfie/**rotor**
   C-to-BTOR2 tool does — not just the straight-line ALU slice we have today.
2. **More Sail-backed pairs.** Bring the v2 reasoning pairs that have an upstream
   Sail model into `main`. Of v2's five (riscv, aarch64, ebpf, evm, wasm) **only
   AArch64** has one ([`rems-project/sail-arm`](https://github.com/rems-project/sail-arm),
   ASL-derived, vendor-blessed). So this goal is concretely **`sail-aarch64` +
   `aarch64_btor2`**.
3. **Generalize beyond Sail (eventual).** eBPF / EVM / Wasm have *no* Sail model
   but *do* have other mechanized/executable semantics (WasmCert, KEVM, Dafny-EVM,
   the Solana eBPF semantics). Generalize the "source-semantics group" so those
   ISAs can be referenced too — see §6.

## Operating principles

- **One independent agent per pair, working sequentially.** Never subdivide a
  single pair's build across parallel agents; parallelize only *across*
  independent pairs/groups. (Research/exploration may parallelize.)
- **Two epistemologies, unchanged.** Source edges are trusted *referentially*
  (conformance to a formal semantics); reasoning edges *differentially*
  (independent decision procedures must agree). A pair lowering is built
  `differential_only` — sandboxed from the semantics during construction — so it
  can *validate* the oracle, not merely consume it.
- **The gate decides merge.** Fidelity lattice `F0_typed < F1_tested <
  F2_bounded < F3_lowering < F4_extracted`. The agent's local run is feedback;
  the verdict is the gate on a clean checkout.

---

## 1. Baseline (what exists today)

**GREEN**
- `sail-riscv` group, `btor2-machine` realization — **RV64I/M ALU slice (43
  instrs)**: reg-reg, reg-imm, W-ops, LUI, AUIPC, M mul/div. All three
  obligations discharged (per-instruction QF_BV lemmas vs reference; reference
  cross-validated vs real Sail v0.12; fetch/decode/dispatch/writeback/pc harness
  lemma). Emitted `model.btor2` model-checked ≡ Sail by pono.
- `riscv_btor2` **own** lowering — same ALU slice, independent (audit-clean),
  differential vs Sail on held-out programs (F0–F3 PASS, merge ALLOW).
- Chain skeleton, route enumeration, gate battery, orchestrator *planner*.

**Stub (BLOCK)** — `c_riscv` (compile), `btor2_smtlib` (bridge).

**Structural gaps that block "full RISC-V"** (file pointers for the agents)
- The machine BTOR2 *already* declares a `bv64→bv8` memory array and fetches the
  instruction word from `mem[pc..pc+3]` (`tools/sail_btor2_machine/control.py`),
  but: **memory is never written**, **next-PC is hardcoded `pc+4`**, and there
  are **no load/store/branch/jump/ecall** specs. The scaffold exists; the
  semantics don't.
- The generator is **hardcoded to RV64** (opcodes, funct fields, XLEN, 5-bit
  regs) — `tools/sail_btor2_machine/isa/rv64_alu.py`, `control.py`. Needs an
  ISA-agnostic refactor before AArch64.
- `tools/sail_btor2_machine/instantiate.py` (ELF image → initial memory) is
  `NotYetImplemented`.
- The **own** path has no memory array and is a straight-line specializer
  (`gurdy/hops/riscv_btor2/{decode,btor2}.py`) — fine for loop-free ALU, not for
  programs with control flow.
- **Version pin nuance:** `GROUP.yaml` says Sail `0.18.0`; the emulator *binary*
  is release `0.12`; `registry/riscv_btor2.yaml` wants `>=0.18.0`. Reconcile
  before scaling (see §7).

---

## 2. Target scope — "full RISC-V" = v2/rotor RV64IMC

Grounded in v2's `riscv-btor2` SCHEMA (preserved at tag `v2-final`) and rotor:

- **ALU** (have it) + **branches** BEQ/BNE/BLT/BGE/BLTU/BGEU + **loads**
  LB/LBU/LH/LHU/LW/LWU/LD + **stores** SB/SH/SW/SD + **jumps** JAL/JALR +
  **M-ext** + **FENCE/FENCE.I** (no-op) + **ECALL/EBREAK** (set `halted`) +
  **CSR** (read nondet, writes dropped at first cut) + **RVC** (expand to 32-bit
  before lowering).
- **Memory:** `Array bv64 bv8`, little-endian, misaligned = per-byte; initial
  state = ELF `PT_LOAD` segments, BSS zero, else unconstrained.
- **Control:** 64-bit PC, `halted` 1-bit; boundary = `ra` constrained outside the
  analyzed function set (self-loop on out-of-range PC).
- **Out of scope (first cut):** FP (F/D), atomics (A), vector (V), privileged.

---

## 3. Agent roster (one independent agent each)

| Agent | Branch | Sail access | Job | Gate target |
|---|---|---|---|---|
| **P‑c_riscv** | `pairs/c_riscv` | no | compile C→rv64-elf (gcc-pinned, reproducible + CBMC differential) | F1 |
| **P‑btor2_smtlib** | `pairs/btor2_smtlib` | no | bridge btor2→smt-lib (decide-both-ways) | F1 |
| **M‑riscv** | `machine/sail-riscv` | **yes** | extend btor2-machine to full RV64IM + memory/control, prove ≡ Sail | machine GREEN |
| **P‑riscv_btor2** | `pairs/riscv_btor2` | no | extend own lowering to full RV64IM (seed from v2), differential vs Sail | F3 |
| **M‑aarch64** | `machine/sail-aarch64` | **yes** | vendor sail-arm, new group + btor2-machine for an AArch64 slice | machine GREEN |
| **P‑aarch64_btor2** | `pairs/aarch64_btor2` | no | aarch64→btor2 pair (seed from v2), differential vs sail-arm | F3 |
| *(later)* **P‑{ebpf,evm,wasm}_btor2** | `pairs/<id>` | no | port v2 lowerings; oracle per §6 | F1–F2 (differential) or higher if §6 |

`machine-*` agents are referential (Sail/oracle access); `pairs/*` agents are
sandboxed and audited for independence.

---

## 4. Phased plan

### Phase 0 — shared infrastructure (I do this; unblocks the agents)

- **Memory + control-flow BTOR2 machinery** (shared by every full-machine model):
  memory read/write ops, symbolic next-PC (`cond ? pc+imm : pc+4`, JAL/JALR
  targets), ECALL/EBREAK → `halted`, and `instantiate.py` ELF→memory init.
- **Orchestrator spawning:** turn `agents/orchestrator.py` from a planner into a
  launcher — one agent per `pairs/<id>` / `machine/<group>` branch, sandbox flag
  wired, gate-on-clean-checkout. (I can also drive this by hand via sub-agents
  initially.)
- *(ISA-agnostic refactor is Phase 2 — not needed for RISC-V.)*

**Decision D1 — own-path control flow.** Either (a) the own path becomes a full
rotor-style fetch-decode-execute machine over a memory image — keeps the
"independently validate Sail" property and matches rotor — *recommended*; or
(b) the own path stays straight-line and control-flow programs use the
Sail-derived machine path (less independent validation, faster).

### Phase 1 — the full RISC-V chain (primary goal)

1. **Quick wins (parallel, independent pairs):** P‑c_riscv and P‑btor2_smtlib.
   These close the chain end-to-end for the *existing* slice immediately.
2. **Full RISC-V (parallel across the two agents; sequential within each):**
   - **M‑riscv** extends the machine model to memory + control flow, re-proves
     the harness lemma (now over loads/stores/symbolic next-PC), re-validates vs
     Sail. *This whole-machine equivalence is the long pole.*
   - **P‑riscv_btor2** extends the own lowering to full RV64IM, **seeded from
     v2's hand-written RV64IMC lowering** (Sail-independent ⇒ audit-clean — see
     D2), differential vs Sail on held-out programs.
   They meet at the gate: machine GREEN (full subset) + F1/F2/F3 on the pair.

**Exit:** `gurdy gate riscv_btor2` ALLOWs at F3 over full RV64IM; `cli.py chain`
runs a looping C program end-to-end to an SMT-LIB query.

### Phase 2 — AArch64 (the Sail-backed v2 pair)

1. **ISA-agnostic refactor** of the generator: parameterize the instruction-spec
   table, decode fields (opcode/funct widths), XLEN, register file shape. RISC-V
   becomes one instantiation.
2. **`sail-aarch64` group:** vendor a pinned `sail-arm` (ASL-derived) model +
   emulator oracle (a Sail-ARM executable). Mirror the `sail-riscv` GROUP/IDF
   layout.
3. **M‑aarch64** → btor2-machine for an AArch64 slice (ALU + flags + mem + branch),
   proven ≡ sail-arm.
4. **P‑aarch64_btor2** → the pair, seeded from v2's AArch64 lowering, differential
   vs sail-arm. *(Optional `c_aarch64` for a full C→aarch64→btor2 chain.)*

### Phase 3 — generalize beyond Sail (see §6)

eBPF / EVM / Wasm pairs, with **non-Sail** source-semantics groups.

---

## 5. Seeding from v2

**Decision D2 — seed from v2 lowerings.** v2's hand-written lowerings (riscv,
aarch64, ebpf, evm, wasm; preserved at `v2-final`) are **independent of Sail**
(they used hand-written Python simulators as oracles, never Sail). Porting/
modernizing them into the v3 hop interface is therefore **audit-clean** — the
independence audit forbids cribbing *Sail / the machine model*, not the team's
own prior work. This is a large de-risk for every pair. *Recommended: yes.* The
agent ports the v2 lowering, then the gate validates it against the (new) Sail
oracle on a held-out partition.

---

## 6. Generalizing source-semantics groups beyond Sail

The pair interface (`decode → btor2`) and the gate are **oracle-agnostic
already**. What is Sail-specific is the *source-semantics group*: today a group =
{ vendored Sail model, an executable emulator realization, a verified
btor2-machine realization }. To admit eBPF/EVM/Wasm we generalize the group to an
**Oracle interface** with pluggable backends.

### 6.1 The Oracle interface (capabilities)

A source-semantics oracle may provide some subset of:

| Capability | What it enables | Sail | KEVM | Dafny-EVM | WasmCert | Wasm ref-interp | eBPF (Solana sem.) |
|---|---|---|---|---|---|---|---|
| **Executable conformance** (run a program, observe the projection) | F1/F2 differential | ✅ emulator | ✅ (K runner) | ✅ | ⚠️ via extraction | ✅ | ✅/⚠️ |
| **Mechanized proof export** (theorem-prover defs) | F3/F4 referential trust | ✅ Isabelle/Rocq/Lean | ⚠️ (K) | ⚠️ (Dafny) | ✅ Isabelle/Coq | ❌ | ⚠️ |
| **Machine-model generation** (ISA → BTOR2 machine) | the `machine` path | ✅ (our tool) | ❌ | ❌ | ❌ | ❌ | ❌ |

The **fidelity ceiling of a pair is bounded by its oracle's capabilities**:
- *Executable only* → F1_tested / F2_bounded (differential, sampled / bounded).
- *+ mechanized semantics* → F3_lowering possible (lemmas vs an exported
  reference), and F4_extracted where the chain to a proof assistant exists.
- *+ machine-model generation* (today: only Sail) → the verified `machine` path.

So Sail stays the **gold tier** (all three), and non-Sail oracles slot in at an
honestly lower ceiling — recorded in the report, never faked.

### 6.2 Concrete adapters

- **Wasm → WasmCert** (Isabelle/Coq mechanized spec) + the **official Wasm
  reference interpreter** as the executable oracle. Executable conformance +
  mechanized proof export ⇒ up to F3; no auto BTOR2 machine ⇒ no `machine` path
  (the pair's own lowering is the only reasoning path).
- **EVM → KEVM** (executable via the K framework) or **Dafny-EVM** (executable +
  Dafny-verifiable). Stack machine; the "projection" is `(decision, model_on_sat,
  gas/stack/storage)`. Executable ⇒ F1/F2; mechanized ⇒ F3 with effort.
- **eBPF → the Solana eBPF formal semantics** + a reference interpreter.
  Executable ⇒ F1/F2.

### 6.3 What Phase 3 actually builds

1. A `gurdy/core/oracle.py` **Oracle protocol** (`run(program) → projection`,
   plus optional `reference_export()` / `machine_model()`), with the current Sail
   emulator as the first implementation.
2. `GROUP.yaml` gains an `oracle:` kind (`sail` | `external`) and a declared
   **capability set**; the gate reads it to cap the achievable fidelity.
3. One `external`-oracle group per ISA (`wasmcert-wasm`, `kevm-evm`,
   `solana-ebpf`), each wrapping the upstream tool behind the Oracle protocol.
4. The pairs (ported from v2 per §5) gate `differential_only` against these
   oracles — same discipline, same held-out partitioner, lower ceiling.

This keeps the architecture honest: **Sail-backed pairs reach F3/F4; non-Sail
pairs reach exactly as far as their oracle's capabilities allow**, and the report
says which.

---

## 7. Cross-cutting concerns & risks

- **Whole-machine equivalence is the real cost.** Per-instruction ALU lemmas were
  easy; proving memory + symbolic next-PC ≡ Sail (the harness lemma over
  loads/stores/branches) is the hard, novel part. M‑riscv is the long pole.
- **Loops ⇒ unbounded.** The full machine BTOR2 needs a BMC bound `k` (or pono
  for k-induction/unbounded). The smt-lib bridge inherits this; record bounds
  honestly (no silent caps).
- **Independence at scale.** Every pair agent sandboxed; the audit must stay
  robust as lowerings grow. Seed-from-v2 (§5) is audit-clean by construction.
- **Version pinning.** Reconcile the Sail 0.12-binary / 0.18-model / `>=0.18`
  mismatch; pin the `sail-arm` ASL date and every external oracle's version, as
  the bench image already pins solvers/Sail (BENCHMARKING.md §9.8).
- **RAM/compute.** One agent per pair, sequential within a pair; conservative
  parallelism across pairs. Heavy backends come from the pinned bench image.

---

## 8. Sequencing summary

```
Phase 0  infra: memory+control BTOR2 machinery, ELF→mem init, orchestrator launch   [me]
Phase 1  P-c_riscv (F1)  ·  P-btor2_smtlib (F1)          ← quick wins, close the chain
         M-riscv (machine GREEN, full RV64IM)  ∥  P-riscv_btor2 (F3, seeded)
         ⇒ full C→RISC-V→BTOR2→SMT-LIB over RV64IM
Phase 2  ISA-agnostic refactor → sail-aarch64 group → M-aarch64 → P-aarch64_btor2
Phase 3  Oracle interface (gurdy/core/oracle.py) → external-oracle groups
         wasmcert-wasm / kevm-evm / solana-ebpf → port v2 pairs (differential)
```

## 9. Open decisions

- **D1 — own-path control flow:** full rotor-style machine *(recommended)* vs
  straight-line + machine-delegation.
- **D2 — seed from v2 lowerings:** yes *(recommended)* vs clean-room rebuild.
- **D3 — non-Sail integration depth (per ISA):** differential-only (executable
  oracle, F1/F2) vs full referential (mechanized semantics ⇒ F3/F4).
- **D4 — Sail version reconciliation** before scaling to a second ISA.
