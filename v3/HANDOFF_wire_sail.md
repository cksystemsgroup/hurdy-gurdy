# HANDOFF — wire real Sail into the v3 sail-riscv group

**Purpose.** A self-contained brief to execute *in one go* on a local Claude
CLI that has Docker + network (this branch's originating environment had
neither Sail nor Docker). It takes the `sail-riscv` group's btor2-machine
realization from `PARTIAL` toward `GREEN` and unlocks the value-to-Sail
conformance results. No prior chat context required — everything you need is
here plus `v3/ARCHITECTURE.md` and
`v3/semantics/sail-riscv/realizations/btor2-machine/MACHINE_BUILD_LOG.md`.

---

## Where things stand (branch `claude/intelligent-cerf-2mbr6n`)

- `v3/` is a runnable depth-i skeleton of the hop-registry architecture
  (`README.md`). `python3 cli.py {routes,plan,gate,chain,hops}` work.
- The `sail-riscv` group has a **PARTIAL** btor2-machine realization: 43
  RV64I/M ALU instructions with per-instruction **QF_BV equivalence lemmas
  discharged by z3** (`python3 -m tools.sail_btor2_machine.selftest` → 43/43).
- **Two honest gaps keep it PARTIAL, and they are this brief's targets:**
  1. The reference is a spec-derived `v3/semantics/sail-riscv/reference_rv64.py`
     **standing in for Sail** (Sail was absent). The lemmas prove the model
     equals *this reference*, not Sail itself.
  2. The fetch/decode/PC **harness lemma** is not discharged
     (`harness_lemma_ok=None`); the emitted model is execute-datapath only.

## Prerequisites on the local machine

- Docker (to build the bench image) + outbound network.
- `python3` with `z3` (the v3 code runs standalone on z3; the selftest must
  still pass before and after your changes).

---

## The concrete vs. symbolic point — READ THIS FIRST

`reference_rv64.py` is a **symbolic** reference (z3 BitVec functions); that is
what makes the **F3** per-instruction lemmas (`encode == reference` *for all
inputs*) possible. The Sail **emulator** is a **concrete executable** (run
program+inputs → state). So installing the emulator does **not** directly
replace the symbolic reference. Wire it as a **two-step chain** instead:

> **Sail emulator validates `reference_rv64.py` (concrete, F1); then
> `reference_rv64.py` validates the BTOR2 model (symbolic, F3).**

This discharges the "stands in for Sail" caveat honestly — the reference is no
longer unaudited, it is pinned to real Sail — while keeping the all-inputs F3
proofs already in place. Keep the existing `_load_reference` swap point in
`verify.py`; **add** a concrete cross-check, do not throw the symbolic
reference away. (Alternative for a *fully* symbolic Sail reference: `sail
-smt` / Isla to extract a per-instruction relation — heavier; the two-step
above is the recommended path.)

---

## The sequence (do in order; each step has an acceptance check)

### Step 1 — install the Sail-RISCV emulator in the image
Edit the repo-root `Dockerfile` (not under `v3/`). Prefer the upstream
**binary release** (the sail-riscv README calls it "strongly recommended")
over an opam source build, matching the existing cvc5 layer pattern: pinned
tag, multi-arch via `TARGETARCH`. Draft to refine against a real build:

```dockerfile
# --- Sail-RISCV reference emulator (v3 sail-riscv group oracle) -------------
ARG SAIL_RISCV_TAG=0.7        # VERIFY current release tag at github.com/riscv/sail-riscv/releases
ARG TARGETARCH
RUN SAIL_ARCH=$([ "${TARGETARCH}" = "amd64" ] && echo x86_64 || echo aarch64) \
 && curl -fsSL "https://github.com/riscv/sail-riscv/releases/download/${SAIL_RISCV_TAG}/sail_riscv-Linux-${SAIL_ARCH}.tar.gz" -o /tmp/sail.tgz \
 && mkdir -p /opt/sail-riscv && tar -xzf /tmp/sail.tgz -C /opt/sail-riscv --strip-components=1 \
 && install -m 0755 /opt/sail-riscv/bin/riscv_sim_RV64 /usr/local/bin/riscv_sim_RV64 \
 && rm -rf /tmp/sail.tgz /opt/sail-riscv
```
**VERIFY** the exact release tag and asset filename against current upstream
(the URL/layout may differ). Fallback if no arch binary: opam — `opam install
sail` (needs Sail ≥ 0.20.1), clone `riscv/sail-riscv` at a pinned tag,
`make ARCH=RV64` (use `DOWNLOAD_GMP=FALSE` to reuse the image's libgmp) →
`c_emulator/riscv_sim_RV64`.
**Acceptance:** `docker build` succeeds; inside the container
`riscv_sim_RV64 --help` runs. Record the image hash + Sail tag in
`BENCHMARKING.md` §8.7 (the pinning manifest).

### Step 2 — make the emulator oracle real
`v3/semantics/sail-riscv/realizations/emulator/oracle.py` currently raises
`NotYetImplemented`. Implement `run(program: bytes, binding, *, max_steps) ->
list[Projection]` by shelling to `riscv_sim_RV64`: write the program to a
temp ELF, apply the initial register/memory `binding`, run for `max_steps`,
and parse the per-step `pc`, `x1..x31`, `halted` into the `Projection`
dataclass already defined in that file.
**Acceptance:** a tiny hand-written RV64 program (e.g. a couple of `addi`s)
produces the expected per-step projection.

### Step 3 — make the F1 differential gate real
`v3/gate/fidelity/f1_tested.py` currently returns `NOT_IMPLEMENTED`. Implement
the concrete differential for a `reasoning` hop: generate instances, run them
through the candidate (model/pair) and through the Step-2 Sail oracle, compare
on the pinned projection. For `oracle_access: differential_only`, validate on
the **held-out** partition via `gate/oracle_service.py` (the `Partitioner` is
already there; wire its `query` to the Step-2 oracle).
**Acceptance:** `python3 cli.py gate riscv_btor2` runs F1 for real (PASS or a
real divergence), not `NOT_IMPLEMENTED`.

### Step 4 — cross-validate the reference against Sail, and wire the machine gate
(a) Add a `reference_vs_sail` concrete cross-check (new function in
`tools/sail_btor2_machine/verify.py` or a sibling): for many random + corner
inputs per instruction, assert `reference_rv64.<instr>` evaluates to the same
result the Sail emulator produces. This audits the *symbolic* reference
against *real Sail*.
(b) Update the caveat: in `reference_rv64.py`, `verify.py`, and
`v3/semantics/sail-riscv/GROUP.yaml`, change "stands in for Sail" →
"cross-validated against Sail v<tag>" once (a) passes clean.
(c) Wire `v3/gate/machine/verify_machine.py` (currently returns an empty
non-green report) to actually call `generate` + `verify` and return the real
`MachineFidelityReport`, so the gate reflects ground truth.
**Acceptance:** the cross-check passes for all 43 instructions (or reports a
genuine Sail/reference divergence — triage it, subtract IDF via
`idf_allowlist.yaml`, and if Sail is the suspect, minimize to one instruction
and note it for upstream). `gate_machine('sail-riscv')` returns the real
report.

### Step 5 (stretch) — the harness lemma
Emit the fetch-from-memory + decode-dispatch + writeback loop in the BTOR2
model (`generate.py`) and discharge the harness lemma (control == reference
`step`) in `verify.py`, setting `harness_lemma_ok=True`. This is the larger
remaining piece; the execute datapaths it dispatches to are already proven.

---

## Definition of done / what GREEN requires

Flip `GROUP.yaml`'s btor2-machine `equivalence: PARTIAL` → `GREEN` **only when
all** hold: (1) every implemented instruction's F3 lemma passes, (2) the
reference is cross-validated against real Sail (Step 4a), **and** (3) the
harness lemma is discharged (Step 5). Until (3), keep it `PARTIAL` even if
Steps 1–4 are green — be honest; the merge policy refuses to rely on a
non-GREEN realization, which is correct.

## Guardrails

- Work only under `v3/` and the repo-root `Dockerfile`. Pin every version.
- Do not fake results. A stubbed/failed check must report as such; the gate is
  the verdict, not your say-so. Keep the existing `cli.py gate` behaviour
  honest (it should not silently flip to GREEN).
- After Step 1, record the image hash + Sail tag in `BENCHMARKING.md` §8.7.
- Commit with `user.email noreply@anthropic.com`, `user.name Claude` (GitHub
  marks other identities Unverified). Push to
  `claude/intelligent-cerf-2mbr6n`. Do not open a PR unless asked.
- Re-run `python3 -m tools.sail_btor2_machine.selftest` and `python3 cli.py
  gate riscv_btor2` after each step; both must stay runnable.
