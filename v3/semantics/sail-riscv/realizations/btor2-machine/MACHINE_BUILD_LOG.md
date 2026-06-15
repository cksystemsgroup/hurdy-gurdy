# Machine build log — btor2-machine realization (RV64I/M ALU slice)

Agent: machine-build (referential). Date: 2026-06-14.

## What was implemented

A BTOR2 machine model for the **lowering-sensitive RV64I/M ALU core**, with a
**single source of truth per instruction** that drives BOTH the BTOR2 emission
and the z3 equivalence proof, so the emitted fragment and the proven semantics
cannot drift.

- `tools/sail_btor2_machine/isa/expr.py` — a tiny QF_BV expression IR with two
  lowerings: `to_z3` (for the proof) and `Btor2Builder` (for `model.btor2`).
- `tools/sail_btor2_machine/isa/rv64_alu.py` — per-instruction `InstrSpec`
  (decode: opcode/funct3/funct7) + an `Expr` execute tree. 43 instructions.
- `tools/sail_btor2_machine/generate.py` — emits `model.btor2` (harness state
  skeleton + one execute datapath per instruction), `decode_map.json`,
  `provenance.json`. Deterministic.
- `tools/sail_btor2_machine/verify.py` — z3 proof of
  `encode(instr) == reference(instr)` for all 64-bit inputs, returns a real
  `MachineFidelityReport`.
- `semantics/sail-riscv/reference_rv64.py` — independent, spec-derived
  reference semantics (the Sail stand-in; see caveat below).
- `tools/sail_btor2_machine/selftest.py` — runs generate -> verify, prints the
  per-instruction table and the report.

## Reference-vs-Sail: now a two-step chain to real Sail (2026-06-15 update)

The architecture requires verifying against **Sail**. The F3 lemmas prove the
BTOR2 fragments equal `semantics/sail-riscv/reference_rv64.py` (a bit-precise
RV64I/M reference derived from the RISC-V Unprivileged ISA spec) symbolically,
over all inputs. That reference is now **cross-validated against the real Sail
emulator** (pinned upstream release **v0.12**, `sail_riscv_sim`):

    Sail emulator  --(concrete cross-check, F1)-->  reference_rv64.py
    reference_rv64 --(z3 QF_BV lemmas, F3)------->  BTOR2 model

- `realizations/emulator/oracle.py` shells to `sail_riscv_sim` (trace-parsed
  per-step projections); binary pinned in the repo-root `Dockerfile`.
- `tools/sail_btor2_machine/sail_cross.py` audits every reference function
  against Sail on random + corner inputs (463 cases, **0 divergences**), and is
  non-vacuous (a deliberately-wrong shamt width is caught). The machine gate
  records this as `reference_vs_sail_ok=True`.
- The gate's **F1 differential** (`gate/fidelity/f1_tested.py`) validates the
  realization against Sail on a gate-owned **held-out** instance partition
  (`oracle_service.Partitioner`); 150/150 held-out instances agree with Sail.

So the "stands in for Sail" caveat is discharged honestly: the reference is
pinned to real Sail concretely while the all-inputs F3 proofs are kept. The
single remaining substitution option (a *symbolic* Sail extraction via
`sail -smt` / Isla) is noted but not required by this chain.

## Instruction list — per-instruction status (z3 QF_BV lemma)

All 43 PROVEN (lemma `encode != reference` is UNSAT over all inputs):

| Group | Instructions | Status |
|---|---|---|
| RV64I reg-reg ALU | ADD SUB SLL SLT SLTU XOR SRL SRA OR AND | PROVEN (10) |
| RV64I reg-imm ALU | ADDI SLTI SLTIU XORI ORI ANDI SLLI SRLI SRAI | PROVEN (9) |
| RV64I word ops | ADDW SUBW SLLW SRLW SRAW ADDIW SLLIW SRLIW SRAIW | PROVEN (9) |
| U-type | LUI AUIPC | PROVEN (2) |
| RV64M multiply | MUL MULH MULHU MULHSU | PROVEN (4) |
| RV64M divide | DIV DIVU REM REMU | PROVEN (4) |
| RV64M W-variants | MULW DIVW DIVUW REMW REMUW | PROVEN (5) |

FAILED: none.

## QF_BV lemma counts

- Per-instruction execute lemmas discharged by z3: **43 / 43** (all UNSAT).
- IDF points subtracted: **0** (no allowlisted point names an instruction in
  this ALU slice).
- Harness lemma (fetch/decode/pc/control == reference `step`): **NOT discharged**
  (`harness_lemma_ok = None`). Next slice.

The lemmas are non-vacuous: a negative control (SRA spec wired to the SRL
execute) is correctly reported as a divergence with a counterexample.

## What z3 proved (the lowering-sensitive corners, explicitly)

- RV64 SLL/SRL/SRA use the **low 6 bits** of the shift operand; W-shifts use
  the **low 5 bits** — verified, including that a 6-bit shamt on a W-shift would
  diverge.
- ADDW/SUBW/SLLW/SRLW/SRAW/MULW and the *IW immediates compute in 32 bits and
  **sign-extend** the 32-bit result to 64.
- SLT/SLTU/SLTI/SLTIU produce 64-bit 0/1 (signed vs unsigned compare).
- MULH/MULHU/MULHSU take the high 64 bits of the 128-bit product with the
  correct signedness per operand.
- DIV/REM corners: div-by-zero -> DIV/DIVU = all-ones (-1), REM/REMU = dividend;
  signed overflow INT_MIN/-1 -> DIV = INT_MIN, REM = 0. W-variants apply the
  same in 32 bits then sign-extend.
- LUI = sign-extended U-immediate; AUIPC = pc + that immediate.

## Surprises / encoding notes

- No first-encoding divergences survived to the report: each execute tree was
  written once and proven on the first solver run. The structure (one IR tree
  feeding both lowerings) makes a "BTOR2 disagrees with the proof" class of bug
  impossible by construction; the only divergence risk is "IR tree disagrees
  with reference," which the z3 lemma catches directly.
- Immediate ALU ops reuse the reg-reg execute tree with operand `b` bound to
  the already-extended 64-bit immediate; the reference does the same, so the
  lemma domains match exactly (no separate immediate-decode lemma in this
  slice — immediate field extraction belongs to the fetch/decode harness, the
  next slice).
- z3's BV `/`, `>>`, and `SRem` are signed; `UDiv`/`LShR`/`URem` are unsigned —
  the IR distinguishes `sdiv`/`udiv`, `sra`/`srl`, `srem`/`urem` explicitly so
  the BTOR2 op names match.

## Next slice (explicitly deferred — do NOT assume done)

1. **Fetch/decode/pc/control harness lemma**: a full
   fetch-from-symbolic-memory + decode-dispatch + writeback transition, proven
   equal to the reference `step`. The emitted `model.btor2` currently declares
   the state skeleton and the execute datapaths but no dispatch `next` logic.
2. **Control flow**: BRANCH (BEQ/BNE/...), JAL, JALR.
3. **Loads / stores** over the memory array (alignment, sign/zero extension).
4. **CSRs, traps, privileged**; **FP** (F/D).
5. ~~Wire the Sail emulator~~ **DONE (2026-06-15)**: the emulator oracle is
   wired and `reference_rv64.py` is cross-validated against Sail v0.12
   (`reference_vs_sail_ok=True`). A *symbolic* Sail extraction remains optional.

Item 5 has landed; item 1 (the harness lemma) has not, so `GROUP.yaml` keeps
`equivalence: PARTIAL` (not GREEN) — honestly. GREEN requires all of: every F3
lemma proven (done), reference cross-validated vs Sail (done), AND the harness
lemma discharged (item 1, pending).
